from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import BinaryIO

import httpx

TTS_URL = os.environ.get("JARVIS_TTS_URL", "http://127.0.0.1:8880").rstrip("/")
TTS_MODEL = os.environ.get("JARVIS_TTS_MODEL", "kokoro")
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "bm_george")
TTS_SPEED = float(os.environ.get("JARVIS_TTS_SPEED", "1.04"))
_TTS_LAST_HEALTHY: bool | None = None
_TTS_PROCESS: subprocess.Popen | None = None
_TTS_MONITOR: threading.Thread | None = None
_TTS_LOG_HANDLE: BinaryIO | None = None
_WSL_HOME: str | None = None


def _record_health_transition(healthy: bool) -> None:
    """Clear a stale startup degradation once Kokoro is observably healthy."""
    global _TTS_LAST_HEALTHY
    previous = _TTS_LAST_HEALTHY
    _TTS_LAST_HEALTHY = bool(healthy)
    if healthy and previous is not True:
        try:
            from jarvis_mrb.runtime_health import record_success

            record_success("tts_start")
        except Exception:
            # TTS health itself must remain usable even if runtime-health telemetry
            # is unavailable during an early startup/migration edge case.
            pass


def tts_health() -> bool:
    """Return true only when the configured low-latency TTS service is ready.

    Kokoro-FastAPI exposes a lightweight /health endpoint. Explicitly reject the
    older Qwen3-TTS server if it is still occupying port 8880 so Jarvis does not
    report a false-positive healthy voice and then fail every synthesis request.
    """
    healthy = False
    try:
        response = httpx.get(f"{TTS_URL}/health", timeout=0.20)
        if response.status_code >= 400:
            _record_health_transition(False)
            return False
        payload = response.json()
        if not isinstance(payload, dict):
            _record_health_transition(False)
            return False

        backend = payload.get("backend")
        if isinstance(backend, dict):
            model_id = str(backend.get("model_id") or "").lower()
            if "qwen" in model_id:
                _record_health_transition(False)
                return False
            if "ready" in backend:
                healthy = bool(backend.get("ready"))
                _record_health_transition(healthy)
                return healthy

        status = str(payload.get("status") or "").lower()
        healthy = status in {"healthy", "ready", "ok"}
        _record_health_transition(healthy)
        return healthy
    except (httpx.HTTPError, ValueError):
        _record_health_transition(False)
        return False


def _wsl_home() -> str | None:
    """Resolve the default WSL user's home without routing through a shell.

    Python's Windows argv quoting plus ``bash -lc`` caused the Kokoro launcher to
    receive a truncated command on the deployed machine.  Resolve HOME once with
    ``printenv`` and use direct WSL argv for every subsequent process instead.
    """
    global _WSL_HOME
    if sys.platform != "win32":
        return None

    override = os.environ.get("JARVIS_WSL_HOME", "").strip()
    if override:
        return override.rstrip("/")
    if _WSL_HOME:
        return _WSL_HOME

    try:
        completed = subprocess.run(
            ["wsl.exe", "--exec", "printenv", "HOME"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=10.0,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None
    home = completed.stdout.strip()
    if not home.startswith("/"):
        return None
    _WSL_HOME = home.rstrip("/")
    return _WSL_HOME


def _wsl_prepare_command() -> list[str] | None:
    """Return Kokoro's upstream model validation command as direct WSL argv."""
    home = _wsl_home()
    if not home:
        return None

    root = f"{home}/.local/share/jarvis/kokoro-fastapi"
    python = f"{root}/.venv/bin/python"
    downloader = f"{root}/docker/scripts/download_model.py"
    model_dir = f"{root}/api/src/models/v1_0"
    return [
        "wsl.exe",
        "--exec",
        python,
        downloader,
        "--output",
        model_dir,
    ]


def _wsl_start_command() -> list[str] | None:
    """Return the proven Kokoro launch as direct WSL argv, with no shell parser."""
    home = _wsl_home()
    if not home:
        return None

    root = f"{home}/.local/share/jarvis/kokoro-fastapi"
    python = f"{root}/.venv/bin/python"
    return [
        "wsl.exe",
        "--exec",
        "env",
        "USE_GPU=true",
        f"PYTHONPATH={root}:{root}/api",
        "MODEL_DIR=src/models",
        "VOICES_DIR=src/voices/v1_0",
        f"WEB_PLAYER_PATH={root}/web",
        python,
        "-m",
        "uvicorn",
        "api.src.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8880",
        "--log-level",
        "info",
    ]


def _runtime_log_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home()) / "JarvisForMRB"
    base.mkdir(parents=True, exist_ok=True)
    return base / "kokoro-wsl.log"


def _prepare_wsl_runtime(timeout_seconds: float = 180.0) -> bool:
    command = _wsl_prepare_command()
    if not command:
        return False

    try:
        with _runtime_log_path().open("ab", buffering=0) as log:
            log.write(b"\n=== Jarvis Kokoro preflight ===\n")
            completed = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=max(1.0, timeout_seconds),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                check=False,
            )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _close_log_handle() -> None:
    global _TTS_LOG_HANDLE
    if _TTS_LOG_HANDLE is None:
        return
    try:
        _TTS_LOG_HANDLE.close()
    except OSError:
        pass
    _TTS_LOG_HANDLE = None


