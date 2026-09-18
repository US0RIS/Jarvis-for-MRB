from __future__ import annotations

import unittest
from unittest.mock import patch

import jarvis_mrb.proactive_monitor as proactive_monitor


class ProactiveAgencyLoopTests(unittest.TestCase):
    def test_disabling_optional_proactive_suggestions_keeps_core_agency_loops_alive(self) -> None:
        calls: list[str] = []

        with (
            patch.object(proactive_monitor, "_proactive_enabled", return_value=False),
            patch.object(
                proactive_monitor,
                "_run_isolated",
                side_effect=lambda name, fn: calls.append(name),
            ),
        ):
            proactive_monitor.check_once()

        self.assertEqual(
            calls,
            [
                "action_verification",
                "desired_state_evaluation",
                "agency_runtime",
            ],
        )

    def test_enabled_proactive_suggestions_add_optional_checks_without_replacing_core(self) -> None:
        calls: list[str] = []

        with (
            patch.object(proactive_monitor, "_proactive_enabled", return_value=True),
            patch.object(
                proactive_monitor,
                "_run_isolated",
                side_effect=lambda name, fn: calls.append(name),
            ),
        ):
            proactive_monitor.check_once()

        self.assertEqual(
            calls,
            [
                "proactive_calendar",
                "proactive_urgent_mail",
                "action_verification",
                "desired_state_evaluation",
                "agency_runtime",
            ],
        )


if __name__ == "__main__":
    unittest.main()
