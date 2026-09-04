from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

TTS_URL = os.environ.get("JARVIS_TTS_URL", "http://127.0.0.1:8880").rstrip("/")
TTS_MODEL = os.environ.get("JARVIS_TTS_MODEL", "qwen3-tts")
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "Ryan")
TTS_SPEED = float(os.environ.get("JARVIS_TTS_SPEED", "1.0"))
TTS_INSTRUCT = os.environ.get(
    "JARVIS_TTS_INSTRUCT",
    "A composed adult male personal aide. Refined and understated. Calm, precise, warm but restrained, "
    "crisp diction, measured pacing, authoritative without sounding theatrical. Keep the delivery natural "
    "and conversational; avoid exaggerated emotion or announcer-style delivery.",
)


def tts_health() -> bool:
    """Return true only when the server process *and model* are ready."""
    try:
        response = httpx.get(f"{TTS_URL}/health", timeout=1.0)
        if response.status_code >= 400:
            return False
        payload = response.json()
        backend = payload.get("backend") if isinstance(payload, dict) else None
        if isinstance(backend, dict) and "ready" in backend:
            return bool(backend.get("ready"))
        # Backward-compatible fallback for a server build that only exposes a
        # textual health status.
        status = str(payload.get("status") or "").lower() if isinstance(payload, dict) else ""
        return status in {"healthy", "ready", "ok"}
    except (httpx.HTTPError, ValueError):
        return False


def _wsl_start_command() -> list[str] | None:
    if sys.platform != "win32":
        return None
    # setup-qwen3-tts-wsl.ps1 installs the service here. Start it detached inside
    # WSL so the normal Jarvis Windows service can own the user-facing port while
    # the model server remains localhost-only.
    shell = r"""
set -e
ROOT="$HOME/.local/share/jarvis/qwen3-tts"
if [ ! -x "$ROOT/.venv/bin/python" ]; then exit 2; fi
# If a server process is already answering, do not launch a duplicate. Its model
# may still be warming; the Windows client polls backend.ready separately.
if curl -fsS http://127.0.0.1:8880/health >/dev/null 2>&1; then exit 0; fi
cd "$ROOT"
. .venv/bin/activate
nohup env \
  HOST=127.0.0.1 \
  PORT=8880 \
  TTS_BACKEND=official \
  TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice \
  TTS_WARMUP_ON_START=true \
  TTS_MAX_CONCURRENT=1 \
  python -m api.main > "$HOME/.local/share/jarvis/qwen3-tts.log" 2>&1 &
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
        time.sleep(0.25)
    return tts_health()


def synthesize_wav(text: str) -> bytes:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        raise ValueError("TTS text is empty")
    if not tts_health() and not ensure_tts_server(wait_seconds=1.0):
        raise RuntimeError("Local Qwen3-TTS model is not ready")

    # This server exposes Qwen's native style control as `instruct` rather than
    # OpenAI's `instructions` spelling. Ryan is the English male CustomVoice; the
    # instruction keeps him restrained enough for an always-on personal aide.
    payload = {
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "input": cleaned,
        "language": "English",
        "response_format": "wav",
        "speed": TTS_SPEED,
        "instruct": TTS_INSTRUCT,
    }
    timeout = httpx.Timeout(90.0, connect=2.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{TTS_URL}/v1/audio/speech", json=payload)
        response.raise_for_status()
        data = response.content
    if len(data) < 44:
        raise RuntimeError("Qwen3-TTS returned an invalid WAV response")
    return data
