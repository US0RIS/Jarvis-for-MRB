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

    def test_agency_runtime_emits_at_most_one_new_approval_per_cycle_and_rolls_forward(self) -> None:
        report = {
            "results": [
                {
                    "desired_state_id": "ds:one",
                    "status": "awaiting_approval",
                    "plan": {
                        "id": "plan:one",
                        "steps": [
                            {
                                "id": "step:one",
                                "status": "awaiting_approval",
                                "tool": "calendar.create",
                            }
                        ],
                    },
                },
                {
                    "desired_state_id": "ds:two",
                    "status": "awaiting_approval",
                    "plan": {
                        "id": "plan:two",
                        "steps": [
                            {
                                "id": "step:two",
                                "status": "awaiting_approval",
                                "tool": "gmail.send",
                            }
                        ],
                    },
                },
            ]
        }
        states = {
            "ds:one": {"title": "First goal"},
            "ds:two": {"title": "Second goal"},
        }
        emitted_keys: set[str] = set()
        calls: list[tuple[str, bool, bool]] = []

        def fake_consider(**kwargs: object) -> dict:
            key = str(kwargs["dedup_key"])
            allow_emit = bool(kwargs.get("allow_emit", True))
            duplicate = key in emitted_keys
            emitted = bool(allow_emit and not duplicate)
            if emitted:
                emitted_keys.add(key)
            calls.append((key, allow_emit, emitted))
            return {
                "decision": "interrupt",
                "emitted": emitted,
                "duplicate": duplicate,
                "suppressed": bool(not allow_emit),
            }

        with (
            patch("jarvis_mrb.agency_runtime.tick_all", return_value=report),
            patch("jarvis_mrb.desired_state.get_desired_state", side_effect=lambda state_id: states[state_id]),
            patch("jarvis_mrb.agency_attention.consider", side_effect=fake_consider),
        ):
            proactive_monitor._check_agency_runtime()
            first_cycle = list(calls)
            calls.clear()
            proactive_monitor._check_agency_runtime()
            second_cycle = list(calls)

        self.assertEqual(
            [(allow, emitted) for _key, allow, emitted in first_cycle],
            [(True, True), (False, False)],
        )
        self.assertEqual(
            [(allow, emitted) for _key, allow, emitted in second_cycle],
            [(True, False), (True, True)],
        )
        self.assertEqual(len(emitted_keys), 2)

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
