from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator

import httpx

from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.conversation import append_message, recent_messages
from jarvis_mrb.server_config import load_server_config

_SERVER_CONFIG = load_server_config()
SERVICE_URL = os.environ.get("JARVIS_SERVICE_URL", "http://127.0.0.1:8765").rstrip("/")
API_TOKEN = (os.environ.get("JARVIS_API_TOKEN") or _SERVER_CONFIG.api_token).strip()
CLI_SESSION_ID = "cli"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}


def _service_ready() -> bool:
    try:
        response = httpx.get(f"{SERVICE_URL}/health", timeout=0.6)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _start_service() -> None:
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        [sys.executable, "-m", "jarvis_mrb.service"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
    for _ in range(30):
        if _service_ready():
            return
        time.sleep(0.1)


def _fallback_local(text: str) -> str:
    history = recent_messages(CLI_SESSION_ID, limit=20)
    reply = handle_natural_language(text, history=history)
    append_message(CLI_SESSION_ID, "user", text)
    if reply.message and reply.message != "__EXIT__":
        append_message(CLI_SESSION_ID, "assistant", reply.message)
    return reply.message


def _stream_service(text: str) -> Iterator[str]:
    if not _service_ready() and SERVICE_URL.startswith("http://127.0.0.1"):
        _start_service()

    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=3.0)) as client:
            with client.stream(
                "POST",
                f"{SERVICE_URL}/command/stream",
                json={"text": text, "session_id": CLI_SESSION_ID},
                headers=_headers(),
            ) as response:
                response.raise_for_status()
                emitted = False
                for line in response.iter_lines():
                    if not line:
                        continue
                    packet = json.loads(line)
                    if packet.get("type") == "delta":
                        piece = str(packet.get("text") or "")
                        if piece:
                            emitted = True
                            yield piece
                    elif packet.get("type") == "done":
                        return
                if emitted:
                    return
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        pass

    if SERVICE_URL.startswith("http://127.0.0.1"):
        fallback = _fallback_local(text)
        if fallback and fallback != "__EXIT__":
            yield fallback
        return
    yield "Jarvis service is unreachable or rejected authentication."


def main() -> None:
    print("Jarvis for MRB — milestone 11")
    print("Persistent presence enabled. Type 'exit' to quit.")

    while True:
        try:
            raw = input("jarvis> ")
            if raw.strip().lower() in {"quit", "exit"}:
                print("Goodbye.")
                return

            wrote = False
            for piece in _stream_service(raw):
                print(piece, end="", flush=True)
                wrote = True
            if wrote:
                print()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return


if __name__ == "__main__":
    main()
