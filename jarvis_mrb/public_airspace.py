from __future__ import annotations

"""Bounded, regional public airspace awareness. Not a person-tracking service."""

from datetime import datetime, timezone
import math
from typing import Any

import httpx

_URL = "https://opensky-network.org/api/states/all"
_DOCS = "https://openskynetwork.github.io/opensky-api/rest.html"
_MAX_BYTES = 2_000_000


def airspace_region(latitude: float, longitude: float, *, radius_km: float = 20) -> dict[str, Any]:
    if not all(math.isfinite(v) for v in (latitude, longitude, radius_km)):
        raise ValueError("Airspace position must be finite.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or not 1 <= radius_km <= 80:
        raise ValueError("Airspace location or radius is outside supported bounds.")
    deg_lat = radius_km / 111.32
    deg_lon = min(180, radius_km / max(10, 111.32 * abs(math.cos(math.radians(latitude)))))
    params = {
        "lamin": max(-90, latitude - deg_lat),
        "lamax": min(90, latitude + deg_lat),
        "lomin": max(-180, longitude - deg_lon),
        "lomax": min(180, longitude + deg_lon),
    }
    checked = datetime.now(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=httpx.Timeout(10), follow_redirects=False) as client:
            with client.stream("GET", _URL, params=params, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_BYTES:
                        raise ValueError("OpenSky response too large.")
        data = __import__("json").loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("states"), (list, type(None))):
            raise ValueError("OpenSky unexpected response.")
        stamp = data.get("time")
        if stamp is None or not isinstance(stamp, (int, float)):
            raise ValueError("OpenSky response missing time.")
        age = datetime.now(timezone.utc).timestamp() - float(stamp)
        if age > 300 or age < -60:
            return {
                "status": "stale", "checked_at": checked, "states_at": stamp,
                "source_url": _DOCS, "aircraft_count": None,
                "source_note": "OpenSky state timestamp is not current; no live count is claimed.",
            }
        # Aggregation only: deliberately do not return transponder IDs, tail numbers,
        # callsigns, flight tracks, presumed passenger identities or historical trail.
        states = data.get("states") or []
        count = sum(
            1 for x in states if isinstance(x, list) and len(x) > 8
            and x[5] is not None and x[6] is not None
            and x[8] is False
        )
        return {
            "status": "ok", "checked_at": checked, "states_at": stamp,
            "source_url": _DOCS, "aircraft_count": count,
            "source_note": (
                "Regional OpenSky state vectors, coverage incomplete. Counts are not "
                "airport schedules, identification of passengers, and are not proof of all aircraft. "
                "OpenSky access is credit-limited and subject to non-commercial licensing."
            ),
        }
    except (httpx.HTTPError, ValueError, OverflowError, TypeError) as exc:
        return {
            "status": "unavailable", "checked_at": checked,
            "source_url": _DOCS, "aircraft_count": None,
            "source_note": "Airspace provider unavailable: " + type(exc).__name__,
        }
