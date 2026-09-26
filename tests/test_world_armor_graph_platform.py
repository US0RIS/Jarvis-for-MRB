from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import world_armor_platform as reg
from jarvis_mrb import world_armor_observe as observe
from jarvis_mrb import world_armor_graph as graph


class CombinedCameraGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "registry.sqlite3"
        self.now = datetime.now(timezone.utc)
        flags = patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "1",
        })
        flags.start()
        self.addCleanup(flags.stop)

    def enroll(self, **kwargs):
        data = dict(
            label="Corridor", kind="public_https",
            locator="https://camera-public.example/road.jpg",
            grant_class="public_publisher", terms_reference="Operator-checked permissions",
            authorized_automated_access=False,
            automated_min_interval_seconds=0, cadence_seconds=0,
            scene_goal="visible standing traffic",
            latitude=34.12, longitude=-118.16,
            now=self.now, db_path=self.db,
        )
        data.update(kwargs)
        return reg.enroll_source(**data)

    def test_camera_evidence_is_receipt_time_not_fake_correlated_source_time(self):
        source = self.enroll()
        frame = {
            "frame": b"one normalized frame",
            "sha256": "b"*64,
            "retrieved_at": self.now.isoformat(),
            "media_kind": "published_still",
            "source_display": "https://camera-public.example/road.jpg",
        }
        with patch.object(observe.perception, "acquire_source",
                          return_value=frame), patch.object(
            observe.perception, "interpret_frame",
            return_value={"condition_status": "observed",
                          "description": "Several stationary cars visible.",
                          "model": "local-moondream"},
        ):
            report = observe.observe_source(
                source["id"], db_path=self.db, now=self.now,
            )
        self.assertEqual(report["status"], "ok")
        legacy = {
            "investigation": {
                "id": "a"*32, "latitude": 34.12,
                "longitude": -118.16, "radius_km": 30,
            },
            "observations": [{
                "source": "usgs_earthquakes",
                "observed_at": self.now.isoformat(),
                "kind": "reported_earthquake",
            }],
            "coverage": {"usgs_earthquakes": {"status": "ok"}},
        }
        with patch("jarvis_mrb.world_armor_graph.replay",
                   return_value=legacy):
            both = graph.combined_evidence(
                "a"*32, platform_db_path=self.db, now=self.now,
            )
        self.assertEqual(len(both["camera_observations"]), 1)
        self.assertEqual(len(both["environmental_observations"]), 1)
        self.assertIsNone(both["camera_observations"][0]["source_capture_at"])
        self.assertIn("capture_times_unverified", both["temporal_join"])
        self.assertFalse(both["source_independent_confirmation"])
        self.assertFalse(both["causal_conclusions"])
        timeline = graph.timeline(db_path=self.db)
        self.assertEqual(timeline["time_axis"], "local_receipt_only")
        self.assertFalse(timeline["automatic_identity_tracking"])

    def test_unknown_geography_is_not_falsely_geolocated(self):
        unknown = self.enroll(latitude=None, longitude=None)
        legacy = {
            "investigation": {
                "id": "a"*32, "latitude": 34.12,
                "longitude": -118.16, "radius_km": 30,
            },
            "observations": [], "coverage": {},
        }
        with patch("jarvis_mrb.world_armor_graph.replay", return_value=legacy):
            report = graph.combined_evidence(
                "a"*32, platform_db_path=self.db, now=self.now,
            )
        self.assertIn(unknown["id"],
                      report["enrolled_camera_location_unknown_source_ids"])
        self.assertEqual(report["nearby_camera_sources"], [])
        self.assertFalse(report["viewing_footprints_verified"])
