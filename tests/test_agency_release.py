from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.agency_real_acceptance as agency_real_acceptance
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
            "completed_work_preserved": True,
            "evidence_preserved": True,
            "pending_approval_preserved": True,
            "next_evaluation_preserved": True,
            "goal_recovered_without_restatement": True,
        },
        "A2": {
            "action_observation_cycles": 2,
            "independent_observation_cycles": 2,
            "second_action_followed_first_observation": True,
            "intermediate_unsatisfied_observed": True,
            "desired_state_satisfied": True,
            "automatic_stop_observed": True,
            "goal_not_repeated": True,
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
            "provenance_structurally_bounded": True,
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
            "protected_action_waited_for_approval": True,
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
        agency_real_acceptance.status()
        agency_release.status()

    def tearDown(self) -> None:
        world_model.APP_DIR = self.original_app_dir
        world_model.DB_PATH = self.original_db
        self.temp.cleanup()

    def _record(
        self,
        gate: str,
        *,
        sha: str = SHA_A,
        env: str = ENV,
        trace_ref: str | None = None,
        harness: str = "agency-real-gate-session-v1",
        finalization_context: bool = True,
    ) -> dict:
        checks = [{"name": f"{gate} real acceptance", "passed": True, "evidence": "observed"}]
        evidence = evidence_for(gate)
        session_id = f"agency-real-session:test-{uuid.uuid4()}"
        evaluation = {
            "session_id": session_id,
            "gate": gate,
            "passed": True,
            "checks": checks,
            "evidence": evidence,
            "manual_orchestration_events": [],
            "evaluated_at": "2030-01-01T00:00:00+00:00",
        }
        parameters_json = "{}"
        baseline_json = "{}"
        started_at = "2030-01-01T00:00:00+00:00"
        session_hash = agency_release._live_session_digest(
            session_id=session_id,
            gate=gate,
            deployment_sha_value=sha,
            environment=env,
            desired_state_id="",
            parameters_json=parameters_json,
            baseline_json=baseline_json,
            started_at=started_at,
        )
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                """
                INSERT INTO agency_real_gate_sessions(
                    id,gate,deployment_sha,environment_fingerprint,desired_state_id,
                    parameters_json,baseline_json,session_hash,status,last_evaluation_json,
                    receipt_id,started_at
                ) VALUES(?,?,?,?,?,?,?,?, 'running',?,'',?)
                """,
                (
                    session_id,
                    gate,
                    sha,
                    env,
                    "",
                    parameters_json,
                    baseline_json,
                    session_hash,
                    json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
                    started_at,
                ),
            )
            conn.commit()

        actual_trace = (
            str(self.a12_trace) if gate == "A12" and trace_ref is None
            else str(trace_ref or "")
        )
        payload = agency_release._real_receipt_context_payload(
            gate=gate,
            deployment_sha_value=sha,
            environment=env,
            harness=harness,
            checks=checks,
            evidence=evidence,
            trace_ref=actual_trace,
            session_id=session_id,
        )
        if finalization_context:
            with agency_release._real_receipt_recording_context(payload):
                receipt = agency_release.record_real_gate_receipt(
                    gate,
                    deployment_sha_value=sha,
                    environment=env,
                    harness=harness,
                    checks=checks,
                    evidence=evidence,
                    trace_ref=actual_trace,
                    session_id=session_id,
                )
        else:
            receipt = agency_release.record_real_gate_receipt(
                gate,
                deployment_sha_value=sha,
                environment=env,
                harness=harness,
                checks=checks,
                evidence=evidence,
                trace_ref=actual_trace,
                session_id=session_id,
            )
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                """
                UPDATE agency_real_gate_sessions
                SET status='completed',receipt_id=?,completed_at=?
                WHERE id=?
                """,
                (receipt["id"], "2030-01-01T00:01:00+00:00", session_id),
            )
            conn.commit()
        return receipt

    def _validation(self, **overrides: object) -> dict:
        values: dict[str, object] = {
            "deployment_sha_value": SHA_A,
            "environment": ENV,
            "source_root_value": str(self.base),
            "compile_ok": True,
            "regression_ok": True,
            "synthetic_ok": True,
            "diagnostics_ok": True,
            "tree_clean_before": True,
            "tree_clean_after": True,
            "regression_summary": "",
            "synthetic_summary": "",
            "diagnostics_summary": "",
        }
        values.update(overrides)
        payload = agency_release._validation_context_payload(
            deployment_sha_value=str(values["deployment_sha_value"]),
            environment=str(values["environment"]),
            source_root_value=str(values["source_root_value"]),
            compile_ok=bool(values["compile_ok"]),
            regression_ok=bool(values["regression_ok"]),
            synthetic_ok=bool(values["synthetic_ok"]),
            diagnostics_ok=bool(values["diagnostics_ok"]),
            tree_clean_before=bool(values["tree_clean_before"]),
            tree_clean_after=bool(values["tree_clean_after"]),
            regression_summary=str(values["regression_summary"])[-5000:],
            synthetic_summary=str(values["synthetic_summary"])[-5000:],
            diagnostics_summary=str(values["diagnostics_summary"])[-5000:],
        )
        with agency_release._validation_recording_context(payload):
            return agency_release.record_validation_run(**values)

    def test_run_full_validation_is_only_supported_validation_minter(self) -> None:
        (self.base / "jarvis_mrb").mkdir(exist_ok=True)
        (self.base / "tests").mkdir(exist_ok=True)

        with (
            patch.object(agency_release, "deployment_sha", return_value=SHA_A),
            patch.object(agency_release, "environment_fingerprint", return_value=ENV),
            patch.object(agency_release, "_git_worktree_clean", return_value=(True, "")),
            patch.object(agency_release, "_run_command", return_value=(True, "stage passed")),
            patch("jarvis_mrb.world_diagnostics.validate", return_value={"ok": True}),
        ):
            result = agency_release.run_full_validation(root=self.base)

        self.assertTrue(result["ok"])
        self.assertTrue(result["recorded"])
        run = result["validation_run"]
        self.assertEqual(run["harness"], agency_release._VALIDATION_HARNESS)
        self.assertTrue(result["release_status"]["validation_hash_ok"])
        self.assertFalse(result["release_status"]["release_ready"])
        self.assertTrue(result["release_status"]["missing_real_gates"])
        self.assertEqual(agency_release._VALIDATION_CONTEXT.get(), "")

    def test_low_level_validation_writer_rejects_asserted_pass_flags(self) -> None:
        with self.assertRaisesRegex(ValueError, "run_full_validation"):
            agency_release.record_validation_run(
                deployment_sha_value=SHA_A,
                environment=ENV,
                source_root_value=str(self.base),
                compile_ok=True,
                regression_ok=True,
                synthetic_ok=True,
                diagnostics_ok=True,
                tree_clean_before=True,
                tree_clean_after=True,
            )

    def test_installation_identity_is_immutable(self) -> None:
        installation_id = agency_release._installation_id()
        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE agency_installation_identity SET installation_id='changed' WHERE singleton=1"
                )
            conn.rollback()
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "DELETE FROM agency_installation_identity WHERE singleton=1"
                )
        finally:
            conn.close()

        self.assertEqual(agency_release._installation_id(), installation_id)

    def test_environment_fingerprint_changes_with_permission_posture(self) -> None:
        with (
            patch.object(agency_release, "_host_machine_identity", return_value="host-policy"),
            patch("jarvis_mrb.permissions._load", return_value={
                "read": "auto",
                "local_write": "auto",
                "external_write": "confirm",
                "destructive": "confirm",
                "security": "confirm",
            }),
        ):
            confirmed = agency_release.environment_fingerprint()

        with (
            patch.object(agency_release, "_host_machine_identity", return_value="host-policy"),
            patch("jarvis_mrb.permissions._load", return_value={
                "read": "auto",
                "local_write": "auto",
                "external_write": "auto",
                "destructive": "confirm",
                "security": "confirm",
            }),
        ):
            weakened = agency_release.environment_fingerprint()

        self.assertNotEqual(confirmed, weakened)

    def test_environment_fingerprint_binds_host_and_source_path(self) -> None:
        with (
            patch.object(agency_release, "_host_machine_identity", return_value="host-A"),
            patch.object(agency_release, "source_root", return_value=self.base / "source-A"),
        ):
            first = agency_release.environment_fingerprint()

        with (
            patch.object(agency_release, "_host_machine_identity", return_value="host-B"),
            patch.object(agency_release, "source_root", return_value=self.base / "source-A"),
        ):
            other_host = agency_release.environment_fingerprint()

        with (
            patch.object(agency_release, "_host_machine_identity", return_value="host-A"),
            patch.object(agency_release, "source_root", return_value=self.base / "source-B"),
        ):
            other_source = agency_release.environment_fingerprint()

        self.assertNotEqual(first, other_host)
        self.assertNotEqual(first, other_source)

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
        self.assertEqual(persisted["harness"], "agency-real-gate-session-v1")

    def test_persisted_passing_session_cannot_mint_receipt_outside_finalize_context(self) -> None:
        with self.assertRaisesRegex(ValueError, "finalize_session"):
            self._record("A1", finalization_context=False)

        receipts = agency_release.list_real_gate_receipts(
            deployment_sha_value=SHA_A,
            environment=ENV,
        )
        self.assertEqual(receipts, [])

    def test_low_level_real_receipt_writer_rejects_unbound_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "live acceptance session"):
            agency_release.record_real_gate_receipt(
                "A1",
                deployment_sha_value=SHA_A,
                environment=ENV,
                harness="agency-real-gate-session-v1",
                checks=[{"name": "A1 direct bypass", "passed": True, "evidence": "claimed"}],
                evidence=evidence_for("A1"),
                session_id="",
            )

    def test_a1_receipt_rejects_incomplete_restart_continuity_evidence(self) -> None:
        evidence = evidence_for("A1")
        evidence["pending_approval_preserved"] = False
        with self.assertRaisesRegex(ValueError, "pending_approval_preserved"):
            agency_release._validate_gate_evidence("A1", evidence, "")

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

    def test_a2_receipt_rejects_step_count_without_independent_causal_cycles(self) -> None:
        evidence = evidence_for("A2")
        evidence["intermediate_unsatisfied_observed"] = False
        with self.assertRaisesRegex(ValueError, "intermediate_unsatisfied_observed"):
            agency_release._validate_gate_evidence("A2", evidence, "")

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

        self._validation(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
            tree_clean_before=True,
            tree_clean_after=True,
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

    def test_modified_a12_trace_invalidates_bound_receipt(self) -> None:
        receipt = self._record("A12")
        original_hash = receipt["trace_sha256"]
        self.a12_trace.write_text(
            "# replaced trace\nThis no longer matches the accepted evidence.\n",
            encoding="utf-8",
        )

        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertIn("A12", status["missing_real_gates"])
        reasons = status["invalid_real_gate_receipts"].get("A12", [])
        self.assertTrue(any("trace content hash mismatch" in item["reason"] for item in reasons))
        self.assertNotEqual(agency_release._file_sha256(str(self.a12_trace)), original_hash)

    def test_deleted_a12_trace_invalidates_release_evidence(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)
        self._validation(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
            tree_clean_before=True,
            tree_clean_after=True,
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

    def test_multiple_immutable_receipts_for_same_gate_sha_environment_are_allowed(self) -> None:
        first = self._record("A1")
        second = self._record("A1")
        self.assertNotEqual(first["id"], second["id"])

        receipts = agency_release.list_real_gate_receipts(
            deployment_sha_value=SHA_A,
            environment=ENV,
        )
        a1 = [item for item in receipts if item["gate"] == "A1"]
        self.assertEqual(len(a1), 2)

    def test_release_uses_older_valid_a12_receipt_if_newest_trace_is_lost(self) -> None:
        older_trace = self.base / "a12-older.md"
        newer_trace = self.base / "a12-newer.md"
        older_trace.write_text("# older valid A12 trace\n", encoding="utf-8")
        newer_trace.write_text("# newer valid A12 trace\n", encoding="utf-8")

        older = self._record("A12", trace_ref=str(older_trace))
        newer = self._record("A12", trace_ref=str(newer_trace))
        newer_trace.unlink()

        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertNotIn("A12", status["missing_real_gates"])
        self.assertEqual(status["real_gate_receipts"]["A12"], older["id"])
        invalid_ids = {
            item["receipt_id"]
            for item in status["invalid_real_gate_receipts"].get("A12", [])
        }
        self.assertIn(newer["id"], invalid_ids)

    def test_completed_session_retry_rejects_corrupted_receipt(self) -> None:
        receipt = self._record("A1")
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("DROP TRIGGER agency_real_gate_receipts_immutable_update")
            conn.execute(
                "UPDATE agency_real_gate_receipts SET harness='tampered' WHERE id=?",
                (receipt["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        retried = agency_real_acceptance.finalize_session(receipt["session_id"])
        self.assertTrue(retried["already_finalized"])
        self.assertFalse(retried["passed"])
        self.assertFalse(retried["receipt_reused"])
        self.assertIn("hash mismatch", retried["receipt_validation_error"])

    def test_content_hash_detects_receipt_corruption(self) -> None:
        receipt = self._record("A1")
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("DROP TRIGGER agency_real_gate_receipts_immutable_update")
            conn.execute(
                "UPDATE agency_real_gate_receipts SET harness='tampered' WHERE id=?",
                (receipt["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertIn("A1", status["missing_real_gates"])
        reasons = status["invalid_real_gate_receipts"].get("A1", [])
        self.assertTrue(any("hash mismatch" in item["reason"] for item in reasons))

    def test_legacy_unique_receipt_schema_migrates_to_append_only_attempts(self) -> None:
        conn = sqlite3.connect(self.db)
        try:
            conn.executescript(
                """
                DROP TRIGGER IF EXISTS agency_real_gate_receipts_immutable_update;
                DROP TRIGGER IF EXISTS agency_real_gate_receipts_immutable_delete;
                DROP INDEX IF EXISTS idx_agency_real_gate_receipts_release;
                DROP INDEX IF EXISTS idx_agency_real_gate_receipts_session;
                DROP TABLE agency_real_gate_receipts;
                CREATE TABLE agency_real_gate_receipts (
                    id TEXT PRIMARY KEY,
                    gate TEXT NOT NULL,
                    deployment_sha TEXT NOT NULL,
                    environment_fingerprint TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    checks_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    trace_ref TEXT NOT NULL DEFAULT '',
                    recorded_at TEXT NOT NULL,
                    UNIQUE(gate,deployment_sha,environment_fingerprint)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        with agency_release._connect():
            pass

        first = self._record("A1")
        second = self._record("A1")
        self.assertNotEqual(first["id"], second["id"])

    def test_validation_must_postdate_selected_real_receipts(self) -> None:
        self._validation(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
            tree_clean_before=True,
            tree_clean_after=True,
            regression_summary="pre-acceptance validation",
        )
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)

        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertFalse(status["release_ready"])
        self.assertFalse(status["validation_after_real_gates"])
        self.assertTrue(
            any("predates" in reason for reason in status["reasons"])
        )

        self._validation(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
            tree_clean_before=True,
            tree_clean_after=True,
            regression_summary="post-acceptance validation",
        )
        after = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertTrue(after["validation_after_real_gates"])
        self.assertTrue(after["release_ready"])

    def test_validation_hash_detects_post_run_corruption(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)
        run = self._validation(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
            tree_clean_before=True,
            tree_clean_after=True,
            regression_summary="all tests passed",
        )
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("DROP TRIGGER agency_release_validation_runs_immutable_update")
            conn.execute(
                "UPDATE agency_release_validation_runs SET regression_ok=0 WHERE id=?",
                (run["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertFalse(status["release_ready"])
        self.assertFalse(status["validation_hash_ok"])

    def test_validation_record_with_dirty_tree_is_not_release_eligible(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)
        self._validation(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=True,
            synthetic_ok=True,
            diagnostics_ok=True,
            tree_clean_before=True,
            tree_clean_after=False,
            regression_summary="Tests passed but modified tracked files.",
        )
        status = agency_release.release_status(
            deployment_sha_value=SHA_A,
            environment=ENV,
            diagnostics={"ok": True},
        )
        self.assertFalse(status["release_ready"])
        self.assertTrue(any("validation run" in reason for reason in status["reasons"]))

    def test_failed_validation_run_is_not_release_eligible(self) -> None:
        for gate in sorted(agency_release.REAL_GATES):
            self._record(gate)
        self._validation(
            deployment_sha_value=SHA_A,
            environment=ENV,
            source_root_value=str(self.base),
            compile_ok=True,
            regression_ok=False,
            synthetic_ok=True,
            diagnostics_ok=True,
            tree_clean_before=True,
            tree_clean_after=True,
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
