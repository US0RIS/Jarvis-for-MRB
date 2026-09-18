from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

from jarvis_mrb.world_model import DB_PATH


_PROCESS_INSTANCE_ID = str(uuid.uuid4())
DEFAULT_EVALUATION_INTERVAL_SECONDS = 60


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
            last_action_at TEXT,
            next_evaluation_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    runtime_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(agency_runtime_state)").fetchall()
    }
    if "last_action_at" not in runtime_columns:
        conn.execute(
            "ALTER TABLE agency_runtime_state ADD COLUMN last_action_at TEXT"
        )
    if "next_evaluation_at" not in runtime_columns:
        conn.execute(
            "ALTER TABLE agency_runtime_state ADD COLUMN next_evaluation_at TEXT"
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agency_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agency_runtime_boots (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            deployment_sha TEXT NOT NULL DEFAULT '',
            process_id INTEGER NOT NULL DEFAULT 0,
            process_instance_id TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agency_runtime_boots_started "
        "ON agency_runtime_boots(started_at DESC)"
    )
    boot_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(agency_runtime_boots)").fetchall()
    }
    if "process_instance_id" not in boot_columns:
        conn.execute(
            "ALTER TABLE agency_runtime_boots "
            "ADD COLUMN process_instance_id TEXT NOT NULL DEFAULT ''"
        )
    conn.commit()
    return conn


def record_boot(*, deployment_sha: str = "") -> dict[str, Any]:
    boot_id = f"agency-boot:{uuid.uuid4()}"
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_runtime_boots(
                id,started_at,deployment_sha,process_id,process_instance_id
            ) VALUES(?,?,?,?,?)
            """,
            (
                boot_id,
                now,
                str(deployment_sha or "")[:80],
                int(os.getpid()),
                _PROCESS_INSTANCE_ID,
            ),
        )
        conn.commit()
    return {
        "id": boot_id,
        "started_at": now,
        "deployment_sha": str(deployment_sha or "")[:80],
        "process_id": int(os.getpid()),
        "process_instance_id": _PROCESS_INSTANCE_ID,
    }


def latest_boot() -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agency_runtime_boots ORDER BY started_at DESC,rowid DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_mode() -> str:
    default = str(os.environ.get("JARVIS_AGENCY_MODE", "monitor") or "monitor").strip().lower()
    if default not in {"off", "monitor", "active"}:
        default = "monitor"
    with _connect() as conn:
        row = conn.execute("SELECT value FROM agency_settings WHERE key='mode'").fetchone()
    if row is None:
        return default
    value = str(row["value"] or "").strip().lower()
    return value if value in {"off", "monitor", "active"} else default


def set_mode(mode: str) -> str:
    clean = str(mode or "").strip().lower()
    if clean not in {"off", "monitor", "active"}:
        raise ValueError("Agency mode must be off, monitor, or active.")
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_settings(key,value,updated_at) VALUES('mode',?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
            """,
            (clean, now),
        )
        conn.commit()
    try:
        from jarvis_mrb.world_model import record_event
        record_event(
            "agency.mode_changed",
            f"Agency mode changed to {clean}.",
            source_kind="jarvis_agency",
            source_ref=f"agency-mode:{now}",
            payload={"mode": clean},
            evidence="Explicit Agency runtime mode change.",
            confidence=1.0,
        )
    except Exception:
        pass
    return clean


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
            "last_action_at": "",
            "next_evaluation_at": "",
        }
    return dict(row)


