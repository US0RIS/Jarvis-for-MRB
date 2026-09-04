from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
CONFIG_PATH = APP_DIR / "server.json"


@dataclass(frozen=True)
class ServerConfig:
    bind_host: str = "127.0.0.1"
    port: int = 8765
    api_token: str = ""


def load_server_config() -> ServerConfig:
    data: dict[str, object] = {}
    if CONFIG_PATH.exists():
        try:
            parsed = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                data = parsed
        except (OSError, json.JSONDecodeError):
            pass

    bind_host = os.environ.get("JARVIS_BIND_HOST") or str(data.get("bind_host") or "127.0.0.1")
    try:
        port = int(os.environ.get("JARVIS_PORT") or data.get("port") or 8765)
    except (TypeError, ValueError):
        port = 8765
    api_token = os.environ.get("JARVIS_API_TOKEN") or str(data.get("api_token") or "")
    return ServerConfig(bind_host=bind_host, port=port, api_token=api_token.strip())


def save_server_config(config: ServerConfig) -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "bind_host": config.bind_host,
                "port": config.port,
                "api_token": config.api_token,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return CONFIG_PATH
