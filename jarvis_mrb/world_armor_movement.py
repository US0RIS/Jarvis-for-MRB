from __future__ import annotations

"""Persistent public movement graph: aircraft + vessel observations.

Movement sources are separate grants because their provider semantics differ
from camera media. They live in the same World Armor platform SQLite file and
share the same design rules: explicit source rights, revocation, per-source
cadence, derived-data retention, lease fencing, and no hidden auto-start.

Entity IDs are public transport identifiers only. Jarvis does not infer or
store passenger/owner/crew identity from them.
"""

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
from uuid import uuid4

from jarvis_mrb.world_armor_platform import _dbpath, _instant

_KINDS = ("opensky_region", "opensky_global", "aisstream_region")
_STATES = ("active", "paused", "stopped")
_GRANTS = ("public_publisher", "api_contract", "owned_or_authorized")
_LEASE = timedelta(minutes=4)


def _enabled() -> bool:
    return (
        os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1"
        and os.getenv("JARVIS_WORLD_ARMOR_PLATFORM_ENABLED") == "1"
        and os.getenv("JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED") == "1"
    )


def _require_enabled() -> None:
    if not _enabled():
        raise RuntimeError(
            "World Armor movement is off; set WORLD_ARMOR, "
            "WORLD_ARMOR_PLATFORM and WORLD_ARMOR_MOVEMENT flags explicitly."
        )


def _id(value: str) -> str:
    try:
        if len(value) != 32 or int(value, 16) < 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("Invalid movement identifier.") from None
    return value


