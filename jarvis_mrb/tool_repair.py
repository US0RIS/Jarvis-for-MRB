from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any
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
    """Use the exact runtime custom-tool request boundary for repair validation."""
    from jarvis_mrb.custom_tools import _validate_plan as validate_custom_plan

    validate_custom_plan(plan, hosts=list(hosts), risk=str(risk))


def _code_sha256(code: str) -> str:
    return hashlib.sha256(
        str(code or "").encode("utf-8", errors="replace")
    ).hexdigest()


def _validate_repair_code(
    code: str,
    *,
    hosts: list[str],
    risk: str,
) -> dict[str, Any]:
    clean_code = str(code or "")
    if not clean_code.strip():
        raise ValueError("Repair proposal contains no Python source.")
    test = run_python(
        clean_code,
        stdin_json={"_jarvis_test": True},
        timeout_seconds=8,
    )
    if not test.ok:
        raise ValueError(f"Repair failed sandbox validation: {test.message}")
    try:
        plan = json.loads(test.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ValueError("Repair did not emit a valid JSON request plan.") from exc
    _validate_plan(plan, hosts, risk)
    return plan


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
            hosts = [str(value) for value in item.get("allowed_hosts") or []]
            risk = str(item.get("risk") or "read")
            _validate_repair_code(code, hosts=hosts, risk=risk)
            proposal = {
                "name": tool_name,
                "error": error[:6000],
                "old_code": old_code,
                "old_code_sha256": _code_sha256(old_code),
                "proposed_code": code,
                "proposed_code_sha256": _code_sha256(code),
                "allowed_hosts": hosts,
                "risk": risk,
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
    current_code = str(item.get("code") or "")
    proposed_code = str(proposal.get("proposed_code") or "")
    expected_old_hash = str(proposal.get("old_code_sha256") or "")
    expected_new_hash = str(proposal.get("proposed_code_sha256") or "")
    current_hosts = [str(value) for value in item.get("allowed_hosts") or []]
    current_risk = str(item.get("risk") or "read")

    if not expected_old_hash or expected_old_hash != _code_sha256(current_code):
        raise ValueError(
            "Repair proposal is stale because the custom tool changed after validation."
        )
    if not expected_new_hash or expected_new_hash != _code_sha256(proposed_code):
        raise ValueError("Repair proposal code integrity check failed.")
    if list(proposal.get("allowed_hosts") or []) != current_hosts:
        raise ValueError(
            "Repair proposal host policy no longer matches the custom tool."
        )
    if str(proposal.get("risk") or "") != current_risk:
        raise ValueError(
            "Repair proposal risk policy no longer matches the custom tool."
        )

    # A queued proposal is mutable on disk. Re-run the isolated test and the
    # canonical runtime request validator immediately before applying it.
    _validate_repair_code(
        proposed_code,
        hosts=current_hosts,
        risk=current_risk,
    )

    updated = dict(item)
    updated["code"] = proposed_code
    # Repairs never silently enable a tool or change its risk/host policy.
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    _tool_path(tool_name).write_text(
        json.dumps(updated, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    path.unlink(missing_ok=True)
    return {
        "name": tool_name,
        "enabled": bool(updated.get("enabled")),
        "risk": updated.get("risk"),
    }
