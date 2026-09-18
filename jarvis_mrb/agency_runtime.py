from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable

from jarvis_mrb.world_model import DB_PATH


def _now_dt() -> datetime:
    return datetime.now().astimezone()


def _now() -> str:
    return _now_dt().isoformat()


def _parse_time(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agency_runtime_state (
            desired_state_id TEXT PRIMARY KEY,
            consecutive_planner_failures INTEGER NOT NULL DEFAULT 0,
            last_planning_attempt_at TEXT,
            next_planning_attempt_at TEXT,
            last_error TEXT NOT NULL DEFAULT '',
            last_tick_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _runtime_state(desired_state_id: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agency_runtime_state WHERE desired_state_id=?",
            (str(desired_state_id),),
        ).fetchone()
    if row is None:
        return {
            "desired_state_id": str(desired_state_id),
            "consecutive_planner_failures": 0,
            "last_planning_attempt_at": "",
            "next_planning_attempt_at": "",
            "last_error": "",
            "last_tick_at": "",
        }
    return dict(row)


def _update_runtime(
    desired_state_id: str,
    *,
    planner_success: bool | None = None,
    error: str = "",
    tick: bool = False,
) -> None:
    now = _now()
    current = _runtime_state(desired_state_id)
    failures = int(current.get("consecutive_planner_failures") or 0)
    last_planning = current.get("last_planning_attempt_at")
    next_planning = current.get("next_planning_attempt_at")
    last_error = str(current.get("last_error") or "")
    if planner_success is True:
        failures = 0
        last_planning = now
        next_planning = None
        last_error = ""
    elif planner_success is False:
        failures += 1
        last_planning = now
        delay_seconds = min(3600, 30 * (2 ** min(failures - 1, 7)))
        next_planning = (_now_dt() + timedelta(seconds=delay_seconds)).isoformat()
        last_error = str(error or "Planning failed.")[:3000]

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_runtime_state(
                desired_state_id,consecutive_planner_failures,last_planning_attempt_at,
                next_planning_attempt_at,last_error,last_tick_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(desired_state_id) DO UPDATE SET
                consecutive_planner_failures=excluded.consecutive_planner_failures,
                last_planning_attempt_at=excluded.last_planning_attempt_at,
                next_planning_attempt_at=excluded.next_planning_attempt_at,
                last_error=excluded.last_error,
                last_tick_at=excluded.last_tick_at,
                updated_at=excluded.updated_at
            """,
            (
                str(desired_state_id),
                failures,
                last_planning,
                next_planning,
                last_error,
                now if tick else current.get("last_tick_at"),
                now,
            ),
        )
        conn.commit()


def _planning_allowed(desired_state_id: str) -> bool:
    state = _runtime_state(desired_state_id)
    retry = _parse_time(str(state.get("next_planning_attempt_at") or ""))
    return retry is None or retry <= _now_dt()


def _workflow_signature(plan: dict[str, Any]) -> str:
    nodes = plan.get("nodes") if isinstance(plan, dict) else None
    normalized: list[dict[str, Any]] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        normalized.append(
            {
                "id": str(node.get("id") or ""),
                "tool": str(node.get("tool") or ""),
                "arguments": node.get("arguments") if isinstance(node.get("arguments"), dict) else {},
                "depends_on": sorted(str(value) for value in (node.get("depends_on") or [])),
            }
        )
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _existing_signature(plan: dict[str, Any] | None) -> str:
    if not plan:
        return ""
    steps = plan.get("steps") or []
    id_to_key = {str(step.get("id") or ""): str(step.get("step_key") or "") for step in steps}
    nodes: list[dict[str, Any]] = []
    for step in steps:
        nodes.append(
            {
                "id": str(step.get("step_key") or ""),
                "tool": str(step.get("tool") or ""),
                "arguments": dict(step.get("arguments") or {}),
                "depends_on": sorted(
                    id_to_key.get(str(dep), str(dep))
                    for dep in (step.get("depends_on") or [])
                ),
            }
        )
    return _workflow_signature({"nodes": nodes})


def _planner_prompt(desired: dict[str, Any], evaluation: dict[str, Any], previous: dict[str, Any] | None) -> str:
    missing = evaluation.get("missing") or []
    previous_text = ""
    if previous:
        failed_steps = [
            {
                "step": step.get("step_key"),
                "tool": step.get("tool"),
                "status": step.get("status"),
                "result": str(step.get("result_summary") or "")[:800],
                "blocked_reason": str(step.get("blocked_reason") or "")[:800],
            }
            for step in (previous.get("steps") or [])
            if str(step.get("status") or "") in {"failed", "blocked"}
        ]
        previous_text = (
            "\nPrevious plan generation "
            + str(previous.get("generation"))
            + " ended as "
            + str(previous.get("status"))
            + ". Do not blindly repeat a failed path. Failure details: "
            + json.dumps(failed_steps, ensure_ascii=False, sort_keys=True)
        )
    return (
        "Create the smallest feasible tool plan that advances this persistent desired state. "
        "The plan is not complete until the success conditions become true in the world model. "
        "Prefer observations before interventions, preserve reversibility, and do not assume a write succeeded merely because its API returned success.\n"
        f"Desired state: {desired.get('title')}\n"
        f"Explicit success criteria: {json.dumps(desired.get('criteria') or [], ensure_ascii=False, sort_keys=True)}\n"
        f"Currently unmet criteria: {json.dumps(missing, ensure_ascii=False, sort_keys=True)}"
        f"{previous_text}"
    )[:12000]


def compile_plan(
    desired_state_id: str,
    *,
    planner: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    from jarvis_mrb.agency_plan import create_plan_from_workflow, current_plan
    from jarvis_mrb.desired_state import evaluate_desired_state, get_desired_state, set_state

    desired = get_desired_state(str(desired_state_id))
    if desired is None:
        raise ValueError(f"Unknown desired state {desired_state_id!r}.")
    if str(desired.get("state") or "") != "active":
        return None
    if not _planning_allowed(str(desired_state_id)):
        return None

    evaluation = evaluate_desired_state(str(desired_state_id), persist=True)
    if evaluation["satisfied"]:
        return None

    previous = current_plan(str(desired_state_id), include_steps=True)
    if planner is None:
        from jarvis_mrb.workflow_engine import plan_workflow
        planner = plan_workflow

    prompt = _planner_prompt(desired, evaluation, previous)
    try:
        workflow = planner(prompt)
        if not isinstance(workflow, dict):
            raise ValueError("Planner returned a non-object plan.")
        signature = _workflow_signature(workflow)
        if not signature:
            raise ValueError("Planner returned no executable nodes.")
        if previous and str(previous.get("status") or "") in {"needs_replan", "blocked"}:
            if signature == _existing_signature(previous):
                reason = "Replanner produced the same failed plan; a new capability, observation, or user decision is required."
                set_state(str(desired_state_id), "blocked", reason=reason)
                _update_runtime(str(desired_state_id), planner_success=False, error=reason)
                return None
        plan = create_plan_from_workflow(str(desired_state_id), workflow)
        _update_runtime(str(desired_state_id), planner_success=True)
        return plan
    except Exception as exc:
        _update_runtime(str(desired_state_id), planner_success=False, error=str(exc))
        return None


def tick_desired_state(
    desired_state_id: str,
    *,
    executor: Callable[..., Any],
    planner: Callable[[str], dict[str, Any]] | None = None,
    allow_action: bool = True,
) -> dict[str, Any]:
    from jarvis_mrb.agency_plan import current_plan, execute_next, reconcile_plan
    from jarvis_mrb.desired_state import evaluate_desired_state, get_desired_state

    state_id = str(desired_state_id)
    _update_runtime(state_id, tick=True)
    desired = get_desired_state(state_id)
    if desired is None:
        return {"desired_state_id": state_id, "status": "missing"}
    lifecycle = str(desired.get("state") or "")
    if lifecycle in {"paused", "blocked", "retired"}:
        return {"desired_state_id": state_id, "status": lifecycle}

    evaluation = evaluate_desired_state(state_id, persist=True)
    if evaluation["satisfied"]:
        plan = current_plan(state_id, include_steps=True)
        if plan:
            plan = reconcile_plan(str(plan["id"]))
        return {
            "desired_state_id": state_id,
            "status": "satisfied",
            "plan": plan,
            "evaluation": evaluation,
            "action_executed": False,
        }

    plan = current_plan(state_id, include_steps=True)
    if plan and str(plan.get("status") or "") in {"awaiting_verification", "active"}:
        plan = reconcile_plan(str(plan["id"]))

    if plan is None or str(plan.get("status") or "") in {"needs_replan", "blocked"}:
        planned = compile_plan(state_id, planner=planner)
        if planned is not None:
            plan = planned
        else:
            refreshed = get_desired_state(state_id)
            return {
                "desired_state_id": state_id,
                "status": str((refreshed or {}).get("state") or "planning_deferred"),
                "plan": current_plan(state_id, include_steps=True),
                "evaluation": evaluation,
                "action_executed": False,
                "runtime": _runtime_state(state_id),
            }

    plan_status = str(plan.get("status") or "")
    if plan_status in {"awaiting_approval", "awaiting_verification", "completed", "superseded"}:
        return {
            "desired_state_id": state_id,
            "status": plan_status,
            "plan": plan,
            "evaluation": evaluation,
            "action_executed": False,
        }

    if not allow_action:
        return {
            "desired_state_id": state_id,
            "status": plan_status,
            "plan": plan,
            "evaluation": evaluation,
            "action_executed": False,
        }

    before_attempts = sum(int(step.get("attempt_count") or 0) for step in (plan.get("steps") or []))
    updated = execute_next(str(plan["id"]), executor)
    after_attempts = sum(int(step.get("attempt_count") or 0) for step in (updated.get("steps") or []))
    return {
        "desired_state_id": state_id,
        "status": str(updated.get("status") or ""),
        "plan": updated,
        "evaluation": evaluate_desired_state(state_id, persist=True),
        "action_executed": after_attempts > before_attempts,
    }


def tick_all(
    *,
    executor: Callable[..., Any] | None = None,
    planner: Callable[[str], dict[str, Any]] | None = None,
    max_actions: int = 2,
    limit: int = 50,
) -> dict[str, Any]:
    from jarvis_mrb.desired_state import list_desired_states

    if executor is None:
        import jarvis_mrb.agent as agent_module
        executor = agent_module.execute_tool

    action_budget = max(0, min(int(max_actions), 10))
    actions = 0
    results: list[dict[str, Any]] = []
    for desired in list_desired_states(limit=max(1, min(int(limit), 200))):
        if str(desired.get("state") or "") not in {"active", "satisfied"}:
            continue
        result = tick_desired_state(
            str(desired["id"]),
            executor=executor,
            planner=planner,
            allow_action=actions < action_budget,
        )
        if result.get("action_executed"):
            actions += 1
        results.append(result)
    return {
        "desired_states_checked": len(results),
        "actions_executed": actions,
        "action_budget": action_budget,
        "results": results,
    }


def reactivate(desired_state_id: str) -> dict[str, Any]:
    from jarvis_mrb.desired_state import set_state

    state = set_state(str(desired_state_id), "active")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_runtime_state(
                desired_state_id,consecutive_planner_failures,last_error,updated_at
            ) VALUES(?,0,'',?)
            ON CONFLICT(desired_state_id) DO UPDATE SET
                consecutive_planner_failures=0,
                next_planning_attempt_at=NULL,
                last_error='',
                updated_at=excluded.updated_at
            """,
            (str(desired_state_id), _now()),
        )
        conn.commit()
    return state


def describe() -> str:
    from jarvis_mrb.agency_plan import current_plan
    from jarvis_mrb.desired_state import list_desired_states

    states = list_desired_states(limit=50)
    if not states:
        return "Agency has no persistent desired states."
    parts: list[str] = []
    for state in states:
        plan = current_plan(str(state["id"]), include_steps=True)
        plan_text = "no plan"
        if plan:
            open_steps = [
                step for step in (plan.get("steps") or [])
                if str(step.get("status") or "") not in {"verified", "skipped"}
            ]
            next_step = open_steps[0] if open_steps else None
            plan_text = f"plan {plan.get('status')} generation {plan.get('generation')}"
            if next_step:
                plan_text += f", next {next_step.get('step_key')}={next_step.get('status')}:{next_step.get('tool')}"
        parts.append(f"{state['title']} [{state['state']}; {plan_text}]")
    return "Agency: " + "; ".join(parts)


def status() -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agency_runtime_state ORDER BY updated_at DESC LIMIT 100"
        ).fetchall()
    return {
        "ready": True,
        "tracked": len(rows),
        "planner_backoff": [dict(row) for row in rows],
    }
