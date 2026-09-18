from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jarvis_mrb.agency_capability as agency_capability
import jarvis_mrb.agency_plan as agency_plan
import jarvis_mrb.agency_runtime as agency_runtime
import jarvis_mrb.desired_state as desired_state
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_model as world_model


class AgencyCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"

        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        desired_state.DB_PATH = self.db
        agency_plan.DB_PATH = self.db
        agency_runtime.DB_PATH = self.db
        agency_capability.DB_PATH = self.db
        permissions.APP_DIR = self.base
        permissions.POLICY_PATH = self.base / "permissions.json"

        world_model.status()
        world_executive.status()
        desired_state.status()
        agency_plan.status()
        agency_runtime.status()
        agency_capability.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _state(self) -> str:
        entity = world_model.ensure_entity("project", "Project Capability")
        state = desired_state.create_desired_state(
            "Project Capability complete",
            [{"kind": "belief_equals", "entity_id": entity, "predicate": "done", "value": True}],
            authority={"agency_enabled": True},
            source_kind="test",
            source_ref="capability-state",
        )
        return str(state["id"])

    def test_gap_is_deduplicated_for_same_desired_state_and_capability(self) -> None:
        state_id = self._state()
        first = agency_capability.record_gap(state_id, "robot.arm", "Missing robot control.")
        second = agency_capability.record_gap(state_id, "robot.arm", "Still missing.")

        self.assertEqual(first["id"], second["id"])
        gaps = agency_capability.list_gaps(desired_state_id=state_id, open_only=True)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["reason"], "Still missing.")

    def test_gap_persists_availability_snapshot_from_time_of_block(self) -> None:
        state_id = self._state()
        gap = agency_capability.record_gap(
            state_id,
            "future.nonexistent.capability",
            "Required for the goal.",
        )
        snapshot = gap["observed_availability"]
        self.assertEqual(snapshot["tool"], "future.nonexistent.capability")
        self.assertFalse(snapshot["known"])
        self.assertFalse(snapshot["available"])
        self.assertFalse(snapshot["authority_blocked"])
        self.assertFalse(snapshot["agency_scope_blocked"])

        loaded = agency_capability.get_gap(gap["id"])
        self.assertEqual(loaded["observed_availability"], snapshot)

    def test_adapter_synthesis_remains_disabled(self) -> None:
        state_id = self._state()
        gap = agency_capability.record_gap(state_id, "weather.private_api", "Need narrow API.")

        with patch(
            "jarvis_mrb.custom_tools.synthesize",
            return_value={"name": "private_weather", "enabled": False, "risk": "read"},
        ):
            result = agency_capability.synthesize_adapter(
                gap["id"],
                name="private_weather",
                description="Read a private weather API.",
                api_spec="GET /weather",
                allowed_hosts=["weather.example.com"],
                risk="read",
            )

        self.assertFalse(result["enabled"])
        self.assertEqual(result["gap"]["status"], "proposed")
        self.assertEqual(result["gap"]["proposed_tool_name"], "private_weather")
        self.assertIn("remains disabled", result["gap"]["resolution"])

    def test_unsupported_planner_tool_blocks_state_and_records_gap(self) -> None:
        state_id = self._state()
        agency_runtime.set_mode("active")

        result = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
            planner=lambda _prompt: (_ for _ in ()).throw(
                ValueError("Workflow requested unsupported tool 'robot.arm'.")
            ),
        )

        self.assertFalse(result["action_executed"])
        state = desired_state.get_desired_state(state_id)
        self.assertEqual(state["state"], "blocked")
        self.assertIn("robot.arm", state["blocked_reason"])

        gaps = agency_capability.list_gaps(desired_state_id=state_id, open_only=True)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["capability"], "robot.arm")

    def test_known_tool_excluded_from_autonomous_workflows_is_scope_boundary_not_missing_capability(self) -> None:
        info = agency_capability.available_tool("meeting.start")
        self.assertTrue(info["known"])
        self.assertFalse(info["available"])
        self.assertFalse(info["implemented_for_agency"])
        self.assertTrue(info["agency_scope_blocked"])
        self.assertFalse(info["authority_blocked"])

    def test_runtime_does_not_record_capability_gap_for_intentionally_excluded_tool(self) -> None:
        state_id = self._state()
        agency_runtime.set_mode("active")

        result = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
            planner=lambda _prompt: (_ for _ in ()).throw(
                ValueError("Workflow requested unsupported tool 'meeting.start'.")
            ),
        )

        self.assertFalse(result["action_executed"])
        state = desired_state.get_desired_state(state_id)
        self.assertEqual(state["state"], "blocked")
        self.assertIn("Agency scope does not permit meeting.start", state["blocked_reason"])
        self.assertEqual(
            agency_capability.list_gaps(desired_state_id=state_id, open_only=True),
            [],
        )

    def test_planner_declared_missing_capability_blocks_and_records_gap(self) -> None:
        state_id = self._state()
        agency_runtime.set_mode("active")

        result = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
            planner=lambda _prompt: {
                "summary": "Cannot finish without a reservation-writing provider.",
                "nodes": [],
                "missing_capability": {
                    "capability": "restaurant.reservation.create",
                    "reason": "The goal requires creating a real reservation and no bounded Agency tool can do so.",
                },
            },
        )

        self.assertFalse(result["action_executed"])
        state = desired_state.get_desired_state(state_id)
        self.assertEqual(state["state"], "blocked")
        self.assertIn("restaurant.reservation.create", state["blocked_reason"])
        gaps = agency_capability.list_gaps(desired_state_id=state_id, open_only=True)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["capability"], "restaurant.reservation.create")

    def test_planner_cannot_declare_available_agency_tool_missing(self) -> None:
        state_id = self._state()
        agency_runtime.set_mode("active")

        result = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
            planner=lambda _prompt: {
                "summary": "Bad declaration",
                "nodes": [],
                "missing_capability": {
                    "capability": "web.search",
                    "reason": "Pretend web search is unavailable.",
                },
            },
        )

        self.assertFalse(result["action_executed"])
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "active")
        self.assertEqual(
            agency_capability.list_gaps(desired_state_id=state_id, open_only=True),
            [],
        )
        runtime = agency_runtime.status()["planner_backoff"]
        self.assertTrue(runtime)
        self.assertIn("declared available Agency tool", runtime[0]["last_error"])

    def test_enabled_custom_adapter_becomes_available_to_agency_through_security_wrapper(self) -> None:
        with patch(
            "jarvis_mrb.custom_tools.list_tools",
            return_value=[
                {
                    "name": "private_weather",
                    "enabled": True,
                    "risk": "read",
                    "description": "Private weather",
                    "allowed_hosts": ["weather.example.com"],
                }
            ],
        ):
            info = agency_capability.available_tool("private_weather")
        self.assertTrue(info["known"])
        self.assertTrue(info["implemented_for_agency"])
        self.assertTrue(info["available"])
        self.assertFalse(info["agency_scope_blocked"])
        self.assertTrue(info["requires_confirmation"])
        self.assertEqual(info["wrapper_tool"], "custom.run")

    def test_enabling_proposed_adapter_reactivates_capability_blocked_goal(self) -> None:
        state_id = self._state()
        gap = agency_capability.record_gap(
            state_id,
            "weather.private_api",
            "Need a narrow private weather API.",
        )
        with patch(
            "jarvis_mrb.custom_tools.synthesize",
            return_value={"name": "private_weather", "enabled": False, "risk": "read"},
        ):
            agency_capability.synthesize_adapter(
                gap["id"],
                name="private_weather",
                description="Read private weather.",
                api_spec="GET /weather",
                allowed_hosts=["weather.example.com"],
                risk="read",
            )
        desired_state.set_state(
            state_id,
            "blocked",
            reason="Missing capability: weather.private_api.",
        )

        with patch(
            "jarvis_mrb.custom_tools.list_tools",
            return_value=[
                {
                    "name": "private_weather",
                    "enabled": True,
                    "risk": "read",
                    "description": "Private weather",
                    "allowed_hosts": ["weather.example.com"],
                }
            ],
        ):
            result = agency_capability.reconcile_gaps()

        self.assertIn(gap["id"], result["resolved"])
        self.assertIn(state_id, result["reactivated"])
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "active")
        self.assertEqual(agency_capability.get_gap(gap["id"])["status"], "resolved")

    def test_known_but_denied_tool_is_authority_gap_not_capability_gap(self) -> None:
        permissions.set_policy("external_write", "deny")
        info = agency_capability.available_tool("gmail.send")
        self.assertTrue(info["known"])
        self.assertFalse(info["available"])
        self.assertTrue(info["implemented_for_agency"])
        self.assertTrue(info["authority_blocked"])
        self.assertFalse(info["agency_scope_blocked"])
        self.assertEqual(info["source"], "builtin")


if __name__ == "__main__":
    unittest.main()
