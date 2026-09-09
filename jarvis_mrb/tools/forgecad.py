from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
DISCOVERY_FILE = LOCAL_APPDATA / "ForgeCAD" / "jarvis_bridge.json"


def _find_forgecad_exe() -> str | None:
    env = os.environ.get("FORGECAD_EXE", "").strip()
    if env and Path(env).exists():
        return env
    direct = shutil.which("ForgeCAD") or shutil.which("ForgeCAD.exe")
    if direct:
        return direct
    candidates = [
        LOCAL_APPDATA / "Programs" / "ForgeCAD" / "ForgeCAD.exe",
        Path(os.environ.get("ProgramFiles", "")) / "ForgeCAD" / "ForgeCAD.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "ForgeCAD" / "ForgeCAD.exe",
    ]
    return next((str(x) for x in candidates if str(x) and x.exists()), None)


def _start_forgecad_engine() -> bool:
    if sys.platform != "win32":
        return False
    exe = _find_forgecad_exe()
    if not exe:
        return False
    try:
        subprocess.Popen(
            [exe, "--headless"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except OSError:
        return False
    deadline = time.time() + 15
    while time.time() < deadline:
        if DISCOVERY_FILE.exists():
            return True
        time.sleep(0.2)
    return False


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    message: str


def _connection() -> tuple[str, str, str]:
    if not DISCOVERY_FILE.exists() and not _start_forgecad_engine():
        raise ValueError("ForgeCAD Engine is not running and Jarvis could not start it. Install ForgeCAD or set FORGECAD_EXE.")
    try:
        data = json.loads(DISCOVERY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"ForgeCAD bridge discovery is unreadable: {exc}") from exc
    base = str(data.get("base_url") or "").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("ForgeCAD bridge refused a non-loopback service address.")
    header = str(data.get("header") or "X-ForgeCAD-Jarvis-Key")
    token = str(data.get("token") or "")
    if len(token) < 32:
        raise ValueError("ForgeCAD bridge credential is missing or invalid.")
    return base, header, token


def _request(method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, timeout: float = 120.0) -> Any:
    base, header, token = _connection()
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=1.0), follow_redirects=False) as client:
            response = client.request(method, base + path, params=params, json=body, headers={header: token})
        if response.status_code == 401:
            raise ValueError("ForgeCAD rejected the Jarvis bridge credential. Restart ForgeCAD to refresh discovery.")
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError as exc:
        raise ValueError("ForgeCAD is not reachable on this machine. Open or restart ForgeCAD.") from exc
    except httpx.TimeoutException as exc:
        raise ValueError("ForgeCAD did not finish the engineering operation before the timeout.") from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:800]
        raise ValueError(f"ForgeCAD returned HTTP {exc.response.status_code}: {detail}") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"ForgeCAD bridge failed: {exc}") from exc


