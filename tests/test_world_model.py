from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_frontend_ingest as world_frontend_ingest
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_occurrence as world_occurrence
import jarvis_mrb.world_snapshot_reconcile as world_snapshot_reconcile


class WorldModelTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"

        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_linker.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        world_snapshot_reconcile.DB_PATH = self.db
        world_model.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _query(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_first_explicit_project_mention_creates_project_and_evidence_link(self) -> None:
        person_id = world_model.ensure_entity(
            "person",
            "Daniel Reed",
            external_namespace="email_address",
            external_id="daniel@example.com",
            aliases=["daniel@example.com"],
            confidence=1.0,
        )
        event_id = world_model.record_knowledge_source(
            "gmail",
            "message-1",
            title="Project Apollo diligence",
            text="Daniel Reed sent the revised Project Apollo diligence memorandum.",
            participants=[(person_id, "sender", 1.0)],
        )

        result = world_linker.link_event(event_id)
        self.assertEqual(result["projects_created"], 1)
        project_rows = self._query(
            "SELECT id FROM entities WHERE kind='project' AND normalized_name='project apollo'"
        )
        self.assertEqual(len(project_rows), 1)
        project_id = str(project_rows[0]["id"])

        relations = world_linker.related_entities(person_id, limit=20)
        matching = [
            item for item in relations
            if item["direction"] == "out"
            and item["predicate"] == "associated_with_project"
            and item["entity_id"] == project_id
        ]
        self.assertEqual(len(matching), 1)
        self.assertGreaterEqual(matching[0]["evidence_count"], 1)
        evidence = self._query(
            "SELECT re.event_id FROM relation_evidence re JOIN entity_relations r ON r.id=re.relation_id WHERE r.subject_id=? AND r.predicate='associated_with_project' AND r.object_id=?",
            (person_id, project_id),
        )
        self.assertEqual([int(row["event_id"]) for row in evidence], [event_id])

    def test_explicit_goal_becomes_intention_and_deleted_goal_is_retired(self) -> None:
        first = {
            "goals": [
                {
                    "id": "goal-1",
                    "title": "Complete Project Apollo signing",
                    "next_action": "Review the final execution version",
                    "note": "Explicit test goal",
                    "created_at": "2026-09-06T12:00:00-07:00",
                    "due_at": "2026-09-11T17:00:00-07:00",
                    "completed_at": None,
                }
            ],
            "waiting": [],
            "people": [],
            "inventory": [],
            "reminders": [],
            "encounters": [],
            "events": [],
            "receipts": [],
            "mode": "Work",
        }
        world_frontend_ingest.ingest_frontend_snapshot(first)
        active = world_executive.active_intentions()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["title"], "Complete Project Apollo signing")
        self.assertEqual(active[0]["next_action"], "Review the final execution version")

        second = dict(first)
        second["goals"] = []
        world_frontend_ingest.ingest_frontend_snapshot(second)

        self.assertEqual(world_executive.active_intentions(), [])
        rows = self._query("SELECT status FROM intentions")
        self.assertEqual([str(row["status"]) for row in rows], ["retired"])
        belief_rows = self._query(
            "SELECT state,value_json FROM beliefs WHERE predicate='status' ORDER BY id"
        )
        self.assertTrue(any(row["state"] == "current" and json.loads(row["value_json"]) == "retired" for row in belief_rows))
        self.assertGreaterEqual(len(world_model.timeline(event_type="goal.removed")), 1)

    def test_deleted_waiting_item_stops_being_a_pending_obligation(self) -> None:
        first = {
            "goals": [],
            "waiting": [
                {
                    "id": "waiting-1",
                    "person": "Daniel Reed",
                    "item": "Send the revised Project Apollo disclosure schedules",
                    "created_at": "2026-09-06T12:00:00-07:00",
                    "due_at": "2026-09-07T09:00:00-07:00",
                    "resolved_at": None,
                }
            ],
            "people": [],
            "inventory": [],
            "reminders": [],
            "encounters": [],
            "events": [],
            "receipts": [],
        }
        world_frontend_ingest.ingest_frontend_snapshot(first)
        self.assertEqual(world_model.status()["pending_commitments"], 1)

        second = dict(first)
        second["waiting"] = []
        world_frontend_ingest.ingest_frontend_snapshot(second)
        self.assertEqual(world_model.status()["pending_commitments"], 0)
        rows = self._query("SELECT status FROM commitments WHERE id='waiting:waiting-1'")
        self.assertEqual(str(rows[0]["status"]), "retired")
        self.assertGreaterEqual(len(world_model.timeline(event_type="waiting_removed")), 1)

    def test_repeated_live_occurrences_remain_distinct(self) -> None:
        first_turn = world_occurrence.record_conversation_occurrence(
            "test-session", "What time is it?", "It is noon.", occurred_at="2026-09-06T12:00:00-07:00"
        )
        second_turn = world_occurrence.record_conversation_occurrence(
            "test-session", "What time is it?", "It is noon.", occurred_at="2026-09-06T12:00:01-07:00"
        )
        self.assertNotEqual(first_turn, second_turn)

        first_sighting = world_occurrence.record_visual_occurrence(
            "Keys are on the desk.",
            ["keys"],
            location_context="office",
            occurred_at="2026-09-06T12:01:00-07:00",
            occurrence_ref="sighting-1",
        )
        second_sighting = world_occurrence.record_visual_occurrence(
            "Keys are on the desk.",
            ["keys"],
            location_context="office",
            occurred_at="2026-09-06T12:02:00-07:00",
            occurrence_ref="sighting-2",
        )
        self.assertNotEqual(first_sighting, second_sighting)
        self.assertEqual(
            int(self._query("SELECT COUNT(*) AS n FROM events WHERE event_type='conversation.turn'")[0]["n"]),
            2,
        )
        self.assertEqual(
            int(self._query("SELECT COUNT(*) AS n FROM events WHERE event_type='perception.visual'")[0]["n"]),
            2,
        )

    def test_lower_confidence_contradiction_is_disputed_not_authoritative(self) -> None:
        object_id = world_model.ensure_entity("object", "Garage side door")
        first_event = world_model.record_event(
            "test.observation",
            "Door observed closed",
            source_kind="test",
            source_ref="closed",
        )
        world_model.assert_belief(
            object_id,
            "door_state",
            value="closed",
            confidence=0.95,
            source_event_id=first_event,
        )
        second_event = world_model.record_event(
            "test.observation",
            "Weak classifier thought door might be open",
            source_kind="test",
            source_ref="open",
            confidence=0.4,
        )
        world_model.assert_belief(
            object_id,
            "door_state",
            value="open",
            confidence=0.4,
            source_event_id=second_event,
        )
        rows = self._query(
            "SELECT state,value_json,confidence FROM beliefs WHERE subject_id=? AND predicate='door_state' ORDER BY id",
            (object_id,),
        )
        states = [(str(row["state"]), json.loads(row["value_json"]), float(row["confidence"])) for row in rows]
        self.assertIn(("current", "closed", 0.95), states)
        self.assertIn(("disputed", "open", 0.4), states)

    def test_tool_receipt_redacts_sensitive_arguments(self) -> None:
        world_model.record_tool_execution(
            "sandbox.command",
            {"command": "print-a-secret", "timeout_seconds": 8},
            ok=True,
            message="Security-class result body omitted by caller.",
        )
        rows = self._query(
            "SELECT payload_json FROM events WHERE event_type='action.tool' ORDER BY id DESC LIMIT 1"
        )
        payload = json.loads(str(rows[0]["payload_json"]))
        self.assertEqual(payload["arguments"]["command"], "<redacted from world-model action log>")
        self.assertEqual(payload["arguments"]["timeout_seconds"], 8)


if __name__ == "__main__":
    unittest.main()
