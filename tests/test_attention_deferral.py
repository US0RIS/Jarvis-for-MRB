from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.agency_attention as attention
import jarvis_mrb.agent as agent
import jarvis_mrb.environment_state as environment_state
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_model as world_model


class AttentionDeferralTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        saved = (world_model.APP_DIR, world_model.DB_PATH, attention.DB_PATH, environment_state.APP_DIR,
                 environment_state.STATE_PATH, permissions.APP_DIR, permissions.POLICY_PATH)

        def restore() -> None:
            (world_model.APP_DIR, world_model.DB_PATH, attention.DB_PATH, environment_state.APP_DIR,
             environment_state.STATE_PATH, permissions.APP_DIR, permissions.POLICY_PATH) = saved

        self.addCleanup(restore)
        world_model.APP_DIR = base
        world_model.DB_PATH = attention.DB_PATH = base / "world_model.sqlite3"
        environment_state.APP_DIR = base
        environment_state.STATE_PATH = base / "state.json"
        permissions.APP_DIR = base
        permissions.POLICY_PATH = base / "permissions.json"
        world_model.status()
        self.emitted: list[str] = []
        quiet = patch("jarvis_mrb.sensor_opportunities.quiet_reason", return_value="")
        self.quiet = quiet.start()
        self.addCleanup(quiet.stop)

    def _consider(self, key: str, severity: str = "warning") -> dict:
        return attention.consider(kind="approval_required", message=f"Need approval {key}", dedup_key=key,
                                  benefit=90, urgency=70, severity=severity, emitter=self.emitted.append)

    def test_busy_window_defers_then_delivers_once_after_it_clears(self) -> None:
        reply = agent._fast_path("Don't interrupt me until 11:59 pm")
        self.assertTrue(reply.ok, reply.message)
        held = self._consider("a")
        self.assertFalse(held["emitted"])
        self.assertIn("not to be interrupted", held["deferred_reason"])
        self.assertEqual(attention.flush_deferred(emitter=self.emitted.append)["delivered"], 0)
        self.assertTrue(agent._fast_path("I'm free now").ok)
        self.assertEqual(attention.flush_deferred(emitter=self.emitted.append)["delivered"], 1)
        self.assertEqual(attention.flush_deferred(emitter=self.emitted.append)["delivered"], 0)
        self._consider("a")  # same evidence again: no second interruption
        self.assertEqual(self.emitted, ["Need approval a"])

    def test_urgent_is_not_deferred_and_driving_defers_non_urgent(self) -> None:
        self.quiet.return_value = "driving or in a conversation (iPhone motion/audio)"
        self.assertFalse(self._consider("b")["emitted"])
        self.assertTrue(self._consider("c", severity="urgent")["emitted"])
        self.assertEqual(self.emitted, ["Need approval c"])

    def test_current_calendar_event_defers(self) -> None:
        now = datetime.now().astimezone()
        event = world_model.ensure_entity("calendar_event", "Board review")
        world_model.assert_belief(event, "start_at", value=(now - timedelta(minutes=10)).isoformat())
        world_model.assert_belief(event, "end_at", value=(now + timedelta(minutes=50)).isoformat())
        world_model.assert_belief(event, "calendar_status", value="confirmed")
        held = self._consider("d")
        self.assertFalse(held["emitted"])
        self.assertIn("Board review", held["deferred_reason"])


if __name__ == "__main__":
    unittest.main()
