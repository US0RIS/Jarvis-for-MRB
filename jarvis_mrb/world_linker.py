from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH, SELF_ID, WORLD_ID, ensure_entity, search as world_search

_GENERIC_ALIASES = {
    "user", "jarvis", "home", "away", "default", "mobile", "work", "meeting",
    "calendar", "email", "note", "document", "unknown", "unnamed",
}

# A person's mere lexical mention next to a project is not durable evidence that the
# person is actually associated with it. These roles originate from structured source
# semantics (mail sender/recipient, calendar attendee/organizer, meeting participant,
# assignment/ownership, etc.) and therefore support a person -> project relationship.
_STRONG_PERSON_PROJECT_ROLES = {
    "sender", "recipient", "attendee", "organizer", "owner", "assignee",
    "participant", "meeting_participant", "speaker", "requester", "beneficiary",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:1000]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entity_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            predicate TEXT NOT NULL,
            object_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            confidence REAL NOT NULL DEFAULT 0.5,
            state TEXT NOT NULL DEFAULT 'current',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(subject_id, predicate, object_id)
        );
        CREATE INDEX IF NOT EXISTS idx_world_relations_subject
            ON entity_relations(subject_id, state, confidence DESC);
        CREATE INDEX IF NOT EXISTS idx_world_relations_object
            ON entity_relations(object_id, state, confidence DESC);

        CREATE TABLE IF NOT EXISTS relation_evidence (
            relation_id INTEGER NOT NULL REFERENCES entity_relations(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            confidence REAL NOT NULL DEFAULT 0.5,
            explanation TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(relation_id, event_id)
        );

        CREATE TABLE IF NOT EXISTS world_linker_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def _candidate_aliases(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        """
        SELECT e.id, e.kind, a.normalized_alias
        FROM entities e
        JOIN aliases a ON a.entity_id=e.id
        WHERE e.id NOT IN (?, ?)
          AND e.kind IN ('person','project','goal','place','object','meeting','document','calendar','reminder')
        ORDER BY length(a.normalized_alias) DESC
        """,
        (SELF_ID, WORLD_ID),
    ).fetchall()
    result: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        alias = _normalize(str(row["normalized_alias"] or ""))
        if len(alias) < 3 or alias in _GENERIC_ALIASES:
            continue
        if " " not in alias and "@" not in alias and len(alias) < 4:
            continue
        key = (str(row["id"]), alias)
        if key in seen:
            continue
        seen.add(key)
        result.append((str(row["id"]), str(row["kind"]), alias))
    return result


def _explicit_project_names(raw_text: str) -> list[str]:
    """Extract only literal `Project Name` identifiers, never inferred project names."""
    result: list[str] = []
    for match in re.finditer(r"\b(?:Project|PROJECT)\s+([A-Z][A-Za-z0-9_-]{2,40})\b", raw_text):
        name = f"Project {match.group(1)}"
        if name.casefold() not in {item.casefold() for item in result}:
            result.append(name)
        if len(result) >= 8:
            break
    return result


def _mentioned(text: str, alias: str) -> bool:
    if not text or not alias:
        return False
    if "@" in alias or any(ch in alias for ch in ("/", "\\", ".")):
        return alias in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(alias)}(?![a-z0-9_])", text) is not None


def _strong_person_project_evidence(person_role: str, event_type: str) -> bool:
    role = _normalize(person_role).replace(" ", "_")
    if role in _STRONG_PERSON_PROJECT_ROLES:
        return True
    # Some source-specific roles are namespaced (for example calendar_attendee).
    if any(token in role for token in ("attendee", "organizer", "sender", "recipient", "assignee", "participant")):
        return True
    # Never infer membership from a generic textual mention, even in a conversation,
    # email body, document, or meeting transcript. Structured role evidence is needed.
    return False


