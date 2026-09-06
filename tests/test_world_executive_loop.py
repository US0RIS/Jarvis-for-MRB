from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_executive_loop as world_executive_loop
import jarvis_mrb.world_intent_capture as world_intent_capture
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_term_context as world_term_context
import jarvis_mrb.world_terms as world_terms


class WorldExecutiveLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_linker.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        world_executive_loop.DB_PATH = self.db
        world_terms.DB_PATH = self.db
        world_term_context.DB_PATH = self.db
        world_model.status()
        world_linker.status()
        world_executive.status()
        world_terms.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _rows(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _create_apollo_goal(self) -> str:
        event_ids = world_intent_capture.capture(
            "We're trying to get Project Apollo signed by Friday.",
            session_id="executive-test",
        )
        self.assertEqual(len(event_ids), 1)
        world_linker.link_event(event_ids[0])
        world_executive.refresh_intentions()
        row = self._rows("SELECT id FROM intentions WHERE status='active' LIMIT 1")[0]
        return str(row["id"])

    def _source_event(self, event_type: str, source_kind: str, source_ref: str, text: str, occurred_at: str) -> int:
        event_id = world_model.record_event(
            event_type,
            text,
            source_kind=source_kind,
            source_ref=source_ref,
            occurred_at=occurred_at,
            payload={"text": text},
            evidence="executive loop test source",
        )
        world_linker.link_event(event_id)
        return event_id

    def test_loop_persists_blockers_dependencies_and_current_decision(self) -> None:
        intention_id = self._create_apollo_goal()
        now = datetime.now().astimezone()

        world_model.ensure_entity(
            "person",
            "Daniel Reed",
            external_namespace="email_address",
            external_id="daniel@example.com",
        )
        world_model.upsert_commitment(
            "apollo-schedules",
            owner_name="Daniel Reed",
            action="Send Project Apollo revised schedules",
            due_at=(now - timedelta(days=1)).isoformat(),
            status="pending",
        )
        world_executive.refresh_intentions()

        older = self._source_event(
            "conversation.turn",
            "conversation",
            "apollo-conversation",
            "Project Apollo indemnity cap is 10%.",
            (now - timedelta(days=1)).isoformat(),
        )
        world_terms.observe_event(older)
        newer = self._source_event(
            "knowledge.gmail_attachment",
            "gmail_attachment",
            "apollo-draft",
            "Project Apollo revised agreement states the indemnity cap is 15%.",
            now.isoformat(),
        )
        term_result = world_terms.observe_event(newer)
        for event_id in term_result.get("generated_event_ids") or []:
            world_linker.link_event(int(event_id))

        result = world_executive_loop.refresh()
        self.assertEqual(result["active_intentions"], 1)
        self.assertGreaterEqual(result["attention_items"], 2)
        self.assertEqual(result["current_decisions"], 1)

        attention = self._rows(
            "SELECT kind,status FROM executive_attention WHERE intention_id=? ORDER BY score DESC",
            (intention_id,),
        )
        kinds = {str(row["kind"]) for row in attention if str(row["status"]) == "open"}
        self.assertIn("term_conflict", kinds)
        self.assertIn("overdue_commitment", kinds)

        decisions = self._rows(
            "SELECT decision_type,proposed_tool,risk,requires_confirmation,status FROM executive_decisions WHERE intention_id=? AND status='current'",
            (intention_id,),
        )
        self.assertEqual(len(decisions), 1)
        self.assertEqual(str(decisions[0]["decision_type"]), "term_conflict")
        self.assertEqual(str(decisions[0]["proposed_tool"]), "knowledge.search")
        self.assertEqual(str(decisions[0]["risk"]), "read")
        self.assertEqual(int(decisions[0]["requires_confirmation"]), 0)

        context = world_executive_loop.context_for_query("What should I do about Project Apollo?")
        self.assertIn("EXECUTIVE LOOP", context)
        self.assertIn("BLOCKERS", context)
        self.assertIn("indemnity cap", context.lower())
        self.assertIn("Daniel Reed", context)
        self.assertIn("RECOMMENDED NOW", context)
        self.assertIn("knowledge.search", context)
        self.assertIn("confirmation_required=False", context)

        projected = world_executive_loop.next_decision("What should I do about Project Apollo?")
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertEqual(projected["tool"], "knowledge.search")
        self.assertEqual(projected["risk"], "read")
        self.assertFalse(projected["requires_confirmation"])
        self.assertEqual(projected["state"], "at_risk")
        self.assertIn("Project Apollo", str(projected["objective"]))

    def test_overdue_dependency_prefers_safe_read_before_followup(self) -> None:
        intention_id = self._create_apollo_goal()
        now = datetime.now().astimezone()
        world_model.ensure_entity(
            "person",
            "Daniel Reed",
            external_namespace="email_address",
            external_id="daniel@example.com",
        )
        world_model.upsert_commitment(
            "apollo-schedules",
            owner_name="Daniel Reed",
            action="Send Project Apollo revised schedules",
            due_at=(now - timedelta(hours=3)).isoformat(),
            status="pending",
        )
        world_executive.refresh_intentions()
        world_executive_loop.refresh()

        decision = self._rows(
            "SELECT proposed_tool,proposed_args_json,risk,requires_confirmation FROM executive_decisions WHERE intention_id=? AND status='current'",
            (intention_id,),
        )[0]
        self.assertEqual(str(decision["proposed_tool"]), "gmail.query")
        self.assertIn("daniel@example.com", str(decision["proposed_args_json"]))
        self.assertEqual(str(decision["risk"]), "read")
        self.assertEqual(int(decision["requires_confirmation"]), 0)

        projected = world_executive_loop.next_decision("What's blocking Project Apollo?")
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertEqual(projected["tool"], "gmail.query")
        self.assertIn("daniel@example.com", str(projected["arguments"]))

    def test_resolved_commitment_stales_dependency_attention(self) -> None:
        intention_id = self._create_apollo_goal()
        now = datetime.now().astimezone()
        world_model.upsert_commitment(
            "apollo-schedules",
            owner_name="Daniel Reed",
            action="Send Project Apollo revised schedules",
            due_at=(now - timedelta(days=1)).isoformat(),
            status="pending",
        )
        world_executive.refresh_intentions()
        world_executive_loop.refresh()
        self.assertEqual(
            len(self._rows("SELECT 1 FROM executive_attention WHERE intention_id=? AND kind='overdue_commitment' AND status='open'", (intention_id,))),
            1,
        )

        world_model.upsert_commitment(
            "apollo-schedules",
            owner_name="Daniel Reed",
            action="Send Project Apollo revised schedules",
            due_at=(now - timedelta(days=1)).isoformat(),
            status="resolved",
        )
        world_executive.refresh_intentions()
        world_executive_loop.refresh()
        self.assertEqual(
            len(self._rows("SELECT 1 FROM executive_attention WHERE intention_id=? AND kind='overdue_commitment' AND status='open'", (intention_id,))),
            0,
        )

    def test_direct_term_question_uses_structured_ledger(self) -> None:
        self._create_apollo_goal()
        now = datetime.now().astimezone()
        event_id = self._source_event(
            "conversation.turn",
            "conversation",
            "term-query",
            "Project Apollo indemnity cap is 12.5%.",
            now.isoformat(),
        )
        world_terms.observe_event(event_id)

        context = world_term_context.context_for_query("What's the indemnity cap on Project Apollo?")
        self.assertIn("PROJECT TERM LEDGER", context)
        self.assertIn("12.5%", context)
        self.assertIn("conversation", context)


if __name__ == "__main__":
    unittest.main()
