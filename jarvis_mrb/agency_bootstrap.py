from __future__ import annotations

from typing import Any


def prepare(*, sync_goals: bool = True) -> dict[str, Any]:
    """Initialize every durable Agency subsystem without executing autonomous actions."""
    from jarvis_mrb import (
        agency_attention,
        agency_capability,
        agency_counterfactual,
        agency_deliberation,
        agency_plan,
        agency_runtime,
        agency_self_model,
        agency_real_acceptance,
        agency_release,
        desired_state,
    )

    result: dict[str, Any] = {
        "ok": True,
        "desired_state": {},
        "plans": {},
        "runtime": {},
        "attention": {},
        "capability": {},
        "counterfactual": {},
        "deliberation": {},
        "self_model": {},
        "real_acceptance": {},
        "release": {},
        "goal_sync": {},
        "errors": [],
    }
    modules = (
        ("desired_state", desired_state),
        ("plans", agency_plan),
        ("runtime", agency_runtime),
        ("attention", agency_attention),
        ("capability", agency_capability),
        ("counterfactual", agency_counterfactual),
        ("deliberation", agency_deliberation),
        ("self_model", agency_self_model),
        ("real_acceptance", agency_real_acceptance),
        ("release", agency_release),
    )
    for label, module in modules:
        try:
            result[label] = module.status()
        except Exception as exc:
            result["ok"] = False
            result[label] = {"ready": False, "error": str(exc)[:1000]}
            result["errors"].append(f"{label}: {exc}")

    if sync_goals and result["ok"]:
        try:
            result["goal_sync"] = desired_state.sync_from_intentions()
        except Exception as exc:
            result["ok"] = False
            result["goal_sync"] = {"error": str(exc)[:1000]}
            result["errors"].append(f"goal_sync: {exc}")
    return result


def status() -> dict[str, Any]:
    from jarvis_mrb.agency_plan import status as plan_status
    from jarvis_mrb.agency_runtime import status as runtime_status
    from jarvis_mrb.desired_state import status as desired_status

    desired = desired_status()
    plans = plan_status()
    runtime = runtime_status()
    return {
        "ready": bool(desired.get("ready")) and bool(plans.get("ready")) and bool(runtime.get("ready")),
        "mode": str(runtime.get("mode") or "monitor"),
        "desired_states": desired.get("states") or {},
        "plans": plans.get("plans") or {},
        "steps": plans.get("steps") or {},
        "planner_backoff": runtime.get("planner_backoff") or [],
    }
