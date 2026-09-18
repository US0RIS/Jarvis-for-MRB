from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.agency_counterfactual as agency_counterfactual
import jarvis_mrb.world_model as world_model


class AgencyCounterfactualTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        agency_counterfactual.DB_PATH = self.db
        world_model.status()
        agency_counterfactual.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_selecting_one_branch_preserves_alternatives_and_change_conditions(self) -> None:
        case = agency_counterfactual.create_case(
            "How should Project Orion proceed?",
            [
                {
                    "id": "a",
                    "title": "Fast reversible pilot",
                    "plan": {"steps": ["pilot"]},
                    "assumptions": ["Pilot data is representative"],
                    "evidence": [{"source": "test", "fact": "Pilot costs 10"}],
                    "expected_outcomes": ["Fast evidence"],
                    "cost": {"usd": 10},
                    "reversibility": 0.95,
                    "uncertainty": 0.4,
                },
                {
                    "id": "b",
                    "title": "Full rollout",
                    "plan": {"steps": ["rollout"]},
                    "assumptions": ["Demand is stable"],
                    "evidence": [{"source": "test", "fact": "Rollout costs 100"}],
                    "expected_outcomes": ["Immediate scale"],
                    "cost": {"usd": 100},
                    "reversibility": 0.2,
                    "uncertainty": 0.6,
                },
            ],
        )

        selected = agency_counterfactual.select_branch(
            case["id"],
            "a",
            rationale="The pilot is much more reversible while uncertainty remains material.",
            change_conditions=[
                "Choose full rollout if representative demand is independently established.",
                "Reconsider if pilot latency exceeds two weeks.",
            ],
        )

        self.assertEqual(selected["status"], "selected")
        self.assertEqual(len(selected["branches"]), 2)
        by_key = {branch["key"]: branch for branch in selected["branches"]}
        self.assertEqual(by_key["a"]["status"], "selected")
        self.assertEqual(by_key["b"]["status"], "candidate")
        self.assertEqual(len(selected["change_conditions"]), 2)

        comparison = agency_counterfactual.comparison(case["id"])
        self.assertEqual(len(comparison["branches"]), 2)
        self.assertIn("reversible", comparison["selection_rationale"])
        self.assertEqual(comparison["branches"][1]["cost"]["usd"], 100)

    def test_selection_requires_explicit_rationale(self) -> None:
        case = agency_counterfactual.create_case(
            "Choose path",
            [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
        )
        with self.assertRaisesRegex(ValueError, "explicit rationale"):
            agency_counterfactual.select_branch(
                case["id"],
                "a",
                rationale="   ",
                change_conditions=["New evidence"],
            )

    def test_selection_requires_condition_that_would_reopen_choice(self) -> None:
        case = agency_counterfactual.create_case(
            "Choose path",
            [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
        )
        with self.assertRaisesRegex(ValueError, "condition"):
            agency_counterfactual.select_branch(
                case["id"],
                "a",
                rationale="A is more reversible.",
                change_conditions=[],
            )

    def test_case_requires_multiple_branches(self) -> None:
        with self.assertRaises(ValueError):
            agency_counterfactual.create_case(
                "Only one?",
                [{"id": "a", "title": "A"}],
            )

    def test_branch_dimensions_round_trip_without_collapsing_uncertainty(self) -> None:
        case = agency_counterfactual.create_case(
            "Choose architecture",
            [
                {
                    "id": "x",
                    "title": "X",
                    "assumptions": ["A1"],
                    "evidence": [{"source": "s1", "claim": "C1"}],
                    "expected_outcomes": ["O1"],
                    "cost": {"engineering_days": 3},
                    "reversibility": 0.8,
                    "uncertainty": 0.25,
                },
                {
                    "id": "y",
                    "title": "Y",
                    "assumptions": ["A2"],
                    "evidence": [{"source": "s2", "claim": "C2"}],
                    "expected_outcomes": ["O2"],
                    "cost": {"engineering_days": 8},
                    "reversibility": 0.4,
                    "uncertainty": 0.75,
                },
            ],
        )
        loaded = agency_counterfactual.get_case(case["id"])
        self.assertEqual(loaded["branches"][0]["uncertainty"], 0.25)
        self.assertEqual(loaded["branches"][1]["uncertainty"], 0.75)
        self.assertEqual(loaded["branches"][0]["evidence"][0]["source"], "s1")


if __name__ == "__main__":
    unittest.main()
