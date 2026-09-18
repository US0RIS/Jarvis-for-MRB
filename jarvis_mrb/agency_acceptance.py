from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator


REAL_GATES = {"A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A11", "A12"}
SYNTHETIC_ONLY_GATES = {"A10"}


def _check(
    checks: list[dict[str, Any]],
    gate: str,
    name: str,
    passed: bool,
    evidence: Any = None,
) -> None:
    checks.append(
        {
            "gate": gate,
            "name": name,
            "passed": bool(passed),
            "evidence": evidence,
        }
    )


@contextmanager
def _isolated_agency_world(base: Path) -> Iterator[dict[str, Any]]:
    """Bind every Agency/world module to a temporary DB and restore all globals.

    This harness is used inside the full unittest process as well as from its CLI.
    Leaking DB_PATH/APP_DIR/POLICY_PATH after the temporary directory is destroyed
    would make later tests or a long-lived caller operate on a deleted database.
    """
    import jarvis_mrb.agency_attention as agency_attention
    import jarvis_mrb.agency_capability as agency_capability
    import jarvis_mrb.agency_counterfactual as agency_counterfactual
    import jarvis_mrb.agency_deliberation as agency_deliberation
    import jarvis_mrb.agency_plan as agency_plan
    import jarvis_mrb.agency_runtime as agency_runtime
    import jarvis_mrb.agency_self_model as agency_self_model
    import jarvis_mrb.desired_state as desired_state
    import jarvis_mrb.permissions as permissions
    import jarvis_mrb.world_executive as world_executive
    import jarvis_mrb.world_model as world_model
    import jarvis_mrb.world_verification as world_verification

    db = base / "agency_acceptance.sqlite3"
    modules = (
        world_model,
        world_executive,
        desired_state,
        agency_plan,
        agency_runtime,
        agency_attention,
        agency_capability,
        agency_counterfactual,
        agency_deliberation,
        agency_self_model,
        world_verification,
    )
    saved: list[tuple[Any, str, Any]] = []
    try:
        saved.append((world_model, "APP_DIR", world_model.APP_DIR))
        world_model.APP_DIR = base
        for module in modules:
            if hasattr(module, "DB_PATH"):
                saved.append((module, "DB_PATH", getattr(module, "DB_PATH")))
                setattr(module, "DB_PATH", db)
        saved.append((permissions, "APP_DIR", permissions.APP_DIR))
        saved.append((permissions, "POLICY_PATH", permissions.POLICY_PATH))
        permissions.APP_DIR = base
        permissions.POLICY_PATH = base / "permissions.json"

        world_model.status()
        world_executive.status()
        desired_state.status()
        agency_plan.status()
        agency_runtime.status()
        agency_attention.status()
        agency_capability.status()
        agency_counterfactual.status()
        agency_deliberation.status()
        agency_self_model.status()
        world_verification.status()

        yield {
            "db": db,
            "world_model": world_model,
            "world_executive": world_executive,
            "desired_state": desired_state,
            "agency_plan": agency_plan,
            "agency_runtime": agency_runtime,
            "agency_attention": agency_attention,
            "agency_capability": agency_capability,
            "agency_counterfactual": agency_counterfactual,
            "agency_deliberation": agency_deliberation,
            "agency_self_model": agency_self_model,
            "world_verification": world_verification,
            "permissions": permissions,
        }
    finally:
        for module, attribute, value in reversed(saved):
            setattr(module, attribute, value)


def _make_state(env: dict[str, Any], name: str, *, predicate: str = "ready", expected: Any = True) -> tuple[str, str]:
    world_model = env["world_model"]
    desired_state = env["desired_state"]
    entity_id = world_model.ensure_entity("project", name)
    state = desired_state.create_desired_state(
        f"{name} desired outcome",
        [{"kind": "belief_equals", "entity_id": entity_id, "predicate": predicate, "value": expected}],
        source_kind="agency_acceptance",
        source_ref=f"acceptance:{name}",
    )
    return entity_id, str(state["id"])


def _fake_audited_pending_write(env: dict[str, Any]) -> Callable[..., SimpleNamespace]:
    world_model = env["world_model"]
    world_verification = env["world_verification"]

    def executor(tool: str, args: dict[str, Any], *, bypass_confirmation: bool = False) -> SimpleNamespace:
        from jarvis_mrb.tool_audit import current_agency_step_id

        if not bypass_confirmation:
            raise AssertionError("Protected acceptance action was not resumed through approval.")
        reply = SimpleNamespace(ok=True, message=f"{tool} accepted by synthetic external service.")
        action_event_id = world_model.record_tool_execution(tool, args, ok=True, message=reply.message)
        world_verification.register_execution(
            tool,
            args,
            reply,
            action_event_id=action_event_id,
            agency_step_id=current_agency_step_id(),
        )
        return reply

    return executor


