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
    import jarvis_mrb.custom_tools as custom_tools
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
        saved.append((custom_tools, "APP_DIR", custom_tools.APP_DIR))
        saved.append((custom_tools, "TOOLS_DIR", custom_tools.TOOLS_DIR))
        permissions.APP_DIR = base
        permissions.POLICY_PATH = base / "permissions.json"
        custom_tools.APP_DIR = base
        custom_tools.TOOLS_DIR = base / "custom_tools"

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
            "custom_tools": custom_tools,
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
        authority={"agency_enabled": True, "origin": "agency_acceptance"},
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
        agency_step_id = current_agency_step_id()
        reply_data: dict[str, Any] = {}
        if tool == "calendar.create":
            reply_data["event_id"] = f"synthetic-calendar-{agency_step_id[-12:]}"
        elif tool == "gmail.send":
            reply_data["message_id"] = f"synthetic-gmail-{agency_step_id[-12:]}"
            reply_data["email"] = str(args.get("recipient") or "")
        reply = SimpleNamespace(
            ok=True,
            message=f"{tool} accepted by synthetic external service.",
            data=reply_data,
        )
        action_event_id = world_model.record_tool_execution(
            tool,
            args,
            ok=True,
            message=reply.message,
            agency_step_id=agency_step_id,
        )
        world_verification.register_execution(
            tool,
            args,
            reply,
            action_event_id=action_event_id,
            agency_step_id=agency_step_id,
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
            ar.set_mode("active")

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

            # A2 — two causal action/observation cycles converge on machine-evaluable reality.
            entity_a2, state_a2 = _make_state(env, "Acceptance A2")
            plan_a2 = ap.create_plan(
                state_a2,
                [
                    {
                        "id": "write-one",
                        "tool": "state.update",
                        "arguments": {"key": "agency_acceptance_a2_phase", "value": 1},
                    },
                    {
                        "id": "write-two",
                        "tool": "state.update",
                        "arguments": {"key": "agency_acceptance_a2_phase", "value": 2},
                        "depends_on": ["write-one"],
                    },
                ],
            )
            calls_a2: list[str] = []

            def exec_a2(tool: str, args: dict[str, Any], **_: Any) -> SimpleNamespace:
                from jarvis_mrb.tool_audit import current_agency_step_id

                calls_a2.append(tool)
                step_id = current_agency_step_id()
                reply = SimpleNamespace(ok=True, message=f"{tool} synthetic write accepted")
                action_event_id = wm.record_tool_execution(
                    tool,
                    args,
                    ok=True,
                    message=reply.message,
                    agency_step_id=step_id,
                )
                wv.register_execution(
                    tool,
                    args,
                    reply,
                    action_event_id=action_event_id,
                    agency_step_id=step_id,
                )
                return reply

            first_a2 = ap.execute_next(plan_a2["id"], exec_a2)
            first_verification_a2 = str(first_a2["steps"][0]["verification_id"])
            original_observe_a2 = wv._observe
            try:
                wv._observe = lambda verifier, expected: (
                    "verified",
                    "Synthetic independent phase-one read-back matched.",
                )
                first_verified_a2 = wv.check_one(first_verification_a2, force=True)
            finally:
                wv._observe = original_observe_a2
            after_first_a2 = ap.reconcile_plan(plan_a2["id"])

            second_a2 = ap.execute_next(plan_a2["id"], exec_a2)
            second_verification_a2 = str(second_a2["steps"][1]["verification_id"])
            original_observe_a2 = wv._observe
            try:
                wv._observe = lambda verifier, expected: (
                    "verified",
                    "Synthetic independent phase-two read-back matched.",
                )
                second_verified_a2 = wv.check_one(second_verification_a2, force=True)
            finally:
                wv._observe = original_observe_a2

            if second_verified_a2 is None or second_verified_a2["status"] != "verified":
                raise AssertionError("Synthetic A2 second independent verification did not resolve.")
            wm.assert_belief(
                entity_a2,
                "ready",
                value=True,
                source_event_id=int(second_verified_a2["resolved_event_id"]),
                evidence="Second independently verified action completed the synthetic A2 goal.",
            )
            result_a2 = ap.reconcile_plan(plan_a2["id"])
            _check(
                checks,
                "A2",
                "closed loop performs two causal action-observation cycles and stops on desired state",
                calls_a2 == ["state.update", "state.update"]
                and first_verified_a2 is not None
                and first_verified_a2["status"] == "verified"
                and after_first_a2["status"] == "active"
                and second_verified_a2["status"] == "verified"
                and result_a2["status"] == "completed"
                and ds.get_desired_state(state_a2)["state"] == "satisfied",
                {
                    "calls": calls_a2,
                    "first_verification": first_verified_a2,
                    "after_first": after_first_a2["status"],
                    "second_verification": second_verified_a2,
                    "plan_status": result_a2["status"],
                },
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
            original_observe_a4 = wv._observe
            try:
                wv._observe = lambda verifier, expected: (
                    "verified",
                    "Synthetic independent read-back matched.",
                )
                verified_a4 = wv.check_one(verification_a4, force=True)
            finally:
                wv._observe = original_observe_a4
            after_a4 = ap.reconcile_plan(plan_a3b["id"])
            _check(
                checks,
                "A4",
                "consequential action is pending after receipt and only advances after verifier",
                before_a4 == "pending"
                and verified_a4 is not None
                and verified_a4["status"] == "verified"
                and after_a4["steps"][0]["status"] == "verified"
                and after_a4["status"] == "needs_replan",
                {
                    "verification_before": before_a4,
                    "verification_after": verified_a4,
                    "step_after": after_a4["steps"][0]["status"],
                },
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
            revised_a5 = ap.create_plan(
                state_a5,
                [
                    {
                        "id": "revised-write",
                        "tool": "calendar.create",
                        "arguments": {
                            "summary": "A5 revised",
                            "start": "2030-01-01T12:00:00-08:00",
                            "end": "2030-01-01T12:30:00-08:00",
                        },
                    }
                ],
                summary="A5 revised path preserves the completed observation",
            )
            preserved_a5 = next(
                step for step in stale_a5["steps"] if step["step_key"] == "read"
            )
            _check(
                checks,
                "A5",
                "relevant change invalidates stale action, preserves valid work, and yields revised plan",
                stale_a5["status"] == "needs_replan"
                and protected_calls_a5 == []
                and preserved_a5["status"] == "verified"
                and preserved_a5["attempt_count"] == 1
                and revised_a5["generation"] > plan_a5["generation"]
                and all(step["step_key"] != "read" for step in revised_a5["steps"]),
                {
                    "status": stale_a5["status"],
                    "protected_calls": protected_calls_a5,
                    "preserved_read": preserved_a5,
                    "revised_generation": revised_a5["generation"],
                },
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
            continuation_a6 = ar.tick_desired_state(
                state_a6,
                executor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("Synthetic protected wake continuation must await approval.")
                ),
                planner=lambda _prompt: {
                    "summary": "Act on the newly available prerequisite.",
                    "nodes": [
                        {
                            "id": "continue",
                            "tool": "calendar.create",
                            "arguments": {
                                "summary": "A6 synthetic continuation",
                                "start": "2030-01-01T12:30:00-08:00",
                                "end": "2030-01-01T13:00:00-08:00",
                            },
                            "depends_on": [],
                        }
                    ],
                    "missing_capability": None,
                },
            )
            _check(
                checks,
                "A6",
                "blocked desired state wakes and surfaces its newly feasible next step",
                sleeping_a6["triggered"] == 0
                and waking_a6["triggered"] == 1
                and ds.get_desired_state(state_a6)["state"] == "active"
                and continuation_a6["status"] == "awaiting_approval",
                {
                    "before": sleeping_a6,
                    "after": waking_a6,
                    "continuation": continuation_a6["status"],
                },
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

            # A9 — missing capability is explicit, synthesis stays disabled, explicit
            # enablement restores capability, and the recovered adapter remains confirmed.
            _, state_a9 = _make_state(env, "Acceptance A9")
            gap_a9 = ac.record_gap(
                state_a9,
                "private.status_api",
                "Synthetic missing private status API.",
            )
            ds.set_state(
                state_a9,
                "blocked",
                reason="Missing capability: private.status_api.",
            )

            custom_tools = env["custom_tools"]
            original_synthesize_a9 = custom_tools.synthesize

            def fake_synthesize_a9(
                *,
                name: str,
                description: str,
                api_spec: str,
                allowed_hosts: list[str],
                risk: str = "read",
            ) -> dict[str, Any]:
                item = {
                    "name": str(name),
                    "description": str(description),
                    "api_spec": str(api_spec),
                    "allowed_hosts": list(allowed_hosts),
                    "risk": str(risk),
                    "enabled": False,
                    "code": (
                        "import json\n"
                        "print(json.dumps({'method':'GET','url':'https://api.example.com/status',"
                        "'headers':{},'body':None}))\n"
                    ),
                }
                custom_tools.TOOLS_DIR.mkdir(parents=True, exist_ok=True)
                custom_tools._path(str(name)).write_text(
                    json.dumps(item, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                return item

            try:
                custom_tools.synthesize = fake_synthesize_a9
                synthesized_a9 = ac.synthesize_adapter(
                    gap_a9["id"],
                    name="a9_status_adapter",
                    description="Read synthetic private status.",
                    api_spec="GET /status",
                    allowed_hosts=["api.example.com"],
                    risk="read",
                )
            finally:
                custom_tools.synthesize = original_synthesize_a9

            wm.record_tool_execution(
                "custom.synthesize",
                {
                    "gap_id": gap_a9["id"],
                    "name": "a9_status_adapter",
                },
                ok=True,
                message="Synthetic adapter sandbox-validation path completed.",
            )
            disabled_a9 = custom_tools.get_tool("a9_status_adapter")
            custom_tools.set_enabled("a9_status_adapter", True)
            wm.record_tool_execution(
                "custom.enable",
                {"name": "a9_status_adapter", "enabled": True},
                ok=True,
                message="Synthetic user explicitly enabled adapter.",
            )
            reconciled_a9 = ac.reconcile_gaps()
            recovered_a9 = ac.available_tool("a9_status_adapter")

            permissions.set_policy("external_write", "deny")
            authority_a9 = ac.available_tool("gmail.send")
            _check(
                checks,
                "A9",
                "capability gap synthesizes disabled adapter, recovers only after explicit enablement, and preserves authority",
                gap_a9["status"] == "open"
                and synthesized_a9["gap"]["status"] == "proposed"
                and not synthesized_a9["enabled"]
                and not bool(disabled_a9.get("enabled"))
                and gap_a9["id"] in reconciled_a9["resolved"]
                and state_a9 in reconciled_a9["reactivated"]
                and recovered_a9["available"]
                and recovered_a9["requires_confirmation"]
                and recovered_a9["source"] == "custom"
                and not authority_a9["available"]
                and authority_a9["authority_blocked"]
                and authority_a9["source"] == "builtin",
                {
                    "gap": ac.get_gap(gap_a9["id"]),
                    "synthesized": synthesized_a9,
                    "reconciled": reconciled_a9,
                    "recovered_adapter": recovered_a9,
                    "known_denied_tool": authority_a9,
                },
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

            # A11 — repeated explicit approvals may produce low-authority preference
            # inference, but that learned preference never grants protected authority.
            _, state_a11 = _make_state(env, "Acceptance A11")
            permissions.set_policy("external_write", "confirm")
            approval_executor_a11 = _fake_audited_pending_write(env)
            approved_events_before_a11 = wm.max_event_id()

            for index in range(3):
                approval_plan_a11 = ap.create_plan(
                    state_a11,
                    [
                        {
                            "id": f"approved-write-{index}",
                            "tool": "calendar.create",
                            "arguments": {
                                "summary": f"A11 synthetic approved hold {index}",
                                "start": f"2030-01-0{index + 1}T14:00:00-08:00",
                                "end": f"2030-01-0{index + 1}T14:30:00-08:00",
                            },
                        }
                    ],
                )
                waiting_approval_a11 = ap.execute_next(
                    approval_plan_a11["id"],
                    lambda *_args, **_kwargs: SimpleNamespace(
                        ok=True,
                        message="must await explicit approval",
                    ),
                )
                ap.approve_step(
                    approval_plan_a11["id"],
                    waiting_approval_a11["steps"][0]["id"],
                    approval_executor_a11,
                )

            preference_key_a11 = sm.approval_preference_key(
                "calendar.create"
            )
            preference_a11 = sm.get(
                "preference",
                preference_key_a11,
            )
            plan_a11 = ap.create_plan(
                state_a11,
                [
                    {
                        "id": "post-inference-write",
                        "tool": "calendar.create",
                        "arguments": {
                            "summary": "A11 synthetic protected hold",
                            "start": "2030-01-10T14:00:00-08:00",
                            "end": "2030-01-10T14:30:00-08:00",
                        },
                    }
                ],
            )
            calls_a11: list[str] = []
            waiting_a11 = ap.execute_next(
                plan_a11["id"],
                lambda tool, args, **kwargs: calls_a11.append(tool)
                or SimpleNamespace(ok=True, message="must not execute"),
            )
            authority_a11 = sm.authority_for("calendar.create")
            inference_events_a11 = [
                item
                for item in wm.list_events(
                    since_event_id=approved_events_before_a11,
                    limit=200,
                )
                if str(item.get("event_type") or "")
                == "agency.self_model.inferred"
            ]
            _check(
                checks,
                "A11",
                "approval-derived autonomy preference cannot bypass protected action approval boundary",
                preference_a11 is not None
                and preference_a11["source_kind"] == "inferred_behavior"
                and len(
                    (preference_a11.get("value") or {}).get(
                        "supporting_approval_event_ids",
                        [],
                    )
                ) >= 3
                and bool(inference_events_a11)
                and waiting_a11["status"] == "awaiting_approval"
                and calls_a11 == []
                and authority_a11["allowed"]
                and authority_a11["requires_confirmation"]
                and authority_a11["authority_source"] == "permissions"
                and not authority_a11["self_model_can_override"],
                {
                    "preference": preference_a11,
                    "inference_events": inference_events_a11,
                    "plan_status": waiting_a11["status"],
                    "executor_calls": calls_a11,
                    "authority": authority_a11,
                },
            )

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
            original_observe_a12 = wv._observe
            try:
                wv._observe = lambda verifier, expected: (
                    "verified",
                    "Synthetic external state independently observed.",
                )
                verified_a12 = wv.check_one(verification_a12, force=True)
            finally:
                wv._observe = original_observe_a12
            if verified_a12 is None or verified_a12["status"] != "verified":
                raise AssertionError("Synthetic A12 independent verification did not resolve.")
            wm.assert_belief(
                entity_a12,
                "complete",
                value=True,
                source_event_id=int(verified_a12["resolved_event_id"]),
                evidence="Synthetic A12 completion follows independent verification.",
            )
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
