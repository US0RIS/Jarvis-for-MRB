from __future__ import annotations

"""World Armor v7 live fabric: durable event journal + explicit supervisor.

One explicitly enabled controller process can keep the already-authorized
World Armor collectors alive. Source enrollment/grants remain authoritative;
the supervisor does not discover sources, widen rights, create watches, or
grant actions. It only runs existing due collectors and journals bounded
metadata receipts for resumable real-time delivery.
"""

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any
from uuid import uuid4

from jarvis_mrb import world_model

LIVE_STORE = Path(world_model.DB_PATH).with_name("world_armor_live.sqlite3")
_MAX_EVENTS = 10_000
_MAX_EVENT_AGE_DAYS = 14
_MAX_PAYLOAD_BYTES = 16_384
_DEFAULT_INTERVAL_SECONDS = 5
_STATE_ID = 1

_runner_lock = threading.RLock()
_runner_thread: threading.Thread | None = None
_runner_stop = threading.Event()


def _now(value: datetime | None = None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("World Armor live timestamps must be offset-aware.")
    return instant.astimezone(timezone.utc)


def enabled() -> bool:
    return (
        os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1"
        and os.getenv("JARVIS_WORLD_ARMOR_LIVE_ENABLED") == "1"
    )


def autostart_enabled() -> bool:
    return enabled() and os.getenv("JARVIS_WORLD_ARMOR_LIVE_AUTOSTART") == "1"


def _connect(path: Path = LIVE_STORE) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA secure_delete=ON")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS live_events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL,
          subsystem TEXT NOT NULL,
          source_id TEXT,
          status TEXT NOT NULL,
          priority TEXT NOT NULL,
          created_at TEXT NOT NULL,
          summary TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_live_events_created
          ON live_events(created_at,seq);

        CREATE TABLE IF NOT EXISTS supervisor_state (
          id INTEGER PRIMARY KEY CHECK(id=1),
          running INTEGER NOT NULL DEFAULT 0,
          process_id INTEGER,
          started_at TEXT,
          heartbeat_at TEXT,
          cycle_count INTEGER NOT NULL DEFAULT 0,
          last_cycle_ms INTEGER,
          last_error TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL
        );
        """
    )
    con.commit()
    return con


def _json_payload(payload: dict[str, Any] | None) -> str:
    value = payload if isinstance(payload, dict) else {}
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    )
    if len(raw.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raw = json.dumps({
            "truncated": True,
            "keys": sorted(str(key)[:100] for key in value)[:100],
        }, separators=(",", ":"))
    return raw


def _present(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    try:
        payload = json.loads(str(item.pop("payload_json", "{}")))
    except (json.JSONDecodeError, TypeError):
        payload = {}
    item["payload"] = payload if isinstance(payload, dict) else {}
    item["seq"] = int(item["seq"])
    return item


def _prune(con: sqlite3.Connection, instant: datetime) -> None:
    cutoff = (instant - timedelta(days=_MAX_EVENT_AGE_DAYS)).isoformat()
    con.execute("DELETE FROM live_events WHERE created_at<?", (cutoff,))
    excess = con.execute(
        "SELECT MAX(0, COUNT(*)-?) FROM live_events", (_MAX_EVENTS,)
    ).fetchone()[0]
    if excess:
        con.execute(
            "DELETE FROM live_events WHERE seq IN "
            "(SELECT seq FROM live_events ORDER BY seq LIMIT ?)",
            (int(excess),),
        )


def publish_event(
    kind: str, *, subsystem: str, status: str,
    summary: str, priority: str = "info",
    source_id: str | None = None,
    payload: dict[str, Any] | None = None,
    now: datetime | None = None,
    db_path: Path | None = None,
    fanout: bool = True,
) -> dict[str, Any]:
    if priority not in {"info", "warning", "urgent"}:
        raise ValueError("Live event priority must be info, warning or urgent.")
    for label, value, maximum in (
        ("kind", kind, 80), ("subsystem", subsystem, 80),
        ("status", status, 100), ("summary", summary, 700),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f"Invalid live event {label}.")
    source = None if source_id is None else str(source_id)[:160]
    instant = _now(now)
    path = Path(db_path) if db_path is not None else LIVE_STORE
    event_id = uuid4().hex
    with closing(_connect(path)) as con, con:
        cur = con.execute(
            """INSERT INTO live_events
               (event_id,kind,subsystem,source_id,status,priority,
                created_at,summary,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                event_id, kind.strip(), subsystem.strip(), source,
                status.strip(), priority, instant.isoformat(),
                summary.strip(), _json_payload(payload),
            ),
        )
        _prune(con, instant)
        row = con.execute(
            "SELECT * FROM live_events WHERE seq=?", (cur.lastrowid,)
        ).fetchone()
    event = _present(row)
    if fanout:
        try:
            from jarvis_mrb.event_bus import companion_events
            companion_events.publish({
                "type": "world_armor_event",
                "event": event,
                "message": event["summary"],
                "severity": event["priority"],
                "cue": "attention" if priority != "info" else "world_update",
            })
        except Exception:
            # Durable journal is the source of truth; live fanout is best effort.
            pass
    return event


