from __future__ import annotations

"""Single-request portable physical-world situational briefing.

Concurrently query bounded provider adapters, preserve partial failures and
source provenance, and never silently interpret missing data as an all-clear.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from jarvis_mrb.physical_conditions import _validate_position


def _safe_call(function: Any, label: str, latitude: float, longitude: float) -> dict[str, Any]:
    try:
        return function(latitude, longitude)
    except Exception as exc:
        return {
            "status": "unavailable", "source_note": (
                label + " failed: " + type(exc).__name__
            ),
            "cameras": [] if label == "camera catalog" else None,
            "facilities": [] if label == "public mapping" else None,
        }


def physical_awareness(latitude: float, longitude: float) -> dict[str, Any]:
    from jarvis_mrb.physical_conditions import physical_conditions
    from jarvis_mrb.public_camera_catalog import discover_public_cameras
    from jarvis_mrb.public_facilities import nearby_mapped_facilities

    _validate_position(latitude, longitude)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            "cameras": pool.submit(_safe_call, discover_public_cameras, "camera catalog", latitude, longitude),
            "conditions": pool.submit(_safe_call, physical_conditions, "environmental data", latitude, longitude),
            "facilities": pool.submit(_safe_call, nearby_mapped_facilities, "public mapping", latitude, longitude),
        }
        results = {key: future.result() for key, future in futures.items()}
    cameras, conditions, facilities = (
        results["cameras"], results["conditions"], results["facilities"]
    )
    parts: list[str] = []
    camera_status = cameras.get("status")
    camera_count = len(cameras.get("cameras") or [])
    if camera_status == "unsupported_region":
        parts.append("No published camera provider integrated in this region")
    elif camera_status == "unavailable":
        parts.append("Public camera discovery unavailable")
    else:
        parts.append(
            f"{camera_count} official highway camera viewpoints within 10 km"
            + ("; provider coverage partial" if camera_status == "partial" else "")
        )

    air = conditions.get("air_quality") or {}
    if air.get("status") == "ok" and air.get("us_aqi") is not None:
        parts.append(f"modelled US AQI {round(float(air['us_aqi']))}")
    elif air.get("status") == "stale":
        parts.append("air model output is stale")
    else:
        parts.append("air quality unavailable")
    warning = conditions.get("weather_alerts") or {}
    if warning.get("status") == "ok":
        alerts = list(warning.get("alerts") or [])
        if alerts:
            parts.append(
                f"{len(alerts)} active NWS point alerts: "
                + ", ".join(str(a.get("event") or "warning")[:60] for a in alerts[:2])
            )
        else:
            parts.append("no active NWS point alerts returned, not an all-hazards clearance")
    elif warning.get("status") == "unsupported_region":
        parts.append("official weather alerts not integrated for this region")
    else:
        parts.append("official weather alerts unavailable")

    facility_status = facilities.get("status")
    if facility_status == "ok":
        listed = facilities.get("facilities") or []
        parts.append(f"{len(listed)} nearby community-mapped public facilities")
    elif facility_status == "rate_limited":
        parts.append("public mapping temporarily rate-limited")
    else:
        parts.append("public mapping unavailable")

    statuses = [
        camera_status,
        air.get("status"),
        warning.get("status"),
        facility_status,
    ]
    status = "partial" if any(value != "ok" for value in statuses) else "ok"
    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": "; ".join(parts) + ".",
        "cameras": cameras,
        "conditions": conditions,
        "facilities": facilities,
        "location_note": (
            "One opt-in location snapshot shared with relevant official/public "
            "providers. This does not observe through walls, establish personal "
            "safety, check all hazards, or verify camera capture time."
        ),
    }
