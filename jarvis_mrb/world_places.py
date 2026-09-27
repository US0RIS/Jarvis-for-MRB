"""Source-labelled world observations that Agency goals can reason over.

World Armor, NWS, Open-Meteo, USGS and OpenSky adapters already exist as
HTTP/UI surfaces.  This module lets the *same* adapters feed the persistent
world model as provenance-bearing beliefs on exact place/device entities, so a
desired state or a dormant wake watch can say "until the modelled AQI near X
drops below 100" or "until the desk lamp reports on" and Jarvis can notice the
change itself.

Rules kept from the underlying adapters:

* provider unavailability is recorded as unavailable, never as a zero/all-clear;
* every belief carries the provider, provider time where supplied, check time
  and the exact coordinates that were queried;
* coordinates are resolved from literal coordinates, an enrolled World Armor
  investigation, or the public Open-Meteo geocoder (never from private data).
"""

from __future__ import annotations

import json
import math
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from jarvis_mrb.world_model import assert_belief, ensure_entity, record_event

GEOCODER_URL = "https://geocoding-api.open-meteo.com/v1/search"
_COORD_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_REFRESH_LOCK = threading.Lock()
_last_refresh: dict[str, datetime] = {}

# Metric vocabulary exposed to the goal compiler and planner.  Each metric is a
# belief predicate on a place entity written only by observe_place().
PLACE_METRICS: dict[str, str] = {
    "us_aqi": "Open-Meteo/CAMS modelled US AQI (number; model grid, not a street sensor)",
    "pm2_5_ug_m3": "Open-Meteo/CAMS modelled PM2.5 in µg/m³ (number)",
    "uv_index": "Open-Meteo modelled UV index (number)",
    "nws_alert_count": "number of active NWS point alerts (US only; unavailable elsewhere)",
    "nws_alert_events": "list of active NWS alert event names",
    "usgs_quake_count": "USGS M2.5+ earthquakes within 100 km in the past 24 h (number)",
    "usgs_max_magnitude": "largest USGS magnitude within 100 km in the past 24 h (number or null)",
    "aircraft_count": "OpenSky airborne aircraft within 20 km (number; coverage incomplete)",
}
DEVICE_METRICS: dict[str, str] = {
    "power_on": "HomeKit light reported power state (boolean) from the iPhone's Apple Home readback",
    "reachable": "HomeKit accessory reachability reported by the iPhone (boolean)",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _round(value: float) -> float:
    return round(float(value), 3)


# ---------------------------------------------------------------------------
# Place resolution
# ---------------------------------------------------------------------------

def _investigation_place(text: str) -> dict[str, Any] | None:
    try:
        from jarvis_mrb.world_armor_phase1 import list_investigations
        listed = list_investigations()
    except Exception:
        return None
    wanted = " ".join(text.lower().split())
    for item in listed.get("investigations") or []:
        label = " ".join(str(item.get("label") or "").lower().split())
        if label and label == wanted:
            return {
                "name": str(item.get("label")),
                "latitude": float(item["latitude"]),
                "longitude": float(item["longitude"]),
                "resolution": "enrolled World Armor region",
                "source": "world_armor_investigation",
            }
    return None


def geocode(text: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """Resolve a public place name with the Open-Meteo geocoder (no API key)."""
    query = " ".join(str(text or "").split())
    if not 2 <= len(query) <= 120:
        raise ValueError("Place name must be 2-120 characters.")
    parts = [part.strip() for part in query.split(",") if part.strip()]
    name, qualifiers = parts[0], [p.lower() for p in parts[1:]]
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False) as client:
            response = client.get(
                GEOCODER_URL,
                params={"name": name, "count": 10, "language": "en", "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ValueError(f"Place lookup unavailable: {type(exc).__name__}") from exc
    results = [item for item in (data.get("results") or []) if isinstance(item, dict)]

    def matches(item: dict[str, Any]) -> bool:
        haystack = " ".join(
            str(item.get(key) or "").lower()
            for key in ("admin1", "admin2", "country", "country_code")
        )
        return all(q in haystack or q.upper() == str(item.get("country_code") or "") for q in qualifiers)

    candidates = [item for item in results if matches(item)] if qualifiers else results
    if not candidates:
        raise ValueError(f"No public geocoder match for {query!r}.")
    top = candidates[0]
    label = ", ".join(
        str(part) for part in (top.get("name"), top.get("admin1"), top.get("country")) if part
    )
    return {
        "name": label,
        "latitude": float(top["latitude"]),
        "longitude": float(top["longitude"]),
        "resolution": "Open-Meteo public geocoder",
        "source": "open_meteo_geocoder",
        "alternatives": len(candidates) - 1,
    }


def resolve_place(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    match = _COORD_RE.match(raw)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Coordinates out of range.")
        return {"name": f"{_round(lat)},{_round(lon)}", "latitude": lat, "longitude": lon,
                "resolution": "literal coordinates", "source": "user"}
    enrolled = _investigation_place(raw)
    if enrolled:
        return enrolled
    return geocode(raw)


def place_entity(place: dict[str, Any]) -> str:
    key = f"{_round(place['latitude'])},{_round(place['longitude'])}"
    return ensure_entity(
        "place",
        str(place.get("name") or key),
        external_namespace="geo",
        external_id=key,
        attributes={"latitude": place["latitude"], "longitude": place["longitude"],
                    "resolution": place.get("resolution", "")},
    )


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

def _belief(entity_id: str, predicate: str, value: Any, *, event_id: int,
            observed_at: str, evidence: str) -> None:
    assert_belief(entity_id, predicate, value=value, observed_at=observed_at,
                  source_event_id=event_id, evidence=evidence, confidence=0.9)


def observe_place(
    text: str = "",
    *,
    place: dict[str, Any] | None = None,
    include: tuple[str, ...] = ("conditions", "earthquakes"),
) -> dict[str, Any]:
    """Query real providers for one place and record source-labelled beliefs."""
    place = dict(place) if place else resolve_place(text)
    lat, lon = place["latitude"], place["longitude"]
    entity_id = place_entity(place)
    checked = _now().isoformat()
    summary: list[str] = []
    recorded: dict[str, Any] = {}
    providers: dict[str, str] = {}

    if "conditions" in include:
        from jarvis_mrb.physical_conditions import physical_conditions
        try:
            conditions = physical_conditions(lat, lon)
        except Exception as exc:
            conditions = {"air_quality": {"status": "unavailable", "source_note": type(exc).__name__},
                          "weather_alerts": {"status": "unavailable", "alerts": []}}
        air = conditions.get("air_quality") or {}
        providers["open_meteo_air"] = str(air.get("status") or "unavailable")
        if air.get("status") in {"ok", "stale"}:
            event_id = record_event(
                "world.air_quality_observed",
                f"Modelled air quality near {place['name']}: US AQI {air.get('us_aqi')} "
                f"({air.get('status')}; model time {air.get('model_time_utc')}).",
                source_kind="open_meteo_air",
                source_ref=f"{entity_id}:{air.get('model_time_utc')}",
                payload={"place": place, "air_quality": air},
                evidence=str(air.get("source_note") or "")[:600],
                confidence=0.8 if air.get("status") == "ok" else 0.4,
                participants=[(entity_id, "place", 1.0)],
            )
            observed_at = str(air.get("model_time_utc") or checked)
            for key in ("us_aqi", "pm2_5_ug_m3", "uv_index"):
                if air.get(key) is not None:
                    _belief(entity_id, key, air.get(key), event_id=event_id, observed_at=observed_at,
                            evidence=f"Open-Meteo/CAMS model ({air.get('status')}); checked {checked}")
                    recorded[key] = air.get(key)
            summary.append(f"modelled US AQI {air.get('us_aqi')} ({air.get('status')})")
        else:
            summary.append("air-quality model unavailable")

        alerts = conditions.get("weather_alerts") or {}
        providers["nws_alerts"] = str(alerts.get("status") or "unavailable")
        if alerts.get("status") in {"ok", "partial"}:
            items = list(alerts.get("alerts") or [])
            events = sorted({str(item.get("event") or "") for item in items if item.get("event")})
            event_id = record_event(
                "world.nws_alerts_observed",
                f"NWS point alerts near {place['name']}: {len(items)} active"
                + (f" ({', '.join(events)})" if events else "") + f"; checked {checked}.",
                source_kind="nws_alerts",
                source_ref=f"{entity_id}:" + ",".join(sorted(str(i.get('id')) for i in items)),
                payload={"place": place, "alerts": items, "status": alerts.get("status")},
                evidence="Official NWS api.weather.gov point alerts. Zero alerts is not an all-hazards clearance.",
                confidence=0.95,
                participants=[(entity_id, "place", 1.0)],
            )
            _belief(entity_id, "nws_alert_count", len(items), event_id=event_id, observed_at=checked,
                    evidence="NWS point alerts; zero is not an all-hazards clearance")
            _belief(entity_id, "nws_alert_events", events, event_id=event_id, observed_at=checked,
                    evidence="NWS point alerts")
            recorded["nws_alert_count"] = len(items)
            recorded["nws_alert_events"] = events
            summary.append(f"{len(items)} active NWS alerts" + (f": {', '.join(events)}" if events else ""))
        else:
            summary.append(f"NWS alerts {alerts.get('status') or 'unavailable'} (not an all clear)")

    if "earthquakes" in include:
        from jarvis_mrb.public_incidents import regional_earthquakes
        try:
            quakes = regional_earthquakes(lat, lon)
        except Exception as exc:
            quakes = {"status": "unavailable", "source_note": type(exc).__name__}
        providers["usgs_earthquakes"] = str(quakes.get("status") or "unavailable")
        if quakes.get("status") in {"ok", "partial"}:
            items = list(quakes.get("events") or [])
            max_mag = max((float(item.get("magnitude") or 0) for item in items), default=None)
            event_id = record_event(
                "world.usgs_earthquakes_observed",
                f"USGS: {len(items)} M2.5+ earthquakes within 100 km of {place['name']} in the past 24 h"
                + (f"; max M{max_mag}" if max_mag is not None else "") + f"; checked {checked}.",
                source_kind="usgs_earthquakes",
                source_ref=f"{entity_id}:" + ",".join(sorted(str(i.get('id')) for i in items)),
                payload={"place": place, "events": items[:20], "status": quakes.get("status")},
                evidence="USGS earthquake catalog; detection counts, not damage assessment.",
                confidence=0.95,
                participants=[(entity_id, "place", 1.0)],
            )
            _belief(entity_id, "usgs_quake_count", len(items), event_id=event_id, observed_at=checked,
                    evidence="USGS FDSN event catalog")
            _belief(entity_id, "usgs_max_magnitude", max_mag, event_id=event_id, observed_at=checked,
                    evidence="USGS FDSN event catalog")
            recorded["usgs_quake_count"] = len(items)
            summary.append(f"{len(items)} USGS earthquakes (24 h, 100 km)")
        else:
            summary.append("USGS earthquakes unavailable")

    if "airspace" in include:
        from jarvis_mrb.public_airspace import airspace_region
        try:
            air_traffic = airspace_region(lat, lon)
        except Exception as exc:
            air_traffic = {"status": "unavailable", "source_note": type(exc).__name__}
        providers["opensky"] = str(air_traffic.get("status") or "unavailable")
        if air_traffic.get("status") == "ok":
            count = int(air_traffic.get("aircraft_count") or 0)
            event_id = record_event(
                "world.aircraft_count_observed",
                f"OpenSky: {count} airborne aircraft within 20 km of {place['name']}; checked {checked}.",
                source_kind="opensky",
                source_ref=f"{entity_id}:{air_traffic.get('states_at')}",
                payload={"place": place, "aircraft_count": count, "states_at": air_traffic.get("states_at")},
                evidence=str(air_traffic.get("source_note") or "")[:600],
                confidence=0.7,
                participants=[(entity_id, "place", 1.0)],
            )
            _belief(entity_id, "aircraft_count", count, event_id=event_id, observed_at=checked,
                    evidence="OpenSky state vectors; coverage incomplete")
            recorded["aircraft_count"] = count
            summary.append(f"{count} aircraft within 20 km")
        else:
            summary.append(f"OpenSky {air_traffic.get('status') or 'unavailable'}")

    for provider, status in providers.items():
        if status in {"ok", "partial"}:
            continue
        # Unavailable/stale/unsupported coverage is recorded as such: a gap is
        # evidence of a gap, never of an all-clear.
        record_event(
            "world.provider_unavailable",
            f"{provider} returned {status} for {place['name']}; no value recorded.",
            source_kind=provider,
            source_ref=f"{entity_id}:{provider}:{status}:{checked}",
            payload={"place": place, "provider": provider, "status": status},
            evidence="Provider did not supply usable current data for this check.",
            confidence=1.0,
            participants=[(entity_id, "place", 1.0)],
        )
    return {
        "place": place,
        "entity_id": entity_id,
        "checked_at": checked,
        "providers": providers,
        "recorded": recorded,
        "summary": f"{place['name']} ({place['resolution']}): " + "; ".join(summary) + ".",
    }


# ---------------------------------------------------------------------------
# HomeKit light catalog/readback (published by the iPhone)
# ---------------------------------------------------------------------------

def light_entity(target_id: str, label: str) -> str:
    return ensure_entity("homekit_light", label, external_namespace="homekit", external_id=str(target_id).lower())


def record_light_catalog(lights: list[dict[str, Any]]) -> dict[str, Any]:
    checked = _now().isoformat()
    stored = []
    for item in lights[:100]:
        target = str(item.get("id") or "").strip().lower()
        name = " ".join(str(item.get("name") or "").split())[:200]
        if not re.fullmatch(r"[0-9a-f-]{36}", target) or not name:
            continue
        entity_id = light_entity(target, name)
        event_id = record_event(
            "presence.homekit_catalog_observed",
            f"iPhone Apple Home reports light {name}: on={item.get('on')} reachable={item.get('reachable')}.",
            source_kind="iphone_homekit",
            source_ref=f"{target}:{checked}",
            payload={"target_id": target, "name": name, "room": str(item.get("room") or "")[:120],
                     "on": item.get("on"), "reachable": item.get("reachable")},
            evidence="Apple Home catalog read on the user's iPhone.",
            confidence=0.9,
            participants=[(entity_id, "device", 1.0)],
        )
        if isinstance(item.get("on"), bool):
            assert_belief(entity_id, "power_on", value=bool(item["on"]), observed_at=checked,
                          source_event_id=event_id, evidence="iPhone Apple Home catalog read", confidence=0.9)
        if isinstance(item.get("reachable"), bool):
            assert_belief(entity_id, "reachable", value=bool(item["reachable"]), observed_at=checked,
                          source_event_id=event_id, evidence="iPhone Apple Home catalog read", confidence=0.9)
        stored.append({"entity_id": entity_id, "target_id": target, "name": name})
    return {"stored": len(stored), "lights": stored, "checked_at": checked}


def record_light_readback(target_id: str, label: str, *, on: bool, request_id: str, message: str) -> int:
    entity_id = light_entity(target_id, label)
    event_id = record_event(
        "presence.homekit_readback",
        f"Apple Home readback: {label} reported {'on' if on else 'off'}.",
        source_kind="iphone_homekit",
        source_ref=f"presence:{request_id}",
        payload={"target_id": target_id, "request_id": request_id, "on": on, "message": message[:500]},
        evidence="Fresh HomeKit accessory readback on the iPhone after the Presence write.",
        confidence=0.95,
        participants=[(entity_id, "device", 1.0)],
    )
    assert_belief(entity_id, "power_on", value=bool(on), source_event_id=event_id,
                  evidence="Fresh HomeKit accessory readback after Presence write", confidence=0.95)
    return event_id


def known_lights(max_age_hours: int = 72) -> list[dict[str, Any]]:
    """Lights the iPhone has published; stale catalogs are excluded."""
    import sqlite3
    from jarvis_mrb.world_model import DB_PATH

    cutoff = (_now() - timedelta(hours=max_age_hours)).isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT e.id, e.canonical_name, x.external_id,
                   (SELECT value_json FROM beliefs b WHERE b.subject_id=e.id AND b.predicate='power_on'
                      AND b.state='current' ORDER BY b.id DESC LIMIT 1) AS power_on,
                   (SELECT observed_at FROM beliefs b WHERE b.subject_id=e.id AND b.predicate='power_on'
                      AND b.state='current' ORDER BY b.id DESC LIMIT 1) AS observed_at,
                   e.last_seen_at
            FROM entities e JOIN external_ids x ON x.entity_id=e.id AND x.namespace='homekit'
            WHERE e.kind='homekit_light' AND e.last_seen_at>=?
            ORDER BY e.canonical_name
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        try:
            power = json.loads(row["power_on"]) if row["power_on"] is not None else None
        except (TypeError, ValueError):
            power = None
        result.append({"entity_id": row["id"], "name": row["canonical_name"], "target_id": row["external_id"],
                       "power_on": power, "observed_at": row["observed_at"], "last_seen_at": row["last_seen_at"]})
    return result


def resolve_light(text: str) -> dict[str, Any]:
    wanted = " ".join(str(text or "").lower().split())
    lights = known_lights()
    exact = [item for item in lights if item["target_id"] == wanted or item["name"].lower() == wanted]
    if len(exact) == 1:
        return exact[0]
    partial = [item for item in lights if wanted and wanted in item["name"].lower()]
    if len(exact) > 1 or len(partial) > 1:
        raise ValueError(f"Light {text!r} is ambiguous; name it exactly ({', '.join(i['name'] for i in lights)}).")
    if len(partial) == 1:
        return partial[0]
    if not lights:
        raise ValueError("No Apple Home lights have been published by the iPhone recently; open Jarvis on the iPhone with Apple Home connected.")
    raise ValueError(f"No published Apple Home light matches {text!r}. Known: {', '.join(i['name'] for i in lights)}.")


# ---------------------------------------------------------------------------
# Periodic refresh for places referenced by active goals / dormant watches
# ---------------------------------------------------------------------------

def referenced_places() -> list[str]:
    """Place entity IDs referenced by active criteria or active wake watches."""
    from jarvis_mrb.desired_state import list_desired_states, list_wake_watches

    ids: set[str] = set()
    for state in list_desired_states(limit=200):
        if str(state.get("state") or "") not in {"active", "blocked"}:
            continue
        for criterion in state.get("criteria") or []:
            entity = str((criterion or {}).get("entity_id") or "")
            if entity.startswith("place:"):
                ids.add(entity)
    for watch in list_wake_watches():
        if str(watch.get("status") or "") != "active":
            continue
        entity = str((watch.get("condition") or {}).get("entity_id") or "")
        if entity.startswith("place:"):
            ids.add(entity)
    return sorted(ids)


def refresh_referenced(*, min_interval_seconds: int = 600) -> dict[str, Any]:
    """Re-observe places that persistent goals depend on (bounded cadence)."""
    from jarvis_mrb.world_model import get_entity

    refreshed, skipped, errors = [], [], []
    with _REFRESH_LOCK:
        for entity_id in referenced_places():
            last = _last_refresh.get(entity_id)
            if last and (_now() - last).total_seconds() < min_interval_seconds:
                skipped.append(entity_id)
                continue
            entity = get_entity(entity_id) or {}
            attrs = entity.get("attributes") or {}
            lat, lon = attrs.get("latitude"), attrs.get("longitude")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not all(
                math.isfinite(v) for v in (lat, lon)
            ):
                errors.append({"entity_id": entity_id, "error": "place has no coordinates"})
                continue
            _last_refresh[entity_id] = _now()
            place = {"name": entity.get("name") or f"{lat},{lon}", "latitude": float(lat),
                     "longitude": float(lon), "resolution": attrs.get("resolution") or "stored place"}
            try:
                observe_place(place=place, include=("conditions", "earthquakes"))
                refreshed.append(entity_id)
            except Exception as exc:
                errors.append({"entity_id": entity_id, "error": f"{type(exc).__name__}: {exc}"[:200]})
    return {"refreshed": refreshed, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Natural conditions -> exact, freshness-bound desired-state criteria
# ---------------------------------------------------------------------------

_OPS = {"eq", "ne", "lt", "le", "gt", "ge"}


def compile_condition(condition: dict[str, Any], *, observed_after: str | None = None) -> dict[str, Any]:
    """Turn a planner/compiler condition into a grounded ``belief_compare``.

    Accepted forms (anything else is rejected, never guessed):

    * ``{"kind":"world_metric","place":"Seattle, WA","predicate":"us_aqi","op":"lt","value":100}``
    * ``{"kind":"device_state","device":"Desk Lamp","predicate":"power_on","value":true}``

    ``observed_after`` defaults to now, so only a *future* observation can
    satisfy the criterion (an old belief cannot wake a goal or finish it).
    """
    if not isinstance(condition, dict):
        raise ValueError("Condition must be an object.")
    kind = str(condition.get("kind") or "")
    predicate = str(condition.get("predicate") or "").strip()
    op = str(condition.get("op") or "eq").strip()
    if op not in _OPS:
        raise ValueError(f"Condition op must be one of {sorted(_OPS)}.")
    value = condition.get("value")
    after = observed_after or _now().isoformat()
    if kind == "world_metric":
        if predicate not in PLACE_METRICS:
            raise ValueError(f"Unknown world metric {predicate!r}; known: {', '.join(sorted(PLACE_METRICS))}.")
        place = resolve_place(str(condition.get("place") or ""))
        entity_id = place_entity(place)
        label = f"{predicate} {op} {value!r} at {place['name']}"
    elif kind == "device_state":
        if predicate not in DEVICE_METRICS:
            raise ValueError(f"Unknown device predicate {predicate!r}; known: {', '.join(sorted(DEVICE_METRICS))}.")
        light = resolve_light(str(condition.get("device") or ""))
        entity_id = light["entity_id"]
        if predicate in {"power_on", "reachable"} and not isinstance(value, bool):
            value = str(value).strip().lower() in {"true", "on", "1", "yes"}
        label = f"{light['name']} {predicate} {op} {value!r}"
    else:
        raise ValueError("Condition kind must be world_metric or device_state.")
    if op in {"lt", "le", "gt", "ge"} and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ValueError("Ordering comparisons need a numeric value.")
    return {
        "kind": "belief_compare",
        "entity_id": entity_id,
        "predicate": predicate,
        "op": op,
        "value": value,
        "observed_after": after,
        "label": label,
    }
