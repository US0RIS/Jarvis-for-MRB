from __future__ import annotations

"""Bounded, private Reality Graph mission ledger.

Stores *normalized observations supplied by an authenticated enrolled client*.
This is not a courier/traffic-provider integration: source labels supplied by a
client are not evidence of provider authenticity. No model calls or actions.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
import secrets
import sqlite3
import threading
from typing import Any

from jarvis_mrb.world_model import APP_DIR
from jarvis_mrb.reality_graph import build_mission_graph, answer_mission_question, model_context

_LOCK = threading.RLock()
_KINDS = {"order", "courier", "traffic", "camera", "device"}
_TTL = {"order": 300, "courier": 180, "traffic": 300, "camera": 180, "device": 60}
_MAX_MISSIONS = 24
_MAX_OBSERVATIONS = 400
_MAX_BATCH = 20
_MAX_LIFETIME_HOURS = 72
_IDENT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,95}$")


class GraphUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return os.getenv("JARVIS_REALITY_GRAPH_MISSIONS_ENABLED") == "1"


def _require_enabled() -> None:
    if not enabled():
        raise GraphUnavailable("Operator must opt in to persisted Reality Graph missions.")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("An offset-aware ISO observation timestamp is required.")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid observation timestamp.") from exc
    if dt.tzinfo is None:
        raise ValueError("Observation timestamp must include timezone.")
    return dt.astimezone(timezone.utc)


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ValueError(f"{label} must be a bounded exact identifier.")
    return value


def _normalized(row: Any, *, mission_id: str, now: datetime) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("Observation must be an object.")
    kind = row.get("kind")
    if kind not in _KINDS:
        raise ValueError("Only registered observation kinds are supported.")
    observed = _stamp(row.get("observed_at"))
    age = (now - observed).total_seconds()
    if age < -30 or age > _TTL[kind]:
        raise ValueError("Observation is future-dated or stale for its source kind.")
    source = _identity(row.get("source"), "Source")
    oid = _identity(row.get("id"), "Observation id")
    if row.get("mission_id") not in (None, mission_id):
        raise ValueError("Observation belongs to another mission.")
    output: dict[str, Any] = {
        "id": oid, "mission_id": mission_id, "kind": kind, "source": source,
        "observed_at": observed.isoformat(),
        "source_attestation": "client_supplied_not_provider_verified",
    }
    # Fixed schema intentionally discards freeform claims, arbitrary metadata,
    # images, recipient identifiers and unbounded provider payloads.
    for key in ("status", "route_id", "disruption", "traffic_state", "state"):
        value = row.get(key)
        if value is not None:
            if not isinstance(value, str) or len(value) > 120:
                raise ValueError(f"{key} must be a short string.")
            if key == "route_id":
                _identity(value, "Route id")
            output[key] = value
    for key in ("delivered", "moving"):
        if key in row:
            if type(row[key]) is not bool:
                raise ValueError(f"{key} must be a boolean.")
            output[key] = row[key]
    for key in ("stationary_seconds", "delay_seconds"):
        if key in row:
            value = row[key]
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 86400:
                raise ValueError(f"{key} must be a finite duration in seconds.")
            output[key] = value
    if "eta_at" in row:
        output["eta_at"] = _stamp(row["eta_at"]).isoformat()
    return output


@contextmanager
def _db():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(APP_DIR / "reality_graph_missions.sqlite3", timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS graph_missions (
        id TEXT PRIMARY KEY, goal TEXT NOT NULL, deadline TEXT,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'active'
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS graph_observations (
        mission_id TEXT NOT NULL, id TEXT NOT NULL,
        observed_at TEXT NOT NULL, data_json TEXT NOT NULL,
        PRIMARY KEY (mission_id, id)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS graph_obs_time ON graph_observations(mission_id, observed_at)")
    db.commit()
    try:
        yield db
    finally:
        db.close()


def _prune(db: sqlite3.Connection, now: datetime) -> None:
    cutoff = (now - timedelta(hours=_MAX_LIFETIME_HOURS)).isoformat()
    db.execute("DELETE FROM graph_observations WHERE mission_id IN (SELECT id FROM graph_missions WHERE expires_at < ?)", (cutoff,))
    db.execute("DELETE FROM graph_missions WHERE expires_at < ?", (cutoff,))


def _active(row: sqlite3.Row | None, now: datetime) -> None:
    if row is None:
        raise KeyError("No such Reality Graph mission.")
    if row["state"] != "active" or _stamp(row["expires_at"]) <= now:
        raise GraphUnavailable("Mission is stopped or expired.")


def create(goal: str, *, deadline: str | None = None, lifetime_hours: int = 24) -> dict[str, Any]:
    _require_enabled()
    if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 240:
        raise ValueError("Mission goal must be 1–240 characters.")
    if type(lifetime_hours) is not int or not 1 <= lifetime_hours <= _MAX_LIFETIME_HOURS:
        raise ValueError("Mission lifetime must be 1–72 hours.")
    now = _utc()
    exact_deadline = _stamp(deadline).isoformat() if deadline is not None else None
    if exact_deadline and not now < _stamp(exact_deadline) <= now + timedelta(hours=lifetime_hours):
        raise ValueError("Deadline must fall within the mission lifetime.")
    mission_id = "rg_" + secrets.token_hex(12)
    expiry = (now + timedelta(hours=lifetime_hours)).isoformat()
    with _LOCK, _db() as db:
        _prune(db, now)
        number = db.execute("SELECT COUNT(*) FROM graph_missions WHERE state = 'active' AND expires_at > ?", (now.isoformat(),)).fetchone()[0]
        if number >= _MAX_MISSIONS:
            raise GraphUnavailable("Active mission limit reached; stop an old mission first.")
        db.execute("INSERT INTO graph_missions(id,goal,deadline,created_at,expires_at) VALUES(?,?,?,?,?)",
                   (mission_id, goal.strip(), exact_deadline, now.isoformat(), expiry))
        db.commit()
    return {"id": mission_id, "goal": goal.strip(), "deadline": exact_deadline,
            "expires_at": expiry, "state": "active", "action_authority": "none"}


def append(mission_id: str, observations: list[dict[str, Any]]) -> dict[str, Any]:
    _require_enabled()
    mid = _identity(mission_id, "Mission id")
    if type(observations) is not list or not 1 <= len(observations) <= _MAX_BATCH:
        raise ValueError("Supply 1–20 typed observations.")
    now = _utc()
    rows = [_normalized(row, mission_id=mid, now=now) for row in observations]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate observation ids in one batch.")
    with _LOCK, _db() as db:
        db.execute("BEGIN IMMEDIATE")
        mission = db.execute("SELECT * FROM graph_missions WHERE id = ?", (mid,)).fetchone()
        _active(mission, now)
        old_count = db.execute("SELECT COUNT(*) FROM graph_observations WHERE mission_id = ?", (mid,)).fetchone()[0]
        new_ids = [r["id"] for r in rows]
        existing = {
            r["id"]: r["data_json"] for r in db.execute(
                "SELECT id,data_json FROM graph_observations WHERE mission_id = ?", (mid,)
            ).fetchall() if r["id"] in new_ids
        }
        for row in rows:
            if row["id"] in existing and json.loads(existing[row["id"]]) != row:
                raise ValueError("Observation ids are immutable; conflicting replay denied.")
        if old_count + sum(r["id"] not in existing for r in rows) > _MAX_OBSERVATIONS:
            raise GraphUnavailable("Mission observation limit reached.")
        for row in rows:
            db.execute("INSERT OR IGNORE INTO graph_observations(mission_id,id,observed_at,data_json) VALUES(?,?,?,?)",
                       (mid, row["id"], row["observed_at"], json.dumps(row, separators=(",", ":"), sort_keys=True)))
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM graph_observations WHERE mission_id = ?", (mid,)).fetchone()[0]
    return {"mission_id": mid, "observations": count, "accepted": len(rows),
            "source_attestation": "client_supplied_not_provider_verified", "action_authority": "none"}


def snapshot(mission_id: str, *, question: str = "") -> dict[str, Any]:
    _require_enabled()
    mid = _identity(mission_id, "Mission id")
    now = _utc()
    with _LOCK, _db() as db:
        row = db.execute("SELECT * FROM graph_missions WHERE id = ?", (mid,)).fetchone()
        if row is None:
            raise KeyError("No such Reality Graph mission.")
        total_observations = db.execute(
            "SELECT COUNT(*) FROM graph_observations WHERE mission_id = ?", (mid,)
        ).fetchone()[0]
        observations = [
            json.loads(r["data_json"]) for r in db.execute(
                "SELECT data_json FROM graph_observations WHERE mission_id = ? ORDER BY observed_at DESC LIMIT 100",
                (mid,),
            )
        ]
    mission = {"id": row["id"], "goal": row["goal"], "deadline": row["deadline"],
               "status": "expired" if _stamp(row["expires_at"]) <= now else row["state"]}
    # The reducer processes at most 100 observations, so always select the newest
    # 100 (not the oldest 100 of a long-running mission).
    graph = build_mission_graph(mission, list(reversed(observations)), now=now)
    graph["source_attestation"] = "client_supplied_not_provider_verified"
    graph["mission_expires_at"] = row["expires_at"]
    graph["observation_count"] = total_observations
    graph["observations_reduced"] = len(observations)
    graph["observations_truncated_to_recent"] = total_observations > len(observations)
    result: dict[str, Any] = {"graph": graph, "answer": None, "model_needed": False}
    if question:
        result["answer"] = answer_mission_question(graph, question)
        if result["answer"] is None:
            result["model_needed"] = True
            result["model_context"] = model_context(graph)
    return result


def stop(mission_id: str) -> dict[str, Any]:
    _require_enabled()
    mid = _identity(mission_id, "Mission id")
    with _LOCK, _db() as db:
        row = db.execute("SELECT state FROM graph_missions WHERE id = ?", (mid,)).fetchone()
        if row is None:
            raise KeyError("No such Reality Graph mission.")
        db.execute("UPDATE graph_missions SET state = 'stopped' WHERE id = ?", (mid,))
        db.commit()
    return {"mission_id": mid, "state": "stopped", "action_authority": "none"}


def delete(mission_id: str) -> dict[str, Any]:
    """Remove mission and observation rows; does not promise SSD/WAL erasure."""
    _require_enabled()
    mid = _identity(mission_id, "Mission id")
    with _LOCK, _db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT id FROM graph_missions WHERE id = ?", (mid,)).fetchone()
        if row is None:
            raise KeyError("No such Reality Graph mission.")
        db.execute("DELETE FROM graph_observations WHERE mission_id = ?", (mid,))
        db.execute("DELETE FROM graph_missions WHERE id = ?", (mid,))
        db.commit()
    return {"mission_id": mid, "state": "deleted", "action_authority": "none"}


def list_active() -> list[dict[str, Any]]:
    """Small bounded catalogue for exact voice/status routing; no observations."""
    _require_enabled()
    with _LOCK, _db() as db:
        rows = db.execute(
            "SELECT id,goal,deadline,expires_at FROM graph_missions "
            "WHERE state = 'active' AND expires_at > ? ORDER BY created_at DESC LIMIT ?",
            (_utc().isoformat(), _MAX_MISSIONS),
        ).fetchall()
    return [{"id": r["id"], "goal": r["goal"], "deadline": r["deadline"],
             "expires_at": r["expires_at"]} for r in rows]
