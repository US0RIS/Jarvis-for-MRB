from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from jarvis_mrb.world_model import SELF_ID, assert_belief, ensure_entity, record_event


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def record_conversation_occurrence(
    session_id: str,
    user_text: str,
    assistant_text: str,
    *,
    occurred_at: str | None = None,
) -> int:
    """Record one actual conversation turn, even if its text repeats an earlier turn."""
    when = str(occurred_at or _now())[:100]
    occurrence_id = str(uuid.uuid4())
    user = " ".join(str(user_text or "").strip().split())[:6000]
    assistant = " ".join(str(assistant_text or "").strip().split())[:6000]
    session = str(session_id or "default")[:200]
    return record_event(
        "conversation.turn",
        f"User: {user[:700]}" + (f" | Jarvis: {assistant[:700]}" if assistant else ""),
        source_kind="conversation",
        source_ref=session,
        occurred_at=when,
        payload={
            "user": user,
            "assistant": assistant,
            "session_id": session,
            "occurrence_id": occurrence_id,
        },
        evidence="Direct Jarvis conversation transcript.",
        confidence=1.0,
        participants=[(SELF_ID, "speaker", 1.0)],
        event_key=f"conversation:{occurrence_id}",
    )


def record_visual_occurrence(
    scene: str,
    objects: Sequence[str],
    *,
    location_context: str = "unknown",
    confidence: float = 0.65,
    occurred_at: str | None = None,
    occurrence_ref: str | None = None,
) -> int:
    """Record one actual visual sighting without persisting the underlying frame."""
    when = str(occurred_at or _now())[:100]
    occurrence_id = str(occurrence_ref or uuid.uuid4())[:300]
    clean_scene = " ".join(str(scene or "").split())[:3000]
    location = " ".join(str(location_context or "unknown").split())[:300]
    score = max(0.0, min(float(confidence), 1.0))

    participants: list[tuple[str, str, float]] = [(SELF_ID, "observer", 1.0)]
    place_id: str | None = None
    if location.lower() not in {"", "unknown", "unknown location"}:
        place_id = ensure_entity("place", location, confidence=0.8)
        participants.append((place_id, "location", 0.8))

    object_ids: list[str] = []
    clean_objects: list[str] = []
    for name in list(objects)[:20]:
        clean_name = " ".join(str(name or "").split())[:240]
        if not clean_name:
            continue
        entity_id = ensure_entity("object", clean_name, confidence=score)
        object_ids.append(entity_id)
        clean_objects.append(clean_name)
        participants.append((entity_id, "observed", score))

    event_id = record_event(
        "perception.visual",
        clean_scene or "Visual observation",
        source_kind="rayban_camera",
        source_ref=occurrence_id,
        occurred_at=when,
        payload={
            "scene": clean_scene,
            "objects": clean_objects,
            "location": location,
            "occurrence_id": occurrence_id,
        },
        evidence="Derived from a Ray-Ban camera observation; raw frame is not persisted in the world model.",
        confidence=score,
        participants=participants,
        event_key=f"visual:{occurrence_id}",
    )

    for entity_id in object_ids:
        assert_belief(
            entity_id,
            "last_seen_at",
            value=when,
            confidence=score,
            source_event_id=event_id,
            evidence="Distinct visual occurrence",
        )
        if place_id:
            assert_belief(
                entity_id,
                "last_seen_at_place",
                object_id=place_id,
                confidence=score,
                source_event_id=event_id,
                evidence="Distinct visual occurrence",
            )
    return event_id
