from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from jarvis_mrb.world_model import (
    SELF_ID,
    assert_belief,
    ensure_entity,
    record_environment_snapshot,
    record_event,
    record_meeting_finish,
    record_meeting_start,
)

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
_SENTINEL = APP_DIR / "world_model_backfill_v1.complete"


def _rows(path: Path, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def _backfill_conversations() -> int:
    path = APP_DIR / "conversation.sqlite3"
    rows = _rows(
        path,
        "SELECT id,session_id,role,content,created_at FROM conversation_messages ORDER BY session_id,id",
    )
    count = 0
    pending_user: sqlite3.Row | None = None
    pending_session = ""

    for row in rows:
        session_id = str(row["session_id"] or "default")
        role = str(row["role"] or "")
        if role == "user":
            if pending_user is not None:
                record_event(
                    "conversation.turn",
                    f"User: {' '.join(str(pending_user['content'] or '').split())[:1400]}",
                    source_kind="conversation_backfill",
                    source_ref=f"message:{pending_user['id']}",
                    occurred_at=str(pending_user["created_at"] or ""),
                    payload={
                        "session_id": pending_session,
                        "user": str(pending_user["content"] or "")[:12000],
                        "assistant": "",
                    },
                    evidence="Backfilled from the durable Jarvis conversation database.",
                    participants=[(SELF_ID, "speaker", 1.0)],
                )
                count += 1
            pending_user = row
            pending_session = session_id
            continue

        if role == "assistant" and pending_user is not None and pending_session == session_id:
            user_text = str(pending_user["content"] or "")
            assistant_text = str(row["content"] or "")
            record_event(
                "conversation.turn",
                f"User: {' '.join(user_text.split())[:700]} | Jarvis: {' '.join(assistant_text.split())[:700]}",
                source_kind="conversation_backfill",
                source_ref=f"messages:{pending_user['id']}:{row['id']}",
                occurred_at=str(pending_user["created_at"] or row["created_at"] or ""),
                payload={
                    "session_id": session_id,
                    "user": user_text[:12000],
                    "assistant": assistant_text[:12000],
                    "assistant_at": str(row["created_at"] or ""),
                },
                evidence="Backfilled from the durable Jarvis conversation database.",
                participants=[(SELF_ID, "speaker", 1.0)],
            )
            count += 1
            pending_user = None
            pending_session = ""

    if pending_user is not None:
        record_event(
            "conversation.turn",
            f"User: {' '.join(str(pending_user['content'] or '').split())[:1400]}",
            source_kind="conversation_backfill",
            source_ref=f"message:{pending_user['id']}",
            occurred_at=str(pending_user["created_at"] or ""),
            payload={"session_id": pending_session, "user": str(pending_user["content"] or "")[:12000], "assistant": ""},
            evidence="Backfilled from the durable Jarvis conversation database.",
            participants=[(SELF_ID, "speaker", 1.0)],
        )
        count += 1
    return count


def _backfill_episodic() -> int:
    path = APP_DIR / "episodic_memory.sqlite3"
    rows = _rows(
        path,
        "SELECT id,created_at,session_id,kind,content FROM episodes ORDER BY id",
    )
    count = 0
    for row in rows:
        kind = str(row["kind"] or "memory")
        # Conversation turns are already imported from the canonical conversation
        # DB where individual message timestamps and session sequencing are clearer.
        if kind == "conversation":
            continue
        content = str(row["content"] or "").strip()
        if not content:
            continue
        record_event(
            f"legacy_memory.{kind}",
            " ".join(content.split())[:2200],
            source_kind="episodic_backfill",
            source_ref=f"episode:{row['id']}",
            occurred_at=str(row["created_at"] or ""),
            payload={"session_id": str(row["session_id"] or ""), "kind": kind, "content": content[:12000]},
            evidence="Backfilled from Jarvis semantic episodic memory; source provenance may be less specific than native world-model events.",
            confidence=0.85,
            participants=[(SELF_ID, "related", 0.8)],
        )
        count += 1
    return count


def _backfill_spatial() -> int:
    path = APP_DIR / "spatial_memory.sqlite3"
    rows = _rows(
        path,
        "SELECT id,seen_at,object_name,location_context,scene,confidence FROM object_sightings ORDER BY id",
    )
    count = 0
    for row in rows:
        name = " ".join(str(row["object_name"] or "").split())
        if not name:
            continue
        confidence = max(0.0, min(float(row["confidence"] or 0.5), 1.0))
        object_id = ensure_entity("object", name, confidence=confidence)
        location = " ".join(str(row["location_context"] or "unknown").split())
        participants: list[tuple[str, str, float]] = [(SELF_ID, "observer", 1.0), (object_id, "observed", confidence)]
        place_id: str | None = None
        if location and location.lower() not in {"unknown", "unknown location"}:
            place_id = ensure_entity("place", location, confidence=0.8)
            participants.append((place_id, "location", 0.8))
        event_id = record_event(
            "perception.visual",
            str(row["scene"] or f"Observed {name}"),
            source_kind="spatial_backfill",
            source_ref=f"sighting:{row['id']}",
            occurred_at=str(row["seen_at"] or ""),
            payload={"objects": [name], "location": location, "scene": str(row["scene"] or "")[:3000]},
            evidence="Backfilled from Jarvis spatial last-seen memory; raw imagery was not retained.",
            confidence=confidence,
            participants=participants,
        )
        assert_belief(object_id, "last_seen_at", value=str(row["seen_at"] or ""), confidence=confidence, source_event_id=event_id)
        if place_id:
            assert_belief(object_id, "last_seen_at_place", object_id=place_id, confidence=confidence, source_event_id=event_id)
        count += 1
    return count


def _parse_actions(value: Any) -> list[dict[str, str]]:
    try:
        raw = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        task = " ".join(str(item.get("task") or "").split())
        if not task:
            continue
        result.append({
            "owner": " ".join(str(item.get("owner") or "unspecified").split())[:120],
            "task": task[:500],
            "due": " ".join(str(item.get("due") or "").split())[:160],
            "evidence": " ".join(str(item.get("evidence") or "").split())[:300],
        })
    return result


def _backfill_meetings() -> int:
    path = APP_DIR / "meeting_notes.sqlite3"
    rows = _rows(
        path,
        "SELECT id,started_at,ended_at,title,status,transcript,action_items_json FROM meetings ORDER BY id",
    )
    count = 0
    for row in rows:
        meeting_id = int(row["id"])
        title = str(row["title"] or "")
        started_at = str(row["started_at"] or "")
        record_meeting_start(meeting_id, title, started_at)
        if str(row["status"] or "") == "completed" or row["ended_at"]:
            record_meeting_finish(
                meeting_id,
                title,
                str(row["ended_at"] or started_at),
                _parse_actions(row["action_items_json"]),
                transcript_excerpt=str(row["transcript"] or "")[-6000:],
            )
        count += 1
    return count


def _backfill_environment() -> int:
    path = APP_DIR / "environment_state.json"
    if not path.exists():
        return 0
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(state, dict):
        return 0
    record_environment_snapshot(state, source_ref="environment_backfill")
    return 1


def backfill_existing_state(*, force: bool = False) -> dict[str, Any]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if _SENTINEL.exists() and not force:
        return {"ok": True, "skipped": True, "reason": "world-model v1 backfill already completed"}

    result: dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "conversations": 0,
        "episodic": 0,
        "spatial": 0,
        "meetings": 0,
        "environment": 0,
        "errors": [],
    }
    steps = (
        ("conversations", _backfill_conversations),
        ("episodic", _backfill_episodic),
        ("spatial", _backfill_spatial),
        ("meetings", _backfill_meetings),
        ("environment", _backfill_environment),
    )
    for name, function in steps:
        try:
            result[name] = int(function())
        except Exception as exc:
            result["ok"] = False
            result["errors"].append(f"{name}: {exc}")

    record_event(
        "system.world_backfill",
        "Jarvis imported its pre-world-model local history into the persistent world graph.",
        source_kind="system",
        source_ref="world_model_backfill_v1",
        payload={key: value for key, value in result.items() if key != "errors"},
        evidence="One-time local migration over existing Jarvis databases.",
        confidence=1.0,
    )

    if result["ok"]:
        _SENTINEL.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
