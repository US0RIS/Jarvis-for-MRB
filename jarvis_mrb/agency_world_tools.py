"""Permission-gated conversational/Agency tools over the real-world subsystems.

Before this module, World Armor, the NWS/Open-Meteo/USGS/OpenSky adapters,
public camera sources, Presence (HomeKit) and Reality Mesh were reachable only
through dedicated HTTP routes and iPhone screens.  Jarvis could therefore not
*compose* them into a persistent goal.  These tools expose the same adapters
through the ordinary tool boundary so that:

* every call crosses ``permissions.decide`` (reads auto, physical writes confirm);
* every write gets an independent verifier in ``world_verification``;
* every observation lands in the world model with provider provenance.

No new authority is created here.  Presence still requires the full-scope flag,
the iPhone's own Apple Home catalog, a one-use short-lived grant and a fresh
accessory readback; camera observation still requires an operator-enrolled,
active source grant.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import Any

# Tool name -> (risk class, argument signature shown to planners)
WORLD_TOOLS: dict[str, tuple[str, str]] = {
    "world.observe_place": (
        "read",
        '{"place": "city/region name or \'lat,lon\'", "include": ["conditions","earthquakes","airspace"]}'
        " -> live NWS alerts, modelled air quality, USGS quakes, OpenSky aircraft count, recorded as place beliefs",
    ),
    "world.camera_sources": ("read", "{} -> enrolled public camera/media sources and their state"),
    "world.observe_camera": (
        "read",
        '{"source": "exact enrolled source label or id"} -> fetch one current public frame and interpret the enrolled scene question',
    ),
    "presence.lights": ("read", "{} -> Apple Home lights the iPhone has published, with last reported power state"),
    "presence.set_light": (
        "external_write",
        '{"light": "exact light name", "on": true|false} -> physical HomeKit light change on the iPhone; verified by fresh accessory readback',
    ),
    "mesh.nodes": ("read", "{} -> paired computers and whether each is actually reachable right now"),
}


@dataclass(frozen=True)
class WorldToolResult:
    ok: bool
    message: str
    data: Any = None


def _fail(message: str) -> WorldToolResult:
    return WorldToolResult(False, message)


def observe_place(args: dict[str, Any]) -> WorldToolResult:
    from jarvis_mrb.world_places import observe_place as observe

    place = str(args.get("place") or "").strip()
    if not place:
        return _fail("world.observe_place requires a place.")
    include_raw = args.get("include") or ["conditions", "earthquakes"]
    if isinstance(include_raw, str):
        include_raw = [include_raw]
    include = tuple(item for item in include_raw if item in {"conditions", "earthquakes", "airspace"})
    if not include:
        include = ("conditions", "earthquakes")
    try:
        result = observe(place, include=include)
    except ValueError as exc:
        return _fail(str(exc))
    unavailable = [name for name, status in result["providers"].items() if status not in {"ok", "partial", "stale"}]
    message = result["summary"]
    if unavailable:
        message += " Unavailable providers: " + ", ".join(unavailable) + " (missing data is not an all clear)."
    return WorldToolResult(True, message, result)


def _platform_sources() -> list[dict[str, Any]]:
    from jarvis_mrb.world_armor_platform import list_sources

    sources: list[dict[str, Any]] = []
    offset: int | None = 0
    while offset is not None and len(sources) < 1000:
        page = list_sources(offset=offset, page_size=200)
        sources.extend(page.get("sources") or [])
        offset = page.get("next_offset")
    return sources


def camera_sources(args: dict[str, Any]) -> WorldToolResult:
    try:
        sources = _platform_sources()
    except RuntimeError as exc:
        return _fail(f"Public camera sources unavailable: {exc}")
    if not sources:
        return WorldToolResult(True, "No public camera/media sources are enrolled.", {"sources": []})
    lines = [
        f"{item.get('label')} [{item.get('kind')}, {item.get('state')}; last {item.get('last_outcome') or 'never checked'}"
        f" at {item.get('last_checked_at') or '-'}; scene question: {item.get('scene_goal') or 'none'}]"
        for item in sources
    ]
    return WorldToolResult(True, "Enrolled public sources: " + "; ".join(lines), {"sources": sources})


def _find_source(text: str) -> dict[str, Any]:
    wanted = " ".join(str(text or "").lower().split())
    sources = _platform_sources()
    exact = [s for s in sources if str(s.get("id")) == wanted or str(s.get("label") or "").lower() == wanted]
    if len(exact) == 1:
        return exact[0]
    partial = [s for s in sources if wanted and wanted in str(s.get("label") or "").lower()]
    if len(partial) == 1 and not exact:
        return partial[0]
    if not sources:
        raise ValueError("No public camera sources are enrolled; enroll one in World Armor first.")
    raise ValueError(
        f"Camera source {text!r} is {'ambiguous' if (exact or partial) else 'not enrolled'}. "
        "Enrolled: " + ", ".join(str(s.get("label")) for s in sources)
    )


def observe_camera(args: dict[str, Any]) -> WorldToolResult:
    from jarvis_mrb.world_armor_observe import observe_source
    from jarvis_mrb.world_model import assert_belief, ensure_entity, record_event

    try:
        source = _find_source(str(args.get("source") or ""))
    except (ValueError, RuntimeError) as exc:
        return _fail(str(exc))
    if str(source.get("state")) != "active":
        return _fail(f"Camera source {source.get('label')} is {source.get('state')}; it will not be collected.")
    try:
        receipt = observe_source(str(source["id"]))
    except (ValueError, KeyError, RuntimeError) as exc:
        return _fail(f"Camera observation failed: {exc}")
    status = str(receipt.get("status") or "")
    entity_id = ensure_entity(
        "public_camera_source", str(source.get("label")),
        external_namespace="world_armor_source", external_id=str(source["id"]),
        attributes={"kind": source.get("kind"), "scene_goal": source.get("scene_goal"),
                    "latitude": source.get("latitude"), "longitude": source.get("longitude")},
    )
    if status != "ok":
        record_event(
            "world.camera_unavailable",
            f"Public camera {source.get('label')} not observed: {receipt.get('status')} {receipt.get('error_type') or ''}".strip(),
            source_kind="public_camera", source_ref=f"{source['id']}:{receipt.get('status')}",
            payload={"receipt": receipt}, evidence="World Armor source check did not yield evidence.",
            confidence=0.9, participants=[(entity_id, "source", 1.0)],
        )
        return WorldToolResult(False, f"Camera {source.get('label')} unavailable/stale: {receipt.get('status')}.", receipt)
    if receipt.get("change_kind") == "same_published_image_not_new_capture":
        return WorldToolResult(
            True,
            f"Camera {source.get('label')} is re-serving the same published image; no new physical observation.",
            receipt,
        )
    description, decision = "", str(receipt.get("condition_status") or "")
    try:
        from jarvis_mrb.world_armor_platform import _connect, _dbpath
        with closing(_connect(_dbpath(None))) as con:
            row = con.execute(
                "SELECT description,retrieved_at,media_kind,source_display FROM source_evidence WHERE id=?",
                (str(receipt.get("evidence_id") or ""),),
            ).fetchone()
        if row is not None:
            description = str(row["description"] or "")
    except (sqlite3.Error, RuntimeError):
        pass
    event_id = record_event(
        "world.camera_observed",
        f"Public camera {source.get('label')}: {description[:400]} "
        f"(scene question {source.get('scene_goal') or 'none'}: {decision or 'n/a'}; publisher capture time unverified).",
        source_kind="public_camera", source_ref=f"{source['id']}:{receipt.get('evidence_id')}",
        payload={"receipt": receipt, "source_id": source["id"]},
        evidence="Local-model interpretation of a publicly published frame; visible evidence, not confirmed identity or incident.",
        confidence=0.6, participants=[(entity_id, "source", 1.0)],
    )
    if decision:
        assert_belief(entity_id, "scene_condition", value=decision, source_event_id=event_id,
                      evidence="World Armor bounded perception of the enrolled scene question", confidence=0.6)
    return WorldToolResult(
        True,
        f"Camera {source.get('label')} (retrieved now; publisher capture time unverified): {description} "
        f"Scene question '{source.get('scene_goal') or 'none'}': {decision or 'not asked'}.",
        {**receipt, "description": description, "entity_id": entity_id},
    )


def presence_lights(args: dict[str, Any]) -> WorldToolResult:
    from jarvis_mrb.world_places import known_lights

    lights = known_lights()
    if not lights:
        return WorldToolResult(True, "The iPhone has not published any Apple Home lights recently.", {"lights": []})
    return WorldToolResult(
        True,
        "Apple Home lights published by the iPhone: " + "; ".join(
            f"{item['name']} (last reported {'on' if item['power_on'] else 'off' if item['power_on'] is False else 'unknown'}"
            f" at {item['observed_at'] or 'unknown'})" for item in lights
        ),
        {"lights": lights},
    )


def presence_set_light(args: dict[str, Any]) -> WorldToolResult:
    from jarvis_mrb.world_armor_full import create_presence_grant, dispatch_presence, enabled
    from jarvis_mrb.world_places import resolve_light

    if not enabled():
        return _fail("Presence is disabled (JARVIS_WORLD_ARMOR_FULL_ENABLED is not set on the backend).")
    desired = args.get("on")
    if not isinstance(desired, bool):
        text = str(desired or "").strip().lower()
        if text in {"true", "on", "1", "yes"}:
            desired = True
        elif text in {"false", "off", "0", "no"}:
            desired = False
        else:
            return _fail("presence.set_light requires on=true or on=false.")
    try:
        light = resolve_light(str(args.get("light") or ""))
    except ValueError as exc:
        return _fail(str(exc))
    try:
        grant = create_presence_grant(
            actuator_kind="homekit_light",
            target_id=light["target_id"],
            target_label=light["name"],
            lifetime_seconds=120,
            max_uses=1,
        )
        receipt = dispatch_presence(str(grant["id"]), desired_on=bool(desired))
    except (ValueError, KeyError, RuntimeError) as exc:
        return _fail(f"Presence dispatch refused: {exc}")
    data = {
        "request_id": receipt.get("id") or receipt.get("request_id"),
        "grant_id": grant["id"],
        "target_id": light["target_id"],
        "target_label": light["name"],
        "desired_on": bool(desired),
        "dispatch_status": receipt.get("status"),
    }
    if str(receipt.get("status")) not in {"dispatched_unverified"}:
        return WorldToolResult(False, f"Presence request for {light['name']} was not delivered: {receipt.get('status')}.", data)
    return WorldToolResult(
        True,
        f"Sent a one-use request to the iPhone to turn {light['name']} {'on' if desired else 'off'}; "
        "unverified until Apple Home reads the accessory back.",
        data,
    )


def mesh_nodes(args: dict[str, Any]) -> WorldToolResult:
    from jarvis_mrb.reality_mesh import nodes

    try:
        listed = nodes().get("nodes") or []
    except Exception as exc:
        return _fail(f"Reality Mesh unavailable: {exc}")
    parts = [
        f"{item.get('label') or item.get('id')} ({item.get('platform') or '?'}): {item.get('status')}"
        for item in listed
    ]
    return WorldToolResult(True, "Paired devices: " + "; ".join(parts), {"nodes": listed})


HANDLERS = {
    "world.observe_place": observe_place,
    "world.camera_sources": camera_sources,
    "world.observe_camera": observe_camera,
    "presence.lights": presence_lights,
    "presence.set_light": presence_set_light,
    "mesh.nodes": mesh_nodes,
}


def execute(tool: str, args: dict[str, Any]) -> WorldToolResult:
    handler = HANDLERS.get(tool)
    if handler is None:
        return _fail(f"Unknown world tool {tool}.")
    return handler(dict(args or {}))


def presence_enabled() -> bool:
    return os.getenv("JARVIS_WORLD_ARMOR_FULL_ENABLED") == "1" and os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1"