def events(
    *, after_seq: int = 0, limit: int = 100,
    db_path: Path | None = None,
) -> dict[str, Any]:
    if type(after_seq) is not int or after_seq < 0:
        raise ValueError("after_seq must be a non-negative integer.")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("event limit must be 1–500.")
    path = Path(db_path) if db_path is not None else LIVE_STORE
    if not path.exists():
        return {
            "events": [], "next_seq": after_seq,
            "truncated": False, "retention_days": _MAX_EVENT_AGE_DAYS,
        }
    with closing(_connect(path)) as con:
        rows = con.execute(
            "SELECT * FROM live_events WHERE seq>? "
            "ORDER BY seq LIMIT ?",
            (after_seq, limit + 1),
        ).fetchall()
    chosen = rows[:limit]
    next_seq = int(chosen[-1]["seq"]) if chosen else after_seq
    return {
        "events": [_present(row) for row in chosen],
        "next_seq": next_seq,
        "truncated": len(rows) > limit,
        "retention_days": _MAX_EVENT_AGE_DAYS,
    }


def _state(path: Path = LIVE_STORE) -> dict[str, Any]:
    if not path.exists():
        return {
            "running": False, "cycle_count": 0, "heartbeat_at": None,
            "last_cycle_ms": None, "last_error": "",
        }
    with closing(_connect(path)) as con:
        row = con.execute(
            "SELECT * FROM supervisor_state WHERE id=?", (_STATE_ID,)
        ).fetchone()
    if row is None:
        return {
            "running": False, "cycle_count": 0, "heartbeat_at": None,
            "last_cycle_ms": None, "last_error": "",
        }
    result = dict(row)
    result["running"] = bool(result["running"])
    return result