def _monitor_tts_child(process: subprocess.Popen, timeout_seconds: float = 120.0) -> None:
    """Observe asynchronous Kokoro warmup and publish recovery when ready."""
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    while time.monotonic() < deadline:
        returncode = process.poll()
        if returncode is not None:
            try:
                from jarvis_mrb.runtime_health import record_failure

                record_failure(
                    "tts_start",
                    f"Kokoro WSL child exited with code {returncode}; see {_runtime_log_path()}",
                )
            except Exception:
                pass
            _close_log_handle()
            return
        if tts_health():
            return
        time.sleep(0.25)


def _ensure_monitor(process: subprocess.Popen) -> None:
    global _TTS_MONITOR
    if _TTS_MONITOR is not None and _TTS_MONITOR.is_alive():
        return
    _TTS_MONITOR = threading.Thread(
        target=_monitor_tts_child,
        args=(process,),
        name="jarvis-kokoro-health",
        daemon=True,
    )
    _TTS_MONITOR.start()


def ensure_tts_server(wait_seconds: float = 0.0) -> bool:
    global _TTS_PROCESS, _TTS_LOG_HANDLE

    if tts_health():
        return True
    if os.environ.get("JARVIS_TTS_AUTOSTART", "1").strip().lower() in {"0", "false", "no"}:
        return False

    command = _wsl_start_command()
    if not command:
        return False

    # Do not launch duplicate Kokoro processes while the existing child is warming.
    # If the prior child exited, rerun the independently observable preflight and
    # then start the same direct argv shape that succeeds manually.
    if _TTS_PROCESS is None or _TTS_PROCESS.poll() is not None:
        if not _prepare_wsl_runtime():
            return False
        _close_log_handle()
        try:
            _TTS_LOG_HANDLE = _runtime_log_path().open("ab", buffering=0)
            _TTS_LOG_HANDLE.write(b"\n=== Jarvis Kokoro server start ===\n")
            _TTS_PROCESS = subprocess.Popen(
                command,
                stdout=_TTS_LOG_HANDLE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except OSError:
            _close_log_handle()
            _TTS_PROCESS = None
            return False

    _ensure_monitor(_TTS_PROCESS)

    deadline = time.monotonic() + max(0.0, wait_seconds)
    while time.monotonic() < deadline:
        if tts_health():
            return True
        if _TTS_PROCESS is not None and _TTS_PROCESS.poll() is not None:
            return False
        time.sleep(0.15)
    return tts_health()


def synthesize_wav(text: str) -> bytes:
    """Synthesize one short Jarvis speech segment with Kokoro-82M."""
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        raise ValueError("TTS text is empty")
    if not tts_health() and not ensure_tts_server(wait_seconds=0.8):
        raise RuntimeError("Local Kokoro voice model is not ready")

    payload = {
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "input": cleaned,
        "response_format": "wav",
        "speed": TTS_SPEED,
    }
    timeout = httpx.Timeout(20.0, connect=1.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{TTS_URL}/v1/audio/speech", json=payload)
        response.raise_for_status()
        data = response.content
    if len(data) < 44:
        raise RuntimeError("Kokoro returned an invalid WAV response")
    return data
