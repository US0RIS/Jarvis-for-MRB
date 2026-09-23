from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:1000]


def _loads(value: str | None, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS intentions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            next_action TEXT NOT NULL DEFAULT '',
            due_at TEXT,
            confidence REAL NOT NULL DEFAULT 1.0,
            source_kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_world_intentions_status
            ON intentions(status, due_at, updated_at DESC);

        CREATE TABLE IF NOT EXISTS intention_entities (
            intention_id TEXT NOT NULL REFERENCES intentions(id) ON DELETE CASCADE,
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY(intention_id, entity_id, role)
        );
        CREATE INDEX IF NOT EXISTS idx_world_intention_entities_entity
            ON intention_entities(entity_id, intention_id);

        CREATE TABLE IF NOT EXISTS intention_commitments (
            intention_id TEXT NOT NULL REFERENCES intentions(id) ON DELETE CASCADE,
            commitment_id TEXT NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'related',
            confidence REAL NOT NULL DEFAULT 0.7,
            PRIMARY KEY(intention_id, commitment_id)
        );
        CREATE INDEX IF NOT EXISTS idx_world_intention_commitments_commitment
            ON intention_commitments(commitment_id, intention_id);
        """
    )
    conn.commit()
    return conn


def _current_belief(conn: sqlite3.Connection, entity_id: str, predicate: str, default: Any = None) -> Any:
    row = conn.execute(
        "SELECT object_id,value_json FROM beliefs WHERE subject_id=? AND predicate=? AND state='current' ORDER BY id DESC LIMIT 1",
        (entity_id, predicate),
    ).fetchone()
    if row is None:
        return default
    if row["object_id"]:
        return str(row["object_id"])
    return _loads(str(row["value_json"]) if row["value_json"] is not None else None, default)


def _entity_name(conn: sqlite3.Connection, entity_id: str | None) -> str:
    if not entity_id:
        return ""
    row = conn.execute("SELECT canonical_name FROM entities WHERE id=?", (entity_id,)).fetchone()
    return str(row["canonical_name"]) if row else str(entity_id)


def _aliases(conn: sqlite3.Connection, entity_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT normalized_alias FROM aliases WHERE entity_id=? ORDER BY length(normalized_alias) DESC",
        (entity_id,),
    ).fetchall()
    return [str(row["normalized_alias"]) for row in rows if len(str(row["normalized_alias"])) >= 3]


def _text_mentions(text: str, aliases: list[str]) -> bool:
    normalized = _normalize(text)
    for alias in aliases:
        if "@" in alias or "." in alias:
            if alias in normalized:
                return True
            continue
        if re.search(rf"(?<![a-z0-9_]){re.escape(alias)}(?![a-z0-9_])", normalized):
            return True
    return False


def _intention_status(goal_status: str) -> str:
    normalized = _normalize(goal_status).replace(" ", "_")
    if normalized in {"completed", "done", "resolved"}:
        return "completed"
    if normalized in {"retired", "deleted", "removed", "cancelled", "canceled", "inactive"}:
        return "retired"
    return "active"


def _unambiguous_owner_project_link(
    conn: sqlite3.Connection,
    owner_id: str,
    project_ids: list[str],
) -> tuple[bool, float]:
    """Use structured owner→project evidence only when it is unambiguous.

    A Waiting-On item such as "final funds-flow memo" may omit the project name even
    when Jarvis has structured evidence that its owner participates in that project.
    We may bridge that gap only when the owner has exactly one current strong project
    association in the world and it is one of this intention's project entities. If
    there are multiple current project associations, ambiguity wins and Jarvis does
    not guess.
    """
    if not owner_id or not project_ids:
        return False, 0.0
    rows = conn.execute(
        """
        SELECT r.object_id,r.confidence
        FROM entity_relations r
        JOIN entities e ON e.id=r.object_id AND e.kind='project'
        WHERE r.subject_id=?
          AND r.predicate='associated_with_project'
          AND r.state='current'
          AND r.confidence>=0.75
        ORDER BY r.confidence DESC,r.object_id
        """,
        (owner_id,),
    ).fetchall()
    by_project: dict[str, float] = {}
    for row in rows:
        project_id = str(row["object_id"])
        by_project[project_id] = max(by_project.get(project_id, 0.0), float(row["confidence"]))
    if len(by_project) != 1:
        return False, 0.0
    only_project, relation_confidence = next(iter(by_project.items()))
    if only_project not in set(project_ids):
        return False, 0.0
    return True, min(0.78, relation_confidence)


def refresh_intentions() -> dict[str, int]:
    now = _now()
    upserted = 0
    linked_entities = 0
    linked_commitments = 0

    with _connect() as conn:
        goals = conn.execute("SELECT id,canonical_name,first_seen_at FROM entities WHERE kind='goal'").fetchall()

        for goal in goals:
            goal_id = str(goal["id"])
            goal_status = str(_current_belief(conn, goal_id, "status", "active") or "active")
            next_action = str(_current_belief(conn, goal_id, "next_action", "") or "")[:1500]
            due_at = _current_belief(conn, goal_id, "due_at", None)
            intention_id = f"goal:{goal_id}"
            clean_status = _intention_status(goal_status)

            existing = conn.execute("SELECT created_at FROM intentions WHERE id=?", (intention_id,)).fetchone()
            created = str(existing["created_at"]) if existing else str(goal["first_seen_at"] or now)
            conn.execute(
                """
                INSERT INTO intentions(id,title,status,next_action,due_at,confidence,source_kind,source_ref,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    next_action=excluded.next_action,
                    due_at=excluded.due_at,
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
                """,
                (
                    intention_id,
                    str(goal["canonical_name"]),
                    clean_status,
                    next_action,
                    str(due_at) if due_at else None,
                    1.0,
                    "explicit_goal",
                    goal_id,
                    created,
                    now,
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO intention_entities(intention_id,entity_id,role,confidence) VALUES(?,?,?,?)",
                (intention_id, goal_id, "goal", 1.0),
            )
            # Project links are a materialized view of current evidence. Rebuild them
            # each refresh so an old project association cannot survive after its
            # underlying relation is retired or corrected.
            conn.execute(
                "DELETE FROM intention_entities WHERE intention_id=? AND role='project'",
                (intention_id,),
            )
            upserted += 1

            # Only active intentions should acquire current project/dependency links.
            if clean_status != "active":
                continue

            try:
                project_rows = conn.execute(
                    """
                    SELECT r.object_id,r.confidence
                    FROM entity_relations r
                    JOIN entities e ON e.id=r.object_id
                    WHERE r.subject_id=? AND r.state='current'
                      AND r.predicate='advances_project' AND e.kind='project'
                    ORDER BY r.confidence DESC
                    """,
                    (goal_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                # The executive must still materialize explicit goals when the
                # optional relation/linker schema has not been initialized yet.
                # Project enrichment can be added on a later refresh once that
                # schema exists.
                project_rows = []
            for project in project_rows:
                conn.execute(
                    "INSERT OR REPLACE INTO intention_entities(intention_id,entity_id,role,confidence) VALUES(?,?,?,?)",
                    (intention_id, str(project["object_id"]), "project", float(project["confidence"])),
                )
                linked_entities += 1

        pending = conn.execute("SELECT * FROM commitments WHERE status='pending'").fetchall()
        intentions = conn.execute("SELECT * FROM intentions WHERE status='active'").fetchall()

        for intention in intentions:
            intention_id = str(intention["id"])
            # Commitment links are also a current materialization. Clear them before
            # deterministic relinking so a still-pending but no-longer-related task
            # cannot remain attached to an objective forever.
            conn.execute("DELETE FROM intention_commitments WHERE intention_id=?", (intention_id,))
            entity_rows = conn.execute(
                "SELECT entity_id,role FROM intention_entities WHERE intention_id=?",
                (intention_id,),
            ).fetchall()
            project_ids = [str(row["entity_id"]) for row in entity_rows if str(row["role"]) == "project"]
            goal_ids = [str(row["entity_id"]) for row in entity_rows if str(row["role"]) == "goal"]
            title = str(intention["title"])
            title_tokens = {token for token in re.findall(r"[a-z0-9][a-z0-9_-]+", _normalize(title)) if len(token) >= 4}

            for commitment in pending:
                commitment_id = str(commitment["id"])
                action = str(commitment["action"])
                confidence = 0.0
                role = "related"

                # Strongest link: the commitment text names a project already tied to
                # the explicit goal through event evidence.
                for project_id in project_ids:
                    if _text_mentions(action, _aliases(conn, project_id)):
                        confidence = max(confidence, 0.90)
                        role = "project_dependency"

                # Medium link: explicit goal name itself appears in the commitment.
                for goal_id in goal_ids:
                    if _text_mentions(action, _aliases(conn, goal_id)):
                        confidence = max(confidence, 0.86)
                        role = "goal_dependency"

                # Conservative lexical fallback for specific multi-token overlap.
                action_tokens = {token for token in re.findall(r"[a-z0-9][a-z0-9_-]+", _normalize(action)) if len(token) >= 4}
                if len(title_tokens & action_tokens) >= 2:
                    confidence = max(confidence, 0.72)

                # Cross-source fallback: a generic Waiting-On item can still belong to
                # an objective when its owner has exactly one strong structured project
                # association and that project is the intention's project. Never use
                # this when the owner participates in multiple current projects.
                if confidence < 0.70:
                    owner_id = str(commitment["owner_id"] or "")
                    owner_matches, owner_confidence = _unambiguous_owner_project_link(conn, owner_id, project_ids)
                    if owner_matches:
                        confidence = max(confidence, owner_confidence)
                        role = "owner_project_dependency"

                if confidence < 0.70:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO intention_commitments(intention_id,commitment_id,role,confidence) VALUES(?,?,?,?)",
                    (intention_id, commitment_id, role, confidence),
                )
                linked_commitments += 1

        # Current executive links disappear when either side ceases to be current;
        # source commitments and intention rows remain for provenance/history.
        conn.execute(
            "DELETE FROM intention_commitments WHERE commitment_id IN (SELECT id FROM commitments WHERE status!='pending')"
        )
        conn.execute(
            "DELETE FROM intention_commitments WHERE intention_id IN (SELECT id FROM intentions WHERE status!='active')"
        )
        conn.commit()

    return {
        "intentions_upserted": upserted,
        "entity_links": linked_entities,
        "commitment_links": linked_commitments,
    }


def active_intentions(limit: int = 8) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 30))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM intentions
            WHERE status='active'
            ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,due_at,updated_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            iid = str(row["id"])
            entities = []
            for linked in conn.execute(
                "SELECT entity_id,role,confidence FROM intention_entities WHERE intention_id=? ORDER BY confidence DESC",
                (iid,),
            ).fetchall():
                entities.append(
                    {
                        "role": str(linked["role"]),
                        "entity_id": str(linked["entity_id"]),
                        "name": _entity_name(conn, str(linked["entity_id"])),
                        "confidence": float(linked["confidence"]),
                    }
                )
            commitments = []
            for linked in conn.execute(
                """
                SELECT c.*,ic.role AS link_role,ic.confidence AS link_confidence
                FROM intention_commitments ic
                JOIN commitments c ON c.id=ic.commitment_id
                WHERE ic.intention_id=? AND c.status='pending'
                ORDER BY CASE WHEN c.due_at IS NULL THEN 1 ELSE 0 END,c.due_at,c.updated_at DESC
                """,
                (iid,),
            ).fetchall():
                owner = _entity_name(conn, str(linked["owner_id"]) if linked["owner_id"] else None)
                commitments.append(
                    {
                        "id": str(linked["id"]),
                        "owner": owner,
                        "action": str(linked["action"]),
                        "due_at": str(linked["due_at"] or linked["due_text"] or ""),
                        "role": str(linked["link_role"]),
                        "confidence": float(linked["link_confidence"]),
                    }
                )
            result.append(
                {
                    "id": iid,
                    "source_kind": str(row["source_kind"]),
                    "title": str(row["title"]),
                    "next_action": str(row["next_action"]),
                    "due_at": str(row["due_at"] or ""),
                    "confidence": float(row["confidence"]),
                    "entities": entities,
                    "commitments": commitments,
                }
            )
        return result


def context(limit: int = 6) -> str:
    try:
        refresh_intentions()
    except Exception:
        pass
    items = active_intentions(limit=limit)
    if not items:
        return ""
    lines = ["PERSISTENT INTENTIONS (derived only from explicit goals and evidence-backed links):"]
    for item in items:
        detail = f"- {item['title']}"
        if item["next_action"]:
            detail += f"; next: {item['next_action']}"
        if item["due_at"]:
            detail += f"; due: {item['due_at']}"
        projects = [entity["name"] for entity in item["entities"] if entity["role"] == "project"]
        if projects:
            detail += "; project: " + ", ".join(projects[:3])
        lines.append(detail)
        for commitment in item["commitments"][:3]:
            owner = f"{commitment['owner']}: " if commitment["owner"] else ""
            due = f" (due {commitment['due_at']})" if commitment["due_at"] else ""
            lines.append(f"  waiting/commitment: {owner}{commitment['action']}{due}")
    return "\n".join(lines)[:7000]


def status() -> dict[str, int]:
    with _connect() as conn:
        active = int(conn.execute("SELECT COUNT(*) FROM intentions WHERE status='active'").fetchone()[0])
        retired = int(conn.execute("SELECT COUNT(*) FROM intentions WHERE status='retired'").fetchone()[0])
        completed = int(conn.execute("SELECT COUNT(*) FROM intentions WHERE status='completed'").fetchone()[0])
        total = int(conn.execute("SELECT COUNT(*) FROM intentions").fetchone()[0])
        links = int(conn.execute("SELECT COUNT(*) FROM intention_commitments").fetchone()[0])
    return {
        "active_intentions": active,
        "retired_intentions": retired,
        "completed_intentions": completed,
        "intentions": total,
        "linked_commitments": links,
    }
