from __future__ import annotations

"""World Armor P1: one-shot, explicitly saved, evidence-backed investigations.

This module makes no requests to arbitrary URLs, installs no background runner,
does not access cameras, aircraft, AIS, private devices or user-world records,
and never turns a provider's response into a verified external outcome.
"""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from jarvis_mrb.world_model import DB_PATH

STORE = Path(DB_PATH).with_name("world_armor.sqlite3")
_MAX_REGIONS = 12
_MAX_SAMPLES = 20
_MAX_OBSERVATIONS = 1200
_PROVIDERS = ("openmeteo_model", "nws_point_alerts", "usgs_earthquakes")
_ID = re.compile(r"^[a-f0-9]{32}$")


class ArmorDisabled(RuntimeError):
    pass


def _enabled() -> bool:
    return os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1"


def _require_enabled() -> None:
    if not _enabled():
        raise ArmorDisabled("World Armor is off. Explicitly set JARVIS_WORLD_ARMOR_ENABLED=1.")


def _clock(now: datetime | None = None) -> datetime:
    result = now or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise ValueError("An offset-aware timestamp is required.")
    return result.astimezone(timezone.utc)


def _timestamp(value: Any) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _position(latitude: float, longitude: float, radius_km: float) -> tuple[float, float, float]:
    try:
        lat, lon, radius = float(latitude), float(longitude), float(radius_km)
    except (ValueError, TypeError) as exc:
        raise ValueError("A finite latitude, longitude and radius are required.") from exc
    if not all(math.isfinite(x) for x in (lat, lon, radius)):
        raise ValueError("Region values must be finite.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 1 <= radius <= 100):
        raise ValueError("Region outside the bounded Phase 1 range.")
    return round(lat, 5), round(lon, 5), round(radius, 2)


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Invalid investigation identifier.")
    return value


def _connect(path: Path, *, create: bool) -> sqlite3.Connection:
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.is_file():
        raise KeyError("No World Armor investigation store exists.")
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    if create:
        con.executescript(
            """
            PRAGMA secure_delete=ON;
            CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                radius_km REAL NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS samples (
                id TEXT PRIMARY KEY,
                investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                received_at TEXT NOT NULL,
                adapter_mode TEXT NOT NULL CHECK(adapter_mode IN ('real_adapter','fixture')),
                UNIQUE(investigation_id,received_at,adapter_mode)
            );
            CREATE TABLE IF NOT EXISTS coverage (
                sample_id TEXT NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                observation_count INTEGER NOT NULL,
                scope TEXT NOT NULL,
                PRIMARY KEY(sample_id,provider)
            );
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                sample_id TEXT NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                provider_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                observed_at TEXT,
                published_at TEXT,
                received_at TEXT NOT NULL,
                revision INTEGER NOT NULL,
                supersedes_id TEXT,
                digest TEXT NOT NULL,
                lineage TEXT NOT NULL,
                geometry_basis TEXT NOT NULL,
                values_json TEXT NOT NULL,
                UNIQUE(investigation_id,provider,provider_key,revision)
            );
            CREATE INDEX IF NOT EXISTS ix_armor_time
                ON observations(investigation_id,received_at);
            CREATE INDEX IF NOT EXISTS ix_armor_provider_revision
                ON observations(investigation_id,provider,provider_key,revision);
            CREATE INDEX IF NOT EXISTS ix_armor_sample
                ON samples(investigation_id,received_at);
            """
        )
    return con


def _prune(con: sqlite3.Connection, now: datetime) -> None:
    con.execute("DELETE FROM investigations WHERE expires_at<=?", (now.isoformat(),))


def _record(con: sqlite3.Connection, key: str, now: datetime) -> dict[str, Any]:
    row = con.execute("SELECT * FROM investigations WHERE id=?", (_identifier(key),)).fetchone()
    if row is None or row["expires_at"] <= now.isoformat():
        raise KeyError("No active investigation for this identifier.")
    return dict(row)


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def capabilities() -> dict[str, Any]:
    return {
        "schema": "jarvis.world_armor.capabilities.v1",
        "enabled": _enabled(),
        "mode": "explicit_one_shot_only",
        "source_state": "adapters_integrated_not_live_checked",
        "providers": [
            {"id": "openmeteo_model", "kind": "modelled_air_quality",
             "coverage": "global_model_not_local_sensor"},
            {"id": "nws_point_alerts", "kind": "official_point_alerts",
             "coverage": "supported_US_points_only"},
            {"id": "usgs_earthquakes", "kind": "official_regional_reports",
             "coverage": "bounded_mag_threshold_not_all_hazards"},
        ],
        "camera_collection": False, "aircraft_collection": False,
        "ais_collection": False, "scheduled_watches": False,
        "remote_workers": False, "actuation": False, "model_calls": 0,
        "store": "separate_local_expiring_sqlite",
    }


def create_investigation(label: str, latitude: float, longitude: float, *,
                         radius_km: float = 30,
                         lifetime_hours: int = 24,
                         db_path: Path | None = None,
                         now: datetime | None = None) -> dict[str, Any]:
    """Explicit enrollment of one limited region; NO provider call."""
    _require_enabled()
    title = " ".join(str(label or "").split())
    if not 1 <= len(title) <= 120 or any(ord(c) < 32 for c in title):
        raise ValueError("A bounded, printable investigation label is required.")
    lat, lon, radius = _position(latitude, longitude, radius_km)
    if not isinstance(lifetime_hours, int) or isinstance(lifetime_hours, bool) or not 1 <= lifetime_hours <= 72:
        raise ValueError("Investigation lifetime must be 1-72 hours.")
    instant = _clock(now)
    key = uuid4().hex
    with closing(_connect(Path(db_path) if db_path is not None else STORE, create=True)) as con, con:
        _prune(con, instant)
        active = con.execute("SELECT COUNT(*) FROM investigations").fetchone()[0]
        if active >= _MAX_REGIONS:
            raise ValueError("Maximum of 12 active investigations; expire or forget one.")
        expiry = (instant + timedelta(hours=lifetime_hours)).isoformat()
        con.execute(
            "INSERT INTO investigations(id,label,latitude,longitude,radius_km,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (key, title, lat, lon, radius, instant.isoformat(), expiry),
        )
    return {
        "id": key, "label": title, "latitude": lat, "longitude": lon,
        "radius_km": radius, "expires_at": expiry, "samples": 0,
        "collection": "not_started", "external_actions": 0,
    }


def list_investigations(*, db_path: Path | None = None,
                        now: datetime | None = None) -> dict[str, Any]:
    _require_enabled()
    path = Path(db_path) if db_path is not None else STORE
    if not path.is_file():
        return {"investigations": [], "setup_required": True}
    instant = _clock(now)
    with closing(_connect(path, create=False)) as con, con:
        _prune(con, instant)
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM investigations ORDER BY created_at DESC LIMIT 12"
        )]
    return {"investigations": rows, "setup_required": not rows}


