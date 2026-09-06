from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.world_document_versions as world_document_versions
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model


class DocumentVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_linker.DB_PATH = self.db
        world_document_versions.DB_PATH = self.db
        world_model.status()
        world_linker.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _rows(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _attachment(
        self,
        source_ref: str,
        filename: str,
        text: str,
        *,
        thread_id: str,
        subject: str,
    ) -> int:
        event_id = world_model.record_knowledge_source(
            "gmail_attachment",
            source_ref,
            title=filename,
            text=text,
            occurred_at="2026-09-06T12:00:00-07:00",
            metadata={
                "message_id": source_ref.split(":", 1)[0],
                "thread_id": thread_id,
                "filename": filename,
                "email_subject": subject,
            },
        )
        world_linker.link_event(event_id)
        return event_id

    def test_related_drafts_detect_numeric_term_change_and_supersession(self) -> None:
        old = self._attachment(
            "m1:a1",
            "Project Apollo Purchase Agreement Draft v1.docx",
            "Project Apollo. The indemnity cap shall equal 10% of the Purchase Price. The survival period is 18 months.",
            thread_id="thread-apollo",
            subject="Project Apollo purchase agreement",
        )
        new = self._attachment(
            "m2:a2",
            "Project Apollo Purchase Agreement Revised v2.docx",
            "Project Apollo. The indemnity cap shall equal 15% of the Purchase Price. The survival period is 18 months.",
            thread_id="thread-apollo",
            subject="Re: Project Apollo purchase agreement",
        )

        result = world_document_versions.refresh()
        self.assertEqual(result["pairs_compared"], 1)
        self.assertEqual(result["pairs_with_changes"], 1)
        self.assertGreaterEqual(result["numeric_change_passages"], 1)

        changes = self._rows("SELECT id,summary FROM events WHERE event_type='document.version_changed'")
        self.assertEqual(len(changes), 1)
        self.assertIn("10%", str(changes[0]["summary"]))
        self.assertIn("15%", str(changes[0]["summary"]))

        old_doc = self._rows(
            "SELECT entity_id FROM external_ids WHERE namespace='gmail_attachment' AND external_id='m1:a1'"
        )[0]["entity_id"]
        new_doc = self._rows(
            "SELECT entity_id FROM external_ids WHERE namespace='gmail_attachment' AND external_id='m2:a2'"
        )[0]["entity_id"]
        relations = self._rows(
            "SELECT confidence,evidence_count FROM entity_relations WHERE subject_id=? AND predicate='supersedes' AND object_id=?",
            (str(new_doc), str(old_doc)),
        )
        self.assertEqual(len(relations), 1)
        self.assertGreater(float(relations[0]["confidence"]), 0.8)
        self.assertGreaterEqual(int(relations[0]["evidence_count"]), 1)

        pair = self._rows(
            "SELECT comparison_event_id FROM document_version_pairs WHERE older_event_id=? AND newer_event_id=?",
            (old, new),
        )
        self.assertEqual(len(pair), 1)
        self.assertIsNotNone(pair[0]["comparison_event_id"])

    def test_unrelated_generic_files_are_not_forced_into_same_lineage(self) -> None:
        self._attachment(
            "m10:x1",
            "Purchase Agreement Draft.docx",
            "Project Apollo acquisition. Seller indemnification is capped at 10% of the purchase price. Closing is Friday.",
            thread_id="thread-apollo",
            subject="Project Apollo agreement",
        )
        self._attachment(
            "m20:x2",
            "Purchase Agreement Revised.docx",
            "Project Borealis acquisition. Employee benefits continue for twelve months. The headquarters lease remains in effect.",
            thread_id="thread-borealis",
            subject="Project Borealis agreement",
        )

        result = world_document_versions.refresh()
        self.assertEqual(result["pairs_compared"], 0)
        self.assertGreaterEqual(result["lineage_candidates_rejected"], 1)
        self.assertEqual(len(self._rows("SELECT 1 FROM events WHERE event_type='document.version_changed'")), 0)

    def test_equivalent_new_version_records_lineage_without_false_change_alert(self) -> None:
        body = "Project Atlas. The escrow amount equals $5,000,000 and the survival period is 12 months."
        self._attachment(
            "m30:z1",
            "Project Atlas Agreement Draft.docx",
            body,
            thread_id="thread-atlas",
            subject="Project Atlas agreement",
        )
        self._attachment(
            "m31:z2",
            "Project Atlas Agreement Final.docx",
            body,
            thread_id="thread-atlas",
            subject="Re: Project Atlas agreement",
        )
        result = world_document_versions.refresh()
        self.assertEqual(result["pairs_compared"], 1)
        self.assertEqual(result["pairs_with_changes"], 0)
        self.assertEqual(len(self._rows("SELECT 1 FROM events WHERE event_type='document.version_equivalent'")), 1)


if __name__ == "__main__":
    unittest.main()
