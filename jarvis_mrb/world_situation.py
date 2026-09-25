from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH, SELF_ID
from jarvis_mrb.situation_evidence import compile_evidence

_SITUATION_CUES = (
    "before i go in",
    "before the meeting",
    "before my meeting",
    "prep me",
    "prepare me",
    "meeting prep",
    "who am i meeting",
    "who are we meeting",
    "what should i know before",
    "what do i need to know before",
    "anything i need to know",
    "anything i should know",
    "what's coming up",
    "what is coming up",
    "next meeting",
    "upcoming meeting",
)

_STOP = {
    "the", "and", "for", "with", "that", "this", "what", "when", "where", "who", "why", "how",
    "did", "does", "have", "has", "was", "were", "are", "from", "about", "into", "your", "you",
    "my", "our", "jarvis", "please", "tell", "show", "find", "search", "me", "meeting", "before",
    "anything", "need", "know", "should", "upcoming", "next", "prep", "prepare",
}

_REFRESH_LOCK = threading.RLock()
_LAST_REFRESH_MONOTONIC = 0.0
_NEAR_TERM_REFRESH_SECONDS = 120.0


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_.@'-]+", _normalize(value))
        if len(token) >= 3 and token not in _STOP
    }


def _loads(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _parse_time(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if "T" not in text and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.fromisoformat(text + "T00:00:00").astimezone()
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return value.astimezone() if value.tzinfo is not None else value.astimezone()
    except (TypeError, ValueError, OverflowError):
        try:
            value = parsedate_to_datetime(text)
            return value.astimezone() if value.tzinfo is not None else value.astimezone()
        except (TypeError, ValueError, OverflowError):
            return None


def is_situation_query(query: str) -> bool:
    normalized = _normalize(query)
    return any(cue in normalized for cue in _SITUATION_CUES)


def _refresh_near_term_if_needed() -> None:
    global _LAST_REFRESH_MONOTONIC
    now_mono = time.monotonic()
    with _REFRESH_LOCK:
        if now_mono - _LAST_REFRESH_MONOTONIC < _NEAR_TERM_REFRESH_SECONDS:
            return
        _LAST_REFRESH_MONOTONIC = now_mono
    try:
        from jarvis_mrb.world_calendar_sync import sync as sync_world_calendar

        result = sync_world_calendar(days_past=2, days_future=14, limit=50)
        if result.get("ok"):
            from jarvis_mrb.world_linker import refresh_links

            refresh_links(limit=500)
    except Exception:
        pass


def _latest_calendar_events(limit: int = 120) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE event_type='calendar.context_enriched' ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 300)),),
        ).fetchall()
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        source_ref = str(row["source_ref"] or "")
        if not source_ref or source_ref in seen:
            continue
        seen.add(source_ref)
        payload = _loads(str(row["payload_json"] or "{}"), {})
        if not isinstance(payload, dict):
            payload = {}
        payload["world_event_id"] = int(row["id"])
        payload["source_ref"] = source_ref
        payload["occurred_at"] = str(row["occurred_at"])
        result.append(payload)
    return result


