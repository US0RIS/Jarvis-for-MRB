from __future__ import annotations

"""Opt-in, expiry-bounded, source-grounded external watches.

Matter scopes live in an independent local SQLite ledger; they are never sent
to remote data providers or written into the general Jarvis world model.
No watch tracks or infers the whereabouts of people.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
import threading
import uuid
from typing import Any

import jarvis_mrb.world_model as world_model

_LOCK = threading.RLock()
_KINDS = {
    "camera": (900, 86400),
    "nws_alerts": (900, 86400),
    "usgs_earthquakes": (900, 86400),
    "sec_filings": (3600, 86400),
    "airspace_region": (1800, 86400),
    "air_quality": (1800, 86400),
}
_SCOPE = re.compile(r"^(personal|matter:[A-Za-z0-9_-]{1,80})$")
_CAMERA = re.compile(r"^caltrans-d(?:[1-9]|1[0-2])-[A-Za-z0-9_-]{1,30}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


@contextmanager
def _database() -> Any:
    folder = world_model.APP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "external_watches.sqlite3", timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS watches (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            config_json TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            next_check_at TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_checked_at TEXT,
            last_status TEXT NOT NULL DEFAULT 'never_checked',
            last_digest TEXT,
            last_summary TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_external_watch_due
          ON watches(enabled,next_check_at,expires_at);
        CREATE TABLE IF NOT EXISTS watch_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id TEXT NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
            scope TEXT NOT NULL,
            observed_at TEXT,
            checked_at TEXT NOT NULL,
            status TEXT NOT NULL,
            digest TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            change_kind TEXT NOT NULL,
            UNIQUE(watch_id,digest)
        );
        CREATE INDEX IF NOT EXISTS idx_external_watch_observations
          ON watch_observations(watch_id,id DESC);
        """
    )
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _validate(scope: str, kind: str, config: dict[str, Any], cadence_seconds: int, hours: int) -> dict[str, Any]:
    if not _SCOPE.fullmatch(scope):
        raise ValueError("Scope must be 'personal' or a matter-scoped opaque identifier.")
    if kind not in _KINDS:
        raise ValueError("Unsupported public-provider watch kind.")
    least, most = _KINDS[kind]
    if not least <= cadence_seconds <= most:
        raise ValueError(f"Interval for {kind} must be {least}–{most} seconds.")
    if not 1 <= hours <= 168:
        raise ValueError("A watch must expire in 1–168 hours.")
    if kind == "camera":
        camera_id = str(config.get("camera_id") or "")
        if not _CAMERA.fullmatch(camera_id):
            raise ValueError("Camera must be selected from the official catalog.")
        return {"camera_id": camera_id}
    if kind == "sec_filings":
        from jarvis_mrb.public_diligence import normalize_cik
        return {"cik": normalize_cik(str(config.get("cik") or ""))}
    from jarvis_mrb.physical_conditions import _validate_position
    lat = float(config.get("latitude"))
    lon = float(config.get("longitude"))
    _validate_position(lat, lon)
    if kind == "airspace_region":
        radius = float(config.get("radius_km", 20))
        if not 1 <= radius <= 80:
            raise ValueError("Invalid airspace radius.")
        return {"latitude": lat, "longitude": lon, "radius_km": radius}
    if kind == "air_quality":
        threshold = float(config.get("us_aqi_threshold", 100))
        if not 1 <= threshold <= 500:
            raise ValueError("Invalid AQI threshold.")
        return {"latitude": lat, "longitude": lon, "us_aqi_threshold": threshold}
    return {"latitude": lat, "longitude": lon}


def create_watch(
    scope: str,
    kind: str,
    label: str,
    config: dict[str, Any],
    *,
    interval_seconds: int = 3600,
    expires_hours: int = 24,
) -> dict[str, Any]:
    if not 1 <= len(label.strip()) <= 120:
        raise ValueError("Watch label must contain 1–120 characters.")
    if len(json.dumps(config)) > 2000:
        raise ValueError("Watch configuration too large.")
    interval_seconds = int(interval_seconds)
    expires_hours = int(expires_hours)
    safe = _validate(scope, kind, config, interval_seconds, expires_hours)
    now = _now()
    with _LOCK, _database() as conn:
        if conn.execute(
            "SELECT count(*) FROM watches WHERE enabled=1 AND expires_at>?", (_iso(now),)
        ).fetchone()[0] >= 30:
            raise ValueError("Maximum 30 active external watches.")
        uid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO watches
            (id,scope,kind,label,config_json,interval_seconds,created_at,expires_at,next_check_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (uid, scope, kind, label.strip(), json.dumps(safe, sort_keys=True),
             interval_seconds, _iso(now), _iso(now + timedelta(hours=expires_hours)), _iso(now)),
        )
        conn.commit()
    return get_watch(uid, scope)


def _view(row: sqlite3.Row) -> dict[str, Any]:
    result = {name: row[name] for name in row.keys()}
    result["enabled"] = bool(result["enabled"])
    result["config"] = json.loads(result.pop("config_json"))
    return result


