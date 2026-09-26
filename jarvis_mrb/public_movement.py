from __future__ import annotations

"""Public movement telemetry adapters for World Armor.

These adapters expose publicly broadcast aircraft/vessel state, not people.
They never infer owner, passenger, crew, itinerary, home, employer, or
counterparty identity. Provider identifiers remain source identifiers only.

OpenSky supports anonymous recent state vectors and optional OAuth client
credentials. AISStream requires a server-side API key and a subscribed
bounding box. Provider quotas/terms remain authoritative over Jarvis settings.
"""

from datetime import datetime, timezone
import json
import math
import os
import threading
import time
from typing import Any

import httpx

_OPENSKY_STATES = "https://opensky-network.org/api/states/all"
_OPENSKY_TOKEN = (
    "https://auth.opensky-network.org/auth/realms/"
    "opensky-network/protocol/openid-connect/token"
)
_OPENSKY_DOCS = "https://openskynetwork.github.io/opensky-api/rest.html"
_AIS_URL = "wss://stream.aisstream.io/v0/stream"
_AIS_DOCS = "https://aisstream.io/documentation"
_MAX_OPENSKY_BYTES = 12_000_000
_MAX_AIS_MESSAGE_BYTES = 1_000_000
_TOKEN_LOCK = threading.Lock()
_TOKEN: dict[str, Any] = {"value": None, "expires_at": 0.0}


def _point(latitude: float, longitude: float) -> tuple[float, float]:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Movement coordinates must be numeric.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("Movement coordinates must be finite.")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Movement coordinates are outside WGS84 bounds.")
    return lat, lon


def _bbox(latitude: float, longitude: float, radius_km: float) -> list[float]:
    lat, lon = _point(latitude, longitude)
    try:
        radius = float(radius_km)
    except (TypeError, ValueError) as exc:
        raise ValueError("Movement radius must be numeric.") from exc
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Movement radius must be positive.")
    if radius >= 20_000:
        return [-90.0, -180.0, 90.0, 180.0]
    dlat = min(90.0, radius / 111.32)
    denom = 111.32 * max(0.01, abs(math.cos(math.radians(lat))))
    dlon = min(180.0, radius / denom)
    return [
        max(-90.0, lat - dlat),
        max(-180.0, lon - dlon),
        min(90.0, lat + dlat),
        min(180.0, lon + dlon),
    ]


