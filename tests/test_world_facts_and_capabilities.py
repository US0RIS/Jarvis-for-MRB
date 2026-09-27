from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.agent as agent
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_model as world_model
from jarvis_mrb import capability_inventory, world_facts


class WorldFactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        saved = (world_model.APP_DIR, world_model.DB_PATH, permissions.APP_DIR, permissions.POLICY_PATH)

        def restore() -> None:
            world_model.APP_DIR, world_model.DB_PATH, permissions.APP_DIR, permissions.POLICY_PATH = saved

        self.addCleanup(restore)
        world_model.APP_DIR = base
        world_model.DB_PATH = base / "world_model.sqlite3"
        permissions.APP_DIR = base
        permissions.POLICY_PATH = base / "permissions.json"
        world_model.status()

    def test_user_fact_then_correction_is_durable_distinguishable_and_keeps_history(self) -> None:
        project = world_model.ensure_entity("project", "Project Apollo")
        inferred = world_model.record_event("gmail.message", "Dana leads Apollo contract", source_kind="gmail",
                                            source_ref="msg-1", participants=[(project, "subject", 1.0)])
        world_model.assert_belief(project, "contract_lead", value="Dana Reyes", confidence=0.7,
                                  source_event_id=inferred, evidence="inferred from email")

        reply = agent._fast_path("Actually, Project Apollo's contract lead is Maria Chen.")
        self.assertTrue(reply.ok, reply.message)
        self.assertIn("replacing Dana Reyes", reply.message)

        described = world_facts.describe("Project Apollo")
        fact = described["facts"]["contract_lead"]
        self.assertEqual(fact["current"]["value"], "Maria Chen")
        self.assertTrue(fact["current"]["corrected_by_user"])
        self.assertEqual(fact["current"]["origin"], "you said")
        self.assertIn("Dana Reyes", [h["value"] for h in fact["history"]])
        self.assertIn("gmail", described["sources"])

        # A later weaker provider observation stays represented as a conflict,
        # it does not silently overwrite the user's correction.
        later = world_model.record_event("gmail.message", "Dana still leads Apollo", source_kind="gmail",
                                         source_ref="msg-2", participants=[(project, "subject", 1.0)])
        world_model.assert_belief(project, "contract_lead", value="Dana Reyes", confidence=0.7,
                                  source_event_id=later, evidence="inferred from email")
        fact = world_facts.describe("Project Apollo")["facts"]["contract_lead"]
        self.assertEqual(fact["current"]["value"], "Maria Chen")
        self.assertEqual(fact["disputed"][0]["value"], "Dana Reyes")
        text = agent._fast_path("What do you know about Project Apollo?").message
        self.assertIn("contract lead: Maria Chen (you said", text)
        self.assertIn("conflicting: Dana Reyes (observed via gmail)", text)

    def test_ambiguous_or_unknown_entities_are_not_guessed(self) -> None:
        world_model.ensure_entity("project", "Atlas")
        world_model.ensure_entity("person", "Atlas")
        reply = agent._fast_path("Remember that Atlas's status is paused")
        self.assertFalse(reply.ok)
        self.assertIn("more than one", reply.message)
        missing = agent._fast_path("Correct Zephyr's budget to 10")
        self.assertFalse(missing.ok)
        self.assertIn("don't have anything recorded", missing.message)

    def test_user_fact_and_linker_extraction_share_one_project_entity(self) -> None:
        reply = agent._fast_path("Remember that Project Apollo's contract lead is Dana Reyes")
        self.assertTrue(reply.ok, reply.message)
        self.assertEqual(reply.data["entity"]["kind"], "project")
        linker_id = world_model.ensure_entity("project", "Project Apollo", confidence=0.92)
        self.assertEqual(linker_id, reply.data["entity"]["id"])
        # A legacy untyped duplicate does not make the name ambiguous.
        world_model.ensure_entity("thing", "Project Apollo")
        corrected = agent._fast_path("Actually, Project Apollo's contract lead is Maria Chen")
        self.assertTrue(corrected.ok, corrected.message)

    def test_new_fact_creates_entity_with_user_provenance(self) -> None:
        reply = agent._fast_path("Remember that the venue for Offsite 2026 is Pier 17")
        self.assertTrue(reply.ok, reply.message)
        fact = world_facts.describe("Offsite 2026")["facts"]["venue"]["current"]
        self.assertEqual((fact["value"], fact["source"]), ("Pier 17", "user_statement"))


class CapabilityInventoryTests(unittest.TestCase):
    def test_answer_reflects_live_state_not_documentation(self) -> None:
        env = {"JARVIS_WORLD_ARMOR_ENABLED": "0", "JARVIS_WORLD_ARMOR_FULL_ENABLED": "0",
               "JARVIS_PUSH_ENABLED": "0", "JARVIS_WORLD_ARMOR_PUSH_ENABLED": "0", "JARVIS_CONDUCTOR_ENABLED": "0"}
        with patch.dict(os.environ, env), \
             patch.object(capability_inventory, "_local_model",
                          return_value=capability_inventory._item("local conversation/planning model", "available", "qwen")), \
             patch.object(capability_inventory, "_google", side_effect=RuntimeError("no creds")), \
             patch.object(capability_inventory, "_mesh", return_value=[
                 capability_inventory._item("paired computer MacBook Air", "unavailable", "offline")]):
            reply = agent._fast_path("What can you do right now?")
        self.assertTrue(reply.ok)
        self.assertIn("Working right now: local conversation/planning model", reply.message)
        self.assertIn("Gmail, Google Calendar and Contacts (status check failed", reply.message)
        self.assertIn("Apple Home light control (Presence) (full-scope Presence flag is off", reply.message)
        self.assertIn("closed-app notifications (push transport disabled", reply.message)
        self.assertIn("paired computer MacBook Air (offline)", reply.message)


if __name__ == "__main__":
    unittest.main()
