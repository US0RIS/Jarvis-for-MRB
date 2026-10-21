from __future__ import annotations

"""Cross-feature earpiece acceptance (MOCKED public providers, no network, no
device). Exercises the real router, storage, watch scheduler step, attention
ledger and delivery bookkeeping in one conversation, with every camera/vision
entry point made to fail loudly so the flow proves camera-free operation.

This is not device validation: iOS audio routing, AirPods, APNs and live
providers are outside what this test can prove."""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import jarvis_mrb.external_watches as ew
import jarvis_mrb.world_armor_push as push
import jarvis_mrb.world_model as world_model
from jarvis_mrb import event_bus, object_memory, saved_places, situational_voice
from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.voice_router import clear_focus, turn_context

HOME = (39.74, -104.99)


def fix():
    return {"latitude": HOME[0], "longitude": HOME[1], "location_accuracy_m": 15,
            "location_captured_at": datetime.now(timezone.utc).isoformat(), "channel": "voice"}


def nws(*alerts):
    payload = {"status": "ok", "alerts": list(alerts), "checked_at": datetime.now(timezone.utc).isoformat(),
               "source_url": "https://www.weather.gov/documentation/services-web-api"}
    return {"status": "ok", "summary": f"{len(alerts)} active NWS point alerts",
            "source_url": payload["source_url"], "observed_at": payload["checked_at"],
            "signature": sorted(a["id"] for a in alerts), "payload": payload}


def alert(ident, event, severity="Severe"):
    return {"id": ident, "event": event, "headline": f"{event} issued", "severity": severity,
            "urgency": "Expected", "instruction": "", "expires": "", "sender": "National Weather Service"}


def camera_forbidden(*_a, **_k):
    raise AssertionError("camera/vision path used in camera-free acceptance")


class EarpieceAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(world_model, "APP_DIR", root),
            mock.patch.object(world_model, "DB_PATH", root / "world_model.sqlite3"),
            mock.patch.object(saved_places, "DB_PATH", root / "places.sqlite3"),
            mock.patch.object(object_memory, "DB_PATH", root / "objects.sqlite3"),
            mock.patch.object(object_memory, "MIRROR_WORLD", False),
            mock.patch.object(situational_voice, "DB_PATH", root / "snap.sqlite3"),
            mock.patch.object(push, "PUSH_STORE", root / "push.sqlite3"),
            mock.patch("jarvis_mrb.spatial_memory.find_object", side_effect=camera_forbidden),
            mock.patch("jarvis_mrb.public_camera_catalog.discover_public_cameras", side_effect=camera_forbidden),
            mock.patch("jarvis_mrb.public_camera_vision.analyze_public_camera", side_effect=camera_forbidden),
            mock.patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_PUSH_ENABLED": "0"}),
        ]
        for p in self.patches:
            p.start()
        self.emit = mock.patch.object(event_bus, "emit_proactive").start()
        # The background-runner heartbeat is process-global; start from "never checked in".
        ew._RUNNER["last_tick"] = None
        self.patches.append(mock.patch.object(event_bus, "emit_proactive"))
        situational_voice._CACHE.clear()
        self.session = "acceptance-" + self.id()

    def tearDown(self):
        mock.patch.stopall()
        clear_focus(session_id=self.session)
        situational_voice._CACHE.clear()
        self.tmp.cleanup()

    def say(self, text, context=None):
        with turn_context(self.session, fix() if context is None else context):
            reply = handle_natural_language(text)
        return reply.message

    def test_remember_recall_watch_alert_explain_cancel_without_a_camera(self):
        self.assertIn("Saved this spot as home", self.say("Horus, save this place as home"))

        # Spoken real-world memory, recall and contextual follow-up.
        self.assertEqual(self.say("Remember I put the jumper cables in the trunk"), "Got it.")
        self.say("I put the tire inflator in the trunk too")
        self.assertIn("You last told me your jumper cables were in the trunk",
                      self.say("Where are my jumper cables?"))
        self.assertIn("tire inflator", self.say("What else did I put there?"))

        # Situational question, source-qualified (mocked NWS/USGS adapters).
        with mock.patch.dict(situational_voice.PROVIDERS, {
            "conditions": lambda lat, lon: {"air_quality": {"status": "ok", "us_aqi": 22},
                                            "weather_alerts": {"status": "ok", "alerts": []}},
            "quakes": lambda lat, lon: {"status": "unavailable"},
        }):
            around = self.say("Is anything unusual happening near home?")
        self.assertIn("Nothing notable near home", around)
        self.assertIn("couldn't reach USGS", around)

        # Natural-language watch, real scheduler step with a mocked source.
        confirmation = self.say("Watch for new severe weather alerts near home for the next three hours")
        self.assertIn("official NWS alerts", confirmation)
        self.assertIn("runner has not checked in", confirmation)  # no phantom monitoring
        watch = [w for w in ew.list_watches("personal") if w["kind"] == "nws_alerts"]
        self.assertEqual(len(watch), 1)
        with mock.patch.object(ew, "_fetch", return_value=nws()):
            ew.check_watch(watch[0]["id"], "personal")          # baseline: silent
        self.emit.assert_not_called()
        with mock.patch.object(ew, "_fetch", return_value=nws(alert("urn:1", "Winter Storm Warning"))):
            ew.check_watch(watch[0]["id"], "personal")
        self.assertEqual(self.emit.call_count, 1)
        spoken_alert = self.emit.call_args.args[0]
        self.assertIn("Winter Storm Warning", spoken_alert)

        from jarvis_mrb import proactive_attention
        item = proactive_attention.ledger(limit=5)[0]
        self.assertNotIn(item.get("push_state"), ("accepted_by_apns", "device_acknowledged"))  # no APNs configured
        self.assertFalse(item.get("confirmed_delivery"))

        why = self.say("Why did you tell me that?")
        self.assertIn("Winter Storm Warning", why)

        # Duplicate source state never re-alerts; cancellation stops alerts.
        with mock.patch.object(ew, "_fetch", return_value=nws(alert("urn:1", "Winter Storm Warning"))):
            ew.check_watch(watch[0]["id"], "personal")
        self.assertEqual(self.emit.call_count, 1)
        self.assertIn("cancel", self.say("Cancel the weather watch").lower())
        with mock.patch.object(ew, "_fetch", return_value=nws(alert("urn:2", "Blizzard Warning", "Extreme"))):
            result = ew.check_watch(watch[0]["id"], "personal")
        self.assertEqual(result["status"], "stopped_or_expired")
        self.assertEqual(self.emit.call_count, 1)

        # A bare correction several unrelated turns later must not silently move
        # whichever object was discussed last.
        self.say("Actually it's in the garage now")
        self.assertIn("in the trunk", self.say("where are my jumper cables"))
        # Right after the lookup, the same correction applies to the right object.
        self.say("Actually it's in the garage now")
        self.assertIn("in the garage", self.say("where are my jumper cables"))
        self.assertIn("in the trunk", self.say("where is my tire inflator"))


if __name__ == "__main__":
    unittest.main()
