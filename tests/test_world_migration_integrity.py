from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.runtime_health as runtime_health
import jarvis_mrb.world_document_versions as world_document_versions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_executive_loop as world_executive_loop
import jarvis_mrb.world_frontend_ingest as world_frontend_ingest
import jarvis_mrb.world_gmail_attachments as world_gmail_attachments
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_migrations as world_migrations
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_snapshot_reconcile as world_snapshot_reconcile
import jarvis_mrb.world_terms as world_terms
import jarvis_mrb.world_verification as world_verification


class WorldMigrationIntegrityTests(unittest.TestCase):
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
        world_gmail_attachments.DB_PATH = self.db
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

    def test_declared_current_schema_with_missing_table_is_rejected(self) -> None:
        world_migrations.run_migrations(backup=False)
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("DROP TABLE verification_observations")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(RuntimeError):
            world_migrations.run_migrations(backup=False)

    def test_declared_current_schema_with_missing_history_is_not_ready(self) -> None:
        world_migrations.run_migrations(backup=False)
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("DELETE FROM world_schema_history WHERE version=3")
            conn.commit()
        finally:
            conn.close()
        self.assertFalse(bool(world_migrations.status()["ready"]))
        with self.assertRaises(RuntimeError):
            world_migrations.run_migrations(backup=False)

    def test_malformed_nonempty_authoritative_list_is_treated_as_partial(self) -> None:
        world_frontend_ingest.ingest_frontend_snapshot(
            {
                "goals": [{"id": "goal-safe", "title": "Keep this goal"}],
                "waiting": [{"id": "wait-safe", "person": "Daniel", "item": "Send schedules"}],
                "people": [{"id": "person-safe", "name": "Daniel"}],
                "inventory": [], "reminders": [], "encounters": [], "events": [], "receipts": [],
            }
        )
        result = world_snapshot_reconcile.reconcile_authoritative_snapshot(
            {
                "goals": [{"title": "missing id"}],
                "waiting": [None],
                "people": [{"id": ""}],
            }
        )
        self.assertEqual(result, {"retired_goals": 0, "retired_waiting": 0, "revoked_known_people": 0})
        self.assertEqual(
            len(self._rows("SELECT 1 FROM external_ids WHERE namespace='iphone_goal' AND external_id='goal-safe'")),
            1,
        )
        self.assertEqual(
            str(self._rows("SELECT status FROM commitments WHERE id='waiting:wait-safe'")[0]["status"]),
            "pending",
        )
        self.assertEqual(
            len(self._rows("SELECT 1 FROM external_ids WHERE namespace='iphone_known_person' AND external_id='person-safe'")),
            1,
        )


if __name__ == "__main__":
    unittest.main()
