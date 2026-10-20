from __future__ import annotations

"""P06-005: bounded, read-only what-if forks of a Reality Graph mission.

This is arithmetic on a fresh *reported* ETA, not a forecast, optimizer,
provider integration or permission to act. Original graph facts are immutable.
"""

import re
from datetime import datetime, timezone
from typing import Any

_SCHEMA = "jarvis.shadow_reality.eta.v1"
_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
_LIMITATIONS = [
    "Every branch is conditional on a caller-supplied ETA shift, not a prediction.",
    "Source labels and reported ETAs are not independent provider authentication.",
    "No route modelling, interventions, device commands, persistence or outcome verification.",
]


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _state(seconds: int) -> str:
    if seconds > 0:
        return "reported_eta_before_deadline"
    if seconds < 0:
        return "reported_eta_after_deadline"
    return "reported_eta_at_deadline"


def _branches(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not 1 <= len(values) <= 6:
        raise ValueError("Supply between one and six what-if branches.")
    seen: set[str] = set()
    normalized = []
    for raw in values:
        if not isinstance(raw, dict) or set(raw) != {"id", "eta_shift_minutes"}:
            raise ValueError("Each branch requires only id and eta_shift_minutes.")
        ident = raw["id"]
        minutes = raw["eta_shift_minutes"]
        if not isinstance(ident, str) or not _IDENT.fullmatch(ident) or ident in seen:
            raise ValueError("Branch ids must be distinct, bounded identifiers.")
        if type(minutes) is not int or not -120 <= minutes <= 120:
            raise ValueError("ETA shift must be a whole number from -120 to 120 minutes.")
        normalized.append({"id": ident, "eta_shift_minutes": minutes})
        seen.add(ident)
    return normalized


def _baseline(graph: dict[str, Any], now: datetime) -> tuple[int | None, dict[str, Any], str]:
    entities = graph.get("entities") or []
    mission = next((r for r in entities if isinstance(r, dict) and r.get("kind") == "mission"), {})
    attrs = mission.get("attributes") if isinstance(mission.get("attributes"), dict) else {}
    deadline = _time(attrs.get("deadline"))
    if attrs.get("status") != "active":
        return None, {}, "Mission is not active."
    if deadline is None or deadline <= now:
        return None, {}, "Mission has no future offset-aware deadline."
    generated = _time(graph.get("generated_at"))
    if generated is None or not -30 <= (now - generated).total_seconds() <= 60:
        return None, {}, "Reality Graph snapshot is missing, future-dated or old."
    facts = {row.get("id"): row for row in graph.get("derived_facts", []) if isinstance(row, dict)}
    if "fact:provider_reports_delivered" in facts:
        return None, {}, "Provider already reports delivered; arrival what-ifs are not applicable."
    margin = facts.get("fact:deadline_margin_seconds", {})
    seconds = margin.get("value")
    if type(seconds) is not int:
        return None, {}, "No fresh provider ETA tied to the mission deadline."
    ids = margin.get("evidence_ids")
    if not isinstance(ids, (list, tuple)) or len(ids) != 1:
        return None, {}, "Deadline margin lacks a single traceable ETA observation."
    evidence = next((x for x in graph.get("evidence", [])
                     if isinstance(x, dict) and x.get("id") == ids[0]), None)
    if not evidence or evidence.get("freshness") != "fresh":
        return None, {}, "Referenced ETA observation is unavailable or stale."
    observed = _time(evidence.get("observed_at"))
    if observed is None or not -30 <= (now - observed).total_seconds() <= 180:
        return None, {}, "Referenced ETA observation has expired or invalid time."
    provenance = {"evidence_id": ids[0], "source": evidence.get("source"),
                  "observed_at": observed.isoformat(),
                  "source_attestation": graph.get("source_attestation", "not_verified")}
    return seconds, provenance, ""


def simulate_eta_branches(
    graph: dict[str, Any], branches: list[dict[str, Any]], *, now: datetime | None = None,
) -> dict[str, Any]:
    """Fork a recent mission graph into isolated conditional ETA-margin scenarios.

    No mutation of the graph, network access, DB read/write or tool invocation.
    Unavailable evidence produces an explicit unknown result in every branch.
    """
    if not isinstance(graph, dict) or graph.get("schema") != "jarvis.reality_graph.mission.v1":
        raise ValueError("A reduced Reality Graph mission snapshot is required.")
    if graph.get("action_authority") != "none" or graph.get("model_calls") != 0:
        raise ValueError("Only model-free, non-actuating Reality Graph snapshots are accepted.")
    variants = _branches(branches)
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Evaluation requires timezone-aware time.")
    now = now.astimezone(timezone.utc)
    seconds, provenance, reason = _baseline(graph, now)
    results: list[dict[str, Any]] = []
    for variant in variants:
        shift = variant["eta_shift_minutes"]
        margin = seconds - 60 * shift if seconds is not None else None
        results.append({**variant, "status": "hypothetical" if margin is not None else "not_evaluated",
                        "deadline_margin_seconds": margin,
                        "conditional_assessment": _state(margin) if margin is not None else "unknown",
                        "assumption": f"Reported ETA shifts by {shift:+d} minutes; all other inputs held fixed.",
                        "prediction": False})
    return {"schema": _SCHEMA, "mission_id": graph.get("mission_id"),
            "evaluated_at": now.isoformat(), "status": "hypothetical" if seconds is not None else "insufficient_evidence",
            "action_authority": "none", "model_calls": 0, "persistent": False,
            "baseline": {"deadline_margin_seconds": seconds,
                         "reported_assessment": _state(seconds) if seconds is not None else "unknown",
                         "evidence": provenance, "unavailable_reason": reason or None},
            "branches": results, "limitations": list(_LIMITATIONS)}
