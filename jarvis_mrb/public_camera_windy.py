from __future__ import annotations

"""Optional, keyed Windy Webcams v3 provider adapter.

Do not scrape Windy pages or claim that a public detail page yields an open
stream. Signed previews are re-fetched from Windy for each explicit analysis,
not saved into World Armor or external-watch ledgers.
"""

from datetime import datetime, timezone
import math
import os
import re
from typing import Any

import httpx

from jarvis_mrb.public_camera_media import (
    snapshot_public_media, validate_public_camera_url,
)

_API = "https://api.windy.com/webcams/api/v3/webcams"
_ID = re.compile(r"^windy-([1-9][0-9]{0,19})$")
_MAX_BODY = 2_500_000


def configured() -> bool:
    return bool(os.getenv("JARVIS_WINDY_WEBCAMS_API_KEY", "").strip())


def _get(path: str, *, params: dict[str, Any]) -> Any:
    key = os.getenv("JARVIS_WINDY_WEBCAMS_API_KEY", "").strip()
    if not key:
        raise ValueError("Windy Webcams is not configured; an API key is required.")
    with httpx.Client(
        timeout=httpx.Timeout(12.0), follow_redirects=False, trust_env=False,
    ) as client:
        with client.stream("GET", path, params=params,
                           headers={"X-Windy-API-Key": key,
                                    "Accept": "application/json"}) as response:
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("Windy API redirected unexpectedly.")
            buf = bytearray()
            for data in response.iter_bytes():
                buf.extend(data)
                if len(buf) > _MAX_BODY:
                    raise ValueError("Windy response exceeds the byte budget.")
    result = __import__("json").loads(buf)
    if not isinstance(result, (dict, list)):
        raise ValueError("Unexpected Windy response shape.")
    return result


def _entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("status") != "active":
        return None
    try:
        ident = int(raw["webcamId"])
        location = raw["location"]
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])
        if ident < 1 or not all(map(math.isfinite, (latitude, longitude))):
            return None
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return None
    except (ValueError, KeyError, TypeError):
        return None
    images = raw.get("images") or {}
    current = images.get("current") or {}
    if not isinstance(current, dict):
        return None
    image_url = next(
        (u for key in ("preview", "icon", "thumbnail", "small", "medium",
                      "large", "full")
         if type(u := current.get(key)) is str and u.startswith("https://")),
        "",
    )
    if image_url:
        try:
            validate_public_camera_url(image_url, provider_signed=True)
        except ValueError:
            image_url = ""
    urls = raw.get("urls") or {}
    detail = str(urls.get("detail") or "")
    if not detail.startswith("https://www.windy.com/webcams/"):
        detail = "https://www.windy.com/webcams"
    return {
        "id": f"windy-{ident}",
        "provider": "Windy Webcams v3",
        "title": str(raw.get("title") or "Public webcam")[:150],
        "latitude": latitude, "longitude": longitude,
        "image_url": image_url,
        "stream_url": "",  # A web player/embed is NOT an accessible stream.
        "provider_detail_url": detail,
        "source_url": "https://api.windy.com/webcams/docs",
        "source_note": (
            "Opt-in third-party webcam metadata and short-lived publisher "
            "preview; captured-at time, coverage, rights and continuity unknown."
        ),
        "capture_time": None,
        "provider_catalog": "Windy Webcams API v3",
        "geography_basis": "provider_reported_camera_location_not_view_cone",
        "in_service_reported": True,
    }


def discover_windy_cameras(latitude: float, longitude: float, *,
                            radius_km: float = 20,
                            limit: int = 30) -> dict[str, Any]:
    if (type(latitude) not in (float, int)
            or type(longitude) not in (float, int)
            or type(radius_km) not in (float, int)
            or not all(math.isfinite(float(x))
                       for x in (latitude, longitude, radius_km))
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
            or not 1 <= radius_km <= 250
            or type(limit) is not int or not 1 <= limit <= 100):
        raise ValueError("Windy search requires a finite point, 1–250 km radius and limit 1–100.")
    if not configured():
        return {
            "status": "not_configured", "cameras": [],
            "key_required": "JARVIS_WINDY_WEBCAMS_API_KEY",
            "provider": "Windy Webcams v3",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    found: list[dict[str, Any]] = []
    total: int | None = None
    errors: list[str] = []
    for offset in range(0, min(200, limit + 50), 50):
        try:
            response = _get(_API, params={
                "nearby": f"{latitude:.5f},{longitude:.5f},{radius_km:.1f}",
                "include": "images,location,urls,player",
                "limit": 50, "offset": offset,
            })
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(type(exc).__name__)
            break
        if not isinstance(response, dict) or not isinstance(response.get("webcams"), list):
            errors.append("invalid_provider_shape")
            break
        if type(response.get("total")) is int:
            total = response["total"]
        rows = response["webcams"]
        for raw in rows:
            entry = _entry(raw)
            if entry:
                found.append(entry)
        if len(rows) < 50 or (total is not None and offset + len(rows) >= total):
            break
    return {
        "status": ("partial" if found and errors else
                   "unavailable" if errors else "ok"),
        "cameras": found[:limit],
        "reported_total": total,
        "truncated": total is not None and total > len(found[:limit]),
        "coverage": "Windy third-party webcam directory, not all public CCTV",
        "provider_errors": errors,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "provider": "Windy Webcams v3",
        "source_url": "https://api.windy.com/webcams/docs",
        "attribution": "Webcams provided by Windy.com",
    }


def camera_from_windy_id(camera_id: str) -> dict[str, Any]:
    match = _ID.fullmatch(camera_id or "")
    if not match:
        raise ValueError("Invalid Windy camera ID.")
    raw = _get(_API + "/" + match.group(1),
               params={"include": "images,location,urls,player"})
    entry = _entry(raw)
    if entry is None or entry["id"] != camera_id:
        raise ValueError("Windy camera inactive or returned no usable metadata.")
    if not entry["image_url"]:
        raise ValueError("Windy did not return an accessible public still.")
    return entry


def snapshot_windy_camera(camera_id: str) -> dict[str, Any]:
    camera = camera_from_windy_id(camera_id)
    frame = snapshot_public_media(camera["image_url"], provider_signed=True)
    return {
        **frame,
        "camera_id": camera_id, "camera_name": camera["title"],
        "provider": camera["provider"],
        "provider_detail_url": camera["provider_detail_url"],
        "source_display": "Windy API-authorized published webcam preview",
        "source_id": camera_id,
        "geography": {"latitude": camera["latitude"],
                       "longitude": camera["longitude"]},
        "image_url_persisted": False,
    }
