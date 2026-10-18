"""View models: command center, dynamic COP, coverage, world search, describe.

future.md ideas implemented here: Command-center / world-model dashboard as a
real destination view, Dynamic Common Operating Picture (temporary view
synthesised around a question/mission, torn down after), Coverage map (where HORUS
can sense *and* where it has no evidence), World Search (live observations as a
queryable corpus using the standing-query DSL), Describe-on-Demand ("what am I
looking at / what changed / what's important" with explicit uncertainty),
Interface Semantic Overlay (normalise heterogeneous accessibility trees into one
interaction layer), and Real-time Guardian alerting (level-triggered watchdog
results routed through attention arbitration instead of read-only evidence).

These functions build plain JSON view models; rendering belongs to the iOS/web
front ends.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Iterable

from jarvis_mrb.horus._util import as_dt, haversine_m, jaccard, tokens
from jarvis_mrb.horus.attention import AttentionCommander, Context, InfoObject
from jarvis_mrb.horus.standing import InvariantWatchdog, Predicate


def command_center(*, now: datetime, health: list[dict[str, str]], modes: dict[str, str], missions: list[str],
                   alerts: list[dict[str, Any]], next_items: dict[str, Any], coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Standing aggregate view (base-of-operations screen)."""
    worst = "ok"
    for h in health:
        if h["state"] == "failing":
            worst = "failing"
        elif h["state"] in ("stale", "unknown") and worst == "ok":
            worst = "degraded"
    return {"generated_at": as_dt(now).isoformat(), "overall": worst, "status": health, "modes": modes,
            "active_missions": missions, "alerts": sorted(alerts, key=lambda a: a.get("priority_rank", 9)),
            "next": next_items, "coverage": coverage or {}}


def dynamic_cop(question: str, layers: dict[str, list[dict[str, Any]]], *, mission_entities: Iterable[str] = (),
                region: tuple[float, float, float] | None = None, max_items_per_layer: int = 8) -> dict[str, Any]:
    """Synthesize a temporary operational picture: only relevant layers/entities.
    ``layers``: name -> items ``{"id", "text", "lat"?, "lon"?, "entity"?}``;
    ``region``: (lat, lon, radius_m)."""
    qt = set(tokens(question))
    ents = set(mission_entities)
    picture: dict[str, list[dict[str, Any]]] = {}
    for name, items in layers.items():
        keep = []
        for it in items:
            rel = jaccard(qt, tokens(it.get("text", ""))) + (1.0 if it.get("entity") in ents else 0.0)
            if region and "lat" in it and "lon" in it:
                if haversine_m(region[0], region[1], it["lat"], it["lon"]) > region[2]:
                    continue
                rel += 0.3
            if rel > 0.1:
                keep.append((rel, it))
        if keep:
            picture[name] = [it for _, it in sorted(keep, key=lambda x: -x[0])[:max_items_per_layer]]
    return {"question": question, "layers": picture, "omitted_layers": sorted(set(layers) - set(picture)),
            "lifecycle": "temporary: archive when the question/mission closes"}


def coverage_map(sources: list[dict[str, Any]], *, bbox: tuple[float, float, float, float], cell_deg: float = 0.05,
                 now: datetime, stale_after: timedelta = timedelta(minutes=30)) -> dict[str, Any]:
    """Grid of cells marked live / stale / none.  Sources: ``{"id","lat","lon","radius_m","last_seen"}``.
    Blank cells are reported explicitly: no evidence is not an all-clear."""
    lat0, lon0, lat1, lon1 = bbox
    rows = max(1, math.ceil((lat1 - lat0) / cell_deg))
    cols = max(1, math.ceil((lon1 - lon0) / cell_deg))
    grid, counts = [], {"live": 0, "stale": 0, "none": 0}
    for r in range(rows):
        row = []
        for c in range(cols):
            clat, clon = lat0 + (r + 0.5) * cell_deg, lon0 + (c + 0.5) * cell_deg
            state = "none"
            for s in sources:
                if haversine_m(clat, clon, s["lat"], s["lon"]) <= s["radius_m"]:
                    fresh = as_dt(now) - as_dt(s["last_seen"]) <= stale_after
                    state = "live" if fresh else ("stale" if state == "none" else state)
                    if state == "live":
                        break
            counts[state] += 1
            row.append(state)
        grid.append(row)
    total = rows * cols
    return {"grid": grid, "counts": counts, "blind_fraction": round(counts["none"] / total, 3),
            "note": "cells marked 'none' have no evidence; that is not an all-clear"}


