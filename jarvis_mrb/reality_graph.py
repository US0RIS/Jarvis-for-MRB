from __future__ import annotations

"""Deterministic Reality Graph.

A small, inspectable world-state layer that turns provider observations into
typed entities, relations, evidence and derived facts before an LLM sees them.
It deliberately contains no model calls and grants no action authority.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any, Iterable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(stamp: str, *, now: datetime | None = None) -> float | None:
    try:
        value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if value.tzinfo is None:
            return None
        return max(0.0, ((now or datetime.now(timezone.utc)) - value).total_seconds())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Entity:
    id: str
    kind: str
    label: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: str
    object: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Evidence:
    id: str
    source: str
    observed_at: str
    age_seconds: float | None
    freshness: str
    claim: str


@dataclass(frozen=True)
class DerivedFact:
    id: str
    rule: str
    value: Any
    confidence: str
    evidence_ids: tuple[str, ...]
    explanation: str


def _freshness(age: float | None, ttl: float) -> str:
    if age is None:
        return "unknown"
    return "fresh" if age <= ttl else "stale"


def _safe_id(value: Any) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or ""))
    return "_".join(part for part in text.split("_") if part)[:80] or "unknown"


def build_place_graph(latitude: float, longitude: float, observation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile existing public/provider observations into a model-free graph.

    This does not perform person identification, infer private activity, or turn
    camera catalog membership into a live observation.
    """
    if observation is None:
        from jarvis_mrb.physical_awareness import physical_awareness
        observation = physical_awareness(latitude, longitude)

    place_id = "place:query"
    entities: list[Entity] = [
        Entity(place_id, "place", "Observed place", {
            "latitude": round(float(latitude), 6),
            "longitude": round(float(longitude), 6),
        })
    ]
    relations: list[Relation] = []
    evidence: list[Evidence] = []
    facts: list[DerivedFact] = []

    checked = str(observation.get("checked_at") or _now())
    cameras = observation.get("cameras") if isinstance(observation.get("cameras"), dict) else {}
    camera_rows = cameras.get("cameras") if isinstance(cameras.get("cameras"), list) else []
    camera_evidence: list[str] = []
    for index, row in enumerate(camera_rows[:24]):
        if not isinstance(row, dict):
            continue
        raw_id = row.get("id") or row.get("camera_id") or index
        entity_id = "camera:" + _safe_id(raw_id)
        label = str(row.get("name") or row.get("label") or "Official public camera")[:120]
        entities.append(Entity(entity_id, "public_camera", label, {
            "provider": str(row.get("provider") or "official catalog")[:80],
            "live_image_verified": False,
        }))
        ev_id = "ev:camera_catalog:" + _safe_id(raw_id)
        age = _age_seconds(str(cameras.get("checked_at") or checked))
        evidence.append(Evidence(
            ev_id, "camera_catalog", str(cameras.get("checked_at") or checked),
            age, _freshness(age, 900),
            "Official provider catalog reports a camera viewpoint near this place; this is not proof of current imagery.",
        ))
        camera_evidence.append(ev_id)
        relations.append(Relation(entity_id, "catalog_near", place_id, (ev_id,)))

    conditions = observation.get("conditions") if isinstance(observation.get("conditions"), dict) else {}
    air = conditions.get("air_quality") if isinstance(conditions.get("air_quality"), dict) else {}
    if air.get("status") == "ok" and air.get("us_aqi") is not None:
        ev_id = "ev:air_quality"
        stamp = str(conditions.get("checked_at") or checked)
        age = _age_seconds(stamp)
        value = round(float(air["us_aqi"]))
        evidence.append(Evidence(ev_id, "openmeteo_air", stamp, age, _freshness(age, 1800), f"Modelled US AQI is {value}."))
        facts.append(DerivedFact("fact:air_quality", "provider_value", value, "provider_reported", (ev_id,), "Direct modelled provider value; not a local sensor."))

    alerts = conditions.get("weather_alerts") if isinstance(conditions.get("weather_alerts"), dict) else {}
    alert_rows = alerts.get("alerts") if isinstance(alerts.get("alerts"), list) else []
    if alerts.get("status") == "ok":
        ev_id = "ev:weather_alerts"
        stamp = str(conditions.get("checked_at") or checked)
        age = _age_seconds(stamp)
        evidence.append(Evidence(ev_id, "nws", stamp, age, _freshness(age, 600), f"Provider returned {len(alert_rows)} active point alert(s)."))
        facts.append(DerivedFact("fact:active_weather_alert_count", "count_provider_rows", len(alert_rows), "high", (ev_id,), "Counted returned active alert records; zero is not an all-hazards clearance."))

    incidents = observation.get("incidents") if isinstance(observation.get("incidents"), dict) else {}
    incident_rows = incidents.get("events") if isinstance(incidents.get("events"), list) else []
    if incidents.get("status") == "ok":
        ev_id = "ev:earthquakes"
        stamp = str(incidents.get("checked_at") or checked)
        age = _age_seconds(stamp)
        evidence.append(Evidence(ev_id, "usgs", stamp, age, _freshness(age, 900), f"USGS query returned {len(incident_rows)} qualifying regional event(s)."))
        facts.append(DerivedFact("fact:regional_earthquake_count", "count_provider_rows", len(incident_rows), "high", (ev_id,), "Counted provider events under the existing query boundary."))

    facilities = observation.get("facilities") if isinstance(observation.get("facilities"), dict) else {}
    facility_rows = facilities.get("facilities") if isinstance(facilities.get("facilities"), list) else []
    if facilities.get("status") == "ok":
        ev_id = "ev:facilities"
        stamp = str(facilities.get("checked_at") or checked)
        age = _age_seconds(stamp)
        evidence.append(Evidence(ev_id, "openstreetmap", stamp, age, _freshness(age, 86400), f"Public mapping returned {len(facility_rows)} nearby facility record(s)."))
        facts.append(DerivedFact("fact:nearby_facility_count", "count_provider_rows", len(facility_rows), "provider_reported", (ev_id,), "Counted community-mapped facility records."))

    # Deterministic completeness/risk signal. Unknown provider state increases
    # uncertainty; absence never becomes an all-clear.
    provider_states = {
        "cameras": str(cameras.get("status") or "unknown"),
        "air_quality": str(air.get("status") or "unknown"),
        "weather_alerts": str(alerts.get("status") or "unknown"),
        "incidents": str(incidents.get("status") or "unknown"),
        "facilities": str(facilities.get("status") or "unknown"),
    }
    unavailable = sorted(k for k, v in provider_states.items() if v != "ok")
    facts.append(DerivedFact(
        "fact:observation_completeness", "provider_status_matrix",
        "complete_for_integrated_sources" if not unavailable else "partial",
        "high", tuple(),
        "Integrated provider gaps: " + (", ".join(unavailable) if unavailable else "none") + ".",
    ))

    return {
        "schema": "jarvis.reality_graph.v1",
        "generated_at": _now(),
        "model_calls": 0,
        "action_authority": "none",
        "scope": {"kind": "place_snapshot", "latitude": round(float(latitude), 6), "longitude": round(float(longitude), 6)},
        "entities": [asdict(x) for x in entities],
        "relations": [asdict(x) for x in relations],
        "evidence": [asdict(x) for x in evidence],
        "derived_facts": [asdict(x) for x in facts],
        "provider_states": provider_states,
    }


