from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
STATE_PATH = APP_DIR / "environment_state.json"
_LOCK = threading.RLock()

_DEFAULT_STATE: dict[str, Any] = {
    "location": "unknown",
    "project_focus": "Jarvis",
    "devices": {
        "ray_ban_meta": "unknown",
        "phone_transport": "unknown",
    },
    "preferences": {
        "address": "sir",
        "response_style": "concise, direct, technical when appropriate",
        "email_emojis": False,
        "proactive_interruptions": "only when useful and high confidence",
    },
    "vision": {
        "last_scene": "",
        "last_scene_at": None,
    },
    "updated_at": None,
}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_state() -> dict[str, Any]:
    with _LOCK:
        state = copy.deepcopy(_DEFAULT_STATE)
        if STATE_PATH.exists():
            try:
                payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    state = _deep_merge(state, payload)
            except (OSError, json.JSONDecodeError):
                pass
        return state


def update_state(patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ValueError("Environment state patch must be an object.")
    with _LOCK:
        state = _deep_merge(get_state(), patch)
        state["updated_at"] = datetime.now().astimezone().isoformat()
        APP_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return state


def set_value(key: str, value: Any) -> dict[str, Any]:
    """Set a small set of user-facing state keys from the agent tool surface."""
    normalized = key.strip().lower().replace(" ", "_")
    if normalized in {"project", "project_focus", "focus"}:
        return update_state({"project_focus": str(value)[:500]})
    if normalized in {"location", "place"}:
        return update_state({"location": str(value)[:200]})
    if normalized.startswith("preference."):
        subkey = normalized.split(".", 1)[1][:100]
        return update_state({"preferences": {subkey: value}})
    raise ValueError("State key must be project_focus, location, or preference.<name>.")


def prompt_context() -> str:
    state = get_state()
    # Keep this bounded because it is appended to every model request.
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))[:5000]