def _update_runtime(
    desired_state_id: str,
    *,
    planner_success: bool | None = None,
    error: str = "",
    tick: bool = False,
    action: bool = False,
) -> None:
    now = _now()
    current = _runtime_state(desired_state_id)
    failures = int(current.get("consecutive_planner_failures") or 0)
    last_planning = current.get("last_planning_attempt_at")
    next_planning = current.get("next_planning_attempt_at")
    last_error = str(current.get("last_error") or "")
    last_action_at = current.get("last_action_at")
    next_evaluation_at = current.get("next_evaluation_at")
    if tick:
        next_evaluation_at = (
            _now_dt() + timedelta(seconds=DEFAULT_EVALUATION_INTERVAL_SECONDS)
        ).isoformat()
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
                next_planning_attempt_at,last_error,last_tick_at,last_action_at,
                next_evaluation_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(desired_state_id) DO UPDATE SET
                consecutive_planner_failures=excluded.consecutive_planner_failures,
                last_planning_attempt_at=excluded.last_planning_attempt_at,
                next_planning_attempt_at=excluded.next_planning_attempt_at,
                last_error=excluded.last_error,
                last_tick_at=excluded.last_tick_at,
                last_action_at=excluded.last_action_at,
                next_evaluation_at=excluded.next_evaluation_at,
                updated_at=excluded.updated_at
            """,
            (
                str(desired_state_id),
                failures,
                last_planning,
                next_planning,
                last_error,
                now if tick else current.get("last_tick_at"),
                now if action else last_action_at,
                next_evaluation_at,
                now,
            ),
        )
        conn.commit()


def reset_planner_backoff(desired_state_id: str) -> None:
    """Clear retry delay after an external blocker has genuinely been removed."""
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_runtime_state(
                desired_state_id,consecutive_planner_failures,next_planning_attempt_at,
                last_error,updated_at
            ) VALUES(?,0,NULL,'',?)
            ON CONFLICT(desired_state_id) DO UPDATE SET
                consecutive_planner_failures=0,
                next_planning_attempt_at=NULL,
                last_error='',
                updated_at=excluded.updated_at
            """,
            (str(desired_state_id), now),
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
    if not normalized:
        return ""
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
    try:
        from jarvis_mrb.agency_self_model import compact_context as self_model_context
        self_context = self_model_context(max_chars=5000)
    except Exception:
        self_context = ""

    return (
        "Create the smallest feasible tool plan that advances this persistent desired state. "
        "The plan is not complete until the success conditions become true in the world model. "
        "Prefer observations before interventions, preserve reversibility, and do not assume a write succeeded merely because its API returned success. "
        "When a consequential choice still has materially different plausible approaches after evidence gathering, include agency.deliberate before the consequential write so independent evidence/skeptic/feasibility/risk workers can preserve disagreement. "
        "Do not add deliberation to routine or obvious actions merely to make the plan longer.\n"
        f"Desired state: {desired.get('title')}\n"
        f"Explicit success criteria: {json.dumps(desired.get('criteria') or [], ensure_ascii=False, sort_keys=True)}\n"
        f"Currently unmet criteria: {json.dumps(missing, ensure_ascii=False, sort_keys=True)}"
        f"{previous_text}"
        + (
            "\n\nExplicit/inferred user decision context (guidance only; NEVER authority):\n"
            + self_context
            + "\nPermission policy remains the sole action-authority source even if a preference or self-model policy suggests otherwise."
            if self_context
            else ""
        )
    )[:12000]


