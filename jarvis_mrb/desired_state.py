from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


VALID_STATES = {"active", "satisfied", "blocked", "paused", "retired"}


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:2000]


def _stable_id(*parts: object) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback
    return parsed


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS desired_states (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            intention_id TEXT REFERENCES intentions(id) ON DELETE SET NULL,
            criteria_json TEXT NOT NULL DEFAULT '[]',
            authority_json TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL DEFAULT 'active',
            priority REAL NOT NULL DEFAULT 50.0,
            source_kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            blocked_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_evaluated_at TEXT,
            satisfied_at TEXT,
            generation INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_desired_states_state
            ON desired_states(state, priority DESC, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_desired_states_intention
            ON desired_states(intention_id, state);

        CREATE TABLE IF NOT EXISTS desired_state_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            desired_state_id TEXT NOT NULL REFERENCES desired_states(id) ON DELETE CASCADE,
            observed_at TEXT NOT NULL,
            satisfied INTEGER NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            missing_json TEXT NOT NULL DEFAULT '[]',
            state_before TEXT NOT NULL,
            state_after TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_desired_state_evaluations
            ON desired_state_evaluations(desired_state_id, id DESC);
        """
    )
    conn.commit()
    return conn


def _validate_criterion(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Each success criterion must be an object.")
    kind = str(raw.get("kind") or "").strip()
    criterion = dict(raw)
    criterion["kind"] = kind

    if kind in {"belief_equals", "belief_in"}:
        if not str(raw.get("entity_id") or "").strip():
            raise ValueError(f"{kind} requires entity_id.")
        if not str(raw.get("predicate") or "").strip():
            raise ValueError(f"{kind} requires predicate.")
        if kind == "belief_in":
            values = raw.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError("belief_in requires a non-empty values list.")
    elif kind == "commitment_status":
        if not str(raw.get("commitment_id") or "").strip():
            raise ValueError("commitment_status requires commitment_id.")
        if not str(raw.get("status") or "").strip():
            raise ValueError("commitment_status requires status.")
    elif kind == "entity_exists":
        if not str(raw.get("entity_id") or "").strip() and not (
            str(raw.get("kind_name") or "").strip() and str(raw.get("canonical_name") or "").strip()
        ):
            raise ValueError("entity_exists requires entity_id or kind_name + canonical_name.")
    elif kind == "event_exists":
        if not str(raw.get("event_type") or "").strip():
            raise ValueError("event_exists requires event_type.")
    else:
        raise ValueError(f"Unsupported desired-state criterion kind {kind!r}.")
    return criterion


def _validate_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("A desired state requires at least one explicit success criterion.")
    if len(criteria) > 32:
        raise ValueError("A desired state supports at most 32 success criteria.")
    return [_validate_criterion(item) for item in criteria]


def create_desired_state(
    title: str,
    criteria: list[dict[str, Any]],
    *,
    intention_id: str | None = None,
    authority: dict[str, Any] | None = None,
    priority: float = 50.0,
    source_kind: str = "user",
    source_ref: str = "",
    desired_state_id: str | None = None,
) -> dict[str, Any]:
    clean_title = " ".join(str(title or "").split())[:1000]
    if not clean_title:
        raise ValueError("Desired-state title is empty.")
    clean_criteria = _validate_criteria(criteria)
    clean_authority = dict(authority or {})
    source_ref = str(source_ref or "").strip()[:1500] or f"desired-state:{_stable_id(clean_title)[:16]}"
    state_id = str(desired_state_id or "").strip() or f"ds:{_stable_id(clean_title, source_kind, source_ref)[:32]}"
    now = _now()

    with _connect() as conn:
        if intention_id:
            row = conn.execute("SELECT 1 FROM intentions WHERE id=?", (str(intention_id),)).fetchone()
            if row is None:
                raise ValueError(f"Unknown intention {intention_id!r}.")
        existing = conn.execute("SELECT id FROM desired_states WHERE id=?", (state_id,)).fetchone()
        if existing:
            raise ValueError(f"Desired state {state_id!r} already exists.")
        conn.execute(
            """
            INSERT INTO desired_states(
                id,title,intention_id,criteria_json,authority_json,state,priority,
                source_kind,source_ref,created_at,updated_at
            ) VALUES(?,?,?,?,?,'active',?,?,?,?,?)
            """,
            (
                state_id,
                clean_title,
                str(intention_id) if intention_id else None,
                json.dumps(clean_criteria, ensure_ascii=False, sort_keys=True),
                json.dumps(clean_authority, ensure_ascii=False, sort_keys=True),
                float(priority),
                str(source_kind or "user")[:100],
                source_ref,
                now,
                now,
            ),
        )
        conn.commit()

    try:
        from jarvis_mrb.world_model import record_event
        record_event(
            "desired_state.created",
            f"Desired state created: {clean_title}",
            source_kind=source_kind,
            source_ref=f"{source_ref}:created",
            occurred_at=now,
            payload={
                "desired_state_id": state_id,
                "title": clean_title,
                "criteria": clean_criteria,
                "authority": clean_authority,
                "priority": float(priority),
            },
            evidence="Explicit desired state with machine-evaluable success criteria.",
            confidence=1.0,
        )
    except Exception:
        pass

    return get_desired_state(state_id) or {}


def _belief_value(conn: sqlite3.Connection, entity_id: str, predicate: str) -> tuple[bool, Any, int | None]:
    row = conn.execute(
        """
        SELECT id,object_id,value_json
        FROM beliefs
        WHERE subject_id=? AND predicate=? AND state='current'
        ORDER BY id DESC LIMIT 1
        """,
        (entity_id, predicate),
    ).fetchone()
    if row is None:
        return False, None, None
    if row["object_id"]:
        value: Any = str(row["object_id"])
    else:
        value = _loads(str(row["value_json"]) if row["value_json"] is not None else None, None)
    return True, value, int(row["id"])


def _equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return _normalize(actual) == _normalize(expected)
    return actual == expected


def _evaluate_criterion(conn: sqlite3.Connection, criterion: dict[str, Any]) -> dict[str, Any]:
    kind = str(criterion.get("kind") or "")
    result: dict[str, Any] = {"kind": kind, "criterion": criterion, "satisfied": False}

    if kind in {"belief_equals", "belief_in"}:
        entity_id = str(criterion.get("entity_id") or "")
        predicate = str(criterion.get("predicate") or "")
        exists, actual, belief_id = _belief_value(conn, entity_id, predicate)
        result.update({"exists": exists, "actual": actual, "belief_id": belief_id})
        if kind == "belief_equals":
            result["expected"] = criterion.get("value")
            result["satisfied"] = bool(exists and _equal(actual, criterion.get("value")))
        else:
            values = list(criterion.get("values") or [])
            result["expected"] = values
            result["satisfied"] = bool(exists and any(_equal(actual, value) for value in values))
        return result

    if kind == "commitment_status":
        commitment_id = str(criterion.get("commitment_id") or "")
        row = conn.execute("SELECT status FROM commitments WHERE id=?", (commitment_id,)).fetchone()
        actual = str(row["status"]) if row else None
        expected = str(criterion.get("status") or "")
        result.update({
            "actual": actual,
            "expected": expected,
            "satisfied": bool(row and _normalize(actual or "") == _normalize(expected)),
        })
        return result

    if kind == "entity_exists":
        entity_id = str(criterion.get("entity_id") or "").strip()
        if entity_id:
            row = conn.execute("SELECT id,kind,canonical_name FROM entities WHERE id=?", (entity_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT id,kind,canonical_name FROM entities WHERE kind=? AND lower(canonical_name)=lower(?) ORDER BY id LIMIT 1",
                (str(criterion.get("kind_name") or ""), str(criterion.get("canonical_name") or "")),
            ).fetchone()
        result.update({
            "entity_id": str(row["id"]) if row else None,
            "actual": {"kind": str(row["kind"]), "canonical_name": str(row["canonical_name"])} if row else None,
            "satisfied": bool(row),
        })
        return result

    if kind == "event_exists":
        event_type = str(criterion.get("event_type") or "")
        source_ref = str(criterion.get("source_ref") or "").strip()
        summary_contains = _normalize(str(criterion.get("summary_contains") or ""))
        sql = "SELECT id,event_type,summary,source_ref FROM events WHERE event_type=?"
        params: list[Any] = [event_type]
        if source_ref:
            sql += " AND source_ref=?"
            params.append(source_ref)
        sql += " ORDER BY id DESC LIMIT 50"
        rows = conn.execute(sql, tuple(params)).fetchall()
        match = None
        for row in rows:
            if summary_contains and summary_contains not in _normalize(str(row["summary"] or "")):
                continue
            match = row
            break
        result.update({
            "event_id": int(match["id"]) if match else None,
            "actual": str(match["summary"]) if match else None,
            "satisfied": bool(match),
        })
        return result

    result["error"] = f"Unsupported criterion kind {kind!r}."
    return result


def evaluate_desired_state(desired_state_id: str, *, persist: bool = True) -> dict[str, Any]:
    state_id = str(desired_state_id or "").strip()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM desired_states WHERE id=?", (state_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown desired state {state_id!r}.")
        criteria = _validate_criteria(list(_loads(str(row["criteria_json"]), [])))
        outcomes = [_evaluate_criterion(conn, criterion) for criterion in criteria]
        satisfied = bool(outcomes) and all(bool(item.get("satisfied")) for item in outcomes)

        before = str(row["state"])
        after = before
        if before not in {"retired", "paused", "blocked"}:
            after = "satisfied" if satisfied else "active"

        now = _now()
        if persist:
            satisfied_at = now if after == "satisfied" and before != "satisfied" else row["satisfied_at"]
            if after != "satisfied":
                satisfied_at = None
            conn.execute(
                """
                UPDATE desired_states
                SET state=?,updated_at=?,last_evaluated_at=?,satisfied_at=?
                WHERE id=?
                """,
                (after, now, now, satisfied_at, state_id),
            )
            evidence = [item for item in outcomes if item.get("satisfied")]
            missing = [item for item in outcomes if not item.get("satisfied")]
            conn.execute(
                """
                INSERT INTO desired_state_evaluations(
                    desired_state_id,observed_at,satisfied,evidence_json,missing_json,state_before,state_after
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    state_id,
                    now,
                    1 if satisfied else 0,
                    json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                    json.dumps(missing, ensure_ascii=False, sort_keys=True),
                    before,
                    after,
                ),
            )
            conn.commit()

    if persist and after != before:
        try:
            from jarvis_mrb.world_model import record_event
            record_event(
                f"desired_state.{after}",
                f"Desired state {after}: {str(row['title'])}",
                source_kind="jarvis_desired_state",
                source_ref=f"{state_id}:{after}:{now}",
                occurred_at=now,
                payload={"desired_state_id": state_id, "state_before": before, "state_after": after},
                evidence="Desired-state transition produced by machine-evaluable world criteria.",
                confidence=1.0,
            )
        except Exception:
            pass

    return {
        "id": state_id,
        "title": str(row["title"]),
        "state_before": before,
        "state": after,
        "satisfied": satisfied,
        "criteria": outcomes,
        "evidence": [item for item in outcomes if item.get("satisfied")],
        "missing": [item for item in outcomes if not item.get("satisfied")],
    }


def get_desired_state(desired_state_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM desired_states WHERE id=?", (str(desired_state_id),)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["criteria"] = list(_loads(str(item.pop("criteria_json")), []))
    item["authority"] = dict(_loads(str(item.pop("authority_json")), {}))
    return item


def list_desired_states(*, include_retired: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as conn:
        if include_retired:
            rows = conn.execute(
                "SELECT * FROM desired_states ORDER BY priority DESC,updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM desired_states WHERE state!='retired' ORDER BY priority DESC,updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["criteria"] = list(_loads(str(item.pop("criteria_json")), []))
        item["authority"] = dict(_loads(str(item.pop("authority_json")), {}))
        result.append(item)
    return result


def set_state(desired_state_id: str, state: str, *, reason: str = "") -> dict[str, Any]:
    clean_state = str(state or "").strip().lower()
    if clean_state not in VALID_STATES:
        raise ValueError(f"Invalid desired-state lifecycle state {clean_state!r}.")
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT state FROM desired_states WHERE id=?", (str(desired_state_id),)).fetchone()
        if row is None:
            raise ValueError(f"Unknown desired state {desired_state_id!r}.")
        satisfied_at = now if clean_state == "satisfied" else None
        conn.execute(
            """
            UPDATE desired_states
            SET state=?,blocked_reason=?,updated_at=?,satisfied_at=?
            WHERE id=?
            """,
            (
                clean_state,
                str(reason or "")[:2000] if clean_state == "blocked" else "",
                now,
                satisfied_at,
                str(desired_state_id),
            ),
        )
        conn.commit()
    return get_desired_state(str(desired_state_id)) or {}


def evaluations(desired_state_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM desired_state_evaluations
            WHERE desired_state_id=?
            ORDER BY id DESC LIMIT ?
            """,
            (str(desired_state_id), max(1, min(int(limit), 200))),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["satisfied"] = bool(item["satisfied"])
        item["evidence"] = list(_loads(str(item.pop("evidence_json")), []))
        item["missing"] = list(_loads(str(item.pop("missing_json")), []))
        result.append(item)
    return result


def sync_from_intentions() -> dict[str, int]:
    """Promote existing explicit Jarvis goals into Agency desired states.

    The goal entity remains the authority for whether the objective is complete.
    Agency adds the control-loop semantics; it does not create a second goal system.
    """
    try:
        from jarvis_mrb.world_executive import refresh_intentions
        refresh_intentions()
    except Exception:
        pass

    created = 0
    updated = 0
    retired = 0
    evaluated = 0
    with _connect() as conn:
        try:
            rows = conn.execute(
                """
                SELECT id,title,status,source_ref
                FROM intentions
                WHERE source_kind='explicit_goal'
                ORDER BY updated_at DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

    for row in rows:
        intention_id = str(row["id"])
        goal_id = str(row["source_ref"] or "")
        if not goal_id:
            continue
        state_id = "ds:intention:" + _stable_id(intention_id)[:24]
        intention_status = str(row["status"] or "active")
        existing = get_desired_state(state_id)

        if existing is None and intention_status == "active":
            create_desired_state(
                str(row["title"]),
                [
                    {
                        "kind": "belief_in",
                        "entity_id": goal_id,
                        "predicate": "status",
                        "values": ["completed", "done", "resolved"],
                    }
                ],
                intention_id=intention_id,
                authority={},
                priority=60.0,
                source_kind="jarvis_intention",
                source_ref=intention_id,
                desired_state_id=state_id,
            )
            created += 1
            existing = get_desired_state(state_id)

        if existing is None:
            continue

        # Keep the user-facing title and authoritative goal link current without
        # overriding an Agency pause/block decision.
        with _connect() as conn:
            conn.execute(
                "UPDATE desired_states SET title=?,intention_id=?,updated_at=? WHERE id=?",
                (str(row["title"])[:1000], intention_id, _now(), state_id),
            )
            conn.commit()
        updated += 1

        if intention_status == "retired":
            set_state(state_id, "retired")
            retired += 1
            continue

        evaluate_desired_state(state_id, persist=True)
        evaluated += 1

    return {
        "created": created,
        "updated": updated,
        "retired": retired,
        "evaluated": evaluated,
    }


def status() -> dict[str, Any]:
    with _connect() as conn:
        counts = {
            str(row["state"]): int(row["count"])
            for row in conn.execute("SELECT state,COUNT(*) AS count FROM desired_states GROUP BY state").fetchall()
        }
        evaluations_count = int(conn.execute("SELECT COUNT(*) FROM desired_state_evaluations").fetchone()[0])
    return {
        "ready": True,
        "states": counts,
        "evaluations": evaluations_count,
        "criterion_kinds": ["belief_equals", "belief_in", "commitment_status", "entity_exists", "event_exists"],
    }