def _relation_for(
    subject_kind: str,
    subject_role: str,
    object_kind: str,
    object_role: str,
    event_type: str,
) -> tuple[str, float] | None:
    sk = subject_kind
    ok = object_kind
    et = event_type.lower()

    if sk == "person" and ok == "project":
        if _strong_person_project_evidence(subject_role, event_type):
            return ("associated_with_project", 0.78)
        return None
    if sk in {"document", "calendar", "meeting"} and ok == "project":
        return ("about_project", 0.82)
    if sk == "goal" and ok == "project":
        return ("advances_project", 0.80)
    if sk in {"document", "calendar", "meeting"} and ok == "person":
        return ("involves_person", 0.78)
    if sk == "reminder" and ok in {"person", "project", "place"}:
        return ("concerns", 0.76)
    if sk == "object" and ok == "place":
        return ("observed_at", 0.88)
    if sk == "person" and ok == "place" and ("encounter" in et or "meeting" in et or "calendar" in et):
        return ("present_at", 0.72)
    if sk == "person" and ok == "person" and ("encounter" in et or "meeting" in et):
        return ("interacted_with", 0.72)
    return None


def _upsert_relation(
    conn: sqlite3.Connection,
    subject_id: str,
    predicate: str,
    object_id: str,
    confidence: float,
    event_id: int,
    explanation: str,
) -> None:
    if subject_id == object_id:
        return
    now = _now()
    row = conn.execute(
        "SELECT id,confidence,evidence_count FROM entity_relations WHERE subject_id=? AND predicate=? AND object_id=?",
        (subject_id, predicate, object_id),
    ).fetchone()
    if row is None:
        cursor = conn.execute(
            "INSERT INTO entity_relations(subject_id,predicate,object_id,confidence,state,first_seen_at,last_seen_at,evidence_count) VALUES(?,?,?,?,?,?,?,?)",
            (subject_id, predicate, object_id, confidence, "current", now, now, 0),
        )
        relation_id = int(cursor.lastrowid)
    else:
        relation_id = int(row["id"])
        old = float(row["confidence"])
        strengthened = min(0.97, max(old, confidence) + min(0.08, 0.015 * int(row["evidence_count"])))
        conn.execute(
            "UPDATE entity_relations SET confidence=?,state='current',last_seen_at=? WHERE id=?",
            (strengthened, now, relation_id),
        )

    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO relation_evidence(relation_id,event_id,confidence,explanation) VALUES(?,?,?,?)",
        (relation_id, event_id, confidence, explanation[:1000]),
    )
    if conn.total_changes > before:
        conn.execute(
            "UPDATE entity_relations SET evidence_count=evidence_count+1,last_seen_at=? WHERE id=?",
            (now, relation_id),
        )


