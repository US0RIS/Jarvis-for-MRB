from __future__ import annotations

"""Conservative, event-driven opportunities grounded in *explicit* user goals.

This is not a general AI-autonomy grant. The first narrow bridge turns a fresh
first-person sighting into a useful, low-risk observation when the user already
asked Jarvis to find that exact object. It never actuates hardware, treats image
text as instructions, or starts a camera. More ambitious affordance->action
policies must be explicit, individually enrolled and verified.
"""

import re
from typing import Any

from jarvis_mrb.environment_state import get_state

_OBJECT_GOAL = re.compile(
    r"^(?:please\s+)?(?:find|locate|look for|help me find|help me locate)"
    r"\s+(?:my|the)\s+([a-z0-9][a-z0-9 '-]{0,77}[a-z0-9])"
    r"[.!?]?\s*$",
    re.IGNORECASE,
)
_DISALLOWED = frozenset({
    "person", "people", "someone", "anyone", "child", "children", "stranger",
    "face", "faces", "driver", "passenger", "neighbor", "neighbour",
})


def _normalize_object(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9 '-]", " ", str(value or "").lower()).split()).strip(" '-")[:80]


def _object_sought(intention: dict[str, Any]) -> str:
    # No broad semantic guessing: the exact user-provided Find/Locate goal or
    # explicit next action is required. A generic "find good options" goal is
    # not a license to interpret passing camera frames.
    for value in (intention.get("title"), intention.get("next_action")):
        text = " ".join(str(value or "").split())
        match = _OBJECT_GOAL.fullmatch(text)
        if not match:
            continue
        target = _normalize_object(match.group(1))
        if not target or target in _DISALLOWED:
            continue
        if len(target.split()) > 5 or len(target) > 70:
            continue
        return target
    return ""


def consider_object_sighting(
    object_name: str,
    *,
    location_context: str,
    confidence: float,
) -> list[dict[str, Any]]:
    """Surface an explicit object-finding goal on a fresh glasses observation.

    Emission is through Agency Attention's durable per-goal dedup and the
    existing companion alert channel. A sighting is a *model inference*, not
    proof that the object is the user's or that it remains there.
    """
    name = _normalize_object(object_name)
    if not name or name in _DISALLOWED:
        return []
    if not 0.0 <= confidence <= 1.0 or confidence < 0.60:
        return []

    state = get_state()
    prefs = state.get("preferences") if isinstance(state.get("preferences"), dict) else {}
    devices = state.get("devices") if isinstance(state.get("devices"), dict) else {}
    if prefs.get("proactive_monitoring", True) is False:
        return []
    if str(state.get("active_profile") or "").lower() == "driving":
        return []
    # The caller normally runs only inside the active vision worker. If a
    # companion explicitly reports a camera/privacy latch, honor it here too.
    if devices.get("camera_master_enabled") is False or devices.get("passive_vision") is False:
        return []

    from jarvis_mrb.world_executive import active_intentions
    from jarvis_mrb.agency_attention import consider

    location = " ".join(str(location_context or "unknown").split())[:160]
    where = (
        f" near {location}"
        if location.lower() not in {"", "unknown", "unknown location"}
        else " in your current glasses view"
    )
    matches = []
    for goal in active_intentions(limit=30):
        sought = _object_sought(goal)
        if sought != name:
            continue
        goal_id = str(goal.get("id") or "")
        if not goal_id or str(goal.get("confidence", 1.0)) and float(goal.get("confidence", 1.0)) < 0.7:
            continue
        # Don't tell the user an object has been "found"; Moondream's
        # identification and ownership are not independently verified.
        message = f"I may have spotted {sought}{where}. The glasses model identified it just now."
        result = consider(
            kind="visual_object_opportunity",
            message=message,
            desired_state_id=goal_id,
            dedup_key=f"object-opportunity:{goal_id}:{sought}:{location.lower()}",
            benefit=95,
            urgency=40,
            confidence=min(confidence, 0.70),
            error_cost=8,
            attention_cost=12,
            threshold=55,
            severity="warning",
            dedup_seconds=6 * 3600,
        )
        matches.append({"goal_id": goal_id, "object": sought, **result})
    return matches
