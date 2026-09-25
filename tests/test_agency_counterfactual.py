from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.agency_counterfactual as agency_counterfactual
import jarvis_mrb.agent as agent
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_verification as world_verification
import jarvis_mrb.world_model as world_model


class AgencyCounterfactualTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        agency_counterfactual.DB_PATH = self.db
        world_verification.DB_PATH = self.db
        world_model.status()
        agency_counterfactual.status()
        world_verification.status()

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

    def test_agent_tools_expose_counterfactual_lifecycle_without_external_authority(self) -> None:
        created = agent._execute_unchecked(
            "agency.counterfactual.create",
            {
                "question": "Which reversible launch path should Project Orion take?",
                "context": "The pilot is cheap; full rollout is faster but harder to reverse.",
                "branches": [
                    {
                        "id": "pilot",
                        "title": "Pilot first",
                        "assumptions": ["Pilot signal is representative"],
                        "evidence": [{"source": "context", "fact": "Pilot is cheap"}],
                        "expected_outcomes": ["Learn before scaling"],
                        "cost": {"relative": "low"},
                        "reversibility": 0.95,
                        "uncertainty": 0.35,
                    },
                    {
                        "id": "rollout",
                        "title": "Full rollout",
                        "assumptions": ["Demand is already established"],
                        "evidence": [{"source": "context", "fact": "Rollout is faster"}],
                        "expected_outcomes": ["Reach scale sooner"],
                        "cost": {"relative": "high"},
                        "reversibility": 0.2,
                        "uncertainty": 0.6,
                    },
                ],
            },
        )
        self.assertTrue(created.ok, created.message)
        self.assertIsInstance(created.data, dict)
        case_id = str(created.data["id"])

        compared = agent._execute_unchecked(
            "agency.counterfactual.compare",
            {"case_id": case_id},
        )
        self.assertTrue(compared.ok, compared.message)
        self.assertEqual(len(compared.data["branches"]), 2)
        self.assertEqual(compared.data["status"], "open")

        selected = agent._execute_unchecked(
            "agency.counterfactual.select",
            {
                "case_id": case_id,
                "branch": "pilot",
                "rationale": "Pilot first preserves optionality while uncertainty remains material.",
                "change_conditions": [
                    "Reopen the choice if independent demand evidence is strong enough to justify full rollout."
                ],
            },
        )
        self.assertTrue(selected.ok, selected.message)
        self.assertEqual(selected.data["status"], "selected")
        self.assertEqual(len(selected.data["branches"]), 2)
        by_key = {item["key"]: item for item in selected.data["branches"]}
        self.assertEqual(by_key["pilot"]["status"], "selected")
        self.assertEqual(by_key["rollout"]["status"], "candidate")
        self.assertEqual(
            permissions.TOOL_RISK["agency.counterfactual.compare"],
            "read",
        )
        self.assertEqual(
            permissions.TOOL_RISK["agency.counterfactual.create"],
            "local_write",
        )
        self.assertEqual(
            permissions.TOOL_RISK["agency.counterfactual.select"],
            "local_write",
        )

    def test_counterfactual_agent_writes_have_independent_ledger_verification(self) -> None:
        create_args = {
            "question": "Which deployment path?",
            "branches": [
                {"id": "a", "title": "Pilot"},
                {"id": "b", "title": "Rollout"},
            ],
        }
        created = agent._execute_unchecked(
            "agency.counterfactual.create",
            create_args,
        )
        self.assertTrue(created.ok, created.message)
        create_event = world_model.record_tool_execution(
            "agency.counterfactual.create",
            create_args,
            ok=True,
            message=created.message,
        )
        create_verification = world_verification.register_execution(
            "agency.counterfactual.create",
            create_args,
            created,
            action_event_id=create_event,
        )
        create_after = world_verification.check_one(
            create_verification,
            force=True,
        )
        self.assertEqual(create_after["status"], "verified")

        case_id = str(created.data["id"])
        select_args = {
            "case_id": case_id,
            "branch": "a",
            "rationale": "Pilot is more reversible.",
            "change_conditions": ["Reopen if rollout risk falls materially."],
        }
        selected = agent._execute_unchecked(
            "agency.counterfactual.select",
            select_args,
        )
        self.assertTrue(selected.ok, selected.message)
        select_event = world_model.record_tool_execution(
            "agency.counterfactual.select",
            select_args,
            ok=True,
            message=selected.message,
        )
        select_verification = world_verification.register_execution(
            "agency.counterfactual.select",
            select_args,
            selected,
            action_event_id=select_event,
        )
        select_after = world_verification.check_one(
            select_verification,
            force=True,
        )
        self.assertEqual(select_after["status"], "verified")
        self.assertGreater(int(select_after["resolved_event_id"]), 0)

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
