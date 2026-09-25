from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.agency_goal_compiler as agency_goal_compiler
import jarvis_mrb.agency_runtime as agency_runtime
import jarvis_mrb.desired_state as desired_state
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_model as world_model


class AgencyGoalCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"

        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        desired_state.DB_PATH = self.db
        agency_runtime.DB_PATH = self.db
        permissions.APP_DIR = self.base
        permissions.POLICY_PATH = self.base / "permissions.json"

        world_model.status()
        world_executive.status()
        desired_state.status()
        agency_runtime.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _legacy_state(self, title: str = "Complete Project Apollo") -> tuple[str, str]:
        goal_id = world_model.ensure_entity("goal", title)
        world_model.assert_belief(goal_id, "status", value="active")
        world_model.assert_belief(goal_id, "next_action", value="Get final confirmation")
        desired_state.sync_from_intentions()
        states = desired_state.list_desired_states()
        self.assertEqual(len(states), 1)
        return goal_id, str(states[0]["id"])

    def _linked_pending_commitment(
        self,
        title: str = "Complete Project Apollo",
        *,
        commitment_id: str = "commitment:apollo-final",
    ) -> tuple[str, str]:
        _, state_id = self._legacy_state(title)
        source_event_id = world_model.record_event(
            "commitment.waiting_updated",
            f"Waiting item pending: {title} final confirmation",
            source_kind="iphone_waiting",
            source_ref=commitment_id,
            evidence="Pending external commitment observation.",
        )
        world_model.upsert_commitment(
            commitment_id,
            owner_name="Daniel Reed",
            action=f"{title} final confirmation",
            status="pending",
            source_event_id=source_event_id,
        )
        world_executive.refresh_intentions()
        state = desired_state.get_desired_state(state_id)
        self.assertIsNotNone(state)
        assert state is not None
        intention = agency_goal_compiler._intention_context(
            str(state.get("intention_id") or "")
        )
        commitment_ids = {
            str(item.get("id") or "")
            for item in (intention.get("commitments") or [])
        }
        self.assertIn(commitment_id, commitment_ids)
        return state_id, commitment_id

    def _compiler(self, _prompt: str) -> dict:
        return {
            "confidence": 0.94,
            "criteria": [
                {
                    "kind": "event_match",
                    "terms_all": ["Project Apollo", "completed"],
                    "terms_none": ["not completed", "pending"],
                    "event_types": [],
                    "source_kinds": [],
                }
            ],
            "explanation": "A later observed event must establish Project Apollo is completed.",
        }

    def test_activation_replaces_circular_goal_status_with_future_observation_contract(self) -> None:
        _, state_id = self._legacy_state()
        before = desired_state.get_desired_state(state_id)
        self.assertEqual(before["criteria"][0]["kind"], "belief_in")
        self.assertEqual(before["state"], "paused")

        activated = agency_runtime.activate_matching(
            "Complete Project Apollo",
            contract_compiler=self._compiler,
        )

        self.assertEqual(activated["state"], "active")
        self.assertTrue(activated["authority"]["agency_enabled"])
        self.assertTrue(activated["authority"]["contract_compiled"])
        self.assertGreaterEqual(float(activated["authority"]["contract_confidence"]), 0.9)
        criterion = activated["criteria"][0]
        self.assertEqual(criterion["kind"], "event_match")
        self.assertGreaterEqual(int(criterion["min_event_id"]), 0)
        self.assertIn("jarvis_verifier", criterion["source_kinds"])
        self.assertNotIn("jarvis_agency", criterion["source_kinds"])

    def test_internal_agency_narration_cannot_self_certify_goal_completion(self) -> None:
        _, state_id = self._legacy_state()
        activated = agency_runtime.activate_matching(
            "Complete Project Apollo",
            contract_compiler=self._compiler,
        )
        baseline = int(activated["criteria"][0]["min_event_id"])

        internal_event = world_model.record_event(
            "agency.plan.completed",
            "Project Apollo completed according to the Agency plan.",
            source_kind="jarvis_agency",
            source_ref="self-certification-attempt",
            evidence="Internal planner narration only.",
            confidence=1.0,
        )
        self.assertGreater(internal_event, baseline)

        evaluated = desired_state.evaluate_desired_state(state_id)
        self.assertFalse(evaluated["satisfied"])
        self.assertEqual(evaluated["state"], "active")
        self.assertIsNone(evaluated["criteria"][0]["event_id"])

    def test_later_independent_verifier_event_can_satisfy_compiled_goal(self) -> None:
        _, state_id = self._legacy_state()
        agency_runtime.activate_matching(
            "Complete Project Apollo",
            contract_compiler=self._compiler,
        )

        world_model.record_event(
            "verification.verified",
            "Action verification verified: Project Apollo completed.",
            source_kind="jarvis_verifier",
            source_ref="verification:apollo",
            evidence="Independent external read-back established Project Apollo completed.",
            confidence=1.0,
        )

        evaluated = desired_state.evaluate_desired_state(state_id)
        self.assertTrue(evaluated["satisfied"])
        self.assertEqual(evaluated["state"], "satisfied")
        self.assertEqual(evaluated["criteria"][0]["source"], "jarvis_verifier:verification:apollo")

    def test_negated_completion_evidence_does_not_satisfy_contract(self) -> None:
        _, state_id = self._legacy_state()
        agency_runtime.activate_matching(
            "Complete Project Apollo",
            contract_compiler=self._compiler,
        )
        world_model.record_event(
            "verification.failed",
            "Project Apollo not completed.",
            source_kind="jarvis_verifier",
            source_ref="verification:apollo-failed",
            evidence="Independent read-back says Project Apollo is not completed and remains pending.",
            confidence=1.0,
        )

        evaluated = desired_state.evaluate_desired_state(state_id)
        self.assertFalse(evaluated["satisfied"])
        self.assertEqual(evaluated["state"], "active")

    def test_compiler_cannot_authorize_internal_agency_events_as_completion_evidence(self) -> None:
        _, state_id = self._legacy_state()

        with self.assertRaises(ValueError):
            agency_runtime.activate_matching(
                "Complete Project Apollo",
                contract_compiler=lambda _prompt: {
                    "confidence": 0.99,
                    "criteria": [
                        {
                            "kind": "event_match",
                            "terms_all": ["Project Apollo", "completed"],
                            "terms_none": [],
                            "event_types": [],
                            "source_kinds": ["jarvis_agency"],
                        }
                    ],
                    "explanation": "Unsafe self-certifying contract.",
                },
            )

        state = desired_state.get_desired_state(state_id)
        self.assertEqual(state["state"], "blocked")
        self.assertFalse(state["authority"]["agency_enabled"])
        self.assertIn("non-observation source", state["blocked_reason"])

    def test_explicit_achieved_state_compiles_without_any_qwen_call(self) -> None:
        _, state_id = self._legacy_state("Have Project Apollo signed")
        with patch.object(
            agency_goal_compiler,
            "_model_compile",
            side_effect=AssertionError("Qwen must not compile an explicit achieved state"),
        ):
            compiled = agency_goal_compiler.compile_observable_contract(state_id)
        self.assertTrue(compiled["authority"]["contract_compiled"])
        self.assertEqual(compiled["criteria"][0]["terms_all"], ["Project Apollo", "signed"])
        self.assertNotIn("jarvis_agency", compiled["criteria"][0]["source_kinds"])

    def test_deterministic_fallback_requires_achieved_state_language(self) -> None:
        self.assertIsNone(
            agency_goal_compiler._fallback_contract(
                "Book dinner",
                {"entities": []},
            )
        )
        contract = agency_goal_compiler._fallback_contract(
            "Get Project Apollo signed",
            {"entities": []},
        )
        self.assertIsNotNone(contract)
        assert contract is not None
        criterion = contract["criteria"][0]
        self.assertEqual(criterion["terms_all"][0], "Project Apollo")
        self.assertEqual(criterion["terms_all"][1], "signed")

    def test_rejects_generic_subject_anchor_not_grounded_to_named_goal(self) -> None:
        _, state_id = self._legacy_state("Have Project Apollo signed")
        with self.assertRaisesRegex(ValueError, "specifically grounded"):
            agency_goal_compiler.compile_observable_contract(
                state_id,
                compiler=lambda _prompt: {
                    "confidence": 0.99,
                    "criteria": [
                        {
                            "kind": "event_match",
                            "terms_all": ["document", "signed"],
                            "terms_none": [],
                            "event_types": [],
                            "source_kinds": [],
                        }
                    ],
                    "explanation": "Too broad.",
                },
            )

    def test_accepts_specific_anchor_tokens_grounded_in_goal_context(self) -> None:
        _, state_id = self._legacy_state("Have Project Apollo signed")
        result = agency_goal_compiler.compile_observable_contract(
            state_id,
            compiler=lambda _prompt: {
                "confidence": 0.95,
                "criteria": [
                    {
                        "kind": "event_match",
                        "terms_all": ["Project Apollo", "signed"],
                        "terms_none": [],
                        "event_types": [],
                        "source_kinds": [],
                    }
                ],
                "explanation": "Project-specific future signature evidence.",
            },
        )
        self.assertEqual(
            result["criteria"][0]["terms_all"],
            ["Project Apollo", "signed"],
        )

    def test_rejects_completion_substring_such_as_unsigned(self) -> None:
        _, state_id = self._legacy_state("Have Apollo signed")
        with self.assertRaisesRegex(ValueError, "exact terms_all item"):
            agency_goal_compiler.compile_observable_contract(
                state_id,
                compiler=lambda _prompt: {
                    "confidence": 0.99,
                    "criteria": [
                        {
                            "kind": "event_match",
                            "terms_all": ["Apollo", "unsigned"],
                            "terms_none": [],
                            "event_types": [],
                            "source_kinds": [],
                        }
                    ],
                    "explanation": "Bad contract",
                },
            )

    def test_rejects_negated_completion_phrase_in_terms_all(self) -> None:
        _, state_id = self._legacy_state("Have Apollo signed")
        with self.assertRaisesRegex(ValueError, "exact terms_all item"):
            agency_goal_compiler.compile_observable_contract(
                state_id,
                compiler=lambda _prompt: {
                    "confidence": 0.99,
                    "criteria": [
                        {
                            "kind": "event_match",
                            "terms_all": ["Apollo", "not signed"],
                            "terms_none": [],
                            "event_types": [],
                            "source_kinds": [],
                        }
                    ],
                    "explanation": "Bad negated contract",
                },
            )

    def test_legitimate_subject_starting_with_un_is_not_treated_as_negation(self) -> None:
        _, state_id = self._legacy_state("Have United Airlines booked")
        result = agency_goal_compiler.compile_observable_contract(
            state_id,
            compiler=lambda _prompt: {
                "confidence": 0.95,
                "criteria": [
                    {
                        "kind": "event_match",
                        "terms_all": ["United Airlines", "booked"],
                        "terms_none": [],
                        "event_types": [],
                        "source_kinds": [],
                    }
                ],
                "explanation": "Future observation that United Airlines is booked.",
            },
        )
        self.assertEqual(result["criteria"][0]["terms_all"], ["United Airlines", "booked"])

    def test_injects_required_negations_when_model_omits_them(self) -> None:
        _, state_id = self._legacy_state("Have Apollo signed")
        result = agency_goal_compiler.compile_observable_contract(
            state_id,
            compiler=lambda _prompt: {
                "confidence": 0.95,
                "criteria": [
                    {
                        "kind": "event_match",
                        "terms_all": ["Apollo", "signed"],
                        "terms_none": [],
                        "event_types": [],
                        "source_kinds": [],
                    }
                ],
                "explanation": "Future external evidence that Apollo is signed.",
            },
        )
        criterion = result["criteria"][0]
        self.assertIn("not signed", criterion["terms_none"])
        self.assertIn("unsigned", criterion["terms_none"])
        self.assertIn("needs signature", criterion["terms_none"])
        self.assertIn("pending", criterion["terms_none"])

    def test_commitment_contract_rejects_resolution_that_occurs_during_compilation(self) -> None:
        state_id, commitment_id = self._linked_pending_commitment()

        def racing_compiler(_prompt: str) -> dict:
            resolution_event_id = world_model.record_event(
                "commitment.waiting_updated",
                "Waiting item resolved: Complete Project Apollo final confirmation",
                source_kind="iphone_waiting",
                source_ref=commitment_id,
                evidence="Commitment resolved while the goal contract model was running.",
            )
            world_model.upsert_commitment(
                commitment_id,
                owner_name="Daniel Reed",
                action="Complete Project Apollo final confirmation",
                status="resolved",
                source_event_id=resolution_event_id,
            )
            return {
                "confidence": 0.98,
                "criteria": [
                    {
                        "kind": "commitment_status",
                        "commitment_id": commitment_id,
                        "status": "resolved",
                    }
                ],
                "explanation": "Resolve the supplied commitment.",
            }

        with self.assertRaisesRegex(ValueError, "already resolved"):
            agency_goal_compiler.compile_observable_contract(
                state_id,
                compiler=racing_compiler,
            )

        state = desired_state.get_desired_state(state_id)
        self.assertEqual(state["state"], "blocked")
        self.assertFalse(state["authority"]["agency_enabled"])

    def test_commitment_contract_requires_resolution_event_after_compile_baseline(self) -> None:
        state_id, commitment_id = self._linked_pending_commitment(
            commitment_id="commitment:apollo-future-resolution"
        )
        compiled = agency_goal_compiler.compile_observable_contract(
            state_id,
            compiler=lambda _prompt: {
                "confidence": 0.97,
                "criteria": [
                    {
                        "kind": "commitment_status",
                        "commitment_id": commitment_id,
                        "status": "resolved",
                    }
                ],
                "explanation": "The linked pending commitment must resolve later.",
            },
        )
        criterion = compiled["criteria"][0]
        self.assertEqual(criterion["kind"], "commitment_status")
        baseline = int(criterion["min_resolution_event_id"])
        self.assertGreaterEqual(baseline, 0)

        before = desired_state.evaluate_desired_state(state_id, persist=True)
        self.assertFalse(before["satisfied"])
        self.assertEqual(before["criteria"][0]["min_resolution_event_id"], baseline)
        self.assertIsNone(before["criteria"][0]["resolution_event_id"])

        resolution_event_id = world_model.record_event(
            "commitment.waiting_updated",
            "Waiting item resolved: Complete Project Apollo final confirmation",
            source_kind="iphone_waiting",
            source_ref=commitment_id,
            evidence="Later external commitment resolution.",
        )
        self.assertGreater(resolution_event_id, baseline)
        world_model.upsert_commitment(
            commitment_id,
            owner_name="Daniel Reed",
            action="Complete Project Apollo final confirmation",
            status="resolved",
            source_event_id=resolution_event_id,
        )

        after = desired_state.evaluate_desired_state(state_id, persist=True)
        self.assertTrue(after["satisfied"])
        self.assertEqual(
            after["criteria"][0]["resolution_event_id"],
            resolution_event_id,
        )

    def test_low_confidence_contract_blocks_activation_and_does_not_grant_agency_authority(self) -> None:
        _, state_id = self._legacy_state("Complete Project Mercury")

        with self.assertRaises(ValueError):
            agency_runtime.activate_matching(
                "Complete Project Mercury",
                contract_compiler=lambda _prompt: {
                    "confidence": 0.4,
                    "criteria": [],
                    "explanation": "Unclear success evidence.",
                },
            )

        state = desired_state.get_desired_state(state_id)
        self.assertEqual(state["state"], "blocked")
        self.assertFalse(state["authority"]["agency_enabled"])
        self.assertFalse(state["authority"]["contract_compiled"])
        self.assertIn("Observable success contract", state["blocked_reason"])


if __name__ == "__main__":
    unittest.main()