def _participants(event_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT e.id,e.kind,e.canonical_name,ee.role,ee.confidence
            FROM event_entities ee
            JOIN entities e ON e.id=ee.entity_id
            WHERE ee.event_id=?
            ORDER BY ee.confidence DESC,e.kind,e.canonical_name
            """,
            (int(event_id),),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "kind": str(row["kind"]),
            "name": str(row["canonical_name"]),
            "role": str(row["role"]),
            "confidence": float(row["confidence"]),
        }
        for row in rows
    ]


def _temporal_score(event: dict[str, Any], now: datetime) -> tuple[float, str]:
    start = _parse_time(str(event.get("start") or event.get("occurred_at") or ""))
    end = _parse_time(str(event.get("end") or ""))
    if start is None:
        return (-50.0, "time unavailable")
    if end is None:
        end = start + timedelta(hours=1)
    if start <= now <= end:
        return (14.0, "happening now")
    delta_hours = (start - now).total_seconds() / 3600.0
    if 0 <= delta_hours <= 2:
        return (12.0, "starts within 2 hours")
    if 0 <= delta_hours <= 8:
        return (9.0, "starts within 8 hours")
    if 0 <= delta_hours <= 24:
        return (6.0, "starts within 24 hours")
    if 0 <= delta_hours <= 72:
        return (3.0, "starts within 3 days")
    if -4 <= delta_hours < 0:
        return (2.0, "recent meeting")
    return (0.0, "")


def _select_event(query: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    events = _latest_calendar_events()
    if not events:
        return (None, [], [])
    now = datetime.now().astimezone()
    query_tokens = _tokens(query)
    generic = is_situation_query(query)
    ranked: list[tuple[float, dict[str, Any], list[dict[str, Any]], list[str]]] = []

    for event in events:
        if _normalize(str(event.get("status") or "confirmed")) == "cancelled":
            continue
        event_id = int(event.get("world_event_id") or 0)
        participants = _participants(event_id) if event_id else []
        temporal, temporal_reason = _temporal_score(event, now)
        score = temporal
        reasons: list[str] = [temporal_reason] if temporal_reason else []

        title = str(event.get("title") or "")
        description = str(event.get("description") or "")
        location = str(event.get("location") or "")
        lexical = _tokens(title + " " + description + " " + location)
        overlap = len(query_tokens & lexical)
        if overlap:
            score += 5.0 * overlap
            reasons.append("query matches meeting")

        participant_match = False
        for participant in participants:
            participant_overlap = len(query_tokens & _tokens(str(participant.get("name") or "")))
            if participant_overlap:
                participant_match = True
                score += 7.0 * participant_overlap
                reasons.append(f"query matches {participant.get('name')}")

        start_raw = str(event.get("start") or event.get("occurred_at") or "")
        all_day = bool(start_raw and "T" not in start_raw)
        if generic and all_day and overlap == 0 and not participant_match:
            continue
        if generic and temporal <= 0 and overlap == 0 and not participant_match:
            continue
        if score > 0:
            ranked.append((score, event, participants, reasons))

    if not ranked:
        return (None, [], [])
    ranked.sort(key=lambda entry: entry[0], reverse=True)
    _score, event, participants, reasons = ranked[0]
    return (event, participants, reasons)


def _related_projects(entity_ids: set[str], limit: int = 8) -> list[dict[str, Any]]:
    if not entity_ids:
        return []
    placeholders = ",".join("?" for _ in entity_ids)
    params = tuple(entity_ids)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT p.id,p.canonical_name,r.predicate,r.confidence,r.evidence_count
            FROM entity_relations r
            JOIN entities p ON p.id=CASE WHEN r.subject_id IN ({placeholders}) THEN r.object_id ELSE r.subject_id END
            WHERE r.state='current'
              AND (r.subject_id IN ({placeholders}) OR r.object_id IN ({placeholders}))
              AND p.kind='project'
              AND r.confidence>=0.72
            ORDER BY r.confidence DESC,r.evidence_count DESC
            LIMIT ?
            """,
            (*params, *params, *params, max(1, min(int(limit), 20))),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "name": str(row["canonical_name"]),
            "predicate": str(row["predicate"]),
            "confidence": float(row["confidence"]),
            "evidence_count": int(row["evidence_count"]),
        }
        for row in rows
    ]


def _pending_commitments(person_ids: set[str], project_names: list[str], limit: int = 8) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM commitments WHERE status='pending' ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,due_at,updated_at DESC LIMIT 100"
        ).fetchall()
        result: list[dict[str, Any]] = []
        project_tokens = [_normalize(name) for name in project_names if name]
        for row in rows:
            owner_id = str(row["owner_id"] or "")
            action = str(row["action"])
            action_normalized = _normalize(action)
            owner_match = bool(owner_id and owner_id in person_ids)
            project_match = any(name in action_normalized for name in project_tokens)
            if not owner_match and not project_match:
                continue
            owner_name = ""
            if owner_id:
                owner = conn.execute("SELECT canonical_name FROM entities WHERE id=?", (owner_id,)).fetchone()
                owner_name = str(owner["canonical_name"]) if owner else ""
            result.append(
                {
                    "id": str(row["id"]),
                    "owner": owner_name,
                    "action": action,
                    "due": str(row["due_at"] or row["due_text"] or ""),
                    "confidence": float(row["confidence"]),
                }
            )
            if len(result) >= max(1, min(int(limit), 20)):
                break
    return result


