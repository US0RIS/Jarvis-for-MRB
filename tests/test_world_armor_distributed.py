from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import world_armor_distributed as distributed
from jarvis_mrb import world_armor_movement as movement
from jarvis_mrb import world_armor_platform as platform


class DistributedObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "platform.sqlite3"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        flags = patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED": "1",
            "AISSTREAM_API_KEY": "test-key",
        })
        flags.start()
        self.addCleanup(flags.stop)

    def source(self, kind: str, label: str):
        common = dict(
            label=label, kind=kind, grant_class="api_contract",
            terms_reference="Operator-reviewed provider terms",
            authorized_automated_access=True,
            provider_min_interval_seconds=0,
            cadence_seconds=60, retention_days=2,
            db_path=self.db, now=self.now,
        )
        if kind == "opensky_global":
            return movement.enroll_source(**common)
        return movement.enroll_source(
            **common, latitude=34.05, longitude=-118.25, radius_km=40,
        )

    def test_worker_inventory_only_accepts_live_exact_opted_in_macs(self):
        with patch("jarvis_mrb.reality_mesh.nodes", return_value={
            "nodes": [
                {"id": "windows", "status": "online", "capabilities": {}},
                {"id": "macbook", "status": "online",
                 "observed_at": self.now.isoformat(),
                 "capabilities": {
                     "world_observer": "opensky_region_read_only"
                 }},
                {"id": "macmini", "status": "online",
                 "capabilities": {"world_observer": "disabled"}},
                {"id": "random-node", "status": "online",
                 "capabilities": {
                     "world_observer": "opensky_region_read_only"
                 }},
            ],
        }):
            result = distributed.available_workers()
        self.assertEqual(
            [x["id"] for x in result["workers"]],
            ["windows", "macbook"],
        )
        self.assertFalse(result["network_discovery"])
        self.assertFalse(result["remote_arbitrary_rpc"])
        self.assertFalse(result["credential_delegation"])

    def test_due_sources_distribute_regional_opensky_but_keep_other_adapters_local(self):
        regional_a = self.source("opensky_region", "Air A")
        regional_b = self.source("opensky_region", "Air B")
        global_air = self.source("opensky_global", "Global")
        ais = self.source("aisstream_region", "Port")
        calls = []

        def fake_collect(source_id, *, db_path, scheduled, worker_id, now):
            calls.append((source_id, worker_id, scheduled))
            # Simulate successful central completion enough to move due time
            # without testing collection internals again.
            with movement.closing(movement._connect(db_path, create=True)) as con, con:
                con.execute(
                    "UPDATE movement_sources SET next_due_at=?,"
                    "last_checked_at=?,check_count=check_count+1 "
                    "WHERE id=?",
                    ("9999-12-31T00:00:00+00:00", now.isoformat(), source_id),
                )
            return {"source_id": source_id, "status": "ok",
                    "worker_id": worker_id}

        with patch.object(distributed, "available_workers", return_value={
            "workers": [
                {"id": "windows",
                 "capabilities": ["local_all_movement_adapters"]},
                {"id": "macbook",
                 "capabilities": ["opensky_region_read_only"]},
                {"id": "macmini",
                 "capabilities": ["opensky_region_read_only"]},
            ]
        }), patch.object(distributed, "collect_source",
                         side_effect=fake_collect):
            result = distributed.run_due(
                db_path=self.db, limit=10, now=self.now,
            )
        assignment = dict((source, worker) for source, worker, _ in calls)
        self.assertEqual(
            {assignment[regional_a["id"]], assignment[regional_b["id"]]},
            {"macbook", "macmini"},
        )
        self.assertEqual(assignment[global_air["id"]], "windows")
        self.assertEqual(assignment[ais["id"]], "windows")
        self.assertTrue(all(scheduled for _, _, scheduled in calls))
        self.assertFalse(result["remote_action_authority"])

    def test_due_cameras_round_robin_across_camera_capable_macs(self):
        sources = [
            platform.enroll_source(
                label=f"Camera {i}", kind="public_https",
                locator=f"https://camera{i}.example/current.jpg",
                grant_class="public_publisher",
                terms_reference="Operator-reviewed publisher terms",
                authorized_automated_access=True,
                automated_min_interval_seconds=0,
                cadence_seconds=60, retention_days=2,
                scene_goal="visible heavy rain on the roadway",
                db_path=self.db, now=self.now,
            )
            for i in range(2)
        ]
        calls = []

        def fake_observe(source_id, *, db_path, scheduled, worker_id, now):
            calls.append((source_id, worker_id, scheduled))
            with platform.closing(
                platform._connect(db_path, create=True)
            ) as con, con:
                con.execute(
                    "UPDATE source_grants SET next_due_at=?,"
                    "last_checked_at=?,check_count=check_count+1 "
                    "WHERE id=?",
                    ("9999-12-31T00:00:00+00:00",
                     now.isoformat(), source_id),
                )
            return {
                "source_id": source_id, "status": "ok",
                "worker_id": worker_id,
            }

        with patch.object(distributed, "available_workers", return_value={
            "workers": [
                {"id": "windows",
                 "capabilities": ["local_all_camera_adapters"]},
                {"id": "macbook",
                 "capabilities": ["camera_source_analysis_read_only"]},
                {"id": "macmini",
                 "capabilities": ["camera_source_analysis_read_only"]},
            ]
        }), patch(
            "jarvis_mrb.world_armor_observe.observe_source",
            side_effect=fake_observe,
        ):
            result = distributed.run_camera_due(
                db_path=self.db, limit=10, now=self.now,
            )
        assignment = {source: worker for source, worker, _ in calls}
        self.assertEqual(
            {assignment[source["id"]] for source in sources},
            {"macbook", "macmini"},
        )
        self.assertTrue(all(scheduled for _, _, scheduled in calls))
        self.assertFalse(result["raw_camera_frames_persisted"])
        self.assertFalse(result["remote_action_authority"])

    def test_remote_failure_does_not_retry_on_a_different_worker_same_tick(self):
        source = self.source("opensky_region", "Air")
        calls = []
        def fail(source_id, **kwargs):
            calls.append(kwargs["worker_id"])
            raise RuntimeError("worker unavailable")
        with patch.object(distributed, "available_workers", return_value={
            "workers": [
                {"id": "windows",
                 "capabilities": ["local_all_movement_adapters"]},
                {"id": "macbook",
                 "capabilities": ["opensky_region_read_only"]},
            ]
        }), patch.object(distributed, "collect_source", side_effect=fail):
            result = distributed.run_due(
                db_path=self.db, limit=1, now=self.now,
            )
        self.assertEqual(calls, ["macbook"])
        self.assertEqual(result["checks"][0]["status"], "not_collected")
        self.assertFalse(result["checks"][0]["fallback_attempted"])

    def test_no_remote_worker_still_uses_windows_same_enrolled_provider(self):
        source = self.source("opensky_region", "Air")
        called = []
        def fake(source_id, **kwargs):
            called.append(kwargs["worker_id"])
            return {"source_id": source_id, "status": "ok",
                    "worker_id": kwargs["worker_id"]}
        with patch.object(distributed, "available_workers", return_value={
            "workers": [
                {"id": "windows",
                 "capabilities": ["local_all_movement_adapters"]},
            ]
        }), patch.object(distributed, "collect_source",
                         side_effect=fake):
            distributed.run_due(db_path=self.db, limit=1, now=self.now)
        self.assertEqual(called, ["windows"])


if __name__ == "__main__":
    unittest.main()
