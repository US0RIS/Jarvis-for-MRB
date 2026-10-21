from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from jarvis_mrb import saved_places
from jarvis_mrb.voice_router import current_turn, turn_context


def fix():
    return {"latitude": 47.6062, "longitude": -122.3321, "location_accuracy_m": 12,
            "location_captured_at": datetime.now(timezone.utc).isoformat(), "channel": "voice"}


class SavedPlacesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(saved_places, "DB_PATH", Path(self.tmp.name) / "p.sqlite3")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_save_requires_a_real_fix(self):
        with turn_context("s", {"channel": "voice"}):
            reply = saved_places.handle("save this place as home", current_turn())
        self.assertIn("can't save home", reply)
        self.assertIsNone(saved_places.get_place("home"))
        with turn_context("s", fix()):
            reply = saved_places.handle("Horus, save this place as home", current_turn())
        self.assertIn("Saved this spot as home", reply)
        self.assertAlmostEqual(saved_places.get_place("my home")["latitude"], 47.6062)

    def test_resolution_order_and_honest_failures(self):
        with turn_context("s", None):
            place, reason = saved_places.resolve_place("anything happening near home?", current_turn())
            self.assertIsNone(place)
            self.assertIn("don't have home saved", reason)
            place, reason = saved_places.resolve_place("anything happening around me?", current_turn())
            self.assertIsNone(place)
            self.assertIn("don't know where you are", reason)
        saved_places.save_place("home", 40.0, -105.0)
        with turn_context("s", fix()):
            place, _ = saved_places.resolve_place("weather alerts near home", current_turn())
            self.assertEqual((place.label, place.provenance), ("home", "saved_place"))
            place, _ = saved_places.resolve_place("what's around me", current_turn())
            self.assertEqual(place.provenance, "phone_fix")

    def test_forget_and_list(self):
        saved_places.save_place("office", 1.0, 2.0)
        with turn_context("s", None):
            self.assertIn("office", saved_places.handle("what places have you saved", current_turn()))
            self.assertIn("Forgot", saved_places.handle("forget my office location", current_turn()))
        self.assertEqual(saved_places.list_places(), [])


if __name__ == "__main__":
    unittest.main()