def _normalized(conditions: dict[str, Any], quake: dict[str, Any], *,
                lat: float, lon: float, received: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Only trusted, structured results from fixed existing adapter functions.

    Fixture mode exercises identical normalization but is always labeled
    fixture, and is not exposed as a user-supplied-source API endpoint.
    """
    checked = received.isoformat()
    conditions = conditions if isinstance(conditions, dict) else {}
    quake = quake if isinstance(quake, dict) else {}
    air = conditions.get("air_quality")
    alerts = conditions.get("weather_alerts") if isinstance(conditions, dict) else None
    air = air if isinstance(air, dict) else {}
    alerts = alerts if isinstance(alerts, dict) else {}
    quake = quake if isinstance(quake, dict) else {}
    collected: list[dict[str, Any]] = []
    cover: list[dict[str, Any]] = []

    air_status = str(air.get("status") or "unavailable")
    model_at = _timestamp(air.get("model_time_utc"))
    reading = air.get("us_aqi")
    accepted_air = (
        air_status in {"ok", "stale"} and model_at is not None
        and type(reading) in (int, float) and math.isfinite(reading)
        and 0 <= reading <= 500
    )
    if accepted_air and _clock(received) + timedelta(seconds=30) < datetime.fromisoformat(model_at):
        accepted_air = False
        air_status = "stale"
    if accepted_air:
        collected.append({
            "provider": "openmeteo_model",
            "provider_key": f"us_aqi:{lat:.5f}:{lon:.5f}:{model_at}",
            "kind": "modelled_us_aqi", "observed_at": model_at,
            "published_at": None,
            "lineage": "openmeteo_cams_model",
            "geometry_basis": "query_point_model_grid_not_local_sensor",
            "values": {"us_aqi": round(float(reading), 1),
                       "unit": "modelled_us_aqi",
                       "note": "Coarse model, not a street-level sensor."},
        })
    cover.append({
        "provider": "openmeteo_model",
        "status": (air_status if accepted_air else
                   "unavailable" if air_status == "ok" else air_status),
        "checked_at": _timestamp(conditions.get("checked_at")) or checked,
        "count": 1 if accepted_air else 0,
        "scope": "query point; coarse model coverage",
    })

    alert_status = str(alerts.get("status") or "unavailable")
    if alert_status == "ok" and not isinstance(alerts.get("alerts"), list):
        alert_status = "unavailable"
    count = 0
    if alert_status == "ok" and isinstance(alerts.get("alerts"), list):
        for a in alerts["alerts"][:15]:
            if not isinstance(a, dict) or not str(a.get("id") or ""):
                continue
            identifier = str(a["id"])[:300]
            collected.append({
                "provider": "nws_point_alerts",
                "provider_key": identifier, "kind": "official_weather_alert",
                # The existing adapter does not expose the alert's issue time.
                "observed_at": None, "published_at": None,
                "lineage": "nws_primary_alert", "geometry_basis": "queried_point_not_alert_footprint",
                "values": {"event": str(a.get("event") or "")[:150],
                           "headline": str(a.get("headline") or "")[:280],
                           "severity": str(a.get("severity") or "Unknown")[:40],
                           "expires": _timestamp(a.get("expires"))},
            })
            count += 1
    cover.append({
        "provider": "nws_point_alerts",
        "status": alert_status if alert_status in {"ok","unavailable","unsupported_region"}
                  else "unavailable",
        "checked_at": _timestamp(alerts.get("checked_at"))
                      or _timestamp(conditions.get("checked_at")) or checked,
        "count": count, "scope": "NWS supported point only; not all-hazards",
    })

    quake_status = str(quake.get("status") or "unavailable")
    if quake_status == "ok" and not isinstance(quake.get("events"), list):
        quake_status = "unavailable"
    count = 0
    if quake_status == "ok" and isinstance(quake.get("events"), list):
        for q in quake["events"][:50]:
            if not isinstance(q, dict):
                continue
            event_time = _timestamp(q.get("occurred_at"))
            key = str(q.get("id") or "")
            mag = q.get("magnitude")
            if not key or not event_time or type(mag) not in (int, float) or not math.isfinite(mag):
                continue
            if datetime.fromisoformat(event_time) > received + timedelta(seconds=30):
                continue
            collected.append({
                "provider": "usgs_earthquakes", "provider_key": key[:70],
                "kind": "reported_earthquake", "observed_at": event_time,
                "published_at": None, "lineage": "usgs_primary_event",
                "geometry_basis": "within_queried_radius_exact_epicenter_not_in_adapter",
                "values": {
                    "magnitude": round(float(mag), 1),
                    "place": str(q.get("place") or "")[:160],
                    "reviewed": bool(q.get("reviewed")),
                    "source_url": str(q.get("source_url") or "")[:300],
                },
            })
            count += 1
    cover.append({
        "provider": "usgs_earthquakes",
        "status": quake_status if quake_status in {"ok","unavailable"} else "unavailable",
        "checked_at": _timestamp(quake.get("checked_at")) or checked,
        "count": count, "scope": "USGS within selected radius / last 24h / M>=2.5; not all incidents",
    })
    return collected, cover


def ingest_fixture(investigation_id: str, conditions: dict[str, Any],
                   earthquakes: dict[str, Any], *, db_path: Path,
                   now: datetime) -> dict[str, Any]:
    """Synthetic test hook; public API cannot submit spoofed provider results."""
    return _capture(investigation_id, conditions, earthquakes,
                    db_path=db_path, now=now, mode="fixture")


def _capture(investigation_id: str, conditions: dict[str, Any],
             earthquakes: dict[str, Any], *, db_path: Path,
             now: datetime, mode: str) -> dict[str, Any]:
    instant = _clock(now)
    _require_enabled()
    with closing(_connect(db_path, create=False)) as con, con:
        row = _record(con, investigation_id, instant)
        if row["sample_count"] >= _MAX_SAMPLES:
            raise ValueError("Investigation reached its 20-sample collection cap.")
        collected, cover = _normalized(conditions, earthquakes,
                                       lat=row["latitude"], lon=row["longitude"],
                                       received=instant)
        sample_id = uuid4().hex
        con.execute(
            "INSERT INTO samples(id,investigation_id,received_at,adapter_mode) VALUES(?,?,?,?)",
            (sample_id, investigation_id, instant.isoformat(), mode),
        )
        if len(collected) > 66:
            raise ValueError("Normalized observation budget exceeded.")
        count = 0
        for o in collected:
            digest = _digest(o["values"])
            prior = con.execute(
                "SELECT id,revision,digest FROM observations "
                "WHERE investigation_id=? AND provider=? AND provider_key=? "
                "ORDER BY revision DESC LIMIT 1",
                (investigation_id, o["provider"], o["provider_key"]),
            ).fetchone()
            # A->B->A is a new source revision, not a duplicate of ancient A.
            if prior and prior["digest"] == digest:
                continue
            con.execute(
                """INSERT INTO observations (
                     id,investigation_id,sample_id,provider,provider_key,kind,
                     observed_at,published_at,received_at,revision,supersedes_id,
                     digest,lineage,geometry_basis,values_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uuid4().hex, investigation_id, sample_id, o["provider"],
                 o["provider_key"], o["kind"], o["observed_at"], o["published_at"],
                 instant.isoformat(), int(prior["revision"])+1 if prior else 1,
                 prior["id"] if prior else None, digest, o["lineage"],
                 o["geometry_basis"], json.dumps(o["values"], sort_keys=True)),
            )
            count += 1
        for c in cover:
            con.execute(
                """INSERT INTO coverage(
                   sample_id,provider,status,checked_at,observation_count,scope
                   ) VALUES(?,?,?,?,?,?)""",
                (sample_id,c["provider"],c["status"],c["checked_at"],c["count"],c["scope"]),
            )
        con.execute("UPDATE investigations SET sample_count=sample_count+1 WHERE id=?",
                    (investigation_id,))
        total = con.execute(
            "SELECT COUNT(*) FROM observations WHERE investigation_id=?",
            (investigation_id,),
        ).fetchone()[0]
        if total > _MAX_OBSERVATIONS:
            raise ValueError("Investigation observation storage cap exceeded.")
    return {
        "sample_id": sample_id, "investigation_id": investigation_id,
        "received_at": instant.isoformat(), "mode": mode,
        "new_observations": count, "coverage": cover,
        "all_sources_available": all(c["status"] == "ok" for c in cover),
        "no_external_actions": True, "model_calls": 0,
    }


