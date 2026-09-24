from __future__ import annotations

"""Deterministic Reality Graph.

This module is intentionally boring: provider observations become typed facts,
relations and mission state before any language model sees them.  It performs
no model calls and has no action authority.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _age_seconds(stamp: Any, *, now: datetime | None = None) -> float | None:
    dt = _parse_time(stamp)
    if dt is None:
        return None
    age = ((now or datetime.now(timezone.utc)) - dt).total_seconds()
    # Future-dated provider observations are not current evidence. Allow small clock skew.
    return age if age >= -30.0 else None


def _freshness(age: float | None, ttl: float) -> str:
    if age is None:
        return "unknown"
    return "fresh" if -30.0 <= age <= ttl else "stale"


def _safe_id(value: Any) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or ""))
    return "_".join(part for part in text.split("_") if part)[:80] or "unknown"


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


def build_place_graph(latitude: float, longitude: float, observation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile public/provider observations into a model-free graph."""
    if observation is None:
        from jarvis_mrb.physical_awareness import physical_awareness
        observation = physical_awareness(latitude, longitude)

    place_id = "place:query"
    entities = [Entity(place_id, "place", "Observed place", {
        "latitude": round(float(latitude), 6), "longitude": round(float(longitude), 6)
    })]
    relations: list[Relation] = []
    evidence: list[Evidence] = []
    facts: list[DerivedFact] = []
    checked = str(observation.get("checked_at") or _now())

    cameras = observation.get("cameras") if isinstance(observation.get("cameras"), dict) else {}
    rows = cameras.get("cameras") if isinstance(cameras.get("cameras"), list) else []
    for index, row in enumerate(rows[:24]):
        if not isinstance(row, dict):
            continue
        raw_id = row.get("id") or row.get("camera_id") or index
        eid = "camera:" + _safe_id(raw_id)
        entities.append(Entity(eid, "public_camera", str(row.get("name") or row.get("label") or "Official public camera")[:120], {
            "provider": str(row.get("provider") or "official catalog")[:80],
            "live_image_verified": False,
        }))
        evid = "ev:camera_catalog:" + _safe_id(raw_id)
        stamp = str(cameras.get("checked_at") or checked)
        age = _age_seconds(stamp)
        evidence.append(Evidence(evid, "camera_catalog", stamp, age, _freshness(age, 900),
            "Official provider catalog reports a camera viewpoint near this place; this is not proof of current imagery."))
        relations.append(Relation(eid, "catalog_near", place_id, (evid,)))

    conditions = observation.get("conditions") if isinstance(observation.get("conditions"), dict) else {}
    air = conditions.get("air_quality") if isinstance(conditions.get("air_quality"), dict) else {}
    if air.get("status") == "ok" and air.get("us_aqi") is not None:
        evid, stamp = "ev:air_quality", str(conditions.get("checked_at") or checked)
        age, value = _age_seconds(stamp), round(float(air["us_aqi"]))
        evidence.append(Evidence(evid, "openmeteo_air", stamp, age, _freshness(age, 1800), f"Modelled US AQI is {value}."))
        facts.append(DerivedFact("fact:air_quality", "provider_value", value, "provider_reported", (evid,), "Direct modelled provider value; not a local sensor."))

    alerts = conditions.get("weather_alerts") if isinstance(conditions.get("weather_alerts"), dict) else {}
    alert_rows = alerts.get("alerts") if isinstance(alerts.get("alerts"), list) else []
    if alerts.get("status") == "ok":
        evid, stamp = "ev:weather_alerts", str(conditions.get("checked_at") or checked)
        age = _age_seconds(stamp)
        evidence.append(Evidence(evid, "nws", stamp, age, _freshness(age, 600), f"Provider returned {len(alert_rows)} active point alert(s)."))
        facts.append(DerivedFact("fact:active_weather_alert_count", "count_provider_rows", len(alert_rows), "high", (evid,), "Counted returned active alert records; zero is not an all-hazards clearance."))

    incidents = observation.get("incidents") if isinstance(observation.get("incidents"), dict) else {}
    incident_rows = incidents.get("events") if isinstance(incidents.get("events"), list) else []
    if incidents.get("status") == "ok":
        evid, stamp = "ev:earthquakes", str(incidents.get("checked_at") or checked)
        age = _age_seconds(stamp)
        evidence.append(Evidence(evid, "usgs", stamp, age, _freshness(age, 900), f"USGS query returned {len(incident_rows)} qualifying regional event(s)."))
        facts.append(DerivedFact("fact:regional_earthquake_count", "count_provider_rows", len(incident_rows), "high", (evid,), "Counted provider events under the existing query boundary."))

    facilities = observation.get("facilities") if isinstance(observation.get("facilities"), dict) else {}
    facility_rows = facilities.get("facilities") if isinstance(facilities.get("facilities"), list) else []
    if facilities.get("status") == "ok":
        evid, stamp = "ev:facilities", str(facilities.get("checked_at") or checked)
        age = _age_seconds(stamp)
        evidence.append(Evidence(evid, "openstreetmap", stamp, age, _freshness(age, 86400), f"Public mapping returned {len(facility_rows)} nearby facility record(s)."))
        facts.append(DerivedFact("fact:nearby_facility_count", "count_provider_rows", len(facility_rows), "provider_reported", (evid,), "Counted community-mapped facility records."))

    states = {
        "cameras": str(cameras.get("status") or "unknown"),
        "air_quality": str(air.get("status") or "unknown"),
        "weather_alerts": str(alerts.get("status") or "unknown"),
        "incidents": str(incidents.get("status") or "unknown"),
        "facilities": str(facilities.get("status") or "unknown"),
    }
    unavailable = sorted(k for k, v in states.items() if v != "ok")
    facts.append(DerivedFact("fact:observation_completeness", "provider_status_matrix",
        "complete_for_integrated_sources" if not unavailable else "partial", "high", tuple(),
        "Integrated provider gaps: " + (", ".join(unavailable) if unavailable else "none") + "."))

    return {
        "schema": "jarvis.reality_graph.v1", "generated_at": _now(), "model_calls": 0,
        "action_authority": "none",
        "scope": {"kind": "place_snapshot", "latitude": round(float(latitude), 6), "longitude": round(float(longitude), 6)},
        "entities": [asdict(x) for x in entities], "relations": [asdict(x) for x in relations],
        "evidence": [asdict(x) for x in evidence], "derived_facts": [asdict(x) for x in facts],
        "provider_states": states,
    }


