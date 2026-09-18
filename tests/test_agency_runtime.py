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

    def _make_state(self, name: str, *, agency_enabled: bool = True) -> tuple[str, str]:
        entity_id = world_model.ensure_entity("project", name)
        state = desired_state.create_desired_state(
            f"{name} ready",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "ready", "value": True}],
            authority={"agency_enabled": bool(agency_enabled)},
            source_kind="test",
            source_ref=f"runtime:{name}",
        )
        return entity_id, str(state["id"])

    def test_active_mode_skips_goal_without_per_goal_agency_authority(self) -> None:
        _, state_id = self._make_state("Project No Authority", agency_enabled=False)
        agency_runtime.set_mode("active")
        planner_calls: list[str] = []
        executor_calls: list[str] = []

        report = agency_runtime.tick_all(
            planner=lambda prompt: planner_calls.append(prompt) or {
                "summary": "must not plan",
                "nodes": [{"id": "x", "tool": "knowledge.search", "arguments": {"query": "x"}}],
            },
            executor=lambda tool, args, **kwargs: executor_calls.append(tool) or SimpleNamespace(ok=True, message="must not run"),
        )

        self.assertEqual(report["mode"], "active")
        self.assertEqual(report["desired_states_checked"], 0)
        self.assertEqual(report["actions_executed"], 0)
        self.assertEqual(planner_calls, [])
        self.assertEqual(executor_calls, [])
        self.assertIsNone(agency_plan.current_plan(state_id))

    def test_direct_tick_cannot_bypass_per_goal_agency_authority(self) -> None:
        _, state_id = self._make_state("Project Direct No Authority", agency_enabled=False)
        agency_runtime.set_mode("active")
        planner_calls: list[str] = []
        executor_calls: list[str] = []

        result = agency_runtime.tick_desired_state(
            state_id,
            planner=lambda prompt: planner_calls.append(prompt) or {
                "summary": "must not plan",
                "nodes": [{"id": "x", "tool": "knowledge.search", "arguments": {"query": "x"}}],
            },
            executor=lambda tool, args, **kwargs: executor_calls.append(tool) or SimpleNamespace(ok=True, message="must not run"),
        )

        self.assertEqual(result["status"], "authority_disabled")
        self.assertFalse(result["action_executed"])
        self.assertEqual(planner_calls, [])
        self.assertEqual(executor_calls, [])

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

    def test_satisfied_goal_that_later_drifts_gets_new_plan_generation(self) -> None:
        entity_id, state_id = self._make_state("Project Reopen")
        agency_runtime.set_mode("active")
        plans: list[str] = []

        def planner(prompt: str) -> dict:
            plans.append(prompt)
            return {
                "summary": f"generation {len(plans)}",
                "nodes": [
                    {
                        "id": "observe",
                        "tool": "knowledge.search",
                        "arguments": {"query": "Project Reopen"},
                        "depends_on": [],
                    }
                ],
            }

        def first_executor(tool: str, args: dict, **kwargs: object) -> SimpleNamespace:
            world_model.assert_belief(entity_id, "ready", value=True)
            return SimpleNamespace(ok=True, message="ready observed")

        first = agency_runtime.tick_desired_state(
            state_id,
            executor=first_executor,
            planner=planner,
        )
        self.assertEqual(first["plan"]["status"], "completed")
        first_generation = first["plan"]["generation"]

        world_model.assert_belief(entity_id, "ready", value=False)
        reopened = desired_state.evaluate_desired_state(state_id)
        self.assertEqual(reopened["state"], "active")

        second = agency_runtime.tick_desired_state(
            state_id,
            executor=lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="still not ready"),
            planner=planner,
            allow_action=False,
        )
        self.assertEqual(second["plan"]["generation"], first_generation + 1)
        self.assertEqual(second["plan"]["status"], "active")
        self.assertEqual(len(plans), 2)

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

    def test_tick_all_preserves_priority_but_rotates_second_action_fairly(self) -> None:
        states: list[str] = []
        for name, priority in (
            ("Priority Champion", 100),
            ("Fair One", 10),
            ("Fair Two", 10),
            ("Fair Three", 10),
        ):
            _entity, state_id = self._make_state(name)
            desired_state.update_desired_state(state_id, priority=priority)
            agency_plan.create_plan(
                state_id,
                [{"id": "observe", "tool": "knowledge.search", "arguments": {"query": name}}],
                summary=f"Observe {name}",
            )
            states.append(state_id)

        agency_runtime.set_mode("active")
        executed: list[str] = []

        def executor(tool: str, args: dict, **kwargs: object) -> SimpleNamespace:
            executed.append(str(args.get("query") or ""))
            return SimpleNamespace(ok=True, message="observed")

        first = agency_runtime.tick_all(executor=executor, max_actions=2)
        self.assertEqual(first["actions_executed"], 2)
        self.assertIn("Priority Champion", executed)
        first_fair = next(value for value in executed if value != "Priority Champion")

        # Recreate one ready read step per goal so every goal remains actionable.
        for index, state_id in enumerate(states):
            agency_plan.create_plan(
                state_id,
                [{"id": "observe", "tool": "knowledge.search", "arguments": {"query": ["Priority Champion", "Fair One", "Fair Two", "Fair Three"][index]}}],
                summary="next observation",
            )

        executed.clear()
        second = agency_runtime.tick_all(executor=executor, max_actions=2)
        self.assertEqual(second["actions_executed"], 2)
        self.assertIn("Priority Champion", executed)
        second_fair = next(value for value in executed if value != "Priority Champion")
        self.assertNotEqual(second_fair, first_fair)

    def test_action_attempt_updates_last_action_at_even_outside_tick_all(self) -> None:
        _, state_id = self._make_state("Approved Action Fairness")
        agency_runtime.set_mode("active")
        plan = agency_plan.create_plan(
            state_id,
            [{"id": "observe", "tool": "knowledge.search", "arguments": {"query": "fairness"}}],
        )
        before = agency_runtime._runtime_state(state_id)
        self.assertFalse(before.get("last_action_at"))

        agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="observed"),
        )

        after = agency_runtime._runtime_state(state_id)
        self.assertTrue(after.get("last_action_at"))

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

        activated = agency_runtime.activate_matching(
            "Ship Project Hermes",
            contract_compiler=lambda _prompt: {
                "confidence": 0.95,
                "criteria": [
                    {
                        "kind": "event_match",
                        "terms_all": ["Project Hermes", "completed"],
                        "terms_none": ["not completed", "pending"],
                        "event_types": [],
                        "source_kinds": ["jarvis_verifier"],
                    }
                ],
                "explanation": "A future independently verified event must state Project Hermes is completed.",
            },
        )
        self.assertEqual(activated["state"], "active")
        self.assertTrue(activated["authority"]["contract_compiled"])
        self.assertEqual(activated["criteria"][0]["kind"], "event_match")

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

    def test_blocked_goal_wakes_when_persisted_condition_becomes_true(self) -> None:
        entity_id, state_id = self._make_state("Project Wake")
        desired_state.set_state(state_id, "blocked", reason="Waiting for prerequisite.")
        desired_state.add_wake_watch(
            state_id,
            {"kind": "belief_equals", "entity_id": entity_id, "predicate": "prerequisite", "value": "available"},
        )

        first = desired_state.check_wake_watches()
        self.assertEqual(first["triggered"], 0)
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "blocked")

        world_model.assert_belief(entity_id, "prerequisite", value="available")
        second = desired_state.check_wake_watches()
        self.assertEqual(second["triggered"], 1)
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "active")
        watches = desired_state.list_wake_watches(desired_state_id=state_id)
        self.assertEqual(watches[0]["status"], "triggered")

    def test_user_paused_goal_does_not_wake_automatically(self) -> None:
        entity_id, state_id = self._make_state("Project Pause")
        desired_state.set_state(state_id, "paused")
        desired_state.add_wake_watch(
            state_id,
            {"kind": "belief_equals", "entity_id": entity_id, "predicate": "prerequisite", "value": True},
        )
        world_model.assert_belief(entity_id, "prerequisite", value=True)

        result = desired_state.check_wake_watches()
        self.assertEqual(result["triggered"], 0)
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "paused")

    def test_agency_authority_expansion_is_security_class(self) -> None:
        self.assertEqual(permissions.decide("agency.enable").risk, "security")
        self.assertTrue(permissions.decide("agency.enable").needs_confirmation)
        self.assertEqual(permissions.decide("agency.activate_goal").risk, "security")
        self.assertTrue(permissions.decide("agency.activate_goal").needs_confirmation)
        self.assertEqual(permissions.decide("agency.disable").risk, "local_write")
        self.assertFalse(permissions.decide("agency.disable").needs_confirmation)


if __name__ == "__main__":
    unittest.main()
