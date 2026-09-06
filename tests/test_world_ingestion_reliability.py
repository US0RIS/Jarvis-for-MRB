from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.world_gmail_attachments as attachments
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_prebrief as world_prebrief


class WorldIngestionReliabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        attachments.DB_PATH = self.db
        world_prebrief.DB_PATH = self.db
        world_model.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_attachment_checkpoint_uses_overlap_and_resumable_page_token(self) -> None:
        attachments.status()  # creates the additive sync-state table
        checkpoint_ms = 1_800_000_000_000
        attachments._state_set(last_complete_internal_ms=checkpoint_ms)
        query, token, pending_max = attachments._effective_query(attachments._DEFAULT_QUERY)
        self.assertEqual(token, "")
        self.assertEqual(pending_max, 0)
        expected_after = checkpoint_ms // 1000 - attachments._OVERLAP_SECONDS
        self.assertIn(f"after:{expected_after}", query)

        attachments._state_set(
            pending_page_token="gmail-page-token",
            pending_effective_query="in:anywhere has:attachment after:123",
            pending_logical_query=attachments._DEFAULT_QUERY,
            pending_max_internal_ms=checkpoint_ms + 5000,
        )
        query, token, pending_max = attachments._effective_query(attachments._DEFAULT_QUERY)
        self.assertEqual(query, "in:anywhere has:attachment after:123")
        self.assertEqual(token, "gmail-page-token")
        self.assertEqual(pending_max, checkpoint_ms + 5000)

    def test_custom_attachment_query_does_not_reuse_default_checkpoint(self) -> None:
        attachments.status()
        attachments._state_set(
            last_complete_internal_ms=1_800_000_000_000,
            pending_page_token="default-token",
            pending_effective_query="default-query",
            pending_logical_query=attachments._DEFAULT_QUERY,
        )
        custom = "from:daniel@example.com has:attachment"
        query, token, pending_max = attachments._effective_query(custom)
        self.assertEqual(query, custom)
        self.assertEqual(token, "")
        self.assertEqual(pending_max, 0)

    def test_xlsx_is_passively_extracted_without_formula_execution(self) -> None:
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Apollo"
        sheet.append(["Term", "Value"])
        sheet.append(["Indemnity cap", "15%"])
        sheet.append(["Formula", "=1+1"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()

        text = attachments._extract("Apollo Terms.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer.getvalue())
        self.assertIn("Sheet: Apollo", text)
        self.assertIn("Indemnity cap", text)
        self.assertIn("15%", text)
        # data_only=True means Jarvis never evaluates the formula itself. Depending on
        # whether a cached value exists, the formula cell may be absent or contain only
        # a previously saved cached result; it must never expose the executable formula.
        self.assertNotIn("=1+1", text)

    def test_attachment_status_declares_textless_pdf_ocr_as_unsupported(self) -> None:
        status = attachments.status()
        self.assertEqual(status["scanned_pdf_ocr"], "explicitly unsupported_needs_ocr")
        self.assertTrue(status["resumable_pagination"])
        self.assertTrue(status["xlsx_passive_text"])

    def test_prebrief_suppresses_document_diff_already_explained_by_term_conflict(self) -> None:
        apollo = world_model.ensure_entity("project", "Project Apollo")
        old_attachment = world_model.record_event(
            "knowledge.gmail_attachment",
            "Old Apollo draft",
            source_kind="gmail_attachment",
            source_ref="old",
            occurred_at="2026-09-01T10:00:00-07:00",
            participants=[(apollo, "project", 1.0)],
        )
        new_attachment = world_model.record_event(
            "knowledge.gmail_attachment",
            "New Apollo draft",
            source_kind="gmail_attachment",
            source_ref="new",
            occurred_at="2026-09-02T10:00:00-07:00",
            participants=[(apollo, "project", 1.0)],
        )
        term_event = world_model.record_event(
            "term.changed_or_conflicted",
            "Project Apollo indemnity cap changed from 10% to 15%.",
            source_kind="term_ledger",
            source_ref="term",
            occurred_at="2026-09-02T10:00:00-07:00",
            payload={
                "older": {"source_event_id": old_attachment},
                "newer": {"source_event_id": new_attachment},
            },
            participants=[(apollo, "project", 1.0)],
        )
        diff_event = world_model.record_event(
            "document.version_changed",
            "New version changes numeric terms from 10% to 15%.",
            source_kind="document_diff",
            source_ref="old->new",
            occurred_at="2026-09-02T10:00:00-07:00",
            payload={
                "older": {"event_id": old_attachment},
                "newer": {"event_id": new_attachment},
                "changes": [{"old_numbers": ["10%"], "new_numbers": ["15%"]}],
            },
            participants=[(apollo, "project", 1.0)],
        )
        ordinary_event = world_model.record_event(
            "knowledge.gmail",
            "Daniel sent the signing agenda.",
            source_kind="gmail",
            source_ref="agenda",
            occurred_at="2026-09-02T11:00:00-07:00",
            participants=[(apollo, "project", 1.0)],
        )

        recent = [
            {"id": term_event, "type": "term.changed_or_conflicted", "summary": "term"},
            {"id": diff_event, "type": "document.version_changed", "summary": "diff"},
            {"id": ordinary_event, "type": "knowledge.gmail", "summary": "agenda"},
        ]
        deduped = world_prebrief._deduplicate_document_changes(recent)
        self.assertEqual([item["type"] for item in deduped], ["term.changed_or_conflicted", "knowledge.gmail"])


if __name__ == "__main__":
    unittest.main()