def model_context(graph: dict[str, Any], *, max_facts: int = 12, max_evidence: int = 12) -> dict[str, Any]:
    """Return the small semantic packet an LLM may see only when language or
    novel planning is actually required. Raw provider payloads stay outside.
    """
    facts = list(graph.get("derived_facts") or [])[:max(0, min(max_facts, 30))]
    evidence = list(graph.get("evidence") or [])[:max(0, min(max_evidence, 30))]
    return {
        "schema": graph.get("schema"),
        "generated_at": graph.get("generated_at"),
        "scope": graph.get("scope"),
        "provider_states": graph.get("provider_states"),
        "facts": facts,
        "evidence": [{
            "id": row.get("id"), "source": row.get("source"),
            "freshness": row.get("freshness"), "claim": row.get("claim"),
        } for row in evidence if isinstance(row, dict)],
        "omitted_raw_provider_payloads": True,
    }


def answer_place_question(graph: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Narrow deterministic Q&A. A miss explicitly escalates instead of guessing."""
    q = " ".join(str(question or "").lower().split()).strip(" ?.!")
    facts = {str(row.get("id")): row for row in graph.get("derived_facts", []) if isinstance(row, dict)}
    if q in {"how many nearby public cameras are there", "how many public cameras are nearby", "are there public cameras nearby"}:
        count = sum(1 for row in graph.get("entities", []) if isinstance(row, dict) and row.get("kind") == "public_camera")
        return {"answered_without_model": True, "answer": f"{count} official catalog camera viewpoint(s) are represented nearby. Catalog presence does not prove a current live image.", "evidence_kind": "catalog"}
    if q in {"what is the air quality", "what's the air quality", "air quality"} and "fact:air_quality" in facts:
        return {"answered_without_model": True, "answer": f"Modelled US AQI is {facts['fact:air_quality']['value']}.", "evidence_kind": "provider_value"}
    if q in {"are there weather alerts", "any weather alerts", "weather alerts"} and "fact:active_weather_alert_count" in facts:
        n = int(facts["fact:active_weather_alert_count"]["value"])
        return {"answered_without_model": True, "answer": f"The integrated weather provider returned {n} active point alert(s). This is not an all-hazards clearance.", "evidence_kind": "provider_count"}
    if q in {"what do you know about this place", "summarize this place", "reality graph status"}:
        parts = [str(row.get("explanation") or "") for row in graph.get("derived_facts", []) if isinstance(row, dict)]
        return {"answered_without_model": True, "answer": " ".join(p for p in parts if p)[:1200], "evidence_kind": "derived_facts"}
    return None
