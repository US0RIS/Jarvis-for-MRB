from __future__ import annotations

"""Opt-in portable environmental observations from documented public providers.

These calls neither persist the requested location nor poll in the background.
Air quality is MODELLED global data, not a sensor reading; NWS is authoritative
for its supported United States area only, never a global all-clear service.
"""

from datetime import datetime, timezone
import math
from typing import Any

import httpx

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
AIR_DOCS = "https://open-meteo.com/en/docs/air-quality-api"
ALERT_URL = "https://api.weather.gov/alerts/active"
ALERT_DOCS = "https://www.weather.gov/documentation/services-web-alerts"
MAX_BODY = 1_500_000


def _validate_position(latitude: float, longitude: float) -> None:
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise ValueError("Coordinates must be finite.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid geographic coordinates.")


def _read_json(client: httpx.Client, url: str, *, params: dict[str, Any], headers: dict[str, str]) -> Any:
    # No redirects to arbitrary external hosts; bound memory for public sources.
    with client.stream("GET", url, params=params, headers=headers) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                raise ValueError("Environmental provider response exceeded size limit.")
    return __import__("json").loads(body)


def _timestamp(value: object) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _number(value: object) -> float | None:
    try:
        v = float(value)
        return round(v, 1) if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def _air_quality(data: Any, checked_at: str) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("current"), dict):
        raise ValueError("Air-quality provider returned an unsupported schema.")
    current = data["current"]
    observation = _timestamp(current.get("time"))
    if not observation:
        raise ValueError("Air-quality provider did not supply a valid model time.")
    elapsed_hours = abs((datetime.now(timezone.utc) - observation).total_seconds()) / 3600
    us_aqi = _number(current.get("us_aqi"))
    european_aqi = _number(current.get("european_aqi"))
    pm25 = _number(current.get("pm2_5"))
    uv_index = _number(current.get("uv_index"))
    if all(v is None for v in (us_aqi, european_aqi, pm25, uv_index)):
        raise ValueError("Air-quality provider returned no requested fields.")
    return {
        "status": "stale" if elapsed_hours > 6 else "ok",
        "us_aqi": us_aqi,
        "european_aqi": european_aqi,
        "pm2_5_ug_m3": pm25,
        "uv_index": uv_index,
        "model_time_utc": observation.isoformat(),
        "checked_at": checked_at,
        "source_url": AIR_DOCS,
        "source": "Open-Meteo / Copernicus CAMS",
        "source_note": (
            "Modelled air quality, NOT a local sensor or government monitoring station; "
            "global model may use roughly 45 km grid cells. US AQI is a reference scale, "
            "including outside the United States. Never treat it as a street-level reading."
        ),
    }


def _in_nws_approximate_region(latitude: float, longitude: float) -> bool:
    # Broad bounding boxes only determine if requesting NWS is worthwhile.
    # NWS itself determines actual point support (parts of Canada, etc. fail).
    return any((
        24 <= latitude <= 50 and -125 <= longitude <= -66,  # CONUS bounding
        50 <= latitude <= 72 and -170 <= longitude <= -129,  # Alaska
        18 <= latitude <= 23 and -161 <= longitude <= -154,  # Hawaii
        17 <= latitude <= 19 and -68 <= longitude <= -64,  # Puerto Rico / VI
        12 <= latitude <= 15 and 144 <= longitude <= 146,  # Guam
    ))


def _official_alerts(data: Any, checked_at: str) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise ValueError("NWS alerts provider returned an unsupported schema.")
    alerts = []
    now = datetime.now(timezone.utc)
    for item in data["features"]:
        props = item.get("properties") if isinstance(item, dict) else None
        if not isinstance(props, dict):
            continue
        expires = _timestamp(props.get("expires"))
        if expires is not None and expires < now:
            continue
        alerts.append({
            "id": str(props.get("id") or item.get("id") or "")[:300],
            "event": str(props.get("event") or "")[:150],
            "headline": str(props.get("headline") or "")[:280],
            "severity": str(props.get("severity") or "Unknown")[:40],
            "urgency": str(props.get("urgency") or "Unknown")[:40],
            "instruction": str(props.get("instruction") or "")[:1000],
            "expires": str(props.get("expires") or ""),
            "sender": str(props.get("senderName") or "National Weather Service")[:120],
        })
        if len(alerts) == 16:
            break
    return {
        "status": "partial" if len(alerts) > 15 else "ok",
        "coverage": "NWS point-specific alerts only",
        "alerts": alerts[:15],
        "source_limit_reached": len(alerts) > 15,
        "source_result_limit": 15,
        "checked_at": checked_at,
        "source_url": ALERT_DOCS,
        "source_note": (
            "Official NWS weather alerts for a supported point. An empty list is not "
            "an all-hazards clearance. No alerts from local police, fire, transit, "
            "earthquake, evacuation or authorities outside NWS are included."
        ),
    }


def physical_conditions(latitude: float, longitude: float) -> dict[str, Any]:
    _validate_position(latitude, longitude)
    checked_at = datetime.now(timezone.utc).isoformat()
    air: dict[str, Any]
    alerts: dict[str, Any]
    with httpx.Client(timeout=httpx.Timeout(9.0), follow_redirects=False) as client:
        try:
            data = _read_json(
                client, AIR_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "us_aqi,european_aqi,pm2_5,uv_index",
                    "timezone": "GMT",
                    "forecast_days": 1,
                },
                headers={"Accept": "application/json"},
            )
            air = _air_quality(data, checked_at)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            air = {
                "status": "unavailable", "source_url": AIR_DOCS,
                "source_note": "Air-quality provider failed: " + type(exc).__name__,
            }
        if _in_nws_approximate_region(latitude, longitude):
            try:
                data = _read_json(
                    client, ALERT_URL,
                    params={"point": f"{latitude:.5f},{longitude:.5f}"},
                    headers={
                        "Accept": "application/geo+json",
                        "User-Agent": "JarvisForMRB/0.13 (+https://github.com/US0RIS/Jarvis-for-MRB)",
                    },
                )
                alerts = _official_alerts(data, checked_at)
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                alerts = {
                    "status": "unavailable", "alerts": [],
                    "source_url": ALERT_DOCS,
                    "source_note": "NWS point alerts could not be checked: " + type(exc).__name__,
                }
        else:
            alerts = {
                "status": "unsupported_region", "alerts": [],
                "source_url": ALERT_DOCS,
                "source_note": "No official weather-alert provider is integrated for this country/region. This is NOT an all clear.",
            }
    return {
        "checked_at": checked_at,
        "air_quality": air,
        "weather_alerts": alerts,
        "coordinates_stored": False,
        "location_sharing_note": (
            "The backend does not store location; external environmental providers receive "
            "the coordinates required for this one-time lookup."
        ),
    }
