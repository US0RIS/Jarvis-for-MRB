from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:1000]


def _parse_time(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Chronos requires a non-empty ISO date/time.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Chronos date/time {text!r}.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone()


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(str(raw or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _entity_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "kind": str(row["kind"]),
        "name": str(row["canonical_name"]),
        "first_seen_at": str(row["first_seen_at"]),
        "last_seen_at": str(row["last_seen_at"]),
        "confidence": float(row["confidence"]),
    }


def resolve_entity(query: str) -> dict[str, Any]:
    clean = " ".join(str(query or "").split())
    if not clean:
        raise ValueError("Chronos entity query is empty.")
    normalized = _normalize(clean)
    conn = _connect()
    try:
        direct = conn.execute(
            "SELECT * FROM entities WHERE id=?",
            (clean,),
        ).fetchone()
        if direct is not None:
            return _entity_dict(direct)

        exact_rows = conn.execute(
            """
            SELECT DISTINCT e.*
            FROM entities e
            LEFT JOIN aliases a ON a.entity_id=e.id
            WHERE e.normalized_name=? OR a.normalized_alias=?
            ORDER BY e.confidence DESC,e.last_seen_at DESC,e.id
            """,
            (normalized, normalized),
        ).fetchall()
        if len(exact_rows) == 1:
            return _entity_dict(exact_rows[0])
        if len(exact_rows) > 1:
            raise ValueError(
                f"Chronos entity query {clean!r} is ambiguous across "
                f"{len(exact_rows)} exact matches."
            )

        pattern = f"%{normalized}%"
        partial_rows = conn.execute(
            """
            SELECT DISTINCT e.*
            FROM entities e
            LEFT JOIN aliases a ON a.entity_id=e.id
            WHERE e.normalized_name LIKE ? OR a.normalized_alias LIKE ?
            ORDER BY e.confidence DESC,e.last_seen_at DESC,e.id
            LIMIT 8
            """,
            (pattern, pattern),
        ).fetchall()
        if len(partial_rows) == 1:
            return _entity_dict(partial_rows[0])
        if not partial_rows:
            raise ValueError(f"Chronos could not resolve entity {clean!r}.")
        names = ", ".join(str(row["canonical_name"]) for row in partial_rows[:5])
        raise ValueError(
            f"Chronos entity query {clean!r} is ambiguous. Matches include: {names}."
        )
    finally:
        conn.close()


def _name_for(conn: sqlite3.Connection, entity_id: str | None) -> str:
    if not entity_id:
        return ""
    row = conn.execute(
        "SELECT canonical_name FROM entities WHERE id=?",
        (str(entity_id),),
    ).fetchone()
    return str(row["canonical_name"]) if row else str(entity_id)


def _belief_observation(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> dict[str, Any]:
    object_id = str(row["object_id"]) if row["object_id"] else ""
    value = (
        {"entity_id": object_id, "name": _name_for(conn, object_id)}
        if object_id
        else _loads(str(row["value_json"]) if row["value_json"] else None, None)
    )
    return {
        "belief_id": int(row["id"]),
        "predicate": str(row["predicate"]),
        "value": value,
        "confidence": float(row["confidence"]),
        "observed_at": str(row["observed_at"]),
        "effective_from": str(row["valid_from"] or row["observed_at"]),
        "effective_to": str(row["valid_to"] or ""),
        "record_state": str(row["state"]),
        "source_event_id": int(row["source_event_id"]) if row["source_event_id"] else None,
        "evidence": str(row["evidence"] or ""),
    }


def state_at(entity: str, at: str) -> dict[str, Any]:
    target = resolve_entity(entity)
    instant = _parse_time(at)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM beliefs
            WHERE subject_id=?
            ORDER BY observed_at,id
            """,
            (str(target["id"]),),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            effective_from = _parse_time(str(row["valid_from"] or row["observed_at"]))
            effective_to_raw = str(row["valid_to"] or "")
            effective_to = _parse_time(effective_to_raw) if effective_to_raw else None
            if effective_from > instant:
                continue
            if effective_to is not None and instant >= effective_to:
                continue
            observation = _belief_observation(conn, row)
            grouped.setdefault(str(row["predicate"]), []).append(observation)

        predicates: dict[str, dict[str, Any]] = {}
        for predicate, observations in grouped.items():
            ordered = sorted(
                observations,
                key=lambda item: (
                    float(item.get("confidence") or 0.0),
                    _parse_time(str(item.get("observed_at") or "")),
                    int(item.get("belief_id") or 0),
                ),
                reverse=True,
            )
            predicates[predicate] = {
                "preferred": ordered[0],
                "alternatives": ordered[1:],
                "uncertain": len(ordered) > 1,
            }
    finally:
        conn.close()

    return {
        "entity": target,
        "at": instant.isoformat(),
        "predicates": predicates,
        "known_predicates": len(predicates),
    }


def _event_dict(row: sqlite3.Row, roles: list[str]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "type": str(row["event_type"]),
        "occurred_at": str(row["occurred_at"]),
        "recorded_at": str(row["recorded_at"]),
        "summary": str(row["summary"]),
        "source_kind": str(row["source_kind"]),
        "source_ref": str(row["source_ref"]),
        "confidence": float(row["confidence"]),
        "roles": roles,
        "evidence": str(row["evidence"] or ""),
    }


def trace(entity: str, limit: int = 40) -> dict[str, Any]:
    target = resolve_entity(entity)
    safe_limit = max(1, min(int(limit), 200))
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT e.*
            FROM events e
            LEFT JOIN event_entities ee ON ee.event_id=e.id
            WHERE ee.entity_id=?
               OR e.id IN (
                    SELECT source_event_id
                    FROM beliefs
                    WHERE subject_id=? AND source_event_id IS NOT NULL
               )
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (str(target["id"]), str(target["id"]), max(safe_limit * 6, 100)),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            role_rows = conn.execute(
                """
                SELECT role
                FROM event_entities
                WHERE event_id=? AND entity_id=?
                ORDER BY role
                """,
                (int(row["id"]), str(target["id"])),
            ).fetchall()
            events.append(
                _event_dict(
                    row,
                    [str(item["role"]) for item in role_rows],
                )
            )
    finally:
        conn.close()

    events.sort(
        key=lambda item: (
            _parse_time(str(item["occurred_at"])),
            int(item["id"]),
        ),
        reverse=True,
    )
    return {
        "entity": target,
        "events": events[:safe_limit],
        "count": min(len(events), safe_limit),
    }


def changes(
    entity: str,
    since: str,
    until: str | None = None,
    *,
    limit: int = 80,
) -> dict[str, Any]:
    target = resolve_entity(entity)
    start = _parse_time(since)
    end = _parse_time(until) if str(until or "").strip() else datetime.now().astimezone()
    if end < start:
        raise ValueError("Chronos until must not precede since.")
    safe_limit = max(1, min(int(limit), 200))
    conn = _connect()
    try:
        belief_rows = conn.execute(
            """
            SELECT b.*,p.object_id AS previous_object_id,p.value_json AS previous_value_json,
                   p.confidence AS previous_confidence
            FROM beliefs b
            LEFT JOIN beliefs p ON p.id=b.revision_of
            WHERE b.subject_id=?
            ORDER BY b.observed_at,b.id
            """,
            (str(target["id"]),),
        ).fetchall()
        belief_changes: list[dict[str, Any]] = []
        for row in belief_rows:
            observed = _parse_time(str(row["observed_at"]))
            if observed < start or observed > end:
                continue
            current = _belief_observation(conn, row)
            previous_object_id = (
                str(row["previous_object_id"])
                if row["previous_object_id"]
                else ""
            )
            previous_value = (
                {
                    "entity_id": previous_object_id,
                    "name": _name_for(conn, previous_object_id),
                }
                if previous_object_id
                else _loads(
                    str(row["previous_value_json"])
                    if row["previous_value_json"]
                    else None,
                    None,
                )
            )
            belief_changes.append(
                {
                    "predicate": str(row["predicate"]),
                    "observed_at": str(row["observed_at"]),
                    "from": previous_value if row["revision_of"] else None,
                    "to": current["value"],
                    "confidence": float(row["confidence"]),
                    "previous_confidence": (
                        float(row["previous_confidence"])
                        if row["previous_confidence"] is not None
                        else None
                    ),
                    "source_event_id": current["source_event_id"],
                    "evidence": current["evidence"],
                    "disputed": str(row["state"]) == "disputed",
                }
            )

        event_rows = conn.execute(
            """
            SELECT DISTINCT e.*
            FROM events e
            JOIN event_entities ee ON ee.event_id=e.id
            WHERE ee.entity_id=?
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (str(target["id"]), max(safe_limit * 6, 100)),
        ).fetchall()
        events = []
        for row in event_rows:
            occurred = _parse_time(str(row["occurred_at"]))
            if occurred < start or occurred > end:
                continue
            roles = [
                str(item["role"])
                for item in conn.execute(
                    """
                    SELECT role FROM event_entities
                    WHERE event_id=? AND entity_id=?
                    ORDER BY role
                    """,
                    (int(row["id"]), str(target["id"])),
                ).fetchall()
            ]
            events.append(_event_dict(row, roles))
    finally:
        conn.close()

    belief_changes.sort(
        key=lambda item: _parse_time(str(item["observed_at"])),
        reverse=True,
    )
    events.sort(
        key=lambda item: (
            _parse_time(str(item["occurred_at"])),
            int(item["id"]),
        ),
        reverse=True,
    )
    return {
        "entity": target,
        "since": start.isoformat(),
        "until": end.isoformat(),
        "belief_changes": belief_changes[:safe_limit],
        "events": events[:safe_limit],
    }


def status() -> dict[str, Any]:
    conn = _connect()
    try:
        event_count = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        belief_count = int(conn.execute("SELECT COUNT(*) FROM beliefs").fetchone()[0])
    finally:
        conn.close()
    return {
        "ready": True,
        "shared_world_database": str(DB_PATH),
        "events": event_count,
        "beliefs": belief_count,
        "operations": ["trace", "state_at", "changes"],
        "separate_memory_store": False,
    }
