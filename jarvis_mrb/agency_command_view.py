from __future__ import annotations

"""Read-only, source-grounded command view for the iPhone / future MemoMind HUD.

This is *not* a separate agent or a new permission surface. It summarizes
persisted Agency facts only; callers cannot approve or execute work here.
"""

from datetime import datetime
from typing import Any


_OPEN_STEP_STATES = {"pending", "awaiting_approval", "executing", "executed", "awaiting_verification", "failed", "blocked"}


def build_command_view(*, goal_limit: int = 5, attention_limit: int = 3) -> dict[str, Any]:
    from jarvis_mrb.agency_attention import list_events
    from jarvis_mrb.agency_plan import current_plan
    from jarvis_mrb.agency_runtime import get_mode
    from jarvis_mrb.desired_state import list_desired_states

    all_goals = list_desired_states(limit=500)
    nonretired = [item for item in all_goals if str(item.get("state") or "") != "retired"]
    rank = {"active": 0, "blocked": 1, "paused": 2, "satisfied": 3}
    ordered = sorted(
        nonretired,
        key=lambda item: (
            rank.get(str(item.get("state") or ""), 4),
            -float(item.get("priority") or 0),
            str(item.get("title") or ""),
        ),
    )
    goal_rows: list[dict[str, Any]] = []
    pending_approvals: list[dict[str, Any]] = []
    for goal in ordered:
        goal_id = str(goal.get("id") or "")
        plan = current_plan(goal_id, include_steps=True)
        steps = list((plan or {}).get("steps") or [])
        open_steps = [
            step for step in steps
            if str(step.get("status") or "") in _OPEN_STEP_STATES
        ]
        next_step = open_steps[0] if open_steps else None
        for step in steps:
            if str(step.get("status") or "") == "awaiting_approval":
                pending_approvals.append(
                    {
                        "goal_id": goal_id,
                        "goal": str(goal.get("title") or "")[:150],
                        "step_id": str(step.get("id") or ""),
                        "tool": str(step.get("tool") or "")[:100],
                        "summary": str(step.get("result_summary") or "")[:240],
                    }
                )
        if len(goal_rows) < max(1, min(int(goal_limit), 20)):
            goal_rows.append(
                {
                    "id": goal_id,
                    "title": str(goal.get("title") or "")[:150],
                    "state": str(goal.get("state") or ""),
                    "priority": float(goal.get("priority") or 0),
                    "evaluated_at": str(goal.get("last_evaluated_at") or ""),
                    "plan_status": str((plan or {}).get("status") or "no_plan"),
                    "step_count": len(steps),
                    "verified_steps": sum(1 for step in steps if str(step.get("status") or "") == "verified"),
                    "next_step": (
                        {
                            "tool": str(next_step.get("tool") or "")[:100],
                            "status": str(next_step.get("status") or ""),
                            "step_key": str(next_step.get("step_key") or "")[:120],
                        }
                        if next_step else None
                    ),
                }
            )

    emitted = [
        event for event in list_events(limit=100)
        if int(event.get("emitted_count") or 0) > 0
    ][: max(0, min(int(attention_limit), 10))]
    alerts = [
        {
            "message": str(event.get("message") or "")[:280],
            "severity": str(event.get("severity") or "info"),
            "seen_at": str(event.get("last_seen_at") or ""),
            "rationale": str(event.get("rationale") or "")[:280],
        }
        for event in emitted
    ]
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": "persisted_agency",
        "mode": get_mode(),
        "total_goals": len(nonretired),
        "active_goals": sum(1 for goal in nonretired if goal.get("state") == "active"),
        "blocked_goals": sum(1 for goal in nonretired if goal.get("state") == "blocked"),
        "pending_approval_count": len(pending_approvals),
        "pending_approvals": pending_approvals[:10],
        "goals": goal_rows,
        "recent_alerts": alerts,
        "read_only": True,
    }
