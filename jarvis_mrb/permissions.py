from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
POLICY_PATH = APP_DIR / "permissions.json"

Risk = Literal["read", "local_write", "external_write", "destructive", "security"]

DEFAULT_POLICY: dict[Risk, str] = {
    "read": "auto",
    "local_write": "auto",
    "external_write": "confirm",
    "destructive": "confirm",
    "security": "confirm",
}

TOOL_RISK: dict[str, Risk] = {
    "smart.status": "read",
    "smart.open": "local_write",
    "smart.close": "local_write",
    "browser.status": "read",
    "browser.list_tabs": "read",
    "browser.tab_status": "read",
    "browser.focus_tab": "local_write",
    "browser.open_site": "local_write",
    "browser.close_tab": "local_write",
    "pc.app_status": "read",
    "pc.list_running_apps": "read",
    "pc.launch_app": "local_write",
    "pc.open_url": "local_write",
    "pc.open_path": "local_write",
    "pc.close_app": "local_write",
    "pc.minecraft_status": "read",
    "pc.launch_minecraft": "local_write",
    "pc.ensure_minecraft_running": "local_write",
    "google.status": "read",
    "contacts.resolve": "read",
    "gmail.query": "read",
    "calendar.list": "read",
    "calendar.query": "read",
    "calendar.recent": "read",
    "calendar.create": "external_write",
    "gmail.send": "external_write",
    "web.status": "read",
    "web.search": "read",
    "jobs.list": "read",
    "jobs.create_time": "local_write",
    "jobs.create_event": "local_write",
    "jobs.cancel": "destructive",
    "background.submit": "local_write",
    "background.list": "read",
    "background.status": "read",
    "background.cancel": "destructive",
    "state.get": "read",
    "state.update": "local_write",
}

@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    needs_confirmation: bool
    risk: Risk

def _load() -> dict[str, str]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    policy = dict(DEFAULT_POLICY)
    if POLICY_PATH.exists():
        try:
            data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in DEFAULT_POLICY and value in {"auto", "confirm", "deny"}:
                        policy[key] = value
        except (OSError, json.JSONDecodeError):
            pass
    return policy

def policy_summary() -> str:
    policy = _load()
    return ", ".join(f"{key}={policy[key]}" for key in DEFAULT_POLICY)

def decide(tool: str) -> PermissionDecision:
    risk = TOOL_RISK.get(tool, "security")
    mode = _load().get(risk, "confirm")
    return PermissionDecision(allowed=mode != "deny", needs_confirmation=mode == "confirm", risk=risk)

def set_policy(risk: str, mode: str) -> str:
    if risk not in DEFAULT_POLICY:
        return f"Unknown risk class: {risk}."
    if mode not in {"auto", "confirm", "deny"}:
        return "Mode must be auto, confirm, or deny."
    policy = _load()
    policy[risk] = mode
    APP_DIR.mkdir(parents=True, exist_ok=True)
    POLICY_PATH.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return f"Set {risk} actions to {mode}."
