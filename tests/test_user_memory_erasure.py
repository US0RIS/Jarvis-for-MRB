from __future__ import annotations

"""Erasure and session-isolation regressions for user-reported object memory.

Two real temporary databases are used: object_memory and the world model. The
tests mirror real traffic (voice, REST, both command endpoints) and check the
world-model copy directly, not just the local record.
"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from jarvis_mrb import object_memory, service, voice_router, world_model
from jarvis_mrb.agent import AgentReply, handle_natural_language
from jarvis_mrb.voice_router import clear_focus, turn_context


class ErasureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(object_memory, "DB_PATH", root / "objects.sqlite3"),
            mock.patch.object(object_memory, "MIRROR_WORLD", True),
            mock.patch.object(object_memory, "VISUAL_SOURCE", False),
            mock.patch.object(world_model, "APP_DIR", root),
            mock.patch.object(world_model, "DB_PATH", root / "world_model.sqlite3"),
        ]
        for p in self.patches:
            p.start()
        self.session = "erase-" + self.id()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        clear_focus(session_id=self.session)
        self.tmp.cleanup()

    def say(self, text, session=None):
        with turn_context(session or self.session, {"channel": "voice"}):
            return handle_natural_language(text).message

    def world(self, sql, params=()):
        with closing(sqlite3.connect(world_model.DB_PATH)) as conn:
            return conn.execute(sql, params).fetchall()

    def mirrored_events(self):
        return self.world("SELECT event_key FROM events WHERE event_key LIKE 'object_memory:%'")

    def mirrored_beliefs(self):
        return self.world("SELECT b.id FROM beliefs b JOIN events e ON e.id=b.source_event_id "
                          "WHERE e.event_key LIKE 'object_memory:%'")

    def entity_named(self, name):
        return self.world("SELECT id FROM entities WHERE normalized_name=?", (name,))


class VoiceErasureTests(ErasureBase):
    def test_voice_forget_removes_world_copy_and_orphaned_entities(self):
        self.say("I put my passport in the safe")
        self.assertEqual(len(self.mirrored_events()), 1)
        self.assertEqual(len(self.mirrored_beliefs()), 1)
        self.assertTrue(self.entity_named("passport"))
        self.say("Forget where I put my passport")
        self.assertEqual(self.mirrored_events(), [])
        self.assertEqual(self.mirrored_beliefs(), [])
        self.assertEqual(self.entity_named("passport"), [])

    def test_shared_entities_and_other_objects_survive(self):
        self.say("I put my passport in the safe")
        self.say("I put my keys in the safe")
        # An unrelated record that shares the same place entity must keep it alive.
        world_model.record_event(
            "note.observed", "The safe was inspected by the locksmith",
            source_kind="user_report", source_ref="unrelated:1",
            participants=[(world_model.ensure_entity("place", "the safe", confidence=0.9), "subject", 0.9)],
            event_key="unrelated:locksmith",
        )
        self.say("Forget where I put my passport")
        self.assertEqual(len(self.mirrored_events()), 1, "keys record must survive")
        self.assertTrue(self.entity_named("keys"))
        self.assertTrue(self.entity_named("the safe"), "place still referenced elsewhere")
        self.assertEqual(self.entity_named("passport"), [])

    def test_superseded_history_is_erased_too(self):
        self.say("I put my passport in the top drawer")
        self.say("I moved my passport into my suitcase")
        self.assertEqual(len(self.mirrored_events()), 2)
        self.say("Forget where I put my passport")
        self.assertEqual(self.mirrored_events(), [])
        self.assertEqual(self.mirrored_beliefs(), [])

    def test_forget_all_erases_every_mirror(self):
        self.say("I put my passport in the safe")
        self.say("I put my keys in the drawer")
        self.say("Forget all my object memories")
        self.assertIn("including their copies in your world history", self.say("yes, forget them all"))
        self.assertEqual(self.mirrored_events(), [])
        self.assertEqual(self.mirrored_beliefs(), [])
        self.assertEqual(object_memory.status()["objects"], 0)

    def test_failed_world_erase_does_not_claim_success(self):
        self.say("I put my passport in the safe")
        with mock.patch("jarvis_mrb.world_model.erase_event_keys", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.OperationalError):
                object_memory.forget(object_memory.resolve("passport")[0]["object_id"])
        # The local record stays, so the user is not told it was deleted.
        self.assertTrue(object_memory.resolve("passport")[0]["history"])


class RestErasureTests(ErasureBase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        self.client = TestClient(service.app)
        self.auth = {"Authorization": "Bearer secret"}
        self.api = [mock.patch.object(service, "API_TOKEN", "secret"),
                    mock.patch.object(service, "remember_exchange_async"),
                    mock.patch.object(service, "append_message")]
        for p in self.api:
            p.start()

    def tearDown(self):
        for p in self.api:
            p.stop()
        super().tearDown()

    def test_rest_single_delete_erases_world_copy(self):
        self.say("I put my passport in the safe")
        self.say("I put my keys in the drawer")
        listing = self.client.get("/memory/objects", headers=self.auth).json()
        passport = next(o for o in listing["objects"] if o["object"] == "passport")
        self.assertEqual(self.client.delete(f"/memory/objects/{passport['object_id']}",
                                            headers=self.auth).status_code, 200)
        self.assertEqual(len(self.mirrored_events()), 1)
        self.assertEqual(self.entity_named("passport"), [])
        self.assertTrue(self.entity_named("keys"))

    def test_rest_forget_all_erases_world_copies(self):
        self.say("I put my passport in the safe")
        resp = self.client.delete("/memory/objects?confirm=forget-all", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.mirrored_events(), [])


class SessionIsolationTests(ErasureBase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        self.client = TestClient(service.app)
        self.auth = {"Authorization": "Bearer secret"}
        self.api = [
            mock.patch.object(service, "API_TOKEN", "secret"),
            mock.patch.object(service, "remember_exchange_async"),
            mock.patch.object(service, "append_message"),
            mock.patch("jarvis_mrb.agent._ollama_plan", return_value=(None, "planner offline")),
            mock.patch.object(service, "get_inference_config", return_value={"provider": "byok", "model": "test"}),
        ]
        for p in self.api:
            p.start()
        self.say("I put my passport in the safe", session="owner")

    def tearDown(self):
        for p in self.api:
            p.stop()
        super().tearDown()

    def command(self, text, session=None):
        body = {"text": text, "context": {"channel": "voice"}}
        if session is not None:
            body["session_id"] = session
        return self.client.post("/command", json=body, headers=self.auth).json()["message"]

    def stream(self, text, session=None):
        body = {"text": text, "context": {"channel": "voice"}}
        if session is not None:
            body["session_id"] = session
        raw = self.client.post("/command/stream", json=body, headers=self.auth).text
        return "".join(json.loads(line).get("text", "") for line in raw.splitlines()
                       if json.loads(line).get("type") == "delta")

    def assert_stays_unforgotten(self, reply):
        self.assertNotIn("forgot", reply.lower())
        self.assertEqual(object_memory.status()["objects"], 1)

    def test_command_without_session_cannot_confirm_another_clients_forget_all(self):
        self.assertIn("confirm", self.command("forget all my object memories"))
        self.assert_stays_unforgotten(self.command("yes, forget them all"))

    def test_stream_without_session_cannot_confirm_another_clients_forget_all(self):
        self.assertIn("confirm", self.stream("forget all my object memories"))
        self.assert_stays_unforgotten(self.stream("yes, forget them all"))

    def test_cross_endpoint_confirmation_is_isolated_too(self):
        self.assertIn("confirm", self.command("forget all my object memories"))
        self.assert_stays_unforgotten(self.stream("yes, forget them all"))

    def test_explicit_session_still_confirms_its_own_request(self):
        self.assertIn("confirm", self.command("forget all my object memories", session="owner"))
        self.assertIn("forgot", self.command("yes, forget them all", session="owner").lower())
        self.assertEqual(object_memory.status()["objects"], 0)

    def test_requests_without_session_get_distinct_sessions(self):
        with turn_context(voice_router.isolated_session_id(None), None) as a:
            pass
        first = voice_router.isolated_session_id(None)
        second = voice_router.isolated_session_id(None)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("anon-"))
        self.assertEqual(voice_router.isolated_session_id("named"), "named")


if __name__ == "__main__":
    unittest.main()