def _handle_declared_capability_gap(
    desired_state_id: str,
    missing: dict[str, Any],
    *,
    set_state: Callable[..., dict[str, Any]],
) -> None:
    capability = " ".join(str(missing.get("capability") or "").split())[:500]
    reason_detail = " ".join(str(missing.get("reason") or "").split())[:2500]
    if not capability or not reason_detail:
        raise ValueError("Planner declared an invalid missing capability.")

    from jarvis_mrb.agency_capability import available_tool, record_gap

    availability = available_tool(capability)
    if not bool(availability.get("known")):
        record_gap(
            str(desired_state_id),
            capability,
            reason_detail,
        )
        reason = f"Missing capability: {capability}. {reason_detail}"
    elif bool(availability.get("agency_scope_blocked")):
        reason = (
            f"Agency scope does not permit {capability}; the capability exists but is "
            f"intentionally excluded from autonomous workflows. {reason_detail}"
        )
    elif bool(availability.get("authority_blocked")):
        reason = f"Permission policy currently denies Agency use of {capability}. {reason_detail}"
    else:
        # A planner may not declare a tool missing if the bounded Agency registry
        # already exposes and authorizes it. Treat that as a planner error.
        raise ValueError(
            f"Planner declared available Agency tool {capability!r} as a missing capability."
        )
    set_state(str(desired_state_id), "blocked", reason=reason)


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
        from jarvis_mrb.workflow_engine import _validate_plan
        _validate_plan(workflow)
        missing = workflow.get("missing_capability")
        if isinstance(missing, dict):
            _handle_declared_capability_gap(
                str(desired_state_id),
                missing,
                set_state=set_state,
            )
            _update_runtime(str(desired_state_id), planner_success=True)
            return None
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
        error = str(exc)
        unsupported = re.search(r"unsupported tool ['\\\"]([^'\\\"]+)['\\\"]", error, flags=re.IGNORECASE)
        if unsupported:
            missing_tool = unsupported.group(1).strip()
            reason = f"Agency planner requested unsupported tool {missing_tool}."
            try:
                from jarvis_mrb.agency_capability import available_tool, record_gap

                availability = available_tool(missing_tool)
                if not bool(availability.get("known")):
                    try:
                        record_gap(
                            str(desired_state_id),
                            missing_tool,
                            f"The planner requires tool {missing_tool!r}, but Jarvis has no implemented Agency capability for it.",
                        )
                    except Exception as gap_exc:
                        reason = (
                            f"Missing capability: {missing_tool}. "
                            f"Capability-gap persistence also failed: {gap_exc}"
                        )
                    else:
                        reason = f"Missing capability: {missing_tool}."
                elif bool(availability.get("agency_scope_blocked")):
                    reason = (
                        f"Agency scope does not permit {missing_tool}; the tool may exist for direct use "
                        "but is intentionally excluded from autonomous workflows."
                    )
                elif bool(availability.get("authority_blocked")):
                    reason = f"Permission policy currently denies Agency use of {missing_tool}."
                else:
                    reason = f"Agency could not use known tool {missing_tool}."
            except Exception as capability_exc:
                reason = (
                    f"Agency planner requested unsupported tool {missing_tool}; "
                    f"capability inspection failed: {capability_exc}"
                )

            try:
                set_state(str(desired_state_id), "blocked", reason=reason)
            except Exception as block_exc:
                combined = (
                    f"{error}; additionally failed to persist blocked state for "
                    f"{missing_tool}: {block_exc}"
                )
                _update_runtime(
                    str(desired_state_id),
                    planner_success=False,
                    error=combined,
                )
                raise RuntimeError(combined) from block_exc
        _update_runtime(str(desired_state_id), planner_success=False, error=error)
        return None


