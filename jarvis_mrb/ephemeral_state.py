from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
STATE_PATH = APP_DIR / "ephemeral_state.json"
_LOCK = threading.RLock()


def _now() -> datetime:
    return datetime.now().astimezone()


def _load_raw() -> dict[str, dict[str, Any]]:
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {
                str(key): value
                for key, value in payload.items()
                if isinstance(value, dict)
            }
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save(items: dict[str, dict[str, Any]]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _prune(items: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    now = _now()
    result: dict[str, dict[str, Any]] = {}
    for key, item in items.items():
        expires = str(item.get("expires_at") or "")
        try:
            expires_at = datetime.fromisoformat(expires)
            if expires_at.tzinfo is None:
                expires_at = expires_at.astimezone()
        except (TypeError, ValueError):
            continue
        if expires_at > now:
            result[key] = item
    return result


def get_all() -> dict[str, Any]:
    with _LOCK:
        items = _load_raw()
        pruned = _prune(items)
        if pruned != items:
            _save(pruned)
        return {
            key: {
                "value": item.get("value"),
                "expires_at": item.get("expires_at"),
                "set_at": item.get("set_at"),
            }
            for key, item in pruned.items()
        }


def set_temporary(key: str, value: Any, ttl_minutes: int = 60) -> dict[str, Any]:
    normalized = key.strip().lower().replace(" ", "_")[:100]
    if not normalized:
        raise ValueError("Temporary state requires a key.")
    ttl = max(1, min(int(ttl_minutes), 7 * 24 * 60))
    now = _now()
    item = {
        "value": value,
        "set_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
    }
    with _LOCK:
        items = _prune(_load_raw())
        items[normalized] = item
        _save(items)
    return {normalized: item}


def clear_temporary(key: str) -> bool:
    normalized = key.strip().lower().replace(" ", "_")[:100]
    with _LOCK:
        items = _load_raw()
        existed = normalized in items
        items.pop(normalized, None)
        _save(_prune(items))
    return existed


def prompt_context() -> str:
    current = get_all()
    if not current:
        return "{}"
    return json.dumps(current, ensure_ascii=False, separators=(",", ":"))[:3000]
