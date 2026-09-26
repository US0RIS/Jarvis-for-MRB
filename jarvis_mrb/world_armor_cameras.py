from __future__ import annotations

"""Opt-in World Armor public-camera evidence sidecar.

The core AQI/NWS/USGS sample contracts remain unchanged. Camera images have
no trusted capture time and cannot be fabricated as source-timed events.
Only source-qualified descriptions/hashes enter the expiring region store.
"""

from contextlib import closing
from datetime import datetime
import math
import os
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from jarvis_mrb.world_armor_phase1 import (
    STORE, ArmorDisabled, _clock, _connect, _identifier, _record, _require_enabled,
)

_MAX_RECEIPTS = 40
_MAX_SEARCH = 100


def _authorize_camera() -> None:
    _require_enabled()
    if os.getenv("JARVIS_WORLD_ARMOR_CAMERAS_ENABLED") != "1":
        raise ArmorDisabled(
            "World Armor camera collection is off. Set "
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED=1 explicitly."
        )


def _path(db_path: Path | None) -> Path:
    return Path(db_path) if db_path is not None else STORE


def _schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS armor_camera_receipts (
            id TEXT PRIMARY KEY,
            investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
            camera_ref TEXT NOT NULL,
            provider TEXT NOT NULL,
            title TEXT NOT NULL,
            media_kind TEXT NOT NULL,
            source_display TEXT NOT NULL,
            condition TEXT,
            classification TEXT,
            description TEXT NOT NULL,
            image_sha256 TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            capture_time TEXT,
            received_at TEXT NOT NULL,
            camera_latitude REAL,
            camera_longitude REAL,
            spatial_basis TEXT NOT NULL,
            change_state TEXT NOT NULL,
            imported_watch_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_armor_camera_region_time
          ON armor_camera_receipts(investigation_id,received_at);
    """)


def _km(a: float, b: float, c: float, d: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    x = sin(radians(c - a) / 2) ** 2 + (
        cos(radians(a)) * cos(radians(c))
        * sin(radians(d - b) / 2) ** 2
    )
    return 6371.0088 * 2 * asin(min(1, sqrt(max(0, x))))


def discover_public_cameras_global(
    latitude: float, longitude: float, *,
    radius_km: float = 30, limit: int = 30,
) -> dict[str, Any]:
    _require_enabled()
    if (type(latitude) not in (float, int)
            or type(longitude) not in (float, int)
            or type(radius_km) not in (float, int)
            or not all(math.isfinite(x) for x in (
                float(latitude), float(longitude), float(radius_km),
            )) or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
            or not 1 <= radius_km <= 250
            or type(limit) is not int or not 1 <= limit <= _MAX_SEARCH):
        raise ValueError("Finite location, 1–250 km radius and limit 1–100 required.")
    results = []
    statuses = []
    from jarvis_mrb.public_camera_windy import discover_windy_cameras
    try:
        windy = discover_windy_cameras(
            latitude, longitude, radius_km=radius_km, limit=limit,
        )
        results.extend(windy["cameras"])
        statuses.append({
            "provider": "Windy Webcams v3", "status": windy["status"],
            "reported_total": windy.get("reported_total"),
            "key_required": windy.get("key_required"),
        })
    except (ValueError, __import__("httpx").HTTPError) as exc:
        statuses.append({
            "provider": "Windy Webcams v3",
            "status": "unavailable", "error_type": type(exc).__name__,
        })
    if 32.0 <= latitude <= 42.1 and -124.6 <= longitude <= -114.0:
        from jarvis_mrb.public_camera_catalog import discover_public_cameras
        try:
            cal = discover_public_cameras(
                latitude, longitude,
                radius_km=min(radius_km, 50), limit=min(20, limit),
            )
            for item in cal["cameras"]:
                results.append({
                    **item, "source_note": cal["source_note"],
                    "camera_ref": item["id"],
                    "geography_basis": "provider_reported_camera_location_not_view_cone",
                })
            statuses.append({
                "provider": "Caltrans CWWP2", "status": cal["status"],
                "reported_total": cal.get("matching_count"),
            })
        except (ValueError, __import__("httpx").HTTPError) as exc:
            statuses.append({
                "provider": "Caltrans CWWP2",
                "status": "unavailable", "error_type": type(exc).__name__,
            })
    results.sort(key=lambda x: (
        _km(latitude, longitude, x["latitude"], x["longitude"]),
        x["id"],
    ))
    return {
        "schema": "jarvis.world_armor.public_camera_catalog.v1",
        "cameras": results[:limit],
        "provider_statuses": statuses,
        "truncated": len(results) > limit,
        "public_media_url_enrollment": True,
        "camera_capture_time_verified": False,
        "qualifier": (
            "Directory catalogs are incomplete. Public image URLs may expire "
            "or require a provider contract. A reported camera location is "
            "not its viewing footprint."
        ),
    }


def _catalog_geography(camera_ref: str) -> tuple[float, float] | None:
    if camera_ref.startswith("caltrans-d"):
        from jarvis_mrb.public_camera_vision import _pick
        item = _pick(camera_ref)
    elif camera_ref.startswith("windy-"):
        from jarvis_mrb.public_camera_windy import camera_from_windy_id
        item = camera_from_windy_id(camera_ref)
    else:
        raise ValueError("Unsupported public camera catalog ID.")
    latitude = float(item["latitude"])
    longitude = float(item["longitude"])
    if not all(map(math.isfinite, (latitude, longitude))):
        raise ValueError("Provider camera has no valid geographic point.")
    return latitude, longitude


def _store_observation(
    investigation_id: str, evidence: dict[str, Any], *,
    point: tuple[float, float] | None,
    db_path: Path | None = None,
    now: datetime | None = None,
    imported_watch_id: str | None = None,
) -> dict[str, Any]:
    instant = _clock(now)
    _authorize_camera()
    path = _path(db_path)
    with closing(_connect(path, create=False)) as con, con:
        _schema(con)
        con.execute("BEGIN IMMEDIATE")
        record = _record(con, investigation_id, instant)
        if point is not None and _km(
            record["latitude"], record["longitude"], point[0], point[1],
        ) > record["radius_km"]:
            raise ValueError(
                "Publisher-reported camera location lies outside the selected region."
            )
        count = con.execute(
            "SELECT COUNT(*) FROM armor_camera_receipts WHERE investigation_id=?",
            (investigation_id,),
        ).fetchone()[0]
        if count >= _MAX_RECEIPTS:
            raise ValueError("Region has reached its 40-camera-evidence cap.")
        condition = evidence.get("watch_condition")
        classification = evidence.get("condition_status")
        if classification not in (None, "observed", "not_observed", "uncertain"):
            raise ValueError("Unsupported camera classification.")
        digest = str(evidence["image_sha256"])
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid content hash.")
        earlier = con.execute(
            "SELECT image_sha256,classification FROM armor_camera_receipts "
            "WHERE investigation_id=? AND camera_ref=? AND "
            "condition IS ? ORDER BY received_at DESC,id DESC LIMIT 1",
            (investigation_id, str(evidence["camera_id"]), condition),
        ).fetchone()
        change = (
            "baseline" if earlier is None else
            "same_published_image_not_new_capture"
            if earlier["image_sha256"] == digest else
            "different_image_not_proven_physical_change"
        )
        key = uuid4().hex
        con.execute(
            "INSERT INTO armor_camera_receipts"
            "(id,investigation_id,camera_ref,provider,title,media_kind,"
            "source_display,condition,classification,description,image_sha256,"
            "retrieved_at,capture_time,received_at,camera_latitude,"
            "camera_longitude,spatial_basis,change_state,imported_watch_id)"
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                key, investigation_id, str(evidence["camera_id"])[:100],
                str(evidence.get("source_kind") or "public_camera")[:90],
                str(evidence.get("camera_name") or "Public camera")[:150],
                str(evidence.get("media_kind") or "published_still")[:40],
                str(evidence["source_url"])[:350],
                condition, classification,
                str(evidence.get("description") or "")[:380], digest,
                str(evidence["retrieved_at"])[:60],
                None, instant.isoformat(),
                point[0] if point else None, point[1] if point else None,
                ("publisher_camera_point_view_cone_unknown" if point
                 else "operator_associated_region_camera_location_unknown"),
                change, imported_watch_id,
            ),
        )
        item = con.execute(
            "SELECT * FROM armor_camera_receipts WHERE id=?", (key,),
        ).fetchone()
    return {**dict(item), "image_retained": False,
            "capture_time_known": False, "independent_incident_verified": False,
            "world_armor_sample_inserted": False,
            "note": (
                "Camera evidence is receipt-time-only. It is NOT inserted "
                "into source-timed AQI/NWS/USGS correlation or Watch alerts."
            )}


def inspect_camera(
    investigation_id: str, *, camera_ref: str = "",
    public_url: str = "", condition: str = "",
    db_path: Path | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    """One explicitly selected camera, no hidden long-running stream."""
    _authorize_camera()
    instant = _clock(now)
    path = _path(db_path)
    with closing(_connect(path, create=False)) as con:
        record = _record(con, investigation_id, instant)
        _schema(con)
        if con.execute(
            "SELECT COUNT(*) FROM armor_camera_receipts WHERE investigation_id=?",
            (investigation_id,),
        ).fetchone()[0] >= _MAX_RECEIPTS:
            raise ValueError("Region has reached its 40-camera-evidence cap.")
    if bool(camera_ref) == bool(public_url):
        raise ValueError("Select exactly one catalog camera or direct public media URL.")
    if public_url:
        from jarvis_mrb.public_camera_media import validate_public_camera_url
        validate_public_camera_url(public_url)
        point = None
    else:
        point = _catalog_geography(camera_ref)
        if _km(
            record["latitude"], record["longitude"], point[0], point[1],
        ) > record["radius_km"]:
            raise ValueError("Camera outside enrolled region.")
    from jarvis_mrb.public_camera_vision import analyze_public_camera
    observed = analyze_public_camera(
        camera_ref=camera_ref, public_url=public_url, condition=condition,
    )
    return _store_observation(
        investigation_id, observed, point=point,
        db_path=path, now=now,
    )


def list_camera_receipts(
    investigation_id: str, *, db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = _path(db_path)
    if not path.is_file():
        return {"camera_receipts": [], "source_coverage": "no_region_store"}
    instant = _clock(now)
    with closing(_connect(path, create=True)) as con:
        _schema(con)
        row = con.execute(
            "SELECT expires_at FROM investigations WHERE id=?",
            (_identifier(investigation_id),),
        ).fetchone()
        if row is None or row["expires_at"] <= instant.isoformat():
            return {"camera_receipts": [], "source_coverage": "region_expired_or_absent"}
        rows = con.execute(
            "SELECT * FROM armor_camera_receipts WHERE investigation_id=? "
            "ORDER BY received_at DESC,id DESC LIMIT ?",
            (investigation_id, _MAX_RECEIPTS),
        ).fetchall()
    return {
        "schema": "jarvis.world_armor.camera_receipts.v1",
        "camera_receipts": [dict(x) for x in rows],
        "source_coverage": "selected_cameras_only_not_all_cameras",
        "capture_time_verified": False,
        "image_archive": False,
        "source_timed_correlation": False,
    }


def forget_camera_receipt(
    receipt_id: str, *, db_path: Path | None = None,
) -> dict[str, Any]:
    path = _path(db_path)
    if not path.is_file():
        return {"deleted": 0}
    with closing(_connect(path, create=True)) as con, con:
        _schema(con)
        result = con.execute(
            "DELETE FROM armor_camera_receipts WHERE id=?",
            (_identifier(receipt_id),),
        )
    return {"deleted": result.rowcount,
            "qualifier": "Only the local text/hash camera receipt was deleted."}
