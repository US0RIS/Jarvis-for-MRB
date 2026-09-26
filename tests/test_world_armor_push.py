from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import world_armor_push as push

NOW = datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)
TOKEN = "ab" * 32
FLAGS = {
    "JARVIS_WORLD_ARMOR_ENABLED": "1",
    "JARVIS_WORLD_ARMOR_PUSH_ENABLED": "1",
    "JARVIS_APNS_TEAM_ID": "TEAM123456",
    "JARVIS_APNS_KEY_ID": "KEY1234567",
    "JARVIS_APNS_BUNDLE_ID": "com.us0ris.JarvisMRB",
    "JARVIS_APNS_KEY_FILE": "/private/not-read-in-mocked-test.p8",
    "JARVIS_APNS_ENVIRONMENT": "development",
}


class WorldArmorPushTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.db = Path(self.temp.name) / "push.sqlite3"
        self.flags = patch.dict("os.environ", FLAGS, clear=False)
        self.flags.start()
        push.stop_worker()

    def tearDown(self):
        push.stop_worker()
        self.flags.stop()
        self.temp.cleanup()

    def test_registration_never_reflects_token(self):
        with patch.object(push, "start_worker", return_value=True):
            result = push.register_device(TOKEN, db_path=self.db, now=NOW)
        self.assertTrue(result["enabled"])
        self.assertFalse(result["token_reflected"])
        self.assertNotIn(TOKEN, str(result))
        state = push.status(db_path=self.db)
        self.assertEqual(state["registered_devices"], 1)

    def test_only_warning_or_urgent_events_enter_outbox(self):
        with patch.object(push, "start_worker", return_value=True):
            push.register_device(TOKEN, db_path=self.db, now=NOW)
            low = push.enqueue_world_event({
                "event_id": "info-event", "seq": 1, "priority": "info",
                "summary": "ordinary",
            }, db_path=self.db, now=NOW)
            high = push.enqueue_world_event({
                "event_id": "warn-event", "seq": 2, "priority": "warning",
                "summary": "important",
            }, db_path=self.db, now=NOW)
        self.assertEqual(low["queued"], 0)
        self.assertEqual(high["queued"], 1)
        self.assertEqual(push.status(db_path=self.db)["pending"], 1)

    def test_durable_outbox_marks_success_only_after_apns_200_equivalent(self):
        with patch.object(push, "start_worker", return_value=True):
            push.register_device(TOKEN, db_path=self.db, now=NOW)
            push.enqueue_world_event({
                "event_id": "urgent-event", "seq": 3, "priority": "urgent",
                "summary": "urgent",
            }, db_path=self.db, now=NOW)
        with patch.object(push, "_send_one", return_value=(True, "")):
            result = push.drain_once(db_path=self.db, now=NOW)
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(push.status(db_path=self.db)["pending"], 0)

    def test_transient_failure_retries_with_backoff(self):
        with patch.object(push, "start_worker", return_value=True):
            push.register_device(TOKEN, db_path=self.db, now=NOW)
            push.enqueue_world_event({
                "event_id": "warn-retry", "seq": 4, "priority": "warning",
                "summary": "retry",
            }, db_path=self.db, now=NOW)
        with patch.object(push, "_send_one", return_value=(False, "ConnectError")):
            result = push.drain_once(db_path=self.db, now=NOW)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(push.status(db_path=self.db)["pending"], 1)
        with patch.object(push, "_send_one", return_value=(True, "")):
            early = push.drain_once(
                db_path=self.db, now=NOW + timedelta(seconds=1)
            )
            later = push.drain_once(
                db_path=self.db, now=NOW + timedelta(seconds=6)
            )
        self.assertEqual(early["attempted"], 0)
        self.assertEqual(later["sent"], 1)

    def test_invalid_token_response_disables_device_without_retry_loop(self):
        with patch.object(push, "start_worker", return_value=True):
            push.register_device(TOKEN, db_path=self.db, now=NOW)
            push.enqueue_world_event({
                "event_id": "bad-device", "seq": 5, "priority": "warning",
                "summary": "invalid device",
            }, db_path=self.db, now=NOW)
        with patch.object(push, "_send_one", return_value=(False, "BadDeviceToken")):
            result = push.drain_once(db_path=self.db, now=NOW)
        self.assertEqual(result["failed"], 1)
        state = push.status(db_path=self.db)
        self.assertEqual(state["registered_devices"], 0)
        self.assertEqual(state["pending"], 0)
        self.assertEqual(state["dead"], 1)

    def test_unregister_disables_delivery(self):
        with patch.object(push, "start_worker", return_value=True):
            push.register_device(TOKEN, db_path=self.db, now=NOW)
        result = push.unregister_device(TOKEN, db_path=self.db)
        self.assertTrue(result["disabled"])
        self.assertEqual(push.status(db_path=self.db)["registered_devices"], 0)


if __name__ == "__main__":
    unittest.main()
