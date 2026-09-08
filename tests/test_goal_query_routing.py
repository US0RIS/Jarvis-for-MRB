from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb.agent import handle_natural_language


class GoalQueryRoutingTests(unittest.TestCase):
    def test_current_goals_bypass_planner_and_calendar_context(self) -> None:
        overview = "\n".join(
            [
                "active_profile: default",
                "focused_on: Jarvis",
                "active goal: Project Apollo — next Review disclosure schedules",
            ]
        )
        with patch("jarvis_mrb.world_model.active_overview", return_value=overview), patch(
            "jarvis_mrb.agent._ollama_plan"
        ) as planner:
            reply = handle_natural_language("What are my current goals?")

        planner.assert_not_called()
        self.assertTrue(reply.ok)
        self.assertIn("Project Apollo", reply.message)
        self.assertIn("Review disclosure schedules", reply.message)
        self.assertNotIn("upcoming event", reply.message.lower())

    def test_no_active_goals_returns_none_not_calendar_event(self) -> None:
        overview = "\n".join(
            [
                "active_profile: default",
                "focused_on: Jarvis",
                "located_at: home",
            ]
        )
        with patch("jarvis_mrb.world_model.active_overview", return_value=overview), patch(
            "jarvis_mrb.agent._ollama_plan"
        ) as planner:
            reply = handle_natural_language("What are my current goals?")

        planner.assert_not_called()
        self.assertTrue(reply.ok)
        self.assertIn("no active goals", reply.message.lower())
        self.assertNotIn("calendar", reply.message.lower())
        self.assertNotIn("event", reply.message.lower())


if __name__ == "__main__":
    unittest.main()