def _schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS movement_sources (
      id TEXT PRIMARY KEY,
      label TEXT NOT NULL,
      kind TEXT NOT NULL,
      grant_class TEXT NOT NULL,
      terms_reference TEXT NOT NULL,
      authorized_automated_access INTEGER NOT NULL CHECK(authorized_automated_access IN (0,1)),
      provider_min_interval_seconds INTEGER NOT NULL,
      cadence_seconds INTEGER NOT NULL,
      retention_days INTEGER NOT NULL,
      state TEXT NOT NULL DEFAULT 'active',
      latitude REAL,
      longitude REAL,
      radius_km REAL,
      global_scope INTEGER NOT NULL DEFAULT 0 CHECK(global_scope IN (0,1)),
      created_at TEXT NOT NULL,
      next_due_at TEXT,
      last_checked_at TEXT,
      last_outcome TEXT,
      check_count INTEGER NOT NULL DEFAULT 0,
      lease_token TEXT,
      lease_until TEXT,
      CHECK(kind IN ('opensky_region','opensky_global','aisstream_region')),
      CHECK(state IN ('active','paused','stopped')),
      CHECK(provider_min_interval_seconds>=0),
      CHECK(cadence_seconds>=0),
      CHECK(retention_days>=1)
    );
    CREATE INDEX IF NOT EXISTS ix_movement_due
      ON movement_sources(state,next_due_at,lease_until);
    CREATE TABLE IF NOT EXISTS movement_entities (
      entity_id TEXT PRIMARY KEY,
      entity_type TEXT NOT NULL,
      provider_identifier TEXT NOT NULL,
      first_seen_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL,
      last_name TEXT,
      last_callsign TEXT
    );
    CREATE TABLE IF NOT EXISTS movement_observations (
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      id TEXT NOT NULL UNIQUE,
      source_id TEXT NOT NULL REFERENCES movement_sources(id) ON DELETE CASCADE,
      entity_id TEXT NOT NULL REFERENCES movement_entities(entity_id) ON DELETE CASCADE,
      entity_type TEXT NOT NULL,
      observed_at TEXT NOT NULL,
      provider_time TEXT,
      received_at TEXT NOT NULL,
      latitude REAL NOT NULL,
      longitude REAL NOT NULL,
      altitude_m REAL,
      velocity_mps REAL,
      heading_deg REAL,
      vertical_rate_mps REAL,
      on_ground INTEGER,
      source_name TEXT NOT NULL,
      category TEXT,
      position_source TEXT,
      digest TEXT NOT NULL,
      worker_id TEXT NOT NULL DEFAULT 'windows',
      UNIQUE(source_id,digest)
    );
    CREATE INDEX IF NOT EXISTS ix_movement_entity_seq
      ON movement_observations(entity_id,seq);
    CREATE INDEX IF NOT EXISTS ix_movement_source_seq
      ON movement_observations(source_id,seq);
    CREATE INDEX IF NOT EXISTS ix_movement_received
      ON movement_observations(received_at);
    CREATE TABLE IF NOT EXISTS movement_checks (
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      source_id TEXT NOT NULL REFERENCES movement_sources(id) ON DELETE CASCADE,
      checked_at TEXT NOT NULL,
      provider_status TEXT NOT NULL,
      entities_seen INTEGER NOT NULL,
      new_observations INTEGER NOT NULL,
      error_type TEXT,
      worker_id TEXT NOT NULL DEFAULT 'windows'
    );
    CREATE INDEX IF NOT EXISTS ix_movement_checks_source
      ON movement_checks(source_id,seq);
    """)
    observation_fields = {
        row["name"] for row in con.execute(
            "PRAGMA table_info(movement_observations)"
        )
    }
    if "worker_id" not in observation_fields:
        con.execute(
            "ALTER TABLE movement_observations "
            "ADD COLUMN worker_id TEXT NOT NULL DEFAULT 'windows'"
        )
    check_fields = {
        row["name"] for row in con.execute(
            "PRAGMA table_info(movement_checks)"
        )
    }
    if "worker_id" not in check_fields:
        con.execute(
            "ALTER TABLE movement_checks "
            "ADD COLUMN worker_id TEXT NOT NULL DEFAULT 'windows'"
        )


def _connect(path: Path, *, create: bool = False) -> sqlite3.Connection:
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.exists():
        raise KeyError("World Armor movement store does not exist.")
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA secure_delete=ON")
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA journal_mode=WAL")
    if create:
        _schema(con)
    return con


def _coords(latitude: float | None, longitude: float | None,
            radius_km: float | None) -> tuple[float | None, float | None, float | None]:
    if latitude is None and longitude is None and radius_km is None:
        return None, None, None
    if latitude is None or longitude is None or radius_km is None:
        raise ValueError("Movement region requires latitude, longitude and radius.")
    try:
        lat, lon, radius = float(latitude), float(longitude), float(radius_km)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid movement region.") from exc
    if (
        not all(math.isfinite(x) for x in (lat, lon, radius))
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
        or radius <= 0
    ):
        raise ValueError("Invalid movement region.")
    return round(lat, 6), round(lon, 6), radius


def _present(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("lease_token", None)
    item.pop("lease_until", None)
    item["authorized_automated_access"] = bool(item["authorized_automated_access"])
    item["global_scope"] = bool(item["global_scope"])
    item["provider_entitlement_independently_verified"] = False
    item["person_identity_inference"] = False
    item["runner_auto_started"] = False
    return item


def enroll_source(
    *, label: str, kind: str, grant_class: str, terms_reference: str,
    authorized_automated_access: bool = False,
    provider_min_interval_seconds: int = 0,
    cadence_seconds: int = 0,
    retention_days: int = 7,
    latitude: float | None = None, longitude: float | None = None,
    radius_km: float | None = None,
    db_path: Path | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    _require_enabled()
    instant = _instant(now)
    if type(label) is not str or not 1 <= len(label.strip()) <= 200:
        raise ValueError("Movement source label required.")
    if kind not in _KINDS or grant_class not in _GRANTS:
        raise ValueError("Unsupported movement source or grant class.")
    if type(terms_reference) is not str or not 1 <= len(terms_reference.strip()) <= 700:
        raise ValueError("Record governing provider terms/permission.")
    if type(authorized_automated_access) is not bool:
        raise ValueError("Explicitly declare automated access authority.")
    if (
        type(provider_min_interval_seconds) is not int
        or provider_min_interval_seconds < 0
        or type(cadence_seconds) is not int
        or cadence_seconds < 0
        or cadence_seconds > 0
        and (
            not authorized_automated_access
            or cadence_seconds < max(provider_min_interval_seconds, 1)
        )
    ):
        raise ValueError("Movement cadence must satisfy declared source permissions.")
    if type(retention_days) is not int or retention_days < 1:
        raise ValueError("Movement retention days must be positive.")
    if kind == "opensky_global":
        if any(x is not None for x in (latitude, longitude, radius_km)):
            raise ValueError("Global OpenSky source cannot also have a local radius.")
        lat = lon = radius = None
        global_scope = 1
    else:
        lat, lon, radius = _coords(latitude, longitude, radius_km)
        global_scope = 0
        if kind == "aisstream_region" and not os.getenv("AISSTREAM_API_KEY", "").strip():
            raise ValueError("AISSTREAM_API_KEY is required for an AIS movement source.")
    key = uuid4().hex
    path = _dbpath(db_path)
    with closing(_connect(path, create=True)) as con, con:
        con.execute(
            """INSERT INTO movement_sources
               (id,label,kind,grant_class,terms_reference,
                authorized_automated_access,provider_min_interval_seconds,
                cadence_seconds,retention_days,state,latitude,longitude,
                radius_km,global_scope,created_at,next_due_at)
               VALUES(?,?,?,?,?,?,?,?,?,'active',?,?,?,?,?,?)""",
            (
                key, label.strip(), kind, grant_class,
                terms_reference.strip(), int(authorized_automated_access),
                provider_min_interval_seconds, cadence_seconds, retention_days,
                lat, lon, radius, global_scope, instant.isoformat(),
                instant.isoformat() if cadence_seconds else None,
            ),
        )
    return get_source(key, db_path=db_path)


def get_source(source_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    with closing(_connect(_dbpath(db_path))) as con:
        row = con.execute(
            "SELECT * FROM movement_sources WHERE id=?", (_id(source_id),)
        ).fetchone()
    if row is None:
        raise KeyError("Movement source does not exist.")
    return _present(row)


def list_sources(*, db_path: Path | None = None,
                 offset: int = 0, page_size: int = 100) -> dict[str, Any]:
    if type(offset) is not int or offset < 0 or type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError("Invalid movement source page.")
    path = _dbpath(db_path)
    if not path.exists():
        return {"sources": [], "next_offset": None, "total": 0,
                "global_source_count_cap": None}
    with closing(_connect(path, create=True)) as con:
        rows = con.execute(
            "SELECT * FROM movement_sources ORDER BY created_at,id LIMIT ? OFFSET ?",
            (page_size + 1, offset),
        ).fetchall()
        total = con.execute("SELECT count(*) FROM movement_sources").fetchone()[0]
    return {
        "sources": [_present(x) for x in rows[:page_size]],
        "next_offset": offset + page_size if len(rows) > page_size else None,
        "total": total,
        "global_source_count_cap": None,
    }


def transition_source(source_id: str, action: str,
                      *, db_path: Path | None = None) -> dict[str, Any]:
    if action not in ("pause", "resume", "stop"):
        raise ValueError("Choose pause, resume or stop.")
    path = _dbpath(db_path)
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM movement_sources WHERE id=?",
                          (_id(source_id),)).fetchone()
        if row is None:
            raise KeyError("Movement source absent.")
        if action == "resume":
            _require_enabled()
            if row["state"] == "stopped":
                raise ValueError("Stopped movement source must be re-enrolled.")
            state = "active"
            due = _instant().isoformat() if row["cadence_seconds"] else None
        else:
            state = "paused" if action == "pause" and row["state"] != "stopped" else "stopped"
            due = None
        con.execute(
            "UPDATE movement_sources SET state=?,next_due_at=?,"
            "lease_token=NULL,lease_until=NULL WHERE id=?",
            (state, due, source_id),
        )
    return get_source(source_id, db_path=db_path)


def forget_source(source_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    path = _dbpath(db_path)
    if not path.exists():
        return {"deleted": 0}
    with closing(_connect(path, create=True)) as con, con:
        result = con.execute(
            "DELETE FROM movement_sources WHERE id=?", (_id(source_id),)
        )
    return {"deleted": result.rowcount,
            "also_deleted": "movement observations and source check receipts"}


def _lease(source_id: str, *, path: Path, now: datetime,
           scheduled: bool) -> dict[str, Any]:
    _require_enabled()
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM movement_sources WHERE id=?",
                          (_id(source_id),)).fetchone()
        if row is None:
            raise KeyError("Movement source absent.")
        if row["state"] != "active":
            raise ValueError("Movement source paused/stopped.")
        if scheduled and (
            not row["authorized_automated_access"] or row["cadence_seconds"] <= 0
        ):
            raise ValueError("Automated movement access not authorized.")
        if scheduled and row["next_due_at"] and row["next_due_at"] > now.isoformat():
            raise ValueError("Movement source not due.")
        if row["lease_until"] and row["lease_until"] > now.isoformat():
            raise ValueError("Movement source already collecting.")
        if row["last_checked_at"] and row["provider_min_interval_seconds"] > 0:
            last = datetime.fromisoformat(row["last_checked_at"])
            if (now - last).total_seconds() < row["provider_min_interval_seconds"]:
                raise ValueError("Provider-specific minimum interval has not elapsed.")
        token = uuid4().hex
        next_due = (
            now + timedelta(seconds=row["cadence_seconds"])
            if row["cadence_seconds"] else None
        )
        con.execute(
            "UPDATE movement_sources SET lease_token=?,lease_until=?,next_due_at=? "
            "WHERE id=?",
            (token, (now + _LEASE).isoformat(),
             next_due.isoformat() if next_due else None, source_id),
        )
    return {**dict(row), "lease": token}


def _still_authorized(con: sqlite3.Connection, source: dict[str, Any],
                      now: datetime) -> bool:
    row = con.execute(
        "SELECT state,lease_token,lease_until FROM movement_sources WHERE id=?",
        (source["id"],),
    ).fetchone()
    return bool(
        row and row["state"] == "active"
        and row["lease_token"] == source["lease"]
        and row["lease_until"] and row["lease_until"] > now.isoformat()
        and _enabled()
    )


def _collect_provider(
    source: dict[str, Any], worker_id: str = "windows",
) -> dict[str, Any]:
    from jarvis_mrb.public_movement import (
        aisstream_position_burst, normalize_opensky_payload,
        opensky_state_vectors,
    )
    if worker_id == "windows":
        if source["kind"] == "opensky_global":
            return opensky_state_vectors(global_scope=True)
        if source["kind"] == "opensky_region":
            return opensky_state_vectors(
                latitude=source["latitude"], longitude=source["longitude"],
                radius_km=source["radius_km"],
            )
        if source["kind"] == "aisstream_region":
            return aisstream_position_burst(
                latitude=source["latitude"], longitude=source["longitude"],
                radius_km=source["radius_km"],
            )
        raise ValueError("Unsupported movement adapter.")
    from jarvis_mrb.reality_mesh import observer_ids
    if worker_id not in observer_ids():
        raise ValueError("Choose Windows or an explicitly registered observer.")
    if source["kind"] != "opensky_region":
        raise ValueError(
            "Paired Mac observers currently accept only regional OpenSky work."
        )
    from jarvis_mrb.reality_mesh import world_observe
    receipt = world_observe(worker_id, {
        "kind": "opensky_region",
        "latitude": source["latitude"],
        "longitude": source["longitude"],
        "radius_km": source["radius_km"],
    })
    return normalize_opensky_payload(
        receipt["provider_payload"],
        checked_at=receipt["worker_observed_at"],
        global_scope=False, authenticated=False,
    )


def _digest(source_id: str, entity: dict[str, Any]) -> str:
    payload = {
        "source": source_id,
        "entity": entity.get("entity_id"),
        "observed_at": entity.get("observed_at"),
        "lat": entity.get("latitude"),
        "lon": entity.get("longitude"),
        "altitude": entity.get("altitude_m"),
        "velocity": entity.get("velocity_mps"),
        "heading": entity.get("heading_deg"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _prune(con: sqlite3.Connection, source: dict[str, Any],
           now: datetime) -> None:
    cutoff = (now - timedelta(days=source["retention_days"])).isoformat()
    con.execute(
        "DELETE FROM movement_observations WHERE source_id=? AND received_at<?",
        (source["id"], cutoff),
    )
    con.execute(
        "DELETE FROM movement_checks WHERE source_id=? AND checked_at<?",
        (source["id"], cutoff),
    )
    con.execute(
        "DELETE FROM movement_entities WHERE entity_id NOT IN "
        "(SELECT DISTINCT entity_id FROM movement_observations)"
    )


def _fail_leased_source(
    source: dict[str, Any], *, path: Path, worker_id: str,
    now: datetime | None = None, error_type: str = "worker_or_provider_error",
) -> None:
    failed = _instant() if now is None else _instant(now)
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        current = con.execute(
            "SELECT state,lease_token FROM movement_sources WHERE id=?",
            (source["id"],),
        ).fetchone()
        if (current and current["state"] == "active"
                and current["lease_token"] == source["lease"]):
            con.execute(
                "UPDATE movement_sources SET lease_token=NULL,"
                "lease_until=NULL,last_checked_at=?,last_outcome=?,"
                "check_count=check_count+1 WHERE id=?",
                (failed.isoformat(), "worker_or_provider_error", source["id"]),
            )
            con.execute(
                "INSERT INTO movement_checks"
                "(source_id,checked_at,provider_status,entities_seen,"
                "new_observations,error_type,worker_id)"
                "VALUES(?,?,?,?,?,?,?)",
                (source["id"], failed.isoformat(), "unavailable", 0, 0,
                 error_type, worker_id),
            )
            _prune(con, source, failed)


def _persist_provider_result(
    source: dict[str, Any], result: dict[str, Any], *,
    path: Path, worker_id: str = "windows",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist one already-leased normalized provider result."""
    finish = _instant() if now is None else _instant(now)
    provider_status = str(result.get("status") or "unavailable")
    entities = result.get("entities")
    if not isinstance(entities, list):
        entities = []
        provider_status = "unavailable"
    source_id = source["id"]
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        if not _still_authorized(con, source, finish):
            return {
                "status": "revoked_or_superseded",
                "source_id": source_id, "observations_saved": 0,
                "worker_id": worker_id,
            }
        inserted = 0
        invalid = 0
        for entity in entities:
            if not isinstance(entity, dict):
                invalid += 1
                continue
            try:
                entity_id = str(entity["entity_id"])
                entity_type = str(entity["entity_type"])
                provider_identifier = str(entity["provider_identifier"])
                lat = float(entity["latitude"])
                lon = float(entity["longitude"])
                observed_at = str(entity["observed_at"])
                if (
                    entity_type not in ("aircraft", "vessel")
                    or not entity_id.startswith(("icao24:", "mmsi:"))
                    or not provider_identifier
                    or not all(math.isfinite(x) for x in (lat, lon))
                    or not -90 <= lat <= 90 or not -180 <= lon <= 180
                ):
                    raise ValueError()
                datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                invalid += 1
                continue
            digest = _digest(source_id, entity)
            prior = con.execute(
                "SELECT 1 FROM movement_observations WHERE source_id=? AND digest=?",
                (source_id, digest),
            ).fetchone()
            if prior:
                continue
            name = str(entity.get("name") or "")[:80] or None
            callsign = str(entity.get("callsign") or "")[:20] or None
            existing = con.execute(
                "SELECT 1 FROM movement_entities WHERE entity_id=?",
                (entity_id,),
            ).fetchone()
            if existing:
                con.execute(
                    "UPDATE movement_entities SET last_seen_at=?,last_name=?,"
                    "last_callsign=? WHERE entity_id=?",
                    (finish.isoformat(), name, callsign, entity_id),
                )
            else:
                con.execute(
                    "INSERT INTO movement_entities"
                    "(entity_id,entity_type,provider_identifier,first_seen_at,"
                    "last_seen_at,last_name,last_callsign) VALUES(?,?,?,?,?,?,?)",
                    (
                        entity_id, entity_type, provider_identifier,
                        finish.isoformat(), finish.isoformat(), name, callsign,
                    ),
                )

            def num(name_: str) -> float | None:
                value = entity.get(name_)
                if type(value) not in (int, float):
                    return None
                number = float(value)
                return number if math.isfinite(number) else None

            category = entity.get("category")
            position_source = entity.get("position_source")
            con.execute(
                """INSERT INTO movement_observations
                   (id,source_id,entity_id,entity_type,observed_at,provider_time,
                    received_at,latitude,longitude,altitude_m,velocity_mps,
                    heading_deg,vertical_rate_mps,on_ground,source_name,category,
                    position_source,digest,worker_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uuid4().hex, source_id, entity_id, entity_type, observed_at,
                    str(entity.get("provider_time") or "") or None,
                    finish.isoformat(), lat, lon, num("altitude_m"),
                    num("velocity_mps"), num("heading_deg"),
                    num("vertical_rate_mps"),
                    int(entity["on_ground"])
                    if type(entity.get("on_ground")) is bool else None,
                    str(entity.get("source") or source["kind"])[:80],
                    str(category)[:80] if category is not None else None,
                    str(position_source)[:80]
                    if position_source is not None else None,
                    digest, worker_id,
                ),
            )
            inserted += 1
        con.execute(
            "UPDATE movement_sources SET lease_token=NULL,lease_until=NULL,"
            "last_checked_at=?,last_outcome=?,check_count=check_count+1 WHERE id=?",
            (finish.isoformat(), provider_status, source_id),
        )
        con.execute(
            "INSERT INTO movement_checks"
            "(source_id,checked_at,provider_status,entities_seen,"
            "new_observations,error_type,worker_id) VALUES(?,?,?,?,?,?,?)",
            (
                source_id, finish.isoformat(), provider_status, len(entities),
                inserted, None if provider_status in ("ok", "partial", "stale")
                else provider_status, worker_id,
            ),
        )
        _prune(con, source, finish)
    return {
        "status": provider_status,
        "source_id": source_id,
        "entities_seen": len(entities),
        "observations_saved": inserted,
        "invalid_entities": invalid,
        "provider_checked_at": result.get("checked_at"),
        "provider_observed_at": result.get("source_observed_at"),
        "provider_note": result.get("source_note"),
        "worker_id": worker_id,
        "person_identity_inference": False,
    }


def collect_source(source_id: str, *, db_path: Path | None = None,
                   scheduled: bool = False, worker_id: str = "windows",
                   now: datetime | None = None) -> dict[str, Any]:
    start = _instant(now)
    path = _dbpath(db_path)
    if worker_id != "windows":
        from jarvis_mrb.reality_mesh import observer_ids
        if worker_id not in observer_ids():
            raise ValueError("Unknown World Armor movement worker.")
    source = _lease(source_id, path=path, now=start, scheduled=scheduled)
    try:
        result = _collect_provider(source, worker_id=worker_id)
    except Exception:
        _fail_leased_source(
            source, path=path, worker_id=worker_id, now=now
        )
        raise
    return _persist_provider_result(
        source, result, path=path, worker_id=worker_id, now=now
    )

def run_due(*, db_path: Path | None = None, limit: int = 4,
            now: datetime | None = None) -> dict[str, Any]:
    _require_enabled()
    if type(limit) is not int or limit < 1:
        raise ValueError("Movement batch size must be positive.")
    path = _dbpath(db_path)
    if not path.exists():
        return {"checks": [], "due_remaining": 0}
    instant = _instant(now)
    with closing(_connect(path, create=True)) as con:
        rows = con.execute(
            "SELECT id FROM movement_sources WHERE state='active' "
            "AND authorized_automated_access=1 AND cadence_seconds>0 "
            "AND next_due_at<=? AND (lease_until IS NULL OR lease_until<=?) "
            "ORDER BY next_due_at,id LIMIT ?",
            (instant.isoformat(), instant.isoformat(), limit),
        ).fetchall()
    outcomes = []
    for row in rows:
        try:
            outcomes.append(
                collect_source(row["id"], db_path=path,
                               scheduled=True, now=now)
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            outcomes.append({
                "source_id": row["id"], "status": "not_collected",
                "error_type": type(exc).__name__,
            })
    with closing(_connect(path, create=True)) as con:
        remaining = con.execute(
            "SELECT count(*) FROM movement_sources WHERE state='active' "
            "AND authorized_automated_access=1 AND cadence_seconds>0 "
            "AND next_due_at<=? AND (lease_until IS NULL OR lease_until<=?)",
            (instant.isoformat(), instant.isoformat()),
        ).fetchone()[0]
    return {
        "checks": outcomes, "due_remaining": remaining,
        "runner": "explicit_local_host_process_not_service_autostart",
    }


def _distance_km(a: float, b: float, c: float, d: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    value = (
        sin(radians(c - a) / 2) ** 2
        + cos(radians(a)) * cos(radians(c))
        * sin(radians(d - b) / 2) ** 2
    )
    return 6371.0088 * 2 * asin(min(1, sqrt(max(0, value))))


def nearby(
    latitude: float, longitude: float, *,
    radius_km: float = 50, entity_type: str | None = None,
    after_seq: int = 0, page_size: int = 100,
    db_path: Path | None = None,
) -> dict[str, Any]:
    try:
        lat, lon, radius = float(latitude), float(longitude), float(radius_km)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid movement query.") from exc
    if (
        not all(math.isfinite(x) for x in (lat, lon, radius))
        or not -90 <= lat <= 90 or not -180 <= lon <= 180 or radius <= 0
        or entity_type not in (None, "aircraft", "vessel")
        or type(after_seq) is not int or after_seq < 0
        or type(page_size) is not int or not 1 <= page_size <= 200
    ):
        raise ValueError("Invalid movement query.")
    path = _dbpath(db_path)
    if not path.exists():
        return {"entities": [], "next_after_seq": None}
    with closing(_connect(path, create=True)) as con:
        rows = con.execute(
            """SELECT o.*,e.last_name,e.last_callsign
               FROM movement_observations o
               JOIN movement_entities e ON e.entity_id=o.entity_id
               JOIN (
                 SELECT entity_id,MAX(seq) AS max_seq
                 FROM movement_observations GROUP BY entity_id
               ) latest ON latest.max_seq=o.seq
               WHERE o.seq>? AND (? IS NULL OR o.entity_type=?)
               ORDER BY o.seq LIMIT ?""",
            (after_seq, entity_type, entity_type, page_size * 5 + 1),
        ).fetchall()
    matches = []
    next_cursor = None
    for row in rows:
        distance = _distance_km(lat, lon, row["latitude"], row["longitude"])
        if distance <= radius:
            item = dict(row)
            item["distance_km"] = round(distance, 3)
            item["person_identity_inference"] = False
            matches.append(item)
            if len(matches) >= page_size:
                next_cursor = item["seq"]
                break
    return {
        "entities": matches,
        "next_after_seq": next_cursor,
        "query": {"latitude": lat, "longitude": lon, "radius_km": radius,
                  "entity_type": entity_type},
        "coverage": "retained enrolled movement sources only",
        "absence_means_clear": False,
    }


def track(entity_id: str, *, after_seq: int = 0, page_size: int = 200,
          db_path: Path | None = None) -> dict[str, Any]:
    if not (
        type(entity_id) is str
        and entity_id.startswith(("icao24:", "mmsi:"))
        and type(after_seq) is int and after_seq >= 0
        and type(page_size) is int and 1 <= page_size <= 500
    ):
        raise ValueError("Invalid movement track query.")
    path = _dbpath(db_path)
    if not path.exists():
        return {"entity_id": entity_id, "observations": [],
                "next_after_seq": None}
    with closing(_connect(path, create=True)) as con:
        entity = con.execute(
            "SELECT * FROM movement_entities WHERE entity_id=?", (entity_id,)
        ).fetchone()
        rows = con.execute(
            "SELECT * FROM movement_observations WHERE entity_id=? AND seq>? "
            "ORDER BY seq LIMIT ?",
            (entity_id, after_seq, page_size + 1),
        ).fetchall()
    page = [dict(x) for x in rows[:page_size]]
    return {
        "entity": dict(entity) if entity else None,
        "entity_id": entity_id,
        "observations": page,
        "next_after_seq": page[-1]["seq"] if len(rows) > page_size else None,
        "public_transport_identifier_not_person_identity": True,
        "owner_or_passenger_inference": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit operator-run World Armor movement collector"
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--interval-seconds", type=int, default=10)
    args = parser.parse_args()
    if args.limit < 1 or args.interval_seconds < 1:
        parser.error("Positive runner values required.")
    _require_enabled()
    while True:
        print(run_due(limit=args.limit), flush=True)
        if args.once:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
