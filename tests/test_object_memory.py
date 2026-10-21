from __future__ import annotations

import importlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from jarvis_mrb import object_memory, voice_router
from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.voice_router import clear_focus, turn_context


class ObjectMemoryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "object_memory.sqlite3"
        self.patches = [
            mock.patch.object(object_memory, "DB_PATH", self.db),
            mock.patch.object(object_memory, "MIRROR_WORLD", False),
            mock.patch.object(object_memory, "VISUAL_SOURCE", False),
        ]
        for p in self.patches:
            p.start()
        self.session = "test-" + self.id()
        clear_focus(session_id=self.session)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        clear_focus(session_id=self.session)
        self.tmp.cleanup()

    def say(self, text: str, *, channel: str = "voice", session: str | None = None) -> str:
        with turn_context(session or self.session, {"channel": channel}):
            reply = handle_natural_language(text)
        self.assertTrue(reply.ok, reply.message)
        return reply.message


class CaptureAndRecallTests(ObjectMemoryBase):
    def test_speak_store_retrieve_move_retrieve_and_history(self):
        self.assertEqual(self.say("Horus, remember I put my passport in the top drawer of my desk"), "Got it.")
        answer = self.say("Where's my passport?")
        self.assertIn("You last told me your passport was in the top drawer of your desk", answer)
        self.assertIn("just now", answer)

        moved = self.say("Remember that I moved my passport into my suitcase.")
        self.assertIn("in your suitcase", moved)
        self.assertIn("not the top drawer of your desk anymore", moved)
        answer = self.say("where is my passport")
        self.assertIn("in your suitcase", answer)
        self.assertNotIn("drawer", answer)
        self.assertIn("top drawer of your desk", self.say("Where was it before?"))

        # History is preserved, the older assertion superseded, not erased.
        view = object_memory.resolve("passport")[0]
        statuses = [h["status"] for h in view["history"]]
        self.assertEqual(statuses, ["active", "superseded"])
        self.assertEqual(view["history"][0]["source_kind"], "user_spoken")

    def test_memory_survives_process_restart(self):
        self.say("I put the jumper cables in the trunk")
        clear_focus(session_id=self.session)
        importlib.reload(object_memory)  # simulate a fresh backend process
        with mock.patch.object(object_memory, "DB_PATH", self.db), \
                mock.patch.object(object_memory, "MIRROR_WORLD", False), \
                mock.patch.object(object_memory, "VISUAL_SOURCE", False):
            voice_router._HANDLERS[:] = [(n, h) for n, h in voice_router._HANDLERS if n != "object_memory"]
            voice_router.register("object_memory", object_memory.handle)
            answer = self.say("Where are my jumper cables?")
        self.assertIn("You last told me your jumper cables were in the trunk", answer)

    def test_follow_up_what_else_did_i_put_there(self):
        self.say("I put the jumper cables in the trunk")
        self.say("I put the tire inflator in the trunk of my car")
        self.say("I left my umbrella in the hall closet")
        clear_focus(session_id=self.session)
        self.assertIn("jumper cables", self.say("Where are my jumper cables?"))
        also = self.say("What else did I put there?")
        self.assertIn("You also mentioned your tire inflator", also)
        self.assertNotIn("umbrella", also)
        self.assertNotIn("jumper", also)
        scoped = self.say("What's in the trunk?")
        self.assertIn("jumper cables", scoped)
        self.assertIn("tire inflator", scoped)

    def test_multiple_objects_in_one_statement(self):
        self.say("I packed my charger and the headphones in my backpack")
        self.assertIn("in your backpack", self.say("where are my headphones?"))
        self.assertIn("in your backpack", self.say("where's my charger"))

    def test_correction_marks_prior_claim_corrected_not_moved(self):
        self.say("Remember I put my passport in the top drawer")
        self.assertIn("Corrected", self.say("No, the bottom drawer"))
        self.assertIn("bottom drawer", self.say("where's my passport"))
        statuses = [h["status"] for h in object_memory.resolve("passport")[0]["history"]]
        self.assertEqual(statuses, ["active", "corrected"])
        self.assertIn("That's the only place", self.say("Where was it before?"))

    def test_update_after_lookup_is_a_move(self):
        self.say("I put the drill in the garage")
        with mock.patch.object(object_memory, "CORRECTION_WINDOW", timedelta(seconds=-1)):
            self.say("Where's the drill?")
            self.say("Actually it's in the basement now")
        statuses = [h["status"] for h in object_memory.resolve("drill")[0]["history"]]
        self.assertEqual(statuses, ["active", "superseded"])

    def test_aliases_and_builtin_synonyms(self):
        self.say("I put the jumper cables in the trunk")
        self.assertIn("in the trunk", self.say("Where are the booster cables?"))
        self.say("My blue bag is also called the gym bag")
        self.say("I left my blue bag in the car")
        self.assertIn("blue bag", self.say("where's my gym bag"))

    def test_fuzzy_speech_slip_still_finds_object(self):
        self.say("I put my passport in the safe")
        self.assertIn("in the safe", self.say("where is my pasport"))

    def test_ambiguous_identity_asks_then_resolves_follow_up(self):
        self.say("I left my car keys in the console")
        self.say("I hung my house keys on the hook by the door")
        clear_focus(session_id=self.session)
        ask = self.say("Where are my keys?")
        self.assertIn("2 matches", ask)
        self.assertIn("car keys", ask)
        self.assertIn("house keys", ask)
        self.assertTrue(ask.endswith("Which one?"))
        pick = self.say("The house keys")
        self.assertIn("on the hook by the door", pick)
        self.assertNotIn("console", pick)

    def test_missing_information_is_an_honest_unknown(self):
        answer = self.say("Where are my sunglasses?")
        self.assertIn("I don't have any record of where your sunglasses are", answer)
        self.assertNotIn("saw", answer.lower())

    def test_not_my_object_falls_through_to_other_routes(self):
        with turn_context(self.session, {"channel": "voice"}):
            self.assertIsNone(object_memory.handle("where is the nearest pharmacy", voice_router.current_turn()))
            self.assertIsNone(object_memory.handle("where is alex", voice_router.current_turn()))
            self.assertIsNone(object_memory.handle("remember my meeting is at 3", voice_router.current_turn()))
            self.assertIsNone(object_memory.handle("remember to call mom", voice_router.current_turn()))
            self.assertIsNone(object_memory.handle("my flight is in two hours", voice_router.current_turn()))
            self.assertIsNone(object_memory.handle("where am i", voice_router.current_turn()))

    def test_stale_location_language(self):
        old = datetime.now(timezone.utc) - timedelta(days=40)
        object_memory.record_placement("snow brush", "the garage shelf", relation="on", now=old)
        answer = self.say("Where's my snow brush?")
        self.assertIn("on the garage shelf", answer)
        self.assertIn("may have moved", answer)

    def test_removal_and_lost(self):
        self.say("I put my passport in my suitcase")
        self.assertIn("took it out", self.say("I took my passport out of my suitcase"))
        answer = self.say("Where's my passport?")
        self.assertIn("I don't know where it is now", answer)
        self.say("I left my wallet in my jacket")
        self.assertIn("in your jacket", self.say("I lost my wallet"))
        self.assertIn("was lost", self.say("where's my wallet"))

    def test_source_is_user_report_never_visual(self):
        self.say("I put my passport in the safe")
        source = self.say("How do you know?")
        self.assertIn("You told me by voice", source)
        self.assertIn("didn't see it", source)
        self.assertIn("I can't see", self.say("Have you seen my passport?"))
        typed = "test-typed-" + self.id()
        with turn_context(typed, {"channel": "text"}):
            handle_natural_language("I put my notebook on the desk")
            self.assertIn("in text", handle_natural_language("how do you know").message)
        clear_focus(session_id=typed)

    def test_camera_sighting_is_labeled_separately_and_optional(self):
        self.say("I put my keys in the bowl")
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        sighting = {"seen_at": future, "location": "kitchen counter", "object": "keys"}
        with mock.patch.object(object_memory, "VISUAL_SOURCE", True), \
                mock.patch("jarvis_mrb.spatial_memory.find_object", return_value=[sighting]):
            answer = self.say("Where are my keys?")
        self.assertIn("You last told me your keys were in the bowl", answer)
        self.assertIn("optional camera sighting", answer)
        self.assertIn("not your report", answer)
        # Camera-off: the same question works with no visual source at all.
        self.assertNotIn("camera", self.say("Where are my keys?"))

    def test_forget_one_and_forget_all_requires_confirmation(self):
        self.say("I put my passport in the safe")
        self.say("I put the drill in the garage")
        self.assertIn("Forgotten", self.say("Forget where I put my passport"))
        self.assertIn("I don't have any record", self.say("where's my passport"))
        self.assertIn("confirm", self.say("Forget all my object memories"))
        self.assertEqual(object_memory.status()["objects"], 1)
        self.assertIn("forgot 1", self.say("yes, forget them all"))
        self.assertEqual(object_memory.status()["objects"], 0)

    def test_focus_is_isolated_between_sessions(self):
        self.say("I put the jumper cables in the trunk")
        other = "other-" + self.id()
        with turn_context(other, {"channel": "voice"}):
            self.assertIn("I don't have a place in mind",
                          handle_natural_language("What else did I put there?").message)
        clear_focus(session_id=other)

    def test_schema_records_provenance_columns(self):
        self.say("I put my passport in the safe")
        with sqlite3.connect(self.db) as conn:
            row = conn.execute(
                "SELECT source_kind, channel, utterance, asserted_at FROM assertions").fetchone()
        self.assertEqual(row[0], "user_spoken")
        self.assertEqual(row[1], "voice")
        self.assertIn("passport", row[2])
        self.assertTrue(row[3])


