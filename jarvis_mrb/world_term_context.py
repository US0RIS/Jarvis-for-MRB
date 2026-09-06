from __future__ import annotations

import re
import sqlite3
from typing import Any

from jarvis_mrb.world_model import DB_PATH, search as world_search

_TERM_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "indemnity_cap": ("indemnity cap", "indemnification cap", "cap on indemnity", "indemnity limit"),
    "indemnity_basket": ("indemnity basket", "basket", "deductible"),
    "escrow": ("escrow", "escrow amount", "holdback", "holdback amount"),
    "survival_period": ("survival period", "survival", "reps survive", "representations survive"),
    "termination_fee": ("termination fee", "breakup fee", "break-up fee"),
    "purchase_price": ("purchase price", "deal price", "consideration"),
    "working_capital_target": ("working capital target", "working capital peg", "working capital"),
    "earnout": ("earnout", "earn-out"),
    "interest_rate": ("interest rate", "rate of interest"),
    "ownership_percentage": ("ownership percentage", "ownership stake", "equity stake", "ownership"),
    "deadline": ("deadline", "signing date", "closing date", "signing deadline", "closing deadline"),
}

_ALL_TERMS_CUES = (
    "deal terms",
    "key terms",
    "current terms",
    "economics",
    "where do the terms stand",
    "what are the terms",
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _requested_term_keys(query: str) -> set[str]:
    normalized = _normalize(query)
    result: set[str] = set()
    for key, aliases in _TERM_QUERY_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            result.add(key)
    return result


def _project_seeds(query: str) -> list[dict[str, Any]]:
    seeds = [
        item for item in world_search(query, limit=12)
        if item.get("type") == "entity" and item.get("kind") == "project"
    ]
    # `world_search` may return project entities through an event match only after a
    # direct entity result. Keep the first unique IDs and never infer a project from a
    # generic noun phrase in the term question.
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for seed in seeds:
        entity_id = str(seed.get("id") or "")
        if entity_id and entity_id not in seen:
            seen.add(entity_id)
            result.append(seed)
    return result[:4]


def _latest_rows(project_id: str, requested: set[str], all_terms: bool) -> list[sqlite3.Row]:
    with _connect() as conn:
        if requested:
            placeholders = ",".join("?" for _ in requested)
            rows = conn.execute(
                f"""
                SELECT o.* FROM term_observations o
                JOIN (
                    SELECT term_key,MAX(id) AS max_id
                    FROM term_observations
                    WHERE project_id=? AND term_key IN ({placeholders})
                    GROUP BY term_key
                ) latest ON latest.max_id=o.id
                ORDER BY o.term_key
                """,
                (project_id, *tuple(sorted(requested))),
            ).fetchall()
        elif all_terms:
            rows = conn.execute(
                """
                SELECT o.* FROM term_observations o
                JOIN (
                    SELECT term_key,MAX(id) AS max_id
                    FROM term_observations WHERE project_id=? GROUP BY term_key
                ) latest ON latest.max_id=o.id
                ORDER BY o.term_key
                LIMIT 15
                """,
                (project_id,),
            ).fetchall()
        else:
            rows = []
    return rows


def _recent_conflict(project_id: str, term_key: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            """
            SELECT e.id,e.summary,e.occurred_at,e.source_ref
            FROM term_conflicts c
            JOIN term_observations newer ON newer.id=c.newer_observation_id
            JOIN events e ON e.id=c.conflict_event_id
            WHERE newer.project_id=? AND newer.term_key=?
            ORDER BY c.rowid DESC LIMIT 1
            """,
            (project_id, term_key),
        ).fetchone()


def context_for_query(query: str) -> str:
    requested = _requested_term_keys(query)
    normalized = _normalize(query)
    all_terms = any(cue in normalized for cue in _ALL_TERMS_CUES)
    if not requested and not all_terms:
        return ""
    projects = _project_seeds(query)
    if not projects:
        return ""

    lines = ["PROJECT TERM LEDGER (explicit extracted values with source provenance; conflicting sources remain visible):"]
    emitted = 0
    for project in projects:
        project_id = str(project.get("id") or "")
        project_name = str(project.get("name") or project.get("text") or project_id)
        rows = _latest_rows(project_id, requested, all_terms)
        if not rows:
            continue
        lines.append(f"- {project_name}:")
        for row in rows:
            lines.append(
                f"  - {row['display_name']}: {row['value_text']} "
                f"[source {row['source_kind']} event {row['source_event_id']}; {row['occurred_at']}; confidence {float(row['confidence']):.2f}]"
            )
            conflict = _recent_conflict(project_id, str(row["term_key"]))
            if conflict is not None:
                lines.append(f"    recent source discrepancy: {str(conflict['summary'])[:900]}")
            emitted += 1
            if emitted >= 15:
                return "\n".join(lines)[:9000]
    return "\n".join(lines)[:9000] if emitted else ""


def status() -> dict[str, Any]:
    return {
        "query_aware": True,
        "requires_explicit_term_or_all_terms_cue": True,
        "requires_project_entity_match": True,
        "shows_source_provenance": True,
        "shows_recent_conflict": True,
    }