def _oauth_token() -> str | None:
    client_id = os.getenv("OPENSKY_CLIENT_ID", "").strip()
    secret = os.getenv("OPENSKY_CLIENT_SECRET", "").strip()
    if not client_id and not secret:
        return None
    if not client_id or not secret:
        raise ValueError("Configure both OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET.")
    now = time.time()
    with _TOKEN_LOCK:
        if _TOKEN["value"] and float(_TOKEN["expires_at"]) > now + 45:
            return str(_TOKEN["value"])
        with httpx.Client(
            timeout=httpx.Timeout(10.0), follow_redirects=False, trust_env=False,
        ) as client:
            response = client.post(
                _OPENSKY_TOKEN,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": secret,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        token = data.get("access_token")
        expires = data.get("expires_in", 1800)
        if type(token) is not str or not token or type(expires) not in (int, float):
            raise ValueError("OpenSky OAuth response missing usable token.")
        _TOKEN["value"] = token
        _TOKEN["expires_at"] = now + max(60.0, float(expires))
        return token


def _opensky_request(params: dict[str, Any]) -> dict[str, Any]:
    token = _oauth_token()
    headers = {
        "Accept": "application/json",
        "User-Agent": "JarvisForMRB/0.13 (public movement awareness)",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    with httpx.Client(
        timeout=httpx.Timeout(15.0), follow_redirects=False, trust_env=False,
    ) as client:
        with client.stream(
            "GET", _OPENSKY_STATES, params=params, headers=headers,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > _MAX_OPENSKY_BYTES:
                    raise ValueError("OpenSky response exceeds host byte budget.")
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(
        payload.get("states"), (list, type(None))
    ):
        raise ValueError("OpenSky returned an unsupported state-vector payload.")
    return payload


def normalize_opensky_payload(
    data: dict[str, Any], *, checked_at: str | datetime | None = None,
    global_scope: bool = False, authenticated: bool = False,
) -> dict[str, Any]:
    """Normalize one provider payload, including responses fetched by a mesh worker."""
    checked = (
        checked_at if isinstance(checked_at, datetime)
        else datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
        if checked_at else datetime.now(timezone.utc)
    )
    if checked.tzinfo is None:
        raise ValueError("OpenSky receipt time must be offset-aware.")
    checked = checked.astimezone(timezone.utc)
    if not isinstance(data, dict) or not isinstance(
        data.get("states"), (list, type(None))
    ):
        raise ValueError("OpenSky returned an unsupported state-vector payload.")
    stamp = data.get("time")
    if type(stamp) not in (int, float) or not math.isfinite(float(stamp)):
        raise ValueError("OpenSky payload missing source timestamp.")
    source_time = datetime.fromtimestamp(float(stamp), timezone.utc)
    age = (checked - source_time).total_seconds()
    if age < -60 or age > 300:
        return {
            "status": "stale", "checked_at": checked.isoformat(),
            "source_observed_at": source_time.isoformat(),
            "entities": [], "source_url": _OPENSKY_DOCS,
            "source_note": (
                "OpenSky source timestamp is stale; "
                "no current entity state is asserted."
            ),
            "authenticated": authenticated,
            "global_scope": global_scope,
        }
    entities = []
    invalid = 0
    for row in data.get("states") or []:
        if not isinstance(row, list) or len(row) < 17:
            invalid += 1
            continue
        icao = str(row[0] or "").strip().lower()
        lon, lat = row[5], row[6]
        if (
            not icao or len(icao) > 16
            or type(lat) not in (int, float)
            or type(lon) not in (int, float)
            or not math.isfinite(float(lat))
            or not math.isfinite(float(lon))
            or not -90 <= float(lat) <= 90
            or not -180 <= float(lon) <= 180
        ):
            invalid += 1
            continue
        position_time = row[3] if type(row[3]) in (int, float) else None
        last_contact = row[4] if type(row[4]) in (int, float) else None
        observed_epoch = position_time or last_contact or stamp
        observed_at = datetime.fromtimestamp(
            float(observed_epoch), timezone.utc
        ).isoformat()
        callsign = " ".join(str(row[1] or "").split())[:20] or None

        def number(index: int) -> float | None:
            if len(row) <= index or type(row[index]) not in (int, float):
                return None
            value = float(row[index])
            return value if math.isfinite(value) else None

        category = row[17] if len(row) > 17 and type(row[17]) is int else None
        entities.append({
            "entity_type": "aircraft",
            "entity_id": "icao24:" + icao,
            "provider_identifier": icao,
            "callsign": callsign,
            "name": None,
            "latitude": round(float(lat), 6),
            "longitude": round(float(lon), 6),
            "altitude_m": number(7),
            "on_ground": bool(row[8]) if type(row[8]) is bool else None,
            "velocity_mps": number(9),
            "heading_deg": number(10),
            "vertical_rate_mps": number(11),
            "category": category,
            "position_source": row[16] if type(row[16]) is int else None,
            "observed_at": observed_at,
            "provider_time": source_time.isoformat(),
            "source": "OpenSky Network",
        })
    return {
        "status": "partial" if invalid else "ok",
        "checked_at": checked.isoformat(),
        "source_observed_at": source_time.isoformat(),
        "entities": entities,
        "invalid_records": invalid,
        "source_url": _OPENSKY_DOCS,
        "source_note": (
            "Public ADS-B/MLAT/etc. state vectors. Coverage is incomplete "
            "and provider-limited. Vehicle identifiers/callsigns are not "
            "person identities, ownership records, passenger data, or schedules."
        ),
        "authenticated": authenticated,
        "global_scope": global_scope,
    }


def opensky_state_vectors(
    *, latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float | None = None,
    global_scope: bool = False,
    extended: bool = True,
) -> dict[str, Any]:
    """Current publicly broadcast aircraft states, source IDs preserved."""
    if global_scope:
        if latitude is not None or longitude is not None or radius_km is not None:
            raise ValueError("Global OpenSky scope cannot also specify a local region.")
        params: dict[str, Any] = {}
    else:
        if latitude is None or longitude is None or radius_km is None:
            raise ValueError("Regional OpenSky scope needs latitude, longitude and radius.")
        lamin, lomin, lamax, lomax = _bbox(latitude, longitude, radius_km)
        params = {
            "lamin": round(lamin, 5), "lomin": round(lomin, 5),
            "lamax": round(lamax, 5), "lomax": round(lomax, 5),
        }
    if extended:
        params["extended"] = 1
    checked = datetime.now(timezone.utc)
    try:
        data = _opensky_request(params)
        return normalize_opensky_payload(
            data, checked_at=checked, global_scope=global_scope,
            authenticated=bool(os.getenv("OPENSKY_CLIENT_ID")),
        )
    except (httpx.HTTPError, ValueError, TypeError, OverflowError) as exc:
        return {
            "status": "unavailable", "checked_at": checked.isoformat(),
            "source_observed_at": None, "entities": [],
            "source_url": _OPENSKY_DOCS,
            "source_note": "OpenSky unavailable: " + type(exc).__name__,
            "global_scope": global_scope,
        }


def _ais_duration(value: float) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("AIS burst duration must be numeric.") from exc
    if not math.isfinite(duration) or not 0.5 <= duration <= 30:
        raise ValueError("AIS burst duration must be 0.5–30 seconds.")
    return duration


def _ais_entity(message: dict[str, Any], checked: datetime) -> dict[str, Any] | None:
    if message.get("MessageType") != "PositionReport":
        return None
    meta = message.get("MetaData")
    report = (message.get("Message") or {}).get("PositionReport")
    if not isinstance(meta, dict) or not isinstance(report, dict):
        raise ValueError("AIS position message missing metadata/report.")
    mmsi = meta.get("MMSI") or report.get("UserID")
    plat = meta.get("Latitude", report.get("Latitude"))
    plon = meta.get("Longitude", report.get("Longitude"))
    if (
        type(mmsi) not in (int, str)
        or type(plat) not in (int, float)
        or type(plon) not in (int, float)
    ):
        raise ValueError("AIS position message missing identity/coordinates.")
    mmsi_text = str(mmsi).strip()
    if (
        not mmsi_text.isdigit()
        or len(mmsi_text) != 9
        or not math.isfinite(float(plat))
        or not math.isfinite(float(plon))
        or not -90 <= float(plat) <= 90
        or not -180 <= float(plon) <= 180
    ):
        raise ValueError("AIS position message has invalid identity/coordinates.")
    ship_name = " ".join(str(meta.get("ShipName") or "").split())[:80] or None

    def num(value: Any) -> float | None:
        if type(value) not in (int, float):
            return None
        x = float(value)
        return x if math.isfinite(x) else None

    sog = num(report.get("Sog"))
    return {
        "entity_type": "vessel",
        "entity_id": "mmsi:" + mmsi_text,
        "provider_identifier": mmsi_text,
        "callsign": None,
        "name": ship_name,
        "latitude": round(float(plat), 6),
        "longitude": round(float(plon), 6),
        "altitude_m": None,
        "on_ground": None,
        "velocity_mps": sog * 0.514444 if sog is not None else None,
        "speed_knots": sog,
        "heading_deg": num(report.get("TrueHeading")),
        "course_deg": num(report.get("Cog")),
        "vertical_rate_mps": None,
        "category": None,
        "position_source": "AIS",
        "observed_at": checked.isoformat(),
        "provider_time": None,
        "source": "AISStream",
    }


def aisstream_position_multi_burst(
    regions: list[dict[str, Any]], *, duration_seconds: float = 4.0,
) -> dict[str, Any]:
    """One controller-side AISStream connection serving multiple exact regions."""
    if not isinstance(regions, list) or not 1 <= len(regions) <= 64:
        raise ValueError("AIS pooled burst requires 1–64 explicit regions.")
    duration = _ais_duration(duration_seconds)
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for region in regions:
        if not isinstance(region, dict):
            raise ValueError("AIS pooled region must be an object.")
        region_id = str(region.get("id") or "")
        if not region_id or len(region_id) > 128 or region_id in seen_ids:
            raise ValueError("AIS pooled region IDs must be unique and bounded.")
        seen_ids.add(region_id)
        lat, lon = _point(region.get("latitude"), region.get("longitude"))
        box = _bbox(lat, lon, region.get("radius_km"))
        normalized.append({"id": region_id, "bbox": box})
    checked = datetime.now(timezone.utc)
    key = os.getenv("AISSTREAM_API_KEY", "").strip()

    def result_for(status: str, entities: list[dict[str, Any]], *,
                   invalid: int = 0, received: int = 0,
                   note: str) -> dict[str, Any]:
        return {
            "status": status,
            "checked_at": checked.isoformat(),
            "source_observed_at": None,
            "entities": entities,
            "raw_position_messages": received,
            "invalid_records": invalid,
            "source_url": _AIS_DOCS,
            "source_note": note,
            "global_scope": False,
        }

    if not key:
        note = "AISStream requires a server-side AISSTREAM_API_KEY."
        return {
            "status": "not_configured",
            "checked_at": checked.isoformat(),
            "pooled_connection": False,
            "region_count": len(normalized),
            "results": {
                item["id"]: result_for(
                    "not_configured", [], note=note
                )
                for item in normalized
            },
        }

    entities: dict[str, dict[str, dict[str, Any]]] = {
        item["id"]: {} for item in normalized
    }
    invalid = 0
    received = 0
    bytes_seen = 0
    try:
        from websockets.sync.client import connect
        boxes = [
            [[item["bbox"][2], item["bbox"][1]],
             [item["bbox"][0], item["bbox"][3]]]
            for item in normalized
        ]
        subscription = {
            "APIKey": key,
            "BoundingBoxes": boxes,
            "FilterMessageTypes": ["PositionReport"],
        }
        deadline = time.monotonic() + duration
        with connect(
            _AIS_URL,
            open_timeout=6,
            close_timeout=2,
            max_size=_MAX_AIS_MESSAGE_BYTES,
            compression="deflate",
            proxy=None,
        ) as socket:
            socket.send(json.dumps(subscription))
            while time.monotonic() < deadline:
                remaining = max(0.05, deadline - time.monotonic())
                try:
                    raw = socket.recv(timeout=remaining)
                except TimeoutError:
                    break
                if isinstance(raw, bytes):
                    bytes_seen += len(raw)
                    text = raw.decode("utf-8")
                else:
                    bytes_seen += len(raw.encode("utf-8"))
                    text = raw
                if bytes_seen > 8_000_000:
                    raise ValueError("AIS burst exceeds host byte budget.")
                message = json.loads(text)
                if not isinstance(message, dict):
                    invalid += 1
                    continue
                if message.get("MessageType") == "SubscriptionConfirmation":
                    continue
                if message.get("MessageType") != "PositionReport":
                    continue
                received += 1
                try:
                    entity = _ais_entity(message, checked)
                except ValueError:
                    invalid += 1
                    continue
                if entity is None:
                    continue
                lat = float(entity["latitude"])
                lon = float(entity["longitude"])
                for item in normalized:
                    lamin, lomin, lamax, lomax = item["bbox"]
                    if lamin <= lat <= lamax and lomin <= lon <= lomax:
                        entities[item["id"]][entity["entity_id"]] = entity
        status = "partial" if invalid else "ok"
        note = (
            "One controller-side AISStream subscription served this exact "
            "enrolled region alongside other due regions. Event-driven "
            "coverage can be incomplete; MMSI is a vessel/station identifier, "
            "not a person identity."
        )
        return {
            "status": status,
            "checked_at": checked.isoformat(),
            "pooled_connection": True,
            "region_count": len(normalized),
            "raw_position_messages": received,
            "results": {
                item["id"]: result_for(
                    status, list(entities[item["id"]].values()),
                    invalid=invalid, received=received, note=note,
                )
                for item in normalized
            },
        }
    except Exception as exc:
        note = "AIS provider unavailable: " + type(exc).__name__
        return {
            "status": "unavailable",
            "checked_at": checked.isoformat(),
            "pooled_connection": True,
            "region_count": len(normalized),
            "results": {
                item["id"]: result_for(
                    "unavailable", [], note=note
                )
                for item in normalized
            },
        }


def aisstream_position_burst(
    *, latitude: float,
    longitude: float,
    radius_km: float,
    duration_seconds: float = 4.0,
) -> dict[str, Any]:
    """Compatibility single-region AIS burst backed by the pooled adapter."""
    pooled = aisstream_position_multi_burst(
        [{
            "id": "single",
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
        }],
        duration_seconds=duration_seconds,
    )
    result = dict(pooled["results"]["single"])
    result["pooled_connection"] = bool(pooled.get("pooled_connection"))
    result["pooled_region_count"] = 1
    return result