def run_synthetic_acceptance() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    traces: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="jarvis-agency-acceptance-") as temp:
        base = Path(temp)
        with _isolated_agency_world(base) as env:
            wm = env["world_model"]
            ds = env["desired_state"]
            ap = env["agency_plan"]
            ar = env["agency_runtime"]
            aa = env["agency_attention"]
            ac = env["agency_capability"]
            cf = env["agency_counterfactual"]
            ad = env["agency_deliberation"]
            sm = env["agency_self_model"]
            wv = env["world_verification"]
            permissions = env["permissions"]

            # A1 — persistent desired state: create, re-open through a fresh DB connection,
            # and preserve explicit criteria/authority without relying on conversation state.
            entity_a1, state_a1 = _make_state(env, "Acceptance A1")
            created_a1 = ds.get_desired_state(state_a1)
            with sqlite3.connect(env["db"]) as conn:
                persisted = conn.execute(
                    "SELECT title,criteria_json,authority_json,state FROM desired_states WHERE id=?",
                    (state_a1,),
                ).fetchone()
            _check(
                checks,
                "A1",
                "desired state survives storage boundary with explicit criteria",
                bool(
                    created_a1
                    and persisted
                    and persisted[3] == "active"
                    and "belief_equals" in str(persisted[1])
                ),
                {"desired_state_id": state_a1, "stored_state": persisted[3] if persisted else None},
            )

            # A2 — two action/observation cycles converge on machine-evaluable reality.
            entity_a2, state_a2 = _make_state(env, "Acceptance A2")
            plan_a2 = ap.create_plan(
                state_a2,
                [
                    {"id": "observe", "tool": "knowledge.search", "arguments": {"query": "A2 current state"}},
                    {
                        "id": "observe_again",
                        "tool": "fact.check",
                        "arguments": {"claim": "A2 is ready"},
                        "depends_on": ["observe"],
                    },
                ],
            )
            calls_a2: list[str] = []

            def exec_a2(tool: str, args: dict[str, Any], **_: Any) -> SimpleNamespace:
                calls_a2.append(tool)
                if tool == "fact.check":
                    wm.assert_belief(entity_a2, "ready", value=True)
                return SimpleNamespace(ok=True, message=f"{tool} observation")

            ap.execute_next(plan_a2["id"], exec_a2)
            result_a2 = ap.execute_next(plan_a2["id"], exec_a2)
            _check(
                checks,
                "A2",
                "closed loop takes multiple observed steps and stops on desired state",
                calls_a2 == ["knowledge.search", "fact.check"]
                and result_a2["status"] == "completed"
                and ds.get_desired_state(state_a2)["state"] == "satisfied",
                {"calls": calls_a2, "plan_status": result_a2["status"]},
            )

            # A3 — safe reads can run, protected action persists approval, denial does not
            # erase the objective, and approval resumes the exact stored step.
            _, state_a3 = _make_state(env, "Acceptance A3")
            plan_a3 = ap.create_plan(
                state_a3,
                [
                    {"id": "read", "tool": "knowledge.search", "arguments": {"query": "A3"}},
                    {
                        "id": "write",
                        "tool": "calendar.create",
                        "arguments": {
                            "summary": "A3 synthetic",
                            "start": "2030-01-01T09:00:00-08:00",
                            "end": "2030-01-01T09:30:00-08:00",
                        },
                        "depends_on": ["read"],
                    },
                ],
            )
            safe_calls: list[str] = []
            ap.execute_next(
                plan_a3["id"],
                lambda tool, args, **kwargs: safe_calls.append(tool) or SimpleNamespace(ok=True, message="read"),
            )
            waiting_a3 = ap.execute_next(
                plan_a3["id"],
                lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="must not run"),
            )
            denied_a3 = ap.deny_step(plan_a3["id"], waiting_a3["steps"][1]["id"], reason="Synthetic denial.")
            _check(
                checks,
                "A3",
                "protected action waits durably and denial preserves objective for replan",
                safe_calls == ["knowledge.search"]
                and waiting_a3["status"] == "awaiting_approval"
                and denied_a3["status"] == "needs_replan"
                and ds.get_desired_state(state_a3)["state"] == "active",
                {
                    "safe_calls": safe_calls,
                    "waiting": waiting_a3["status"],
                    "after_denial": denied_a3["status"],
                },
            )

            _, state_a3b = _make_state(env, "Acceptance A3 Approval")
            plan_a3b = ap.create_plan(
                state_a3b,
                [
                    {
                        "id": "write",
                        "tool": "calendar.create",
                        "arguments": {
                            "summary": "A3 approval synthetic",
                            "start": "2030-01-01T10:00:00-08:00",
                            "end": "2030-01-01T10:30:00-08:00",
                        },
                    }
                ],
            )
            waiting_a3b = ap.execute_next(
                plan_a3b["id"],
                lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="must not run"),
            )
            approved_a3b = ap.approve_step(
                plan_a3b["id"],
                waiting_a3b["steps"][0]["id"],
                _fake_audited_pending_write(env),
            )
            _check(
                checks,
                "A3",
                "approval resumes exact persistent step and enters independent verification",
                approved_a3b["status"] == "awaiting_verification"
                and bool(approved_a3b["steps"][0]["verification_id"]),
                {
                    "step_id": waiting_a3b["steps"][0]["id"],
                    "verification_id": approved_a3b["steps"][0]["verification_id"],
                },
            )

            # A4 — tool receipt remains pending until a separate verifier state resolves it.
            verification_a4 = approved_a3b["steps"][0]["verification_id"]
            with sqlite3.connect(env["db"]) as conn:
                before_a4 = conn.execute(
                    "SELECT status FROM action_verifications WHERE id=?",
                    (verification_a4,),
                ).fetchone()[0]
                conn.execute(
                    "UPDATE action_verifications SET status='verified',last_evidence='Synthetic independent read-back matched.' WHERE id=?",
                    (verification_a4,),
                )
                conn.commit()
            after_a4 = ap.reconcile_plan(plan_a3b["id"])
            _check(
                checks,
                "A4",
                "consequential action is pending after receipt and only advances after verifier",
                before_a4 == "pending"
                and after_a4["steps"][0]["status"] == "verified"
                and after_a4["status"] == "needs_replan",
                {"verification_before": before_a4, "step_after": after_a4["steps"][0]["status"]},
            )

            # Also prove failed tool execution becomes a terminal verification result.
            failed_event = wm.record_tool_execution(
                "calendar.create",
                {"summary": "failure", "start": "x", "end": "y"},
                ok=False,
                message="synthetic failure",
            )
            failed_verification = wv.register_execution(
                "calendar.create",
                {"summary": "failure", "start": "x", "end": "y"},
                SimpleNamespace(ok=False, message="synthetic failure"),
                action_event_id=failed_event,
            )
            with sqlite3.connect(env["db"]) as conn:
                failed_status = conn.execute(
                    "SELECT status FROM action_verifications WHERE id=?",
                    (failed_verification,),
                ).fetchone()[0]
            _check(
                checks,
                "A4",
                "failed execution is never reported as verified success",
                failed_status == "failed",
                {"verification_id": failed_verification, "status": failed_status},
            )

            # A5 — relevant reality change invalidates stale plan before protected action.
            entity_a5, state_a5 = _make_state(env, "Acceptance A5")
            wm.assert_belief(entity_a5, "constraint", value="old")
            plan_a5 = ap.create_plan(
                state_a5,
                [
                    {"id": "read", "tool": "knowledge.search", "arguments": {"query": "A5"}},
                    {
                        "id": "write",
                        "tool": "calendar.create",
                        "arguments": {
                            "summary": "A5 stale",
                            "start": "2030-01-01T11:00:00-08:00",
                            "end": "2030-01-01T11:30:00-08:00",
                        },
                        "depends_on": ["read"],
                    },
                ],
            )
            protected_calls_a5: list[str] = []
            ap.execute_next(
                plan_a5["id"],
                lambda tool, args, **kwargs: SimpleNamespace(ok=True, message="observed"),
            )
            wm.assert_belief(entity_a5, "constraint", value="new")
            stale_a5 = ap.execute_next(
                plan_a5["id"],
                lambda tool, args, **kwargs: protected_calls_a5.append(tool) or SimpleNamespace(ok=True, message="wrong"),
            )
            _check(
                checks,
                "A5",
                "relevant state change invalidates stale path before consequential action",
                stale_a5["status"] == "needs_replan" and protected_calls_a5 == [],
                {"status": stale_a5["status"], "protected_calls": protected_calls_a5},
            )

            # A6 — blocked goal sleeps until explicit watched world condition becomes true.
            entity_a6, state_a6 = _make_state(env, "Acceptance A6")
            ds.set_state(state_a6, "blocked", reason="Waiting for prerequisite.")
            ds.add_wake_watch(
                state_a6,
                {"kind": "belief_equals", "entity_id": entity_a6, "predicate": "prerequisite", "value": "available"},
            )
            sleeping_a6 = ds.check_wake_watches()
            wm.assert_belief(entity_a6, "prerequisite", value="available")
            waking_a6 = ds.check_wake_watches()
            _check(
                checks,
                "A6",
                "blocked desired state reactivates only after persisted wake condition",
                sleeping_a6["triggered"] == 0
                and waking_a6["triggered"] == 1
                and ds.get_desired_state(state_a6)["state"] == "active",
                {"before": sleeping_a6, "after": waking_a6},
            )

            # A7 — independent workers actually overlap and disagreement remains visible.
            barrier = threading.Barrier(4)

            def worker_a7(role: str, question: str, context: str) -> dict[str, Any]:
                barrier.wait(timeout=2)
                time.sleep(0.05)
                confidence = 0.9 if role == "evidence" else 0.2 if role == "skeptic" else 0.55
                return {
                    "conclusion": "proceed" if role in {"evidence", "feasibility"} else "do not proceed",
                    "claims": [
                        {
                            "claim": "The dependency is reliable",
                            "confidence": confidence,
                            "evidence": role,
                        }
                    ],
                    "risks": [],
                    "unknowns": [],
                }

            started_a7 = time.monotonic()
            deliberation_a7 = ad.deliberate(
                "A7 decision?",
                worker=worker_a7,
                synthesizer=lambda q, c, outputs, disagreements: {
                    "answer": "Workers disagree.",
                    "consensus": [],
                    "disagreements": disagreements,
                    "unknowns": [],
                    "recommended_next_evidence": ["Test dependency"],
                    "confidence": 0.5,
                },
            )
            elapsed_a7 = time.monotonic() - started_a7
            _check(
                checks,
                "A7",
                "parallel workers persist independent outputs before synthesis",
                len(deliberation_a7["outputs"]) == 4
                and elapsed_a7 < 0.5
                and bool(deliberation_a7["disagreements"]),
                {
                    "workers": len(deliberation_a7["outputs"]),
                    "wall_seconds": round(elapsed_a7, 3),
                    "disagreements": deliberation_a7["disagreements"],
                },
            )

            # A8 — low-value changes remain queryable; one high-value exception emits once.
            emitted_a8: list[str] = []
            for index in range(10):
                aa.consider(
                    kind="background",
                    message=f"Low value change {index}",
                    dedup_key=f"a8-low:{index}",
                    benefit=10,
                    urgency=5,
                    confidence=0.9,
                    error_cost=5,
                    attention_cost=25,
                    emitter=emitted_a8.append,
                )
            high1_a8 = aa.consider(
                kind="approval",
                message="High value approval required.",
                dedup_key="a8-high",
                benefit=95,
                urgency=85,
                confidence=1.0,
                error_cost=0,
                attention_cost=15,
                emitter=emitted_a8.append,
            )
            high2_a8 = aa.consider(
                kind="approval",
                message="High value approval required.",
                dedup_key="a8-high",
                benefit=95,
                urgency=85,
                confidence=1.0,
                error_cost=0,
                attention_cost=15,
                emitter=emitted_a8.append,
            )
            _check(
                checks,
                "A8",
                "attention gate logs low-value changes and deduplicates high-value interruption",
                len(aa.list_events()) == 11
                and emitted_a8 == ["High value approval required."]
                and high1_a8["emitted"]
                and high2_a8["duplicate"],
                {"emitted": emitted_a8, "events": len(aa.list_events())},
            )

            # A9 — missing capability is explicit, while denied known tool is authority.
            _, state_a9 = _make_state(env, "Acceptance A9")
            gap_a9 = ac.record_gap(state_a9, "robot.arm", "Synthetic missing actuator.")
            permissions.set_policy("external_write", "deny")
            authority_a9 = ac.available_tool("gmail.send")
            _check(
                checks,
                "A9",
                "missing capability and authority denial are represented separately",
                gap_a9["status"] == "open"
                and not authority_a9["available"]
                and authority_a9["authority_blocked"]
                and authority_a9["source"] == "builtin",
                {"gap": gap_a9, "known_denied_tool": authority_a9},
            )
            permissions.set_policy("external_write", "confirm")

            # A10 — preserve alternatives and explicit evidence that would change choice.
            case_a10 = cf.create_case(
                "A10 choice?",
                [
                    {
                        "id": "reversible",
                        "title": "Reversible pilot",
                        "assumptions": ["Pilot is representative"],
                        "evidence": [{"source": "acceptance", "fact": "pilot cheaper"}],
                        "expected_outcomes": ["evidence"],
                        "cost": {"units": 1},
                        "reversibility": 0.95,
                        "uncertainty": 0.4,
                    },
                    {
                        "id": "full",
                        "title": "Full rollout",
                        "assumptions": ["Demand stable"],
                        "evidence": [{"source": "acceptance", "fact": "rollout faster"}],
                        "expected_outcomes": ["scale"],
                        "cost": {"units": 10},
                        "reversibility": 0.2,
                        "uncertainty": 0.7,
                    },
                ],
            )
            selected_a10 = cf.select_branch(
                case_a10["id"],
                "reversible",
                rationale="Prefer reversibility while uncertainty is material.",
                change_conditions=["Switch if demand becomes independently established."],
            )
            _check(
                checks,
                "A10",
                "selected counterfactual preserves alternatives and change conditions",
                len(selected_a10["branches"]) == 2
                and sum(1 for branch in selected_a10["branches"] if branch["status"] == "selected") == 1
                and len(selected_a10["change_conditions"]) == 1,
                {
                    "selected": selected_a10["selected_branch_id"],
                    "branches": [branch["status"] for branch in selected_a10["branches"]],
                },
            )

            # A11 — self model guides choices but can never grant authority.
            sm.upsert(
                "preference",
                "email_autonomy",
                "send routine email automatically",
                confidence=1.0,
                source_ref="a11:preference",
            )
            permissions.set_policy("external_write", "deny")
            authority_a11 = sm.authority_for("gmail.send")
            _check(
                checks,
                "A11",
                "high-confidence self-model preference cannot override permission authority",
                not authority_a11["allowed"]
                and authority_a11["authority_source"] == "permissions"
                and not authority_a11["self_model_can_override"],
                authority_a11,
            )
            permissions.set_policy("external_write", "confirm")

            # A12 — synthetic one-decision trace. It deliberately includes private/public
            # reads, parallel analysis, injected reality change -> replan, protected write,
            # approval, separate verification, and desired-state convergence.
            entity_a12, state_a12 = _make_state(env, "Acceptance A12", predicate="complete", expected=True)
            wm.assert_belief(entity_a12, "route", value="old")

            deliberation_a12 = ad.deliberate(
                "Choose A12 execution path",
                roles=["evidence", "skeptic", "feasibility", "risk_cost"],
                worker=lambda role, q, ctx: {
                    "conclusion": f"{role} analysis",
                    "claims": [{"claim": "A12 can proceed", "confidence": 0.7, "evidence": role}],
                    "risks": [],
                    "unknowns": [],
                },
                synthesizer=lambda q, c, outputs, disagreements: {
                    "answer": "Proceed with bounded reversible path.",
                    "consensus": ["Use bounded path"],
                    "disagreements": disagreements,
                    "unknowns": [],
                    "recommended_next_evidence": [],
                    "confidence": 0.7,
                },
            )

            first_a12 = ap.create_plan(
                state_a12,
                [
                    {"id": "private", "tool": "knowledge.search", "arguments": {"query": "A12 private state"}},
                    {
                        "id": "public",
                        "tool": "web.search",
                        "arguments": {"query": "A12 public evidence", "num": 5},
                        "depends_on": ["private"],
                    },
                    {
                        "id": "write",
                        "tool": "calendar.create",
                        "arguments": {
                            "summary": "A12 synthetic external action",
                            "start": "2030-01-01T12:00:00-08:00",
                            "end": "2030-01-01T12:30:00-08:00",
                        },
                        "depends_on": ["public"],
                    },
                ],
                summary="A12 initial path",
            )
            trace_a12: list[str] = []
            read_exec = lambda tool, args, **kwargs: trace_a12.append(tool) or SimpleNamespace(ok=True, message=f"{tool} evidence")
            ap.execute_next(first_a12["id"], read_exec)
            ap.execute_next(first_a12["id"], read_exec)

            # Reality changes after research but before the external write.
            wm.assert_belief(entity_a12, "route", value="new")
            invalidated_a12 = ap.execute_next(first_a12["id"], read_exec)
            trace_a12.append("replan_required")

            second_a12 = ap.create_plan(
                state_a12,
                [
                    {"id": "private2", "tool": "knowledge.search", "arguments": {"query": "A12 refreshed private state"}},
                    {
                        "id": "public2",
                        "tool": "web.search",
                        "arguments": {"query": "A12 refreshed public evidence", "num": 5},
                        "depends_on": ["private2"],
                    },
                    {
                        "id": "write2",
                        "tool": "calendar.create",
                        "arguments": {
                            "summary": "A12 revised synthetic external action",
                            "start": "2030-01-01T13:00:00-08:00",
                            "end": "2030-01-01T13:30:00-08:00",
                        },
                        "depends_on": ["public2"],
                    },
                ],
                summary="A12 revised path",
            )
            ap.execute_next(second_a12["id"], read_exec)
            ap.execute_next(second_a12["id"], read_exec)
            waiting_a12 = ap.execute_next(second_a12["id"], read_exec)
            trace_a12.append("approval_required")
            approved_a12 = ap.approve_step(
                second_a12["id"],
                waiting_a12["steps"][2]["id"],
                _fake_audited_pending_write(env),
            )
            trace_a12.append("approved")
            verification_a12 = approved_a12["steps"][2]["verification_id"]
            with sqlite3.connect(env["db"]) as conn:
                conn.execute(
                    "UPDATE action_verifications SET status='verified',last_evidence='Synthetic external state independently observed.' WHERE id=?",
                    (verification_a12,),
                )
                conn.commit()
            wm.assert_belief(entity_a12, "complete", value=True)
            completed_a12 = ap.reconcile_plan(second_a12["id"])
            trace_a12.append("verified_and_satisfied")

            traces["A12"] = {
                "trace": trace_a12,
                "first_plan": first_a12["id"],
                "invalidated_status": invalidated_a12["status"],
                "second_plan": second_a12["id"],
                "verification_id": verification_a12,
                "final_plan_status": completed_a12["status"],
                "desired_state": ds.get_desired_state(state_a12)["state"],
                "deliberation_id": deliberation_a12["id"],
            }
            _check(
                checks,
                "A12",
                "one-decision synthetic trace crosses research, parallel analysis, replan, approval, verification, convergence",
                trace_a12
                == [
                    "knowledge.search",
                    "web.search",
                    "replan_required",
                    "knowledge.search",
                    "web.search",
                    "approval_required",
                    "approved",
                    "verified_and_satisfied",
                ]
                and invalidated_a12["status"] == "needs_replan"
                and completed_a12["status"] == "completed"
                and ds.get_desired_state(state_a12)["state"] == "satisfied"
                and len(deliberation_a12["outputs"]) == 4,
                traces["A12"],
            )

    gate_results: dict[str, dict[str, Any]] = {}
    for gate in [f"A{index}" for index in range(1, 13)]:
        relevant = [check for check in checks if check["gate"] == gate]
        gate_results[gate] = {
            "synthetic_passed": bool(relevant) and all(bool(check["passed"]) for check in relevant),
            "checks": len(relevant),
            "failed": [check["name"] for check in relevant if not check["passed"]],
            "real_deployment_required": gate in REAL_GATES,
        }

    synthetic_ok = all(result["synthetic_passed"] for result in gate_results.values())
    return {
        "ok": synthetic_ok,
        "mode": "synthetic_isolated",
        "mutates_user_data": False,
        "uses_external_services": False,
        "synthetic_gate_results": gate_results,
        "checks": checks,
        "failed_checks": [check for check in checks if not check["passed"]],
        "real_deployment_required": sorted(REAL_GATES),
        "synthetic_only_gates": sorted(SYNTHETIC_ONLY_GATES),
        "release_ready": False,
        "release_ready_reason": (
            "Synthetic preflight only. Agency 1.0 cannot be release-ready until every REAL gate "
            "has a recorded deployment receipt on the actual Jarvis Windows/iPhone/services stack."
        ),
        "traces": traces,
    }


def status() -> dict[str, Any]:
    return {
        "gates": [f"A{index}" for index in range(1, 13)],
        "synthetic_isolated": True,
        "mutates_user_data": False,
        "uses_external_services": False,
        "real_deployment_required": sorted(REAL_GATES),
    }
