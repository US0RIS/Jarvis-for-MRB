from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.agency_release as agency_release
import jarvis_mrb.world_model as world_model


SHA_A = "a" * 40
SHA_B = "b" * 40
ENV = "test-environment"


def evidence_for(gate: str) -> dict:
    base = {
        "real_services": True,
        "synthetic": False,
        "manual_orchestration": False,
    }
    extras = {
        "A1": {
            "restart_observed": True,
            "goal_recovered_without_restatement": True,
        },
        "A2": {
            "action_observation_cycles": 2,
            "desired_state_satisfied": True,
            "automatic_stop_observed": True,
        },
        "A3": {
            "protected_external_write_observed": True,
            "approval_resumed_same_plan": True,
            "denial_case_observed": True,
        },
        "A4": {
            "verified_real_write_observed": True,
            "failure_timeout_or_unverified_observed": True,
            "independent_readback_observed": True,
        },
        "A5": {
            "external_change_observed": True,
            "stale_path_invalidated": True,
            "replanned_without_goal_restatement": True,
        },
        "A6": {
            "dormant_state_observed": True,
            "wake_condition_changed": True,
            "reactivated_without_goal_restatement": True,
        },
        "A7": {
            "parallel_workers": 4,
            "parallel_overlap_observed": True,
            "material_disagreement_preserved": True,
        },
        "A8": {
            "low_value_changes": 10,
            "bounded_interruptions": 1,
            "duplicate_interruptions": 0,
            "interruption_reason_inspectable": True,
        },
        "A9": {
            "missing_capability_observed": True,
            "fabricated_tool_availability": False,
            "blocked_or_disabled_adapter_observed": True,
        },
        "A11": {
            "preference_authority_conflict_observed": True,
            "permission_policy_remained_authoritative": True,
        },
        "A12": {
            "private_information_retrieval": True,
            "public_research": True,
            "parallel_analysis": True,
            "protected_external_action": True,
            "independent_outcome_verification": True,
            "replan_after_injected_change": True,
            "final_desired_state_satisfied": True,
        },
    }
    return {**base, **extras[gate]}


class AgencyReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        self.a12_trace = self.base / "a12-real-trace.md"
        self.a12_trace.write_text("# A12 REAL trace\nObserved real scenario.\n", encoding="utf-8")
        self.original_app_dir = world_model.APP_DIR
        self.original_db = world_model.DB_PATH
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_model.status()
        agency_release.status()

    def tearDown(self) -> None:
        world_model.APP_DIR = self.original_app_dir
        world_model.DB_PATH = self.original_db
        self.temp.cleanup()

    def _record(self, gate: str, *, sha: str = SHA_A, env: str = ENV) -> dict:
        return agency_release.record_real_gate_receipt(
            gate,
            deployment_sha_value=sha,
            environment=env,
            harness=f"real-{gate.lower()}-acceptance",
            checks=[{"name": f"{gate} real acceptance", "passed": True, "evidence": "observed"}],
            evidence=evidence_for(gate),
            trace_ref=str(self.a12_trace) if gate == "A12" else "",
        )

    def test_real_gate_receipt_is_append_only(self) -> None:
        receipt = self._record("A1")
        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE agency_real_gate_receipts SET harness='changed' WHERE id=?",
                    (receipt["id"],),
                )
            conn.rollback()
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "DELETE FROM agency_real_gate_receipts WHERE id=?",
                    (receipt["id"],),
                )
        finally:
            conn.close()

        persisted = agency_release.get_receipt(receipt["id"])
        self.assertEqual(persisted["harness"], "real-a1-acceptance")

    def test_synthetic_or_synthetic_only_gate_cannot_be_recorded_as_real(self) -> None:
        with self.assertRaises(ValueError):
            agency_release.record_real_gate_receipt(
                "A1",
                deployment_sha_value=SHA_A,
                environment=ENV,
                harness="synthetic-acceptance",
                checks=[{"name": "fake", "passed": True}],
                evidence=evidence_for("A1"),
            )

        with self.assertRaises(ValueError):
            agency_release.record_real_gate_receipt(
                "A10",
                deployment_sha_value=SHA_A,
                environment=ENV,
                harness="real-a10",
                checks=[{"name": "fake", "passed": True}],
                evidence={
                    "real_services": True,
                    "synthetic": False,
                    "manual_orchestration": False,
                },
            )

    def test_a12_requires_human_readable_trace_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "trace_ref"):
            agency_release.record_real_gate_receipt(
                "A12",
                deployment_sha_value=SHA_A,
                environment=ENV,
                harness="real-a12",
                checks=[{"name": "A12", "passed": True}],
                evidence=evidence_for("A12"),
                trace_ref="",
            )

    def test_receipt_for_other_sha_does_not_count(self) -> None:
        self._record("A1", sha=SHA_B)
        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertIn("A1", status["missing_real_gates"])
        self.assertEqual(status["real_gate_receipts"], {})

    def test_all_real_receipts_still_do_not_release_without_validation_run(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)

        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertEqual(status["missing_real_gates"], [])
        self.assertFalse(status["release_ready"])
        self.assertTrue(any("validation run" in reason for reason in status["reasons"]))

    def test_release_ready_requires_same_sha_environment_validation_and_all_real_gates(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)

        agency_release.record_validation_run(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
            regression_summary="all tests passed",
            synthetic_summary="A1-A12 synthetic passed",
            diagnostics_summary="strict diagnostics clean",
        )
        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertTrue(status["release_ready"])
        self.assertEqual(status["missing_real_gates"], [])
        self.assertEqual(len(status["real_gate_receipts"]), len(agency_release.REAL_GATES))

        other_environment = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment="different-machine",
            diagnostics={"ok": True},
        )
        self.assertFalse(other_environment["release_ready"])
        self.assertEqual(other_environment["real_gate_receipts"], {})

    def test_deleted_a12_trace_invalidates_release_evidence(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)
        agency_release.record_validation_run(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
        )
        self.a12_trace.unlink()

        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertFalse(status["release_ready"])
        self.assertIn("A12", status["missing_real_gates"])
        self.assertIn("A12", status["invalid_real_gate_receipts"])

    def test_failed_validation_run_is_not_release_eligible(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)
        agency_release.record_validation_run(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=False,
            synthetic_ok=True,
            diagnostics_ok=True,
            regression_summary="one test failed",
        )
        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertFalse(status["release_ready"])


if __name__ == "__main__":
    unittest.main()
