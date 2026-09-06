from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_intent_capture as world_intent_capture
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_relevance as world_relevance


class ConversationalIntentCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_linker.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        world_model.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _rows(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_explicit_trying_statement_becomes_project_linked_persistent_intention(self) -> None:
        events = world_intent_capture.capture(
            "We're trying to get Project Apollo signed by Friday.",
            session_id="test",
        )
        self.assertEqual(len(events), 1)
        world_linker.link_event(events[0])
        world_executive.refresh_intentions()

        goals = self._rows("SELECT id,canonical_name FROM entities WHERE kind='goal'")
        self.assertEqual(len(goals), 1)
        self.assertEqual(str(goals[0]["canonical_name"]), "get Project Apollo signed by Friday")
        projects = self._rows("SELECT id,canonical_name FROM entities WHERE kind='project'")
        self.assertEqual(len(projects), 1)
        self.assertEqual(str(projects[0]["canonical_name"]), "Project Apollo")

        relations = self._rows(
            "SELECT predicate FROM entity_relations WHERE subject_id=? AND object_id=? AND state='current'",
            (str(goals[0]["id"]), str(projects[0]["id"])),
        )
        self.assertTrue(any(str(row["predicate"]) == "advances_project" for row in relations))

        due = self._rows(
            "SELECT value_json FROM beliefs WHERE subject_id=? AND predicate='due_at' AND state='current'",
            (str(goals[0]["id"]),),
        )
        self.assertEqual(len(due), 1)
        active = world_executive.active_intentions()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["title"], "get Project Apollo signed by Friday")
        self.assertIn("Project Apollo", world_relevance.context_for_query("What is happening with Project Apollo?"))

    def test_explicit_goal_language_is_captured(self) -> None:
        declarations = world_intent_capture.extract_declarations(
            "Our goal is to finish the Project Atlas migration before next Friday."
        )
        self.assertEqual(len(declarations), 1)
        self.assertEqual(declarations[0]["kind"], "explicit_goal")
        self.assertIn("Project Atlas", declarations[0]["action"])

    def test_questions_hypotheticals_and_ordinary_wants_are_not_captured(self) -> None:
        samples = (
            "What if we're trying to get Project Apollo signed by Friday?",
            "Are we trying to get Project Apollo signed by Friday?",
            "Could we try to get Project Apollo signed by Friday?",
            "I want pizza for dinner.",
            "I'd like to watch a movie tonight.",
            "I'm trying to fall asleep.",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(world_intent_capture.extract_declarations(sample), [])

    def test_repeating_same_declaration_updates_same_goal_instead_of_creating_duplicate(self) -> None:
        statement = "We're trying to get Project Apollo signed by Friday."
        first = world_intent_capture.capture(statement, session_id="one")
        second = world_intent_capture.capture(statement, session_id="two")
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        count = int(self._rows("SELECT COUNT(*) AS n FROM entities WHERE kind='goal'")[0]["n"])
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
