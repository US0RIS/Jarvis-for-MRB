from __future__ import annotations

import sys
import threading
import time
from typing import Any

from jarvis_mrb.environment_state import get_state

_LOCK = threading.RLock()
_STARTED = False
_DAMPED = False
_ORIGINAL_VOLUME: float | None = None
_TARGET = 0.24


def _endpoint() -> Any:
    if sys.platform != "win32":
        return None
    try:
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
        direct = getattr(device, "EndpointVolume", None)
        if direct is not None:
            return direct
    except Exception:
        pass
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        device = AudioUtilities.GetSpeakers()
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception:
        return None


def status() -> dict[str, Any]:
    endpoint = _endpoint()
    current = None
    if endpoint is not None:
        try:
            current = float(endpoint.GetMasterVolumeLevelScalar())
        except Exception:
            current = None
    with _LOCK:
        return {
            "available": endpoint is not None,
            "damped": _DAMPED,
            "current_volume": current,
            "target_volume": _TARGET,
        }


def _set_damped(active: bool) -> None:
    global _DAMPED, _ORIGINAL_VOLUME
    endpoint = _endpoint()
    if endpoint is None:
        return
    with _LOCK:
        if active and not _DAMPED:
            try:
                current = float(endpoint.GetMasterVolumeLevelScalar())
                _ORIGINAL_VOLUME = current
                if current > _TARGET:
                    endpoint.SetMasterVolumeLevelScalar(_TARGET, None)
                _DAMPED = True
            except Exception:
                return
        elif not active and _DAMPED:
            try:
                if _ORIGINAL_VOLUME is not None:
                    endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, _ORIGINAL_VOLUME)), None)
            except Exception:
                pass
            _ORIGINAL_VOLUME = None
            _DAMPED = False


def _conversation_active() -> bool:
    state = get_state()
    audio = state.get("audio") if isinstance(state.get("audio"), dict) else {}
    preferences = state.get("preferences") if isinstance(state.get("preferences"), dict) else {}
    if preferences.get("smart_audio_damping", True) is False:
        return False
    return bool(audio.get("conversation_active", False))


def _loop() -> None:
    while True:
        try:
            _set_damped(_conversation_active())
        except Exception:
            pass
        time.sleep(0.75)


def start() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    threading.Thread(target=_loop, name="jarvis-audio-damping", daemon=True).start()
