from __future__ import annotations

"""Exact user-button Windows desktop app launches, independent of model tools.

No arbitrary program paths, shell, terminal, URL, arguments or process kill.
A separate Windows operator opt-in and the existing Windows Jarvis API bearer
are required, and the authenticated client chooses only a fixed menu entry.
"""
from datetime import datetime, timezone
import os
import platform
import subprocess
import threading
import time
from typing import Any

# These literal argv arrays never contain user-controlled command or paths.
_APPS: dict[str, tuple[str, ...]] = {
    "Notepad": ("notepad.exe",),
    "Calculator": ("calc.exe",),
    "File Explorer": ("explorer.exe",),
    "Paint": ("mspaint.exe",),
}
_PROCESSES = {
    "Notepad": "notepad.exe",
    "Calculator": "calculatorapp.exe",  # modern UWP; may be unobservable
    "File Explorer": "explorer.exe",
    "Paint": "mspaint.exe",
}
_LOCK = threading.Lock()
_LAST_CALL = 0.0


class WindowsAppUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return (platform.system() == "Windows"
            and os.getenv("JARVIS_MESH_WINDOWS_APP_ENABLED") == "1")


def _seen(name: str) -> bool:
    try:
        import psutil
        for process in psutil.process_iter(["name"]):
            try:
                if str(process.info.get("name") or "").casefold() == name.casefold():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except (ImportError, OSError):
        return False
    return False


def launch_exact(name: str) -> dict[str, Any]:
    global _LAST_CALL
    if name not in _APPS:
        raise ValueError("Windows app not in the fixed Mesh allowlist.")
    if not enabled():
        raise WindowsAppUnavailable("Separate Windows app-launch startup opt-in is off.")
    from jarvis_mrb.permissions import decide

    permission = decide("pc.launch_app")
    if not permission.allowed:
        raise WindowsAppUnavailable("Jarvis PC launch permissions explicitly deny local writes.")
    # A confirmed UI button is the specific approval when policy is confirm;
    # no model, background scheduler or generic call gets that authorization.
    with _LOCK:
        now = time.monotonic()
        if now - _LAST_CALL < 3:
            raise WindowsAppUnavailable("Exact Windows app launch rate-limited.")
        _LAST_CALL = now  # reserve before side effect; don't retry uncertain failures
    argv = list(_APPS[name])
    try:
        child = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False, close_fds=True,
        )
    except (OSError, ValueError) as exc:
        raise WindowsAppUnavailable(
            "Windows did not accept the exact app request; do not infer app state."
        ) from exc
    process = _seen(_PROCESSES[name])
    return {
        "node_id": "windows", "app_name": name,
        "status": (
            "launch_accepted_process_observed"
            if process else "launch_accepted_process_unverified"
        ),
        "process_observed": process,
        "receipt": "Exact fixed argv submitted on interactive Windows host; "
                   "running-process check is not proof of focus or a new window.",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
