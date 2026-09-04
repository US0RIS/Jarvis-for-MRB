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


def get_planner_model() -> str:
    """Return the currently selected Ollama planner model.

    The phone-controlled setting is persisted outside the repository so it survives
    normal Jarvis updates/restarts. JARVIS_MODEL is still honored as the initial
    default when no persisted selection exists.
    """
    with _LOCK:
        try:
            payload = json.loads(MODEL_SETTINGS_PATH.read_text(encoding="utf-8"))
            model = str(payload.get("model") or "").strip() if isinstance(payload, dict) else ""
            if model in SUPPORTED_MODELS:
                return model
        except (OSError, json.JSONDecodeError):
            pass
        return _default_model()


def set_planner_model(model: str) -> str:
    value = model.strip()
    if value not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported planner model {value!r}. Allowed models: {', '.join(SUPPORTED_MODELS)}"
        )

    with _LOCK:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_SETTINGS_PATH.write_text(
            json.dumps({"model": value}, indent=2),
            encoding="utf-8",
        )
    return value


def model_options() -> list[str]:
    return list(SUPPORTED_MODELS)
