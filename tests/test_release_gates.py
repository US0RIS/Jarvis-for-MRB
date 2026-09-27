from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.release_gates as gates

SHA = "a" * 40
ENV = "env-fingerprint-1"


def _identity(sha: str = SHA, clean: bool = True, env: str = ENV) -> dict:
    return {
        "code_sha": sha,
        "worktree_clean": clean,
        "worktree_detail": "" if clean else " M jarvis_mrb/agent.py",
        "environment_fingerprint": env,
        "world_schema_ready": True,
        "world_schema_version": 5,
        "world_schema_target": 5,
        "pid": 1,
        "python": "3.12",
    }


def _service(sha: str = SHA, env: str = ENV) -> dict:
    return {**_identity(sha=sha, env=env), "reachable": True, "boot_id": "boot-1"}


_PASSING_RUN = {
    "id": "validation-1",
    "recorded_at": "2026-09-27T00:00:00+00:00",
    "compile_ok": 1,
    "regression_ok": 1,
    "synthetic_ok": 1,
    "diagnostics_ok": 1,
    "tree_clean_before": 1,
    "tree_clean_after": 1,
}

_FIELDS = {
    "user_entry_surface": "physical iPhone Jarvis app, Presence panel",
    "literal_user_request": "Turn on the desk lamp",
    "devices": "iPhone 16 Pro; Windows host",
    "real_services_or_providers": "Apple HomeKit",
    "preconditions": "lamp off",
    "expected_observable_result": "lamp on and HomeKit reads on",
    "actual_observable_result": "lamp turned on",
    "external_readback_or_independent_evidence": "HomeKit readback on=true",
    "permission_or_grant_evidence": "one-use 120s grant",
    "failure_case_exercised": "revoked grant refused second actuation",
    "artifacts": "presence receipt 1234",
    "notes": "",
}


class ReleaseGateLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        patches = [
            patch.object(gates, "LEDGER_PATH", base / "ledger.sqlite3"),
            patch.object(gates, "EXPORT_DIR", base / "export"),
            patch.object(gates, "build_identity", side_effect=lambda: _identity()),
            patch.object(gates, "service_identity", side_effect=lambda timeout=5.0: _service()),
            patch("jarvis_mrb.agency_release.latest_validation_run", return_value=dict(_PASSING_RUN)),
            patch.object(gates, "_load_optional_evaluators", return_value=None),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        # The generic evaluator table must not leak between tests.
        saved = dict(gates.EVALUATORS)
        self.addCleanup(lambda: (gates.EVALUATORS.clear(), gates.EVALUATORS.update(saved)))

    def test_freeze_refuses_dirty_tree_and_missing_validation(self) -> None:
        with patch.object(gates, "build_identity", return_value=_identity(clean=False)):
            with self.assertRaisesRegex(ValueError, "dirty"):
                gates.freeze()
        with patch("jarvis_mrb.agency_release.latest_validation_run", return_value=None):
            with self.assertRaisesRegex(ValueError, "validation"):
                gates.freeze()
        failing = {**_PASSING_RUN, "regression_ok": 0}
        with patch("jarvis_mrb.agency_release.latest_validation_run", return_value=failing):
            with self.assertRaisesRegex(ValueError, "validation"):
                gates.freeze()
        self.assertIsNone(gates.current_candidate())

    def test_session_requires_frozen_matching_checkout(self) -> None:
        with self.assertRaisesRegex(ValueError, "No frozen"):
            gates.start_session("C19")
        gates.freeze()
        with patch.object(gates, "build_identity", return_value=_identity(sha="b" * 40)):
            with self.assertRaisesRegex(ValueError, "not the frozen candidate"):
                gates.start_session("C19")
        with self.assertRaisesRegex(ValueError, "Unknown gate"):
            gates.start_session("C99")

    def test_pass_refused_without_human_observation_or_fields(self) -> None:
        gates.freeze()
        session = gates.start_session("C19")
        with self.assertRaisesRegex(ValueError, "human attestation required"):
            gates.finalize_session(session["id"], result="PASS", fields=_FIELDS)
        partial = {**_FIELDS, "failure_case_exercised": ""}
        with self.assertRaisesRegex(ValueError, "failure_case_exercised"):
            gates.finalize_session(
                session["id"], result="PASS", fields=partial,
                attestations=[{"statement": "the lamp visibly turned on"}],
            )
        self.assertEqual(gates.records(), [])

    def test_pass_refused_when_running_service_is_another_sha(self) -> None:
        gates.freeze()
        session = gates.start_session("C19")
        with patch.object(gates, "service_identity", return_value=_service(sha="c" * 40)):
            with self.assertRaisesRegex(ValueError, "running Jarvis service"):
                gates.finalize_session(
                    session["id"], result="PASS", fields=_FIELDS,
                    attestations=[{"statement": "the lamp visibly turned on"}],
                )

    def test_gate_evaluator_failure_blocks_pass_but_fail_is_recorded(self) -> None:
        gates.register_evaluator("C19", lambda session: [gates._check("presence readback", False, "none")])
        gates.freeze()
        session = gates.start_session("C19")
        with self.assertRaisesRegex(ValueError, "presence readback"):
            gates.finalize_session(
                session["id"], result="PASS", fields=_FIELDS,
                attestations=[{"statement": "the lamp visibly turned on"}],
            )
        record = gates.finalize_session(session["id"], result="FAIL", fields={"actual_observable_result": "no readback"})
        self.assertEqual(record["result"], "FAIL")
        with self.assertRaisesRegex(ValueError, "already finalized"):
            gates.finalize_session(session["id"], result="FAIL", fields={})
        self.assertEqual(gates.release_status()["gates"]["C19"]["state"], "FAIL")

    def test_agency_backed_gate_requires_valid_same_session_receipt(self) -> None:
        gates.freeze()
        session = gates.start_session("C04")
        with patch("jarvis_mrb.agency_release.list_real_gate_receipts", return_value=[]):
            evaluation = gates.evaluate_session(session["id"])
        self.assertFalse(evaluation["all_checks_passed"])
        receipt = {"id": "r1", "gate": "A1", "recorded_at": "2999-01-01T00:00:00+00:00"}
        with (
            patch("jarvis_mrb.agency_release.list_real_gate_receipts", return_value=[receipt]),
            patch("jarvis_mrb.agency_release.validate_real_gate_receipt", return_value={"valid": True}),
        ):
            evaluation = gates.evaluate_session(session["id"])
        self.assertTrue(evaluation["all_checks_passed"], evaluation)
        stale = {"id": "r0", "gate": "A1", "recorded_at": "2000-01-01T00:00:00+00:00"}
        with (
            patch("jarvis_mrb.agency_release.list_real_gate_receipts", return_value=[stale]),
            patch("jarvis_mrb.agency_release.validate_real_gate_receipt", return_value={"valid": True}),
        ):
            self.assertFalse(gates.evaluate_session(session["id"])["all_checks_passed"])

    def test_pass_record_is_append_only_and_hash_chained(self) -> None:
        gates.register_evaluator("C19", lambda session: [gates._check("presence readback", True, "on")])
        gates.freeze()
        first = gates.start_session("C19")
        gates.finalize_session(first["id"], result="FAIL", fields={"actual_observable_result": "timeout"})
        second = gates.start_session("C19")
        record = gates.finalize_session(
            second["id"], result="PASS", fields=_FIELDS,
            attestations=[{"statement": "the lamp visibly turned on", "observer": "user"}],
        )
        self.assertEqual(record["result"], "PASS")
        self.assertTrue(gates.verify_chain()["ok"])
        status = gates.release_status()
        self.assertEqual(status["gates"]["C19"]["state"], "PASS")
        self.assertFalse(status["release_complete"])
        self.assertEqual([item["result"] for item in gates.records(gate="C19")], ["FAIL", "PASS"])
        with sqlite3.connect(gates.LEDGER_PATH) as conn:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE release_gate_records SET result='PASS' WHERE result='FAIL'")
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM release_gate_records")
        exported = list((Path(self.tmp.name) / "export").rglob("C19-PASS-*.json"))
        self.assertEqual(len(exported), 1)

    def test_refreeze_on_new_sha_invalidates_previous_passes(self) -> None:
        gates.register_evaluator("C19", lambda session: [gates._check("presence readback", True, "on")])
        gates.freeze()
        session = gates.start_session("C19")
        gates.finalize_session(
            session["id"], result="PASS", fields=_FIELDS,
            attestations=[{"statement": "the lamp visibly turned on"}],
        )
        new_sha = "d" * 40
        with (
            patch.object(gates, "build_identity", return_value=_identity(sha=new_sha)),
            patch.object(gates, "service_identity", return_value=_service(sha=new_sha)),
        ):
            gates.freeze()
            self.assertEqual(gates.release_status()["gates"]["C19"]["state"], "UNPROVEN")

    def test_client_builds_are_recorded(self) -> None:
        gates.record_client_seen(device_id="dev-1", build_sha=SHA, model="iPhone iOS 26")
        gates.record_client_seen(device_id="dev-1", build_sha=SHA, model="iPhone iOS 26")
        builds = gates.client_builds()
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds[0]["requests"], 2)


if __name__ == "__main__":
    unittest.main()


class ReleaseIdentityServiceTests(unittest.TestCase):
    def test_identity_endpoint_and_client_build_recording_require_auth(self) -> None:
        from fastapi.testclient import TestClient

        from jarvis_mrb import service

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(gates, "LEDGER_PATH", Path(tmp) / "ledger.sqlite3"), \
                patch.object(service, "API_TOKEN", "private-secret"), \
                patch.object(gates, "build_identity", return_value=_identity()):
            service._client_seen_at.clear()
            client = TestClient(service.app)
            headers = {"X-Jarvis-Client-Build": SHA, "X-Jarvis-Client-Device": "dev-9"}
            denied = client.get("/release/identity", headers=headers)
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(gates.client_builds(), [])
            allowed = client.get(
                "/release/identity",
                headers={**headers, "Authorization": "Bearer private-secret"},
            )
            self.assertEqual(allowed.status_code, 200)
            body = allowed.json()
            self.assertEqual(body["code_sha"], SHA)
            self.assertTrue(body["boot_id"])
            self.assertEqual(allowed.headers["Cache-Control"], "private, no-store")
            self.assertEqual([item["build_sha"] for item in gates.client_builds()], [SHA])
