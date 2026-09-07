from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jarvis_mrb.jarvis20_fuzz import run_world_fuzz


class Jarvis20FuzzTests(unittest.TestCase):
    def test_rejects_invalid_count(self) -> None:
        with self.assertRaises(ValueError):
            run_world_fuzz("x", count=0)
        with self.assertRaises(ValueError):
            run_world_fuzz("x", count=501)

    @patch("jarvis_mrb.jarvis20_fuzz.run_world_variant")
    @patch("jarvis_mrb.jarvis20_fuzz.generate_variant_bundle")
    def test_aggregates_failures_by_seed_and_test(self, generate, run) -> None:
        def fake_bundle(seed, anchor=None):
            return SimpleNamespace(
                public={
                    "scenario_id": f"scenario-{seed}",
                    "world_fixture": {"project": "Project Test"},
                },
                oracle={"world": {"expected_term": {"term_key": "indemnity_cap"}}},
            )

        results = [
            {
                "ok": True,
                "tests": {str(i): {"passed": True} for i in range(5, 11)},
                "failed_checks": [],
            },
            {
                "ok": False,
                "tests": {
                    **{str(i): {"passed": True} for i in range(5, 11)},
                    "8": {"passed": False},
                },
                "failed_checks": ["term chronology failed"],
            },
        ]
        generate.side_effect = fake_bundle
        run.side_effect = results

        report = run_world_fuzz("nightly", count=2)
        self.assertFalse(report["ok"])
        self.assertEqual(report["passed_worlds"], 1)
        self.assertEqual(report["failed_worlds"], 1)
        self.assertEqual(report["tests"]["8"], {"passed": 1, "failed": 1})
        self.assertEqual(report["failures"][0]["seed"], "nightly-0002")
        self.assertEqual(report["failures"][0]["failed_tests"], [8])


if __name__ == "__main__":
    unittest.main()
