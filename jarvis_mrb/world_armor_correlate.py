from __future__ import annotations

"""Read-only Phase 1 spatiotemporal investigation over retained World Armor receipts.

The USGS adapter may preserve a validated publisher epicenter, while NWS
alert footprints and the Open-Meteo model-grid geometry are not retained.
Cross-source pairs are therefore bounded temporal/spatial candidates, NEVER
proof of exact co-location, common cause or independent truth.
"""

from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
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


def _km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    rlat = math.radians(lat_b - lat_a)
    rlon = math.radians(lon_b - lon_a)
    value = (math.sin(rlat / 2) ** 2
             + math.cos(math.radians(lat_a)) * math.cos(math.radians(lat_b))
             * math.sin(rlon / 2) ** 2)
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, value))))


def correlate(
    investigation_id: str, *, start_at: str, end_at: str,
    as_known_at: str | None = None,
    source_ids: list[str] | None = None,
    query_radius_km: float | None = None,
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
    explicit_cutoff = as_known_at is not None
    requested_cutoff = (
        _instant(as_known_at, "as_known_at") if explicit_cutoff else instant
    )
    if requested_cutoff > instant:
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
        investigation_id, as_known_at=requested_cutoff.isoformat(),
        db_path=db_path, now=instant,
    )
    if explicit_cutoff:
        cutoff=requested_cutoff
    else:
        moments=report.get("sample_timeline") or []
        cutoff=(
            max(datetime.fromisoformat(x["received_at"]) for x in moments)
            if moments else end
        )
    region = report["investigation"]
    # The operator can narrow (never expand) the enrollment's radius. The
    # center itself is immutable; no arbitrary target/location may be joined.
    if query_radius_km is None:
        radius = region["radius_km"]
    else:
        if (type(query_radius_km) not in (int, float)
                or not math.isfinite(query_radius_km)
                or not 1 <= query_radius_km <= region["radius_km"]):
            raise ValueError("Query radius must be finite and within the enrolled region.")
        radius = round(float(query_radius_km), 2)
    selected = [x for x in report["observations"]
                if x["source"] in chosen][:_MAX_RECORDS]
    spatial_indeterminate: list[dict[str, Any]] = []
    spatially_eligible: list[dict[str, Any]] = []
    for obs in selected:
        if obs["source"] != "usgs_earthquakes":
            # NWS status is for a point; AQI is a coarse model at that
            # selected point. Neither asserts full-radius coverage.
            spatially_eligible.append(obs)
            continue
        values = obs.get("values") or {}
        lat, lon = values.get("latitude"), values.get("longitude")
        if (type(lat) in (int, float) and type(lon) in (int, float)
                and math.isfinite(lat) and math.isfinite(lon)
                and -90 <= lat <= 90 and -180 <= lon <= 180):
            if _km(region["latitude"], region["longitude"], lat, lon) <= radius:
                spatially_eligible.append(obs)
        elif radius == region["radius_km"]:
            # Historical USGS reports returned by the bounded adapter are
            # known to have been listed for its query radius, but do not
            # acquire invented epicenter coordinates.
            spatially_eligible.append(obs)
        else:
            spatial_indeterminate.append(obs)
    spatial_indeterminate = [
        x for x in spatial_indeterminate
        if x["observed_at"] is not None
        and start <= datetime.fromisoformat(x["observed_at"]) <= end
    ]
    timed = [
        x for x in spatially_eligible
        if x["observed_at"] is not None
        and start <= datetime.fromisoformat(x["observed_at"]) <= end
    ]
    timed.sort(key=lambda x: (x["observed_at"], x["source"], x["id"]))
    degraded = [
        x for x in timed
        if x.get("sample_coverage_status") != "ok"
    ]
    receipt_only = [
        x for x in spatially_eligible
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
            # Correlation requires the producing sample itself to have healthy
            # source coverage. Stale/unavailable evidence remains visible but
            # cannot corroborate another source.
            if (earlier.get("sample_coverage_status") != "ok"
                    or later.get("sample_coverage_status") != "ok"):
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
                "spatial_basis": (
                    "publisher_epicenter_within_selected_query_radius; "
                    "model_at_query_point_is_coarse"
                    if any(x["source"] == "usgs_earthquakes"
                           and x.get("geometry_basis") == "usgs_primary_reported_epicenter"
                           for x in (earlier, later))
                    else "same_enrolled_query_region_only"
                ),
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
    query_plan = {
        "version": 1,
        "investigation_id": investigation_id,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "as_known_at": cutoff.isoformat(),
        "source_ids": chosen,
        "query_radius_km": radius,
        "pair_window_seconds": int(_WINDOW.total_seconds()),
    }
    query_id = "query:" + sha256(
        json.dumps(query_plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]

    return {
        "schema": "jarvis.world_armor.correlation.v1",
        "investigation_id": investigation_id,
        "query_id": query_id,
        "query_plan": query_plan,
        "as_known_at": cutoff.isoformat(),
        "observation_window": {
            "start": start.isoformat(), "end": end.isoformat(),
        },
        "query_region": {
            "latitude": region["latitude"],
            "longitude": region["longitude"],
            "enrolled_radius_km": region["radius_km"],
            "radius_km": radius,
            "geometry_basis": (
                "operator_selected_query_scope_not_verified_event_footprints"
            ),
        },
        "source_ids": chosen,
        "timed_observations": timed,
        "degraded_observations": degraded,
        "receipt_time_only_observations": receipt_only,
        "spatially_indeterminate_observations": spatial_indeterminate[:60],
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
            "USGS epicenters, where reported and valid, may filter the "
            "selected radius; missing coordinates remain unknown for a "
            "narrower radius. NWS alert footprints and model-grid geometry "
            "are not available; no exact event-to-event spatial join. "
            "Temporal coincidence is not causation or an all-clear."
        ),
    }
