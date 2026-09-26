from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import unittest
from unittest.mock import patch

from jarvis_mrb import world_armor_watchdog as watchdog


class WorldArmorWatchdogTests(unittest.TestCase):
    def test_restart_backoff_is_capped(self):
        self.assertEqual(watchdog.restart_backoff(0), 0)
        self.assertEqual(watchdog.restart_backoff(1), 1)
        self.assertEqual(watchdog.restart_backoff(2), 2)
        self.assertEqual(watchdog.restart_backoff(3), 4)
        self.assertEqual(watchdog.restart_backoff(100), 60)

    def test_status_distinguishes_seen_from_running(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            self.assertFalse(watchdog.status(path)["watchdog_seen"])
            path.write_text(
                '{"watchdog_pid":999999,"child_pid":999998,"restart_count":3}',
                encoding="utf-8",
            )
            with patch.object(watchdog, "_pid_alive", return_value=False):
                value = watchdog.status(path)
            self.assertTrue(value["watchdog_seen"])
            self.assertFalse(value["watchdog_running"])
            self.assertFalse(value["child_running"])
            self.assertEqual(value["restart_count"], 3)

    def test_command_is_exact_typed_live_supervisor(self):
        args = argparse.Namespace(
            interval_seconds=5,
            movement_limit=16,
            camera_limit=8,
            watch_limit=4,
        )
        command = watchdog._command(args)
        self.assertEqual(command[1:4], [
            "-m", "jarvis_mrb.world_armor_live", "--loop"
        ])
        self.assertIn("--movement-limit", command)
        self.assertIn("--camera-limit", command)
        self.assertIn("--watch-limit", command)
        self.assertNotIn("shell", " ".join(command).lower())

    def test_watchdog_refuses_competing_in_process_autostart(self):
        args = argparse.Namespace(
            interval_seconds=5,
            movement_limit=16,
            camera_limit=8,
            watch_limit=4,
            status_path="unused",
            lock_path="unused",
        )
        with patch.dict("os.environ", {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_LIVE_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_LIVE_AUTOSTART": "1",
        }, clear=False):
            with self.assertRaises(RuntimeError):
                watchdog.run(args)


if __name__ == "__main__":
    unittest.main()