def _compact_json(value: Any, limit: int = 5000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else text[:limit] + "…"


def status() -> ToolResult:
    try:
        data = _request("GET", "/api/jarvis/status", timeout=8)
    except ValueError as exc:
        return ToolResult(False, str(exc))
    p = data.get("project") or {}
    metrics = p.get("metrics") or {}
    design = p.get("active_design") or "unknown"
    project = p.get("project") or "Untitled project"
    mass = metrics.get("mass_kg")
    parts = metrics.get("parts")
    risks = [r for r in (p.get("reality_risks") or []) if r.get("severity") not in {"pass"}]
    msg = f"ForgeCAD is connected. {project}, design {design}, {parts} parts"
    if isinstance(mass, (int, float)):
        msg += f", {mass:.3f} kg"
    if risks:
        msg += f". {len(risks)} current reality-risk finding(s)"
    return ToolResult(True, msg + ".")


def summary() -> ToolResult:
    try:
        data = _request("GET", "/api/jarvis/status", timeout=8)
    except ValueError as exc:
        return ToolResult(False, str(exc))
    return ToolResult(True, _compact_json(data.get("project") or {}, 7000))


def designs() -> ToolResult:
    try:
        data = _request("GET", "/api/jarvis/designs", timeout=8)
    except ValueError as exc:
        return ToolResult(False, str(exc))
    rows = data.get("designs") or []
    if not rows:
        return ToolResult(True, "ForgeCAD has no design branches.")
    rendered = []
    for row in rows[:30]:
        state = str(row.get("status") or "unverified").replace("_", " ")
        flags = []
        if row.get("active"): flags.append("active")
        if row.get("physical_verified"): flags.append("works in real life")
        if row.get("protected"): flags.append("protected")
        suffix = f" ({', '.join(flags)})" if flags else ""
        rendered.append(f"{row.get('name')}: {state}{suffix}")
    return ToolResult(True, "ForgeCAD designs: " + "; ".join(rendered))


def history(limit: int = 20) -> ToolResult:
    try:
        data = _request("GET", "/api/jarvis/history", params={"limit": max(1, min(int(limit), 80))}, timeout=8)
    except ValueError as exc:
        return ToolResult(False, str(exc))
    rows = data.get("history") or []
    if not rows:
        return ToolResult(True, "There is no ForgeCAD design history yet.")
    return ToolResult(True, "Recent ForgeCAD history: " + "; ".join(
        f"{r.get('id')} {r.get('message')} by {r.get('actor')}" for r in rows[:20]
    ))


def diff(design: str) -> ToolResult:
    name = design.strip()
    if not name:
        return ToolResult(False, "A ForgeCAD design name is required.")
    try:
        data = _request("GET", f"/api/jarvis/diff/{name}", timeout=10)
    except ValueError as exc:
        return ToolResult(False, str(exc))
    return ToolResult(True, _compact_json(data.get("diff") or data, 7000))


def change(request: str, *, execute: bool = True, always_branch: bool = True) -> ToolResult:
    text = request.strip()
    if not text:
        return ToolResult(False, "The ForgeCAD change request is empty.")
    try:
        data = _request(
            "POST", "/api/jarvis/change",
            body={"text": text, "execute": bool(execute), "always_branch": bool(always_branch)},
            timeout=180.0,
        )
    except ValueError as exc:
        return ToolResult(False, str(exc))
    if not data.get("ok", False):
        return ToolResult(False, str(data.get("message") or data.get("error") or "ForgeCAD did not complete the change."))
    if not data.get("executed"):
        plan = data.get("plan") or {}
        return ToolResult(True, str(data.get("message") or plan.get("summary") or "ForgeCAD prepared the change plan."))
    branch = data.get("design")
    risk_count = len([r for r in (data.get("reality_risks") or []) if r.get("severity") not in {"pass"}])
    stale = int(data.get("stale_simulation_count") or 0)
    msg = str(data.get("message") or f"Updated ForgeCAD design {branch}.")
    if stale:
        msg += f" {stale} prior simulation result(s) are now stale and should be rerun before relying on them."
    if risk_count:
        msg += f" The reality scan has {risk_count} non-pass finding(s)."
    return ToolResult(True, msg)


def analyze(kind: str, object_id: str | None = None, object_name: str | None = None, params: dict[str, Any] | None = None) -> ToolResult:
    resolved_id = object_id
    if not resolved_id and object_name and kind.lower() not in {"reality", "risk", "risk_scan", "reality_scan"}:
        try:
            status_data = _request("GET", "/api/jarvis/status", timeout=8)
            parts = ((status_data.get("project") or {}).get("parts") or [])
            needle = object_name.strip().lower()
            exact = [p for p in parts if str(p.get("name") or "").lower() == needle]
            partial = [p for p in parts if needle and needle in str(p.get("name") or "").lower()]
            match = (exact or partial)[:1]
            if match:
                resolved_id = str(match[0].get("id") or "") or None
        except ValueError:
            pass
    try:
        data = _request("POST", "/api/jarvis/analyze", body={"kind": kind, "object_id": resolved_id, "params": params or {}}, timeout=240.0)
    except ValueError as exc:
        return ToolResult(False, str(exc))
    if kind.lower() in {"reality", "risk", "risk_scan", "reality_scan"}:
        findings = data.get("findings") or []
        return ToolResult(True, "ForgeCAD reality scan: " + "; ".join(str(x.get("title")) for x in findings[:10]))
    result = data.get("result") or {}
    summary = {k: result.get(k) for k in (
        "max_displacement_mm", "max_von_mises_mpa", "yield_fos", "first_mode_hz",
        "max_temperature_c", "min_temperature_c", "avg_temperature_c",
    ) if result.get(k) is not None}
    return ToolResult(True, f"ForgeCAD {kind} analysis completed for {resolved_id}. " + _compact_json(summary, 1800))


def select_component(category: str, constraints: dict[str, Any], *, query: str = "", weights: dict[str, float] | None = None) -> ToolResult:
    if not category.strip():
        return ToolResult(False, "Component category is required.")
    try:
        data = _request("POST", "/api/jarvis/components/select", body={"category": category, "constraints": constraints, "weights": weights or {}, "query": query}, timeout=15)
    except ValueError as exc:
        return ToolResult(False, str(exc))
    if not data.get("ok"):
        return ToolResult(False, "No real catalog component satisfied all required constraints with known source data. " + _compact_json(data.get("alternatives") or [], 2500))
    selected = (data.get("selected") or {}).get("component") or {}
    return ToolResult(True, f"Best feasible ForgeCAD component: {selected.get('manufacturer','')} {selected.get('name') or selected.get('part_number')}. " + _compact_json({"part_number":selected.get("part_number"),"mass_kg":selected.get("mass_kg"),"electrical":selected.get("electrical"),"performance":selected.get("performance"),"procurement":selected.get("procurement")}, 3000))