def link_event(event_id: int) -> dict[str, int]:
    with _connect() as conn:
        event = conn.execute("SELECT * FROM events WHERE id=?", (int(event_id),)).fetchone()
        if event is None:
            return {"mentions": 0, "relations": 0, "projects_created": 0}

        payload = str(event["payload_json"] or "")
        raw_text = f"{event['summary']} {event['evidence']} {payload}"
        text = _normalize(raw_text)
        linked = {
            str(row["entity_id"]): (str(row["role"]), float(row["confidence"]))
            for row in conn.execute(
                "SELECT entity_id,role,confidence FROM event_entities WHERE event_id=?",
                (int(event_id),),
            ).fetchall()
        }

        mentions = 0
        projects_created = 0
        for project_name in _explicit_project_names(raw_text):
            project_id = ensure_entity("project", project_name, confidence=0.92)
            if project_id in linked:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO event_entities(event_id,entity_id,role,confidence) VALUES(?,?,?,?)",
                (int(event_id), project_id, "mentioned", 0.92),
            )
            linked[project_id] = ("mentioned", 0.92)
            mentions += 1
            projects_created += 1

        for entity_id, _kind, alias in _candidate_aliases(conn):
            if entity_id in linked or not _mentioned(text, alias):
                continue
            conn.execute(
                "INSERT OR IGNORE INTO event_entities(event_id,entity_id,role,confidence) VALUES(?,?,?,?)",
                (int(event_id), entity_id, "mentioned", 0.72),
            )
            linked[entity_id] = ("mentioned", 0.72)
            mentions += 1

        rows = conn.execute(
            """
            SELECT ee.entity_id,ee.role,ee.confidence,e.kind
            FROM event_entities ee
            JOIN entities e ON e.id=ee.entity_id
            WHERE ee.event_id=? AND ee.entity_id NOT IN (?,?)
            """,
            (int(event_id), SELF_ID, WORLD_ID),
        ).fetchall()

        relations_before = int(conn.execute("SELECT COUNT(*) FROM relation_evidence").fetchone()[0])
        event_type = str(event["event_type"])
        for subject in rows:
            for obj in rows:
                if str(subject["entity_id"]) == str(obj["entity_id"]):
                    continue
                relation = _relation_for(
                    str(subject["kind"]), str(subject["role"]),
                    str(obj["kind"]), str(obj["role"]), event_type,
                )
                if relation is None:
                    continue
                predicate, base_confidence = relation
                evidence_confidence = min(
                    base_confidence,
                    float(subject["confidence"]),
                    float(obj["confidence"]),
                    float(event["confidence"]),
                )
                _upsert_relation(
                    conn,
                    str(subject["entity_id"]), predicate, str(obj["entity_id"]),
                    evidence_confidence, int(event_id),
                    f"Co-occurrence in {event_type}: {str(event['summary'])[:700]}",
                )

        conn.commit()
        relations_after = int(conn.execute("SELECT COUNT(*) FROM relation_evidence").fetchone()[0])
        return {
            "mentions": mentions,
            "relations": max(0, relations_after - relations_before),
            "projects_created": projects_created,
        }


