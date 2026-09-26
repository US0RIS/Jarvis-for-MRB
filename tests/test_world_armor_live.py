from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import world_armor_live as live


class WorldArmorLiveFabricTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "live.sqlite3"
        self.now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)

    def test_journal_is_monotonic_resumable_and_payload_bounded(self):
        with patch.object(
            __import__("jarvis_mrb.event_bus", fromlist=["companion_events"]).companion_events,
            "publish",
        ) as fanout:
            first = live.publish_event(
                "movement_receipt", subsystem="movement", status="ok",
                summary="First", source_id="source-a",
                payload={"count": 1}, now=self.now, db_path=self.db,
            )
            second = live.publish_event(
                "camera_receipt", subsystem="camera", status="ok",
                summary="Second", source_id="source-b",
                payload={"blob": "x" * 30_000},
                now=self.now, db_path=self.db,
            )
        self.assertEqual(first["seq"] + 1, second["seq"])
        page = live.events(
            after_seq=first["seq"], limit=20, db_path=self.db
        )
        self.assertEqual([second["seq"]], [x["seq"] for x in page["events"]])
        self.assertTrue(page["events"][0]["payload"]["truncated"])
        self.assertFalse(page["replay_gap"])
        self.assertEqual(fanout.call_count, 2)

    def test_replay_gap_is_explicit_after_retention_or_deletion(self):
        rows = [
            live.publish_event(
                "test", subsystem="test", status="ok",
                summary=f"event {index}", now=self.now, db_path=self.db,
                fanout=False,
            )
            for index in range(4)
        ]
        with live.closing(live._connect(self.db)) as con, con:
            con.execute("DELETE FROM live_events WHERE seq<=?", (rows[1]["seq"],))
        page = live.events(
            after_seq=rows[0]["seq"], limit=20, db_path=self.db
        )
        self.assertTrue(page["replay_gap"])
        self.assertEqual(page["oldest_seq"], rows[2]["seq"])

    def test_cycle_drives_existing_authorized_collectors_and_journals_receipts(self):
        flags = {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_LIVE_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "1",
        }
        movement = {
            "checks": [{
                "source_id": "m" * 32, "status": "ok",
                "observations_saved": 3, "worker_id": "observer-3",
            }],
            "due_remaining": 0,
        }
        cameras = {
            "checks": [{
                "source_id": "c" * 32, "status": "ok",
                "observation_saved": True, "worker_id": "observer-4",
            }],
            "due_remaining": 0,
        }
        watches = [{
            "id": "w" * 32, "status": "ok", "checked": True,
            "change_state": "retained_source_report_delta",
            "notices_created": 0,
        }]
        with patch.dict(os.environ, flags, clear=False), patch(
            "jarvis_mrb.world_armor_distributed.run_due",
            return_value=movement,
        ) as move, patch(
            "jarvis_mrb.world_armor_distributed.run_camera_due",
            return_value=cameras,
        ) as camera, patch.object(
            live, "_run_watch_batch", return_value=watches,
        ) as watch:
            result = live.run_cycle(
                movement_limit=7, camera_limit=5, watch_limit=2,
                now=self.now, db_path=self.db,
            )
        move.assert_called_once_with(limit=7, now=self.now)
        camera.assert_called_once_with(limit=5, now=self.now)
        watch.assert_called_once_with(
            limit=2, now=self.now, live_db_path=self.db
        )
        self.assertEqual(result["events_created"], 3)
        page = live.events(after_seq=0, limit=20, db_path=self.db)
        self.assertEqual(len(page["events"]), 3)
        self.assertEqual(
            {item["subsystem"] for item in page["events"]},
            {"movement", "camera", "watch"},
        )
        state = live.status(db_path=self.db)
        self.assertTrue(state["running"])
        self.assertEqual(state["cycle_count"], 1)

    def test_collection_failure_is_warning_not_all_clear(self):
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_LIVE_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED": "1",
        }, clear=False), patch(
            "jarvis_mrb.world_armor_distributed.run_due",
            side_effect=RuntimeError("provider down"),
        ):
            result = live.run_cycle(now=self.now, db_path=self.db)
        self.assertEqual(result["errors"], ["movement:RuntimeError"])
        page = live.events(after_seq=0, limit=20, db_path=self.db)
        event = page["events"][0]
        self.assertEqual(event["priority"], "warning")
        self.assertEqual(event["status"], "degraded")
        self.assertNotIn("safe", event["summary"].lower())

    def test_live_fabric_requires_explicit_gate(self):
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_LIVE_ENABLED": "0",
        }, clear=False):
            self.assertFalse(live.enabled())
            with self.assertRaises(RuntimeError):
                live.run_cycle(now=self.now, db_path=self.db)


if __name__ == "__main__":
    unittest.main()
