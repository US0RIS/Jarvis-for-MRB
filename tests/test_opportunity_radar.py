from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from jarvis_mrb.opportunity_radar import _object_sought, consider_object_sighting


class OpportunityRadarTests(TestCase):
    def test_only_explicit_exact_object_finding_goals_qualify(self) -> None:
        self.assertEqual(_object_sought({"title": "Find my keys"}), "keys")
        self.assertEqual(_object_sought({"title": "Locate the black backpack"}), "black backpack")
        self.assertEqual(_object_sought({"title": "Work", "next_action": "Look for my wallet"}), "wallet")
        for title in (
            "Find me a hotel", "Improve home safety", "Get to the airport",
            "Find my keys and send a message", "Find my neighbor", "Get groceries",
            "Find the person", "Find my keys then unlock the door",
        ):
            with self.subTest(title=title):
                self.assertEqual(_object_sought({"title": title}), "")

    @patch("jarvis_mrb.agency_attention.consider")
    @patch("jarvis_mrb.world_executive.active_intentions")
    @patch("jarvis_mrb.opportunity_radar.get_state")
    def test_sighting_surfaces_tentative_observation_not_an_action(
        self, state, goals, consider
    ) -> None:
        state.return_value = {"preferences": {"proactive_monitoring": True}, "devices": {}}
        goals.return_value = [
            {"id": "goal:keys", "title": "Find my keys", "confidence": 1.0},
            {"id": "goal:wallet", "title": "Find my wallet", "confidence": 1.0},
        ]
        consider.return_value = {"emitted": True, "decision": "interrupt"}
        result = consider_object_sighting("keys", location_context="home", confidence=0.65)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["goal_id"], "goal:keys")
        call = consider.call_args.kwargs
        self.assertIn("may have spotted keys", call["message"])
        self.assertIn("near home", call["message"])
        self.assertEqual(call["kind"], "visual_object_opportunity")
        self.assertEqual(call["desired_state_id"], "goal:keys")
        self.assertEqual(call["severity"], "warning")
        self.assertEqual(call["dedup_seconds"], 6 * 3600)
        self.assertLessEqual(call["confidence"], 0.70)
        self.assertNotIn("tool", call)
        self.assertNotIn("execute", call)

        self.assertEqual(
            consider_object_sighting("wallet", location_context="unknown", confidence=0.59),
            [],
        )
        self.assertEqual(consider.call_count, 1)

    @patch("jarvis_mrb.agency_attention.consider")
    @patch("jarvis_mrb.world_executive.active_intentions")
    @patch("jarvis_mrb.opportunity_radar.get_state")
    def test_privacy_preference_and_driving_suppress_discovery(
        self, state, goals, consider
    ) -> None:
        goals.return_value = [{"id": "g", "title": "Find my keys", "confidence": 1}]
        for disabled in (
            {"preferences": {"proactive_monitoring": False}},
            {"active_profile": "driving"},
            {"devices": {"camera_master_enabled": False}},
            {"devices": {"passive_vision": False}},
        ):
            with self.subTest(disabled=disabled):
                state.return_value = disabled
                self.assertEqual(
                    consider_object_sighting("keys", location_context="home", confidence=0.65),
                    [],
                )
        consider.assert_not_called()

    @patch("jarvis_mrb.agency_attention.consider")
    @patch("jarvis_mrb.world_executive.active_intentions")
    @patch("jarvis_mrb.opportunity_radar.get_state", return_value={})
    def test_nonmatching_and_people_are_never_alerts(
        self, _state, goals, consider
    ) -> None:
        goals.return_value = [{"id": "g", "title": "Find my wallet", "confidence": 1}]
        self.assertEqual(
            consider_object_sighting("keys", location_context="home", confidence=0.9), []
        )
        self.assertEqual(
            consider_object_sighting("person", location_context="home", confidence=0.9), []
        )
        goals.return_value = [{"id": "g", "title": "Find my keys", "confidence": 0.4}]
        self.assertEqual(
            consider_object_sighting("keys", location_context="home", confidence=0.9), []
        )
        consider.assert_not_called()
