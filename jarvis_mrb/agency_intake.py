"""Ordinary-language goal intake for Agency.

Previously an explicit goal ("My goal is to ...") became a *paused* desired
state and only started if the user already knew the internal phrase
"agency activate <goal>".  That made persistent pursuit depend on the user
acting as Jarvis's orchestration layer.

Now, when a user states an explicit goal, Jarvis records it and *asks* whether
to pursue it.  Pursuit is still a security-class authority expansion that
crosses the normal confirmation boundary, and every protected step inside the
plan still stops for its own approval.
"""

from __future__ import annotations

from typing import Any


def pursue(query: str) -> dict[str, Any]:
    """Activate one exact goal and make sure the Agency runtime is running."""
    from jarvis_mrb.agency_runtime import activate_matching, get_mode, set_mode

    state = activate_matching(query)
    mode = get_mode()
    if mode != "active":
        set_mode("active")
    return {"state": state, "previous_mode": mode, "mode": "active"}


def declared_goal_offer(text: str, *, session_id: str = "default") -> dict[str, Any] | None:
    """Record an explicit goal declaration and return what to offer, if any."""
    from jarvis_mrb.world_intent_capture import capture, extract_declarations

    declarations = [item for item in extract_declarations(text) if item.get("kind") == "explicit_goal"]
    if not declarations:
        return None
    capture(text, session_id=session_id)
    try:
        from jarvis_mrb.world_executive import refresh_intentions
        refresh_intentions()
    except Exception:
        pass
    from jarvis_mrb.agency_runtime import find_desired_state
    from jarvis_mrb.desired_state import sync_from_intentions

    sync_from_intentions()
    action = str(declarations[0]["action"])
    state = find_desired_state(action)
    return {
        "action": action,
        "desired_state_id": str((state or {}).get("id") or ""),
        "title": str((state or {}).get("title") or action),
        "already_active": bool(state and str(state.get("state")) == "active"
                               and (state.get("authority") or {}).get("agency_enabled") is True),
    }
