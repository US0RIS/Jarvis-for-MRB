from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from jarvis_mrb.planner_model import QUALITY_MODEL
from jarvis_mrb.sandbox import run_python

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
TOOLS_DIR = APP_DIR / "custom_tools"
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def _safe_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9_.-]+", "_", name.strip().lower()).strip("_.-")
    if not value:
        raise ValueError("Custom tool needs a name.")
    return value[:80]


def _path(name: str) -> Path:
    return TOOLS_DIR / f"{_safe_name(name)}.json"


def list_tools() -> list[dict[str, Any]]:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []
    for path in sorted(TOOLS_DIR.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            result.append({
                "name": item.get("name"),
                "description": item.get("description"),
                "allowed_hosts": item.get("allowed_hosts"),
                "risk": item.get("risk"),
                "enabled": bool(item.get("enabled", False)),
            })
    return result


def get_tool(name: str) -> dict[str, Any]:
    path = _path(name)
    if not path.exists():
        raise ValueError(f"Custom tool {name!r} does not exist.")
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Custom tool {name!r} is unreadable: {exc}") from exc
    if not isinstance(item, dict):
        raise ValueError(f"Custom tool {name!r} is invalid.")
    return item


def set_enabled(name: str, enabled: bool) -> dict[str, Any]:
    item = get_tool(name)
    item["enabled"] = bool(enabled)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    return item


def _extract_code(text: str) -> str:
    value = text.strip()
    match = re.search(r"```(?:python)?\s*(.*?)```", value, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return value


def synthesize(
    *,
    name: str,
    description: str,
    api_spec: str,
    allowed_hosts: list[str],
    risk: str = "read",
) -> dict[str, Any]:
    tool_name = _safe_name(name)
    hosts = sorted({host.strip().lower() for host in allowed_hosts if host.strip()})
    if not hosts:
        raise ValueError("A custom API tool must declare at least one allowed HTTPS host.")
    if risk not in {"read", "external_write"}:
        raise ValueError("Custom API tool risk must be read or external_write.")

    system = """Write a small Python 3.12 request-planning adapter for a personal assistant.
The script cannot access the network. It reads JSON arguments from /work/input.json if present, otherwise {}.
It MUST print exactly one JSON object with keys: method, url, headers, body.
- method must be GET for read-only tools; POST/PUT/PATCH/DELETE are allowed only when the supplied risk says external_write.
- url must be an HTTPS URL on one of the explicitly allowed hosts.
- headers must contain only non-secret static headers. Never hard-code API keys or credentials.
- body may be null, a JSON object, or a string.
Do not execute requests. Do not access files other than /work/input.json. Do not spawn processes. Do not use eval/exec.
Return Python source only."""
    user = (
        f"Tool name: {tool_name}\nDescription: {description}\nRisk: {risk}\n"
        f"Allowed hosts: {', '.join(hosts)}\nAPI specification:\n{api_spec[:12000]}"
    )
    payload = {
        "model": QUALITY_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": "0",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ValueError(f"Could not synthesize custom tool: {exc}") from exc

    code = _extract_code(str((data.get("message") or {}).get("content") or ""))
    if not code:
        raise ValueError("The synthesis model returned no Python source.")

    # Execute once with empty arguments inside the locked-down sandbox. A valid
    # adapter should at least emit a structurally valid request plan.
    test = run_python(code, stdin_json={"_jarvis_test": True}, timeout_seconds=6)
    if not test.ok:
        raise ValueError(f"Generated tool failed sandbox validation: {test.message}")
    try:
        plan = json.loads(test.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ValueError("Generated tool did not emit a JSON request plan during validation.") from exc
    _validate_plan(plan, hosts=hosts, risk=risk)

    item = {
        "name": tool_name,
        "description": description.strip()[:1000],
        "api_spec": api_spec.strip()[:16000],
        "allowed_hosts": hosts,
        "risk": risk,
        "enabled": False,
        "code": code,
    }
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    _path(tool_name).write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    return item


def _validate_plan(plan: Any, *, hosts: list[str], risk: str) -> tuple[str, str, dict[str, str], Any]:
    if not isinstance(plan, dict):
        raise ValueError("Custom tool did not return a JSON object.")
    method = str(plan.get("method") or "GET").upper()
    allowed_methods = {"GET"} if risk == "read" else {"GET", "POST", "PUT", "PATCH", "DELETE"}
    if method not in allowed_methods:
        raise ValueError(f"Custom tool attempted disallowed HTTP method {method}.")
    url = str(plan.get("url") or "").strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in hosts:
        raise ValueError("Custom tool attempted a URL outside its allowed HTTPS hosts.")
    headers_raw = plan.get("headers") or {}
    if not isinstance(headers_raw, dict):
        raise ValueError("Custom tool headers must be an object.")
    headers: dict[str, str] = {}
    for key, value in headers_raw.items():
        k = str(key).strip()
        v = str(value).strip()
        if not k or len(k) > 120 or len(v) > 1000:
            continue
        lower = k.lower()
        if lower in {"authorization", "x-api-key", "api-key", "cookie", "set-cookie"}:
            raise ValueError("Custom tool adapters cannot embed authentication secrets.")
        headers[k] = v
    return method, url, headers, plan.get("body")


def run(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    item = get_tool(name)
    if not item.get("enabled"):
        raise ValueError(f"Custom tool {name!r} is disabled. Enable it explicitly before use.")
    code = str(item.get("code") or "")
    result = run_python(code, stdin_json=arguments, timeout_seconds=8)
    if not result.ok:
        raise ValueError(result.message)
    try:
        plan = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ValueError("Custom tool did not emit a valid request plan.") from exc

    hosts = [str(value).lower() for value in item.get("allowed_hosts") or []]
    risk = str(item.get("risk") or "read")
    method, url, headers, body = _validate_plan(plan, hosts=hosts, risk=risk)
    try:
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=3.0), follow_redirects=False) as client:
            response = client.request(method, url, headers=headers, json=body if isinstance(body, (dict, list)) else None, content=body if isinstance(body, str) else None)
    except httpx.HTTPError as exc:
        raise ValueError(f"Custom API request failed: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text[:12000]
    else:
        payload = response.text[:12000]
    return {
        "status_code": response.status_code,
        "content_type": content_type,
        "body": payload,
    }
