from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_situation as world_situation
import jarvis_mrb.world_term_context as world_term_context
import jarvis_mrb.world_terms as world_terms


class WorldTermLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_linker.DB_PATH = self.db
        world_terms.DB_PATH = self.db
        world_term_context.DB_PATH = self.db
        world_situation.DB_PATH = self.db
        world_model.status()
        world_linker.status()
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

    def _source_event(self, event_type: str, source_kind: str, source_ref: str, text: str, occurred_at: str) -> int:
        event_id = world_model.record_event(
            event_type,
            text,
            source_kind=source_kind,
            source_ref=source_ref,
            occurred_at=occurred_at,
            payload={"text": text},
            evidence="test source",
        )
        world_linker.link_event(event_id)
        return event_id

    def test_conversation_then_attachment_different_indemnity_cap_creates_provenance_conflict(self) -> None:
        yesterday = (datetime.now().astimezone() - timedelta(days=1)).isoformat()
        now = datetime.now().astimezone().isoformat()
        conversation = self._source_event(
            "conversation.turn",
            "conversation",
            "test-session",
            "We discussed Project Apollo and agreed the indemnity cap is 10% of the purchase price.",
            yesterday,
        )
        first = world_terms.observe_event(conversation)
        self.assertEqual(first["observations"], 1)
        self.assertEqual(first["conflicts"], 0)

        attachment = self._source_event(
            "knowledge.gmail_attachment",
            "gmail_attachment",
            "message-2:attachment-1",
            "Project Apollo revised draft. The indemnity cap shall equal 15% of the Purchase Price.",
            now,
        )
        second = world_terms.observe_event(attachment)
        self.assertEqual(second["observations"], 1)
        self.assertEqual(second["conflicts"], 1)

        conflicts = self._rows("SELECT id,summary,payload_json FROM events WHERE event_type='term.changed_or_conflicted'")
        self.assertEqual(len(conflicts), 1)
        summary = str(conflicts[0]["summary"])
        self.assertIn("Project Apollo", summary)
        self.assertIn("indemnity cap", summary)
        self.assertIn("10%", summary)
        self.assertIn("15%", summary)
        self.assertIn("conversation", summary)
        self.assertIn("gmail_attachment", summary)

    def test_same_term_value_across_sources_does_not_create_conflict(self) -> None:
        first_event = self._source_event(
            "conversation.turn",
            "conversation",
            "s1",
            "Project Atlas indemnity cap is 12.5%.",
            "2026-09-05T12:00:00-07:00",
        )
        second_event = self._source_event(
            "knowledge.gmail_attachment",
            "gmail_attachment",
            "m1:a1",
            "Project Atlas agreement states the indemnity cap shall be 12.5%.",
            "2026-09-06T12:00:00-07:00",
        )
        world_terms.observe_event(first_event)
        world_terms.observe_event(second_event)
        self.assertEqual(len(self._rows("SELECT 1 FROM term_conflicts")), 0)
        self.assertEqual(len(self._rows("SELECT 1 FROM term_observations")), 2)

    def test_number_without_named_supported_term_is_not_promoted(self) -> None:
        event_id = self._source_event(
            "conversation.turn",
            "conversation",
            "s2",
            "Project Atlas has 15 people on the call and 3 open workstreams.",
            "2026-09-06T12:00:00-07:00",
        )
        result = world_terms.observe_event(event_id)
        self.assertEqual(result["observations"], 0)
        self.assertEqual(len(self._rows("SELECT 1 FROM term_observations")), 0)

    def test_term_without_project_is_not_promoted_into_global_fact(self) -> None:
        event_id = world_model.record_event(
            "conversation.turn",
            "The indemnity cap is 20%.",
            source_kind="conversation",
            source_ref="s3",
            payload={"text": "The indemnity cap is 20%."},
        )
        result = world_terms.observe_event(event_id)
        self.assertEqual(result["observations"], 0)

    def test_direct_term_query_resolves_project_even_when_generic_search_is_crowded(self) -> None:
        now = datetime.now().astimezone()
        old_event = self._source_event(
            "conversation.turn",
            "conversation",
            "crowded-old",
            "Project Apollo indemnity cap is 10%.",
            (now - timedelta(hours=2)).isoformat(),
        )
        world_terms.observe_event(old_event)
        new_event = self._source_event(
            "knowledge.gmail_attachment",
            "gmail_attachment",
            "crowded-new",
            "Project Apollo revised draft says the indemnity cap is 15%.",
            (now - timedelta(hours=1)).isoformat(),
        )
        world_terms.observe_event(new_event)

        # Create enough high-scoring events to crowd a low-scoring project entity out
        # of the generic world_search top-N window. Direct term lookup must still bind
        # the explicitly named project before consulting that ranked fallback.
        for index in range(30):
            world_model.record_event(
                "conversation.turn",
                f"Distractor {index}: Project Apollo indemnity cap discussion placeholder.",
                source_kind="conversation",
                source_ref=f"crowded-distractor-{index}",
                occurred_at=(now + timedelta(seconds=index)).isoformat(),
                payload={"text": "Project Apollo indemnity cap discussion placeholder"},
            )

        generic_projects = [
            item for item in world_model.search("What's the indemnity cap on Project Apollo?", limit=12)
            if item.get("type") == "entity" and item.get("kind") == "project"
        ]
        self.assertEqual(generic_projects, [])

        context = world_term_context.context_for_query("What's the indemnity cap on Project Apollo?")
        self.assertIn("Project Apollo", context)
        self.assertIn("15%", context)
        self.assertIn("current source discrepancy", context)
        self.assertIn("10%", context)

    def test_meeting_situation_surfaces_project_term_conflict(self) -> None:
        now = datetime.now().astimezone()
        old_event = self._source_event(
            "conversation.turn",
            "conversation",
            "s4",
            "Project Apollo indemnity cap is 10%.",
            (now - timedelta(days=1)).isoformat(),
        )
        world_terms.observe_event(old_event)
        new_event = self._source_event(
            "knowledge.gmail_attachment",
            "gmail_attachment",
            "m2:a2",
            "Project Apollo revised draft says the indemnity cap is 15%.",
            now.isoformat(),
        )
        generated = world_terms.observe_event(new_event)["generated_event_ids"]
        for event_id in generated:
            world_linker.link_event(event_id)

        project_id = str(self._rows("SELECT id FROM entities WHERE kind='project' AND normalized_name='project apollo'")[0]["id"])
        person_id = world_model.ensure_entity(
            "person",
            "Daniel Reed",
            external_namespace="email_address",
            external_id="daniel@example.com",
        )
        meeting_id = world_model.ensure_entity(
            "calendar",
            "Project Apollo signing call",
            external_namespace="calendar",
            external_id="meeting-apollo",
        )
        meeting_event = world_model.record_event(
            "calendar.context_enriched",
            "Calendar context: Project Apollo signing call",
            source_kind="calendar_enriched",
            source_ref="meeting-apollo",
            occurred_at=(now + timedelta(hours=1)).isoformat(),
            payload={
                "calendar_event_id": "meeting-apollo",
                "title": "Project Apollo signing call",
                "start": (now + timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=2)).isoformat(),
                "status": "confirmed",
                "description": "Project Apollo signing readiness.",
            },
            participants=[
                (meeting_id, "meeting", 1.0),
                (world_model.SELF_ID, "calendar_owner", 1.0),
                (person_id, "attendee", 1.0),
                (project_id, "mentioned", 0.95),
            ],
        )
        world_linker.link_event(meeting_event)

        context = world_situation.context_for_query("Anything I need to know before I go in?")
        self.assertIn("term changed or conflicts across sources", context)
        self.assertIn("10%", context)
        self.assertIn("15%", context)


if __name__ == "__main__":
    unittest.main()
