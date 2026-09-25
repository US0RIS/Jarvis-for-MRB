from __future__ import annotations

"""Opt-in discovery of officially published public traffic cameras.

This module does not scan an IP range, enumerate local network devices,
authenticate to cameras, proxy footage, or claim the camera view is fresh.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx

_CALTRANS_CATALOG = "https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm"
_VICTRAFFIC = "https://traffic.transport.vic.gov.au/"
_CATALOG_TTL_SECONDS = 900.0
_MAX_FEED_BYTES = 5_000_000
_cache_lock = Lock()
_cache: dict[int, tuple[float, list[dict[str, Any]], str]] = {}


def _source_url(district: int) -> str:
    if district not in range(1, 13):
        raise ValueError("Unknown Caltrans district")
    return f"https://cwwp2.dot.ca.gov/data/d{district}/cctv/cctvStatusD{district:02d}.json"


def _public_media_url(raw: object) -> str:
    """Allow vendor-published HTTPS images/streams only on government hosts."""
    value = str(raw or "").strip()
    if len(value) > 1500:
        return ""
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname:
        return ""
    host = parts.hostname.lower()
    if host not in {"cwwp2.dot.ca.gov", "wzmedia.dot.ca.gov"}:
        return ""
    if parts.username or parts.password or parts.port not in (None, 443):
        return ""
    return value


def _parse_caltrans(data: Any, district: int) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Unexpected Caltrans CCTV catalog structure")
    result: list[dict[str, Any]] = []
    for wrapper in data["data"]:
        if not isinstance(wrapper, dict):
            continue
        record = wrapper.get("cctv")
        if not isinstance(record, dict):
            continue
        if str(record.get("inService") or "").lower() != "true":
            continue
        location = record.get("location") or {}
        image = record.get("imageData") or {}
        if not isinstance(location, dict) or not isinstance(image, dict):
            continue
        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        static = image.get("static") or {}
        if not isinstance(static, dict):
            static = {}
        image_url = _public_media_url(static.get("currentImageURL"))
        stream_url = _public_media_url(image.get("streamingVideoURL"))
        if not (image_url or stream_url):
            continue
        result.append(
            {
                "id": f"caltrans-d{district}-{str(record.get('index') or '')[:30]}",
                "title": str(location.get("locationName") or "Traffic camera")[:140],
                "nearby_place": str(location.get("nearbyPlace") or "")[:90],
                "latitude": latitude,
                "longitude": longitude,
                "direction": str(location.get("direction") or "")[:32],
                "in_service_reported": True,
                "image_url": image_url,
                "stream_url": stream_url,
                "provider": "Caltrans CWWP2",
                "provider_catalog": _CALTRANS_CATALOG,
            }
        )
    return result


def _get_district(district: int) -> tuple[list[dict[str, Any]], str]:
    now = monotonic()
    with _cache_lock:
        cached = _cache.get(district)
        if cached and now - cached[0] < _CATALOG_TTL_SECONDS:
            return cached[1], cached[2]
    url = _source_url(district)
    try:
        with httpx.Client(timeout=httpx.Timeout(7.0), follow_redirects=False) as client:
            with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                if response.is_redirect:
                    raise ValueError("Public catalog redirected")
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > _MAX_FEED_BYTES:
                        raise ValueError("Public catalog exceeds maximum size")
            data = __import__("json").loads(payload)
        entries = _parse_caltrans(data, district)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        # A transient provider failure is not interpreted as zero cameras.
        with _cache_lock:
            previous = _cache.get(district)
        if previous:
            return previous[1], previous[2] + " (stale; refresh failed)"
        return [], f"unavailable: {type(exc).__name__}"
    retrieved = datetime.now(timezone.utc).isoformat()
    with _cache_lock:
        _cache[district] = (monotonic(), entries, retrieved)
    return entries, retrieved


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    a = (
        sin(delta_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * asin(min(1.0, sqrt(a)))


def discover_public_cameras(
    latitude: float,
    longitude: float,
    *,
    radius_km: float = 10.0,
    limit: int = 8,
) -> dict[str, Any]:
    """Use caller-supplied location only for this read; never persist coordinates."""
    import math

    if not all(math.isfinite(v) for v in (latitude, longitude, radius_km)):
        raise ValueError("Coordinates and radius must be finite")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid geographic coordinates")
    if not 0.1 <= radius_km <= 50:
        raise ValueError("radius_km must be between 0.1 and 50")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    # Provider adapters are location-conditional. This first adapter is statewide
    # Caltrans, not a claim to discover arbitrary public safety / private cameras.
    if not (32.0 <= latitude <= 42.1 and -124.6 <= longitude <= -114.0):
        melbourne_area = -39.0 <= latitude <= -37.0 and 144.0 <= longitude <= 146.0
        return {
            "status": "unsupported_region",
            "coverage": "no integrated public-camera catalog in this region",
            "cameras": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source_url": _VICTRAFFIC if melbourne_area else "",
            "source_kind": "official traffic information" if melbourne_area else "",
            "source_note": (
                "VicTraffic offers official local traffic information; this does not imply its cameras have a public stream API."
                if melbourne_area else "A documented, publicly accessible feed provider must be added."
            ),
            "coordinates_stored": False,
        }

    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    fetched: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_get_district, district): district for district in range(1, 13)}
        for future in as_completed(futures):
            district = futures[future]
            rows, retrieved = future.result()
            if retrieved.startswith("unavailable"):
                errors.append(f"d{district}: {retrieved}")
            else:
                fetched.append(f"d{district}: {retrieved}")
            entries.extend(rows)

    near: list[dict[str, Any]] = []
    for row in entries:
        distance = _km(latitude, longitude, row["latitude"], row["longitude"])
        if distance <= radius_km:
            near.append({**row, "distance_km": round(distance, 2)})
    near.sort(key=lambda item: (item["distance_km"], item["id"]))
    return {
        "status": "partial" if errors else "ok",
        "coverage": "Caltrans highway cameras only; no municipal/private CCTV",
        "cameras": near[:limit],
        "matching_count": len(near),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "provider_fetched_at": fetched,
        "provider_errors": errors,
        "source_url": _CALTRANS_CATALOG,
        "source_note": (
            "Published location/service status is not proof a still or live stream is currently working. "
            "Camera field timestamps are not the capture time of the current image."
        ),
        "coordinates_stored": False,
    }