def _linked_intentions(entity_ids: set[str], commitment_ids: set[str], limit: int = 5) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 12))
    intention_ids: set[str] = set()
    try:
        with _connect() as conn:
            if entity_ids:
                placeholders = ",".join("?" for _ in entity_ids)
                for row in conn.execute(
                    f"SELECT DISTINCT intention_id FROM intention_entities WHERE entity_id IN ({placeholders})",
                    tuple(entity_ids),
                ).fetchall():
                    intention_ids.add(str(row["intention_id"]))
            if commitment_ids:
                placeholders = ",".join("?" for _ in commitment_ids)
                for row in conn.execute(
                    f"SELECT DISTINCT intention_id FROM intention_commitments WHERE commitment_id IN ({placeholders})",
                    tuple(commitment_ids),
                ).fetchall():
                    intention_ids.add(str(row["intention_id"]))
            if not intention_ids:
                return []
            placeholders = ",".join("?" for _ in intention_ids)
            rows = conn.execute(
                f"""
                SELECT id,title,next_action,due_at,confidence
                FROM intentions
                WHERE status='active' AND id IN ({placeholders})
                ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,due_at,updated_at DESC
                LIMIT ?
                """,
                (*tuple(intention_ids), safe_limit),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "next_action": str(row["next_action"]),
                "due": str(row["due_at"] or ""),
                "confidence": float(row["confidence"]),
            }
            for row in rows
        ]
    except sqlite3.Error:
        return []