def observe_once(investigation_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    """One conscious action, three existing provider families, no scheduler."""
    _require_enabled()
    path = Path(db_path) if db_path is not None else STORE
    with closing(_connect(path, create=False)) as con:
        row = _record(con, investigation_id, _clock())
        if row["sample_count"] >= _MAX_SAMPLES:
            raise ValueError("Investigation reached its 20-sample collection cap.")
    from jarvis_mrb.physical_conditions import physical_conditions
    from jarvis_mrb.public_incidents import regional_earthquakes
    try:
        conditions = physical_conditions(row["latitude"], row["longitude"])
    except Exception:
        conditions = {"air_quality": {"status":"unavailable"},
                      "weather_alerts": {"status":"unavailable"}}
    try:
        quakes = regional_earthquakes(row["latitude"],row["longitude"],
                                      radius_km=row["radius_km"], hours=24,
                                      minimum_magnitude=2.5)
    except Exception:
        quakes = {"status": "unavailable"}
    return _capture(investigation_id, conditions, quakes,
                    db_path=path, now=_clock(), mode="real_adapter")


def replay(investigation_id: str, *, as_known_at: str | None = None,
           db_path: Path | None = None,
           now: datetime | None = None) -> dict[str, Any]:
    """History as received by Jarvis, NOT a claim about a complete real-world history."""
    _require_enabled()
    instant = _clock(now)
    cutoff = _timestamp(as_known_at) if as_known_at is not None else instant.isoformat()
    if not cutoff or cutoff > instant.isoformat():
        raise ValueError("Replay time must be offset-aware and no later than now.")
    path = Path(db_path) if db_path is not None else STORE
    with closing(_connect(path, create=False)) as con:
        item = _record(con, investigation_id, instant)
        samples = con.execute(
            "SELECT * FROM samples WHERE investigation_id=? AND received_at<=? "
            "ORDER BY received_at,id LIMIT 20", (investigation_id, cutoff)
        ).fetchall()
        obs = con.execute(
            "SELECT * FROM observations WHERE investigation_id=? AND received_at<=? "
            "ORDER BY received_at,revision,id LIMIT 1200", (investigation_id, cutoff)
        ).fetchall()
        cover = con.execute(
            """SELECT s.received_at,s.adapter_mode,c.*
               FROM coverage c JOIN samples s ON s.id=c.sample_id
               WHERE s.investigation_id=? AND s.received_at<=?
               ORDER BY s.received_at,s.id""", (investigation_id, cutoff)
        ).fetchall()
    last_cover: dict[str, dict[str, Any]] = {}
    for row in cover:
        last_cover[row["provider"]] = {
            "source": row["provider"], "status": row["status"],
            "checked_at": row["checked_at"], "received_at": row["received_at"],
            "reported_count": row["observation_count"],
            "scope": row["scope"], "adapter_mode": row["adapter_mode"],
        }
    visible: dict[tuple[str,str], dict[str, Any]] = {}
    revision_history: list[dict[str, Any]] = []
    for row in obs:
        entry = {
            "id":row["id"],"source":row["provider"],
            "provider_key":row["provider_key"],"kind":row["kind"],
            "observed_at":row["observed_at"],"published_at":row["published_at"],
            "received_at":row["received_at"],"revision":row["revision"],
            "supersedes_id":row["supersedes_id"],"digest":row["digest"],
            "lineage":row["lineage"],"geometry_basis":row["geometry_basis"],
            "values":json.loads(row["values_json"]),
        }
        visible[(row["provider"],row["provider_key"])] = entry
        if row["supersedes_id"]:
            revision_history.append({
                "provider":row["provider"],"provider_key":row["provider_key"],
                "revision":row["revision"],"supersedes_id":row["supersedes_id"],
                "new_id":row["id"],"received_at":row["received_at"],
            })
    observations = sorted(visible.values(),key=lambda x:(x["source"],x["provider_key"]))
    available = all(c["status"]=="ok" for c in last_cover.values()) and len(last_cover)==len(_PROVIDERS)
    modes = sorted({row["adapter_mode"] for row in samples})
    return {
        "schema":"jarvis.world_armor.replay.v1",
        "investigation":{"id":item["id"],"label":item["label"],
                         "latitude":item["latitude"],"longitude":item["longitude"],
                         "radius_km":item["radius_km"],"expires_at":item["expires_at"]},
        "as_known_at":cutoff, "samples_retained":len(samples),
        "observation_count":len(observations),"observations":observations,
        "revisions":revision_history[:1200],"coverage":last_cover,
        "coverage_complete_for_integrated_sources":available,
        "mode": ("fixture_only" if modes==["fixture"] else
                 "real_adapter_only" if modes==["real_adapter"] else
                 "mixed" if modes else "no_samples"),
        "unknown_is_not_all_clear":True,"model_calls":0,"external_actions":0,
    }


def forget(investigation_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    """Forget even while disabled, so revocation cannot lock users out of deletion."""
    path = Path(db_path) if db_path is not None else STORE
    if not path.is_file():
        return {"deleted": 0}
    with closing(_connect(path, create=False)) as con, con:
        con.execute("PRAGMA secure_delete=ON")
        cursor = con.execute("DELETE FROM investigations WHERE id=?",
                             (_identifier(investigation_id),))
        return {"deleted": cursor.rowcount,
                "qualifier":"Live SQLite rows; backups and external provider records not erased."}
