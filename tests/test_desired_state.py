from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.desired_state as desired_state
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.proactive_monitor as proactive_monitor
import jarvis_mrb.world_model as world_model


class DesiredStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"

        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        world_executive.DB_PATH = self.db
        desired_state.DB_PATH = self.db

        world_model.status()
        world_executive.status()
        desired_state.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_belief_criterion_converges_and_reopens_on_drift(self) -> None:
        entity_id = world_model.ensure_entity(
            "project",
            "Project Atlas",
            external_namespace="test_project",
            external_id="atlas",
        )
        state = desired_state.create_desired_state(
            "Project Atlas is approved",
            [
                {
                    "kind": "belief_equals",
                    "entity_id": entity_id,
                    "predicate": "approval_status",
                    "value": "approved",
                }
            ],
            source_kind="test",
            source_ref="atlas-approval",
        )

        first = desired_state.evaluate_desired_state(state["id"])
        self.assertFalse(first["satisfied"])
        self.assertEqual(first["state"], "active")
        self.assertEqual(len(first["missing"]), 1)

        world_model.assert_belief(entity_id, "approval_status", value="approved")
        converged = desired_state.evaluate_desired_state(state["id"])
        self.assertTrue(converged["satisfied"])
        self.assertEqual(converged["state"], "satisfied")

        world_model.assert_belief(entity_id, "approval_status", value="rejected")
        drifted = desired_state.evaluate_desired_state(state["id"])
        self.assertFalse(drifted["satisfied"])
        self.assertEqual(drifted["state"], "active")
        self.assertEqual(len(desired_state.evaluations(state["id"])), 3)

    def test_desired_state_persists_full_contract(self) -> None:
        entity_id = world_model.ensure_entity("project", "Project Persist")
        created = desired_state.create_desired_state(
            "Persist the objective",
            [
                {
                    "kind": "belief_in",
                    "entity_id": entity_id,
                    "predicate": "phase",
                    "values": ["done", "complete"],
                }
            ],
            authority={"read": "auto", "external_write": "confirm"},
            priority=91,
            source_kind="user",
            source_ref="conversation:test",
        )

        loaded = desired_state.get_desired_state(created["id"])
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["title"], "Persist the objective")
        self.assertEqual(float(loaded["priority"]), 91.0)
        self.assertEqual(loaded["authority"]["external_write"], "confirm")
        self.assertEqual(loaded["criteria"][0]["kind"], "belief_in")

        listed = desired_state.list_desired_states()
        self.assertEqual([item["id"] for item in listed], [created["id"]])

    def test_commitment_status_is_machine_evaluable(self) -> None:
        commitment_id = world_model.upsert_commitment(
            "atlas-docs",
            owner_name="Daniel Reed",
            action="Send Atlas documents",
            status="pending",
        )
        state = desired_state.create_desired_state(
            "Atlas documents received",
            [
                {
                    "kind": "commitment_status",
                    "commitment_id": commitment_id,
                    "status": "resolved",
                }
            ],
            source_kind="test",
            source_ref="atlas-docs-state",
        )

        self.assertFalse(desired_state.evaluate_desired_state(state["id"])["satisfied"])

        world_model.upsert_commitment(
            "atlas-docs",
            owner_name="Daniel Reed",
            action="Send Atlas documents",
            status="resolved",
        )
        self.assertTrue(desired_state.evaluate_desired_state(state["id"])["satisfied"])

    def test_event_criterion_can_close_a_goal_from_observed_reality(self) -> None:
        state = desired_state.create_desired_state(
            "Deployment completed",
            [{"kind": "event_exists", "event_type": "deployment.completed", "summary_contains": "Atlas"}],
            source_kind="test",
            source_ref="deploy-atlas",
        )
        self.assertFalse(desired_state.evaluate_desired_state(state["id"])["satisfied"])

        world_model.record_event(
            "deployment.completed",
            "Project Atlas deployment completed successfully.",
            source_kind="test_system",
            source_ref="deployment:atlas:1",
            evidence="test event",
        )
        result = desired_state.evaluate_desired_state(state["id"])
        self.assertTrue(result["satisfied"])
        self.assertIsNotNone(result["evidence"][0]["event_id"])

    def test_proactive_loop_reconciles_desired_state_without_user_prompt(self) -> None:
        entity_id = world_model.ensure_entity("project", "Project Ambient")
        state = desired_state.create_desired_state(
            "Ambient project becomes ready",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "ready", "value": True}],
            source_kind="test",
            source_ref="ambient-project",
        )
        self.assertEqual(desired_state.get_desired_state(state["id"])["state"], "active")

        world_model.assert_belief(entity_id, "ready", value=True)
        proactive_monitor._check_desired_states()

        updated = desired_state.get_desired_state(state["id"])
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["state"], "satisfied")

    def test_authority_and_lifecycle_mutations_are_durably_audited(self) -> None:
        entity_id = world_model.ensure_entity("project", "Project Audit")
        state = desired_state.create_desired_state(
            "Project Audit ready",
            [
                {
                    "kind": "belief_equals",
                    "entity_id": entity_id,
                    "predicate": "ready",
                    "value": True,
                }
            ],
            authority={"agency_enabled": False},
            source_kind="test",
            source_ref="audit-project",
        )

        desired_state.update_authority(
            state["id"],
            {"agency_enabled": True, "contract_compiled": True},
        )
        desired_state.set_state(
            state["id"],
            "blocked",
            reason="Waiting for external prerequisite.",
        )

        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            authority_event = conn.execute(
                """
                SELECT payload_json FROM events
                WHERE event_type='desired_state.authority_changed'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            lifecycle_event = conn.execute(
                """
                SELECT payload_json FROM events
                WHERE event_type='desired_state.lifecycle_changed'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()

        self.assertIsNotNone(authority_event)
        self.assertIsNotNone(lifecycle_event)
        authority_payload = json.loads(str(authority_event["payload_json"]))
        lifecycle_payload = json.loads(str(lifecycle_event["payload_json"]))
        self.assertEqual(authority_payload["desired_state_id"], state["id"])
        self.assertIn("agency_enabled", authority_payload["changed_keys"])
        self.assertFalse(authority_payload["previous"]["agency_enabled"])
        self.assertTrue(authority_payload["current"]["agency_enabled"])
        self.assertEqual(lifecycle_payload["state_before"], "active")
        self.assertEqual(lifecycle_payload["state_after"], "blocked")
        self.assertEqual(
            lifecycle_payload["reason_after"],
            "Waiting for external prerequisite.",
        )

    def test_noop_authority_or_lifecycle_update_does_not_emit_duplicate_audit_event(self) -> None:
        entity_id = world_model.ensure_entity("project", "Project Audit Noop")
        state = desired_state.create_desired_state(
            "Project Audit Noop ready",
            [
                {
                    "kind": "belief_equals",
                    "entity_id": entity_id,
                    "predicate": "ready",
                    "value": True,
                }
            ],
            authority={"agency_enabled": False},
            source_kind="test",
            source_ref="audit-project-noop",
        )
        desired_state.update_authority(state["id"], {"agency_enabled": False})
        desired_state.set_state(state["id"], "active")

        with sqlite3.connect(self.db) as conn:
            authority_count = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='desired_state.authority_changed'"
            ).fetchone()[0]
            lifecycle_count = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='desired_state.lifecycle_changed'"
            ).fetchone()[0]
        self.assertEqual(authority_count, 0)
        self.assertEqual(lifecycle_count, 0)

    def test_blocked_and_retired_lifecycle_are_not_overridden_by_evaluation(self) -> None:
        entity_id = world_model.ensure_entity("project", "Project Blocked")
        world_model.assert_belief(entity_id, "ready", value=True)
        state = desired_state.create_desired_state(
            "Blocked project is ready",
            [{"kind": "belief_equals", "entity_id": entity_id, "predicate": "ready", "value": True}],
            source_kind="test",
            source_ref="blocked-project",
        )

        desired_state.set_state(state["id"], "blocked", reason="Missing capability")
        blocked = desired_state.evaluate_desired_state(state["id"])
        self.assertTrue(blocked["satisfied"])
        self.assertEqual(blocked["state"], "blocked")

        desired_state.set_state(state["id"], "retired")
        retired = desired_state.evaluate_desired_state(state["id"])
        self.assertEqual(retired["state"], "retired")
        self.assertEqual(desired_state.list_desired_states(), [])


if __name__ == "__main__":
    unittest.main()
