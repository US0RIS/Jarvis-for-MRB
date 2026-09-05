from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes
from typing import Any

import psutil

from jarvis_mrb.environment_state import update_state
from jarvis_mrb.tools.browser import list_tabs

_LOCK = threading.RLock()
_LAST: dict[str, Any] = {}
_STARTED = False


def _foreground_window() -> tuple[str, str, int | None]:
    if sys.platform != "win32":
        return "", "", None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", "", None
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = ""
        try:
            process_name = psutil.Process(int(pid.value)).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            pass
        return " ".join(buffer.value.split())[:500], process_name[:120], int(pid.value)
    except Exception:
        return "", "", None


def snapshot() -> dict[str, Any]:
    title, process, pid = _foreground_window()
    tabs: list[dict[str, str]] = []
    try:
        result = list_tabs()
        if result.ok and isinstance(result.data, list):
            tabs = [
                {
                    "title": " ".join(str(item.get("title") or "").split())[:200],
                    "url": str(item.get("url") or "")[:500],
                }
                for item in result.data[:12]
                if isinstance(item, dict)
            ]
    except Exception:
        tabs = []
    current = {
        "captured_at": time.time(),
        "foreground_title": title,
        "foreground_process": process,
        "foreground_pid": pid,
        "browser_tabs": tabs,
    }
    with _LOCK:
        _LAST.clear()
        _LAST.update(current)
    return current


def describe() -> str:
    current = snapshot()
    title = current.get("foreground_title") or "an untitled window"
    process = current.get("foreground_process") or "unknown application"
    parts = [f"The PC foreground application is {process}; the active window is {title}."]
    tabs = current.get("browser_tabs") or []
    if tabs:
        titles = [str(item.get("title") or "").strip() for item in tabs[:5] if str(item.get("title") or "").strip()]
        if titles:
            parts.append("Open browser context includes: " + "; ".join(titles) + ".")
    parts.append("Jarvis can hand off this visible application/window context, but it does not claim to have read the full document unless a dedicated document or screen-reading tool supplied its contents.")
    return " ".join(parts)


def _loop() -> None:
    while True:
        try:
            current = snapshot()
            update_state({"pc_context": current})
        except Exception:
            pass
        time.sleep(3.0)


def start() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    threading.Thread(target=_loop, name="jarvis-pc-context", daemon=True).start()
