from __future__ import annotations

"""World Armor source registry, lawful-access records, durable observation graph.

Scopes and quotas derive from the enrolled provider grant, not a global
camera-count or 72-hour-investigation rule. A user's authorization declaration
is recorded but is NOT an independent legal opinion or entitlement grant.
Observations remain receipt-timed until source capture time is proven.
"""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from jarvis_mrb import world_model
from jarvis_mrb.public_camera_media import validate_public_camera_url
from jarvis_mrb.world_armor_perception import validate_scene_goal

_KINDS = ("caltrans", "windy", "public_https")
_STATES = ("active", "paused", "stopped")
_GRANTS = ("public_publisher", "api_contract", "owned_or_authorized")
_LEASE = timedelta(minutes=3)


def _dbpath(db_path: Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else (
        Path(world_model.DB_PATH).with_name("world_armor_platform.sqlite3")
    )


def _instant(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("Use an offset-aware time.")
    return moment.astimezone(timezone.utc)


def _enabled() -> bool:
    return (os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1"
            and os.getenv("JARVIS_WORLD_ARMOR_CAMERAS_ENABLED") == "1"
            and os.getenv("JARVIS_WORLD_ARMOR_PLATFORM_ENABLED") == "1")


def _require_enabled() -> None:
    if not _enabled():
        raise RuntimeError(
            "World Armor platform is off; explicitly set its three "
            "WORLD_ARMOR, WORLD_ARMOR_CAMERAS and WORLD_ARMOR_PLATFORM flags."
        )


def _id(value: str) -> str:
    try:
        if len(value) != 32 or int(value, 16) < 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Invalid World Armor platform identifier.") from None
    return value


def _connect(path: Path, *, create: bool = False) -> sqlite3.Connection:
    if not create and not path.exists():
        raise KeyError("World Armor source registry does not exist.")
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA secure_delete=ON")
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA journal_mode=WAL")
    if create:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS source_grants (
          id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          kind TEXT NOT NULL,
          locator TEXT NOT NULL,
          source_display TEXT NOT NULL,
          grant_class TEXT NOT NULL,
          terms_reference TEXT NOT NULL,
          authorized_automated_access INTEGER NOT NULL CHECK(authorized_automated_access IN (0,1)),
          automated_min_interval_seconds INTEGER NOT NULL,
          cadence_seconds INTEGER NOT NULL,
          sample_budget INTEGER,
          check_count INTEGER NOT NULL DEFAULT 0,
          consent_expires_at TEXT,
          retention_days INTEGER NOT NULL,
          scene_goal TEXT NOT NULL DEFAULT '',
          latitude REAL,
          longitude REAL,
          spatial_basis TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL,
          next_due_at TEXT,
          last_checked_at TEXT,
          last_outcome TEXT,
          last_image_hash TEXT,
          positive_streak INTEGER NOT NULL DEFAULT 0,
          alert_armed INTEGER NOT NULL DEFAULT 1,
          lease_token TEXT,
          lease_until TEXT,
          CHECK(kind IN ('caltrans','windy','public_https')),
          CHECK(state IN ('active','paused','stopped')),
          CHECK(cadence_seconds>=0 AND automated_min_interval_seconds>=0),
          CHECK(sample_budget IS NULL OR sample_budget>0),
          CHECK(retention_days>=1)
        );
        CREATE INDEX IF NOT EXISTS ix_platform_due
          ON source_grants(state,next_due_at,lease_until);
        CREATE TABLE IF NOT EXISTS source_evidence (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          id TEXT NOT NULL UNIQUE,
          source_id TEXT NOT NULL REFERENCES source_grants(id) ON DELETE CASCADE,
          image_sha256 TEXT NOT NULL,
          description TEXT NOT NULL,
          condition_status TEXT,
          scene_goal TEXT NOT NULL,
          source_capture_at TEXT,
          retrieved_at TEXT NOT NULL,
          received_at TEXT NOT NULL,
          media_kind TEXT NOT NULL,
          model TEXT,
          source_display TEXT NOT NULL,
          geometry_basis TEXT NOT NULL,
          change_kind TEXT NOT NULL,
          adapter_mode TEXT NOT NULL DEFAULT 'real_adapter',
          source_status TEXT NOT NULL DEFAULT 'ok'
        );
        CREATE INDEX IF NOT EXISTS ix_platform_evidence_source
          ON source_evidence(source_id,seq);
        CREATE INDEX IF NOT EXISTS ix_platform_evidence_received
          ON source_evidence(received_at);
        CREATE TABLE IF NOT EXISTS source_notices (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          id TEXT NOT NULL UNIQUE,
          source_id TEXT NOT NULL REFERENCES source_grants(id) ON DELETE CASCADE,
          evidence_id TEXT NOT NULL REFERENCES source_evidence(id) ON DELETE CASCADE,
          created_at TEXT NOT NULL,
          kind TEXT NOT NULL,
          summary TEXT NOT NULL,
          read_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_platform_notice_source
          ON source_notices(source_id,seq);
        CREATE TABLE IF NOT EXISTS source_checks (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          source_id TEXT NOT NULL REFERENCES source_grants(id) ON DELETE CASCADE,
          checked_at TEXT NOT NULL,
          status TEXT NOT NULL,
          error_type TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_platform_checks_source
          ON source_checks(source_id,seq);
        """)
    return con


def _present(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("lease_token", None)
    result.pop("lease_until", None)
    # Fetchable locators remain confined to the host SQLite ledger. A direct
    # URL can include harmless query metadata; do not reflect it through the
    # iPhone API even if no recognized credential-name is present.
    result.pop("locator", None)
    result["authorized_automated_access"] = bool(result["authorized_automated_access"])
    result["alert_armed"] = bool(result["alert_armed"])
    result["capture_time_verified"] = False
    result["permission_verified_by_jarvis"] = False
    result["raw_frame_retention"] = False
    result["runner_auto_started"] = False
    return result


def _valid_coordinates(latitude: float | None,
                       longitude: float | None) -> tuple[float | None, float | None]:
    if latitude is None and longitude is None:
        return None, None
    if latitude is None or longitude is None:
        raise ValueError("Either provide both camera coordinates or neither.")
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid camera coordinates.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon) or not (
        -90 <= lat <= 90 and -180 <= lon <= 180
    ):
        raise ValueError("Invalid public-camera position.")
    return round(lat, 6), round(lon, 6)


def enroll_source(*, label: str, kind: str, locator: str,
                  grant_class: str, terms_reference: str,
                  authorized_automated_access: bool,
                  automated_min_interval_seconds: int,
                  cadence_seconds: int = 0,
                  sample_budget: int | None = None,
                  consent_expires_at: str | None = None,
                  retention_days: int = 30,
                  scene_goal: str = "",
                  latitude: float | None = None,
                  longitude: float | None = None,
                  db_path: Path | None = None,
                  now: datetime | None = None) -> dict[str, Any]:
    """Record *operator-declared* access scope; do not check remote entitlement."""
    _require_enabled()
    moment = _instant(now)
    if type(label) is not str or not 1 <= len(label.strip()) <= 200:
        raise ValueError("Source label required (1–200 characters).")
    if kind not in _KINDS:
        raise ValueError("Unsupported source adapter.")
    if grant_class not in _GRANTS:
        raise ValueError("Choose a source access class.")
    if type(terms_reference) is not str or not 1 <= len(terms_reference.strip()) <= 700:
        raise ValueError("Record the governing source permission/terms reference.")
    if type(authorized_automated_access) is not bool:
        raise ValueError("Explicitly declare whether automated access is authorized.")
    if (type(cadence_seconds) is not int or cadence_seconds < 0
            or type(automated_min_interval_seconds) is not int
            or automated_min_interval_seconds < 0
            or cadence_seconds > 0 and (
                not authorized_automated_access
                or cadence_seconds < max(1, automated_min_interval_seconds)
            )):
        raise ValueError("Polling must be explicitly authorized and satisfy source cadence.")
    if sample_budget is not None and (type(sample_budget) is not int or sample_budget <= 0):
        raise ValueError("Sample budget must be positive or unspecified.")
    if type(retention_days) is not int or retention_days < 1:
        raise ValueError("Retention days must be a positive integer.")
    goal = validate_scene_goal(scene_goal)
    expiry = None
    if consent_expires_at:
        try:
            expiry = _instant(datetime.fromisoformat(
                consent_expires_at.replace("Z", "+00:00")
            )).isoformat()
        except (ValueError, TypeError) as exc:
            raise ValueError("Consent expiry must be an aware ISO date.") from exc
        if expiry <= moment.isoformat():
            raise ValueError("Cannot enroll an already expired grant.")
    if kind == "public_https":
        loc = validate_public_camera_url(locator)
        display = loc.display
    elif kind == "caltrans":
        from jarvis_mrb.public_camera_vision import _ID
        if not _ID.fullmatch(locator):
            raise ValueError("Select a catalog-shaped Caltrans camera ID.")
        display = "Caltrans " + locator
    else:
        from jarvis_mrb.public_camera_windy import _ID
        if not _ID.fullmatch(locator):
            raise ValueError("Select a Windy webcam ID.")
        if not os.getenv("JARVIS_WINDY_WEBCAMS_API_KEY"):
            raise ValueError("Windy API key not configured on this host.")
        display = "Windy Webcams " + locator
    lat, lon = _valid_coordinates(latitude, longitude)
    if kind == "public_https" and lat is not None:
        spatial_basis = "operator_reported_camera_point_not_verified_view_cone"
    elif lat is not None:
        spatial_basis = "operator_reported_catalog_camera_point_not_verified"
    else:
        spatial_basis = "camera_geography_unverified"
    key = uuid4().hex
    with closing(_connect(_dbpath(db_path), create=True)) as con, con:
        con.execute(
            """INSERT INTO source_grants
            (id,label,kind,locator,source_display,grant_class,terms_reference,
             authorized_automated_access,automated_min_interval_seconds,
             cadence_seconds,sample_budget,consent_expires_at,retention_days,
             scene_goal,latitude,longitude,spatial_basis,state,created_at,next_due_at)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?)""",
            (key, label.strip(), kind, locator, display, grant_class,
             terms_reference.strip(), int(authorized_automated_access),
             automated_min_interval_seconds, cadence_seconds, sample_budget,
             expiry, retention_days, goal, lat, lon, spatial_basis,
             moment.isoformat(), moment.isoformat() if cadence_seconds else None),
        )
    return get_source(key, db_path=db_path)


def get_source(source_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    with closing(_connect(_dbpath(db_path))) as con:
        row = con.execute(
            "SELECT * FROM source_grants WHERE id=?", (_id(source_id),),
        ).fetchone()
    if row is None:
        raise KeyError("Public source does not exist.")
    return _present(row)


def list_sources(*, db_path: Path | None = None,
                 offset: int = 0, page_size: int = 100) -> dict[str, Any]:
    """Page size is bounded per HTTP response; total source count is not capped."""
    if type(offset) is not int or offset < 0 or type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError("Invalid page cursor or page size.")
    path = _dbpath(db_path)
    if not path.exists():
        return {"sources": [], "next_offset": None, "total": 0}
    with closing(_connect(path)) as con:
        rows = con.execute(
            "SELECT * FROM source_grants ORDER BY created_at,id LIMIT ? OFFSET ?",
            (page_size + 1, offset),
        ).fetchall()
        total = con.execute("SELECT count(*) FROM source_grants").fetchone()[0]
    return {"sources": [_present(x) for x in rows[:page_size]],
            "next_offset": offset + page_size if len(rows) > page_size else None,
            "total": total, "global_source_count_cap": None}


def transition_source(source_id: str, action: str, *,
                      db_path: Path | None = None) -> dict[str, Any]:
    if action not in ("pause", "resume", "stop"):
        raise ValueError("Choose pause, resume or stop.")
    path = _dbpath(db_path)
    with closing(_connect(path)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM source_grants WHERE id=?",
                          (_id(source_id),)).fetchone()
        if row is None:
            raise KeyError("Source does not exist.")
        if action == "resume":
            _require_enabled()
            if row["state"] == "stopped":
                raise ValueError("A stopped consent grant cannot be resurrected.")
            if (row["consent_expires_at"]
                    and row["consent_expires_at"] <= _instant().isoformat()):
                raise ValueError("Expired consent must be re-enrolled.")
            state = "active"
            due = _instant().isoformat() if row["cadence_seconds"] else None
        else:
            state = "paused" if action == "pause" and row["state"] != "stopped" else "stopped"
            due = None
        con.execute(
            "UPDATE source_grants SET state=?,next_due_at=?,"
            "lease_token=NULL,lease_until=NULL WHERE id=?",
            (state, due, source_id),
        )
    return get_source(source_id, db_path=db_path)


def forget_source(source_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    path = _dbpath(db_path)
    if not path.exists():
        return {"deleted": 0}
    with closing(_connect(path)) as con, con:
        result = con.execute(
            "DELETE FROM source_grants WHERE id=?", (_id(source_id),),
        )
    return {"deleted": result.rowcount,
            "also_deleted": "all source frames' derived text/hash, notices and check history"}


def observations(*, db_path: Path | None = None, source_id: str | None = None,
                 after_seq: int = 0, page_size: int = 100) -> dict[str, Any]:
    path = _dbpath(db_path)
    if type(after_seq) is not int or after_seq < 0 or type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError("Invalid evidence page cursor or size.")
    if not path.exists():
        return {"observations": [], "next_after_seq": None}
    with closing(_connect(path)) as con:
        if source_id is not None:
            rows = con.execute(
                "SELECT * FROM source_evidence WHERE source_id=? AND seq>? "
                "ORDER BY seq LIMIT ?", (_id(source_id), after_seq, page_size + 1),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM source_evidence WHERE seq>? ORDER BY seq LIMIT ?",
                (after_seq, page_size + 1),
            ).fetchall()
    result = [dict(x) for x in rows[:page_size]]
    return {
        "observations": result,
        "next_after_seq": result[-1]["seq"] if len(rows) > page_size else None,
        "source_time_verified": False,
        "spatial_viewing_footprint_verified": False,
        "visual_judgments": "model_observations_not_incident_confirmation",
        "raw_frames_retained": False,
    }


def notices(*, db_path: Path | None = None, source_id: str | None = None,
            after_seq: int = 0, page_size: int = 100) -> dict[str, Any]:
    path = _dbpath(db_path)
    if type(after_seq) is not int or after_seq < 0 or type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError("Invalid notice cursor or size.")
    if not path.exists():
        return {"notices": [], "next_after_seq": None}
    with closing(_connect(path)) as con:
        if source_id:
            rows = con.execute(
                "SELECT * FROM source_notices WHERE source_id=? AND seq>? "
                "ORDER BY seq LIMIT ?",
                (_id(source_id), after_seq, page_size + 1),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM source_notices WHERE seq>? ORDER BY seq LIMIT ?",
                (after_seq, page_size + 1),
            ).fetchall()
    result = [dict(x) for x in rows[:page_size]]
    return {"notices": result,
            "next_after_seq": result[-1]["seq"] if len(rows) > page_size else None,
            "remote_push": False}


def _bytes_budget(path: Path) -> None:
    """A configurable *host* disk cap, not a fixed investigation-size ceiling."""
    bound = os.getenv("JARVIS_WORLD_ARMOR_PLATFORM_MAX_DB_MB", "1024")
    try:
        megabytes = int(bound)
    except ValueError as exc:
        raise ValueError("Host database budget must be whole MB.") from exc
    if megabytes < 0:
        raise ValueError("Host database budget cannot be negative.")
    if megabytes and path.exists() and path.stat().st_size >= megabytes * 1024 * 1024:
        raise RuntimeError("Configured host storage budget reached; no source data fetched.")


def plan(*, db_path: Path | None = None, source_ids: list[str] | None = None,
         max_concurrent: int = 4) -> dict[str, Any]:
    """Deterministic preflight: state, rights, host constraints and source coverage."""
    if type(max_concurrent) is not int or max_concurrent <= 0:
        raise ValueError("Host concurrency must be positive.")
    path = _dbpath(db_path)
    if not path.exists():
        return {"sources": [], "available": 0, "unknown_coverage": True}
    with closing(_connect(path)) as con:
        rows = con.execute("SELECT * FROM source_grants ORDER BY created_at").fetchall()
    chosen = set(_id(x) for x in source_ids) if source_ids is not None else None
    if chosen is not None and chosen.difference(x["id"] for x in rows):
        raise KeyError("Plan contains an unenrolled source.")
    now = _instant().isoformat()
    results = []
    for row in rows:
        if chosen is not None and row["id"] not in chosen:
            continue
        eligible = (
            row["state"] == "active"
            and (not row["consent_expires_at"] or row["consent_expires_at"] > now)
            and (row["sample_budget"] is None
                 or row["check_count"] < row["sample_budget"])
        )
        results.append({
            "id": row["id"], "kind": row["kind"],
            "state": row["state"], "can_collect_now": bool(eligible),
            "automated_polling": bool(eligible and row["authorized_automated_access"]
                                      and row["cadence_seconds"] > 0),
            "provider_grant_class": row["grant_class"],
            "provider_terms_reference": row["terms_reference"],
            "camera_geography": row["spatial_basis"],
            "publisher_capture_time_verified": False,
            "retention_days": row["retention_days"],
            "cadence_seconds": row["cadence_seconds"],
        })
    return {
        "schema": "world_armor.source_plan.v1",
        "sources": results, "available": sum(x["can_collect_now"] for x in results),
        "automated": sum(x["automated_polling"] for x in results),
        "proposed_host_concurrency": min(max_concurrent, max(1, len(results))),
        "max_source_count": None,
        "model_calls_for_unchanged_image": 0,
        "provider_entitlement_independently_verified": False,
        "camera_coverage": "only explicitly enrolled sources",
        "remote_distributed_workers": False,
        "external_actions": 0,
    }
