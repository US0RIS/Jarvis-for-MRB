from __future__ import annotations

"""Two-region, read-only comparison of previously enrolled World Armor evidence.

Only data with matching semantics and valid producing-sample coverage is
compared. Same USGS event ID = one source report returned by two queries,
NOT two independent confirmations. Model AQI is never a ground sensor.
"""

from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any
from datetime import datetime

from jarvis_mrb.world_armor_correlate import correlate, _km
from jarvis_mrb.world_armor_phase1 import _clock, _require_enabled, _identifier

_MAX_COMPARABLE = 50


def _eligible(observation: dict[str, Any], mode: str) -> bool:
    return (observation.get("sample_coverage_status") == "ok"
            and observation.get("adapter_mode") == mode
            and mode in {"fixture", "real_adapter"})


def _aqi_items(
    report: dict[str, Any], mode: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report["timed_observations"]:
        if (item.get("source") != "openmeteo_model"
                or item.get("kind") != "modelled_us_aqi"
                or not _eligible(item, mode)):
            continue
        value = (item.get("values") or {}).get("us_aqi")
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not 0 <= value <= 500):
            continue
        # Same model period, not approximately equal receipt time. Every
        # period is source-reported and never synthesized by Jarvis.
        at = item["observed_at"]
        if at is not None:
            prior = result.get(at)
            if prior is None or (item["received_at"], item["id"]) > (
                    prior["received_at"], prior["id"]):
                result[at] = item
    return result