def get_watch(watch_id: str, scope: str) -> dict[str, Any]:
    if not _SCOPE.fullmatch(scope):
        raise ValueError("Invalid scope.")
    with _database() as conn:
        row = conn.execute(
            "SELECT * FROM watches WHERE id=? AND scope=?", (watch_id, scope)
        ).fetchone()
    if row is None:
        raise ValueError("No watch exists in that scope.")
    return _view(row)


def list_watches(scope: str) -> list[dict[str, Any]]:
    if not _SCOPE.fullmatch(scope):
        raise ValueError("Invalid scope.")
    with _database() as conn:
        rows = conn.execute(
            "SELECT * FROM watches WHERE scope=? ORDER BY created_at DESC LIMIT 100", (scope,)
        ).fetchall()
    return [_view(row) for row in rows]


def stop_watch(watch_id: str, scope: str) -> dict[str, Any]:
    get_watch(watch_id, scope)
    with _LOCK, _database() as conn:
        conn.execute(
            "UPDATE watches SET enabled=0 WHERE id=? AND scope=?", (watch_id, scope)
        )
        conn.commit()
    return get_watch(watch_id, scope)


def watch_history(watch_id: str, scope: str, *, limit: int = 20) -> list[dict[str, Any]]:
    get_watch(watch_id, scope)
    with _database() as conn:
        rows = conn.execute(
            "SELECT * FROM watch_observations WHERE watch_id=? AND scope=? ORDER BY id DESC LIMIT ?",
            (watch_id, scope, max(1, min(int(limit), 100))),
        ).fetchall()
    return [
        {**{k: row[k] for k in row.keys()}, "payload": json.loads(row["payload_json"])}
        for row in rows
    ]


def _fetch(row: dict[str, Any]) -> dict[str, Any]:
    kind = row["kind"]
    cfg = row["config"]
    if kind == "camera":
        from jarvis_mrb.public_camera_vision import analyze_official_still
        result = analyze_official_still(cfg["camera_id"])
        return {
            "status": "ok", "summary": result["camera_name"] + ": " + result["description"],
            "source_url": result["source_url"],
            "observed_at": result["capture_time"],
            "signature": result["description"],
            "payload": result,
        }
    if kind == "sec_filings":
        from jarvis_mrb.public_diligence import fetch_company_filings
        result = fetch_company_filings(cfg["cik"], limit=30)
        ids = sorted(f["accession"] for f in result["filings"])
        return {
            "status": "ok",
            "summary": result["registrant_name"] + ": " + str(len(ids)) + " recent SEC submissions recorded",
            "source_url": "https://data.sec.gov/submissions/CIK" + cfg["cik"] + ".json",
            "observed_at": result["checked_at"], "signature": ids,
            "payload": result,
        }
    if kind == "nws_alerts":
        from jarvis_mrb.physical_conditions import _official_alerts, _read_json, _in_nws_approximate_region, ALERT_URL
        import httpx
        if not _in_nws_approximate_region(cfg["latitude"], cfg["longitude"]):
            return {"status": "unsupported_region", "summary": "NWS not integrated for this region.", "payload": {}}
        with httpx.Client(timeout=httpx.Timeout(12), follow_redirects=False) as client:
            data = _read_json(
                client, ALERT_URL,
                params={"point": f"{cfg['latitude']:.5f},{cfg['longitude']:.5f}"},
                headers={"Accept": "application/geo+json", "User-Agent": "JarvisForMRB/0.13 (personal assistant)"},
            )
        result = _official_alerts(data, _iso(_now()))
        ids = sorted(a["id"] for a in result["alerts"])
        return {
            "status": "ok",
            "summary": str(len(ids)) + " active NWS point alerts: "
            + ", ".join(a["event"] for a in result["alerts"][:3]),
            "source_url": result["source_url"], "observed_at": result["checked_at"],
            "signature": ids, "payload": result,
        }
    if kind == "usgs_earthquakes":
        from jarvis_mrb.public_incidents import regional_earthquakes
        result = regional_earthquakes(cfg["latitude"], cfg["longitude"])
        return {
            "status": result["status"],
            "summary": str(len(result.get("events") or [])) + " recent USGS earthquakes in region",
            "source_url": result["source_url"],
            "observed_at": result["checked_at"],
            "signature": sorted(x["id"] for x in result.get("events") or []),
            "payload": result,
        }
    if kind == "airspace_region":
        from jarvis_mrb.public_airspace import airspace_region
        result = airspace_region(cfg["latitude"], cfg["longitude"], radius_km=cfg["radius_km"])
        return {
            "status": result["status"],
            "summary": str(result.get("aircraft_count")) + " aircraft reported in region",
            "source_url": result["source_url"], "observed_at": str(result.get("states_at") or ""),
            "signature": result.get("aircraft_count"), "payload": result,
        }
    if kind == "air_quality":
        from jarvis_mrb.physical_conditions import physical_conditions
        result = physical_conditions(cfg["latitude"], cfg["longitude"])
        air = result["air_quality"]
        aqi = air.get("us_aqi")
        threshold = cfg["us_aqi_threshold"]
        band = "above_threshold" if aqi is not None and aqi >= threshold else "below_threshold"
        return {
            "status": air["status"],
            "summary": "Modelled US AQI " + str(aqi) + "; alert threshold " + str(threshold),
            "source_url": air["source_url"], "observed_at": air.get("model_time_utc"),
            "signature": band, "payload": result,
        }
    raise ValueError("Unsupported watch.")


