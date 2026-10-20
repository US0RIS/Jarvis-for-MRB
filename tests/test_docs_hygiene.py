"""Documentation layout and roadmap hygiene contracts.

The archives preserve ideas and history; root docs stay navigable and short.
"""
from pathlib import Path
import re
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ENTRYPOINTS = (
    ROOT / "README.md",
    ROOT / "future.md",
    DOCS / "INDEX.md",
    DOCS / "CAPABILITIES.md",
)


class DocumentationHygieneTests(unittest.TestCase):
    def test_root_contains_only_readme_and_roadmap(self):
        files = {p.name for p in ROOT.glob("*.md")}
        self.assertEqual(files, {"README.md", "future.md"})

    def test_future_is_short_and_archive_retains_full_ideas(self):
        future = (ROOT / "future.md").read_text(encoding="utf-8")
        self.assertLess(len(future.splitlines()), 100)
        self.assertIn("FUTURE_IDEAS_2026_10.md", future)
        archived = DOCS / "archive" / "FUTURE_IDEAS_2026_10.md"
        self.assertTrue(archived.is_file())
        self.assertGreater(archived.stat().st_size, 100_000)

    def test_legacy_readme_is_preserved(self):
        archived = DOCS / "archive" / "README_LEGACY_2026_10.md"
        self.assertTrue(archived.is_file())
        self.assertGreater(archived.stat().st_size, 150_000)

    def test_canonical_entrypoint_links_resolve(self):
        bad = []
        for doc in ENTRYPOINTS:
            self.assertTrue(doc.is_file(), str(doc))
            source = doc.read_text(encoding="utf-8")
            for raw in re.findall(r"!?(?:\[[^\]\n]*\])\(([^)\n]+)\)", source):
                target = raw.strip().split(" ", 1)[0]
                if re.match(r"^(?:https?://|mailto:|tel:|#|//)", target):
                    continue
                filepath = unquote(target.split("#", 1)[0].split("?", 1)[0])
                if filepath and not (doc.parent / filepath).exists():
                    bad.append(f"{doc.relative_to(ROOT)} -> {target}")
        self.assertEqual(bad, [])

    def test_moved_technical_docs_are_indexed(self):
        root_docs = [
            "CONDUCTOR.md", "AGENCY_ACCEPTANCE.md",
            "JARVIS_COMPLETE_CAPABILITIES_AND_BUILD_HISTORY.md",
        ]
        index = (DOCS / "INDEX.md").read_text(encoding="utf-8")
        for name in root_docs:
            with self.subTest(name=name):
                self.assertFalse((ROOT / name).exists())
                self.assertTrue((DOCS / name).exists())
                self.assertIn(name, index)


if __name__ == "__main__":
    unittest.main()
