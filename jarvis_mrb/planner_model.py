from __future__ import annotations

import json
import os
import threading
from pathlib import Path

QUALITY_MODEL = "qwen3.8:27b"
FAST_MODEL = "qwen3:8b"
SUPPORTED_MODELS = (QUALITY_MODEL, FAST_MODEL)

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
MODEL_SETTINGS_PATH = APP_DIR / "planner_model.json"
_LOCK = threading.RLock()


def _default_model() -> str:
    configured = os.environ.get("JARVIS_MODEL", QUALITY_MODEL).strip()
    return configured if configured in SUPPORTED_MODELS else QUALITY_MODEL


def _load() -> dict[str, object]:
    default_auto = os.environ.get("JARVIS_AUTO_ROUTE", "1").strip().lower() not in {"0", "false", "no"}
    settings: dict[str, object] = {"model": _default_model(), "auto_route": default_auto}
    try:
        payload = json.loads(MODEL_SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            model = str(payload.get("model") or "").strip()
            if model in SUPPORTED_MODELS:
                settings["model"] = model
            if isinstance(payload.get("auto_route"), bool):
                settings["auto_route"] = bool(payload["auto_route"])
    except (OSError, json.JSONDecodeError):
        pass
    return settings


def _save(settings: dict[str, object]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def get_planner_model() -> str:
    with _LOCK:
        return str(_load()["model"])


def get_auto_route() -> bool:
    with _LOCK:
        return bool(_load()["auto_route"])


def set_planner_model(model: str) -> str:
    value = model.strip()
    if value not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported planner model {value!r}. Allowed models: {', '.join(SUPPORTED_MODELS)}"
        )
    with _LOCK:
        settings = _load()
        settings["model"] = value
        _save(settings)
    return value


def set_auto_route(enabled: bool) -> bool:
    with _LOCK:
        settings = _load()
        settings["auto_route"] = bool(enabled)
        _save(settings)
    return bool(enabled)


def planner_settings() -> dict[str, object]:
    with _LOCK:
        settings = _load()
    return {
        "model": str(settings["model"]),
        "auto_route": bool(settings["auto_route"]),
        "options": list(SUPPORTED_MODELS),
    }


def model_options() -> list[str]:
    return list(SUPPORTED_MODELS)