def check_watch(watch_id: str, scope: str, *, scheduled: bool = False) -> dict[str, Any]:
    with _LOCK:
        current = get_watch(watch_id, scope)
        now = _now()
        if not current["enabled"] or current["expires_at"] <= _iso(now):
            return {"status": "stopped_or_expired", "watch_id": watch_id}
        # Reserve the next run *before* remote IO. A server with multiple workers
        # should still use a single configured scheduler per deployment.
        with _database() as conn:
            conn.execute(
                "UPDATE watches SET next_check_at=? WHERE id=? AND scope=?",
                (_iso(now + timedelta(seconds=current["interval_seconds"])), watch_id, scope),
            )
            conn.commit()
    try:
        evidence = _fetch(current)
    except Exception as exc:
        evidence = {
            "status": "unavailable", "summary": "Source check failed: " + type(exc).__name__,
            "source_url": "", "payload": {"error_type": type(exc).__name__},
        }
    checked_at = _iso(_now())
    status = str(evidence.get("status") or "unavailable")
    if status not in {"ok", "partial"}:
        with _LOCK, _database() as conn:
            conn.execute(
                "UPDATE watches SET last_checked_at=?,last_status=?,last_summary=? WHERE id=? AND scope=?",
                (checked_at, status, evidence.get("summary", "")[:600], watch_id, scope),
            )
            conn.commit()
        return {"status": status, "watch_id": watch_id, "summary": evidence.get("summary", "")}

    signature = evidence.get("signature")
    digest = hashlib.sha256(json.dumps(signature, sort_keys=True, default=str).encode()).hexdigest()
    summary = str(evidence.get("summary") or "")[:600]
    payload = evidence.get("payload") or {}
    # Camera images are inspected in memory, never stored. Keep only text and
    # provider metadata in the watch ledger.
    with _LOCK, _database() as conn:
        previous = conn.execute(
            "SELECT last_digest FROM watches WHERE id=? AND scope=?", (watch_id, scope)
        ).fetchone()
        if previous is None:
            return {"status": "stopped_or_expired", "watch_id": watch_id}
        older = previous["last_digest"]
        changed = older is not None and older != digest
        change_kind = "changed" if changed else ("baseline" if older is None else "unchanged")
        conn.execute(
            "UPDATE watches SET last_digest=?,last_checked_at=?,last_status=?,last_summary=? WHERE id=? AND scope=?",
            (digest, checked_at, status, summary, watch_id, scope),
        )
        conn.execute(
            """INSERT OR IGNORE INTO watch_observations
              (watch_id,scope,observed_at,checked_at,status,digest,summary,payload_json,source_url,change_kind)
              VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (watch_id, scope, str(evidence.get("observed_at") or "")[:100],
             checked_at, status, digest, summary,
             json.dumps(payload, ensure_ascii=False, default=str)[:25000],
             str(evidence.get("source_url") or "")[:1000], change_kind),
        )
        conn.execute(
            """DELETE FROM watch_observations WHERE watch_id=? AND id NOT IN
              (SELECT id FROM watch_observations WHERE watch_id=? ORDER BY id DESC LIMIT 100)""",
            (watch_id, watch_id),
        )
        conn.commit()

    # Baselines do not alert; camera/airspace remain inspectable but never
    # claim automatic person tracking or confirmed emergencies from ML output.
    if changed and current["kind"] in {"sec_filings", "nws_alerts", "usgs_earthquakes", "air_quality"}:
        from jarvis_mrb.event_bus import emit_proactive
        safe_label = current["label"] if scope == "personal" else "matter-scoped external watch"
        emit_proactive(
            "Independent public source changed for " + safe_label
            + ". Review Jarvis's external watch evidence; this is not a legal or safety conclusion.",
            cue="attention", severity="info",
        )
    return {
        "status": status, "watch_id": watch_id,
        "change_kind": change_kind,
        "summary": summary, "source_url": evidence.get("source_url", ""),
        "checked_at": checked_at,
    }


def run_due_watches(*, limit: int = 2) -> list[dict[str, Any]]:
    now = _iso(_now())
    with _database() as conn:
        due = conn.execute(
            """SELECT id,scope FROM watches
               WHERE enabled=1 AND next_check_at<=? AND expires_at>?
               ORDER BY next_check_at LIMIT ?""",
            (now, now, max(1, min(int(limit), 5))),
        ).fetchall()
        conn.execute("UPDATE watches SET enabled=0 WHERE enabled=1 AND expires_at<=?", (now,))
        conn.commit()
    return [check_watch(str(row["id"]), str(row["scope"]), scheduled=True) for row in due]
