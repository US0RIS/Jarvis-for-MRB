from __future__ import annotations

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.agency_attention as agency_attention
import jarvis_mrb.agency_capability as agency_capability
import jarvis_mrb.agency_deliberation as agency_deliberation
import jarvis_mrb.agency_plan as agency_plan
import jarvis_mrb.agency_real_acceptance as agency_real_acceptance
import jarvis_mrb.agency_release as agency_release
import jarvis_mrb.agency_runtime as agency_runtime
import jarvis_mrb.agency_self_model as agency_self_model
import jarvis_mrb.desired_state as desired_state
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_verification as world_verification


SHA_A = "a" * 40
SHA_B = "b" * 40
ENV = "real-harness-test-env"


class AgencyRealAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"

        self.originals = {
            "world_app": world_model.APP_DIR,
            "world_db": world_model.DB_PATH,
            "executive_db": world_executive.DB_PATH,
            "desired_db": desired_state.DB_PATH,
            "plan_db": agency_plan.DB_PATH,
            "runtime_db": agency_runtime.DB_PATH,
            "self_model_db": agency_self_model.DB_PATH,
            "attention_db": agency_attention.DB_PATH,
            "capability_db": agency_capability.DB_PATH,
            "deliberation_db": agency_deliberation.DB_PATH,
            "verification_db": world_verification.DB_PATH,
            "permissions_app": permissions.APP_DIR,
            "permissions_path": permissions.POLICY_PATH,
        }
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        desired_state.DB_PATH = self.db
        agency_plan.DB_PATH = self.db
        agency_runtime.DB_PATH = self.db
        agency_self_model.DB_PATH = self.db
        agency_attention.DB_PATH = self.db
        agency_capability.DB_PATH = self.db
        agency_deliberation.DB_PATH = self.db
        world_verification.DB_PATH = self.db
        permissions.APP_DIR = self.base
        permissions.POLICY_PATH = self.base / "permissions.json"

        world_model.status()
        world_executive.status()
        desired_state.status()
        agency_plan.status()
        agency_runtime.status()
        agency_self_model.status()
        agency_attention.status()
        agency_capability.status()
        agency_deliberation.status()
        world_verification.status()
        agency_real_acceptance.status()
        # Initialize release tables without depending on current deployment status.
        with agency_release._connect():
            pass

    def tearDown(self) -> None:
        world_model.APP_DIR = self.originals["world_app"]
        world_model.DB_PATH = self.originals["world_db"]
        world_executive.DB_PATH = self.originals["executive_db"]
        desired_state.DB_PATH = self.originals["desired_db"]
        agency_plan.DB_PATH = self.originals["plan_db"]
        agency_runtime.DB_PATH = self.originals["runtime_db"]
        agency_self_model.DB_PATH = self.originals["self_model_db"]
        agency_attention.DB_PATH = self.originals["attention_db"]
        agency_capability.DB_PATH = self.originals["capability_db"]
        agency_deliberation.DB_PATH = self.originals["deliberation_db"]
        world_verification.DB_PATH = self.originals["verification_db"]
        permissions.APP_DIR = self.originals["permissions_app"]
        permissions.POLICY_PATH = self.originals["permissions_path"]
        self.temp.cleanup()

    def _patch_identity(self, sha: str = SHA_A):
        return patch.multiple(
            agency_real_acceptance,
            deployment_sha=lambda: sha,
            environment_fingerprint=lambda: ENV,
        )

    def _state_with_plan(self, title: str) -> tuple[str, dict]:
        entity_id = world_model.ensure_entity("project", title)
        state = desired_state.create_desired_state(
            f"{title} ready",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "ready", "value": True}],
            source_kind="test",
            source_ref=f"real:{title}",
        )
        plan = agency_plan.create_plan(
            state["id"],
            [{"id": "observe", "tool": "knowledge.search", "arguments": {"query": title}}],
            summary=f"Observe {title}",
        )
        agency_runtime._update_runtime(str(state["id"]), tick=True)
        return str(state["id"]), plan

    def test_a1_requires_actual_new_boot_and_same_persistent_plan(self) -> None:
        state_id, plan = self._state_with_plan("Restart Project")
        agency_runtime.record_boot(deployment_sha=SHA_A)

        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A1",
                desired_state_id=state_id,
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            before = agency_real_acceptance.evaluate_session(session["id"])
            self.assertFalse(before["passed"])
            self.assertFalse(before["evidence"]["restart_observed"])

            with patch("jarvis_mrb.agency_runtime.os.getpid", return_value=987654):
                agency_runtime.record_boot(deployment_sha=SHA_A)
            after = agency_real_acceptance.evaluate_session(session["id"])
            self.assertTrue(after["passed"], after["checks"])

            finalized = agency_real_acceptance.finalize_session(session["id"])
            self.assertTrue(finalized["receipt_created"])
            self.assertEqual(finalized["receipt"]["gate"], "A1")
            self.assertEqual(finalized["receipt"]["deployment_sha"], SHA_A)

        loaded_plan = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertIsNotNone(loaded_plan)

    def test_a8_receipt_is_derived_from_attention_ledger(self) -> None:
        emitted: list[str] = []
        state_id, _ = self._state_with_plan("Attention Gate")
        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A8",
                desired_state_id=state_id,
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            for index in range(6):
                agency_attention.consider(
                    kind="background",
                    message=f"Low value {index}",
                    desired_state_id=state_id,
                    dedup_key=f"low:{index}",
                    benefit=10,
                    urgency=5,
                    confidence=1.0,
                    error_cost=5,
                    attention_cost=30,
                    emitter=emitted.append,
                )
            agency_attention.consider(
                kind="exception",
                message="One high-value exception",
                desired_state_id=state_id,
                dedup_key="high:one",
                benefit=100,
                urgency=90,
                confidence=1.0,
                error_cost=0,
                attention_cost=10,
                emitter=emitted.append,
            )
            # Duplicate observation should not create a duplicate interruption.
            agency_attention.consider(
                kind="exception",
                message="One high-value exception",
                desired_state_id=state_id,
                dedup_key="high:one",
                benefit=100,
                urgency=90,
                confidence=1.0,
                error_cost=0,
                attention_cost=10,
                emitter=emitted.append,
            )

            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertTrue(evaluation["passed"], evaluation["checks"])
            self.assertEqual(evaluation["evidence"]["low_value_changes"], 6)
            self.assertEqual(evaluation["evidence"]["bounded_interruptions"], 1)
            self.assertEqual(evaluation["evidence"]["duplicate_interruptions"], 0)

            finalized = agency_real_acceptance.finalize_session(session["id"])
            self.assertTrue(finalized["receipt_created"])
            self.assertEqual(finalized["receipt"]["gate"], "A8")

        self.assertEqual(emitted, ["One high-value exception"])

    def test_real_session_identity_and_baseline_are_immutable(self) -> None:
        state_id, _ = self._state_with_plan("Immutable Session")
        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A8",
                desired_state_id=state_id,
                deployment_sha_value=SHA_A,
                environment=ENV,
            )

        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE agency_real_gate_sessions SET desired_state_id='tampered' WHERE id=?",
                    (session["id"],),
                )
            conn.rollback()
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "DELETE FROM agency_real_gate_sessions WHERE id=?",
                    (session["id"],),
                )
        finally:
            conn.close()

    def test_forced_real_session_tampering_fails_integrity_check_and_cannot_finalize(self) -> None:
        state_id, _ = self._state_with_plan("Tampered Session")
        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A8",
                desired_state_id=state_id,
                deployment_sha_value=SHA_A,
                environment=ENV,
            )

        conn = sqlite3.connect(self.db)
        try:
            conn.execute("DROP TRIGGER agency_real_gate_sessions_immutable_identity")
            conn.execute(
                "UPDATE agency_real_gate_sessions SET baseline_json='{}' WHERE id=?",
                (session["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        with self._patch_identity():
            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertFalse(evaluation["passed"])
            self.assertIn("integrity hash mismatch", evaluation["checks"][0]["evidence"])
            finalized = agency_real_acceptance.finalize_session(session["id"])

        self.assertFalse(finalized["passed"])
        self.assertFalse(finalized["receipt_created"])
        self.assertEqual(
            agency_release.list_real_gate_receipts(
                deployment_sha_value=SHA_A,
                environment=ENV,
            ),
            [],
        )

    def test_uncorrelated_audited_tool_execution_is_manual_orchestration(self) -> None:
        events = [
            {
                "id": 1,
                "event_type": "action.tool",
                "source_kind": "jarvis_tool",
                "payload": {"tool": "web.search", "agency_step_id": ""},
            },
            {
                "id": 2,
                "event_type": "action.tool",
                "source_kind": "jarvis_tool",
                "payload": {"tool": "knowledge.search", "agency_step_id": "agency-step:owned"},
            },
        ]
        flagged = agency_real_acceptance._manual_orchestration_events(events)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["event_id"], 1)
        self.assertEqual(flagged[0]["tool"], "web.search")

    def test_a5_requires_external_change_before_invalidation_and_new_generation(self) -> None:
        entity_id = world_model.ensure_entity("project", "Causal Replan Gate")
        state = desired_state.create_desired_state(
            "Causal Replan Gate scheduled",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "scheduled", "value": True}],
            source_kind="test",
            source_ref="real:a5",
        )
        plan = agency_plan.create_plan(
            state["id"],
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Causal replan",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )

        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A5",
                desired_state_id=str(state["id"]),
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            event_id = world_model.record_event(
                "calendar.context_enriched",
                "Causal Replan Gate timing changed externally.",
                source_kind="calendar_enriched",
                source_ref="real-a5:external-change",
                evidence="External calendar observation changed the relevant timing.",
                participants=[(entity_id, "subject", 1.0)],
            )
            invalidated = agency_plan.execute_next(
                plan["id"],
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("stale protected plan must not execute")
                ),
            )
            self.assertEqual(invalidated["status"], "needs_replan")

            new_plan = agency_plan.create_plan(
                str(state["id"]),
                [{"id": "observe", "tool": "knowledge.search", "arguments": {"query": "new timing"}}],
                summary="Replanned after external timing change",
            )
            self.assertGreater(new_plan["generation"], plan["generation"])

            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertTrue(evaluation["passed"], evaluation["checks"])
            causal = evaluation["checks"][0]["evidence"]
            self.assertTrue(any(event_id in item["external_event_ids"] for item in causal))

            finalized = agency_real_acceptance.finalize_session(session["id"])
            self.assertTrue(finalized["receipt_created"])
            self.assertEqual(finalized["receipt"]["gate"], "A5")

    def test_a6_requires_externally_grounded_wake_evidence(self) -> None:
        entity_id = world_model.ensure_entity("project", "Dormant Wake Gate")
        state = desired_state.create_desired_state(
            "Dormant Wake Gate available",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "available", "value": True}],
            source_kind="test",
            source_ref="real:a6",
        )
        desired_state.set_state(str(state["id"]), "blocked", reason="Waiting for external availability.")
        desired_state.add_wake_watch(
            str(state["id"]),
            {"kind": "belief_equals", "entity_id": entity_id, "predicate": "available", "value": True},
        )

        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A6",
                desired_state_id=str(state["id"]),
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            source_event_id = world_model.record_event(
                "calendar.context_enriched",
                "Dormant Wake Gate is now available.",
                source_kind="calendar_enriched",
                source_ref="real-a6:availability",
                evidence="External availability observation.",
                participants=[(entity_id, "subject", 1.0)],
            )
            world_model.assert_belief(
                entity_id,
                "available",
                value=True,
                source_event_id=source_event_id,
                evidence="Observed externally.",
            )
            wake = desired_state.check_wake_watches()
            self.assertEqual(wake["triggered"], 1)

            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertTrue(evaluation["passed"], evaluation["checks"])
            self.assertTrue(evaluation["evidence"]["wake_condition_changed"])

            finalized = agency_real_acceptance.finalize_session(session["id"])
            self.assertTrue(finalized["receipt_created"])
            self.assertEqual(finalized["receipt"]["gate"], "A6")

    def test_a6_internal_only_wake_does_not_count_as_real_evidence(self) -> None:
        entity_id = world_model.ensure_entity("project", "Internal Wake Gate")
        state = desired_state.create_desired_state(
            "Internal Wake Gate available",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "available", "value": True}],
            source_kind="test",
            source_ref="real:a6-internal",
        )
        desired_state.set_state(str(state["id"]), "blocked", reason="Waiting.")
        desired_state.add_wake_watch(
            str(state["id"]),
            {"kind": "belief_equals", "entity_id": entity_id, "predicate": "available", "value": True},
        )

        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A6",
                desired_state_id=str(state["id"]),
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            internal_event = world_model.record_event(
                "agency.synthetic_change",
                "Jarvis internally marked availability.",
                source_kind="jarvis_agency",
                source_ref="real-a6:internal",
                evidence="Internal-only change.",
                participants=[(entity_id, "subject", 1.0)],
            )
            world_model.assert_belief(
                entity_id,
                "available",
                value=True,
                source_event_id=internal_event,
                evidence="Internal-only belief.",
            )
            desired_state.check_wake_watches()

            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertFalse(evaluation["passed"])
            wake_check = next(
                item for item in evaluation["checks"]
                if item["name"].startswith("wake condition later triggered")
            )
            self.assertFalse(wake_check["passed"])

    def test_a7_is_scoped_to_matching_real_deliberation(self) -> None:
        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A7",
                parameters={"question_contains": "scoped launch decision"},
                deployment_sha_value=SHA_A,
                environment=ENV,
            )

            agency_deliberation.deliberate(
                "Unrelated pricing decision",
                roles=["evidence", "skeptic"],
                worker=lambda role, q, ctx: {
                    "conclusion": "yes" if role == "evidence" else "no",
                    "claims": [],
                    "risks": [],
                    "unknowns": [],
                },
                synthesizer=lambda q, ctx, outputs, disagreements: {
                    "answer": "unrelated",
                    "consensus": [],
                    "disagreements": [],
                    "unknowns": [],
                    "recommended_next_evidence": [],
                    "confidence": 0.5,
                },
            )
            unrelated = agency_real_acceptance.evaluate_session(session["id"])
            self.assertFalse(unrelated["passed"])

            barrier = threading.Barrier(2)

            def worker(role: str, q: str, ctx: str) -> dict:
                barrier.wait(timeout=2)
                time.sleep(0.05)
                return {
                    "conclusion": "launch" if role == "evidence" else "wait",
                    "claims": [
                        {
                            "claim": f"{role} claim",
                            "confidence": 0.6,
                            "evidence": "Reasoning only",
                            "source": "reasoning",
                        }
                    ],
                    "risks": [],
                    "unknowns": [],
                }

            agency_deliberation.deliberate(
                "Scoped launch decision for the real gate",
                roles=["evidence", "skeptic"],
                worker=worker,
                synthesizer=lambda q, ctx, outputs, disagreements: {
                    "answer": "preserve disagreement",
                    "consensus": [],
                    "disagreements": [{"issue": "launch timing"}],
                    "unknowns": [],
                    "recommended_next_evidence": [],
                    "confidence": 0.5,
                },
            )

            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertTrue(evaluation["passed"], evaluation["checks"])
            self.assertTrue(evaluation["evidence"]["provenance_structurally_bounded"])
            finalized = agency_real_acceptance.finalize_session(session["id"])
            self.assertTrue(finalized["receipt_created"])
            self.assertEqual(finalized["receipt"]["gate"], "A7")

    def test_a9_only_counts_gap_for_target_desired_state(self) -> None:
        target_state, _ = self._state_with_plan("Capability Target")
        other_state, _ = self._state_with_plan("Capability Other")

        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A9",
                desired_state_id=target_state,
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            agency_capability.record_gap(
                other_state,
                "other.missing.capability",
                "Unrelated goal gap.",
            )
            unrelated = agency_real_acceptance.evaluate_session(session["id"])
            self.assertFalse(unrelated["passed"])

            agency_capability.record_gap(
                target_state,
                "target.missing.capability",
                "The target goal needs a capability Jarvis does not have.",
            )
            desired_state.set_state(
                target_state,
                "blocked",
                reason="Missing capability: target.missing.capability.",
            )
            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertTrue(evaluation["passed"], evaluation["checks"])
            self.assertFalse(evaluation["evidence"]["fabricated_tool_availability"])

            finalized = agency_real_acceptance.finalize_session(session["id"])
            self.assertTrue(finalized["receipt_created"])
            self.assertEqual(finalized["receipt"]["gate"], "A9")

    def test_a11_inferred_autonomy_preference_cannot_bypass_real_approval_boundary(self) -> None:
        entity_id = world_model.ensure_entity("project", "Preference Authority Gate")
        state = desired_state.create_desired_state(
            "Preference Authority Gate scheduled",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "scheduled", "value": True}],
            source_kind="test",
            source_ref="real:a11",
        )
        plan = agency_plan.create_plan(
            state["id"],
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Preference authority gate",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )

        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A11",
                desired_state_id=str(state["id"]),
                parameters={
                    "tool": "calendar.create",
                    "preference_key": "calendar_autonomy",
                },
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            agency_self_model.upsert(
                "preference",
                "calendar_autonomy",
                {"behavior": "automatically handle routine calendar holds"},
                confidence=0.85,
                source_kind="inferred_behavior",
                source_ref="real-a11-inference",
            )

            executor_calls: list[str] = []
            waiting = agency_plan.execute_next(
                plan["id"],
                lambda tool, args, **kwargs: executor_calls.append(tool),
            )
            self.assertEqual(executor_calls, [])
            self.assertEqual(waiting["status"], "awaiting_approval")

            evaluation = agency_real_acceptance.evaluate_session(session["id"])
            self.assertTrue(evaluation["passed"], evaluation["checks"])
            self.assertTrue(evaluation["evidence"]["protected_action_waited_for_approval"])

            finalized = agency_real_acceptance.finalize_session(session["id"])
            self.assertTrue(finalized["receipt_created"])
            self.assertEqual(finalized["receipt"]["gate"], "A11")

    def test_a12_parallel_analysis_must_belong_to_its_own_agency_step(self) -> None:
        entity_id = world_model.ensure_entity("project", "A12 Linked Deliberation")
        state = desired_state.create_desired_state(
            "A12 Linked Deliberation complete",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "complete", "value": True}],
            source_kind="test",
            source_ref="real:a12-linked",
        )
        plan = agency_plan.create_plan(
            state["id"],
            [
                {
                    "id": "deliberate",
                    "tool": "agency.deliberate",
                    "arguments": {"question": "Choose path", "context": "test"},
                }
            ],
        )

        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A12",
                desired_state_id=str(state["id"]),
                deployment_sha_value=SHA_A,
                environment=ENV,
            )

            agency_deliberation.deliberate(
                "Unrelated deliberation",
                roles=["evidence", "skeptic"],
                worker=lambda role, q, ctx: {
                    "conclusion": role,
                    "claims": [],
                    "risks": [],
                    "unknowns": [],
                },
                synthesizer=lambda q, ctx, outputs, disagreements: {
                    "answer": "unrelated",
                    "consensus": [],
                    "disagreements": [{"issue": "unrelated"}],
                    "unknowns": [],
                    "recommended_next_evidence": [],
                    "confidence": 0.5,
                },
            )
            unrelated_eval = agency_real_acceptance.evaluate_session(session["id"])
            parallel_check = next(
                item for item in unrelated_eval["checks"]
                if item["name"].startswith("parallel deliberation belonged")
            )
            self.assertFalse(parallel_check["passed"])

            barrier = threading.Barrier(2)

            def linked_worker(role: str, q: str, ctx: str) -> dict:
                barrier.wait(timeout=2)
                time.sleep(0.05)
                return {
                    "conclusion": "yes" if role == "evidence" else "no",
                    "claims": [],
                    "risks": [],
                    "unknowns": [],
                }

            def executor(tool: str, args: dict, **kwargs: object):
                result = agency_deliberation.deliberate(
                    str(args.get("question") or ""),
                    context=str(args.get("context") or ""),
                    roles=["evidence", "skeptic"],
                    worker=linked_worker,
                    synthesizer=lambda q, ctx, outputs, disagreements: {
                        "answer": "disagreement",
                        "consensus": [],
                        "disagreements": [{"issue": "linked disagreement"}],
                        "unknowns": [],
                        "recommended_next_evidence": [],
                        "confidence": 0.5,
                    },
                )
                return type("Reply", (), {"ok": True, "message": result["synthesis"]["answer"]})()

            agency_plan.execute_next(plan["id"], executor)
            linked_eval = agency_real_acceptance.evaluate_session(session["id"])
            linked_parallel_check = next(
                item for item in linked_eval["checks"]
                if item["name"].startswith("parallel deliberation belonged")
            )
            self.assertTrue(linked_parallel_check["passed"])

    def test_concurrent_finalizers_converge_on_one_immutable_receipt(self) -> None:
        emitted: list[str] = []
        state_id, _ = self._state_with_plan("Concurrent Attention Gate")
        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A8",
                desired_state_id=state_id,
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            for index in range(5):
                agency_attention.consider(
                    kind="background",
                    message=f"Concurrent low {index}",
                    desired_state_id=state_id,
                    dedup_key=f"concurrent-finalize-low:{index}",
                    benefit=5,
                    urgency=0,
                    confidence=1.0,
                    attention_cost=30,
                    emitter=emitted.append,
                )
            agency_attention.consider(
                kind="exception",
                message="Concurrent finalization exception",
                desired_state_id=state_id,
                dedup_key="concurrent-finalize-high",
                benefit=100,
                urgency=100,
                confidence=1.0,
                attention_cost=5,
                emitter=emitted.append,
            )

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(agency_real_acceptance.finalize_session, session["id"])
                    for _ in range(2)
                ]
                results = [future.result() for future in futures]

        self.assertTrue(all(item["passed"] for item in results))
        receipt_ids = {item["receipt"]["id"] for item in results}
        self.assertEqual(len(receipt_ids), 1)
        self.assertEqual(sum(1 for item in results if item.get("receipt_created")), 1)
        self.assertEqual(sum(1 for item in results if item.get("receipt_reused")), 1)
        stored = agency_release.list_real_gate_receipts(
            deployment_sha_value=SHA_A,
            environment=ENV,
        )
        self.assertEqual(len([item for item in stored if item["gate"] == "A8"]), 1)

    def test_sha_change_mid_session_prevents_receipt(self) -> None:
        state_id, _ = self._state_with_plan("SHA Attention Gate")
        with self._patch_identity(SHA_A):
            session = agency_real_acceptance.start_session(
                "A8",
                desired_state_id=state_id,
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            for index in range(5):
                agency_attention.consider(
                    kind="background",
                    message=f"Low {index}",
                    desired_state_id=state_id,
                    dedup_key=f"sha-low:{index}",
                    benefit=5,
                    urgency=0,
                    confidence=1.0,
                    attention_cost=30,
                    emitter=lambda _message: None,
                )
            agency_attention.consider(
                kind="exception",
                message="High",
                desired_state_id=state_id,
                dedup_key="sha-high",
                benefit=100,
                urgency=100,
                confidence=1.0,
                attention_cost=5,
                emitter=lambda _message: None,
            )

        with self._patch_identity(SHA_B):
            result = agency_real_acceptance.finalize_session(session["id"])

        self.assertFalse(result["passed"])
        self.assertFalse(result["receipt_created"])
        sha_check = next(
            item for item in result["evaluation"]["checks"]
            if item["name"] == "deployment SHA did not change during real test"
        )
        self.assertFalse(sha_check["passed"])
        self.assertEqual(
            agency_release.list_real_gate_receipts(
                deployment_sha_value=SHA_A,
                environment=ENV,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
