from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


def _compact(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    shortened = text[: max(1, limit - 3)].rsplit(" ", 1)[0].rstrip()
    return shortened + "..."


def _parse_time(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return value.astimezone() if value.tzinfo is not None else value.astimezone()
    except (TypeError, ValueError, OverflowError):
        return None


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _meaningful_recent_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_prefixes = (
        "term.changed_or_conflicted",
        "document.version_changed",
        "knowledge.gmail",
        "knowledge.note",
        "knowledge.meeting",
        "meeting.completed",
        "meeting.started",
        "journal.generated",
        "expense.captured",
    )
    return [
        item for item in items
        if str(item.get("type") or "").startswith(allowed_prefixes)
    ]


def _evidence_priority(item: dict[str, Any]) -> int:
    event_type = str(item.get("type") or "")
    if event_type.startswith("term.changed_or_conflicted"):
        return 0
    if event_type.startswith("document.version_changed"):
        return 1
    return 2


def _deduplicate_document_changes(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suppress a generic document-diff alert when a term conflict already explains it.

    Project-term conflicts are often generated from the exact attachment events that
    also produce document.version_changed. Showing both wastes one of the two prebrief
    fact slots and makes one substantive change look like two independent warnings.
    We retain the more actionable term discrepancy and suppress only document diffs
    whose underlying older/newer source events overlap that discrepancy.
    """
    term_ids = [
        int(item.get("id") or 0)
        for item in items
        if str(item.get("type") or "").startswith("term.changed_or_conflicted") and int(item.get("id") or 0) > 0
    ]
    document_ids = [
        int(item.get("id") or 0)
        for item in items
        if str(item.get("type") or "").startswith("document.version_changed") and int(item.get("id") or 0) > 0
    ]
    if not term_ids or not document_ids:
        return items

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        term_placeholders = ",".join("?" for _ in term_ids)
        doc_placeholders = ",".join("?" for _ in document_ids)
        term_rows = conn.execute(
            f"SELECT id,payload_json FROM events WHERE id IN ({term_placeholders})",
            tuple(term_ids),
        ).fetchall()
        doc_rows = conn.execute(
            f"SELECT id,payload_json FROM events WHERE id IN ({doc_placeholders})",
            tuple(document_ids),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return items

    term_source_events: set[int] = set()
    for row in term_rows:
        payload = _loads(str(row["payload_json"] or "{}"))
        for side in ("older", "newer"):
            value = payload.get(side)
            if isinstance(value, dict):
                try:
                    source_event_id = int(value.get("source_event_id") or 0)
                except (TypeError, ValueError):
                    source_event_id = 0
                if source_event_id:
                    term_source_events.add(source_event_id)

    covered_document_events: set[int] = set()
    for row in doc_rows:
        payload = _loads(str(row["payload_json"] or "{}"))
        lineage_events: set[int] = set()
        for side in ("older", "newer"):
            value = payload.get(side)
            if isinstance(value, dict):
                try:
                    event_id = int(value.get("event_id") or 0)
                except (TypeError, ValueError):
                    event_id = 0
                if event_id:
                    lineage_events.add(event_id)
        if lineage_events & term_source_events:
            covered_document_events.add(int(row["id"]))

    if not covered_document_events:
        return items
    return [
        item for item in items
        if not (
            str(item.get("type") or "").startswith("document.version_changed")
            and int(item.get("id") or 0) in covered_document_events
        )
    ]


def build(event_id: str, summary: str) -> dict[str, Any] | None:
    """Build one compact proactive pre-brief only when useful context exists."""
    title = " ".join(str(summary or "your next event").split())[:300]
    try:
        from jarvis_mrb.world_situation import compile_situation

        situation = compile_situation(f"Prepare me for {title}")
    except Exception:
        return None
    if not situation:
        return None

    meeting = situation.get("meeting") or {}
    selected_id = str(meeting.get("source_ref") or meeting.get("calendar_event_id") or "")
    if event_id and selected_id and selected_id != str(event_id):
        return None

    commitments = list(situation.get("commitments") or [])
    intentions = list(situation.get("intentions") or [])
    raw_recent = _meaningful_recent_evidence(list(situation.get("recent_evidence") or []))
    raw_recent.sort(key=_evidence_priority)
    recent = _deduplicate_document_changes(raw_recent)

    facts: list[str] = []
    severity = "info"

    # A provenance-bearing disagreement in an explicit project term is more urgent
    # than a generic task reminder: it can change the substance of the meeting. It is
    # phrased as a conflict/change, never as a declaration that one source is true.
    for item in recent:
        if not str(item.get("type") or "").startswith("term.changed_or_conflicted"):
            continue
        summary_text = _compact(str(item.get("summary") or ""), 200)
        if summary_text:
            facts.append(f"Term discrepancy: {summary_text}")
            severity = "warning"
            break

    for item in commitments[:2]:
        if len(facts) >= 2:
            break
        owner = str(item.get("owner") or "").strip()
        action = _compact(str(item.get("action") or ""), 150)
        if not action:
            continue
        due = str(item.get("due") or "").strip()
        due_time = _parse_time(due)
        if due_time is not None and due_time <= datetime.now().astimezone():
            severity = "warning"
        prefix = f"{owner} still owes " if owner else "Still pending: "
        facts.append(prefix + action)

    if len(facts) < 2:
        for item in intentions[:2]:
            next_action = _compact(str(item.get("next_action") or ""), 150)
            if not next_action:
                continue
            facts.append(f"Your next action for {item.get('title')}: {next_action}")
            if len(facts) >= 2:
                break

    if len(facts) < 2:
        for item in recent:
            if str(item.get("type") or "").startswith("term.changed_or_conflicted"):
                continue
            summary_text = _compact(str(item.get("summary") or ""), 175)
            if not summary_text:
                continue
            if str(item.get("type") or "").startswith("document.version_changed"):
                facts.append(f"A connected draft changed: {summary_text}")
                severity = "warning"
            else:
                facts.append(f"Recent connected update: {summary_text}")
            if len(facts) >= 2:
                break

    if not facts:
        return None

    message = f"Before {title}: " + " ".join(facts[:2])
    return {
        "message": _compact(message, 430),
        "severity": severity,
        "meeting_id": selected_id or str(event_id),
        "facts": facts[:2],
        "has_commitments": bool(commitments),
        "has_intentions": bool(intentions),
        "has_recent_evidence": bool(recent),
        "has_document_change": any(str(item.get("type") or "").startswith("document.version_changed") for item in recent),
        "has_term_conflict": any(str(item.get("type") or "").startswith("term.changed_or_conflicted") for item in recent),
        "deduplicated_evidence_count": max(0, len(raw_recent) - len(recent)),
    }


def status() -> dict[str, Any]:
    return {
        "enabled": True,
        "deterministic": True,
        "requires_actionable_world_context": True,
        "prioritizes_cross_source_term_conflicts": True,
        "prioritizes_document_version_changes": True,
        "deduplicates_term_conflict_underlying_document_diff": True,
        "max_facts": 2,
        "max_message_chars": 430,
    }
