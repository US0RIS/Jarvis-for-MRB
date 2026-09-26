from __future__ import annotations

"""Recent USGS earthquake detections near any selected location.

This is NOT a comprehensive 911/fire/police incident feed, earthquake forecast,
or emergency warning service. Data is a bounded official public GeoJSON query.
"""

from datetime import datetime, timedelta, timezone
import math
from typing import Any

import httpx

_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
_DOCS = "https://earthquake.usgs.gov/fdsnws/event/1/"
_MAX_BYTES = 1_500_000


def regional_earthquakes(
    latitude: float,
    longitude: float,
    *,
    radius_km: float = 100,
    hours: int = 24,
    minimum_magnitude: float = 2.5,
) -> dict[str, Any]:
    if not all(math.isfinite(v) for v in (latitude, longitude, radius_km, minimum_magnitude)):
        raise ValueError("Incident parameters must be finite.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid incident coordinates.")
    if not 1 <= radius_km <= 300 or not 1 <= hours <= 72 or not 0 <= minimum_magnitude <= 9:
        raise ValueError("Incident query outside allowed bounds.")
    checked = datetime.now(timezone.utc)
    try:
        with httpx.Client(timeout=httpx.Timeout(12), follow_redirects=False) as client:
            with client.stream(
                "GET", _URL,
                params={
                    "format": "geojson",
                    "latitude": round(latitude, 5),
                    "longitude": round(longitude, 5),
                    "maxradiuskm": radius_km,
                    "starttime": (checked - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S"),
                    "endtime": checked.strftime("%Y-%m-%dT%H:%M:%S"),
                    "minmagnitude": minimum_magnitude,
                    "orderby": "time",
                    "limit": 51,  # one extra source row detects an incomplete 50-item result
                },
                headers={"Accept": "application/geo+json", "User-Agent": "JarvisForMRB/0.13 (public incident information)"},
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_BYTES:
                        raise ValueError("USGS response too large.")
        data = __import__("json").loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("features"), list):
            raise ValueError("USGS earthquake response has unexpected shape.")
        source_limit_reached = len(data["features"]) > 50
        events = []
        for item in data["features"][:50]:
            props = item.get("properties") if isinstance(item, dict) else None
            if not isinstance(props, dict):
                continue
            identifier = str(item.get("id") or "")[:70]
            if not identifier or not identifier.replace("_", "").replace("-", "").isalnum():
                continue
            magnitude = props.get("mag")
            epoch = props.get("time")
            if not isinstance(magnitude, (float, int)) or not isinstance(epoch, (float, int)):
                continue
            moment = datetime.fromtimestamp(epoch / 1000, timezone.utc)
            url = str(props.get("url") or "")
            if not url.startswith("https://earthquake.usgs.gov/"):
                url = _DOCS
            # USGS GeoJSON geometry is [longitude, latitude, depth_km].
            # A missing or invalid geometry remains unknown; the query center
            # is never substituted for an earthquake's epicenter.
            coords = ((item.get("geometry") or {}).get("coordinates")
                      if isinstance(item.get("geometry"), dict) else None)
            epicenter_lat: float | None = None
            epicenter_lon: float | None = None
            if (isinstance(coords, list) and len(coords) >= 2
                    and all(type(v) in (int, float) and math.isfinite(v)
                            for v in coords[:2])
                    and -90 <= coords[1] <= 90 and -180 <= coords[0] <= 180):
                epicenter_lon = round(float(coords[0]), 5)
                epicenter_lat = round(float(coords[1]), 5)
            events.append({
                "id": identifier, "magnitude": round(float(magnitude), 1),
                "latitude": epicenter_lat, "longitude": epicenter_lon,
                "place": str(props.get("place") or "unspecified location")[:160],
                "occurred_at": moment.isoformat(), "source_url": url,
                "reviewed": props.get("status") == "reviewed",
            })
        return {
            "status": "partial" if source_limit_reached else "ok",
            "events": events,
            "source_limit_reached": source_limit_reached,
            "source_result_limit": 50,
            "checked_at": checked.isoformat(), "source_url": _DOCS,
            "source_note": (
                "USGS earthquake detections only, subject to magnitude threshold, "
                "coverage and later revision. These are not all local emergencies, "
                "not tsunami/evacuation warnings, and not predictions or assurances."
            ),
        }
    except (httpx.HTTPError, ValueError, TypeError, OverflowError) as exc:
        return {
            "status": "unavailable", "events": [],
            "checked_at": checked.isoformat(), "source_url": _DOCS,
            "source_note": "USGS incident provider unavailable: " + type(exc).__name__,
        }
