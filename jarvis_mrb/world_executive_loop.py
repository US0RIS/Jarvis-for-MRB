from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from jarvis_mrb.permissions import decide as permission_decision
from jarvis_mrb.world_model import DB_PATH
from jarvis_mrb.world_relevance import is_executive_query, relevant_intentions

_PLAN_CUES = (
    "status", "where does", "where do", "where are we", "where am i",
    "blocker", "blocking", "dependency", "dependencies", "next step", "next action",
    "what changed", "what's changed", "what has changed", "waiting on", "due", "deadline",
    "at risk", "verification", "verified", "did it work", "did that work",
)

_RECENT_CHANGE_TYPES = {
    "document.version_changed", "term.changed_or_conflicted", "meeting.finished",
    "meeting.completed", "commitment.resolved", "knowledge.gmail_attachment",
    "verification.verified", "verification.failed", "verification.timed_out",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:1500]


def _stable_key(*parts: object) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _parse_time(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.astimezone()
        return value.astimezone()
    except (TypeError, ValueError, OverflowError):
        return None


def _days_until(raw: str | None) -> float | None:
    value = _parse_time(raw)
    if value is None:
        return None
    return (value - datetime.now().astimezone()).total_seconds() / 86400.0


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS executive_attention (
            attention_key TEXT PRIMARY KEY,
            intention_id TEXT NOT NULL REFERENCES intentions(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            source_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
            commitment_id TEXT REFERENCES commitments(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            severity TEXT NOT NULL,
            score REAL NOT NULL,
            due_at TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            evidence TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_executive_attention_intention
            ON executive_attention(intention_id,status,score DESC,updated_at DESC);

        CREATE TABLE IF NOT EXISTS executive_decisions (
            id TEXT PRIMARY KEY,
            intention_id TEXT NOT NULL REFERENCES intentions(id) ON DELETE CASCADE,
            attention_key TEXT REFERENCES executive_attention(attention_key) ON DELETE SET NULL,
            decision_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            rationale TEXT NOT NULL,
            proposed_tool TEXT NOT NULL DEFAULT '',
            proposed_args_json TEXT NOT NULL DEFAULT '{}',
            risk TEXT NOT NULL DEFAULT '',
            requires_confirmation INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL DEFAULT 'current',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_executive_decisions_intention
            ON executive_decisions(intention_id,status,updated_at DESC);

        CREATE TABLE IF NOT EXISTS executive_loop_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def _entity_name(conn: sqlite3.Connection, entity_id: str) -> str:
    row = conn.execute("SELECT canonical_name FROM entities WHERE id=?", (entity_id,)).fetchone()
    return str(row["canonical_name"]) if row else entity_id


def _owner_email(conn: sqlite3.Connection, owner_id: str | None) -> str:
    if not owner_id:
        return ""
    row = conn.execute(
        "SELECT external_id FROM external_ids WHERE entity_id=? AND namespace='email_address' ORDER BY external_id LIMIT 1",
        (owner_id,),
    ).fetchone()
    return str(row["external_id"]) if row else ""


def _project_ids(item: dict[str, Any]) -> list[str]:
    return [
        str(entity.get("entity_id") or "")
        for entity in item.get("entities") or []
        if str(entity.get("role") or "") == "project" and entity.get("entity_id")
    ]


def _active_term_conflicts(conn: sqlite3.Connection, project_ids: list[str]) -> list[dict[str, Any]]:
    """Return only discrepancies attached to each term's chronological latest source."""
    if not project_ids:
        return []
    try:
        from jarvis_mrb.world_terms import latest_observations
    except Exception:
        return []

    result: list[dict[str, Any]] = []
    for project_id in project_ids[:8]:
        latest = latest_observations(project_id)
        for observation in latest:
            observation_id = int(observation.get("id") or 0)
            if not observation_id:
                continue
            try:
                row = conn.execute(
                    """
                    SELECT c.older_observation_id,c.newer_observation_id,c.conflict_event_id,
                           older.value_text AS older_value,older.source_kind AS older_source,
                           newer.project_id,newer.term_key,newer.display_name,newer.value_text AS newer_value,
                           newer.source_kind AS newer_source,newer.occurred_at,
                           e.summary AS event_summary,e.confidence AS event_confidence
                    FROM term_conflicts c
                    JOIN term_observations older ON older.id=c.older_observation_id
                    JOIN term_observations newer ON newer.id=c.newer_observation_id
                    LEFT JOIN events e ON e.id=c.conflict_event_id
                    WHERE newer.project_id=? AND newer.term_key=? AND newer.id=?
                    ORDER BY e.occurred_at DESC,e.id DESC LIMIT 1
                    """,
                    (project_id, str(observation.get("term_key") or ""), observation_id),
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
            if row is None:
                continue
            project = _entity_name(conn, project_id)
            detail = str(row["event_summary"] or "").strip()
            if not detail:
                detail = (
                    f"{project} {row['display_name']} differs across current sources: "
                    f"{row['older_value']} ({row['older_source']}) versus "
                    f"{row['newer_value']} ({row['newer_source']})."
                )
            result.append(
                {
                    "kind": "term_conflict",
                    "source_ref": f"term-conflict:{row['older_observation_id']}:{row['newer_observation_id']}",
                    "source_event_id": int(row["conflict_event_id"]) if row["conflict_event_id"] else None,
                    "title": f"Resolve {row['display_name']} discrepancy on {project}",
                    "detail": detail[:1800],
                    "severity": "high",
                    "score": 100.0,
                    "due_at": None,
                    "evidence": f"chronologically latest explicit {row['display_name']} observation conflicts with the preceding explicit source",
                    "project": project,
                    "term": str(row["display_name"]),
                    "older_value": str(row["older_value"]),
                    "newer_value": str(row["newer_value"]),
                    "occurred_at": str(row["occurred_at"]),
                    "confidence": float(row["event_confidence"] or 0.9),
                }
            )
    result.sort(
        key=lambda item: (_parse_time(str(item.get("occurred_at") or "")) or datetime.min.astimezone()),
        reverse=True,
    )
    return result[:12]


def _commitment_items(conn: sqlite3.Connection, item: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for commitment in item.get("commitments") or []:
        commitment_id = str(commitment.get("id") or "")
        row = conn.execute(
            "SELECT owner_id,action,due_at,due_text,confidence FROM commitments WHERE id=? AND status='pending'",
            (commitment_id,),
        ).fetchone()
        if row is None:
            continue
        due_at = str(row["due_at"] or "")
        remaining = _days_until(due_at)
        overdue = remaining is not None and remaining < 0
        due_soon = remaining is not None and remaining <= 7
        owner_id = str(row["owner_id"] or "")
        owner = _entity_name(conn, owner_id) if owner_id else str(commitment.get("owner") or "")
        action = str(row["action"])
        if overdue:
            kind, severity, score = "overdue_commitment", "high", 92.0
            title = f"Overdue: {owner + ': ' if owner else ''}{action}"
        elif due_soon:
            kind, severity, score = "due_commitment", "medium", 76.0
            title = f"Due soon: {owner + ': ' if owner else ''}{action}"
        else:
            kind, severity, score = "dependency", "low", 55.0
            title = f"Waiting on {owner}: {action}" if owner else f"Pending dependency: {action}"
        result.append(
            {
                "kind": kind,
                "source_ref": f"commitment:{commitment_id}",
                "source_event_id": None,
                "commitment_id": commitment_id,
                "title": title[:1000],
                "detail": action[:1800],
                "severity": severity,
                "score": score,
                "due_at": due_at or None,
                "evidence": f"pending commitment {commitment_id}",
                "owner": owner,
                "owner_id": owner_id,
                "owner_email": _owner_email(conn, owner_id),
                "confidence": float(row["confidence"] or commitment.get("confidence") or 0.8),
            }
        )
    return result


def _verification_items(conn: sqlite3.Connection, intention_id: str) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """
            SELECT v.id,v.tool,v.status,v.verifier,v.deadline_at,v.last_evidence,v.last_error,
                   v.action_event_id,v.resolved_event_id,v.updated_at
            FROM action_verifications v
            JOIN executive_decisions d ON d.id=v.executive_decision_id
            WHERE d.intention_id=? AND v.status IN ('pending','failed','timed_out','unverified')
            ORDER BY
                CASE v.status WHEN 'failed' THEN 0 WHEN 'timed_out' THEN 1 WHEN 'unverified' THEN 2 ELSE 3 END,
                v.updated_at DESC
            LIMIT 12
            """,
            (intention_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        status = str(row["status"])
        tool = str(row["tool"])
        evidence = str(row["last_evidence"] or row["last_error"] or "")
        if status == "failed":
            kind, severity, score = "verification_failed", "high", 112.0
            title = f"Verified outcome failed: {tool}"
        elif status == "timed_out":
            kind, severity, score = "verification_timed_out", "high", 108.0
            title = f"Outcome verification timed out: {tool}"
        elif status == "unverified":
            kind, severity, score = "verification_unverified", "medium", 96.0
            title = f"Outcome cannot be independently verified: {tool}"
        else:
            kind, severity, score = "verification_pending", "medium", 86.0
            title = f"Awaiting independent outcome verification: {tool}"
        result.append(
            {
                "kind": kind,
                "verification_status": status,
                "verification_id": str(row["id"]),
                "source_ref": f"verification:{row['id']}",
                "source_event_id": int(row["resolved_event_id"]) if row["resolved_event_id"] else None,
                "title": title,
                "detail": evidence[:1800] or f"Verifier {row['verifier']} has not produced conclusive evidence yet.",
                "severity": severity,
                "score": score,
                "due_at": str(row["deadline_at"] or "") or None,
                "evidence": f"closed-loop verification {status} for action event {row['action_event_id']}",
                "confidence": 1.0,
                "tool": tool,
            }
        )
    return result


def _recent_changes(conn: sqlite3.Connection, project_ids: list[str]) -> list[dict[str, Any]]:
    if not project_ids:
        return []
    placeholders = ",".join("?" for _ in project_ids)
    type_placeholders = ",".join("?" for _ in _RECENT_CHANGE_TYPES)
    rows = conn.execute(
        f"""
        SELECT DISTINCT e.id,e.event_type,e.occurred_at,e.summary,e.confidence,e.source_kind,e.source_ref
        FROM events e
        JOIN event_entities ee ON ee.event_id=e.id
        WHERE ee.entity_id IN ({placeholders}) AND e.event_type IN ({type_placeholders})
        ORDER BY e.id DESC LIMIT 500
        """,
        (*tuple(project_ids), *tuple(sorted(_RECENT_CHANGE_TYPES))),
    ).fetchall()
    now = datetime.now().astimezone()
    candidates: list[tuple[datetime, sqlite3.Row]] = []
    for row in rows:
        occurred = _parse_time(str(row["occurred_at"] or ""))
        if occurred is None:
            continue
        age = (now - occurred).total_seconds()
        if age < -86400 or age > 14 * 86400:
            continue
        if str(row["event_type"]) == "term.changed_or_conflicted":
            continue
        candidates.append((occurred, row))
    candidates.sort(key=lambda item: (item[0], int(item[1]["id"])), reverse=True)
    return [
        {
            "event_id": int(row["id"]),
            "event_type": str(row["event_type"]),
            "occurred_at": str(row["occurred_at"]),
            "summary": str(row["summary"]),
            "confidence": float(row["confidence"]),
            "source_kind": str(row["source_kind"]),
            "source_ref": str(row["source_ref"]),
        }
        for _, row in candidates[:5]
    ]


def _deadline_attention(item: dict[str, Any]) -> dict[str, Any] | None:
    due_at = str(item.get("due_at") or "")
    remaining = _days_until(due_at)
    if remaining is None:
        return None
    if remaining < 0:
        severity, score, label = "high", 88.0, "Objective deadline has passed"
    elif remaining <= 2:
        severity, score, label = "high", 82.0, "Objective due within 2 days"
    elif remaining <= 7:
        severity, score, label = "medium", 68.0, "Objective due within 7 days"
    else:
        return None
    return {
        "kind": "objective_deadline",
        "source_ref": "objective-deadline",
        "source_event_id": None,
        "title": label,
        "detail": f"{item.get('title')} is due {due_at}.",
        "severity": severity,
        "score": score,
        "due_at": due_at,
        "evidence": "explicit intention due_at",
        "confidence": float(item.get("confidence") or 1.0),
    }


def _next_action_attention(item: dict[str, Any]) -> dict[str, Any] | None:
    action = str(item.get("next_action") or "").strip()
    if not action:
        return None
    return {
        "kind": "explicit_next_action",
        "source_ref": "explicit-next-action",
        "source_event_id": None,
        "title": f"Next action: {action}"[:1000],
        "detail": action[:1800],
        "severity": "low",
        "score": 50.0,
        "due_at": str(item.get("due_at") or "") or None,
        "evidence": "explicit goal next_action belief",
        "confidence": float(item.get("confidence") or 1.0),
    }


def _proposal_for(candidate: dict[str, Any], projects: list[str]) -> tuple[str, dict[str, Any], str]:
    kind = str(candidate.get("kind") or "")
    if kind == "term_conflict":
        project = str(candidate.get("project") or (projects[0] if projects else "project"))
        term = str(candidate.get("term") or "changed term")
        return (
            "knowledge.search",
            {"query": f"{project} {term}", "limit": 5},
            "Gather the underlying private evidence before deciding which source controls.",
        )
    if kind in {"overdue_commitment", "due_commitment", "dependency"} and candidate.get("owner_email"):
        return (
            "gmail.query",
            {"query": f"from:{candidate['owner_email']} newer_than:14d", "limit": 5},
            "Check whether the dependency has already been satisfied before following up.",
        )
    if kind == "document_change":
        project = projects[0] if projects else ""
        return (
            "knowledge.search",
            {"query": f"{project} revised draft changes".strip(), "limit": 5},
            "Review the changed source material connected to the active objective.",
        )
    if kind == "verification_pending":
        return ("", {}, "Do not advance the plan until the independent verifier resolves the action outcome.")
    if kind in {"verification_failed", "verification_timed_out", "verification_unverified"}:
        return ("", {}, "The previous action outcome is not established; reassess or obtain independent confirmation before continuing.")
    return ("", {}, "")


def _decision_view(candidate: dict[str, Any], projects: list[str]) -> dict[str, Any]:
    tool, args, tool_rationale = _proposal_for(candidate, projects)
    risk = ""
    needs_confirmation = False
    if tool:
        decision = permission_decision(tool)
        if decision.allowed:
            risk = str(decision.risk)
            needs_confirmation = bool(decision.needs_confirmation)
        else:
            tool = ""
            args = {}
            tool_rationale = "The relevant tool is currently denied by permission policy."

    summary = str(candidate.get("title") or candidate.get("detail") or "Review active objective")[:1200]
    rationale = " ".join(
        part for part in (str(candidate.get("evidence") or "").strip(), tool_rationale.strip()) if part
    )[:2200]
    return {
        "summary": summary,
        "rationale": rationale,
        "tool": tool,
        "arguments": args,
        "risk": risk,
        "requires_confirmation": needs_confirmation,
        "confidence": max(0.0, min(float(candidate.get("confidence") or 0.8), 1.0)),
    }


def _persist_attention(conn: sqlite3.Connection, intention_id: str, candidate: dict[str, Any]) -> str:
    key = _stable_key(intention_id, candidate.get("kind"), candidate.get("source_ref"))
    now = _now()
    existing = conn.execute("SELECT created_at FROM executive_attention WHERE attention_key=?", (key,)).fetchone()
    created = str(existing["created_at"]) if existing else now
    conn.execute(
        """
        INSERT INTO executive_attention(
            attention_key,intention_id,kind,source_ref,source_event_id,commitment_id,title,detail,
            severity,score,due_at,status,evidence,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(attention_key) DO UPDATE SET
            source_event_id=excluded.source_event_id,commitment_id=excluded.commitment_id,
            title=excluded.title,detail=excluded.detail,severity=excluded.severity,score=excluded.score,
            due_at=excluded.due_at,status='open',evidence=excluded.evidence,updated_at=excluded.updated_at
        """,
        (
            key, intention_id, str(candidate.get("kind") or "attention")[:80],
            str(candidate.get("source_ref") or "")[:500], candidate.get("source_event_id"),
            candidate.get("commitment_id"), str(candidate.get("title") or "")[:1200],
            str(candidate.get("detail") or "")[:2400], str(candidate.get("severity") or "low")[:20],
            float(candidate.get("score") or 0.0), str(candidate.get("due_at") or "")[:100] or None,
            "open", str(candidate.get("evidence") or "")[:1500], created, now,
        ),
    )
    return key


def _persist_decision(
    conn: sqlite3.Connection,
    intention_id: str,
    attention_key: str | None,
    candidate: dict[str, Any],
    projects: list[str],
) -> dict[str, Any]:
    view = _decision_view(candidate, projects)
    summary = str(view["summary"])
    decision_id = "decision:" + _stable_key(intention_id, attention_key or "none", summary)[:40]
    now = _now()
    existing = conn.execute("SELECT created_at FROM executive_decisions WHERE id=?", (decision_id,)).fetchone()
    created = str(existing["created_at"]) if existing else now
    conn.execute(
        "UPDATE executive_decisions SET status='superseded',updated_at=? WHERE intention_id=? AND status='current' AND id!=?",
        (now, intention_id, decision_id),
    )
    conn.execute(
        """
        INSERT INTO executive_decisions(
            id,intention_id,attention_key,decision_type,summary,rationale,proposed_tool,
            proposed_args_json,risk,requires_confirmation,confidence,status,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            attention_key=excluded.attention_key,decision_type=excluded.decision_type,summary=excluded.summary,
            rationale=excluded.rationale,proposed_tool=excluded.proposed_tool,
            proposed_args_json=excluded.proposed_args_json,risk=excluded.risk,
            requires_confirmation=excluded.requires_confirmation,confidence=excluded.confidence,
            status='current',updated_at=excluded.updated_at
        """,
        (
            decision_id, intention_id, attention_key, str(candidate.get("kind") or "review"), summary,
            str(view["rationale"]), str(view["tool"]),
            json.dumps(view["arguments"], ensure_ascii=False, sort_keys=True), str(view["risk"]),
            1 if view["requires_confirmation"] else 0, float(view["confidence"]), "current", created, now,
        ),
    )
    return {"id": decision_id, **view}


def _compile_item(conn: sqlite3.Connection, item: dict[str, Any], *, persist: bool) -> dict[str, Any]:
    intention_id = str(item.get("id") or "")
    project_ids = _project_ids(item)
    project_names = [_entity_name(conn, project_id) for project_id in project_ids]

    candidates: list[dict[str, Any]] = []
    verifications = _verification_items(conn, intention_id)
    candidates.extend(verifications)
    candidates.extend(_active_term_conflicts(conn, project_ids))
    candidates.extend(_commitment_items(conn, item))
    deadline = _deadline_attention(item)
    if deadline:
        candidates.append(deadline)
    explicit_next = _next_action_attention(item)
    if explicit_next:
        candidates.append(explicit_next)

    recent_changes = _recent_changes(conn, project_ids)
    for change in recent_changes:
        if change["event_type"] == "document.version_changed":
            candidates.append(
                {
                    "kind": "document_change",
                    "source_ref": f"event:{change['event_id']}",
                    "source_event_id": change["event_id"],
                    "title": "Review revised document changes",
                    "detail": change["summary"],
                    "severity": "medium",
                    "score": 72.0,
                    "due_at": None,
                    "evidence": f"document.version_changed event {change['event_id']}",
                    "confidence": change["confidence"],
                }
            )

    candidates.sort(
        key=lambda value: (float(value.get("score") or 0.0), str(value.get("title") or "")),
        reverse=True,
    )

    open_keys: list[str] = []
    keyed_candidates: list[tuple[str | None, dict[str, Any]]] = []
    for candidate in candidates:
        key = _persist_attention(conn, intention_id, candidate) if persist else None
        if key:
            open_keys.append(key)
        keyed_candidates.append((key, candidate))

    if persist:
        if open_keys:
            placeholders = ",".join("?" for _ in open_keys)
            conn.execute(
                f"UPDATE executive_attention SET status='stale',updated_at=? WHERE intention_id=? AND status='open' AND attention_key NOT IN ({placeholders})",
                (_now(), intention_id, *tuple(open_keys)),
            )
        else:
            conn.execute(
                "UPDATE executive_attention SET status='stale',updated_at=? WHERE intention_id=? AND status='open'",
                (_now(), intention_id),
            )

    top_key, top_candidate = keyed_candidates[0] if keyed_candidates else (
        None,
        {
            "kind": "review",
            "title": str(item.get("next_action") or "Review objective status"),
            "detail": str(item.get("title") or ""),
            "evidence": "active explicit intention with no stronger blocker or dependency",
            "confidence": float(item.get("confidence") or 1.0),
        },
    )
    decision = (
        _persist_decision(conn, intention_id, top_key, top_candidate, project_names)
        if persist else _decision_view(top_candidate, project_names)
    )

    blockers = [
        candidate for _, candidate in keyed_candidates
        if candidate.get("kind") in {
            "term_conflict", "overdue_commitment", "verification_failed",
            "verification_timed_out", "verification_unverified",
        }
    ]
    dependencies = [
        candidate for _, candidate in keyed_candidates
        if candidate.get("kind") in {"overdue_commitment", "due_commitment", "dependency"}
    ]
    pending_verification = [
        candidate for _, candidate in keyed_candidates if candidate.get("kind") == "verification_pending"
    ]

    due_remaining = _days_until(str(item.get("due_at") or ""))
    if blockers:
        state = "at_risk"
    elif pending_verification:
        state = "awaiting_verification"
    elif due_remaining is not None and due_remaining < 0:
        state = "overdue"
    elif due_remaining is not None and due_remaining <= 2:
        state = "due_soon"
    else:
        state = "active"

    next_actions: list[str] = []
    for _, candidate in keyed_candidates:
        kind = str(candidate.get("kind") or "")
        if kind == "term_conflict":
            next_actions.append(str(candidate.get("title") or "Resolve source discrepancy"))
        elif kind == "overdue_commitment":
            owner = str(candidate.get("owner") or "")
            action = str(candidate.get("detail") or "")
            next_actions.append(
                f"Check/follow up with {owner} on {action}" if owner else f"Resolve overdue dependency: {action}"
            )
        elif kind == "due_commitment":
            next_actions.append(str(candidate.get("title") or "Review due dependency"))
        elif kind == "document_change":
            next_actions.append(str(candidate.get("title") or "Review document changes"))
        elif kind == "explicit_next_action":
            next_actions.append(str(candidate.get("detail") or ""))
        elif kind == "verification_pending":
            next_actions.append(f"Wait for independent verification of {candidate.get('tool') or 'the action'}")
        elif kind == "verification_failed":
            next_actions.append(f"Reassess after failed outcome verification for {candidate.get('tool') or 'the action'}")
        elif kind == "verification_timed_out":
            next_actions.append(f"Obtain manual confirmation or retry {candidate.get('tool') or 'the action'}")
        elif kind == "verification_unverified":
            next_actions.append(f"Do not assume success; independently confirm {candidate.get('tool') or 'the action'}")
        if len(next_actions) >= 5:
            break
    deduped_actions: list[str] = []
    for action in next_actions:
        action = " ".join(action.split())
        if action and action not in deduped_actions:
            deduped_actions.append(action)

    return {
        "intention_id": intention_id,
        "objective": str(item.get("title") or ""),
        "state": state,
        "due_at": str(item.get("due_at") or ""),
        "projects": project_names,
        "attention": [candidate for _, candidate in keyed_candidates][:12],
        "verifications": verifications[:8],
        "blockers": blockers[:6],
        "dependencies": dependencies[:8],
        "recent_changes": recent_changes[:5],
        "next_actions": deduped_actions[:5],
        "decision": decision,
    }


def refresh() -> dict[str, int]:
    from jarvis_mrb.world_executive import active_intentions, refresh_intentions

    refresh_intentions()
    items = active_intentions(limit=50)
    now = _now()
    with _connect() as conn:
        active_ids: list[str] = []
        for item in items:
            active_ids.append(str(item.get("id") or ""))
            _compile_item(conn, item, persist=True)
        if active_ids:
            placeholders = ",".join("?" for _ in active_ids)
            conn.execute(
                f"UPDATE executive_attention SET status='stale',updated_at=? WHERE status='open' AND intention_id NOT IN ({placeholders})",
                (now, *tuple(active_ids)),
            )
            conn.execute(
                f"UPDATE executive_decisions SET status='superseded',updated_at=? WHERE status='current' AND intention_id NOT IN ({placeholders})",
                (now, *tuple(active_ids)),
            )
        else:
            conn.execute("UPDATE executive_attention SET status='stale',updated_at=? WHERE status='open'", (now,))
            conn.execute("UPDATE executive_decisions SET status='superseded',updated_at=? WHERE status='current'", (now,))
        conn.execute(
            "INSERT INTO executive_loop_state(key,value) VALUES('last_refresh',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (now,),
        )
        conn.commit()
        attention_count = int(conn.execute("SELECT COUNT(*) FROM executive_attention WHERE status='open'").fetchone()[0])
        decisions = int(conn.execute("SELECT COUNT(*) FROM executive_decisions WHERE status='current'").fetchone()[0])
    return {"active_intentions": len(items), "attention_items": attention_count, "current_decisions": decisions}


def plans_for_query(query: str, limit: int = 4) -> list[dict[str, Any]]:
    try:
        refresh()
    except Exception:
        pass
    selected = relevant_intentions(query, limit=max(1, min(int(limit), 8)))
    if not selected:
        return []
    with _connect() as conn:
        return [_compile_item(conn, item, persist=False) for item in selected]


def should_supply_context(query: str) -> bool:
    normalized = _normalize(query)
    return is_executive_query(query) or any(cue in normalized for cue in _PLAN_CUES)


def context_for_query(query: str, limit: int = 3) -> str:
    if not should_supply_context(query):
        return ""
    plans = plans_for_query(query, limit=limit)
    if not plans:
        return ""
    lines = ["EXECUTIVE LOOP (persistent operational state derived from explicit intentions and provenance-bearing world evidence):"]
    for plan in plans:
        lines.append(f"- OBJECTIVE: {plan['objective']} | state={plan['state']}")
        if plan["due_at"]:
            lines.append(f"  deadline: {plan['due_at']}")
        if plan["projects"]:
            lines.append("  projects: " + ", ".join(plan["projects"][:3]))
        if plan["verifications"]:
            lines.append("  OUTCOME VERIFICATION:")
            for verification in plan["verifications"][:4]:
                lines.append(
                    f"    - {verification.get('verification_status')}: {verification.get('tool')}; {verification.get('detail')}"
                )
        if plan["blockers"]:
            lines.append("  BLOCKERS:")
            for blocker in plan["blockers"][:4]:
                lines.append(f"    - {blocker.get('title')}: {blocker.get('detail')}")
        if plan["dependencies"]:
            lines.append("  DEPENDENCIES / WAITING ON:")
            for dep in plan["dependencies"][:4]:
                due = f"; due {dep.get('due_at')}" if dep.get("due_at") else ""
                lines.append(f"    - {dep.get('title')}{due}")
        if plan["recent_changes"]:
            lines.append("  RECENT CHANGES:")
            for change in plan["recent_changes"][:3]:
                lines.append(f"    - {change.get('occurred_at')}: {change.get('summary')}")
        if plan["next_actions"]:
            lines.append("  NEXT ACTIONS:")
            for action in plan["next_actions"][:4]:
                lines.append(f"    - {action}")
        decision = plan.get("decision") or {}
        if decision:
            lines.append(f"  RECOMMENDED NOW: {decision.get('summary')}")
            if decision.get("tool"):
                lines.append(
                    "  executable proposal (only through normal permission gate): "
                    f"{decision.get('tool')} {json.dumps(decision.get('arguments') or {}, ensure_ascii=False, sort_keys=True)}; "
                    f"risk={decision.get('risk') or 'unknown'}; confirmation_required={bool(decision.get('requires_confirmation'))}"
                )
    return "\n".join(lines)[:12000]


def next_decision(query: str) -> dict[str, Any] | None:
    plans = plans_for_query(query, limit=1)
    if not plans:
        return None
    plan = plans[0]
    decision = dict(plan.get("decision") or {})
    if not decision:
        return None
    decision["objective"] = plan.get("objective")
    decision["state"] = plan.get("state")
    return decision


def describe(query: str) -> str:
    context = context_for_query(query, limit=4)
    return context or "No active persistent intention matched that executive query."


def status() -> dict[str, Any]:
    try:
        from jarvis_mrb.world_executive import status as executive_status
        executive_status()
        with _connect() as conn:
            open_attention = int(conn.execute("SELECT COUNT(*) FROM executive_attention WHERE status='open'").fetchone()[0])
            current_decisions = int(conn.execute("SELECT COUNT(*) FROM executive_decisions WHERE status='current'").fetchone()[0])
            row = conn.execute("SELECT value FROM executive_loop_state WHERE key='last_refresh'").fetchone()
            try:
                pending_verification = int(conn.execute("SELECT COUNT(*) FROM action_verifications WHERE status='pending'").fetchone()[0])
                failed_verification = int(
                    conn.execute("SELECT COUNT(*) FROM action_verifications WHERE status IN ('failed','timed_out','unverified')").fetchone()[0]
                )
            except sqlite3.OperationalError:
                pending_verification = 0
                failed_verification = 0
    except Exception as exc:
        return {"installed": True, "error": str(exc)[:500]}
    return {
        "installed": True,
        "persistent_attention": True,
        "persistent_decisions": True,
        "deterministic_priority": True,
        "query_decision_projection": True,
        "permission_aware_proposals": True,
        "closed_loop_verification": True,
        "verification_reenters_priority": True,
        "term_conflicts_use_source_chronology": True,
        "recent_changes_use_source_chronology": True,
        "pending_verifications": pending_verification,
        "failed_or_unverified_outcomes": failed_verification,
        "open_attention_items": open_attention,
        "current_decisions": current_decisions,
        "last_refresh": str(row["value"]) if row else "",
    }
