from __future__ import annotations

import re
import sqlite3
from typing import Any

from jarvis_mrb.world_model import DB_PATH, search as world_search
from jarvis_mrb.world_terms import latest_observations

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
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for seed in seeds:
        entity_id = str(seed.get("id") or "")
        if entity_id and entity_id not in seen:
            seen.add(entity_id)
            result.append(seed)
    return result[:4]


def _latest_rows(project_id: str, requested: set[str], all_terms: bool) -> list[dict[str, Any]]:
    if not requested and not all_terms:
        return []
    rows = latest_observations(project_id, requested if requested else None)
    return rows[:15]


def _conflict_for_latest(project_id: str, term_key: str, latest_observation_id: int) -> sqlite3.Row | None:
    """Return a discrepancy only when the chronologically latest observation is one side.

    Historical conflicts remain provenance, but they should not be presented as the
    current discrepancy after a later source converges on one value.
    """
    with _connect() as conn:
        return conn.execute(
            """
            SELECT e.id,e.summary,e.occurred_at,e.source_ref
            FROM term_conflicts c
            JOIN term_observations newer ON newer.id=c.newer_observation_id
            JOIN events e ON e.id=c.conflict_event_id
            WHERE newer.project_id=? AND newer.term_key=? AND newer.id=?
            ORDER BY e.occurred_at DESC,e.id DESC LIMIT 1
            """,
            (project_id, term_key, int(latest_observation_id)),
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

    lines = ["PROJECT TERM LEDGER (explicit extracted values with source provenance; current state follows source occurrence time, not ingestion order):"]
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
                f"  - {row['display_name']}: {row['value']} "
                f"[source {row['source_kind']} event {row['source_event_id']}; {row['occurred_at']}; confidence {float(row['confidence']):.2f}]"
            )
            conflict = _conflict_for_latest(project_id, str(row["term_key"]), int(row["id"]))
            if conflict is not None:
                lines.append(f"    current source discrepancy: {str(conflict['summary'])[:900]}")
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
        "shows_current_conflict": True,
        "chronology_uses_occurred_at": True,
    }
