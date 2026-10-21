from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb import voice_router
from jarvis_mrb.voice_router import (
    bound_stream, current_turn, get_focus, set_focus, turn_context,
)


def _ctx(minutes_old: float = 1, **extra):
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes_old)).isoformat()
    return {"latitude": 37.77, "longitude": -122.42, "location_accuracy_m": 30,
            "location_captured_at": stamp, **extra}


class VoiceTurnContextTests(unittest.TestCase):
    def test_no_context_means_no_location_and_honest_note(self):
        with turn_context("s1", None) as turn:
            self.assertIsNone(turn.location)
            self.assertIn("no phone location", turn.location_note)
        self.assertTrue(current_turn().session_id.startswith("anon-"))

    def test_recent_fix_accepted_stale_and_invalid_rejected(self):
        with turn_context("s1", _ctx()) as turn:
            self.assertAlmostEqual(turn.location.latitude, 37.77)
        with turn_context("s1", _ctx(minutes_old=90)) as turn:
            self.assertIsNone(turn.location)
            self.assertIn("minutes old", turn.location_note)
        bad = _ctx(); bad["latitude"] = 123
        with turn_context("s1", bad) as turn:
            self.assertIsNone(turn.location)
        undated = _ctx(); undated.pop("location_captured_at")
        with turn_context("s1", undated) as turn:
            self.assertIsNone(turn.location)
        nan = _ctx(); nan["longitude"] = float("nan")
        with turn_context("s1", nan) as turn:
            self.assertIsNone(turn.location)

    def test_focus_is_session_isolated(self):
        with turn_context("alpha"):
            set_focus("object", "passport")
        with turn_context("beta"):
            self.assertIsNone(get_focus("object"))
        with turn_context("alpha"):
            self.assertEqual(get_focus("object"), "passport")

    def test_bound_stream_keeps_context_across_threads(self):
        seen: list[str] = []

        def factory():
            for _ in range(3):
                yield current_turn().session_id

        stream = bound_stream("streamed", None, factory)
        def step():
            seen.append(next(stream))
        for _ in range(3):
            worker = threading.Thread(target=step)
            worker.start(); worker.join()
        self.assertEqual(seen, ["streamed"] * 3)

    def test_failing_handler_reports_failure_not_success(self):
        def boom(text, turn):
            raise RuntimeError("x")
        # Restore both the handler list and the loaded flag: skipping the real handler
        # import here would otherwise leave later tests without their capabilities.
        saved_handlers = list(voice_router._HANDLERS)
        saved_loaded = voice_router._LOADED
        voice_router._LOADED = True
        voice_router._HANDLERS[:] = [("broken_family", boom)]
        try:
            family, message = voice_router.route("anything")
            self.assertEqual(family, "broken_family")
            self.assertIn("failed", message)
        finally:
            voice_router._HANDLERS[:] = saved_handlers
            voice_router._LOADED = saved_loaded


if __name__ == "__main__":
    unittest.main()
