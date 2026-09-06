from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.world_document_versions as world_document_versions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_executive_loop as world_executive_loop
import jarvis_mrb.world_intent_capture as world_intent_capture
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_term_context as world_term_context
import jarvis_mrb.world_terms as world_terms


class WorldChronologyTests(unittest.TestCase):
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
        world_document_versions.DB_PATH = self.db
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

    def _term_event(self, text: str, occurred_at: str, source_ref: str) -> int:
        event_id = world_model.record_event(
            "conversation.turn",
            text,
            source_kind="conversation",
            source_ref=source_ref,
            occurred_at=occurred_at,
            payload={"user": text},
        )
        world_linker.link_event(event_id)
        result = world_terms.observe_event(event_id)
        for generated in result.get("generated_event_ids") or []:
            world_linker.link_event(int(generated))
        return event_id

    def test_late_ingested_old_term_does_not_become_current(self) -> None:
        goal_events = world_intent_capture.capture(
            "We're trying to get Project Chronos signed this week.",
            session_id="chronology-test",
        )
        self.assertEqual(len(goal_events), 1)
        world_linker.link_event(goal_events[0])

        # Deliberately ingest the real-world newer source first, then replay an older
        # historical source afterward. Ingestion ID must not control current state.
        self._term_event(
            "Project Chronos indemnity cap is 15%.",
            "2026-09-06T12:00:00-07:00",
            "chronos-newer",
        )
        self._term_event(
            "Project Chronos indemnity cap is 10%.",
            "2026-09-05T12:00:00-07:00",
            "chronos-older-replayed-late",
        )

        project = self._rows(
            "SELECT id FROM entities WHERE kind='project' AND normalized_name='project chronos'"
        )[0]
        project_id = str(project["id"])
        latest = world_terms.latest_observations(project_id, {"indemnity_cap"})
        self.assertEqual(len(latest), 1)
        self.assertEqual(str(latest[0]["value"]), "15%")
        self.assertEqual(str(latest[0]["occurred_at"]), "2026-09-06T12:00:00-07:00")

        conflict = self._rows(
            """
            SELECT older.occurred_at AS older_at,newer.occurred_at AS newer_at,
                   older.value_text AS older_value,newer.value_text AS newer_value
            FROM term_conflicts c
            JOIN term_observations older ON older.id=c.older_observation_id
            JOIN term_observations newer ON newer.id=c.newer_observation_id
            WHERE newer.project_id=? AND newer.term_key='indemnity_cap'
            """,
            (project_id,),
        )
        self.assertEqual(len(conflict), 1)
        self.assertEqual(str(conflict[0]["older_value"]), "10%")
        self.assertEqual(str(conflict[0]["newer_value"]), "15%")
        self.assertLess(str(conflict[0]["older_at"]), str(conflict[0]["newer_at"]))

        term_context = world_term_context.context_for_query(
            "What's the indemnity cap on Project Chronos?"
        )
        self.assertIn("15%", term_context)
        self.assertIn("current source discrepancy", term_context)

        world_executive.refresh_intentions()
        world_executive_loop.refresh()
        plan = world_executive_loop.plans_for_query(
            "What's blocking Project Chronos?", limit=1
        )[0]
        conflicts = [item for item in plan["blockers"] if item.get("kind") == "term_conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(str(conflicts[0]["older_value"]), "10%")
        self.assertEqual(str(conflicts[0]["newer_value"]), "15%")

    def _attachment(
        self,
        source_ref: str,
        filename: str,
        text: str,
        occurred_at: str,
    ) -> int:
        event_id = world_model.record_knowledge_source(
            "gmail_attachment",
            source_ref,
            title=filename,
            text=text,
            occurred_at=occurred_at,
            metadata={
                "message_id": source_ref.split(":", 1)[0],
                "thread_id": "thread-chronos",
                "filename": filename,
                "email_subject": "Project Chronos purchase agreement",
            },
        )
        world_linker.link_event(event_id)
        return event_id

    def test_late_ingested_old_document_is_still_predecessor(self) -> None:
        newer_event = self._attachment(
            "m-new:a-new",
            "Project Chronos Purchase Agreement Revised v2.docx",
            "Project Chronos. The indemnity cap shall equal 15% of the Purchase Price. The survival period is 18 months.",
            "2026-09-06T12:00:00-07:00",
        )
        older_event = self._attachment(
            "m-old:a-old",
            "Project Chronos Purchase Agreement Draft v1.docx",
            "Project Chronos. The indemnity cap shall equal 10% of the Purchase Price. The survival period is 18 months.",
            "2026-09-05T12:00:00-07:00",
        )
        self.assertGreater(older_event, newer_event)  # confirms ingestion order is reversed

        result = world_document_versions.refresh()
        self.assertEqual(result["pairs_compared"], 1)
        pair = self._rows(
            "SELECT older_event_id,newer_event_id FROM document_version_pairs"
        )[0]
        self.assertEqual(int(pair["older_event_id"]), older_event)
        self.assertEqual(int(pair["newer_event_id"]), newer_event)

        old_doc = str(self._rows(
            "SELECT entity_id FROM external_ids WHERE namespace='gmail_attachment' AND external_id='m-old:a-old'"
        )[0]["entity_id"])
        new_doc = str(self._rows(
            "SELECT entity_id FROM external_ids WHERE namespace='gmail_attachment' AND external_id='m-new:a-new'"
        )[0]["entity_id"])
        correct = self._rows(
            "SELECT state FROM entity_relations WHERE subject_id=? AND predicate='supersedes' AND object_id=?",
            (new_doc, old_doc),
        )
        self.assertEqual(len(correct), 1)
        self.assertEqual(str(correct[0]["state"]), "current")

    def test_repair_retires_reversed_supersession_but_keeps_evidence(self) -> None:
        newer_event = self._attachment(
            "r-new:a-new",
            "Project Chronos Agreement Revised v2.docx",
            "Project Chronos. The indemnity cap shall equal 15% of Purchase Price.",
            "2026-09-06T12:00:00-07:00",
        )
        older_event = self._attachment(
            "r-old:a-old",
            "Project Chronos Agreement Draft v1.docx",
            "Project Chronos. The indemnity cap shall equal 10% of Purchase Price.",
            "2026-09-05T12:00:00-07:00",
        )
        old_doc = str(self._rows(
            "SELECT entity_id FROM external_ids WHERE namespace='gmail_attachment' AND external_id='r-old:a-old'"
        )[0]["entity_id"])
        new_doc = str(self._rows(
            "SELECT entity_id FROM external_ids WHERE namespace='gmail_attachment' AND external_id='r-new:a-new'"
        )[0]["entity_id"])
        comparison = world_model.record_event(
            "document.version_changed",
            "Legacy reversed comparison",
            source_kind="document_diff",
            source_ref="legacy-reversed",
        )
        now = "2026-09-06T13:00:00-07:00"
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "INSERT INTO document_version_pairs(older_event_id,newer_event_id,family_key,comparison_event_id,compared_at) VALUES(?,?,?,?,?)",
                (newer_event, older_event, "project chronos agreement", comparison, now),
            )
            cursor = conn.execute(
                "INSERT INTO entity_relations(subject_id,predicate,object_id,confidence,state,first_seen_at,last_seen_at,evidence_count) VALUES(?,?,?,?,?,?,?,1)",
                (old_doc, "supersedes", new_doc, 0.9, "current", now, now),
            )
            relation_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO relation_evidence(relation_id,event_id,confidence,explanation) VALUES(?,?,?,?)",
                (relation_id, comparison, 0.9, "legacy reversed lineage"),
            )
            conn.commit()
        finally:
            conn.close()

        repaired = world_document_versions.repair_pair_chronology()
        self.assertEqual(repaired["repaired"], 1)
        self.assertEqual(self._rows("SELECT 1 FROM document_version_pairs"), [])
        relation = self._rows("SELECT state FROM entity_relations WHERE id=?", (relation_id,))[0]
        self.assertEqual(str(relation["state"]), "retired")
        self.assertEqual(
            len(self._rows("SELECT 1 FROM relation_evidence WHERE relation_id=? AND event_id=?", (relation_id, comparison))),
            1,
        )


if __name__ == "__main__":
    unittest.main()
