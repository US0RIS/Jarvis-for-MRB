from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.runtime_health as runtime_health
import jarvis_mrb.world_document_versions as world_document_versions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_executive_loop as world_executive_loop
import jarvis_mrb.world_frontend_ingest as world_frontend_ingest
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_migrations as world_migrations
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_snapshot_reconcile as world_snapshot_reconcile
import jarvis_mrb.world_terms as world_terms
import jarvis_mrb.world_verification as world_verification


class WorldReliabilityTests(unittest.TestCase):
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
        world_verification.DB_PATH = self.db
        runtime_health.DB_PATH = self.db
        world_migrations.DB_PATH = self.db
        world_snapshot_reconcile.DB_PATH = self.db
        world_document_versions.DB_PATH = self.db
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

    def _full_snapshot(self) -> dict[str, object]:
        return {
            "goals": [
                {
                    "id": "goal-1",
                    "title": "Complete Project Apollo signing",
                    "next_action": "Review execution version",
                    "created_at": "2026-09-06T12:00:00-07:00",
                }
            ],
            "waiting": [
                {
                    "id": "waiting-1",
                    "person": "Daniel Reed",
                    "item": "Send revised Project Apollo schedules",
                    "created_at": "2026-09-06T12:00:00-07:00",
                    "resolved_at": None,
                }
            ],
            "people": [
                {"id": "known-1", "name": "Daniel Reed", "note": "private enrollment note"}
            ],
            "inventory": [],
            "reminders": [],
            "encounters": [],
            "events": [],
            "receipts": [],
        }

    def test_partial_snapshot_cannot_mass_retire_authoritative_collections(self) -> None:
        world_frontend_ingest.ingest_frontend_snapshot(self._full_snapshot())
        before_goal = self._rows(
            "SELECT b.value_json FROM external_ids x JOIN beliefs b ON b.subject_id=x.entity_id "
            "WHERE x.namespace='iphone_goal' AND x.external_id='goal-1' AND b.predicate='status' AND b.state='current'"
        )
        self.assertTrue(before_goal)
        self.assertEqual(json.loads(str(before_goal[-1]["value_json"])), "active")
        self.assertEqual(
            str(self._rows("SELECT status FROM commitments WHERE id='waiting:waiting-1'")[0]["status"]),
            "pending",
        )
        self.assertEqual(
            len(self._rows("SELECT 1 FROM external_ids WHERE namespace='iphone_known_person' AND external_id='known-1'")),
            1,
        )

        # Missing keys and malformed values mean "partial/unknown", not an authoritative empty list.
        result = world_snapshot_reconcile.reconcile_authoritative_snapshot(
            {"mode": "Work", "goals": None, "waiting": "not-a-list", "people": {"id": "bad"}}
        )
        self.assertEqual(result, {"retired_goals": 0, "retired_waiting": 0, "revoked_known_people": 0})
        goal = self._rows(
            "SELECT b.value_json FROM external_ids x JOIN beliefs b ON b.subject_id=x.entity_id "
            "WHERE x.namespace='iphone_goal' AND x.external_id='goal-1' AND b.predicate='status' AND b.state='current'"
        )
        self.assertEqual(json.loads(str(goal[-1]["value_json"])), "active")
        self.assertEqual(
            str(self._rows("SELECT status FROM commitments WHERE id='waiting:waiting-1'")[0]["status"]),
            "pending",
        )
        self.assertEqual(
            len(self._rows("SELECT 1 FROM external_ids WHERE namespace='iphone_known_person' AND external_id='known-1'")),
            1,
        )

    def test_generic_negative_person_project_mention_does_not_create_association(self) -> None:
        daniel = world_model.ensure_entity(
            "person",
            "Daniel Reed",
            external_namespace="email_address",
            external_id="daniel@example.com",
        )
        event_id = world_model.record_event(
            "conversation.turn",
            "Daniel Reed is not on Project Apollo.",
            source_kind="conversation",
            source_ref="negative-association",
            payload={"user": "Daniel Reed is not on Project Apollo."},
            participants=[(world_model.SELF_ID, "user", 1.0)],
        )
        world_linker.link_event(event_id)
        project = self._rows("SELECT id FROM entities WHERE kind='project' AND normalized_name='project apollo'")
        self.assertEqual(len(project), 1)
        relation = self._rows(
            "SELECT 1 FROM entity_relations WHERE subject_id=? AND predicate='associated_with_project' AND object_id=? AND state='current'",
            (daniel, str(project[0]["id"])),
        )
        self.assertEqual(relation, [])

    def test_structured_calendar_attendee_still_creates_project_association(self) -> None:
        daniel = world_model.ensure_entity(
            "person",
            "Daniel Reed",
            external_namespace="email_address",
            external_id="daniel@example.com",
        )
        calendar = world_model.ensure_entity(
            "calendar",
            "Project Apollo signing call",
            external_namespace="calendar",
            external_id="apollo-call",
        )
        event_id = world_model.record_event(
            "calendar.context_enriched",
            "Project Apollo signing call",
            source_kind="calendar_enriched",
            source_ref="apollo-call",
            payload={"title": "Project Apollo signing call"},
            participants=[
                (calendar, "meeting", 1.0),
                (daniel, "attendee", 1.0),
            ],
        )
        world_linker.link_event(event_id)
        project = self._rows("SELECT id FROM entities WHERE kind='project' AND normalized_name='project apollo'")[0]
        relation = self._rows(
            "SELECT evidence_count FROM entity_relations WHERE subject_id=? AND predicate='associated_with_project' AND object_id=? AND state='current'",
            (daniel, str(project["id"])),
        )
        self.assertEqual(len(relation), 1)
        self.assertGreaterEqual(int(relation[0]["evidence_count"]), 1)

    def test_legacy_weak_person_project_relation_is_retired_not_erased(self) -> None:
        daniel = world_model.ensure_entity("person", "Daniel Reed")
        apollo = world_model.ensure_entity("project", "Project Apollo")
        event_id = world_model.record_event(
            "conversation.turn",
            "Daniel Reed is not on Project Apollo.",
            source_kind="conversation",
            source_ref="legacy-negative",
            participants=[(daniel, "mentioned", 0.72), (apollo, "mentioned", 0.92)],
        )
        world_linker.status()
        now = "2026-09-06T12:00:00-07:00"
        conn = sqlite3.connect(self.db)
        try:
            cursor = conn.execute(
                "INSERT INTO entity_relations(subject_id,predicate,object_id,confidence,state,first_seen_at,last_seen_at,evidence_count) VALUES(?,?,?,?,?,?,?,1)",
                (daniel, "associated_with_project", apollo, 0.72, "current", now, now),
            )
            relation_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO relation_evidence(relation_id,event_id,confidence,explanation) VALUES(?,?,?,?)",
                (relation_id, event_id, 0.72, "legacy generic co-occurrence"),
            )
            conn.commit()
        finally:
            conn.close()

        repaired = world_linker.repair_person_project_relations()
        self.assertEqual(repaired["retired"], 1)
        row = self._rows("SELECT state FROM entity_relations WHERE id=?", (relation_id,))[0]
        self.assertEqual(str(row["state"]), "retired")
        self.assertEqual(
            len(self._rows("SELECT 1 FROM relation_evidence WHERE relation_id=? AND event_id=?", (relation_id, event_id))),
            1,
        )

    def test_migration_is_versioned_idempotent_and_backed_up(self) -> None:
        world_model.record_event(
            "test.seed",
            "Existing world data before migration",
            source_kind="test",
            source_ref="seed",
        )
        self.assertEqual(world_migrations.current_version(), 0)
        result = world_migrations.run_migrations(backup=True)
        self.assertEqual(result["after"], world_migrations.TARGET_SCHEMA_VERSION)
        self.assertEqual(result["applied"], [1, 2, 3, 4])
        self.assertTrue(result["backup"])
        self.assertTrue(Path(str(result["backup"])).exists())

        rerun = world_migrations.run_migrations(backup=True)
        self.assertEqual(rerun["before"], world_migrations.TARGET_SCHEMA_VERSION)
        self.assertEqual(rerun["applied"], [])
        self.assertEqual(rerun["backup"], "")
        history = self._rows("SELECT version FROM world_schema_history ORDER BY version")
        self.assertEqual([int(row["version"]) for row in history], [1, 2, 3, 4])
        tables = {str(row["name"]) for row in self._rows("SELECT name FROM sqlite_master WHERE type='table'")}
        for required in (
            "entity_relations", "intentions", "term_observations", "document_version_pairs",
            "executive_decisions", "action_verifications", "runtime_subsystem_health",
        ):
            self.assertIn(required, tables)

    def test_newer_unknown_schema_is_refused(self) -> None:
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS world_schema_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            conn.execute("INSERT OR REPLACE INTO world_schema_meta(key,value) VALUES('schema_version','99')")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(RuntimeError):
            world_migrations.run_migrations(backup=False)

    def test_runtime_health_tracks_failure_and_recovery(self) -> None:
        runtime_health.record_failure("calendar", RuntimeError("temporary provider failure"))
        runtime_health.record_failure("calendar", RuntimeError("temporary provider failure"))
        first = {item["subsystem"]: item for item in runtime_health.snapshot()}["calendar"]
        self.assertEqual(first["status"], "degraded")
        self.assertEqual(first["consecutive_failures"], 2)
        self.assertIn("temporary provider failure", str(first["last_error"]))

        runtime_health.record_success("calendar")
        recovered = {item["subsystem"]: item for item in runtime_health.snapshot()}["calendar"]
        self.assertEqual(recovered["status"], "ok")
        self.assertEqual(recovered["consecutive_failures"], 0)
        self.assertEqual(recovered["last_error"], "")


if __name__ == "__main__":
    unittest.main()