class WorldMirrorTests(ObjectMemoryBase):
    def test_world_mirror_uses_user_report_provenance(self):
        calls = {}

        def fake_record_event(event_type, summary, **kwargs):
            calls["event"] = (event_type, kwargs["source_kind"], kwargs["evidence"])
            return 7

        with mock.patch.object(object_memory, "MIRROR_WORLD", True), \
                mock.patch("jarvis_mrb.world_model.ensure_entity", side_effect=lambda kind, name, **_: f"{kind}:{name}"), \
                mock.patch("jarvis_mrb.world_model.record_event", side_effect=fake_record_event), \
                mock.patch("jarvis_mrb.world_model.assert_belief") as belief:
            object_memory.record_placement("passport", "the safe")
        self.assertEqual(calls["event"][0], "memory.user_reported_location")
        self.assertEqual(calls["event"][1], "user_report")
        self.assertIn("not a visual", calls["event"][2])
        self.assertEqual(belief.call_args.args[1], "user_reported_place")


if __name__ == "__main__":
    unittest.main()


class ObjectMemoryApiTests(ObjectMemoryBase):
    def test_command_endpoint_end_to_end_and_private_controls(self):
        from fastapi.testclient import TestClient
        from jarvis_mrb import service

        client = TestClient(service.app)
        headers = {"Authorization": "Bearer secret"}
        body = {"session_id": self.session, "context": {"channel": "voice"}}
        with mock.patch.object(service, "API_TOKEN", "secret"), \
                mock.patch.object(service, "remember_exchange_async"), \
                mock.patch.object(service, "append_message"):
            said = client.post("/command", json={**body, "text": "Remember I put my passport in the safe"},
                               headers=headers).json()
            self.assertEqual(said["message"], "Got it.")
            asked = client.post("/command", json={**body, "text": "where's my passport?"}, headers=headers).json()
            self.assertIn("in the safe", asked["message"])
            self.assertEqual(client.get("/memory/objects").status_code, 401)
            listing = client.get("/memory/objects", headers=headers).json()
            self.assertEqual(listing["status"]["evidence"], "user_reported")
            self.assertFalse(listing["status"]["camera_required"])
            object_id = listing["objects"][0]["object_id"]
            self.assertEqual(client.delete("/memory/objects", headers=headers).status_code, 400)
            self.assertEqual(client.delete(f"/memory/objects/{object_id}", headers=headers).status_code, 200)
            self.assertEqual(client.delete(f"/memory/objects/{object_id}", headers=headers).status_code, 404)
            gone = client.post("/command", json={**body, "text": "where's my passport?"}, headers=headers).json()
            self.assertIn("I don't have any record", gone["message"])


class ParkingTests(ObjectMemoryBase):
    def test_parking_capture_and_recall(self):
        self.assertEqual(self.say("I parked on level 3 of the airport garage"), "Got it.")
        self.assertIn("on level 3 of the airport garage", self.say("Where did I park?"))
        self.say("I just parked my bike at the rack by the library")
        self.assertIn("at the rack by the library", self.say("where's my bike parked"))
        self.assertIn("on level 3", self.say("where did I park my car"))
