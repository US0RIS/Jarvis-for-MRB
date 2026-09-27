"""Live answer to "What can you do right now?" (criteria.md C02).

The answer is computed from what is actually enabled, configured and reachable
on this deployment at the moment of asking, never from documentation.  Every
item is reported as available, unavailable (with the concrete reason) or
unverified (enabled but not recently exercised against its provider).
"""

from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

import jarvis_mrb.world_model as world_model


def _item(name: str, state: str, detail: str) -> dict[str, str]:
    return {"capability": name, "state": state, "detail": detail}


def _safe(name: str, probe: Callable[[], dict[str, str]]) -> dict[str, str]:
    try:
        return probe()
    except Exception as exc:
        return _item(name, "unavailable", f"status check failed ({type(exc).__name__}; e.g. service not running)")


def _local_model() -> dict[str, str]:
    from jarvis_mrb.agent import OLLAMA_MODEL, OLLAMA_URL
    response = httpx.get(f"{OLLAMA_URL.rstrip('/')}/api/tags", timeout=2.5)
    response.raise_for_status()
    names = {str(m.get("name") or "") for m in (response.json().get("models") or [])}
    if OLLAMA_MODEL in names:
        return _item("local conversation/planning model", "available", OLLAMA_MODEL)
    return _item("local conversation/planning model", "unavailable", f"{OLLAMA_MODEL} is not installed in Ollama")


def _google() -> dict[str, str]:
    from jarvis_mrb.tools.google import google_status
    result = google_status()
    return _item("Gmail, Google Calendar and Contacts", "available" if result.ok else "unavailable",
                 "connected" if result.ok else "Google is not authorized on the backend")


def _web() -> dict[str, str]:
    from jarvis_mrb.tools.web import web_status
    result = web_status()
    return _item("web search", "available" if result.ok else "unavailable",
                 "Serper configured" if result.ok else "no web-search key configured")


def _agency() -> dict[str, str]:
    from jarvis_mrb.agency_runtime import get_mode
    from jarvis_mrb.desired_state import list_desired_states
    mode = get_mode()
    active = [s for s in list_desired_states(limit=200) if s.get("state") in {"active", "blocked"}
              and (s.get("authority") or {}).get("agency_enabled") is True]
    return _item("persistent goals (Agency)", "available" if mode == "active" else "limited",
                 f"mode {mode}; {len(active)} goal(s) being pursued" + ("" if mode == "active" else
                 "; say 'my goal is …' and confirm to start pursuing one"))


