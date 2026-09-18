from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.agency_attention as agency_attention
import jarvis_mrb.agency_plan as agency_plan
import jarvis_mrb.agency_real_acceptance as agency_real_acceptance
import jarvis_mrb.agency_release as agency_release
import jarvis_mrb.agency_runtime as agency_runtime
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
            "attention_db": agency_attention.DB_PATH,
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
        agency_attention.DB_PATH = self.db
        world_verification.DB_PATH = self.db
        permissions.APP_DIR = self.base
        permissions.POLICY_PATH = self.base / "permissions.json"

        world_model.status()
        world_executive.status()
        desired_state.status()
        agency_plan.status()
        agency_runtime.status()
        agency_attention.status()
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
        agency_attention.DB_PATH = self.originals["attention_db"]
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
        with self._patch_identity():
            session = agency_real_acceptance.start_session(
                "A8",
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            for index in range(6):
                agency_attention.consider(
                    kind="background",
                    message=f"Low value {index}",
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

    def test_sha_change_mid_session_prevents_receipt(self) -> None:
        with self._patch_identity(SHA_A):
            session = agency_real_acceptance.start_session(
                "A8",
                deployment_sha_value=SHA_A,
                environment=ENV,
            )
            for index in range(5):
                agency_attention.consider(
                    kind="background",
                    message=f"Low {index}",
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
