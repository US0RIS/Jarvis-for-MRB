from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis_mrb.ephemeral_state import prompt_context as ephemeral_prompt_context

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
STATE_PATH = APP_DIR / "environment_state.json"
_LOCK = threading.RLock()

_DEFAULT_STATE: dict[str, Any] = {
    "location": "unknown",
    "active_profile": "default",
    "project_focus": "Jarvis",
    "devices": {
        "ray_ban_meta": "unknown",
        "phone_transport": "unknown",
    },
    "audio": {
        "ambient_dbfs": None,
        "whisper_mode": False,
    },
    "health": {
        "enabled": False,
        "heart_rate_bpm": None,
        "hrv_ms": None,
        "sleep_hours": None,
        "updated_at": None,
    },
    "preferences": {
        "address": "sir",
        "response_style": "concise, direct, technical when appropriate",
        "email_emojis": False,
        "proactive_interruptions": "only when useful and high confidence",
        "proactive_monitoring": True,
        "proactive_threshold": "warning",
        "reality_check": True,
    },
    "vision": {
        "last_scene": "",
        "last_scene_at": None,
    },
    "updated_at": None,
}

_WORLD_CONTEXT_KEYS = {
    "location",
    "active_profile",
    "project_focus",
    "devices",
    "audio",
    "health",
    "preferences",
    "meeting",
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

    # The iPhone may attach an explicit metadata-only world snapshot to its normal
    # authenticated environment update. Consume that snapshot into the world model,
    # but never duplicate it into environment_state.json. In particular, the
    # snapshot contract excludes biometric feature prints and raw camera/audio data.
    working_patch = copy.deepcopy(patch)
    frontend_world_snapshot = working_patch.pop("world_snapshot", None)
    # Ambient sensor data is a short-lived signal, not a durable world snapshot.
    # In particular, never save raw GPS coordinates or a health series to
    # environment_state.json or record_environment_snapshot on every phone ping.
    sensor_snapshot = working_patch.pop("sensor_snapshot", None)

    with _LOCK:
        state = _deep_merge(get_state(), working_patch)
        state["updated_at"] = datetime.now().astimezone().isoformat()
        APP_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    if isinstance(sensor_snapshot, dict):
        try:
            from jarvis_mrb.sensor_opportunities import ingest
            ingest(sensor_snapshot)
        except Exception as exc:
            try:
                from jarvis_mrb.runtime_health import record_failure
                record_failure("ambient_opportunities", exc)
            except Exception:
                pass

    # World-model mirroring is intentionally best-effort. A graph/database problem
    # must never prevent the live companion state from being updated.
    try:
        if isinstance(frontend_world_snapshot, dict):
            from jarvis_mrb.world_frontend_ingest import ingest_frontend_snapshot

            ingest_frontend_snapshot(frontend_world_snapshot)
        if any(key in working_patch for key in _WORLD_CONTEXT_KEYS):
            from jarvis_mrb.world_model import record_environment_snapshot

            record_environment_snapshot(state)
    except Exception:
        pass

    return state


def set_value(key: str, value: Any) -> dict[str, Any]:
    normalized = key.strip().lower().replace(" ", "_")
    if normalized in {"project", "project_focus", "focus"}:
        return update_state({"project_focus": str(value)[:500]})
    if normalized in {"location", "place"}:
        return update_state({"location": str(value)[:200]})
    if normalized in {"profile", "active_profile"}:
        return update_state({"active_profile": str(value)[:100]})
    if normalized.startswith("preference."):
        subkey = normalized.split(".", 1)[1][:100]
        return update_state({"preferences": {subkey: value}})
    raise ValueError("State key must be project_focus, location, active_profile, or preference.<name>.")


def prompt_context() -> str:
    state = get_state()
    durable = json.dumps(state, ensure_ascii=False, separators=(",", ":"))[:5000]
    temporary = ephemeral_prompt_context()
    return f"durable={durable}\ntemporary={temporary}"[:8000]