def _recent_evidence(entity_ids: set[str], selected_event_id: int, limit: int = 10) -> list[dict[str, Any]]:
    if not entity_ids:
        return []
    placeholders = ",".join("?" for _ in entity_ids)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT ev.id,ev.event_type,ev.occurred_at,ev.summary,ev.source_kind,ev.source_ref,ev.confidence
            FROM event_entities ee
            JOIN events ev ON ev.id=ee.event_id
            WHERE ee.entity_id IN ({placeholders})
              AND ev.id!=?
              AND ev.event_type NOT IN ('action.tool','calendar.context_enriched','context.environment','context.conversation_mode')
            ORDER BY ev.id DESC
            LIMIT 120
            """,
            (*tuple(entity_ids), int(selected_event_id)),
        ).fetchall()

    cutoff = datetime.now().astimezone() - timedelta(days=45)
    result: list[dict[str, Any]] = []
    for row in rows:
        occurred = str(row["occurred_at"])
        parsed = _parse_time(occurred)
        if parsed is not None and parsed < cutoff:
            continue
        result.append(
            {
                "id": int(row["id"]),
                "type": str(row["event_type"]),
                "time": occurred,
                "summary": str(row["summary"]),
                "source": f"{row['source_kind']}:{row['source_ref']}",
                "confidence": float(row["confidence"]),
            }
        )
        if len(result) >= max(1, min(int(limit), 30)):
            break
    return result


def compile_situation(
    query: str, *, phone_mission: dict[str, Any] | None = None,
    resolved_place: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not is_situation_query(query):
        return None
    _refresh_near_term_if_needed()
    event, participants, reasons = _select_event(query)
    if event is None:
        return None

    person_ids = {
        str(item.get("id"))
        for item in participants
        if item.get("kind") == "person" and item.get("id") != SELF_ID
    }
    base_ids = {
        str(item.get("id"))
        for item in participants
        if item.get("id") and item.get("id") != SELF_ID
    }
    projects = _related_projects(base_ids)
    project_ids = {str(item["id"]) for item in projects}
    all_ids = base_ids | project_ids
    commitments = _pending_commitments(person_ids, [str(item["name"]) for item in projects])
    commitment_ids = {str(item["id"]) for item in commitments}
    intentions = _linked_intentions(all_ids, commitment_ids, limit=5)
    recent = _recent_evidence(all_ids, int(event.get("world_event_id") or 0), limit=10)
    # The additional modules have separate privacy/authority boundaries.
    # Read existing evidence only; never evaluate Guardian or sense a camera,
    # and never pretend phone-local Mission Control is PC-readable.
    cross_source = compile_evidence(
        event, intentions, projects,
        phone_mission=phone_mission, resolved_place=resolved_place,
    )

    return {
        "meeting": event,
        "participants": participants,
        "projects": projects,
        "intentions": intentions,
        "commitments": commitments,
        "recent_evidence": recent,
        "cross_source_evidence": cross_source,
        "selection_reasons": reasons,
    }


def context_for_query(
    query: str, *, phone_mission: dict[str, Any] | None = None,
    resolved_place: dict[str, Any] | None = None,
) -> str:
    situation = compile_situation(
        query, phone_mission=phone_mission, resolved_place=resolved_place,
    )
    if not situation:
        return ""
    meeting = situation["meeting"]
    lines = ["CURRENT/UPCOMING SITUATION (calendar-selected, graph-connected private context):"]
    title = str(meeting.get("title") or "(untitled event)")
    start = str(meeting.get("start") or meeting.get("occurred_at") or "")
    location = str(meeting.get("location") or "")
    lines.append(f"- Meeting: {title}; start: {start}" + (f"; location: {location}" if location else ""))
    if situation.get("selection_reasons"):
        lines.append("- Selected because: " + ", ".join(str(v) for v in situation["selection_reasons"][:3]))

    people = [
        f"{item.get('name')} ({item.get('role')})"
        for item in situation.get("participants") or []
        if item.get("kind") == "person" and item.get("id") != SELF_ID
    ]
    if people:
        lines.append("- People: " + ", ".join(people[:12]))
    projects = [str(item.get("name")) for item in situation.get("projects") or [] if item.get("name")]
    if projects:
        lines.append("- Connected projects: " + ", ".join(projects[:6]))

    for item in (situation.get("intentions") or [])[:5]:
        detail = f"- Active objective: {item.get('title')}"
        if item.get("next_action"):
            detail += f"; next: {item.get('next_action')}"
        if item.get("due"):
            detail += f"; due: {item.get('due')}"
        lines.append(detail)

    for item in (situation.get("commitments") or [])[:6]:
        owner = f"{item.get('owner')}: " if item.get("owner") else ""
        due = f" (due {item.get('due')})" if item.get("due") else ""
        lines.append(f"- Pending obligation: {owner}{item.get('action')}{due}")

    cross_source = situation.get("cross_source_evidence") or {}
    sections = cross_source.get("sections") or {}
    if any(sections.values()):
        lines.append("ADDITIONAL SOURCE-QUALIFIED, EVENT-RELATED EVIDENCE:")
    for item in (sections.get("guardian") or [])[:4]:
        lines.append(
            f"- [Guardian enrolled watch {item['watch_id']} | last evaluated "
            f"{item['observed_at']}] {item['title']}: {item['signal']}; "
            f"due {item['deadline_at']}. {item['qualifier']}"
        )
    for item in (sections.get("life_fabric") or [])[:6]:
        lines.append(
            f"- [Life Fabric user-enrolled task {item['task_id']} | "
            f"{item['link']}] {item['title']}: {item['due_state']}; "
            f"completion {item['completion_state']}; "
            f"blocked {item['blocked']}. {item['qualifier']}"
        )
    for item in (sections.get("mission_control") or [])[:1]:
        lines.append(
            f"- [iPhone Mission Control | phone snapshot {item['observed_at']}] "
            f"Exact-event mission phase {item['phase']}; {item['qualifier']}"
        )
    for item in (sections.get("reality_lens") or [])[:4]:
        lines.append(
            f"- [Reality Lens saved snapshots | {item['observed_at']} | "
            f"provider {item['provider']}] {item['label']}: "
            f"{item['before']} -> {item['after']}. {item['qualifier']}"
        )
    statuses = cross_source.get("source_status") or {}
    missing = []
    if statuses.get("mission_control") == "phone_local_not_shared":
        missing.append("phone-local Mission Control was not shared")
    if statuses.get("reality_lens") == "exact_place_not_linked":
        missing.append("the calendar has no verified Reality Lens place match")
    if missing:
        lines.append("- Coverage limits: " + "; ".join(missing)
                     + ". No all-clear may be inferred.")
    evidence = situation.get("recent_evidence") or []
    if evidence:
        lines.append("RECENT CONNECTED EVIDENCE:")
        for item in evidence[:8]:
            lines.append(f"- [{item.get('time')} | {item.get('source')}] {item.get('summary')}")
    return "\n".join(lines)[:12000]


def status() -> dict[str, Any]:
    events = _latest_calendar_events(limit=300)
    now = datetime.now().astimezone()
    upcoming = 0
    for event in events:
        if _normalize(str(event.get("status") or "confirmed")) == "cancelled":
            continue
        start = _parse_time(str(event.get("start") or event.get("occurred_at") or ""))
        if start is not None and now - timedelta(hours=4) <= start <= now + timedelta(days=7):
            upcoming += 1
    return {
        "enriched_calendar_events": len(events),
        "near_term_events": upcoming,
        "situation_compiler": True,
        "uses_attendee_identity_graph": True,
        "uses_connected_projects_commitments": True,
        "uses_linked_intentions": True,
        "near_term_refresh_seconds": int(_NEAR_TERM_REFRESH_SECONDS),
        "cancelled_events_excluded": True,
        "generic_all_day_events_excluded": True,
        "recent_evidence_parses_iso_and_rfc_dates": True,
        "additional_source_qualified_evidence": True,
        "guardian_read_only_no_alert_emission": True,
        "life_fabric_only_linked_manual_tasks": True,
        "iphone_mission_auto_sync": False,
        "lens_location_label_only_join": False,
    }
