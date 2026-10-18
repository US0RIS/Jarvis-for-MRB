from __future__ import annotations

import re
import unittest
from pathlib import Path

from jarvis_mrb.horus import registry

FUTURE = Path(__file__).resolve().parents[1] / "future.md"


def future_ideas() -> list[str]:
    titles = []
    for line in FUTURE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*- \*\*(.+?)\*\*", line)
        if m:
            titles.append(m.group(1))
    return titles


class RegistryTests(unittest.TestCase):
    def test_every_future_idea_is_mapped(self) -> None:
        missing = [t for t in future_ideas() if t not in registry.IDEAS]
        self.assertEqual(missing, [], "future.md ideas without an implementation mapping")

    def test_no_stale_registry_entries(self) -> None:
        titles = set(future_ideas())
        stale = [t for t in registry.IDEAS if t not in titles]
        self.assertEqual(stale, [])

    def test_every_reference_resolves(self) -> None:
        for title, (kind, refs) in {**registry.IDEAS, **registry.PROSE_IDEAS}.items():
            self.assertIn(kind, {"implemented", "harness", "catalog", "naming"}, title)
            self.assertTrue(refs, title)
            for ref in refs:
                with self.subTest(idea=title, ref=ref):
                    self.assertIsNotNone(registry.resolve(ref))

    def test_catalog_entries_name_their_repo(self) -> None:
        from jarvis_mrb.horus.radar import CATALOG

        repos = {c.repo.lower() for c in CATALOG}
        for title, (kind, _) in registry.IDEAS.items():
            if kind == "catalog":
                repo = title.split(" ")[0].lower()
                with self.subTest(idea=title):
                    self.assertIn(repo, repos)

    def test_summary_and_lookup(self) -> None:
        s = registry.summary()
        self.assertGreaterEqual(s["ideas"], len(future_ideas()))
        self.assertTrue(registry.lookup("reality rewind"))


if __name__ == "__main__":
    unittest.main()
