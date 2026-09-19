from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jarvis_mrb.agent as agent
import jarvis_mrb.agency_plan as agency_plan
import jarvis_mrb.agency_runtime as agency_runtime
import jarvis_mrb.desired_state as desired_state
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_verification as world_verification
from jarvis_mrb.tool_audit import current_agency_step_id


class AgencyPlanTests(unittest.TestCase):
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
        permissions.set_policy("external_write", "confirm")
        agent._PENDING_ACTION = None
        with agency_plan._ACTIVE_EXECUTIONS_LOCK:
            agency_plan._ACTIVE_EXECUTIONS.clear()

        world_model.status()
        world_executive.status()
        desired_state.status()
        agency_plan.status()
        agency_runtime.status()
        agency_runtime.set_mode("active")
        world_verification.status()

    def tearDown(self) -> None:
        agent._PENDING_ACTION = None
        with agency_plan._ACTIVE_EXECUTIONS_LOCK:
            agency_plan._ACTIVE_EXECUTIONS.clear()
        self.temp.cleanup()

    def _state_for_project(self, name: str = "Project Agency") -> tuple[str, str]:
        entity_id = world_model.ensure_entity("project", name)
        state = desired_state.create_desired_state(
            f"{name} ready",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "ready", "value": True}],
            authority={"agency_enabled": True},
            source_kind="test",
            source_ref=f"test:{name}",
        )
        return entity_id, str(state["id"])

    def test_agent_result_preserves_structured_provider_data(self) -> None:
        provider = SimpleNamespace(
            ok=True,
            message="Created external object.",
            data={"event_id": "evt-123", "message_id": "msg-123"},
        )
        reply = agent._result(provider)
        self.assertTrue(reply.ok)
        self.assertEqual(reply.data, provider.data)

    def test_pending_approval_description_redacts_sensitive_email_body(self) -> None:
        item = {
            "id": "agency-step:redaction-email",
            "tool": "gmail.send",
            "resolved_arguments": {
                "recipient": "counsel@example.com",
                "subject": "Project Falcon",
                "body": "TOP SECRET BODY VALUE 739184",
            },
        }
        rendered = agency_plan.describe_pending_approval(item)

        self.assertIn("counsel@example.com", rendered)
        self.assertIn("Project Falcon", rendered)
        self.assertIn("body omitted", rendered)
        self.assertNotIn("TOP SECRET BODY VALUE", rendered)
        self.assertNotIn("739184", rendered)

    def test_custom_run_approval_discloses_hosts_and_field_names_but_not_values(self) -> None:
        item = {
            "id": "agency-step:custom-redaction",
            "tool": "custom.run",
            "resolved_arguments": {
                "name": "private_weather",
                "arguments": {
                    "city": "Pasadena",
                    "secret_note": "DO NOT LEAK THIS VALUE 8842",
                },
            },
        }
        with patch(
            "jarvis_mrb.custom_tools.list_tools",
            return_value=[
                {
                    "name": "private_weather",
                    "enabled": True,
                    "risk": "read",
                    "allowed_hosts": ["weather.example.com"],
                }
            ],
        ):
            rendered = agency_plan.describe_pending_approval(item)

        self.assertIn("private_weather", rendered)
        self.assertIn("weather.example.com", rendered)
        self.assertIn("city", rendered)
        self.assertIn("secret_note", rendered)
        self.assertIn("values omitted", rendered)
        self.assertNotIn("Pasadena", rendered)
        self.assertNotIn("DO NOT LEAK THIS VALUE", rendered)
        self.assertNotIn("8842", rendered)

    def test_pending_approval_display_id_does_not_depend_on_hidden_payload(self) -> None:
        first = {
            "id": "agency-step:redaction-stable",
            "tool": "gmail.send",
            "resolved_arguments": {
                "recipient": "counsel@example.com",
                "subject": "Project Falcon",
                "body": "secret one",
            },
        }
        second = {
            **first,
            "resolved_arguments": {
                **first["resolved_arguments"],
                "body": "secret two",
            },
        }

        first_text = agency_plan.describe_pending_approval(first)
        second_text = agency_plan.describe_pending_approval(second)
        first_id = first_text.rsplit("action ", 1)[1]
        second_id = second_text.rsplit("action ", 1)[1]
        self.assertEqual(first_id, second_id)
        self.assertNotIn("secret one", first_text)
        self.assertNotIn("secret two", second_text)

    def test_generic_pending_approval_description_exposes_names_not_values(self) -> None:
        item = {
            "id": "agency-step:redaction-generic",
            "tool": "unknown.protected",
            "resolved_arguments": {
                "token": "SECRET-TOKEN-123",
                "destination": "Sensitive Destination",
            },
        }
        rendered = agency_plan.describe_pending_approval(item)

        self.assertIn("destination", rendered)
        self.assertIn("token", rendered)
        self.assertNotIn("SECRET-TOKEN-123", rendered)
        self.assertNotIn("Sensitive Destination", rendered)

    def test_permission_policy_change_requires_security_confirmation(self) -> None:
        self.assertEqual(permissions.decide("agency.enable").risk, "security")
        self.assertTrue(permissions.decide("permissions.set").needs_confirmation)

        staged = agent.execute_tool(
            "permissions.set",
            {"risk": "security", "mode": "auto"},
        )
        self.assertTrue(staged.ok)
        self.assertIn("Say 'confirm'", staged.message)
        self.assertTrue(permissions.decide("agency.enable").needs_confirmation)

        confirmed = agent._confirm_pending()
        self.assertTrue(confirmed.ok)
        self.assertFalse(permissions.decide("agency.enable").needs_confirmation)

    def test_permission_policy_change_cannot_use_naked_bypass(self) -> None:
        reply = agent.execute_tool(
            "permissions.set",
            {"risk": "security", "mode": "auto"},
            bypass_confirmation=True,
        )
        self.assertFalse(reply.ok)
        self.assertTrue(permissions.decide("agency.enable").needs_confirmation)

    def test_naked_confirmation_bypass_is_rejected(self) -> None:
        args = {
            "summary": "Naked bypass",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        with patch.object(
            agent,
            "_execute_unchecked",
            return_value=agent.AgentReply(True, "unexpected execution"),
        ) as unchecked:
            reply = agent.execute_tool(
                "calendar.create",
                args,
                bypass_confirmation=True,
            )

        self.assertFalse(reply.ok)
        self.assertIn("no matching persisted confirmation authority", reply.message)
        unchecked.assert_not_called()

    def test_staged_user_confirmation_executes_only_exact_unchanged_action(self) -> None:
        args = {
            "summary": "Exact user confirmation",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        with patch.object(
            agent,
            "_execute_unchecked",
            return_value=agent.AgentReply(True, "executed exact action"),
        ) as unchecked:
            staged = agent.execute_tool("calendar.create", args)
            self.assertTrue(staged.ok)
            self.assertIn("Say 'confirm'", staged.message)

            confirmed = agent._confirm_pending()

        self.assertTrue(confirmed.ok)
        self.assertEqual(confirmed.message, "executed exact action")
        unchecked.assert_called_once_with("calendar.create", args)
        self.assertIsNone(agent._PENDING_ACTION)

    def test_second_protected_action_cannot_replace_pending_confirmation(self) -> None:
        first_args = {
            "summary": "First pending action",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        second_args = {
            "summary": "Second pending action",
            "start": "2030-01-01T10:00:00-08:00",
            "end": "2030-01-01T10:30:00-08:00",
        }

        first = agent.execute_tool("calendar.create", first_args)
        second = agent.execute_tool("calendar.create", second_args)

        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        self.assertIn("already awaiting confirmation", second.message)
        self.assertIsNotNone(agent._PENDING_ACTION)
        assert agent._PENDING_ACTION is not None
        pending_tool, pending_args, pending_key = agent._PENDING_ACTION
        self.assertEqual(pending_tool, "calendar.create")
        self.assertEqual(pending_args, first_args)
        self.assertEqual(
            pending_key,
            agent._confirmation_action_key("calendar.create", first_args),
        )

    def test_repeated_identical_protected_action_deduplicates_without_replacing_pending(self) -> None:
        args = {
            "summary": "Same pending action",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        first = agent.execute_tool("calendar.create", args)
        pending_before = agent._PENDING_ACTION
        repeated = agent.execute_tool("calendar.create", dict(args))

        self.assertTrue(first.ok)
        self.assertTrue(repeated.ok)
        self.assertEqual(agent._PENDING_ACTION, pending_before)

    def test_mutated_staged_user_confirmation_is_cancelled(self) -> None:
        args = {
            "summary": "Original pending action",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        staged = agent.execute_tool("calendar.create", args)
        self.assertTrue(staged.ok)
        self.assertIsNotNone(agent._PENDING_ACTION)
        assert agent._PENDING_ACTION is not None
        tool, stored_args, stored_key = agent._PENDING_ACTION
        stored_args["summary"] = "Tampered after prompt"
        agent._PENDING_ACTION = (tool, stored_args, stored_key)

        with patch.object(
            agent,
            "_execute_unchecked",
            return_value=agent.AgentReply(True, "must not execute"),
        ) as unchecked:
            confirmed = agent._confirm_pending()

        self.assertFalse(confirmed.ok)
        self.assertIn("changed after confirmation was requested", confirmed.message)
        unchecked.assert_not_called()
        self.assertIsNone(agent._PENDING_ACTION)

    def test_agency_approval_capability_authorizes_only_exact_persisted_action_once(self) -> None:
        _, state_id = self._state_for_project("Project Exact Approval")
        args = {
            "summary": "Exact Agency approval",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        plan = agency_plan.create_plan(
            state_id,
            [{"id": "write", "tool": "calendar.create", "arguments": args}],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        step_id = str(waiting["steps"][0]["id"])

        # A persisted awaiting-approval step is not itself confirmation authority.
        from jarvis_mrb.tool_audit import agency_step_context
        with (
            agency_step_context(step_id),
            patch.object(
                agent,
                "_execute_unchecked",
                return_value=agent.AgentReply(True, "must not execute yet"),
            ) as unchecked_before,
        ):
            premature = agent.execute_tool(
                "calendar.create",
                args,
                bypass_confirmation=True,
            )
        self.assertFalse(premature.ok)
        unchecked_before.assert_not_called()

        exact_reply: agent.AgentReply | None = None
        tampered_reply: agent.AgentReply | None = None

        def approved_executor(
            tool: str,
            resolved: dict,
            *,
            bypass_confirmation: bool = False,
        ) -> agent.AgentReply:
            nonlocal exact_reply, tampered_reply
            self.assertTrue(bypass_confirmation)
            exact_reply = agent.execute_tool(
                tool,
                resolved,
                bypass_confirmation=True,
            )
            tampered = dict(resolved)
            tampered["summary"] = "Different unapproved action"
            tampered_reply = agent.execute_tool(
                tool,
                tampered,
                bypass_confirmation=True,
            )
            assert exact_reply is not None
            return exact_reply

        with patch.object(
            agent,
            "_execute_unchecked",
            return_value=agent.AgentReply(True, "exact protected action executed"),
        ) as unchecked:
            result = agency_plan.approve_step(
                plan["id"],
                step_id,
                approved_executor,
            )

        self.assertIsNotNone(exact_reply)
        self.assertTrue(exact_reply.ok)
        self.assertIsNotNone(tampered_reply)
        self.assertFalse(tampered_reply.ok)
        self.assertIn(
            "no matching persisted confirmation authority",
            tampered_reply.message,
        )
        unchecked.assert_called_once_with("calendar.create", args)

        # This fake executor did not produce a durable external verification, so
        # the plan correctly fails outcome verification; confirmation was still
        # consumed and cannot be replayed.
        self.assertEqual(result["status"], "needs_replan")
        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertEqual(persisted["steps"][0]["approval_digest"], "")

        with (
            agency_step_context(step_id),
            patch.object(
                agent,
                "_execute_unchecked",
                return_value=agent.AgentReply(True, "must not replay"),
            ) as replay_unchecked,
        ):
            replay = agent.execute_tool(
                "calendar.create",
                args,
                bypass_confirmation=True,
            )
        self.assertFalse(replay.ok)
        replay_unchecked.assert_not_called()

    def test_concurrent_execute_next_claims_automatic_step_exactly_once(self) -> None:
        _, state_id = self._state_for_project("Project Atomic Automatic Claim")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "observe",
                    "tool": "knowledge.search",
                    "arguments": {"query": "Project Atomic Automatic Claim"},
                }
            ],
        )
        entered = threading.Event()
        release = threading.Event()
        calls: list[str] = []
        calls_lock = threading.Lock()

        def executor(tool: str, _args: dict, **_kwargs: object) -> SimpleNamespace:
            with calls_lock:
                calls.append(tool)
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return SimpleNamespace(ok=True, message="single read result")

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(agency_plan.execute_next, plan["id"], executor)
            self.assertTrue(entered.wait(timeout=5))
            second = pool.submit(agency_plan.execute_next, plan["id"], executor)
            second_result = second.result(timeout=5)

            during = agency_plan.get_plan(plan["id"], include_steps=True)
            self.assertIsNotNone(during)
            assert during is not None
            self.assertEqual(during["steps"][0]["status"], "executing")
            self.assertEqual(during["steps"][0]["attempt_count"], 1)
            self.assertEqual(calls, ["knowledge.search"])

            release.set()
            first_result = first.result(timeout=5)

        self.assertEqual(calls, ["knowledge.search"])
        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted["steps"][0]["attempt_count"], 1)
        self.assertEqual(persisted["steps"][0]["status"], "verified")
        self.assertIn(second_result["status"], {"active", "needs_replan"})
        self.assertEqual(first_result["status"], "needs_replan")

    def test_concurrent_approval_cannot_invoke_protected_step_twice(self) -> None:
        _, state_id = self._state_for_project("Project Atomic Protected Claim")
        args = {
            "summary": "Atomic approved write",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        plan = agency_plan.create_plan(
            state_id,
            [{"id": "write", "tool": "calendar.create", "arguments": args}],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        step_id = str(waiting["steps"][0]["id"])
        entered = threading.Event()
        release = threading.Event()
        calls: list[str] = []
        calls_lock = threading.Lock()

        def executor(
            tool: str,
            _args: dict,
            *,
            bypass_confirmation: bool = False,
        ) -> SimpleNamespace:
            self.assertTrue(bypass_confirmation)
            with calls_lock:
                calls.append(tool)
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            return SimpleNamespace(ok=True, message="single protected invocation")

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                agency_plan.approve_step,
                plan["id"],
                step_id,
                executor,
            )
            self.assertTrue(entered.wait(timeout=5))
            second = pool.submit(
                agency_plan.approve_step,
                plan["id"],
                step_id,
                executor,
            )
            with self.assertRaises(ValueError):
                second.result(timeout=5)

            during = agency_plan.get_plan(plan["id"], include_steps=True)
            self.assertIsNotNone(during)
            assert during is not None
            self.assertEqual(during["steps"][0]["status"], "executing")
            self.assertEqual(during["steps"][0]["attempt_count"], 1)
            self.assertEqual(calls, ["calendar.create"])

            release.set()
            first.result(timeout=5)

        self.assertEqual(calls, ["calendar.create"])
        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted["steps"][0]["attempt_count"], 1)
        self.assertEqual(persisted["steps"][0]["approval_digest"], "")

    def test_interrupted_protected_execution_is_never_replayed_automatically(self) -> None:
        _, state_id = self._state_for_project("Project Interrupted Write")
        args = {
            "summary": "Interrupted write",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        plan = agency_plan.create_plan(
            state_id,
            [{"id": "write", "tool": "calendar.create", "arguments": args}],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        step_id = str(waiting["steps"][0]["id"])
        agency_plan._grant_step_approval(step_id, "calendar.create", args)

        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                """
                UPDATE agency_steps
                SET status='executing',attempt_count=attempt_count+1,started_at=?
                WHERE id=?
                """,
                ("2030-01-01T09:00:00-08:00", step_id),
            )
            conn.commit()
        finally:
            conn.close()

        recovered = agency_plan.reconcile_plan(plan["id"])
        self.assertEqual(recovered["status"], "needs_replan")
        step = recovered["steps"][0]
        self.assertEqual(step["status"], "failed")
        self.assertEqual(step["approval_digest"], "")
        self.assertIn("automatic replay is forbidden", step["blocked_reason"])
        self.assertIsNone(agency_plan.next_ready_step(plan["id"]))

        from jarvis_mrb.tool_audit import agency_step_context
        with (
            agency_step_context(step_id),
            patch.object(
                agent,
                "_execute_unchecked",
                return_value=agent.AgentReply(True, "must not replay"),
            ) as unchecked,
        ):
            replay = agent.execute_tool(
                "calendar.create",
                args,
                bypass_confirmation=True,
            )
        self.assertFalse(replay.ok)
        unchecked.assert_not_called()

    def test_bare_confirm_does_not_execute_pending_agency_action(self) -> None:
        _, state_id = self._state_for_project("Project Explicit Confirm")
        args = {
            "summary": "Bare confirm must not run",
            "start": "2030-01-01T09:00:00-08:00",
            "end": "2030-01-01T09:30:00-08:00",
        }
        plan = agency_plan.create_plan(
            state_id,
            [{"id": "write", "tool": "calendar.create", "arguments": args}],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        self.assertEqual(waiting["status"], "awaiting_approval")

        with patch.object(
            agent,
            "_execute_unchecked",
            return_value=agent.AgentReply(True, "must not execute"),
        ) as unchecked:
            reply = agent._confirm_pending()

        self.assertFalse(reply.ok)
        self.assertIn("approve agency <goal>", reply.message)
        self.assertIn("Bare confirm must not run", reply.message)
        unchecked.assert_not_called()
        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertEqual(persisted["status"], "awaiting_approval")
        self.assertEqual(persisted["steps"][0]["status"], "awaiting_approval")

    def test_bare_cancel_does_not_deny_pending_agency_action(self) -> None:
        _, state_id = self._state_for_project("Project Explicit Denial")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Bare cancel must not deny",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        self.assertEqual(waiting["status"], "awaiting_approval")

        reply = agent._cancel_pending()

        self.assertFalse(reply.ok)
        self.assertIn("deny agency <goal>", reply.message)
        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertEqual(persisted["status"], "awaiting_approval")
        self.assertEqual(persisted["steps"][0]["status"], "awaiting_approval")

    def test_pausing_goal_after_approval_is_staged_prevents_execution(self) -> None:
        _, state_id = self._state_for_project("Project Revoke Goal")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Should not run",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        step = waiting["steps"][0]
        self.assertEqual(step["status"], "awaiting_approval")

        desired_state.update_authority(state_id, {"agency_enabled": False})
        desired_state.set_state(state_id, "paused")
        calls: list[str] = []
        with self.assertRaises(PermissionError):
            agency_plan.approve_step(
                plan["id"],
                step["id"],
                lambda tool, args, **kwargs: calls.append(tool) or SimpleNamespace(ok=True, message="unexpected"),
            )

        self.assertEqual(calls, [])
        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertEqual(persisted["status"], "awaiting_approval")
        self.assertEqual(persisted["steps"][0]["status"], "awaiting_approval")

    def test_global_mode_revocation_prevents_pending_approval_execution(self) -> None:
        _, state_id = self._state_for_project("Project Revoke Global")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Should not run globally",
                        "start": "2030-01-01T10:00:00-08:00",
                        "end": "2030-01-01T10:30:00-08:00",
                    },
                }
            ],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        step = waiting["steps"][0]
        agency_runtime.set_mode("off")

        calls: list[str] = []
        with self.assertRaises(PermissionError):
            agency_plan.approve_step(
                plan["id"],
                step["id"],
                lambda tool, args, **kwargs: calls.append(tool) or SimpleNamespace(ok=True, message="unexpected"),
            )

        self.assertEqual(calls, [])
        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertEqual(persisted["status"], "awaiting_approval")
        self.assertEqual(persisted["steps"][0]["status"], "awaiting_approval")

    def test_persisted_plan_and_step_specification_cannot_be_mutated_in_place(self) -> None:
        _, state_id = self._state_for_project("Project Immutable Spec")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Original approved target",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        step_id = str(plan["steps"][0]["id"])

        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE agency_steps SET arguments_json=? WHERE id=?",
                    (
                        json.dumps(
                            {
                                "summary": "Substituted target",
                                "start": "2030-01-01T11:00:00-08:00",
                                "end": "2030-01-01T11:30:00-08:00",
                            },
                            sort_keys=True,
                        ),
                        step_id,
                    ),
                )
            conn.rollback()
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE agency_steps SET tool='gmail.send' WHERE id=?",
                    (step_id,),
                )
            conn.rollback()
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE agency_plans SET relevance_hash='tampered' WHERE id=?",
                    (plan["id"],),
                )
        finally:
            conn.close()

        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertEqual(persisted["steps"][0]["tool"], "calendar.create")
        self.assertEqual(
            persisted["steps"][0]["arguments"]["summary"],
            "Original approved target",
        )

    def test_plan_persists_steps_and_dependencies(self) -> None:
        _, state_id = self._state_for_project()
        plan = agency_plan.create_plan(
            state_id,
            [
                {"id": "research", "tool": "knowledge.search", "arguments": {"query": "Agency"}},
                {
                    "id": "check",
                    "tool": "fact.check",
                    "arguments": {"claim": "Agency ready"},
                    "depends_on": ["research"],
                },
            ],
            summary="Determine whether Agency is ready",
        )

        loaded = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["status"], "active")
        self.assertEqual([step["step_key"] for step in loaded["steps"]], ["research", "check"])
        self.assertEqual(loaded["steps"][1]["depends_on"], [loaded["steps"][0]["id"]])
        self.assertEqual(agency_plan.current_plan(state_id)["id"], plan["id"])

    def test_safe_steps_execute_in_dependency_order_and_close_when_world_converges(self) -> None:
        entity_id, state_id = self._state_for_project("Project Converge")
        plan = agency_plan.create_plan(
            state_id,
            [
                {"id": "observe", "tool": "knowledge.search", "arguments": {"query": "Converge"}},
                {
                    "id": "confirm",
                    "tool": "fact.check",
                    "arguments": {"claim": "Project Converge ready"},
                    "depends_on": ["observe"],
                },
            ],
        )
        calls: list[str] = []

        def executor(tool: str, args: dict, **_: object) -> SimpleNamespace:
            calls.append(tool)
            if tool == "fact.check":
                world_model.assert_belief(entity_id, "ready", value=True)
            return SimpleNamespace(ok=True, message=f"{tool} returned")

        first = agency_plan.execute_next(plan["id"], executor)
        self.assertEqual(calls, ["knowledge.search"])
        self.assertEqual(first["steps"][0]["status"], "verified")
        self.assertEqual(first["steps"][1]["status"], "pending")
        self.assertEqual(first["status"], "active")

        second = agency_plan.execute_next(plan["id"], executor)
        self.assertEqual(calls, ["knowledge.search", "fact.check"])
        self.assertEqual(second["status"], "completed")
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "satisfied")
        self.assertEqual(second["steps"][0]["status"], "verified")
        # The final step may be verified directly or skipped during convergence;
        # either way the desired state, not step count, is the termination authority.
        self.assertIn(second["steps"][1]["status"], {"verified", "skipped"})

    def test_downstream_arguments_resolve_persisted_dependency_outputs(self) -> None:
        _, state_id = self._state_for_project("Project Resolve")
        plan = agency_plan.create_plan(
            state_id,
            [
                {"id": "research", "tool": "knowledge.search", "arguments": {"query": "Resolve"}},
                {
                    "id": "use",
                    "tool": "fact.check",
                    "arguments": {"claim": "Evidence: ${research.message}"},
                    "depends_on": ["research"],
                },
            ],
        )
        observed: list[tuple[str, dict]] = []

        def executor(tool: str, args: dict, **_: object) -> SimpleNamespace:
            observed.append((tool, dict(args)))
            if tool == "knowledge.search":
                return SimpleNamespace(ok=True, message="alpha evidence")
            return SimpleNamespace(ok=True, message="checked")

        agency_plan.execute_next(plan["id"], executor)
        agency_plan.execute_next(plan["id"], executor)

        self.assertEqual(observed[0][0], "knowledge.search")
        self.assertEqual(observed[1][0], "fact.check")
        self.assertEqual(observed[1][1]["claim"], "Evidence: alpha evidence")

    def test_executor_typeerror_after_side_effect_is_not_retried(self) -> None:
        _, state_id = self._state_for_project("Project TypeError")
        plan = agency_plan.create_plan(
            state_id,
            [{"id": "read", "tool": "knowledge.search", "arguments": {"query": "TypeError"}}],
        )
        calls: list[str] = []

        def executor(tool: str, args: dict, **kwargs: object) -> SimpleNamespace:
            calls.append(tool)
            raise TypeError("internal executor bug after observable side effect")

        result = agency_plan.execute_next(plan["id"], executor)

        self.assertEqual(calls, ["knowledge.search"])
        self.assertEqual(result["steps"][0]["status"], "failed")
        self.assertEqual(result["status"], "needs_replan")
        self.assertIn("TypeError", result["steps"][0]["result_summary"])

    def test_approved_execution_rejects_adapter_without_explicit_bypass_support(self) -> None:
        _, state_id = self._state_for_project("Project Strict Approval")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Strict approval",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda tool, args: SimpleNamespace(ok=True, message="must not run"),
        )
        calls: list[str] = []

        def unsafe_adapter(tool: str, args: dict) -> SimpleNamespace:
            calls.append(tool)
            return SimpleNamespace(ok=True, message="unsafe")

        result = agency_plan.approve_step(
            plan["id"],
            waiting["steps"][0]["id"],
            unsafe_adapter,
        )

        self.assertEqual(calls, [])
        self.assertEqual(result["status"], "needs_replan")
        self.assertEqual(result["steps"][0]["status"], "failed")
        self.assertIn("bypass_confirmation", result["steps"][0]["result_summary"])

    def test_confirmed_read_only_custom_adapter_becomes_verified_without_write_verifier(self) -> None:
        _, state_id = self._state_for_project("Project Custom Read")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "custom-read",
                    "tool": "custom.run",
                    "arguments": {
                        "name": "private_weather",
                        "arguments": {"city": "Pasadena"},
                    },
                }
            ],
        )
        with patch(
            "jarvis_mrb.custom_tools.list_tools",
            return_value=[
                {"name": "private_weather", "enabled": True, "risk": "read"}
            ],
        ):
            waiting = agency_plan.execute_next(
                plan["id"],
                lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="must wait"),
            )
            self.assertEqual(waiting["status"], "awaiting_approval")
            approved = agency_plan.approve_step(
                plan["id"],
                waiting["steps"][0]["id"],
                lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="read succeeded"),
            )

        self.assertEqual(approved["steps"][0]["status"], "verified")
        self.assertEqual(approved["steps"][0]["result_summary"], "read succeeded")
        self.assertEqual(approved["status"], "needs_replan")
        self.assertIn("Plan exhausted", approved["last_error"])

    def test_protected_step_waits_for_persistent_approval_without_calling_executor(self) -> None:
        _, state_id = self._state_for_project("Project Approval")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Agency test",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        calls: list[str] = []

        def executor(tool: str, args: dict, **_: object) -> SimpleNamespace:
            calls.append(tool)
            return SimpleNamespace(ok=True, message="unexpected")

        waiting = agency_plan.execute_next(plan["id"], executor)
        self.assertEqual(calls, [])
        self.assertEqual(waiting["status"], "awaiting_approval")
        self.assertEqual(waiting["steps"][0]["status"], "awaiting_approval")

        recovered = agency_plan.pending_approval()
        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(recovered["id"], waiting["steps"][0]["id"])

    def test_denial_rejects_step_that_never_reached_approval_boundary(self) -> None:
        _, state_id = self._state_for_project("Project Invalid Denial")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "read",
                    "tool": "knowledge.search",
                    "arguments": {"query": "Project Invalid Denial"},
                }
            ],
        )
        step_id = str(plan["steps"][0]["id"])

        with self.assertRaisesRegex(
            ValueError,
            "not waiting for approval",
        ):
            agency_plan.deny_step(
                plan["id"],
                step_id,
                reason="This read never crossed a protected approval boundary.",
            )

        persisted = agency_plan.get_plan(plan["id"], include_steps=True)
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted["status"], "active")
        self.assertEqual(persisted["steps"][0]["status"], "pending")

    def test_denial_moves_plan_to_replan_instead_of_losing_goal(self) -> None:
        _, state_id = self._state_for_project("Project Denial")
        plan = agency_plan.create_plan(
            state_id,
            [{"id": "write", "tool": "gmail.send", "arguments": {"recipient": "a@example.com", "body": "test"}}],
        )
        agency_plan.execute_next(plan["id"], lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"))
        denied = agency_plan.deny_pending(reason="No email.")
        self.assertIsNotNone(denied)
        assert denied is not None
        self.assertEqual(denied["status"], "needs_replan")
        self.assertEqual(denied["steps"][0]["status"], "blocked")
        self.assertEqual(desired_state.get_desired_state(state_id)["state"], "active")

    def test_approved_step_correlates_exact_action_verification(self) -> None:
        _, state_id = self._state_for_project("Project Verify")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Agency verification test",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        step_id = str(waiting["steps"][0]["id"])

        def audited_fake(tool: str, args: dict, *, bypass_confirmation: bool = False) -> SimpleNamespace:
            self.assertTrue(bypass_confirmation)
            self.assertEqual(current_agency_step_id(), step_id)
            reply = SimpleNamespace(ok=True, message="Calendar event created.")
            action_event_id = world_model.record_tool_execution(tool, args, ok=True, message=reply.message)
            world_verification.register_execution(
                tool,
                args,
                reply,
                action_event_id=action_event_id,
                agency_step_id=current_agency_step_id(),
            )
            return reply

        resumed = agency_plan.approve_step(plan["id"], step_id, audited_fake)
        self.assertEqual(resumed["status"], "awaiting_verification")
        self.assertEqual(resumed["steps"][0]["status"], "awaiting_verification")
        verification_id = resumed["steps"][0]["verification_id"]
        self.assertTrue(verification_id)

        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute(
                "SELECT agency_step_id,status FROM action_verifications WHERE id=?",
                (verification_id,),
            ).fetchone()
            self.assertEqual(row[0], step_id)
            self.assertEqual(row[1], "pending")
            conn.execute(
                "UPDATE action_verifications SET status='verified',last_evidence='Observed exact event.' WHERE id=?",
                (verification_id,),
            )
            conn.commit()
        finally:
            conn.close()

        reconciled = agency_plan.reconcile_plan(plan["id"])
        self.assertEqual(reconciled["steps"][0]["status"], "verified")
        self.assertEqual(reconciled["status"], "needs_replan")
        self.assertIn("not yet satisfied", reconciled["last_error"])

    def test_relevant_world_change_invalidates_plan_before_consequential_step(self) -> None:
        entity_id, state_id = self._state_for_project("Project Drift")
        world_model.assert_belief(entity_id, "constraint", value="old")
        plan = agency_plan.create_plan(
            state_id,
            [
                {"id": "observe", "tool": "knowledge.search", "arguments": {"query": "Project Drift"}},
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Drift action",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                    "depends_on": ["observe"],
                },
            ],
        )
        calls: list[str] = []

        def executor(tool: str, args: dict, **_: object) -> SimpleNamespace:
            calls.append(tool)
            return SimpleNamespace(ok=True, message="observed")

        first = agency_plan.execute_next(plan["id"], executor)
        self.assertEqual(first["steps"][0]["status"], "verified")
        self.assertEqual(calls, ["knowledge.search"])

        world_model.assert_belief(entity_id, "constraint", value="new")
        stale = agency_plan.execute_next(plan["id"], executor)

        self.assertEqual(calls, ["knowledge.search"])
        self.assertEqual(stale["status"], "needs_replan")
        self.assertIn("Relevant world state changed", stale["last_error"])
        self.assertEqual(stale["steps"][1]["status"], "pending")

    def test_new_external_event_linked_to_goal_invalidates_consequential_plan(self) -> None:
        entity_id, state_id = self._state_for_project("Project Event Drift")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Event drift action",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        self.assertEqual(waiting["status"], "awaiting_approval")

        external_event_id = world_model.record_event(
            "calendar.context_enriched",
            "Project Event Drift timing changed externally.",
            source_kind="calendar_enriched",
            source_ref="event-drift:new",
            evidence="Synthetic external calendar observation.",
            participants=[(entity_id, "subject", 1.0)],
        )

        calls: list[str] = []
        result = agency_plan.approve_step(
            plan["id"],
            waiting["steps"][0]["id"],
            lambda tool, args, **kwargs: calls.append(tool) or SimpleNamespace(ok=True, message="unexpected"),
        )

        self.assertEqual(calls, [])
        self.assertEqual(result["status"], "needs_replan")
        self.assertEqual(result["steps"][0]["status"], "pending")
        self.assertIn("Relevant world state changed", result["last_error"])
        self.assertGreater(result["invalidation_event_id"], 0)

        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            invalidation = conn.execute(
                """
                SELECT payload_json FROM events
                WHERE id=? AND event_type='agency.plan.invalidated'
                """,
                (result["invalidation_event_id"],),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(invalidation)
        payload = json.loads(invalidation["payload_json"])
        self.assertIn(external_event_id, payload["trigger_event_ids"])

        replacement = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "replacement-write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Event drift replacement",
                        "start": "2030-01-01T10:00:00-08:00",
                        "end": "2030-01-01T10:30:00-08:00",
                    },
                }
            ],
        )
        self.assertEqual(replacement["replaces_plan_id"], plan["id"])
        self.assertEqual(
            replacement["replan_cause_event_id"],
            result["invalidation_event_id"],
        )

        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE agency_plans SET replaces_plan_id=? WHERE id=?",
                    ("agency-plan:tampered", replacement["id"]),
                )
        finally:
            conn.close()

    def test_world_change_while_waiting_for_approval_does_not_consume_approval(self) -> None:
        entity_id, state_id = self._state_for_project("Project Approval Drift")
        world_model.assert_belief(entity_id, "window", value="morning")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Approval drift action",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        waiting = agency_plan.execute_next(
            plan["id"],
            lambda *_args, **_kwargs: SimpleNamespace(ok=True, message="unused"),
        )
        step_id = waiting["steps"][0]["id"]
        self.assertEqual(waiting["status"], "awaiting_approval")

        world_model.assert_belief(entity_id, "window", value="afternoon")
        calls: list[str] = []
        result = agency_plan.approve_step(
            plan["id"],
            step_id,
            lambda tool, args, **kwargs: calls.append(tool) or SimpleNamespace(ok=True, message="unexpected"),
        )

        self.assertEqual(calls, [])
        self.assertEqual(result["status"], "needs_replan")
        self.assertEqual(result["steps"][0]["status"], "pending")
        self.assertIn("Relevant world state changed", result["last_error"])

    def test_concurrent_pending_approvals_require_disambiguation(self) -> None:
        _, state_one = self._state_for_project("Project Approval One")
        _, state_two = self._state_for_project("Project Approval Two")
        plan_one = agency_plan.create_plan(
            state_one,
            [
                {
                    "id": "write-one",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Approval One",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
            summary="Handle Project Approval One",
        )
        plan_two = agency_plan.create_plan(
            state_two,
            [
                {
                    "id": "write-two",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Approval Two",
                        "start": "2030-01-01T10:00:00-08:00",
                        "end": "2030-01-01T10:30:00-08:00",
                    },
                }
            ],
            summary="Handle Project Approval Two",
        )

        agency_plan.execute_next(plan_one["id"], lambda *_a, **_k: SimpleNamespace(ok=True, message="unused"))
        agency_plan.execute_next(plan_two["id"], lambda *_a, **_k: SimpleNamespace(ok=True, message="unused"))

        pending = agency_plan.list_pending_approvals()
        self.assertEqual(len(pending), 2)
        self.assertIsNone(agency_plan.pending_approval())

        one = agency_plan.matching_pending_approval("Project Approval One")
        two = agency_plan.matching_pending_approval("Approval Two")
        self.assertEqual(one["plan_id"], plan_one["id"])
        self.assertEqual(two["plan_id"], plan_two["id"])

        with self.assertRaises(ValueError):
            agency_plan.matching_pending_approval("calendar.create")

    def test_pending_approval_cannot_be_selected_by_action_arguments(self) -> None:
        _, state_id = self._state_for_project("Project Goal Identity Only")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "send",
                    "tool": "gmail.send",
                    "arguments": {
                        "recipient": "unique-recipient@example.com",
                        "subject": "Sensitive approval text",
                        "body": "Do not use these arguments as goal selectors.",
                    },
                }
            ],
            summary="Handle Project Goal Identity Only",
        )
        agency_plan.execute_next(
            plan["id"],
            lambda *_a, **_k: SimpleNamespace(ok=True, message="unused"),
        )

        matched = agency_plan.matching_pending_approval("Goal Identity Only")
        self.assertEqual(matched["plan_id"], plan["id"])

        with self.assertRaises(ValueError):
            agency_plan.matching_pending_approval("unique-recipient@example.com")
        with self.assertRaises(ValueError):
            agency_plan.matching_pending_approval("Sensitive approval text")
        with self.assertRaises(ValueError):
            agency_plan.matching_pending_approval("gmail.send")

    def test_targeted_denial_changes_only_selected_pending_plan(self) -> None:
        _, state_one = self._state_for_project("Project Deny One")
        _, state_two = self._state_for_project("Project Deny Two")
        plan_one = agency_plan.create_plan(
            state_one,
            [{"id": "one", "tool": "gmail.send", "arguments": {"recipient": "a@example.com", "body": "one"}}],
            summary="Project Deny One",
        )
        plan_two = agency_plan.create_plan(
            state_two,
            [{"id": "two", "tool": "gmail.send", "arguments": {"recipient": "b@example.com", "body": "two"}}],
            summary="Project Deny Two",
        )
        agency_plan.execute_next(plan_one["id"], lambda *_a, **_k: SimpleNamespace(ok=True, message="unused"))
        agency_plan.execute_next(plan_two["id"], lambda *_a, **_k: SimpleNamespace(ok=True, message="unused"))

        denied = agency_plan.deny_matching("Project Deny One", reason="No.")
        untouched = agency_plan.get_plan(plan_two["id"], include_steps=True)

        self.assertEqual(denied["status"], "needs_replan")
        self.assertEqual(denied["steps"][0]["status"], "blocked")
        self.assertEqual(untouched["status"], "awaiting_approval")
        self.assertEqual(untouched["steps"][0]["status"], "awaiting_approval")

    def test_verification_event_carries_agency_desired_state_context(self) -> None:
        _, state_id = self._state_for_project("Project Verification Context")
        plan = agency_plan.create_plan(
            state_id,
            [
                {
                    "id": "write",
                    "tool": "calendar.create",
                    "arguments": {
                        "summary": "Verification context action",
                        "start": "2030-01-01T09:00:00-08:00",
                        "end": "2030-01-01T09:30:00-08:00",
                    },
                }
            ],
        )
        step_id = plan["steps"][0]["id"]
        action_event_id = world_model.record_tool_execution(
            "calendar.create",
            {"summary": "Verification context action"},
            ok=True,
            message="accepted",
        )

        event_id = world_verification._record_world_transition(
            "verification:context-test",
            status="verified",
            tool="calendar.create",
            evidence="Independent calendar read-back matched.",
            action_event_id=action_event_id,
            executive_decision_id="",
            agency_step_id=step_id,
        )
        self.assertIsNotNone(event_id)

        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT summary,payload_json,source_kind FROM events WHERE id=?",
                (event_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIn("Project Verification Context ready", row["summary"])
        payload = json.loads(row["payload_json"])
        self.assertEqual(payload["desired_state_id"], state_id)
        self.assertEqual(payload["agency_step_id"], step_id)
        self.assertEqual(row["source_kind"], "jarvis_verifier")

    def test_new_generation_supersedes_old_plan_without_destroying_history(self) -> None:
        _, state_id = self._state_for_project("Project Replan")
        first = agency_plan.create_plan(
            state_id,
            [{"id": "a", "tool": "knowledge.search", "arguments": {"query": "old"}}],
            summary="Old plan",
        )
        second = agency_plan.create_plan(
            state_id,
            [{"id": "b", "tool": "knowledge.search", "arguments": {"query": "new"}}],
            summary="New plan",
        )
        old = agency_plan.get_plan(first["id"])
        self.assertEqual(old["status"], "superseded")
        self.assertEqual(second["generation"], first["generation"] + 1)
        self.assertEqual(len(agency_plan.list_plans(desired_state_id=state_id)), 2)


if __name__ == "__main__":
    unittest.main()
