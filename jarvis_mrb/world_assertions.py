from __future__ import annotations

"""P06-008: explicitly enrolled, observe-only desired-state assertions.

This is a small event-triggered monitor over the *client-supplied* mission ledger.
It neither invokes tools nor issues notifications; no background scheduler exists.
"""

from datetime import datetime, timezone
import json
import secrets
import sqlite3
from typing import Any

from jarvis_mrb import reality_graph_missions as missions

_SCHEMA = "jarvis.world_assertions.mission.v1"
_MAX_PER_MISSION = 12
_MAX_EVENTS = 32
_KINDS = {"order_status_equals", "route_delay_at_most", "reported_eta_before_deadline"}
_SUGGESTIONS = {
    "order_status_equals": "Review the reported order status with its source; no automatic contact or action.",
    "route_delay_at_most": "Review the route report and consider an independently authorized alternative.",
    "reported_eta_before_deadline": "Review the ETA and deadline; no automatic rescheduling or sending.",
}


def enabled() -> bool:
    import os
    return missions.enabled() and os.getenv("JARVIS_WORLD_ASSERTIONS_ENABLED") == "1"


def _require_enabled() -> None:
    if not enabled():
        raise missions.GraphUnavailable("Enable both Reality Graph missions and World Assertions explicitly.")


