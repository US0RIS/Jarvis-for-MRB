from __future__ import annotations

import unittest
from pathlib import Path
from jarvis_mrb.explicit_meeting_actions import extract_structured_actions


class StructuredMeetingActionTests(unittest.TestCase):
    def test_explicit_actions_without_ollama(self) -> None:
        rows = extract_structured_actions(
            "ACTION: Alex Morgan | send the signed agreement | 2026-10-01\n"
            "TODO: counsel | collect final schedule | -"
        )
        self.assertIsNotNone(rows)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["owner"], "Alex Morgan")
        self.assertEqual(rows[0]["task"], "send the signed agreement")
        self.assertEqual(rows[0]["due"], "2026-10-01")
        self.assertEqual(rows[1]["due"], "")
        self.assertIn("ACTION: Alex Morgan", rows[0]["evidence"])

    def test_ambiguous_prose_and_unassigned_owner_fall_through(self) -> None:
        for text in (
            "Alex said he could send the agreement, or perhaps Mary would.",
            "ACTION: someone | send agreement | tomorrow",
            "ACTION: Alex | send agreement | tomorrow\n"
            "We also discussed something else.",
            "ACTION: Alex | send agreement",
            "ACTION: Alex | send agreement | tomorrow | extra field",
            "\n",
        ):
            with self.subTest(text=text):
                self.assertIsNone(extract_structured_actions(text))

    def test_real_meeting_extraction_invokes_pure_parser_before_model(self) -> None:
        source = (Path(__file__).resolve().parents[1] /
                  "jarvis_mrb/meeting_notes.py").read_text(encoding="utf-8")
        func = source[source.index("def _extract_actions("):source.index("def finish(", source.index("def _extract_actions("))]
        self.assertLess(func.index("extract_structured_actions(transcript)"),
                        func.index("client.post(f\"{OLLAMA_URL}/api/chat\""))


if __name__ == "__main__":
    unittest.main()