def _earthquake_items(
    report: dict[str, Any], mode: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report["timed_observations"]:
        if (item.get("source") != "usgs_earthquakes"
                or item.get("kind") != "reported_earthquake"
                or not _eligible(item, mode)):
            continue
        key = item.get("provider_key")
        if not isinstance(key, str) or not key:
            continue
        prior = result.get(key)
        if prior is None or (item["received_at"], item["id"]) > (
                prior["received_at"], prior["id"]):
            result[key] = item
    return result


def compare_regions(
    primary_id: str, secondary_id: str, *,
    start_at: str, end_at: str,
    as_known_at: str | None = None,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare two *different* explicitly enrolled regions; no provider IO.

    A shared USGS ID is one underlying agency report across both query
    footprints. Identically time-stamped, modelled AQI measures a
    location-to-location difference *within the same model and unit*.
    """
    _require_enabled()
    primary_id, secondary_id = _identifier(primary_id), _identifier(secondary_id)
    if primary_id == secondary_id:
        raise ValueError("Select two different, actively enrolled investigations.")
    instant = _clock(now)
    args = dict(start_at=start_at, end_at=end_at, as_known_at=as_known_at,
                db_path=db_path, now=instant)
    first = correlate(primary_id, **args)
    second = correlate(secondary_id, **args)
    region_a, region_b = first["query_region"], second["query_region"]
    distance = _km(region_a["latitude"], region_a["longitude"],
                   region_b["latitude"], region_b["longitude"])
    overlap = distance <= region_a["radius_km"] + region_b["radius_km"]
    # The shared query has a deterministic identity even without an explicit
    # cutoff: both component query IDs depend on retained receipts rather
    # than a fresh wall-clock timestamp.
    query_plan = {
        "version": 1,
        "operation": "compare_two_enrolled_regions",
        "primary_query_id": first["query_id"],
        "secondary_query_id": second["query_id"],
        "source_time_window": first["observation_window"],
        "primary_id": primary_id,
        "secondary_id": secondary_id,
    }
    query_id = "regions:" + sha256(json.dumps(
        query_plan, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()[:20]
    source_status = {
        source: {
            "primary": first["source_coverage"][source].get("status", "unknown"),
            "secondary": second["source_coverage"][source].get("status", "unknown"),
            "primary_scope": first["source_coverage"][source].get("scope", ""),
            "secondary_scope": second["source_coverage"][source].get("scope", ""),
        }
        for source in first["source_ids"]
    }
    # A fixture in one region must NEVER corroborate live-adapter data from
    # the other. Mixed/empty histories are displayed but never compared.
    compatible_mode = (
        first["mode"] == second["mode"]
        and first["mode"] in {"fixture_only", "real_adapter_only"}
    )
    mode = ("fixture" if first["mode"] == "fixture_only"
            else "real_adapter" if first["mode"] == "real_adapter_only"
            else "uncomparable")
    comparisons: list[dict[str, Any]] = []
    shared: list[dict[str, Any]] = []
    if compatible_mode:
        air_a = _aqi_items(first, mode)
        air_b = _aqi_items(second, mode)
        for at in sorted(air_a.keys() & air_b.keys(), reverse=True)[:_MAX_COMPARABLE]:
            a, b = air_a[at], air_b[at]
            # Same provider lineage, same modelled unit and period. It is
            # not a second independent physical sensor reading.
            if (a["lineage"] != b["lineage"]
                    or a["values"].get("unit") != b["values"].get("unit")):
                continue
            comparisons.append({
                "kind": "same_model_same_period_location_contrast",
                "model_time": at,
                "primary_observation_id": a["id"],
                "secondary_observation_id": b["id"],
                "primary_modelled_us_aqi": a["values"]["us_aqi"],
                "secondary_modelled_us_aqi": b["values"]["us_aqi"],
                "difference_secondary_minus_primary": round(
                    b["values"]["us_aqi"]-a["values"]["us_aqi"], 1
                ),
                "model_lineage": a["lineage"],
                "adapter_mode": mode,
                "independent_measurements": False,
                "qualifier": "Same model and period; not ground sensors, a trend, or causal evidence.",
            })
        quake_a = _earthquake_items(first, mode)
        quake_b = _earthquake_items(second, mode)
        for key in sorted(quake_a.keys() & quake_b.keys())[:_MAX_COMPARABLE]:
            a, b = quake_a[key], quake_b[key]
            if a["lineage"] != b["lineage"]:
                continue
            shared.append({
                "kind": "same_primary_source_event_reported_in_two_regions",
                "source": "usgs_earthquakes", "provider_key": key,
                "primary_observation_id": a["id"],
                "secondary_observation_id": b["id"],
                "primary_source_time": a["observed_at"],
                "secondary_source_time": b["observed_at"],
                "primary_magnitude": a["values"].get("magnitude"),
                "secondary_magnitude": b["values"].get("magnitude"),
                "revision_or_receipt_disagreement": (
                    a["values"].get("magnitude") != b["values"].get("magnitude")
                    or a["observed_at"] != b["observed_at"]
                ),
                "independent_confirmations": 1,
                "qualifier": (
                    "One USGS source event appeared in two bounded query "
                    "results, not two earthquakes or independent confirmations."
                ),
            })
    return {
        "schema": "jarvis.world_armor.cross_region.v1",
        "query_id": query_id, "query_plan": query_plan,
        "primary": {
            "investigation_id": primary_id,
            "query_id": first["query_id"], "region": region_a,
            "as_known_at": first["as_known_at"],
            "mode": first["mode"],
            "timed_observation_count": len(first["timed_observations"]),
            "receipt_only_count": len(first["receipt_time_only_observations"]),
            "spatially_indeterminate_count": len(
                first["spatially_indeterminate_observations"]),
            "degraded_observation_count": len(first["degraded_observations"]),
        },
        "secondary": {
            "investigation_id": secondary_id,
            "query_id": second["query_id"], "region": region_b,
            "as_known_at": second["as_known_at"],
            "mode": second["mode"],
            "timed_observation_count": len(second["timed_observations"]),
            "receipt_only_count": len(second["receipt_time_only_observations"]),
            "spatially_indeterminate_count": len(
                second["spatially_indeterminate_observations"]),
            "degraded_observation_count": len(second["degraded_observations"]),
        },
        "source_coverage": source_status,
        "center_separation_km": round(distance, 2),
        "enrolled_regions_overlap_geometrically": overlap,
        "modelled_aqi_comparisons": comparisons,
        "shared_usgs_source_events": shared,
        "comparison_eligible": compatible_mode,
        "comparison_block_reason": (
            None if compatible_mode else
            "Regions need separately retained same-mode observations. "
            "Fixture and real-adapter evidence cannot be compared or corroborated."
        ),
        "absence_is_not_an_all_clear": True,
        "physical_colocation_verified": False,
        "cross_region_causation_claims": 0,
        "independent_corroboration_from_shared_event": 0,
        "external_requests": 0, "external_actions": 0, "model_calls": 0,
        "qualifier": (
            "Historical retained reports in two separately enrolled regions. "
            "Different provider outages, model grids, unsynchronized model "
            "periods and partial queries prevent an all-clear. A shared "
            "USGS ID is one source record, not multiple independent events. "
            "Neither region's evidence establishes a cause in the other."
        ),
    }