def status(*, db_path: Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else LIVE_STORE
    state = _state(path)
    heartbeat = state.get("heartbeat_at")
    heartbeat_age: float | None = None
    if heartbeat:
        try:
            heartbeat_age = max(
                0.0,
                (_now() - datetime.fromisoformat(str(heartbeat))).total_seconds(),
            )
        except (ValueError, TypeError):
            heartbeat_age = None
    with closing(_connect(path)) as con:
        latest = con.execute(
            "SELECT COALESCE(MAX(seq),0),COUNT(*) FROM live_events"
        ).fetchone()
    state.update({
        "enabled": enabled(),
        "autostart_enabled": autostart_enabled(),
        "heartbeat_age_seconds": heartbeat_age,
        "journal_events": int(latest[1]),
        "latest_seq": int(latest[0]),
        "event_retention_days": _MAX_EVENT_AGE_DAYS,
        "source_authority_expansion": False,
        "remote_action_authority": False,
    })
    return state


def _heartbeat(
    *, path: Path, running: bool, cycle_ms: int | None = None,
    error: str = "", started_at: str | None = None,
) -> None:
    instant = _now().isoformat()
    with closing(_connect(path)) as con, con:
        current = con.execute(
            "SELECT * FROM supervisor_state WHERE id=?", (_STATE_ID,)
        ).fetchone()
        cycles = int(current["cycle_count"]) if current else 0
        if cycle_ms is not None:
            cycles += 1
        con.execute(
            """INSERT INTO supervisor_state
               (id,running,process_id,started_at,heartbeat_at,cycle_count,
                last_cycle_ms,last_error,updated_at)
               VALUES(1,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 running=excluded.running,
                 process_id=excluded.process_id,
                 started_at=COALESCE(supervisor_state.started_at,excluded.started_at),
                 heartbeat_at=excluded.heartbeat_at,
                 cycle_count=excluded.cycle_count,
                 last_cycle_ms=COALESCE(excluded.last_cycle_ms,
                                        supervisor_state.last_cycle_ms),
                 last_error=excluded.last_error,
                 updated_at=excluded.updated_at""",
            (
                int(running), os.getpid() if running else None,
                started_at or (current["started_at"] if current else instant),
                instant, cycles, cycle_ms,
                str(error)[:1000], instant,
            ),
        )


def _summary_for_result(
    subsystem: str, result: dict[str, Any],
) -> tuple[str, str, str]:
    status_value = str(result.get("status") or result.get("outcome") or "unknown")
    source_id = str(
        result.get("source_id") or result.get("watch_id") or ""
    )[:160]
    if subsystem == "movement":
        summary = (
            f"Movement source {source_id or 'unknown'}: {status_value}; "
            f"{int(result.get('observations_saved') or 0)} new positions."
        )
    elif subsystem == "camera":
        summary = (
            f"Camera source {source_id or 'unknown'}: {status_value}; "
            + (
                "new environmental/infrastructure evidence."
                if result.get("observation_saved") or result.get("evidence_saved")
                else "check completed."
            )
        )
    else:
        summary = (
            f"Standing watch {source_id or 'unknown'}: "
            f"{str(result.get('change_state') or status_value)}."
        )
    bad = {
        "unavailable", "not_collected", "worker_or_provider_error",
        "sample_degraded_or_partial", "collection_failed",
    }
    priority = "warning" if (
        status_value in bad
        or status_value.startswith("collection_failed")
        or "degraded" in status_value
    ) else "info"
    return status_value, summary, priority


def _journal_results(
    subsystem: str, results: list[dict[str, Any]],
    *, path: Path, now: datetime,
) -> int:
    count = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        status_value, summary, priority = _summary_for_result(
            subsystem, result
        )
        source_id = (
            result.get("source_id") or result.get("watch_id")
        )
        payload = {
            key: value for key, value in result.items()
            if key not in {
                "provider_payload", "evaluation", "raw_image",
                "frame", "image", "locator",
            }
        }
        publish_event(
            f"{subsystem}_receipt",
            subsystem=subsystem,
            source_id=str(source_id) if source_id else None,
            status=status_value,
            priority=priority,
            summary=summary,
            payload=payload,
            now=now,
            db_path=path,
        )
        count += 1
    return count


def _run_watch_batch(*, limit: int, now: datetime) -> list[dict[str, Any]]:
    if os.getenv("JARVIS_WORLD_ARMOR_WATCHES_ENABLED") != "1":
        return []
    from jarvis_mrb.world_armor_watches import run_due_once
    results: list[dict[str, Any]] = []
    for _ in range(limit):
        result = run_due_once(now=now)
        if not result.get("checked"):
            break
        results.append(result)
        if int(result.get("notices_created") or 0) > 0:
            try:
                from jarvis_mrb.world_armor_attention import list_notices
                notices = list_notices(
                    watch_id=str(result["id"] if "id" in result else result["watch_id"]),
                    unread_only=True,
                    now=now,
                ).get("notices") or []
                if notices:
                    notice = notices[0]
                    publish_event(
                        "attention_notice",
                        subsystem="watch",
                        source_id=str(result.get("watch_id") or result.get("id") or ""),
                        status="attention",
                        priority="warning",
                        summary=str(notice.get("summary") or "World Armor attention notice.")[:700],
                        payload={
                            "notice_id": notice.get("id"),
                            "watch_id": notice.get("watch_id"),
                            "investigation_id": notice.get("investigation_id"),
                            "source": notice.get("source"),
                            "kind": notice.get("kind"),
                            "observed_at": notice.get("observed_at"),
                            "received_at": notice.get("received_at"),
                        },
                        now=now,
                    )
            except Exception:
                pass
    return results


def run_cycle(
    *, movement_limit: int = 16, camera_limit: int = 8,
    watch_limit: int = 4, now: datetime | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    if not enabled():
        raise RuntimeError(
            "World Armor live fabric is off; set JARVIS_WORLD_ARMOR_LIVE_ENABLED=1."
        )
    if any(type(value) is not int or value < 1 for value in (
        movement_limit, camera_limit, watch_limit
    )):
        raise ValueError("Supervisor batch limits must be positive integers.")
    path = Path(db_path) if db_path is not None else LIVE_STORE
    instant = _now(now)
    started = time.perf_counter()
    result: dict[str, Any] = {
        "started_at": instant.isoformat(),
        "movement": None, "cameras": None, "watches": [],
        "events_created": 0,
    }
    errors: list[str] = []

    if (
        os.getenv("JARVIS_WORLD_ARMOR_PLATFORM_ENABLED") == "1"
        and os.getenv("JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED") == "1"
    ):
        try:
            from jarvis_mrb.world_armor_distributed import run_due
            movement = run_due(limit=movement_limit, now=now)
            result["movement"] = movement
            result["events_created"] += _journal_results(
                "movement", movement.get("checks") or [],
                path=path, now=instant,
            )
        except Exception as exc:
            errors.append("movement:" + type(exc).__name__)
            publish_event(
                "collector_degraded", subsystem="movement",
                status="degraded", priority="warning",
                summary="World Armor movement collector cycle failed.",
                payload={"error_type": type(exc).__name__},
                now=instant, db_path=path,
            )

    if (
        os.getenv("JARVIS_WORLD_ARMOR_PLATFORM_ENABLED") == "1"
        and os.getenv("JARVIS_WORLD_ARMOR_CAMERAS_ENABLED") == "1"
    ):
        try:
            from jarvis_mrb.world_armor_distributed import run_camera_due
            cameras = run_camera_due(limit=camera_limit, now=now)
            result["cameras"] = cameras
            result["events_created"] += _journal_results(
                "camera", cameras.get("checks") or [],
                path=path, now=instant,
            )
        except Exception as exc:
            errors.append("camera:" + type(exc).__name__)
            publish_event(
                "collector_degraded", subsystem="camera",
                status="degraded", priority="warning",
                summary="World Armor camera collector cycle failed.",
                payload={"error_type": type(exc).__name__},
                now=instant, db_path=path,
            )

    try:
        watches = _run_watch_batch(limit=watch_limit, now=instant)
        result["watches"] = watches
        result["events_created"] += _journal_results(
            "watch", watches, path=path, now=instant,
        )
    except Exception as exc:
        errors.append("watch:" + type(exc).__name__)
        publish_event(
            "collector_degraded", subsystem="watch",
            status="degraded", priority="warning",
            summary="World Armor standing-watch collector cycle failed.",
            payload={"error_type": type(exc).__name__},
            now=instant, db_path=path,
        )

    cycle_ms = max(0, int((time.perf_counter() - started) * 1000))
    result["cycle_ms"] = cycle_ms
    result["errors"] = errors
    _heartbeat(
        path=path, running=True, cycle_ms=cycle_ms,
        error=";".join(errors),
    )
    return result


def _loop(
    *, interval_seconds: int, movement_limit: int,
    camera_limit: int, watch_limit: int, db_path: Path,
) -> None:
    started_at = _now().isoformat()
    _heartbeat(path=db_path, running=True, started_at=started_at)
    try:
        while not _runner_stop.is_set():
            cycle_start = time.monotonic()
            try:
                run_cycle(
                    movement_limit=movement_limit,
                    camera_limit=camera_limit,
                    watch_limit=watch_limit,
                    db_path=db_path,
                )
            except Exception as exc:
                _heartbeat(
                    path=db_path, running=True,
                    error=type(exc).__name__ + ":" + str(exc)[:500],
                    started_at=started_at,
                )
            elapsed = time.monotonic() - cycle_start
            _runner_stop.wait(max(0.2, interval_seconds - elapsed))
    finally:
        _heartbeat(path=db_path, running=False, started_at=started_at)


def start_supervisor(
    *, interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
    movement_limit: int = 16, camera_limit: int = 8,
    watch_limit: int = 4, db_path: Path | None = None,
) -> bool:
    if not enabled():
        return False
    if type(interval_seconds) is not int or not 1 <= interval_seconds <= 3600:
        raise ValueError("World Armor live interval must be 1–3600 seconds.")
    path = Path(db_path) if db_path is not None else LIVE_STORE
    global _runner_thread
    with _runner_lock:
        if _runner_thread is not None and _runner_thread.is_alive():
            return True
        _runner_stop.clear()
        _runner_thread = threading.Thread(
            target=_loop,
            kwargs={
                "interval_seconds": interval_seconds,
                "movement_limit": movement_limit,
                "camera_limit": camera_limit,
                "watch_limit": watch_limit,
                "db_path": path,
            },
            name="world-armor-live-supervisor",
            daemon=True,
        )
        _runner_thread.start()
    return True


def stop_supervisor(*, db_path: Path | None = None) -> None:
    global _runner_thread
    path = Path(db_path) if db_path is not None else LIVE_STORE
    with _runner_lock:
        _runner_stop.set()
        thread = _runner_thread
    if thread and thread.is_alive():
        thread.join(timeout=2.0)
    with _runner_lock:
        if _runner_thread is thread:
            _runner_thread = None
    _heartbeat(path=path, running=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit World Armor always-on live fabric supervisor."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=int,
                        default=_DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--movement-limit", type=int, default=16)
    parser.add_argument("--camera-limit", type=int, default=8)
    parser.add_argument("--watch-limit", type=int, default=4)
    args = parser.parse_args()
    if args.once == args.loop:
        parser.error("Choose exactly one of --once or --loop.")
    if not enabled():
        parser.error(
            "Set JARVIS_WORLD_ARMOR_ENABLED=1 and "
            "JARVIS_WORLD_ARMOR_LIVE_ENABLED=1 first."
        )
    if args.once:
        print(run_cycle(
            movement_limit=args.movement_limit,
            camera_limit=args.camera_limit,
            watch_limit=args.watch_limit,
        ), flush=True)
        return
    start_supervisor(
        interval_seconds=args.interval_seconds,
        movement_limit=args.movement_limit,
        camera_limit=args.camera_limit,
        watch_limit=args.watch_limit,
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop_supervisor()


if __name__ == "__main__":
    main()
