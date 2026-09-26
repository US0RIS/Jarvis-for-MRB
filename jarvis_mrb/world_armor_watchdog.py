from __future__ import annotations

"""Process-level watchdog for the World Armor live supervisor.

This is an optional deployment wrapper.  It does not grant source rights or
start collection unless the normal World Armor/live feature flags are already
enabled.  Run it under the host's ordinary service manager; it starts exactly
one live-supervisor child, restarts unexpected exits with capped exponential
backoff, and writes a small local status record.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from jarvis_mrb import world_model

STATUS_PATH = Path(world_model.DB_PATH).with_name("world_armor_watchdog.json")
LOCK_PATH = Path(world_model.DB_PATH).with_name("world_armor_watchdog.lock")
_MAX_BACKOFF_SECONDS = 60
_STABLE_RESET_SECONDS = 120


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def restart_backoff(consecutive_failures: int) -> int:
    if type(consecutive_failures) is not int or consecutive_failures < 0:
        raise ValueError("consecutive_failures must be a non-negative integer.")
    if consecutive_failures == 0:
        return 0
    return min(_MAX_BACKOFF_SECONDS, 2 ** min(consecutive_failures - 1, 6))


def _pid_alive(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        return False


def _acquire_lock(path: Path = LOCK_PATH) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            raw = path.read_text(encoding="utf-8").strip()
            pid = int(raw)
        except (OSError, ValueError):
            pid = 0
        if pid and _pid_alive(pid):
            raise RuntimeError(
                f"World Armor watchdog already appears active as PID {pid}."
            )
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError("Cannot clear stale World Armor watchdog lock.") from exc
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, str(os.getpid()).encode("ascii"))
    os.fsync(fd)
    return fd


def _release_lock(fd: int, path: Path = LOCK_PATH) -> None:
    try:
        os.close(fd)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_status(value: dict[str, Any], path: Path = STATUS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def status(path: Path = STATUS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "watchdog_seen": False,
            "watchdog_running": False,
            "child_running": False,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {
            "watchdog_seen": True,
            "watchdog_running": False,
            "child_running": False,
            "status_corrupt": True,
        }
    if not isinstance(value, dict):
        value = {}
    watchdog_pid = int(value.get("watchdog_pid") or 0)
    child_pid = int(value.get("child_pid") or 0)
    value["watchdog_seen"] = True
    value["watchdog_running"] = _pid_alive(watchdog_pid)
    value["child_running"] = _pid_alive(child_pid)
    return value


def _command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "-m", "jarvis_mrb.world_armor_live",
        "--loop",
        "--interval-seconds", str(args.interval_seconds),
        "--movement-limit", str(args.movement_limit),
        "--camera-limit", str(args.camera_limit),
        "--watch-limit", str(args.watch_limit),
    ]


def run(args: argparse.Namespace) -> int:
    if os.getenv("JARVIS_WORLD_ARMOR_ENABLED") != "1" or (
        os.getenv("JARVIS_WORLD_ARMOR_LIVE_ENABLED") != "1"
    ):
        raise RuntimeError(
            "World Armor and its live fabric must be explicitly enabled first."
        )
    if os.getenv("JARVIS_WORLD_ARMOR_LIVE_AUTOSTART") == "1":
        raise RuntimeError(
            "Disable JARVIS_WORLD_ARMOR_LIVE_AUTOSTART when using the "
            "separate process watchdog, so only one supervisor owns collection."
        )

    lock_fd = _acquire_lock(Path(args.lock_path))
    child: subprocess.Popen[bytes] | None = None
    stopping = False
    restarts = 0
    failures = 0
    last_exit: int | None = None
    status_path = Path(args.status_path)

    def request_stop(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            try:
                child.terminate()
            except OSError:
                pass

    prior_sigint = signal.signal(signal.SIGINT, request_stop)
    prior_sigterm = signal.signal(signal.SIGTERM, request_stop)
    try:
        while not stopping:
            started = time.monotonic()
            child = subprocess.Popen(
                _command(args),
                stdin=subprocess.DEVNULL,
                stdout=None,
                stderr=None,
                close_fds=(os.name != "nt"),
            )
            _write_status({
                "schema": "jarvis.world_armor.watchdog.v1",
                "watchdog_pid": os.getpid(),
                "child_pid": child.pid,
                "child_started_at": _now(),
                "restart_count": restarts,
                "consecutive_failures": failures,
                "last_exit_code": last_exit,
                "updated_at": _now(),
            }, status_path)

            while not stopping:
                code = child.poll()
                if code is not None:
                    last_exit = int(code)
                    break
                _write_status({
                    "schema": "jarvis.world_armor.watchdog.v1",
                    "watchdog_pid": os.getpid(),
                    "child_pid": child.pid,
                    "child_started_at": _now(),
                    "restart_count": restarts,
                    "consecutive_failures": failures,
                    "last_exit_code": last_exit,
                    "updated_at": _now(),
                }, status_path)
                time.sleep(5)

            if stopping:
                break
            runtime = time.monotonic() - started
            failures = 1 if runtime >= _STABLE_RESET_SECONDS else failures + 1
            restarts += 1
            delay = restart_backoff(failures)
            _write_status({
                "schema": "jarvis.world_armor.watchdog.v1",
                "watchdog_pid": os.getpid(),
                "child_pid": 0,
                "restart_count": restarts,
                "consecutive_failures": failures,
                "last_exit_code": last_exit,
                "restart_after_seconds": delay,
                "updated_at": _now(),
            }, status_path)
            deadline = time.monotonic() + delay
            while not stopping and time.monotonic() < deadline:
                time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    finally:
        if child is not None and child.poll() is None:
            try:
                child.terminate()
                child.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    child.kill()
                except OSError:
                    pass
        _write_status({
            "schema": "jarvis.world_armor.watchdog.v1",
            "watchdog_pid": os.getpid(),
            "child_pid": 0,
            "restart_count": restarts,
            "consecutive_failures": failures,
            "last_exit_code": last_exit,
            "stopped_at": _now(),
            "updated_at": _now(),
        }, status_path)
        signal.signal(signal.SIGINT, prior_sigint)
        signal.signal(signal.SIGTERM, prior_sigterm)
        _release_lock(lock_fd, Path(args.lock_path))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restarting process watchdog for World Armor live fabric."
    )
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--movement-limit", type=int, default=16)
    parser.add_argument("--camera-limit", type=int, default=8)
    parser.add_argument("--watch-limit", type=int, default=4)
    parser.add_argument("--status-path", default=str(STATUS_PATH))
    parser.add_argument("--lock-path", default=str(LOCK_PATH))
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    for value in (
        args.interval_seconds, args.movement_limit,
        args.camera_limit, args.watch_limit,
    ):
        if type(value) is not int or value < 1:
            parser.error("Intervals and batch limits must be positive integers.")
    if args.interval_seconds > 3600:
        parser.error("Interval must be at most 3600 seconds.")
    if args.status:
        print(json.dumps(status(Path(args.status_path)), indent=2, sort_keys=True))
        return
    try:
        raise SystemExit(run(args))
    except RuntimeError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
