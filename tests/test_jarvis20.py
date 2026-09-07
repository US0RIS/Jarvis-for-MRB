from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jarvis_mrb.jarvis20 import NORTH_STAR_IDS, SPECS, history, save_scored_run, score_run, score_template


class Jarvis20Tests(unittest.TestCase):
    def test_frozen_suite_has_twenty_unique_tests(self) -> None:
        self.assertEqual(len(SPECS), 20)
        self.assertEqual({spec.id for spec in SPECS}, set(range(1, 21)))
        self.assertEqual(len({spec.name for spec in SPECS}), 20)

    def test_north_star_is_fixed_four_tests(self) -> None:
        self.assertEqual(NORTH_STAR_IDS, frozenset({7, 8, 12, 17}))

    def test_perfect_score_is_sixty_and_north_star_twelve(self) -> None:
        payload = score_template(variant_seed="unit-test")
        payload["build"] = "abc123"
        for row in payload["results"]:
            row["score"] = 3
            row["instance"] = f"variant-{row['id']}"
        report = score_run(payload)
        self.assertEqual(report["score"], 60)
        self.assertEqual(report["maximum"], 60)
        self.assertEqual(report["north_star_score"], 12)
        self.assertEqual(report["percent"], 100.0)
        self.assertEqual(report["level"], "exceptional / near north-star")

    def test_low_score_does_not_get_inflated(self) -> None:
        payload = score_template()
        for row in payload["results"]:
            row["score"] = 0
        payload["results"][6]["score"] = 3  # situational awareness only
        report = score_run(payload)
        self.assertEqual(report["score"], 3)
        self.assertEqual(report["north_star_score"], 3)
        self.assertEqual(report["level"], "prototype")

    def test_missing_test_is_rejected(self) -> None:
        payload = score_template()
        for row in payload["results"]:
            row["score"] = 2
        payload["results"].pop()
        with self.assertRaises(ValueError):
            score_run(payload)

    def test_out_of_range_score_is_rejected(self) -> None:
        payload = score_template()
        for row in payload["results"]:
            row["score"] = 2
        payload["results"][0]["score"] = 4
        with self.assertRaises(ValueError):
            score_run(payload)

    def test_saved_runs_create_history_without_latest_duplication(self) -> None:
        payload = score_template()
        for row in payload["results"]:
            row["score"] = 2
        report = score_run(payload)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            path = save_scored_run(report, directory=root)
            self.assertTrue(path.exists())
            self.assertTrue((root / "latest.json").exists())
            rows = history(directory=root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["score"], 40)


if __name__ == "__main__":
    unittest.main()