def build_mission_graph(mission: dict[str, Any], observations: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """Compile a cross-provider mission state without asking an LLM to reason.

    Provider adapters should normalize observations to:
      kind, source, observed_at and typed fields such as status, eta_at,
      latitude/longitude, moving, delay_seconds, disruption, delivered.
    Unknown/missing data remains unknown. No person identity is inferred.
    """
    now = now or datetime.now(timezone.utc)
    mid = _safe_id(mission.get("id") or "mission")
    goal = str(mission.get("goal") or "")[:240]
    deadline = _parse_time(mission.get("deadline"))
    entities = [Entity("mission:" + mid, "mission", goal or "Mission", {
        "status": str(mission.get("status") or "active")[:40],
        "deadline": deadline.isoformat() if deadline else None,
    })]
    evidence: list[Evidence] = []
    relations: list[Relation] = []
    facts: list[DerivedFact] = []
    newest: dict[str, dict[str, Any]] = {}

    ttl_by_kind = {"courier": 180.0, "traffic": 300.0, "camera": 180.0, "order": 300.0, "device": 60.0}
    for idx, row in enumerate(observations[-100:]):
        if not isinstance(row, dict):
            continue
        # A shared source bundle must not let observations explicitly tied to
        # another mission establish this mission's delivery or route outcome.
        linked_mission = row.get("mission_id")
        if linked_mission is not None and str(linked_mission) != str(mission.get("id") or ""):
            continue
        kind = str(row.get("kind") or "observation").lower()
        source = str(row.get("source") or "unknown")[:80]
        stamp = str(row.get("observed_at") or "")
        age = _age_seconds(stamp, now=now)
        fresh = _freshness(age, ttl_by_kind.get(kind, 300.0))
        evid = f"ev:{_safe_id(kind)}:{idx}"
        claim = str(row.get("claim") or f"{kind} observation from {source}")[:300]
        evidence.append(Evidence(evid, source, stamp, age, fresh, claim))
        if fresh == "fresh":
            previous = newest.get(kind)
            prev_time = _parse_time(previous.get("observed_at")) if previous else None
            row_time = _parse_time(stamp)
            if row_time and (prev_time is None or row_time > prev_time):
                newest[kind] = {**row, "_evidence_id": evid}

    order = newest.get("order")
    courier = newest.get("courier")
    traffic = newest.get("traffic")
    camera = newest.get("camera")

    # Create real typed graph edges. A route relation requires an explicit
    # matching route ID; a nearby camera alone cannot establish coverage of
    # this courier, and an unmatched source cannot explain a delay.
    for kind, row in (("order", order), ("courier", courier), ("traffic", traffic), ("camera", camera)):
        if not row:
            continue
        entity_id = f"{kind}:{mid}"
        if kind == "camera":
            entity_id = "camera:" + _safe_id(row.get("id") or row.get("source"))
        entities.append(Entity(entity_id, kind, kind.capitalize() + " observation", {
            "source": str(row.get("source") or "unknown")[:80],
            "observed_at": str(row.get("observed_at") or ""),
            "source_attestation": str(row.get("source_attestation") or "not_verified")[:60],
        }))
        relations.append(Relation(entity_id, "observed_for", "mission:" + mid,
                                  (row["_evidence_id"],)))
        rid = row.get("route_id")
        if kind in {"courier", "traffic", "camera"} and isinstance(rid, str) and rid:
            route_id = "route:" + _safe_id(rid)
            if not any(item.id == route_id for item in entities):
                entities.append(Entity(route_id, "route", "Declared route", {
                    "provider_route_id": rid[:96], "geometry_verified": False,
                }))
            relations.append(Relation(entity_id, "reports_on_route", route_id,
                                      (row["_evidence_id"],)))

    if order:
        status = str(order.get("status") or "unknown")[:60]
        facts.append(DerivedFact("fact:order_status", "fresh_latest_order", status, "provider_reported",
            (order["_evidence_id"],), "Latest fresh order-provider status."))
        if order.get("delivered") is True:
            facts.append(DerivedFact("fact:provider_reports_delivered", "provider_delivery_flag", True, "provider_reported",
                (order["_evidence_id"],), "Provider reports delivered; this does not prove personal receipt."))

    eta = _parse_time(courier.get("eta_at")) if courier else None
    if eta:
        seconds = int((eta - now).total_seconds())
        facts.append(DerivedFact("fact:provider_eta_seconds", "fresh_eta_minus_now", seconds, "provider_reported",
            (courier["_evidence_id"],), "Fresh provider ETA converted to seconds from graph evaluation time."))
        if deadline:
            margin = int((deadline - eta).total_seconds())
            facts.append(DerivedFact("fact:deadline_margin_seconds", "deadline_minus_provider_eta", margin, "high",
                (courier["_evidence_id"],), "Positive means provider ETA precedes the exact mission deadline."))

    if courier and courier.get("moving") is False:
        stopped = courier.get("stationary_seconds")
        if isinstance(stopped, (int, float)) and stopped >= 180:
            facts.append(DerivedFact("fact:courier_stationary", "fresh_motion_threshold", int(stopped), "high",
                (courier["_evidence_id"],), "Courier telemetry reports no movement for at least three minutes."))

    if traffic:
        delay = traffic.get("delay_seconds")
        disruption = str(traffic.get("disruption") or "").strip()
        if isinstance(delay, (int, float)) and delay >= 300:
            facts.append(DerivedFact("fact:route_delay_seconds", "fresh_route_delay_threshold", int(delay), "high",
                (traffic["_evidence_id"],), "Fresh route data reports at least five minutes of excess travel time."))
        if disruption:
            facts.append(DerivedFact("fact:route_disruption", "fresh_provider_disruption", disruption[:160], "provider_reported",
                (traffic["_evidence_id"],), "Fresh traffic provider reports a route disruption."))

    # Camera evidence may corroborate public-area conditions, never identity.
    if camera:
        state = str(camera.get("traffic_state") or camera.get("state") or "").strip().lower()
        if state in {"stopped", "heavy", "congested"}:
            facts.append(DerivedFact("fact:camera_route_congestion", "fresh_public_camera_condition", state, "tentative",
                (camera["_evidence_id"],), "Public camera observation is consistent with congestion; no person/vehicle identity is inferred."))

    fact_map = {f.id: f for f in facts}
    cause_evidence: list[str] = []
    courier_route = str(courier.get("route_id") or "") if courier else ""
    traffic_route = str(traffic.get("route_id") or "") if traffic else ""
    # Require a declared exact route join. Without it, observations are
    # contemporaneous but not proven to describe the same journey.
    same_route = bool(courier_route) and courier_route == traffic_route
    distinct_sources = bool(courier and traffic and courier.get("source") != traffic.get("source"))
    if same_route and distinct_sources and "fact:courier_stationary" in fact_map and ("fact:route_delay_seconds" in fact_map or "fact:route_disruption" in fact_map):
        cause_evidence.extend(fact_map["fact:courier_stationary"].evidence_ids)
        for key in ("fact:route_delay_seconds", "fact:route_disruption"):
            if key in fact_map:
                cause_evidence.extend(fact_map[key].evidence_ids)
        camera_route = str(camera.get("route_id") or "") if camera else ""
        if camera_route == courier_route and "fact:camera_route_congestion" in fact_map:
            cause_evidence.extend(fact_map["fact:camera_route_congestion"].evidence_ids)
        facts.append(DerivedFact("fact:delay_correlation", "stationary_plus_matching_route_disruption", "route_disruption_consistent_with_delay",
            "corroborated", tuple(dict.fromkeys(cause_evidence)),
            "Fresh courier and traffic observations declare the same route and are consistent with a traffic-related delay; this is correlation, not proof of cause or verified provider authenticity."))

    if deadline and now >= deadline and not any(f.id == "fact:provider_reports_delivered" for f in facts):
        facts.append(DerivedFact("fact:deadline_passed_without_delivery_confirmation", "deadline_state_machine", True, "high", tuple(),
            "Mission deadline passed without a fresh provider-delivered flag. This is not proof the item was not received."))

    return {
        "schema": "jarvis.reality_graph.mission.v1", "generated_at": now.isoformat(), "model_calls": 0,
        "action_authority": "none", "mission_id": str(mission.get("id") or ""),
        "entities": [asdict(x) for x in entities], "relations": [asdict(x) for x in relations],
        "evidence": [asdict(x) for x in evidence], "derived_facts": [asdict(x) for x in facts],
        "fresh_observation_kinds": sorted(newest),
    }


def build_fabric_graph(
    node_snapshot: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Live paired-node state plus non-live public-source registry.

    Node capability is descriptive, not authorization. Unconfigured/offline
    nodes and merely registered feeds never become observed live resources.
    """
    if node_snapshot is None or registry is None:
        from jarvis_mrb import reality_mesh
        if node_snapshot is None:
            node_snapshot = reality_mesh.nodes()
        if registry is None:
            registry = reality_mesh.public_sources()
    now = now or datetime.now(timezone.utc)
    entities: list[Entity] = []
    relations: list[Relation] = []
    evidence: list[Evidence] = []
    facts: list[DerivedFact] = []
    online: list[str] = []
    for idx, row in enumerate((node_snapshot.get("nodes") or [])[:10]):
        if not isinstance(row, dict):
            continue
        nid = str(row.get("id") or "")
        if nid not in {"windows", "macbook", "macmini"}:
            continue
        node_id = "device:" + nid
        observed = str(row.get("observed_at") or row.get("checked_at") or "")
        age = _age_seconds(observed, now=now)
        fresh = _freshness(age, 60)
        status = str(row.get("status") or "unknown")
        verified_online = status == "online" and fresh == "fresh"
        evid = f"ev:device:{_safe_id(nid)}:{idx}"
        evidence.append(Evidence(evid, "paired_device_health", observed, age, fresh,
            "Explicit node health status: " + status[:40] +
            "; capability flags do not grant action authority."))
        entities.append(Entity(node_id, "paired_device", str(row.get("label") or nid)[:100], {
            "reported_status": status[:40],
            "fresh_authenticated_health": verified_online and nid != "windows",
            "local_host_health": verified_online and nid == "windows",
            "screen_session_active": row.get("screen_session_active") is True,
        }))
        if verified_online:
            online.append(nid)
        capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
        for name in ("context", "screen", "app_launch", "remote_input", "file_transfer"):
            state = str(capabilities.get(name) or "unknown")[:64]
            cap_id = "capability:" + _safe_id(name)
            if not any(e.id == cap_id for e in entities):
                entities.append(Entity(cap_id, "capability", name.replace("_", " "), {}))
            relations.append(Relation(node_id, "declares_capability", cap_id, (evid,)))
            if verified_online and state in {"read_only", "session_opt_in", "exact_user_tap_only"}:
                facts.append(DerivedFact(f"fact:{nid}:{name}", "fresh_capability_flag",
                    state, "observed_capability_not_authority", (evid,),
                    "Node declares this capability; independent user/host permissions still apply."))

    for idx, row in enumerate((registry.get("sources") or [])[:24]):
        if not isinstance(row, dict):
            continue
        rid = _safe_id(row.get("id") or idx)
        sid = "registered_source:" + rid
        entities.append(Entity(sid, "public_source_registry_entry", str(row.get("label") or rid)[:100], {
            "coverage": str(row.get("coverage") or "unknown")[:160],
            "status": "registered_not_currently_observed",
            "claim_live": False,
        }))
        relations.append(Relation(sid, "may_observe", "place:provider_coverage_not_verified", ()))
    facts.append(DerivedFact("fact:fresh_online_device_ids", "fresh_paired_node_health",
        online, "high", tuple(e.id for e in evidence if e.freshness == "fresh"),
        "Only fresh nodes with explicitly reported online status are listed."))
    return {
        "schema": "jarvis.reality_graph.fabric.v1",
        "generated_at": now.isoformat(), "model_calls": 0,
        "action_authority": "none",
        "entities": [asdict(e) for e in entities],
        "relations": [asdict(r) for r in relations],
        "evidence": [asdict(e) for e in evidence],
        "derived_facts": [asdict(f) for f in facts],
        "registered_public_sources_are_live": False,
    }


def model_context(graph: dict[str, Any], *, max_facts: int = 12, max_evidence: int = 12) -> dict[str, Any]:
    """Bounded facts-first semantic packet for exceptional model reasoning.

    Stale/unsupported facts are excluded, even if the raw graph preserves
    historical evidence for inspection. Always carry trust/freshness metadata.
    """
    fact_limit = max(0, min(max_facts, 30))
    evidence_limit = max(0, min(max_evidence, 30))
    rows = [e for e in graph.get("evidence", []) if isinstance(e, dict)]
    lookup = {str(e.get("id")): e for e in rows if e.get("freshness") == "fresh"}
    candidates = [
        fact for fact in graph.get("derived_facts", [])
        if isinstance(fact, dict) and
        all(str(eid) in lookup for eid in (fact.get("evidence_ids") or ()))
    ]
    facts: list[dict[str, Any]] = []
    required: list[str] = []
    for fact in candidates:
        if len(facts) >= fact_limit:
            break
        refs = list(dict.fromkeys(str(eid) for eid in (fact.get("evidence_ids") or ())))
        if len(set(required).union(refs)) > evidence_limit:
            continue
        facts.append(fact)
        for ref in refs:
            if ref not in required:
                required.append(ref)
    # Preserve all evidence for selected facts before adding the newest fresh
    # unrelated source observations; no references to omitted evidence.
    selected = [lookup[eid] for eid in required]
    for ev in reversed(rows):
        if len(selected) >= evidence_limit:
            break
        if ev.get("freshness") == "fresh" and str(ev.get("id")) not in required:
            selected.append(ev)
            required.append(str(ev.get("id")))
    return {
        "schema": graph.get("schema"), "generated_at": graph.get("generated_at"),
        "scope": graph.get("scope"), "mission_id": graph.get("mission_id"),
        "provider_states": graph.get("provider_states"),
        "source_attestation": graph.get("source_attestation", "not_verified"),
        "facts": facts,
        "evidence": [{
            "id": row.get("id"), "source": row.get("source"),
            "observed_at": row.get("observed_at"),
            "age_seconds": row.get("age_seconds"),
            "freshness": row.get("freshness"), "claim": row.get("claim"),
        } for row in selected],
        "omitted_raw_provider_payloads": True,
        "omitted_stale_or_unlinked_facts": len(graph.get("derived_facts") or []) - len(candidates),
    }


def answer_place_question(graph: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Narrow deterministic Q&A; misses explicitly escalate instead of guessing."""
    q = " ".join(str(question or "").lower().split()).strip(" ?.!")
    facts = {str(r.get("id")): r for r in graph.get("derived_facts", []) if isinstance(r, dict)}
    if q in {"how many nearby public cameras are there", "how many public cameras are nearby", "are there public cameras nearby"}:
        count = sum(1 for r in graph.get("entities", []) if isinstance(r, dict) and r.get("kind") == "public_camera")
        return {"answered_without_model": True, "answer": f"{count} official catalog camera viewpoint(s) are represented nearby. Catalog presence does not prove a current live image.", "evidence_kind": "catalog"}
    fresh_evidence = {str(e.get("id")) for e in graph.get("evidence", []) if isinstance(e, dict) and e.get("freshness") == "fresh"}
    def supported(fact_id: str) -> bool:
        fact = facts.get(fact_id)
        return bool(fact and fact.get("evidence_ids") and all(e in fresh_evidence for e in fact["evidence_ids"]))
    if q in {"what is the air quality", "what's the air quality", "air quality"} and supported("fact:air_quality"):
        return {"answered_without_model": True, "answer": f"Modelled US AQI is {facts['fact:air_quality']['value']}.", "evidence_kind": "provider_value"}
    if q in {"are there weather alerts", "any weather alerts", "weather alerts"} and supported("fact:active_weather_alert_count"):
        n = int(facts["fact:active_weather_alert_count"]["value"])
        return {"answered_without_model": True, "answer": f"The integrated weather provider returned {n} active point alert(s). This is not an all-hazards clearance.", "evidence_kind": "provider_count"}
    if q in {"what do you know about this place", "summarize this place", "reality graph status"}:
        parts = []
        for fact in graph.get("derived_facts", []):
            if not isinstance(fact, dict):
                continue
            ids = fact.get("evidence_ids") or ()
            label = "" if all(e in fresh_evidence for e in ids) else "Historical/stale source (not current): "
            parts.append(label + str(fact.get("explanation") or ""))
        return {"answered_without_model": True, "answer": " ".join(p for p in parts if p)[:1200], "evidence_kind": "derived_facts"}
    return None


def answer_mission_question(graph: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Routine mission questions are answered from facts, not an LLM."""
    q = " ".join(str(question or "").lower().split()).strip(" ?.!")
    facts = {str(r.get("id")): r for r in graph.get("derived_facts", []) if isinstance(r, dict)}
    if q in {"is it late", "will it be late", "will this be late"} and "fact:deadline_margin_seconds" in facts:
        margin = int(facts["fact:deadline_margin_seconds"]["value"])
        if margin >= 0:
            answer = f"Current provider ETA is {margin // 60} minute(s) before the mission deadline."
        else:
            answer = f"Current provider ETA is {abs(margin) // 60} minute(s) after the mission deadline."
        return {"answered_without_model": True, "answer": answer, "evidence_kind": "deadline_math"}
    if q in {"why is it delayed", "why is the delivery delayed", "what is causing the delay"} and "fact:delay_correlation" in facts:
        return {"answered_without_model": True, "answer": "Fresh courier and route evidence are consistent with a traffic-related delay. That is corroboration, not proof of cause.", "evidence_kind": "correlation"}
    if q in {"has it arrived", "was it delivered", "is it delivered"}:
        if "fact:provider_reports_delivered" in facts:
            return {"answered_without_model": True, "answer": "The provider reports the delivery complete. Personal receipt has not been independently proven.", "evidence_kind": "provider_status"}
        return {"answered_without_model": True, "answer": "There is no fresh provider-delivered confirmation in the graph.", "evidence_kind": "absence_of_confirmation"}
    return None
