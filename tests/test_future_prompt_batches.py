"""Ensure every original future.md bullet has one bounded implementation packet."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs" / "implementation_batches"


class FuturePromptCoverageTests(unittest.TestCase):
    def test_all_archive_entries_are_covered_once(self):
        archive = (ROOT / "docs" / "archive" / "FUTURE_IDEAS_2026_10.md").read_text(encoding="utf-8")
        expected = {
            i for i, line in enumerate(archive.splitlines(), 1)
            if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line)
        }
        seen = []
        packets = {}
        for file in sorted(BASE.glob("[0-9][0-9]_*.md")):
            batch = None
            for line in file.read_text(encoding="utf-8").splitlines():
                match = re.match(r"^### (P\d{2}-\d{3})$", line)
                if match:
                    batch = match.group(1)
                    self.assertNotIn(batch, packets)
                    packets[batch] = []
                entry = re.search(r"\[(?:source|archived requirement) L(\d+)\]", line)
                if entry:
                    self.assertIsNotNone(batch)
                    number = int(entry.group(1))
                    seen.append(number)
                    packets[batch].append(number)
        self.assertEqual(len(seen), len(expected))
        self.assertEqual(set(seen), expected)
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue(all(1 <= len(v) <= 3 for v in packets.values()))
        self.assertGreaterEqual(len(packets), 150)

    def test_active_roadmap_remains_short(self):
        roadmap = (ROOT / "future.md").read_text(encoding="utf-8")
        self.assertLess(len(roadmap.splitlines()), 100)
        self.assertIn("implementation_batches/README.md", roadmap)
        self.assertTrue((BASE / "TRACE.md").is_file())


if __name__ == "__main__":
    unittest.main()
