from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

import dateparser

from jarvis_mrb.world_model import SELF_ID, assert_belief, ensure_entity, record_event

_DECLARATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("explicit_goal", r"\b(?:our|my) (?:current )?goal is (?:to )?(.+?)(?:[.!?]|$)"),
    ("explicit_goal", r"\bthe goal is (?:to )?(.+?)(?:[.!?]|$)"),
    ("trying", r"\bwe(?:'re| are) trying to (.+?)(?:[.!?]|$)"),
    ("trying", r"\bi(?:'m| am) trying to (.+?)(?:[.!?]|$)"),
)

_HYPOTHETICAL_PREFIXES = (
    "if ",
    "what if ",
    "suppose ",
    "imagine ",
    "could we ",
    "should we ",
    "are we ",
    "am i ",
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _clean_action(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    text = re.sub(r"\s+(?:please|thanks|thank you)$", "", text, flags=re.IGNORECASE)
    return text[:1000].strip(" ,;:-")


def _plausibly_persistent(kind: str, action: str) -> bool:
    normalized = _normalize(action)
    if len(normalized.split()) < 3 or len(normalized) < 12:
        return False
    if any(normalized.startswith(prefix) for prefix in _HYPOTHETICAL_PREFIXES):
        return False
    if re.search(r"\b(?:not|never) trying to\b", normalized):
        return False
    # Explicit "goal" language is sufficient. "Trying to" is also an explicit
    # persistence signal, but reject trivial immediate-state phrases that should not
    # become durable executive objectives.
    if kind == "explicit_goal":
        return True
    transient = (
        "fall asleep",
        "go to sleep",
        "remember a word",
        "think of a word",
        "decide what to eat",
        "choose what to eat",
    )
    return not any(phrase in normalized for phrase in transient)


def _due_from_action(action: str) -> tuple[str | None, str]:
    # Only parse an explicit trailing/near-trailing deadline phrase. Do not infer a
    # due date from unrelated dates elsewhere in the sentence.
    match = re.search(
        r"\b(?:by|before)\s+((?:this|next)\s+(?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|tomorrow|tonight|(?:\w+\s+)?\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)\b",
        action,
        flags=re.IGNORECASE,
    )
    if not match:
        return (None, "")
    due_text = match.group(1).strip()[:120]
    parsed = dateparser.parse(
        due_text,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "RELATIVE_BASE": datetime.now().astimezone(),
        },
    )
    if parsed is None:
        return (None, due_text)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return (parsed.isoformat(), due_text)


def _goal_key(action: str) -> str:
    digest = hashlib.sha256(_normalize(action).encode("utf-8", errors="replace")).hexdigest()[:32]
    return f"conversation-goal-{digest}"


def extract_declarations(text: str) -> list[dict[str, Any]]:
    raw = " ".join(str(text or "").strip().split())
    if not raw or raw.rstrip().endswith("?"):
        return []
    normalized = _normalize(raw)
    if any(normalized.startswith(prefix) for prefix in _HYPOTHETICAL_PREFIXES):
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kind, pattern in _DECLARATION_PATTERNS:
        for match in re.finditer(pattern, raw, flags=re.IGNORECASE):
            action = _clean_action(match.group(1))
            if not _plausibly_persistent(kind, action):
                continue
            key = _normalize(action)
            if key in seen:
                continue
            seen.add(key)
            due_at, due_text = _due_from_action(action)
            results.append(
                {
                    "kind": kind,
                    "action": action,
                    "due_at": due_at,
                    "due_text": due_text,
                    "confidence": 1.0,
                }
            )
            if len(results) >= 3:
                return results
    return results


def capture(text: str, *, session_id: str = "default") -> list[int]:
    declarations = extract_declarations(text)
    event_ids: list[int] = []
    for declaration in declarations:
        action = str(declaration["action"])
        external_id = _goal_key(action)
        goal_id = ensure_entity(
            "goal",
            action,
            external_namespace="conversation_goal",
            external_id=external_id,
            attributes={
                "origin": "explicit_conversation_declaration",
                "session_id": str(session_id or "default")[:128],
                "due_text": str(declaration.get("due_text") or ""),
            },
            confidence=1.0,
        )
        event_id = record_event(
            "goal.conversation_declared",
            f"Explicit conversational goal: {action}",
            source_kind="conversation_goal",
            source_ref=external_id,
            payload={
                "goal_id": external_id,
                "action": action,
                "due_at": declaration.get("due_at"),
                "due_text": declaration.get("due_text"),
                "session_id": str(session_id or "default")[:128],
            },
            evidence="Direct user declaration using explicit goal/trying-to language.",
            confidence=1.0,
            participants=[(SELF_ID, "owner", 1.0), (goal_id, "goal", 1.0)],
        )
        assert_belief(goal_id, "status", value="active", source_event_id=event_id, evidence="Explicit user goal declaration")
        assert_belief(goal_id, "next_action", value="", source_event_id=event_id, evidence="No next action explicitly supplied")
        if declaration.get("due_at"):
            assert_belief(goal_id, "due_at", value=str(declaration["due_at"]), source_event_id=event_id, evidence=str(declaration.get("due_text") or ""))
        assert_belief(SELF_ID, "pursues", object_id=goal_id, source_event_id=event_id, cardinality="multi")
        event_ids.append(event_id)
    return event_ids


def status() -> dict[str, Any]:
    return {
        "enabled": True,
        "accepted_forms": ["my/our goal is ...", "the goal is ...", "I/we are trying to ..."],
        "questions_ignored": True,
        "hypotheticals_ignored": True,
        "ordinary_wants_ignored": True,
        "deadline_parsing": "explicit by/before phrases only",
    }
