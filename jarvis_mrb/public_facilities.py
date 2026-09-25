from __future__ import annotations

"""On-demand discoverability of mapped public facilities around the phone.

OpenStreetMap data can be missing or stale. This is a convenience finder,
NEVER an emergency response or a guarantee that a facility is accessible.
"""

from datetime import datetime, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
import json
from threading import Lock
from time import monotonic
from typing import Any

import httpx

OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_ATTRIBUTION = "https://www.openstreetmap.org/copyright"
API_DOCS = "https://wiki.openstreetmap.org/wiki/Overpass_API"
MAX_BODY = 650_000
_lock = Lock()
_next_request = 0.0
# Single-user local deployment. Only one live request per 15 seconds to
# protect the shared public API; no location or result cache.
_ALLOWED = {
    "defibrillator": "defibrillator",
    "drinking_water": "drinking water",
    "toilets": "public toilets",
}


def _validate(latitude: float, longitude: float, radius_m: int, limit: int) -> None:
    if not (isfinite(latitude) and isfinite(longitude)):
        raise ValueError("Coordinates must be finite.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid coordinates.")
    if radius_m < 100 or radius_m > 2000:
        raise ValueError("Search radius must be 100–2000 m.")
    if limit < 1 or limit > 30:
        raise ValueError("Result limit must be 1–30.")


def _query(latitude: float, longitude: float, radius_m: int) -> str:
    # Validated floats/integers only; no user-controlled Overpass QL.
    center = f"(around:{radius_m},{latitude:.6f},{longitude:.6f})"
    branches = (
        f'node["emergency"="defibrillator"]{center};'
        f'way["emergency"="defibrillator"]{center};'
        f'node["amenity"="drinking_water"]{center};'
        f'way["amenity"="drinking_water"]{center};'
        f'node["amenity"="toilets"]{center};'
        f'way["amenity"="toilets"]{center};'
    )
    return f"[out:json][timeout:10];({branches});out center 90;"


def _distance(latitude: float, longitude: float, other_lat: float, other_lon: float) -> float:
    dy = radians(other_lat - latitude)
    dx = radians(other_lon - longitude)
    a = sin(dy / 2) ** 2 + cos(radians(latitude)) * cos(radians(other_lat)) * sin(dx / 2) ** 2
    return 6371008.8 * 2 * asin(min(1.0, sqrt(a)))


def _parse(data: Any, latitude: float, longitude: float, radius_m: int, limit: int) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise ValueError("OpenStreetMap provider response has unexpected shape.")
    entries: list[dict[str, Any]] = []
    for item in data["elements"]:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        kind = str(tags.get("emergency") or tags.get("amenity") or "")
        if kind not in _ALLOWED:
            continue
        center = item.get("center") or item
        try:
            p_lat, p_lon = float(center["lat"]), float(center["lon"])
            if not (isfinite(p_lat) and isfinite(p_lon)):
                continue
        except (TypeError, ValueError, KeyError):
            continue
        distance = _distance(latitude, longitude, p_lat, p_lon)
        if distance > radius_m + 20:
            continue
        osm_type = str(item.get("type") or "")
        osm_id = item.get("id")
        if osm_type not in {"node", "way"}:
            continue
        try:
            ident = int(osm_id)
        except (ValueError, TypeError):
            continue
        if ident < 1:
            continue
        name = str(tags.get("name") or _ALLOWED[kind])[:140]
        entries.append({
            "id": f"osm-{osm_type}-{ident}",
            "title": name,
            "kind": kind,
            "category": _ALLOWED[kind],
            "distance_m": int(round(distance)),
            "latitude": p_lat,
            "longitude": p_lon,
            "access": str(tags.get("access") or "unknown")[:70],
            "opening_hours": str(tags.get("opening_hours") or "unknown")[:150],
            "source_url": f"https://www.openstreetmap.org/{osm_type}/{ident}",
        })
    entries.sort(key=lambda e: (e["distance_m"], e["id"]))
    return entries[:limit]


def nearby_mapped_facilities(
    latitude: float,
    longitude: float,
    *,
    radius_m: int = 1500,
    limit: int = 18,
) -> dict[str, Any]:
    _validate(latitude, longitude, radius_m, limit)
    global _next_request
    # Fail closed rather than hammer Overpass under concurrency.
    with _lock:
        now = monotonic()
        if now < _next_request:
            return {
                "status": "rate_limited", "facilities": [],
                "source_url": API_DOCS,
                "source_note": "Shared public mapping service was queried recently. Retry shortly.",
                "coordinates_stored": False,
            }
        _next_request = now + 15.0
    try:
        with httpx.Client(timeout=httpx.Timeout(14), follow_redirects=False) as client:
            with client.stream(
                "POST", OVERPASS, data={"data": _query(latitude, longitude, radius_m)},
                headers={"User-Agent": "JarvisForMRB/0.13 (+https://github.com/US0RIS/Jarvis-for-MRB)"},
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        raise ValueError("Facility catalog exceeds response size limit.")
        facilities = _parse(json.loads(body), latitude, longitude, radius_m, limit)
        return {
            "status": "ok", "facilities": facilities,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source_url": API_DOCS,
            "attribution_url": OSM_ATTRIBUTION,
            "source_note": (
                "© OpenStreetMap contributors. Community-mapped facilities may be "
                "missing, relocated, restricted, out of service or closed. "
                "Opening hours and access are unverified unless stated. "
                "Do not rely on these results for emergency medical response."
            ),
            "coordinates_stored": False,
        }
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {
            "status": "unavailable", "facilities": [],
            "source_url": API_DOCS,
            "source_note": "Public mapping provider unavailable: " + type(exc).__name__,
            "coordinates_stored": False,
        }
