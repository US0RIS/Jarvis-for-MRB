from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jarvis_mrb.tool_audit as tool_audit
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_executive_loop as world_executive_loop
import jarvis_mrb.world_intent_capture as world_intent_capture
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_verification as world_verification


class WorldVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_linker.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        world_executive_loop.DB_PATH = self.db
        world_verification.DB_PATH = self.db
        world_model.status()
        world_linker.status()
        world_executive.status()
        world_executive_loop.status()
        world_verification.status()
        self.original_observe = world_verification._observe
        with tool_audit._LOCK:
            tool_audit._STAGED_EXECUTIVE.clear()

    def tearDown(self) -> None:
        world_verification._observe = self.original_observe
        with tool_audit._LOCK:
            tool_audit._STAGED_EXECUTIVE.clear()
        self.temp.cleanup()

    def _rows(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _goal_and_decision(self) -> tuple[str, str]:
        events = world_intent_capture.capture(
            "We're trying to get Project Apollo signed by Friday.",
            session_id="verification-test",
        )
        self.assertEqual(len(events), 1)
        world_linker.link_event(events[0])
        world_executive.refresh_intentions()
        world_executive_loop.refresh()
        intention = self._rows("SELECT id FROM intentions WHERE status='active' LIMIT 1")[0]
        decision = self._rows(
            "SELECT id FROM executive_decisions WHERE intention_id=? AND status='current' LIMIT 1",
            (str(intention["id"]),),
        )[0]
        return str(intention["id"]), str(decision["id"])

    def _action_event(self, tool: str = "gmail.send", ok: bool = True) -> int:
        return world_model.record_tool_execution(
            tool,
            {"recipient": "daniel@example.com", "subject": "Apollo", "body": "<redacted>"},
            ok=ok,
            message="tool execution receipt",
        )

    def test_read_tool_return_value_closes_immediately(self) -> None:
        action_event = self._action_event(tool="knowledge.search", ok=True)
        verification_id = world_verification.register_execution(
            "knowledge.search",
            {"query": "Project Apollo indemnity cap", "limit": 5},
            SimpleNamespace(ok=True, message="Relevant unified-knowledge matches: ..."),
            action_event_id=action_event,
        )
        row = self._rows("SELECT status,verifier FROM action_verifications WHERE id=?", (verification_id,))[0]
        self.assertEqual(str(row["status"]), "verified")
        self.assertEqual(str(row["verifier"]), "return_value")

    def test_gmail_verification_prefers_exact_provider_message_id(self) -> None:
        action_event = self._action_event()
        verification_id = world_verification.register_execution(
            "gmail.send",
            {
                "recipient": "daniel@example.com",
                "subject": "Apollo",
                "body": "Please send the schedules.",
            },
            SimpleNamespace(
                ok=True,
                message="Sent email to daniel@example.com.",
                data={
                    "message_id": "gmail-message-123",
                    "email": "daniel@example.com",
                },
            ),
            action_event_id=action_event,
        )
        row = self._rows(
            "SELECT expected_json FROM action_verifications WHERE id=?",
            (verification_id,),
        )[0]
        expected = json.loads(str(row["expected_json"]))
        self.assertEqual(expected["message_id"], "gmail-message-123")

        with patch(
            "jarvis_mrb.tools.google.query_emails",
            return_value=SimpleNamespace(
                ok=True,
                message="Found one sent message.",
                data={"emails": [{"id": "gmail-message-123"}]},
            ),
        ):
            status, evidence = world_verification._gmail_observation(expected)

        self.assertEqual(status, "verified")
        self.assertIn("gmail-message-123", evidence)

    def test_calendar_verification_prefers_exact_provider_event_id(self) -> None:
        action_event = world_model.record_tool_execution(
            "calendar.create",
            {
                "summary": "Apollo signing",
                "start": "2030-01-01T09:00:00-08:00",
                "end": "2030-01-01T09:30:00-08:00",
            },
            ok=True,
            message="calendar execution receipt",
        )
        verification_id = world_verification.register_execution(
            "calendar.create",
            {
                "summary": "Apollo signing",
                "start": "2030-01-01T09:00:00-08:00",
                "end": "2030-01-01T09:30:00-08:00",
            },
            SimpleNamespace(
                ok=True,
                message="Created calendar event 'Apollo signing'.",
                data={"event_id": "calendar-event-456"},
            ),
            action_event_id=action_event,
        )
        row = self._rows(
            "SELECT expected_json FROM action_verifications WHERE id=?",
            (verification_id,),
        )[0]
        expected = json.loads(str(row["expected_json"]))
        self.assertEqual(expected["event_id"], "calendar-event-456")

        with patch(
            "jarvis_mrb.tools.google.query_calendar_events",
            return_value=SimpleNamespace(
                ok=True,
                message="Found event.",
                data={"events": [{"id": "calendar-event-456"}]},
            ),
        ):
            status, evidence = world_verification._calendar_observation(expected)

        self.assertEqual(status, "verified")
        self.assertIn("calendar-event-456", evidence)

    def test_external_write_is_not_verified_by_tool_success_alone(self) -> None:
        _, decision_id = self._goal_and_decision()
        action_event = self._action_event()
        verification_id = world_verification.register_execution(
            "gmail.send",
            {"recipient": "daniel@example.com", "subject": "Apollo", "body": "Please send the schedules."},
            SimpleNamespace(ok=True, message="Sent email to daniel@example.com."),
            action_event_id=action_event,
            executive_decision_id=decision_id,
        )
        row = self._rows("SELECT status,verifier,expected_json FROM action_verifications WHERE id=?", (verification_id,))[0]
        self.assertEqual(str(row["status"]), "pending")
        self.assertEqual(str(row["verifier"]), "gmail_sent_message")
        expected = json.loads(str(row["expected_json"]))
        self.assertGreater(int(expected.get("not_before_unix") or 0), 0)

        plan = world_executive_loop.plans_for_query("What should I do about Project Apollo?", limit=1)[0]
        self.assertEqual(plan["state"], "awaiting_verification")
        self.assertTrue(any(item.get("kind") == "verification_pending" for item in plan["attention"]))

    def test_independent_success_transitions_pending_to_verified(self) -> None:
        intention_id, decision_id = self._goal_and_decision()
        verification_id = world_verification.register_execution(
            "gmail.send",
            {"recipient": "daniel@example.com", "subject": "Apollo", "body": "Please send the schedules."},
            SimpleNamespace(ok=True, message="Sent email to daniel@example.com."),
            action_event_id=self._action_event(),
            executive_decision_id=decision_id,
        )
        world_verification._observe = lambda verifier, expected: (
            "verified",
            "Sent Mail independently contains the message.",
        )
        outcome = world_verification.check_one(verification_id, force=True)
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual(outcome["status"], "verified")
        self.assertEqual(
            str(self._rows("SELECT status FROM action_verifications WHERE id=?", (verification_id,))[0]["status"]),
            "verified",
        )
        self.assertEqual(
            len(self._rows("SELECT 1 FROM events WHERE event_type='verification.verified'")),
            1,
        )
        world_executive_loop.refresh()
        self.assertEqual(
            len(self._rows(
                "SELECT 1 FROM executive_attention WHERE intention_id=? AND kind='verification_pending' AND status='open'",
                (intention_id,),
            )),
            0,
        )

    def test_failed_outcome_reenters_executive_loop_as_blocker(self) -> None:
        _, decision_id = self._goal_and_decision()
        verification_id = world_verification.register_execution(
            "gmail.send",
            {"recipient": "daniel@example.com", "subject": "Apollo", "body": "Please send the schedules."},
            SimpleNamespace(ok=True, message="Sent email to daniel@example.com."),
            action_event_id=self._action_event(),
            executive_decision_id=decision_id,
        )
        world_verification._observe = lambda verifier, expected: (
            "failed",
            "Provider reports the tracked action did not reach the expected terminal state.",
        )
        outcome = world_verification.check_one(verification_id, force=True)
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual(outcome["status"], "failed")

        plan = world_executive_loop.plans_for_query("What's blocking Project Apollo?", limit=1)[0]
        self.assertEqual(plan["state"], "at_risk")
        self.assertTrue(any(item.get("kind") == "verification_failed" for item in plan["blockers"]))
        self.assertEqual(plan["decision"]["tool"], "")
        self.assertIn("Verified outcome failed", str(plan["decision"]["summary"]))

    def test_timeout_gets_final_observation_before_becoming_timeout(self) -> None:
        _, decision_id = self._goal_and_decision()
        verification_id = world_verification.register_execution(
            "gmail.send",
            {"recipient": "daniel@example.com", "subject": "Apollo", "body": "Please send the schedules."},
            SimpleNamespace(ok=True, message="Sent email to daniel@example.com."),
            action_event_id=self._action_event(),
            executive_decision_id=decision_id,
        )
        expired = (datetime.now().astimezone() - timedelta(seconds=1)).isoformat()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("UPDATE action_verifications SET deadline_at=?,next_check_at=? WHERE id=?", (expired, expired, verification_id))
            conn.commit()
        finally:
            conn.close()
        world_verification._observe = lambda verifier, expected: (
            "pending",
            "No causal read-back match is visible.",
        )
        outcome = world_verification.check_one(verification_id, force=True)
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual(outcome["status"], "timed_out")
        self.assertEqual(
            len(self._rows("SELECT 1 FROM events WHERE event_type='verification.timed_out'")),
            1,
        )

    def test_expired_deadline_still_accepts_final_independent_success(self) -> None:
        _, decision_id = self._goal_and_decision()
        verification_id = world_verification.register_execution(
            "gmail.send",
            {"recipient": "daniel@example.com", "subject": "Apollo", "body": "Please send the schedules."},
            SimpleNamespace(ok=True, message="Sent email to daniel@example.com."),
            action_event_id=self._action_event(),
            executive_decision_id=decision_id,
        )
        expired = (datetime.now().astimezone() - timedelta(seconds=1)).isoformat()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("UPDATE action_verifications SET deadline_at=?,next_check_at=? WHERE id=?", (expired, expired, verification_id))
            conn.commit()
        finally:
            conn.close()
        world_verification._observe = lambda verifier, expected: (
            "verified",
            "Final read-back independently found the expected state.",
        )
        outcome = world_verification.check_one(verification_id, force=True)
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual(outcome["status"], "verified")

    def test_unverifiable_write_never_becomes_verified_from_receipt(self) -> None:
        action_event = self._action_event(tool="custom.run", ok=True)
        verification_id = world_verification.register_execution(
            "custom.run",
            {"name": "example", "arguments": {"secret": "value"}},
            SimpleNamespace(ok=True, message="Custom tool returned HTTP 200."),
            action_event_id=action_event,
        )
        row = self._rows("SELECT status,verifier,arguments_json FROM action_verifications WHERE id=?", (verification_id,))[0]
        self.assertEqual(str(row["status"]), "unverified")
        self.assertEqual(str(row["verifier"]), "no_independent_verifier")
        self.assertNotIn("secret", str(row["arguments_json"]))

    def test_tool_failure_is_immediate_failed_attempt_not_verified_outcome(self) -> None:
        action_event = self._action_event(tool="calendar.create", ok=False)
        verification_id = world_verification.register_execution(
            "calendar.create",
            {"summary": "Apollo signing", "start": "2026-09-08T10:00:00-07:00", "end": "2026-09-08T11:00:00-07:00"},
            SimpleNamespace(ok=False, message="Calendar create failed: provider error"),
            action_event_id=action_event,
        )
        row = self._rows("SELECT status,verifier,last_evidence FROM action_verifications WHERE id=?", (verification_id,))[0]
        self.assertEqual(str(row["status"]), "failed")
        self.assertEqual(str(row["verifier"]), "tool_return")
        self.assertIn("Tool returned failure", str(row["last_evidence"]))

    def test_audited_tool_receipt_persists_agency_step_correlation(self) -> None:
        step_id = "agency-step:receipt-correlation-test"
        with tool_audit.agency_step_context(step_id):
            tool_audit._record(
                "knowledge.search",
                {"query": "Apollo"},
                SimpleNamespace(ok=True, message="Found evidence."),
            )

        row = self._rows(
            """
            SELECT payload_json FROM events
            WHERE event_type='action.tool' AND source_kind='jarvis_tool'
            ORDER BY id DESC LIMIT 1
            """
        )[0]
        payload = json.loads(str(row["payload_json"]))
        self.assertEqual(payload["agency_step_id"], step_id)

    def test_temporary_state_verifier_uses_storage_normalized_key(self) -> None:
        normalized = tool_audit._verification_args(
            "state.temp_set",
            {"key": "Current Focus", "value": "Apollo", "ttl_minutes": 60},
        )
        self.assertEqual(normalized["key"], "current_focus")

    def test_executive_correlation_requires_exact_tool_and_arguments(self) -> None:
        _, decision_id = self._goal_and_decision()
        expected_args = {"query": "Project Apollo indemnity cap", "limit": 5}
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "UPDATE executive_decisions SET proposed_tool=?,proposed_args_json=? WHERE id=?",
                ("knowledge.search", json.dumps(expected_args, sort_keys=True), decision_id),
            )
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(tool_audit._executive_decision_id("knowledge.search", expected_args), decision_id)
        altered = {"query": "Project Apollo indemnity cap", "limit": 8}
        self.assertEqual(tool_audit._executive_decision_id("knowledge.search", altered), "")

    def test_staged_confirmation_keeps_exact_decision_after_supersession(self) -> None:
        _, decision_id = self._goal_and_decision()
        args = {"recipient": "daniel@example.com", "subject": "Apollo", "body": "Please send schedules."}
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "UPDATE executive_decisions SET proposed_tool=?,proposed_args_json=? WHERE id=?",
                ("gmail.send", json.dumps(args, sort_keys=True), decision_id),
            )
            conn.commit()
        finally:
            conn.close()

        tool_audit._stage_executive_decision("gmail.send", args)
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("UPDATE executive_decisions SET status='superseded' WHERE id=?", (decision_id,))
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(tool_audit._consume_staged_decision("gmail.send", args), decision_id)
        self.assertEqual(tool_audit._consume_staged_decision("gmail.send", args), "")


if __name__ == "__main__":
    unittest.main()
