from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.server_config import load_server_config

_SERVER_CONFIG = load_server_config()
SERVICE_URL = os.environ.get("JARVIS_SERVICE_URL", "http://127.0.0.1:8765").rstrip("/")
API_TOKEN = (os.environ.get("JARVIS_API_TOKEN") or _SERVER_CONFIG.api_token).strip()


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


def _ask_service(text: str) -> str:
    if not _service_ready() and SERVICE_URL.startswith("http://127.0.0.1"):
        _start_service()
    try:
        response = httpx.post(
            f"{SERVICE_URL}/command",
            json={"text": text},
            headers=_headers(),
            timeout=120.0,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("message", ""))
    except (httpx.HTTPError, ValueError):
        if SERVICE_URL.startswith("http://127.0.0.1"):
            return handle_natural_language(text).message
        return "Jarvis service is unreachable or rejected authentication."


def main() -> None:
    print("Jarvis for MRB — milestone 6")
    print("Speak naturally. Type 'help' for examples or 'exit' to quit.")

    while True:
        try:
            raw = input("jarvis> ")
            if raw.strip().lower() in {"quit", "exit"}:
                print("Goodbye.")
                return
            response = _ask_service(raw)
            if response and response != "__EXIT__":
                print(response)
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return


if __name__ == "__main__":
    main()
