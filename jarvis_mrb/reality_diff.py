from __future__ import annotations

"""P06-007: evidence-bounded Reality Diff over two retained mission replay points.

Differences are changes in *reported* facts, not proof of physical-world
appearance, disappearance, cause or provider identity. Read-only and model-free.
"""

from datetime import datetime
from typing import Any

from jarvis_mrb import reality_graph_missions as missions

_SCHEMA = "jarvis.reality_diff.mission.v1"
# Only stable, typed semantic facts. Exclude clocks/absence-derived assertions.
_FACTS = {
    "fact:order_status": "reported_order_status",
    "fact:provider_reports_delivered": "reported_delivery_confirmation",
    "fact:deadline_margin_seconds": "reported_eta_deadline_margin",
    "fact:courier_stationary": "reported_courier_stationary",
    "fact:route_delay_seconds": "reported_route_delay",
    "fact:route_disruption": "reported_route_disruption",
    "fact:camera_route_congestion": "reported_camera_route_congestion",
}


def _supported_facts(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = {x.get("id"): x for x in graph.get("evidence", [])
                if isinstance(x, dict) and x.get("freshness") == "fresh"}
    out = {}
    for fact in graph.get("derived_facts", []):
        if not isinstance(fact, dict) or fact.get("id") not in _FACTS:
            continue
        refs = fact.get("evidence_ids")
        # Evidence-free temporal derivations cannot establish a physical change.
        if not isinstance(refs, (list, tuple)) or not refs or not all(x in evidence for x in refs):
            continue
        sources = [evidence[x] for x in refs]
        out[fact["id"]] = {
            "value": fact.get("value"),
            "observations": [
                {"id": e.get("source_observation_id"), "source": e.get("source"),
                 "observed_at": e.get("observed_at"),
                 "source_attestation": "client_supplied_not_provider_verified"}
                for e in sources
            ],
        }
    return out


def diff(mission_id: str, *, before: str, after: str) -> dict[str, Any]:
    """Compare two as-of views of exactly one enrolled mission.

    Rewind enforces opt-in, mission scope, retention and event-time boundaries.
    Missing evidence is unknown; it never means an object disappeared.
    """
    start, end = missions._stamp(before), missions._stamp(after)
    if not start < end or (end - start).total_seconds() > 72 * 3600:
        raise ValueError("Diff requires before < after within 72 hours.")
    left = missions.rewind(mission_id, at=start.isoformat())
    right = missions.rewind(mission_id, at=end.isoformat())
    a = _supported_facts(left["graph"])
    b = _supported_facts(right["graph"])
    changes: list[dict[str, Any]] = []
    for key in sorted(set(a) | set(b)):
        old, new = a.get(key), b.get(key)
        if old and new and old["value"] == new["value"]:
            continue
        changes.append({
            "fact": _FACTS[key],
            "kind": "reported_change" if old and new else
                    ("newly_supported" if new else "no_recent_evidence"),
            "before": old,
            "after": new,
            "physical_change_verified": False,
        })
    return {
        "schema": _SCHEMA, "mission_id": left["mission_id"],
        "before": left["as_of"], "after": right["as_of"],
        "status": "changes_reported" if any(x["kind"] in {"reported_change", "newly_supported"} for x in changes)
                  else ("insufficient_evidence" if not a and not b else "no_supported_change"),
        "changes": changes[:len(_FACTS)],
        "coverage": {"before": left["coverage"], "after": right["coverage"]},
        "source_attestation": "client_supplied_not_provider_verified",
        "action_authority": "none", "model_calls": 0, "persistent": False,
        "limitations": [
            "Compares two event-time replays of a single opted-in retained mission, not continuously monitored reality.",
            "Newly supported means new evidence, not that an object appeared.",
            "Missing or stale evidence means unknown, not disappearance or recovery.",
            "Late-submitted observations can alter event-time history; ingestion-time history is not available.",
            "Client source labels are not independent provider authentication or proof of cause.",
        ],
    }