def world_search(observations: list[dict[str, Any]], where: str, *, near: tuple[float, float] | None = None,
                 radius_m: float | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Query live observations ("aircraft within 20 miles currently descending")."""
    pred = Predicate(where)
    out = []
    for o in observations:
        rec = dict(o)
        if near is not None and "lat" in o and "lon" in o:
            rec["distance_m"] = haversine_m(near[0], near[1], o["lat"], o["lon"])
            rec["distance_mi"] = rec["distance_m"] / 1609.344
            if radius_m is not None and rec["distance_m"] > radius_m:
                continue
        if pred(rec):
            out.append(rec)
    return sorted(out, key=lambda r: r.get("distance_m", 0))[:limit]


def describe_scene(detections: list[dict[str, Any]], *, previous: list[dict[str, Any]] | None = None,
                   important_labels: Iterable[str] = ("person", "smoke", "fire", "water", "vehicle", "warning sign"),
                   min_conf: float = 0.5) -> dict[str, Any]:
    """Describe-on-Demand over detections ``{"label","confidence"}`` with explicit
    uncertainty and change versus a prior view."""
    confident = [d for d in detections if d["confidence"] >= min_conf]
    unsure = [d for d in detections if d["confidence"] < min_conf]
    labels = sorted({d["label"] for d in confident})
    imp = set(important_labels)
    out = {
        "seen": labels,
        "maybe": sorted({d["label"] for d in unsure}),
        "important": sorted(l for l in labels if l in imp),
        "summary": ("I can see " + ", ".join(labels) + "." if labels else "I can't identify anything with confidence.")
        + (" Possibly also: " + ", ".join(sorted({d['label'] for d in unsure})) + "." if unsure else ""),
    }
    if previous is not None:
        before = {d["label"] for d in previous if d["confidence"] >= min_conf}
        out["changed"] = {"appeared": sorted(set(labels) - before), "gone": sorted(before - set(labels))}
    return out


ROLE_MAP = {
    "button": "button", "AXButton": "button", "push button": "button", "ButtonControl": "button",
    "link": "link", "AXLink": "link", "HyperlinkControl": "link",
    "textbox": "text_input", "AXTextField": "text_input", "EditControl": "text_input", "edit": "text_input",
    "checkbox": "toggle", "AXCheckBox": "toggle", "CheckBoxControl": "toggle",
    "combobox": "choice", "AXPopUpButton": "choice", "ComboBoxControl": "choice",
    "menuitem": "menu_item", "AXMenuItem": "menu_item", "MenuItemControl": "menu_item",
}
VERBS = {"button": ["press"], "link": ["open"], "text_input": ["set_text", "read"], "toggle": ["toggle", "read"],
         "choice": ["choose", "read"], "menu_item": ["press"]}


def semantic_overlay(tree: list[dict[str, Any]], *, app: str) -> list[dict[str, Any]]:
    """Interface Semantic Overlay: map UIA/AX/ARIA nodes to one interaction vocabulary."""
    out = []
    for i, node in enumerate(tree):
        role = ROLE_MAP.get(node.get("role", ""))
        if role is None:
            continue
        name = node.get("name") or node.get("label") or node.get("title") or ""
        out.append({"ref": f"{app}#{i}", "role": role, "name": name, "verbs": VERBS[role],
                    "enabled": node.get("enabled", True), "accessible": bool(name)})
    return out


def guardian_alerts(watchdog: InvariantWatchdog, trigger: str, readings: dict[str, list[dict[str, Any]]],
                    commander: AttentionCommander, ctx: Context) -> dict[str, Any]:
    """Real-time Guardian alerting: level-triggered invariant failures become
    attention-arbitrated proactive alerts (insufficient evidence is surfaced as its
    own low-urgency state, never silently treated as all-clear)."""
    results = watchdog.check(trigger, readings, ctx.now)
    items = []
    for r in results:
        urgency = "critical" if r["status"] == "violated" and watchdog.assertions[r["assertion"]].critical else \
            "high" if r["status"] in ("violated", "sensor_disagreement") else "low"
        items.append(InfoObject(
            id=f"guardian:{r['assertion']}:{r['status']}", title=f"Guardian: {r['assertion']}",
            body=f"{r['status'].replace('_', ' ')}" + (f" — {r['intervention']}" if r.get("intervention") else ""),
            urgency=urgency, evidence=r["live_sources"] or r["problems"], reason=f"assertion:{r['assertion']}",
            confidence=0.9 if r["status"] == "violated" else 0.7, source="guardian", consequence=0.8))
    return {"results": results, "delivery": commander.arbitrate(items, ctx) if items else {"shown": [], "demoted": []}}