def _recent_provider_status() -> dict[str, str]:
    """Last real outcome per public provider in the past 24 h (no new calls)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    result: dict[str, str] = {}
    try:
        conn = sqlite3.connect(f"file:{world_model.DB_PATH}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error:
        return result
    with closing(conn):
        try:
            rows = conn.execute(
                """SELECT source_kind,event_type,recorded_at FROM events
                   WHERE source_kind IN ('nws_alerts','open_meteo_air','usgs_earthquakes','opensky','public_camera')
                     AND recorded_at>=? ORDER BY id""", (since,)
            ).fetchall()
        except sqlite3.Error:
            return result
    for kind, event_type, _ in rows:
        result[str(kind)] = "unavailable at last check" if event_type in {
            "world.provider_unavailable", "world.camera_unavailable"} else "worked at last check"
    return result


def _world() -> list[dict[str, str]]:
    recent = _recent_provider_status()

    def status_for(kind: str) -> tuple[str, str]:
        seen = recent.get(kind)
        if seen is None:
            return "unverified", "public provider; not exercised in the past 24 h"
        return ("available" if seen.startswith("worked") else "unavailable"), seen

    items = []
    for kind, label in (("nws_alerts", "US National Weather Service alerts"),
                        ("open_meteo_air", "modelled air quality / UV (Open-Meteo)"),
                        ("usgs_earthquakes", "USGS earthquakes"),
                        ("opensky", "OpenSky aircraft counts")):
        state, detail = status_for(kind)
        items.append(_item(label, state, detail))
    return items


def _cameras() -> dict[str, str]:
    from jarvis_mrb.world_armor_platform import _enabled, list_sources
    if not _enabled():
        return _item("public camera sources", "unavailable",
                     "World Armor camera platform flags are off on the backend")
    sources = list_sources(page_size=200).get("sources") or []
    active = [s for s in sources if s.get("state") == "active"]
    if not active:
        return _item("public camera sources", "limited", "enabled, but no source is enrolled/active")
    return _item("public camera sources", "available",
                 f"{len(active)} enrolled active source(s): " + ", ".join(str(s.get('label')) for s in active[:6]))


def _presence() -> dict[str, str]:
    from jarvis_mrb.world_armor_full import enabled
    from jarvis_mrb.world_places import known_lights
    if not enabled():
        return _item("Apple Home light control (Presence)", "unavailable",
                     "full-scope Presence flag is off on the backend")
    lights = known_lights()
    if not lights:
        return _item("Apple Home light control (Presence)", "limited",
                     "enabled, but the iPhone has not published its Apple Home lights recently")
    return _item("Apple Home light control (Presence)", "available",
                 "lights: " + ", ".join(item["name"] for item in lights[:8]) + " (each change needs your confirmation)")


def _push() -> dict[str, str]:
    from jarvis_mrb.world_armor_push import configured, enabled, status
    if not enabled():
        return _item("closed-app notifications", "unavailable", "push transport disabled on the backend")
    if not configured():
        return _item("closed-app notifications", "unavailable", "APNs credentials not configured on the backend")
    devices = int(status().get("registered_devices") or 0)
    return _item("closed-app notifications", "available" if devices else "limited",
                 f"{devices} registered device(s)")


def _mesh() -> list[dict[str, str]]:
    from jarvis_mrb.reality_mesh import nodes
    listed = nodes().get("nodes") or []
    items = []
    for node in listed:
        if str(node.get("id")) == "windows":
            continue
        status = str(node.get("status") or "unknown")
        items.append(_item(f"paired computer {node.get('label') or node.get('id')}",
                           "available" if status == "online" else "unavailable",
                           f"{status} (checked {node.get('checked_at') or 'now'})"))
    if not items:
        items.append(_item("paired computers (Reality Mesh)", "unavailable", "no Mac/remote node is configured"))
    return items


def _conductor() -> dict[str, str]:
    from jarvis_mrb.conductor import enabled
    return _item("verified app launches on paired computers (Conductor)",
                 "available" if enabled() else "unavailable",
                 "enabled; launches need a one-use confirmation from the iPhone" if enabled()
                 else "Conductor flag is off on the backend")


def _cloud() -> dict[str, str]:
    from jarvis_mrb.cloud_cognition import durable_telemetry
    since = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
    rows = durable_telemetry(since_epoch=since)
    results = [r for r in rows if r.get("event") == "cloud_result"]
    fallbacks = [r for r in rows if r.get("event") == "cloud_fallback"]
    if results and (not fallbacks or results[-1].get("at", 0) >= fallbacks[-1].get("at", 0)):
        return _item("harder reasoning via Groq", "available", "used successfully through your iPhone key in the past 24 h")
    if fallbacks:
        return _item("harder reasoning via Groq", "unavailable",
                     f"last cloud attempt fell back to local ({fallbacks[-1].get('reason') or 'unknown'})")
    return _item("harder reasoning via Groq", "unverified",
                 "only possible when your iPhone has a Groq key and cloud cognition is on; not used in 24 h")


def _sandbox() -> dict[str, str]:
    from jarvis_mrb.sandbox import status
    ready = bool(status().get("docker"))
    return _item("isolated code sandbox", "available" if ready else "unavailable",
                 "Docker ready" if ready else "Docker unavailable")


def live_inventory() -> dict[str, Any]:
    probes: list[tuple[str, Callable[[], Any]]] = [
        ("local conversation/planning model", _local_model), ("Gmail, Google Calendar and Contacts", _google),
        ("web search", _web), ("persistent goals (Agency)", _agency), ("public camera sources", _cameras),
        ("Apple Home light control (Presence)", _presence), ("closed-app notifications", _push),
        ("verified app launches on paired computers (Conductor)", _conductor),
        ("harder reasoning via Groq", _cloud), ("isolated code sandbox", _sandbox),
    ]
    items: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(name, pool.submit(_safe, name, fn)) for name, fn in probes]
        world_future = pool.submit(lambda: _world())
        mesh_future = pool.submit(lambda: _mesh())
        for name, future in futures:
            items.append(future.result())
        try:
            items.extend(world_future.result())
        except Exception as exc:
            items.append(_item("public world evidence", "unavailable", type(exc).__name__))
        try:
            items.extend(mesh_future.result())
        except Exception as exc:
            items.append(_item("paired computers (Reality Mesh)", "unavailable", type(exc).__name__))
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "items": items}


def describe() -> str:
    inventory = live_inventory()
    groups: dict[str, list[str]] = {"available": [], "limited": [], "unverified": [], "unavailable": []}
    for item in inventory["items"]:
        groups.setdefault(item["state"], []).append(f"{item['capability']} ({item['detail']})")
    parts = []
    if groups["available"]:
        parts.append("Working right now: " + "; ".join(groups["available"]) + ".")
    if groups["limited"]:
        parts.append("Enabled but limited: " + "; ".join(groups["limited"]) + ".")
    if groups["unverified"]:
        parts.append("Enabled but not verified recently: " + "; ".join(groups["unverified"]) + ".")
    if groups["unavailable"]:
        parts.append("Unavailable: " + "; ".join(groups["unavailable"]) + ".")
    return " ".join(parts) or "I could not determine my current capabilities."
