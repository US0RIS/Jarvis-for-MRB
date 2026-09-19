from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.agent as agent
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_chronos as world_chronos
import jarvis_mrb.world_model as world_model


class WorldChronosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_chronos.DB_PATH = self.db
        world_model.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _project_with_revision(self) -> str:
        project_id = world_model.ensure_entity("project", "Project Chronos")
        draft_event = world_model.record_event(
            "project.observation",
            "Project Chronos status is draft.",
            source_kind="test",
            source_ref="chronos:draft",
            occurred_at="2026-09-01T09:00:00-07:00",
            participants=[(project_id, "subject", 1.0)],
        )
        world_model.assert_belief(
            project_id,
            "status",
            value="draft",
            observed_at="2026-09-01T09:00:00-07:00",
            source_event_id=draft_event,
            evidence="Observed draft state.",
        )
        signed_event = world_model.record_event(
            "project.observation",
            "Project Chronos status is signed.",
            source_kind="test",
            source_ref="chronos:signed",
            occurred_at="2026-09-03T15:00:00-07:00",
            participants=[(project_id, "subject", 1.0)],
        )
        world_model.assert_belief(
            project_id,
            "status",
            value="signed",
            observed_at="2026-09-03T15:00:00-07:00",
            source_event_id=signed_event,
            evidence="Observed signed state.",
        )
        return project_id

    def test_state_at_reconstructs_belief_before_and_after_revision(self) -> None:
        self._project_with_revision()

        before = world_chronos.state_at(
            "Project Chronos",
            "2026-09-02T12:00:00-07:00",
        )
        after = world_chronos.state_at(
            "Project Chronos",
            "2026-09-04T12:00:00-07:00",
        )

        self.assertEqual(
            before["predicates"]["status"]["preferred"]["value"],
            "draft",
        )
        self.assertEqual(
            after["predicates"]["status"]["preferred"]["value"],
            "signed",
        )
        self.assertFalse(before["predicates"]["status"]["uncertain"])
        self.assertFalse(after["predicates"]["status"]["uncertain"])

    def test_trace_uses_occurrence_time_not_ingestion_order(self) -> None:
        project_id = world_model.ensure_entity("project", "Project Reverse Ingest")
        newer = world_model.record_event(
            "project.observation",
            "Newer real-world observation.",
            source_kind="test",
            source_ref="chronos:newer-first",
            occurred_at="2026-09-05T18:00:00-07:00",
            participants=[(project_id, "subject", 1.0)],
        )
        older = world_model.record_event(
            "project.observation",
            "Older observation ingested later.",
            source_kind="test",
            source_ref="chronos:older-late",
            occurred_at="2026-09-04T18:00:00-07:00",
            participants=[(project_id, "subject", 1.0)],
        )
        self.assertGreater(older, newer)

        traced = world_chronos.trace("Project Reverse Ingest")
        self.assertEqual(
            [item["source_ref"] for item in traced["events"][:2]],
            ["chronos:newer-first", "chronos:older-late"],
        )

    def test_changes_preserve_revision_provenance(self) -> None:
        self._project_with_revision()

        result = world_chronos.changes(
            "Project Chronos",
            "2026-09-02T00:00:00-07:00",
            "2026-09-04T23:59:59-07:00",
        )
        status_changes = [
            item for item in result["belief_changes"]
            if item["predicate"] == "status"
        ]
        self.assertEqual(len(status_changes), 1)
        change = status_changes[0]
        self.assertEqual(change["from"], "draft")
        self.assertEqual(change["to"], "signed")
        self.assertGreater(int(change["source_event_id"]), 0)

    def test_agent_surface_exposes_read_only_chronos_queries(self) -> None:
        self._project_with_revision()

        state_reply = agent._execute_unchecked(
            "chronos.state_at",
            {
                "entity": "Project Chronos",
                "at": "2026-09-02T12:00:00-07:00",
            },
        )
        self.assertTrue(state_reply.ok, state_reply.message)
        self.assertIn("status=", state_reply.message)
        self.assertEqual(
            state_reply.data["predicates"]["status"]["preferred"]["value"],
            "draft",
        )

        trace_reply = agent._execute_unchecked(
            "chronos.trace",
            {"entity": "Project Chronos", "limit": 10},
        )
        self.assertTrue(trace_reply.ok, trace_reply.message)
        self.assertGreaterEqual(len(trace_reply.data["events"]), 2)

        changes_reply = agent._execute_unchecked(
            "chronos.changes",
            {
                "entity": "Project Chronos",
                "since": "2026-09-02T00:00:00-07:00",
                "until": "2026-09-04T23:59:59-07:00",
            },
        )
        self.assertTrue(changes_reply.ok, changes_reply.message)
        self.assertIn("status changed", changes_reply.message)

        self.assertEqual(permissions.TOOL_RISK["chronos.trace"], "read")
        self.assertEqual(permissions.TOOL_RISK["chronos.state_at"], "read")
        self.assertEqual(permissions.TOOL_RISK["chronos.changes"], "read")


if __name__ == "__main__":
    unittest.main()
