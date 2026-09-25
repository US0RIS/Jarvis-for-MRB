from __future__ import annotations

"""Read-only Phase 1 spatiotemporal investigation over retained World Armor receipts.

Existing provider adapters expose only the *selected query region*, not exact
USGS epicentres, alert polygons or the Open-Meteo grid cell. Therefore every
cross-source pair below is a TEMPORAL coincidence inside an investigation's
sampling scope, NEVER proven co-location, common cause or independent truth.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jarvis_mrb.world_armor_phase1 import (
    _PROVIDERS, _clock, _require_enabled, _timestamp, replay,
)

_MAX_HOURS = 72
_MAX_PAIRS = 60
_MAX_RECORDS = 1200
_WINDOW = timedelta(minutes=60)


def _instant(raw: str, field: str) -> datetime:
    normalized = _timestamp(raw)
    if normalized is None:
        raise ValueError(field + " must be an offset-aware ISO timestamp.")
    return datetime.fromisoformat(normalized)


def correlate(
    investigation_id: str, *, start_at: str, end_at: str,
    as_known_at: str | None = None,
    source_ids: list[str] | None = None,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Join typed source observations with known event times, without IO.

    When an event has NO source-observed time (current NWS adapter), it is
    returned in a separate *receipt-time-only* section and cannot participate
    in an event-time pair. This is deliberate; received != occurred.
    """
    _require_enabled()
    instant = _clock(now)
    start = _instant(start_at, "start_at")
    end = _instant(end_at, "end_at")
    if not start < end or end > instant or end - start > timedelta(hours=_MAX_HOURS):
        raise ValueError("Require a past, positive observation window <=72 hours.")
    cutoff = _instant(as_known_at, "as_known_at") if as_known_at is not None else instant
    if cutoff > instant:
        raise ValueError("as_known_at cannot be in the future.")
    if source_ids is None:
        chosen = list(_PROVIDERS)
    elif isinstance(source_ids, list) and source_ids and len(source_ids) <= len(_PROVIDERS):
        if any(not isinstance(x, str) or x not in _PROVIDERS for x in source_ids):
            raise ValueError("Only registered Phase 1 source IDs are allowed.")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("Source IDs must be unique.")
        chosen = sorted(source_ids)
    else:
        raise ValueError("Choose one to three distinct registered source IDs.")
    report = replay(
        investigation_id, as_known_at=cutoff.isoformat(),
        db_path=db_path, now=instant,
    )
    region = report["investigation"]
    # replay already verifies the exact owner-selected investigation/expiry.
    selected = [x for x in report["observations"]
                if x["source"] in chosen][:_MAX_RECORDS]
    timed = [
        x for x in selected
        if x["observed_at"] is not None
        and start <= datetime.fromisoformat(x["observed_at"]) <= end
    ]
    timed.sort(key=lambda x: (x["observed_at"], x["source"], x["id"]))
    receipt_only = [
        x for x in selected
        if x["observed_at"] is None
        and start <= datetime.fromisoformat(x["received_at"]) <= end
    ]
    receipt_only.sort(key=lambda x: (x["received_at"], x["source"], x["id"]))
    # Two different collection lineages are necessary even for a candidate.
    # USGS's reported "within query radius" and a model's query point do
    # not establish the same physical location or even identical footprint.
    candidates: list[dict[str, Any]] = []
    for idx, earlier in enumerate(timed):
        earlier_at = datetime.fromisoformat(earlier["observed_at"])
        for later in timed[idx + 1:]:
            delta = datetime.fromisoformat(later["observed_at"]) - earlier_at
            if delta > _WINDOW:
                break
            if earlier["source"] == later["source"]:
                continue
            # Synthetic fixture data must never corroborate real-adapter data.
            if (earlier.get("adapter_mode") != later.get("adapter_mode")
                    or earlier.get("adapter_mode") not in {"real_adapter", "fixture"}):
                continue
            if earlier["lineage"] == later["lineage"]:
                continue
            candidates.append({
                "kind": "independent_source_temporal_overlap_candidate",
                "first_observation_id": earlier["id"],
                "second_observation_id": later["id"],
                "first_source": earlier["source"],
                "second_source": later["source"],
                "first_source_time": earlier["observed_at"],
                "second_source_time": later["observed_at"],
                "separation_seconds": int(delta.total_seconds()),
                "adapter_mode": earlier["adapter_mode"],
                "spatial_basis": "same_enrolled_query_region_only",
                "physical_colocation_verified": False,
                "causation_verified": False,
                "note": (
                    "Independent publishing lineages reported phenomena in "
                    "the same selected query scope within one hour. "
                    "No verified shared footprint or causal mechanism."
                ),
            })
            if len(candidates) >= _MAX_PAIRS:
                break
        if len(candidates) >= _MAX_PAIRS:
            break
    coverage = {
        source: (report["coverage"].get(source) or {
            "status": "not_checked",
            "scope": "No retained receipt for this source.",
        })
        for source in chosen
    }
    return {
        "schema": "jarvis.world_armor.correlation.v1",
        "investigation_id": investigation_id,
        "as_known_at": cutoff.isoformat(),
        "observation_window": {
            "start": start.isoformat(), "end": end.isoformat(),
        },
        "query_region": {
            "latitude": region["latitude"],
            "longitude": region["longitude"],
            "radius_km": region["radius_km"],
            "geometry_basis": (
                "operator_selected_query_scope_not_verified_event_footprints"
            ),
        },
        "source_ids": chosen,
        "timed_observations": timed,
        "receipt_time_only_observations": receipt_only,
        "candidate_links": candidates,
        "candidate_links_truncated": len(candidates) >= _MAX_PAIRS,
        "source_coverage": coverage,
        "coverage_adequate_to_claim_no_world_events": False,
        "hypotheses_proven": 0,
        "causal_claims": 0,
        "external_requests": 0,
        "external_actions": 0,
        "model_calls": 0,
        "mode": report["mode"],
        "qualifier": (
            "Historical retained source reports, not a live query. "
            "NWS items without source event timestamps are receipt-only. "
            "USGS event epicentres and alert footprints are not available in "
            "the current normalized adapter; no exact spatial join is possible. "
            "Temporal coincidence is not causation or an all-clear."
        ),
    }
