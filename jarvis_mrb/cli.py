from __future__ import annotations

import subprocess
import sys
import time

import httpx

from jarvis_mrb.agent import handle_natural_language


SERVICE_URL = "http://127.0.0.1:8765"


def _service_ready() -> bool:
    try:
        response = httpx.get(f"{SERVICE_URL}/health", timeout=0.4)
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
    for _ in range(20):
        if _service_ready():
            return
        time.sleep(0.1)


def _ask_service(text: str) -> str:
    if not _service_ready():
        _start_service()
    try:
        response = httpx.post(
            f"{SERVICE_URL}/command",
            json={"text": text},
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("message", ""))
    except (httpx.HTTPError, ValueError):
        # Keep the CLI usable even if the local service cannot start.
        return handle_natural_language(text).message


def main() -> None:
    print("Jarvis for MRB — milestone 2")
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
