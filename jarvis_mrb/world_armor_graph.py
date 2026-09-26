from __future__ import annotations

"""Read-only combined World Armor evidence graph.

Public camera receipt times do not become physical event/capture times. The
graph can show evidence proximity and apparent changes without fabricating
causation, independent confirmations or verified camera viewing polygons.
"""

from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from typing import Any

from jarvis_mrb.world_armor_phase1 import replay, _clock, _timestamp, _require_enabled
from jarvis_mrb.world_armor_platform import (
    _dbpath, _enabled, _instant, list_sources, observations,
)


def _distance(a: float, b: float, c: float, d: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    x = sin(radians(c-a)/2)**2 + (
        cos(radians(a)) * cos(radians(c))
        * sin(radians(d-b)/2)**2
    )
    return 6371.0088 * 2 * asin(min(1, sqrt(max(0, x))))


def combined_evidence(investigation_id: str, *,
                      world_db_path: Path | None = None,
                      platform_db_path: Path | None = None,
                      after_seq: int = 0,
                      page_size: int = 100,
                      now: datetime | None = None) -> dict[str, Any]:
    """One region's environmental receipts plus source-qualified camera timeline."""
    _require_enabled()
    at = _clock(now)
    report = replay(investigation_id, db_path=world_db_path, now=at)
    region = report["investigation"]
    sources = list_sources(db_path=platform_db_path, offset=0, page_size=200)
    # No falsely broad geographic coverage: a camera whose reported location
    # is unknown is returned separately, and selection is operator-attested.
    eligible: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for entry in sources["sources"]:
        if entry["latitude"] is None or entry["longitude"] is None:
            unknown.append(entry["id"])
            continue
        if _distance(region["latitude"], region["longitude"],
                     entry["latitude"], entry["longitude"]) <= region["radius_km"]:
            eligible[entry["id"]] = entry
    # Pagination is over globally ordered evidence; the next cursor is
    # supplied even when this particular page contains no regional cameras.
    events = observations(
        db_path=platform_db_path, after_seq=after_seq, page_size=page_size,
    )
    selected = [
        e for e in events["observations"] if e["source_id"] in eligible
    ]
    source_time = report["observations"]
    return {
        "schema": "world_armor.combined_evidence.v1",
        "investigation_id": region["id"],
        "region": {
            "latitude": region["latitude"], "longitude": region["longitude"],
            "radius_km": region["radius_km"],
        },
        "environmental_observations": source_time,
        "environmental_coverage": report["coverage"],
        "camera_observations": selected,
        "nearby_camera_sources": list(eligible.values()),
        "enrolled_camera_location_unknown_source_ids": unknown,
        "next_camera_after_seq": events["next_after_seq"],
        "source_catalog_next_offset": sources["next_offset"],
        "temporal_join": "co_display_only_camera_capture_times_unverified",
        "camera_observation_time": "Jarvis_receipt_not_publisher_capture",
        "source_independent_confirmation": False,
        "viewing_footprints_verified": False,
        "causal_conclusions": False,
        "source_status": "per_source_not_all_clear",
        "model_calls": 0,
    }


def timeline(*, source_ids: list[str] | None = None,
             after_seq: int = 0, page_size: int = 100,
             db_path: Path | None = None) -> dict[str, Any]:
    """Cross-location navigable camera receipt timeline; no blind inference."""
    if source_ids is not None:
        if type(source_ids) is not list or not all(
            type(x) is str and len(x) == 32 for x in source_ids
        ):
            raise ValueError("Source IDs must be exact enrolled identifiers.")
    page = observations(db_path=db_path, after_seq=after_seq,
                        page_size=page_size)
    source_set = set(source_ids) if source_ids is not None else None
    return {
        "schema": "world_armor.camera_timeline.v1",
        "observations": [o for o in page["observations"]
                         if source_set is None or o["source_id"] in source_set],
        "next_after_seq": page["next_after_seq"],
        "time_axis": "local_receipt_only",
        "all_sources_geolocated": False,
        "automatic_identity_tracking": False,
    }
