from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb.agency_command_view import build_command_view


class AgencyCommandViewTests(unittest.TestCase):
    def test_goal_order_approval_outside_visible_limit_and_no_sensitive_step_args(self) -> None:
        goals = [
            {"id": "low", "title": "Later goal", "state": "active", "priority": 1, "last_evaluated_at": ""},
            {"id": "high", "title": "Prepare trip", "state": "active", "priority": 99, "last_evaluated_at": "2026-09-19T10:00:00-07:00"},
            {"id": "old", "title": "Retired", "state": "retired", "priority": 1000},
        ]
        plans = {
            "high": {
                "status": "active",
                "steps": [
                    {"id": "a", "tool": "knowledge.search", "step_key": "research", "status": "verified"},
                    {"id": "b", "tool": "web.search", "step_key": "lookup", "status": "pending"},
                ],
            },
            "low": {
                "status": "awaiting_approval",
                "steps": [
                    {
                        "id": "sensitive-step",
                        "tool": "gmail.send",
                        "status": "awaiting_approval",
                        "result_summary": "Email awaiting confirmation",
                        "arguments": {"body": "DO NOT EXPOSE THIS BODY"},
                    },
                ],
            },
        }
        events = [
            {"message": "A meeting changed", "severity": "warning", "last_seen_at": "2026-09-19", "emitted_count": 1},
            {"message": "Routine update", "severity": "info", "last_seen_at": "2026-09-19", "emitted_count": 0},
        ]
        with (
            patch("jarvis_mrb.desired_state.list_desired_states", return_value=goals),
            patch("jarvis_mrb.agency_plan.current_plan", side_effect=lambda goal_id, **_: plans.get(goal_id)),
            patch("jarvis_mrb.agency_attention.list_events", return_value=events),
            patch("jarvis_mrb.agency_runtime.get_mode", return_value="monitor"),
        ):
            response = build_command_view(goal_limit=1)

        self.assertEqual(response["mode"], "monitor")
        self.assertEqual(response["source"], "persisted_agency")
        self.assertTrue(response["read_only"])
        self.assertEqual(response["total_goals"], 2)
        self.assertEqual(response["active_goals"], 2)
        self.assertEqual(len(response["goals"]), 1)
        self.assertEqual(response["goals"][0]["title"], "Prepare trip")
        self.assertEqual(response["goals"][0]["verified_steps"], 1)
        self.assertEqual(response["goals"][0]["next_step"]["tool"], "web.search")
        self.assertEqual(response["pending_approval_count"], 1)
        self.assertEqual(response["pending_approvals"][0]["goal"], "Later goal")
        self.assertEqual(len(response["recent_alerts"]), 1)
        self.assertNotIn("DO NOT EXPOSE", str(response))
        self.assertNotIn("arguments", str(response))

    def test_empty_state_is_honest(self) -> None:
        with (
            patch("jarvis_mrb.desired_state.list_desired_states", return_value=[]),
            patch("jarvis_mrb.agency_attention.list_events", return_value=[]),
            patch("jarvis_mrb.agency_runtime.get_mode", return_value="off"),
        ):
            response = build_command_view()
        self.assertEqual(response["active_goals"], 0)
        self.assertEqual(response["pending_approval_count"], 0)
        self.assertEqual(response["goals"], [])
        self.assertEqual(response["recent_alerts"], [])
        self.assertEqual(response["mode"], "off")


if __name__ == "__main__":
    unittest.main()
