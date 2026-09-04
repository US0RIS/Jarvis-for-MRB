from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

TTS_URL = os.environ.get("JARVIS_TTS_URL", "http://127.0.0.1:8880").rstrip("/")
TTS_MODEL = os.environ.get("JARVIS_TTS_MODEL", "kokoro")
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "bm_george")
TTS_SPEED = float(os.environ.get("JARVIS_TTS_SPEED", "1.04"))


def tts_health() -> bool:
    """Return true only when the configured low-latency TTS service is ready.

    Kokoro-FastAPI exposes a lightweight /health endpoint. Explicitly reject the
    older Qwen3-TTS server if it is still occupying port 8880 so Jarvis does not
    report a false-positive healthy voice and then fail every synthesis request.
    """
    try:
        response = httpx.get(f"{TTS_URL}/health", timeout=0.20)
        if response.status_code >= 400:
            return False
        payload = response.json()
        if not isinstance(payload, dict):
            return False

        # Qwen3-TTS health includes backend.model_id. Reject it now that Kokoro is
        # the default runtime even though that older server may itself be healthy.
        backend = payload.get("backend")
        if isinstance(backend, dict):
            model_id = str(backend.get("model_id") or "").lower()
            if "qwen" in model_id:
                return False
            if "ready" in backend:
                return bool(backend.get("ready"))

        status = str(payload.get("status") or "").lower()
        return status in {"healthy", "ready", "ok"}
    except (httpx.HTTPError, ValueError):
        return False


def _wsl_start_command() -> list[str] | None:
    if sys.platform != "win32":
        return None

    shell = r"""
set -e
ROOT="$HOME/.local/share/jarvis/kokoro-fastapi"
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then exit 2; fi
if curl -fsS http://127.0.0.1:8880/health >/dev/null 2>&1; then exit 0; fi
cd "$ROOT"
nohup env \
  USE_GPU=true \
  PYTHONPATH="$ROOT:$ROOT/api" \
  MODEL_DIR=src/models \
  VOICES_DIR=src/voices/v1_0 \
  WEB_PLAYER_PATH="$ROOT/web" \
  "$PY" -m uvicorn api.src.main:app --host 127.0.0.1 --port 8880 \
  > "$HOME/.local/share/jarvis/kokoro-fastapi.log" 2>&1 &
""".strip()
    return ["wsl.exe", "bash", "-lc", shell]


def ensure_tts_server(wait_seconds: float = 0.0) -> bool:
    if tts_health():
        return True
    if os.environ.get("JARVIS_TTS_AUTOSTART", "1").strip().lower() in {"0", "false", "no"}:
        return False
    command = _wsl_start_command()
    if not command:
        return False
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except OSError:
        return False

    deadline = time.monotonic() + max(0.0, wait_seconds)
    while time.monotonic() < deadline:
        if tts_health():
            return True
        time.sleep(0.15)
    return tts_health()


def synthesize_wav(text: str) -> bytes:
    """Synthesize one short Jarvis speech segment with Kokoro-82M.

    Kokoro is intentionally used instead of Qwen3-TTS here. On an RTX 5080 the
    82M model has negligible VRAM pressure next to the planner and its FastAPI
    implementation is designed for sub-second first audio. The iPhone still owns
    playback and barge-in, so changing the model does not weaken interruption.
    """
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
