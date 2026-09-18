from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import jarvis_mrb.agency_plan as agency_plan
import jarvis_mrb.agency_runtime as agency_runtime
import jarvis_mrb.desired_state as desired_state
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_verification as world_verification


class AgencyRuntimeTests(unittest.TestCase):
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
        world_verification.DB_PATH = self.db

        permissions.APP_DIR = self.base
        permissions.POLICY_PATH = self.base / "permissions.json"

        world_model.status()
        world_executive.status()
        desired_state.status()
        agency_plan.status()
        agency_runtime.status()
        world_verification.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _make_state(self, name: str) -> tuple[str, str]:
        entity_id = world_model.ensure_entity("project", name)
        state = desired_state.create_desired_state(
            f"{name} ready",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "ready", "value": True}],
            source_kind="test",
            source_ref=f"runtime:{name}",
        )
        return entity_id, str(state["id"])

    def test_monitor_mode_neither_plans_nor_executes(self) -> None:
        _, state_id = self._make_state("Project Monitor")
        planner_calls: list[str] = []
        executor_calls: list[str] = []

        result = agency_runtime.tick_all(
            planner=lambda prompt: planner_calls.append(prompt) or {
                "summary": "unused",
                "nodes": [{"id": "n1", "tool": "knowledge.search", "arguments": {"query": "x"}, "depends_on": []}],
            },
            executor=lambda tool, args, **kwargs: executor_calls.append(tool) or SimpleNamespace(ok=True, message="ok"),
        )

        self.assertEqual(result["mode"], "monitor")
        self.assertEqual(planner_calls, [])
        self.assertEqual(executor_calls, [])
        self.assertEqual(agency_plan.current_plan(state_id), None)

    def test_active_mode_plans_executes_and_stops_when_desired_state_converges(self) -> None:
        entity_id, state_id = self._make_state("Project Active")
        agency_runtime.set_mode("active")
        planner_calls: list[str] = []
        executor_calls: list[str] = []

        def planner(prompt: str) -> dict:
            planner_calls.append(prompt)
            return {
                "summary": "Observe and resolve",
                "nodes": [
                    {
                        "id": "n1",
                        "tool": "knowledge.search",
                        "arguments": {"query": "Project Active readiness"},
                        "depends_on": [],
                    }
                ],
            }

        def executor(tool: str, args: dict, **kwargs: object) -> SimpleNamespace:
            executor_calls.append(tool)
            world_model.assert_belief(entity_id, "ready", value=True)
            return SimpleNamespace(ok=True, message="Observed readiness.")

        result = agency_runtime.tick_all(planner=planner, executor=executor, max_actions=2)

        self.assertEqual(result["mode"], "active")
        self.assertEqual(len(planner_calls), 1)
        self.assertEqual(executor_calls, ["knowledge.search"])
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "satisfied")
        plan = agency_plan.current_plan(state_id, include_steps=True)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan["status"], "completed")

    def test_planner_failure_uses_backoff_instead_of_retrying_every_tick(self) -> None:
        _, state_id = self._make_state("Project Backoff")
        agency_runtime.set_mode("active")
        calls = 0

        def planner(_prompt: str) -> dict:
            nonlocal calls
            calls += 1
            raise RuntimeError("model unavailable")

        first = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
            planner=planner,
        )
        second = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
            planner=planner,
        )

        self.assertEqual(calls, 1)
        self.assertFalse(first["action_executed"])
        self.assertFalse(second["action_executed"])
        self.assertEqual(agency_runtime.status()["planner_backoff"][0]["consecutive_planner_failures"], 1)

    def test_identical_failed_replan_blocks_instead_of_looping(self) -> None:
        _, state_id = self._make_state("Project Loop")
        agency_runtime.set_mode("active")

        workflow = {
            "summary": "Same plan",
            "nodes": [
                {
                    "id": "n1",
                    "tool": "knowledge.search",
                    "arguments": {"query": "Project Loop"},
                    "depends_on": [],
                }
            ],
        }

        first = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=False, message="No useful observation."),
            planner=lambda _prompt: workflow,
        )
        self.assertEqual(first["plan"]["status"], "needs_replan")

        second = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=False, message="unused"),
            planner=lambda _prompt: workflow,
        )
        self.assertFalse(second["action_executed"])
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "blocked")
        self.assertIn("same failed plan", desired_state.get_desired_state(state_id)["blocked_reason"])

    def test_existing_goals_are_imported_paused_until_explicit_activation(self) -> None:
        goal_id = world_model.ensure_entity("goal", "Ship Project Hermes")
        world_model.assert_belief(goal_id, "status", value="active")
        world_model.assert_belief(goal_id, "next_action", value="Finish validation")

        result = desired_state.sync_from_intentions()
        self.assertEqual(result["created"], 1)

        states = desired_state.list_desired_states()
        self.assertEqual(len(states), 1)
        state = states[0]
        self.assertEqual(state["state"], "paused")
        self.assertFalse(state["authority"]["agency_enabled"])

        activated = agency_runtime.activate_matching("Ship Project Hermes")
        self.assertEqual(activated["state"], "active")

    def test_goal_completion_closes_imported_desired_state(self) -> None:
        goal_id = world_model.ensure_entity("goal", "Finish Project Iris")
        world_model.assert_belief(goal_id, "status", value="active")
        desired_state.sync_from_intentions()
        state = desired_state.list_desired_states()[0]
        self.assertEqual(state["state"], "paused")

        world_model.assert_belief(goal_id, "status", value="completed")
        desired_state.sync_from_intentions()
        closed = desired_state.get_desired_state(state["id"])
        self.assertEqual(closed["state"], "satisfied")

    def test_agency_authority_expansion_is_security_class(self) -> None:
        self.assertEqual(permissions.decide("agency.enable").risk, "security")
        self.assertTrue(permissions.decide("agency.enable").needs_confirmation)
        self.assertEqual(permissions.decide("agency.activate_goal").risk, "security")
        self.assertTrue(permissions.decide("agency.activate_goal").needs_confirmation)
        self.assertEqual(permissions.decide("agency.disable").risk, "local_write")
        self.assertFalse(permissions.decide("agency.disable").needs_confirmation)


if __name__ == "__main__":
    unittest.main()
