from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb.workflow_engine import _ALLOWED_NODE_TOOLS, _validate_plan, execute_workflow


class AgencyWorkflowContractTests(unittest.TestCase):
    def test_parallel_deliberation_is_available_inside_autonomous_dag(self) -> None:
        self.assertIn("agency.deliberate", _ALLOWED_NODE_TOOLS)
        plan = {
            "summary": "Research then deliberate.",
            "nodes": [
                {
                    "id": "research",
                    "tool": "web.search",
                    "arguments": {"query": "current evidence", "num": 5},
                    "depends_on": [],
                },
                {
                    "id": "deliberate",
                    "tool": "agency.deliberate",
                    "arguments": {
                        "question": "Which path is best supported?",
                        "context": "Evidence: ${research.message}",
                    },
                    "depends_on": ["research"],
                },
            ],
            "missing_capability": None,
        }
        _validate_plan(plan)

    def test_explicit_missing_capability_can_replace_fake_node(self) -> None:
        _validate_plan(
            {
                "summary": "Cannot complete with bounded tools.",
                "nodes": [],
                "missing_capability": {
                    "capability": "restaurant.reservation.create",
                    "reason": "No allowed tool can create the required real reservation.",
                },
            }
        )

    def test_empty_workflow_without_capability_gap_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_plan(
                {
                    "summary": "Nothing",
                    "nodes": [],
                    "missing_capability": None,
                }
            )

    def test_direct_workflow_reports_missing_capability_as_blocked(self) -> None:
        plan = {
            "summary": "Blocked",
            "nodes": [],
            "missing_capability": {
                "capability": "restaurant.reservation.create",
                "reason": "No bounded tool can create the reservation.",
            },
        }
        calls: list[str] = []
        with patch("jarvis_mrb.workflow_engine.plan_workflow", return_value=plan):
            result = execute_workflow(
                "Make reservation",
                executor=lambda tool, args: calls.append(tool),
            )
        self.assertFalse(result.ok)
        self.assertEqual(calls, [])
        self.assertIn("missing capability restaurant.reservation.create", result.message)

    def test_missing_capability_requires_reason(self) -> None:
        with self.assertRaises(ValueError):
            _validate_plan(
                {
                    "summary": "Missing",
                    "nodes": [],
                    "missing_capability": {
                        "capability": "something.new",
                        "reason": "",
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
