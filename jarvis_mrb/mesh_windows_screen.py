from __future__ import annotations

"""Explicit, short-lived screen *viewing* on the Jarvis Windows host.

No screen recording service, no network listener, no remote input, no file
write, and no screenshot persistence. Access requires the normal Jarvis API
bearer plus an additional Windows process startup opt-in and exact phone tap.
An interactive Windows desktop and Pillow ImageGrab are required. Headless or
session-zero deployments return unavailable rather than a bogus blank image.
"""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
import platform
import threading
from typing import Any

_LOCK = threading.RLock()
_CAPTURE_LOCK = threading.Lock()
_EXPIRES_AT: datetime | None = None
_MAX_BYTES = 4_000_000
_MAX_SECONDS = 300


class WindowsScreenUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enabled() -> bool:
    return (platform.system() == "Windows"
            and os.getenv("JARVIS_MESH_WINDOWS_SCREEN_ENABLED", "") == "1")


def active() -> bool:
    with _LOCK:
        return bool(enabled() and _EXPIRES_AT and _now() < _EXPIRES_AT)


def begin(seconds: int = 120) -> dict[str, Any]:
    global _EXPIRES_AT
    if not enabled():
        raise WindowsScreenUnavailable(
            "Windows screen serving is not enabled on an interactive Jarvis host."
        )
    if type(seconds) is not int or not 15 <= seconds <= _MAX_SECONDS:
        raise ValueError("Screen session must last 15–300 seconds.")
    with _LOCK:
        _EXPIRES_AT = _now() + timedelta(seconds=seconds)
        return {
            "node_id": "windows",
            "status": "active",
            "expires_at": _EXPIRES_AT.isoformat(),
            "source": "Windows desktop, separate process opt-in and explicit phone session",
        }


def stop() -> dict[str, str]:
    global _EXPIRES_AT
    with _LOCK:
        _EXPIRES_AT = None
    return {"node_id": "windows", "status": "closed"}


def frame() -> tuple[bytes, str]:
    if not active():
        raise WindowsScreenUnavailable("Windows screen session disabled or expired.")
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise WindowsScreenUnavailable(
            "Pillow ImageGrab is required for the optional Windows screen feature."
        ) from exc
    # Prevent unbounded simultaneous pixel capture from concurrent API callers.
    with _CAPTURE_LOCK:
        try:
            screen = ImageGrab.grab(all_screens=False)
            try:
                if screen.width < 80 or screen.height < 80:
                    raise WindowsScreenUnavailable("No valid interactive Windows desktop.")
                if screen.width > 1600 or screen.height > 1200:
                    screen.thumbnail((1600, 1200))
                with BytesIO() as stream:
                    screen.convert("RGB").save(
                        stream, format="JPEG", quality=58, optimize=True
                    )
                    encoded = stream.getvalue()
            finally:
                screen.close()
        except WindowsScreenUnavailable:
            raise
        except Exception as exc:
            raise WindowsScreenUnavailable(
                "Windows desktop capture unavailable; check interactive session."
            ) from exc
        if not 80 <= len(encoded) <= _MAX_BYTES or not encoded.startswith(b"\\xff\\xd8\\xff"):
            raise WindowsScreenUnavailable(
                "Captured desktop image invalid or exceeded private 4 MB limit."
            )
        if not active():  # stop or expiry *during* capture cancels transfer
            raise WindowsScreenUnavailable("Screen viewing was revoked during capture.")
        return encoded, "image/jpeg"
