from __future__ import annotations

import sqlite3
import unittest

from jarvis_mrb.world_executive import _unambiguous_owner_project_link


class ExecutiveOwnerProjectLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                canonical_name TEXT NOT NULL
            );
            CREATE TABLE entity_relations (
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                state TEXT NOT NULL
            );
            """
        )
        self.conn.executemany(
            "INSERT INTO entities(id,kind,canonical_name) VALUES(?,?,?)",
            [
                ("person:maya", "person", "Maya Nguyen"),
                ("project:nimbus", "project", "Project Nimbus"),
                ("project:orion", "project", "Project Orion"),
            ],
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_single_structured_project_association_can_bridge_generic_waiting_item(self) -> None:
        self.conn.execute(
            "INSERT INTO entity_relations(subject_id,predicate,object_id,confidence,state) VALUES(?,?,?,?,?)",
            ("person:maya", "associated_with_project", "project:nimbus", 0.78, "current"),
        )
        matched, confidence = _unambiguous_owner_project_link(
            self.conn,
            "person:maya",
            ["project:nimbus"],
        )
        self.assertTrue(matched)
        self.assertGreaterEqual(confidence, 0.75)

    def test_multiple_current_project_associations_fail_closed(self) -> None:
        self.conn.executemany(
            "INSERT INTO entity_relations(subject_id,predicate,object_id,confidence,state) VALUES(?,?,?,?,?)",
            [
                ("person:maya", "associated_with_project", "project:nimbus", 0.78, "current"),
                ("person:maya", "associated_with_project", "project:orion", 0.82, "current"),
            ],
        )
        matched, confidence = _unambiguous_owner_project_link(
            self.conn,
            "person:maya",
            ["project:nimbus"],
        )
        self.assertFalse(matched)
        self.assertEqual(confidence, 0.0)

    def test_retired_or_weak_associations_do_not_support_bridge(self) -> None:
        self.conn.executemany(
            "INSERT INTO entity_relations(subject_id,predicate,object_id,confidence,state) VALUES(?,?,?,?,?)",
            [
                ("person:maya", "associated_with_project", "project:nimbus", 0.95, "retired"),
                ("person:maya", "associated_with_project", "project:orion", 0.70, "current"),
            ],
        )
        matched, confidence = _unambiguous_owner_project_link(
            self.conn,
            "person:maya",
            ["project:nimbus"],
        )
        self.assertFalse(matched)
        self.assertEqual(confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
