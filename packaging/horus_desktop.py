"""Horus desktop entry point: Qt Mission Control and isolated backend process."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _health_url() -> str:
    from jarvis_mrb.server_config import load_server_config
    return f"http://127.0.0.1:{load_server_config().port}/health"


def service_running() -> bool:
    try:
        with urllib.request.urlopen(_health_url(), timeout=1.8) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def start_service() -> bool:
    if service_running():
        return True
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    executable = sys.executable
    command = ([executable, "--service"] if getattr(sys, "frozen", False) else
               [executable, "-m", "jarvis_mrb.service"])
    subprocess.Popen(
        command, cwd=os.path.dirname(executable), creationflags=flags,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True,
    )
    for _ in range(55):
        if service_running():
            return True
        time.sleep(0.35)
    return False


def main() -> int:
    if "--service" in sys.argv:
        from jarvis_mrb.service import main as run_service
        run_service()
        return 0
    from mission_control import start_qt
    if "--self-test" in sys.argv:
        from jarvis_mrb.inference import inference_status
        from jarvis_mrb.service import app
        assert app and inference_status()["provider"]
        return start_qt(start_service, service_running, self_test=True)
    return start_qt(start_service, service_running)


if __name__ == "__main__":
    sys.exit(main())