def repair_person_project_relations() -> dict[str, int]:
    """Retire legacy person/project edges that lack structured participant evidence.

    Earlier linker versions allowed a generic textual mention of a person and project
    in the same event to create `associated_with_project`. Historical source evidence
    remains untouched, but the derived relation is retired unless at least one evidence
    event contains the person in a structured strong role.
    """
    retired = 0
    retained = 0
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id,r.subject_id
            FROM entity_relations r
            JOIN entities s ON s.id=r.subject_id AND s.kind='person'
            JOIN entities o ON o.id=r.object_id AND o.kind='project'
            WHERE r.predicate='associated_with_project' AND r.state='current'
            """
        ).fetchall()
        for row in rows:
            relation_id = int(row["id"])
            person_id = str(row["subject_id"])
            evidence_rows = conn.execute(
                """
                SELECT ee.role,e.event_type
                FROM relation_evidence re
                JOIN events e ON e.id=re.event_id
                JOIN event_entities ee ON ee.event_id=e.id AND ee.entity_id=?
                WHERE re.relation_id=?
                """,
                (person_id, relation_id),
            ).fetchall()
            strong = any(
                _strong_person_project_evidence(str(item["role"]), str(item["event_type"]))
                for item in evidence_rows
            )
            if strong:
                retained += 1
                continue
            conn.execute(
                "UPDATE entity_relations SET state='retired',last_seen_at=? WHERE id=?",
                (_now(), relation_id),
            )
            retired += 1
        conn.commit()
    return {"retired": retired, "retained": retained}


def refresh_links(limit: int = 1200) -> dict[str, int]:
    safe_limit = max(1, min(int(limit), 5000))
    with _connect() as conn:
        row = conn.execute("SELECT value FROM world_linker_state WHERE key='last_event_id'").fetchone()
        last_id = int(row["value"]) if row and str(row["value"]).isdigit() else 0
        events = conn.execute(
            "SELECT id FROM events WHERE id>? ORDER BY id ASC LIMIT ?",
            (last_id, safe_limit),
        ).fetchall()

    processed = 0
    mentions = 0
    relations = 0
    projects_created = 0
    newest = last_id
    for row in events:
        event_id = int(row["id"])
        result = link_event(event_id)
        processed += 1
        mentions += int(result.get("mentions", 0))
        relations += int(result.get("relations", 0))
        projects_created += int(result.get("projects_created", 0))
        newest = event_id

    if newest != last_id:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO world_linker_state(key,value) VALUES('last_event_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(newest),),
            )
            conn.commit()

    return {
        "processed_events": processed,
        "linked_mentions": mentions,
        "relation_evidence_added": relations,
        "explicit_projects_created": projects_created,
        "last_event_id": newest,
    }


def _entity_name(conn: sqlite3.Connection, entity_id: str) -> tuple[str, str]:
    row = conn.execute("SELECT kind,canonical_name FROM entities WHERE id=?", (entity_id,)).fetchone()
    if row is None:
        return ("entity", entity_id)
    return (str(row["kind"]), str(row["canonical_name"]))


def related_entities(entity_id: str, limit: int = 12) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 40))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM entity_relations
            WHERE state='current' AND (subject_id=? OR object_id=?)
            ORDER BY confidence DESC,evidence_count DESC,last_seen_at DESC
            LIMIT ?
            """,
            (entity_id, entity_id, safe_limit),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            outbound = str(row["subject_id"]) == entity_id
            other_id = str(row["object_id"] if outbound else row["subject_id"])
            kind, name = _entity_name(conn, other_id)
            result.append(
                {
                    "direction": "out" if outbound else "in",
                    "predicate": str(row["predicate"]),
                    "entity_id": other_id,
                    "kind": kind,
                    "name": name,
                    "confidence": float(row["confidence"]),
                    "evidence_count": int(row["evidence_count"]),
                    "last_seen_at": str(row["last_seen_at"]),
                }
            )
        return result


def related_context(query: str, limit: int = 8) -> str:
    try:
        refresh_links(limit=120)
    except Exception:
        pass

    seeds = [item for item in world_search(query, limit=max(4, limit)) if item.get("type") == "entity"]
    if not seeds:
        return ""

    lines: list[str] = ["CONNECTED WORLD ENTITIES:"]
    emitted: set[tuple[str, str, str]] = set()
    for seed in seeds[:4]:
        seed_id = str(seed.get("id") or "")
        seed_name = str(seed.get("name") or seed.get("text") or seed_id)
        if not seed_id:
            continue
        for relation in related_entities(seed_id, limit=6):
            key = (seed_id, str(relation["predicate"]), str(relation["entity_id"]))
            if key in emitted:
                continue
            emitted.add(key)
            if relation["direction"] == "out":
                rendered = f"{seed_name} -> {relation['predicate']} -> {relation['name']}"
            else:
                rendered = f"{relation['name']} -> {relation['predicate']} -> {seed_name}"
            lines.append(
                f"- {rendered} (confidence {relation['confidence']:.2f}; {relation['evidence_count']} supporting event(s))"
            )
            if len(lines) >= limit + 1:
                return "\n".join(lines)

    return "\n".join(lines) if len(lines) > 1 else ""


def status() -> dict[str, Any]:
    with _connect() as conn:
        relations = int(conn.execute("SELECT COUNT(*) FROM entity_relations WHERE state='current'").fetchone()[0])
        evidence = int(conn.execute("SELECT COUNT(*) FROM relation_evidence").fetchone()[0])
        row = conn.execute("SELECT value FROM world_linker_state WHERE key='last_event_id'").fetchone()
    return {
        "relations": relations,
        "relation_evidence": evidence,
        "last_linked_event_id": int(row["value"]) if row and str(row["value"]).isdigit() else 0,
        "person_project_requires_structured_role": True,
    }
