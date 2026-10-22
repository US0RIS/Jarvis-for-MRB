"""Ephemeral receipt for a deliberate, authenticated iPhone setup test.

This is evidence of authenticated app-to-backend communication, NOT evidence
of Bluetooth routing, user identity, physical phone proximity, or audio.
No phone IP, persistent identifiers, or bearer credentials are stored here.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_WINDOW_SECONDS = 300.0
_LOCK = threading.RLock()
_last_checkin: float | None = None


def check_in(*, now: float | None = None) -> dict[str, Any]:
    global _last_checkin
    moment = time.monotonic() if now is None else float(now)
    with _LOCK:
        _last_checkin = moment
    return {"accepted": True, "verification": "authenticated_app_request"}


def status(*, now: float | None = None) -> dict[str, Any]:
    moment = time.monotonic() if now is None else float(now)
    with _LOCK:
        last = _last_checkin
    age = max(0.0, moment - last) if last is not None else None
    return {
        "recent_authenticated_app_checkin": age is not None and age <= _WINDOW_SECONDS,
        "seconds_since_checkin": round(age) if age is not None else None,
        "window_seconds": int(_WINDOW_SECONDS),
        "airpods_verified": False,
        "scope": "server_received_authenticated_app_setup_request_only",
    }
