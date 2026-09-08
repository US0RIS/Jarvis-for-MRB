from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import jarvis_mrb.tool_audit as tool_audit
import jarvis_mrb.verification_routing as verification_routing
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_verification as world_verification


class VerificationRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_verification.DB_PATH = self.db
        world_model.status()
        world_verification.status()
        self.original_observe = world_verification._observe

    def tearDown(self) -> None:
        world_verification._observe = self.original_observe
        self.temp.cleanup()

    def _latest(self) -> sqlite3.Row:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM action_verifications ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            assert row is not None
            return row
        finally:
            conn.close()

    def _calendar_verification(self) -> str:
        action_event_id = world_model.record_tool_execution(
            "calendar.create",
            {"summary": "Jarvis Live Verification"},
            ok=True,
            message="Created calendar event 'Jarvis Live Verification'.",
        )
        return world_verification.register_execution(
            "calendar.create",
            {
                "summary": "Jarvis Live Verification",
                "start": "{'date_time': '2026-09-08T23:55:00-07:00'}",
                "end": "{'date_time': '2026-09-09T00:00:00-07:00'}",
            },
            SimpleNamespace(ok=True, message="Created calendar event 'Jarvis Live Verification'."),
            action_event_id=action_event_id,
        )

    def test_tool_audit_normalizes_calendar_verification_arguments(self) -> None:
        args = {
            "summary": "Jarvis Live Verification",
            "start": {"date_time": "2026-09-08T23:55:00-07:00"},
            "end": "{'date_time': '2026-09-09T00:00:00-07:00'}",
        }
        normalized = tool_audit._verification_args("calendar.create", args)
        self.assertEqual(normalized["start"], "2026-09-08T23:55:00-07:00")
        self.assertEqual(normalized["end"], "2026-09-09T00:00:00-07:00")

    def test_did_that_work_repairs_legacy_calendar_expectation_and_checks_fresh(self) -> None:
        verification_id = self._calendar_verification()

        observed: dict[str, str] = {}

        def observe(verifier: str, expected: dict[str, object]) -> tuple[str, str]:
            observed["verifier"] = verifier
            observed["start"] = str(expected.get("start") or "")
            observed["end"] = str(expected.get("end") or "")
            return "verified", "Calendar read-back contains the created event."

        world_verification._observe = observe
        reply = verification_routing.reply_for_query("Did that work?")

        self.assertIsNotNone(reply)
        assert reply is not None
        self.assertTrue(reply.startswith("Yes. I independently verified"), reply)
        self.assertEqual(observed["verifier"], "calendar_event_exists")
        self.assertEqual(observed["start"], "2026-09-08T23:55:00-07:00")
        self.assertEqual(observed["end"], "2026-09-09T00:00:00-07:00")

        row = self._latest()
        self.assertEqual(str(row["id"]), verification_id)
        self.assertEqual(str(row["status"]), "verified")
        expected = json.loads(str(row["expected_json"]))
        self.assertEqual(expected["start"], "2026-09-08T23:55:00-07:00")
        self.assertEqual(expected["end"], "2026-09-09T00:00:00-07:00")

    def test_explicit_query_can_recover_timed_out_verification_when_evidence_arrives_late(self) -> None:
        verification_id = self._calendar_verification()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                """
                UPDATE action_verifications
                SET status='timed_out',next_check_at=NULL,
                    last_evidence='Verification deadline elapsed before evidence was visible.'
                WHERE id=?
                """,
                (verification_id,),
            )
            conn.commit()
        finally:
            conn.close()

        world_verification._observe = lambda verifier, expected: (
            "verified",
            "Calendar read-back now contains the created event with matching title/start/end.",
        )

        reply = verification_routing.reply_for_query("Did that work?")
        self.assertIsNotNone(reply)
        assert reply is not None
        self.assertTrue(reply.startswith("Yes. I independently verified"), reply)

        row = self._latest()
        self.assertEqual(str(row["id"]), verification_id)
        self.assertEqual(str(row["status"]), "verified")
        self.assertIn("now contains the created event", str(row["last_evidence"]))

    def test_late_inconclusive_recheck_preserves_timeout_but_records_fresh_attempt(self) -> None:
        verification_id = self._calendar_verification()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "UPDATE action_verifications SET status='timed_out',next_check_at=NULL,attempts=4 WHERE id=?",
                (verification_id,),
            )
            conn.commit()
        finally:
            conn.close()

        world_verification._observe = lambda verifier, expected: (
            "pending",
            "Created calendar event is still not independently visible.",
        )

        reply = verification_routing.reply_for_query("Did that work?")
        self.assertIsNotNone(reply)
        assert reply is not None
        self.assertTrue(reply.startswith("I still could not independently verify"), reply)

        row = self._latest()
        self.assertEqual(str(row["status"]), "timed_out")
        self.assertEqual(int(row["attempts"]), 5)
        self.assertIn("still not independently visible", str(row["last_evidence"]))

    def test_non_outcome_question_is_not_intercepted(self) -> None:
        self.assertIsNone(verification_routing.reply_for_query("Create a calendar event tomorrow."))
        self.assertIsNone(verification_routing.reply_for_query("What is verification in software testing?"))


if __name__ == "__main__":
    unittest.main()
