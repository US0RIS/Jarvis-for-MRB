from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from jarvis_mrb.world_model import DB_PATH, status as world_status


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def validate() -> dict[str, Any]:
    # Importing these modules creates their additive schema tables if this is the
    # first diagnostic call after an upgrade.
    from jarvis_mrb.world_executive import status as executive_status
    from jarvis_mrb.world_linker import status as linker_status

    core = world_status()
    linker = linker_status()
    executive = executive_status()
    problems: list[str] = []
    warnings: list[str] = []

    with _connect() as conn:
        integrity_row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = str(integrity_row[0]) if integrity_row else "unknown"
        if integrity.lower() != "ok":
            problems.append(f"SQLite integrity_check: {integrity}")

        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            problems.append(f"Foreign-key violations: {len(fk_rows)}")

        max_event = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0])
        linked_event = int(linker.get("last_linked_event_id") or 0)
        linker_lag = max(0, max_event - linked_event)
        if linker_lag > 500:
            warnings.append(f"World linker is {linker_lag} events behind.")

        # Current explicit-goal belief should agree with its intention status. A
        # mismatch means the executive layer is stale or a migration was interrupted.
        mismatch_rows = conn.execute(
            """
            SELECT e.id,e.canonical_name,b.value_json,i.status
            FROM entities e
            JOIN beliefs b ON b.subject_id=e.id AND b.predicate='status' AND b.state='current'
            LEFT JOIN intentions i ON i.source_kind='explicit_goal' AND i.source_ref=e.id
            WHERE e.kind='goal'
            """
        ).fetchall()
        goal_mismatches = 0
        for row in mismatch_rows:
            raw = str(row["value_json"] or "\"active\"").strip('"').lower()
            expected = "completed" if raw in {"completed", "done", "resolved"} else (
                "retired" if raw in {"retired", "deleted", "removed", "cancelled", "canceled", "inactive"} else "active"
            )
            actual = str(row["status"] or "missing")
            if expected != actual:
                goal_mismatches += 1
        if goal_mismatches:
            problems.append(f"Goal/intention status mismatches: {goal_mismatches}")

        stale_links = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM intention_commitments ic
                JOIN intentions i ON i.id=ic.intention_id
                JOIN commitments c ON c.id=ic.commitment_id
                WHERE i.status!='active' OR c.status!='pending'
                """
            ).fetchone()[0]
        )
        if stale_links:
            problems.append(f"Stale current intention/commitment links: {stale_links}")

        relation_without_evidence = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM entity_relations r
                LEFT JOIN relation_evidence re ON re.relation_id=r.id
                WHERE r.state='current'
                GROUP BY r.id
                HAVING COUNT(re.event_id)=0
                """
            ).fetchall().__len__()
        )
        if relation_without_evidence:
            problems.append(f"Current derived relations without evidence: {relation_without_evidence}")

        # Privacy boundary: the iPhone->PC world snapshot contract explicitly bans
        # these raw/sensitive channels. Search only iPhone-origin world events; a hit
        # should trigger manual inspection, not automatic deletion.
        privacy_terms = (
            "feature_prints",
            "featureprints",
            "raw_image",
            "raw camera frame",
            "rolling_audio",
            "raw microphone",
            "clipboard_contents",
            "privacy_zone_coordinates",
        )
        clauses = " OR ".join(["lower(payload_json) LIKE ?"] * len(privacy_terms))
        privacy_hits = int(
            conn.execute(
                f"SELECT COUNT(*) FROM events WHERE source_kind LIKE 'iphone%' AND ({clauses})",
                tuple(f"%{term}%" for term in privacy_terms),
            ).fetchone()[0]
        )
        if privacy_hits:
            problems.append(f"Potential prohibited raw iPhone payloads in world events: {privacy_hits}")

        disputed = int(conn.execute("SELECT COUNT(*) FROM beliefs WHERE state='disputed'").fetchone()[0])
        if disputed:
            warnings.append(f"There are {disputed} disputed belief(s); this is allowed but should remain visible to reasoning.")

    try:
        audit: dict[str, Any]
        from jarvis_mrb.tool_audit import status as audit_status

        audit = audit_status()
        if not bool(audit.get("installed")):
            warnings.append("Backend tool audit wrapper is not installed in this process yet.")
    except Exception as exc:
        audit = {"installed": False, "error": str(exc)[:300]}
        warnings.append("Backend tool audit status could not be read.")

    path = Path(DB_PATH)
    return {
        "ok": not problems,
        "integrity": integrity,
        "foreign_key_violations": len(fk_rows),
        "database_bytes": path.stat().st_size if path.exists() else 0,
        "core": core,
        "linker": linker,
        "executive": executive,
        "tool_audit": audit,
        "linker_lag_events": linker_lag,
        "goal_intention_mismatches": goal_mismatches,
        "stale_intention_commitment_links": stale_links,
        "relations_without_evidence": relation_without_evidence,
        "privacy_boundary_hits": privacy_hits,
        "problems": problems,
        "warnings": warnings,
    }
