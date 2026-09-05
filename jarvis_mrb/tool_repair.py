from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from jarvis_mrb.planner_model import QUALITY_MODEL
from jarvis_mrb.sandbox import run_python

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
TOOLS_DIR = APP_DIR / "custom_tools"
REPAIRS_DIR = APP_DIR / "custom_tool_repairs"
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_LOCK = threading.RLock()
_ACTIVE: set[str] = set()


def _safe_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9_.-]+", "_", name.strip().lower()).strip("_.-")
    if not value:
        raise ValueError("Custom tool needs a name.")
    return value[:80]


def _tool_path(name: str) -> Path:
    return TOOLS_DIR / f"{_safe_name(name)}.json"


def _repair_path(name: str) -> Path:
    return REPAIRS_DIR / f"{_safe_name(name)}.json"


def _load_tool(name: str) -> dict[str, Any]:
    path = _tool_path(name)
    if not path.exists():
        raise ValueError(f"Custom tool {name!r} does not exist.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Custom tool {name!r} is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Custom tool {name!r} is invalid.")
    return data


def _extract_code(text: str) -> str:
    value = text.strip()
    match = re.search(r"```(?:python)?\s*(.*?)```", value, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else value


def _validate_plan(plan: Any, hosts: list[str], risk: str) -> None:
    if not isinstance(plan, dict):
        raise ValueError("Repair did not emit a JSON request plan.")
    method = str(plan.get("method") or "GET").upper()
    allowed_methods = {"GET"} if risk == "read" else {"GET", "POST", "PUT", "PATCH", "DELETE"}
    if method not in allowed_methods:
        raise ValueError(f"Repair attempted disallowed method {method}.")
    parsed = urlparse(str(plan.get("url") or ""))
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in hosts:
        raise ValueError("Repair attempted a URL outside the tool's allowlisted HTTPS hosts.")
    headers = plan.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("Repair emitted invalid headers.")
    forbidden = {"authorization", "x-api-key", "api-key", "cookie", "set-cookie"}
    if any(str(key).lower() in forbidden for key in headers):
        raise ValueError("Repair attempted to embed authentication secrets.")


def queue_repair(name: str, error: str) -> None:
    tool_name = _safe_name(name)
    with _LOCK:
        if tool_name in _ACTIVE:
            return
        _ACTIVE.add(tool_name)

    def work() -> None:
        try:
            item = _load_tool(tool_name)
            old_code = str(item.get("code") or "")
            system = """Repair a small Python request-planning adapter for a private assistant.
The adapter runs in a network-disabled Docker sandbox and prints exactly one JSON request plan with keys method,url,headers,body.
Preserve the API specification, allowed hosts, risk level, and security constraints. Never add credentials, environment-variable secret reads, subprocess execution, eval/exec, or filesystem access beyond /work/input.json.
Return revised Python source only, not an explanation."""
            user = (
                f"Tool: {tool_name}\nRisk: {item.get('risk')}\nAllowed hosts: {', '.join(item.get('allowed_hosts') or [])}\n"
                f"API spec:\n{str(item.get('api_spec') or '')[:12000]}\n\n"
                f"Failure:\n{error[:5000]}\n\nCurrent code:\n{old_code[:20000]}"
            )
            payload = {
                "model": QUALITY_MODEL,
                "stream": False,
                "think": False,
                "keep_alive": "0",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": {"temperature": 0, "num_predict": 1800},
            }
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=2.0)) as client:
                response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
            code = _extract_code(str((data.get("message") or {}).get("content") or ""))
            if not code:
                return
            test = run_python(code, stdin_json={"_jarvis_test": True}, timeout_seconds=8)
            if not test.ok:
                return
            try:
                plan = json.loads(test.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                return
            hosts = [str(value).lower() for value in item.get("allowed_hosts") or []]
            risk = str(item.get("risk") or "read")
            _validate_plan(plan, hosts, risk)
            proposal = {
                "name": tool_name,
                "error": error[:6000],
                "old_code": old_code,
                "proposed_code": code,
                "validated": True,
            }
            REPAIRS_DIR.mkdir(parents=True, exist_ok=True)
            _repair_path(tool_name).write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        finally:
            with _LOCK:
                _ACTIVE.discard(tool_name)

    threading.Thread(target=work, name=f"jarvis-repair-{tool_name}", daemon=True).start()


def list_repairs() -> list[dict[str, Any]]:
    REPAIRS_DIR.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []
    for path in sorted(REPAIRS_DIR.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            result.append({
                "name": item.get("name"),
                "validated": bool(item.get("validated")),
                "error": str(item.get("error") or "")[:800],
            })
    return result


def apply_repair(name: str) -> dict[str, Any]:
    tool_name = _safe_name(name)
    path = _repair_path(tool_name)
    if not path.exists():
        raise ValueError(f"There is no queued repair for {tool_name!r}.")
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Repair proposal is unreadable: {exc}") from exc
    if not isinstance(proposal, dict) or not proposal.get("validated"):
        raise ValueError("Repair proposal has not passed sandbox validation.")
    item = _load_tool(tool_name)
    item["code"] = str(proposal.get("proposed_code") or "")
    # Repairs never silently enable a tool or change its risk/host policy.
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    _tool_path(tool_name).write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    path.unlink(missing_ok=True)
    return {"name": tool_name, "enabled": bool(item.get("enabled")), "risk": item.get("risk")}