def _schema(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS world_assertions (
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
        definition_json TEXT NOT NULL, created_at TEXT NOT NULL,
        last_state TEXT NOT NULL DEFAULT 'unknown', checked_at TEXT
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS world_assertions_mission
        ON world_assertions(mission_id)""")
    db.execute("""CREATE TABLE IF NOT EXISTS world_assertion_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, assertion_id TEXT NOT NULL,
        checked_at TEXT NOT NULL, previous_state TEXT NOT NULL,
        state TEXT NOT NULL, evidence_json TEXT NOT NULL
    )""")


def _definition(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str) or value["kind"] not in _KINDS:
        raise ValueError("Use an explicitly supported desired-state predicate.")
    kind = value["kind"]
    if kind == "order_status_equals":
        expected = value.get("expected")
        if (set(value) != {"kind", "expected"} or not isinstance(expected, str)
                or not 1 <= len(expected) <= 80 or any(ord(c) < 32 for c in expected)):
            raise ValueError("order_status_equals requires a bounded expected status.")
    elif kind == "route_delay_at_most":
        route = value.get("route_id")
        maximum = value.get("max_seconds")
        if (set(value) != {"kind", "route_id", "max_seconds"}
                or not isinstance(route, str) or not missions._IDENT.fullmatch(route)
                or type(maximum) is not int or not 0 <= maximum <= 86400):
            raise ValueError("route_delay_at_most requires exact route_id and 0..86400 max_seconds.")
    elif set(value) != {"kind"}:
        raise ValueError("reported_eta_before_deadline accepts no extra arguments.")
    return dict(value)


def _evaluate(definition: dict[str, Any], mission: sqlite3.Row, observations: list[dict[str, Any]],
              now: datetime) -> tuple[str, dict[str, Any] | None]:
    kind = definition["kind"]
    wanted = {"order_status_equals": "order", "route_delay_at_most": "traffic",
              "reported_eta_before_deadline": "courier"}[kind]
    # Only the latest matching typed record may establish the reported state.
    # A stale latest record must never be replaced by an older, favorable one.
    relevant = [r for r in observations if r.get("kind") == wanted
                and (kind != "route_delay_at_most" or
                     r.get("route_id") == definition["route_id"])]
    if not relevant:
        return "unknown", None
    latest = max(relevant, key=lambda r: (r["observed_at"], r["id"]))
    age = (now - missions._stamp(latest["observed_at"])).total_seconds()
    if not 0 <= age <= missions._TTL[wanted]:
        return "unknown", None
    state: bool | None = None
    if kind == "order_status_equals":
        if isinstance(latest.get("status"), str):
            state = latest["status"] == definition["expected"]
    elif kind == "route_delay_at_most":
        if type(latest.get("delay_seconds")) in (int, float):
            state = latest["delay_seconds"] <= definition["max_seconds"]
    else:
        if mission["deadline"] and latest.get("eta_at"):
            state = missions._stamp(latest["eta_at"]) <= missions._stamp(mission["deadline"])
    proof = {"observation_id": latest["id"], "kind": wanted, "source": latest["source"],
             "observed_at": latest["observed_at"],
             "source_attestation": "client_supplied_not_provider_verified"}
    return ("unknown" if state is None else "met" if state else "violated"), proof


def _refresh(db: sqlite3.Connection, mission_id: str, now: datetime) -> list[dict[str, Any]]:
    _schema(db)
    mission = db.execute("SELECT * FROM graph_missions WHERE id=?", (mission_id,)).fetchone()
    missions._active(mission, now)
    rows = db.execute(
        "SELECT data_json FROM graph_observations WHERE mission_id=? ORDER BY observed_at DESC LIMIT 400",
        (mission_id,),
    ).fetchall()
    observations = [json.loads(row["data_json"]) for row in rows]
    assertions = db.execute(
        "SELECT * FROM world_assertions WHERE mission_id=? ORDER BY created_at,id",
        (mission_id,),
    ).fetchall()
    out = []
    for row in assertions:
        definition = json.loads(row["definition_json"])
        status, proof = _evaluate(definition, mission, observations, now)
        if status != row["last_state"]:
            db.execute(
                "INSERT INTO world_assertion_events(assertion_id,checked_at,previous_state,state,evidence_json) "
                "VALUES(?,?,?,?,?)",
                (row["id"], now.isoformat(), row["last_state"], status,
                 json.dumps(proof, sort_keys=True)),
            )
            db.execute(
                "DELETE FROM world_assertion_events WHERE assertion_id=? AND id NOT IN "
                "(SELECT id FROM world_assertion_events WHERE assertion_id=? ORDER BY id DESC LIMIT ?)",
                (row["id"], row["id"], _MAX_EVENTS),
            )
        db.execute("UPDATE world_assertions SET last_state=?,checked_at=? WHERE id=?",
                   (status, now.isoformat(), row["id"]))
        out.append({
            "id": row["id"], "mission_id": mission_id, "definition": definition,
            "state": status, "checked_at": now.isoformat(), "evidence": proof,
            "suggested_review": _SUGGESTIONS[definition["kind"]] if status == "violated" else None,
            "intervention_executed": False,
        })
    return out


def _on_append(db: sqlite3.Connection, mission_id: str, now: datetime) -> None:
    """Update enrolled monitors in the observation's own database transaction."""
    if not enabled():
        return
    _schema(db)
    if db.execute("SELECT 1 FROM world_assertions WHERE mission_id=? LIMIT 1", (mission_id,)).fetchone():
        _refresh(db, mission_id, now)


def enroll(mission_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    _require_enabled()
    mid = missions._identity(mission_id, "Mission id")
    desired = _definition(definition)
    now = missions._utc()
    ident = "wa_" + secrets.token_hex(12)
    with missions._LOCK, missions._db() as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        missions._active(db.execute("SELECT * FROM graph_missions WHERE id=?", (mid,)).fetchone(), now)
        count = db.execute("SELECT COUNT(*) FROM world_assertions WHERE mission_id=?", (mid,)).fetchone()[0]
        if count >= _MAX_PER_MISSION:
            raise missions.GraphUnavailable("World assertion limit reached.")
        db.execute(
            "INSERT INTO world_assertions(id,mission_id,definition_json,created_at) VALUES(?,?,?,?)",
            (ident, mid, json.dumps(desired, sort_keys=True), now.isoformat()),
        )
        entries = _refresh(db, mid, now)
        db.commit()
    return {**next(x for x in entries if x["id"] == ident), "schema": _SCHEMA,
            "action_authority": "none", "model_calls": 0}


def check(mission_id: str) -> dict[str, Any]:
    _require_enabled()
    mid = missions._identity(mission_id, "Mission id")
    now = missions._utc()
    with missions._LOCK, missions._db() as db:
        db.execute("BEGIN IMMEDIATE")
        entries = _refresh(db, mid, now)
        db.commit()
    return {"schema": _SCHEMA, "mission_id": mid, "assertions": entries,
            "checked_at": now.isoformat(), "action_authority": "none",
            "model_calls": 0, "continuous_monitoring": False,
            "trigger": "on_observation_append_or_explicit_check",
            "source_attestation": "client_supplied_not_provider_verified",
            "limitations": [
                "Only explicitly enrolled typed mission predicates; no file, flight, or arbitrary physical-device verification.",
                "No background polling, push delivery, autonomous intervention or independent provider attestation.",
                "Stale or absent evidence produces unknown, not a verified good state.",
            ]}


def history(mission_id: str, assertion_id: str) -> dict[str, Any]:
    _require_enabled()
    mid = missions._identity(mission_id, "Mission id")
    aid = missions._identity(assertion_id, "Assertion id")
    with missions._LOCK, missions._db() as db:
        _schema(db)
        missions._active(db.execute("SELECT * FROM graph_missions WHERE id=?", (mid,)).fetchone(), missions._utc())
        assertion = db.execute("SELECT id FROM world_assertions WHERE id=? AND mission_id=?",
                               (aid, mid)).fetchone()
        if assertion is None:
            raise KeyError("No such assertion for this mission.")
        events = db.execute(
            "SELECT checked_at,previous_state,state,evidence_json FROM world_assertion_events "
            "WHERE assertion_id=? ORDER BY id DESC LIMIT ?", (aid, _MAX_EVENTS),
        ).fetchall()
    return {"schema": _SCHEMA, "mission_id": mid, "assertion_id": aid,
            "transitions": [
                {"checked_at": x["checked_at"], "from": x["previous_state"],
                 "to": x["state"], "evidence": json.loads(x["evidence_json"])} for x in events
            ], "action_authority": "none"}


def revoke(mission_id: str, assertion_id: str) -> dict[str, Any]:
    _require_enabled()
    mid = missions._identity(mission_id, "Mission id")
    aid = missions._identity(assertion_id, "Assertion id")
    with missions._LOCK, missions._db() as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        missions._active(db.execute("SELECT * FROM graph_missions WHERE id=?", (mid,)).fetchone(), missions._utc())
        result = db.execute("DELETE FROM world_assertions WHERE id=? AND mission_id=?", (aid, mid))
        if result.rowcount != 1:
            raise KeyError("No such assertion for this mission.")
        db.execute("DELETE FROM world_assertion_events WHERE assertion_id=?", (aid,))
        db.commit()
    return {"mission_id": mid, "assertion_id": aid, "state": "revoked",
            "action_authority": "none"}


def _on_mission_delete(db: sqlite3.Connection, mission_id: str) -> None:
    _schema(db)
    db.execute(
        "DELETE FROM world_assertion_events WHERE assertion_id IN "
        "(SELECT id FROM world_assertions WHERE mission_id=?)", (mission_id,))
    db.execute("DELETE FROM world_assertions WHERE mission_id=?", (mission_id,))


def _on_prune(db: sqlite3.Connection, cutoff: str) -> None:
    """Discard assertion and audit rows for missions aged out by retention."""
    _schema(db)
    db.execute(
        "DELETE FROM world_assertion_events WHERE assertion_id IN "
        "(SELECT id FROM world_assertions WHERE mission_id IN "
        "(SELECT id FROM graph_missions WHERE expires_at < ?))", (cutoff,))
    db.execute(
        "DELETE FROM world_assertions WHERE mission_id IN "
        "(SELECT id FROM graph_missions WHERE expires_at < ?)", (cutoff,))