def tick_desired_state(
    desired_state_id: str,
    *,
    executor: Callable[..., Any],
    planner: Callable[[str], dict[str, Any]] | None = None,
    allow_action: bool = True,
    allow_planning: bool = True,
) -> dict[str, Any]:
    from jarvis_mrb.agency_plan import current_plan, execute_next, reconcile_plan
    from jarvis_mrb.desired_state import evaluate_desired_state, get_desired_state

    state_id = str(desired_state_id)
    _update_runtime(state_id, tick=True)
    mode = get_mode()
    if mode != "active":
        return {
            "desired_state_id": state_id,
            "status": f"mode_{mode}",
            "action_executed": False,
        }
    desired = get_desired_state(state_id)
    if desired is None:
        return {"desired_state_id": state_id, "status": "missing"}
    authority = desired.get("authority") if isinstance(desired.get("authority"), dict) else {}
    if authority.get("agency_enabled") is not True:
        return {
            "desired_state_id": state_id,
            "status": "authority_disabled",
            "action_executed": False,
        }
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

    if plan is None or str(plan.get("status") or "") in {"needs_replan", "blocked", "completed"}:
        if not allow_planning:
            return {
                "desired_state_id": state_id,
                "status": "monitoring",
                "plan": plan,
                "evaluation": evaluation,
                "action_executed": False,
            }
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
    max_plans: int = 4,
    limit: int = 50,
) -> dict[str, Any]:
    from jarvis_mrb.desired_state import list_desired_states

    if executor is None:
        import jarvis_mrb.agent as agent_module
        executor = agent_module.execute_tool

    mode = get_mode()
    if mode == "off":
        return {
            "mode": mode,
            "desired_states_checked": 0,
            "candidate_pool": 0,
            "actions_executed": 0,
            "action_budget": 0,
            "planning_attempts": 0,
            "planning_budget": 0,
            "results": [],
        }

    action_budget = max(0, min(int(max_actions), 10)) if mode == "active" else 0
    planning_budget = max(0, min(int(max_plans), 20)) if mode == "active" else 0
    window_limit = max(1, min(int(limit), 200))

    # Load a broader pool than the per-cycle evaluation window. Otherwise a stable
    # ORDER BY priority DESC LIMIT N permanently starves goal N+1.
    candidates: list[dict[str, Any]] = []
    for desired in list_desired_states(limit=500):
        if str(desired.get("state") or "") not in {"active", "satisfied"}:
            continue
        authority = desired.get("authority") if isinstance(desired.get("authority"), dict) else {}
        if authority.get("agency_enabled") is not True:
            continue
        candidates.append(desired)

    runtime_by_id: dict[str, dict[str, Any]] = {}
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT desired_state_id,last_tick_at,last_action_at
            FROM agency_runtime_state
            """
        ).fetchall()
    for row in rows:
        runtime_by_id[str(row["desired_state_id"])] = {
            "last_tick_at": str(row["last_tick_at"] or ""),
            "last_action_at": str(row["last_action_at"] or ""),
        }

    def timestamp_for(state_id: str, field: str) -> float:
        raw = str((runtime_by_id.get(state_id) or {}).get(field) or "")
        parsed = _parse_time(raw)
        return parsed.timestamp() if parsed is not None else float("-inf")

    def priority(item: dict[str, Any]) -> float:
        return float(item.get("priority") or 0.0)

    selected: list[dict[str, Any]] = []
    active_candidates = [
        item for item in candidates
        if str(item.get("state") or "") == "active"
    ]
    satisfied_candidates = [
        item for item in candidates
        if str(item.get("state") or "") == "satisfied"
    ]

    def tick_age_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            items,
            key=lambda item: (
                timestamp_for(str(item.get("id") or ""), "last_tick_at"),
                -priority(item),
                str(item.get("id") or ""),
            ),
        )

    if active_candidates:
        max_priority = max(priority(item) for item in active_candidates)
        top_priority = [
            item for item in active_candidates
            if priority(item) == max_priority
        ]
        champion = min(
            top_priority,
            key=lambda item: (
                timestamp_for(str(item.get("id") or ""), "last_tick_at"),
                str(item.get("id") or ""),
            ),
        )
        selected.append(champion)
        active_remaining = [
            item for item in active_candidates
            if str(item.get("id")) != str(champion.get("id"))
        ]
        selected.extend(
            tick_age_order(active_remaining)[: max(0, window_limit - len(selected))]
        )

    if len(selected) < window_limit and satisfied_candidates:
        selected_ids = {str(item.get("id") or "") for item in selected}
        satisfied_remaining = [
            item for item in satisfied_candidates
            if str(item.get("id") or "") not in selected_ids
        ]
        selected.extend(
            tick_age_order(satisfied_remaining)[: max(0, window_limit - len(selected))]
        )

    if not selected and candidates:
        selected.extend(tick_age_order(candidates)[:window_limit])

    # Within the rotating evaluation window, allocate scarce action opportunities
    # using a separate action-age clock. The highest-priority selected goal gets
    # first opportunity, then longest-waiting goals get the remaining slots.
    ordered: list[dict[str, Any]] = []
    if selected:
        actionable_selected = [
            item for item in selected
            if str(item.get("state") or "") == "active"
        ]
        action_pool = actionable_selected or selected
        selected_max_priority = max(priority(item) for item in action_pool)
        selected_top = [
            item for item in action_pool
            if priority(item) == selected_max_priority
        ]
        action_champion = min(
            selected_top,
            key=lambda item: (
                timestamp_for(str(item.get("id") or ""), "last_action_at"),
                str(item.get("id") or ""),
            ),
        )
        ordered.append(action_champion)

        remaining = [
            item for item in selected
            if str(item.get("id")) != str(action_champion.get("id"))
        ]
        remaining.sort(
            key=lambda item: (
                timestamp_for(str(item.get("id") or ""), "last_action_at"),
                -priority(item),
                str(item.get("id") or ""),
            )
        )
        ordered.extend(remaining)

    from jarvis_mrb.agency_plan import current_plan

    actions = 0
    planning_attempts = 0
    results: list[dict[str, Any]] = []
    for desired in ordered:
        state_id = str(desired["id"])
        existing = current_plan(state_id, include_steps=False)
        needs_planning = bool(
            str(desired.get("state") or "") == "active"
            and (
                existing is None
                or str(existing.get("status") or "")
                in {"needs_replan", "blocked", "completed"}
            )
        )
        planning_due = bool(
            needs_planning and _planning_allowed(state_id)
        )
        permit_planning = bool(
            mode == "active"
            and (
                not planning_due
                or planning_attempts < planning_budget
            )
        )
        if planning_due and permit_planning:
            planning_attempts += 1

        result = tick_desired_state(
            state_id,
            executor=executor,
            planner=planner,
            allow_action=mode == "active" and actions < action_budget,
            allow_planning=permit_planning,
        )
        if result.get("action_executed"):
            actions += 1
        results.append(result)
    return {
        "mode": mode,
        "desired_states_checked": len(results),
        "candidate_pool": len(candidates),
        "actions_executed": actions,
        "action_budget": action_budget,
        "planning_attempts": planning_attempts,
        "planning_budget": planning_budget,
        "results": results,
    }


def _normalize(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def find_desired_state(query: str) -> dict[str, Any] | None:
    from jarvis_mrb.desired_state import list_desired_states

    needle = _normalize(query)
    if not needle:
        return None
    states = list_desired_states(include_retired=False, limit=200)
    exact = [
        item for item in states
        if _normalize(str(item.get("id") or "")) == needle
        or _normalize(str(item.get("title") or "")) == needle
    ]
    if len(exact) == 1:
        return exact[0]
    partial = [
        item for item in states
        if needle in _normalize(str(item.get("title") or ""))
        or needle in _normalize(str(item.get("id") or ""))
    ]
    return partial[0] if len(partial) == 1 else None


def activate_matching(
    query: str,
    *,
    contract_compiler: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = find_desired_state(query)
    if state is None:
        raise ValueError("Agency could not uniquely identify that desired state.")
    state_id = str(state["id"])
    from jarvis_mrb.agency_goal_compiler import ensure_observable_contract

    ensure_observable_contract(state_id, compiler=contract_compiler)
    return reactivate(state_id)


def pause_matching(query: str) -> dict[str, Any]:
    from jarvis_mrb.desired_state import set_state, update_authority

    state = find_desired_state(query)
    if state is None:
        raise ValueError("Agency could not uniquely identify that desired state.")
    state_id = str(state["id"])
    update_authority(state_id, {"agency_enabled": False})
    return set_state(state_id, "paused")


def reactivate(desired_state_id: str) -> dict[str, Any]:
    from jarvis_mrb.desired_state import set_state, update_authority

    state_id = str(desired_state_id)
    update_authority(state_id, {"agency_enabled": True})
    state = set_state(state_id, "active")
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
    from jarvis_mrb.agency_capability import list_gaps
    from jarvis_mrb.agency_plan import current_plan
    from jarvis_mrb.desired_state import list_desired_states

    states = list_desired_states(limit=50)
    if not states:
        return "Agency has no persistent desired states."
    open_gaps = list_gaps(open_only=True)
    gaps_by_state: dict[str, list[dict[str, Any]]] = {}
    for gap in open_gaps:
        state_id = str(gap.get("desired_state_id") or "")
        if state_id:
            gaps_by_state.setdefault(state_id, []).append(gap)

    parts: list[str] = []
    for state in states:
        state_id = str(state["id"])
        plan = current_plan(state_id, include_steps=True)
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

        extras: list[str] = []
        blocked_reason = " ".join(str(state.get("blocked_reason") or "").split())
        if blocked_reason:
            extras.append(f"blocked reason: {blocked_reason[:500]}")
        gaps = gaps_by_state.get(state_id, [])
        if gaps:
            rendered_gaps = ", ".join(
                f"{gap.get('capability')} ({gap.get('id')}, {gap.get('status')})"
                for gap in gaps[:5]
            )
            extras.append(f"capability gaps: {rendered_gaps}")
        extra_text = "; " + "; ".join(extras) if extras else ""
        parts.append(f"{state['title']} [{state['state']}; {plan_text}{extra_text}]")
    return "Agency: " + "; ".join(parts)


def status() -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agency_runtime_state ORDER BY updated_at DESC LIMIT 100"
        ).fetchall()
    return {
        "ready": True,
        "mode": get_mode(),
        "tracked": len(rows),
        "planner_backoff": [dict(row) for row in rows],
    }
