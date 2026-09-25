from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from jarvis_mrb import world_armor_correlate as correlation
from jarvis_mrb import world_armor_phase1 as armor


BASE = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
LATER = BASE + timedelta(minutes=20)


def conditions(at=BASE, aq=40, alerts=True, status="ok", nws_status="ok"):
    return {
        "checked_at": at.isoformat(),
        "air_quality": {
            "status": status, "us_aqi": aq,
            "model_time_utc": at.isoformat(),
        },
        "weather_alerts": {
            "status": nws_status,
            "alerts": [
                {"id": "NWS-7", "event": "Wind Advisory",
                 "headline": "Original NWS announcement",
                 "severity": "Moderate"}
            ] if alerts else [],
        },
    }


def quake(at=BASE - timedelta(minutes=8), status="ok", identifier="us-earth-7"):
    return {
        "status": status, "checked_at": at.isoformat(),
        "events": [{
            "id": identifier, "magnitude": 3.2,
            "place": "within report query radius",
            "occurred_at": at.isoformat(),
            "reviewed": False,
            "source_url": "https://earthquake.usgs.gov/"
        }] if status == "ok" else [],
    }


class WorldArmorCorrelationTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "armor.sqlite3"
        self.env = patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.key = armor.create_investigation(
            "California public infrastructure",
            34.12, -118.16,
            radius_km=30, db_path=self.db, now=BASE,
        )["id"]

    def collect(self, at=BASE, air=None, quakes=None):
        return armor.ingest_fixture(
            self.key,
            air if air is not None else conditions(at=at),
            quakes if quakes is not None else quake(at=at-timedelta(minutes=8)),
            db_path=self.db, now=at,
        )

    def query(self, **kwargs):
        args = {
            "investigation_id": self.key,
            "start_at": (BASE - timedelta(hours=1)).isoformat(),
            "end_at": (BASE + timedelta(hours=1)).isoformat(),
            "now": BASE + timedelta(hours=2),
            "db_path": self.db,
        }
        args.update(kwargs)
        return correlation.correlate(**args)

    def test_no_observations_not_a_claim_about_world(self):
        r = self.query()
        self.assertEqual(r["timed_observations"], [])
        self.assertEqual(r["receipt_time_only_observations"], [])
        self.assertEqual(r["candidate_links"], [])
        self.assertEqual(r["source_coverage"]["usgs_earthquakes"]["status"], "not_checked")
        self.assertFalse(r["coverage_adequate_to_claim_no_world_events"])
        self.assertEqual(r["external_requests"], 0)

    def test_distinct_independent_source_times_make_bounded_temporal_candidate(self):
        self.collect()
        r = self.query()
        self.assertEqual(r["mode"], "fixture_only")
        self.assertEqual(len(r["timed_observations"]), 2)
        self.assertEqual(len(r["receipt_time_only_observations"]), 1)
        self.assertEqual(len(r["candidate_links"]), 1)
        pair = r["candidate_links"][0]
        self.assertEqual(pair["separation_seconds"], 8*60)
        self.assertEqual(
            {pair["first_source"], pair["second_source"]},
            {"openmeteo_model", "usgs_earthquakes"},
        )
        self.assertEqual(pair["spatial_basis"], "same_enrolled_query_region_only")
        self.assertFalse(pair["physical_colocation_verified"])
        self.assertFalse(pair["causation_verified"])
        self.assertEqual(r["query_region"]["latitude"], 34.12)
        self.assertEqual(r["hypotheses_proven"], 0)

    def test_nws_receipt_is_not_promoted_to_source_event_time(self):
        self.collect()
        r = self.query(source_ids=["nws_point_alerts", "usgs_earthquakes"])
        self.assertEqual(r["candidate_links"], [])
        self.assertEqual(len(r["receipt_time_only_observations"]), 1)
        record = r["receipt_time_only_observations"][0]
        self.assertIsNone(record["observed_at"])
        self.assertIsNone(record["published_at"])
        self.assertEqual(record["source"], "nws_point_alerts")
        self.assertIn("receipt-only", r["qualifier"])

    def test_events_outside_source_time_window_do_not_pair_on_arrival_time(self):
        self.collect(
            quakes=quake(at=BASE-timedelta(hours=2)),
        )
        r = self.query(
            start_at=(BASE-timedelta(minutes=15)).isoformat(),
            end_at=(BASE+timedelta(minutes=20)).isoformat(),
        )
        self.assertEqual(r["candidate_links"], [])
        self.assertEqual({x["source"] for x in r["timed_observations"]},
                         {"openmeteo_model"})

    def test_cross_source_time_separation_over_hour_has_no_link(self):
        later = BASE+timedelta(minutes=90)
        self.collect(at=later, air=conditions(at=BASE),
                     quakes=quake(at=later))
        r = self.query(end_at=(BASE+timedelta(hours=2)).isoformat())
        self.assertEqual(len(r["timed_observations"]), 2)
        self.assertEqual(r["candidate_links"], [])

    def test_same_source_revisions_not_independent_confirmation(self):
        self.collect(quakes=quake(status="unavailable"))
        later = BASE+timedelta(minutes=10)
        self.collect(at=later, air=conditions(at=later,aq=45),
                     quakes=quake(status="unavailable"))
        r = self.query(source_ids=["openmeteo_model"])
        self.assertGreaterEqual(len(r["timed_observations"]), 2)
        self.assertEqual(r["candidate_links"], [])

    def test_fixture_cannot_corroborate_a_real_source_observation(self):
        self.collect(quakes=quake(status="unavailable"))
        real_air=conditions(at=LATER,status="unavailable",
                            nws_status="unsupported_region")
        with patch.object(armor, "_clock", return_value=LATER), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   return_value=real_air), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=quake(at=LATER-timedelta(minutes=8))):
            armor.observe_once(self.key,db_path=self.db)
        r=self.query()
        self.assertEqual(r["mode"],"mixed")
        self.assertEqual(len(r["timed_observations"]),2)
        self.assertEqual(r["candidate_links"],[])
        self.assertEqual(
            {x["adapter_mode"] for x in r["timed_observations"]},
            {"fixture","real_adapter"},
        )

    def test_as_known_then_cutoff_excludes_later_source_report(self):
        self.collect(quakes=quake(status="unavailable"))
        self.collect(at=LATER, air=conditions(at=LATER,aq=51),
                     quakes=quake(at=LATER-timedelta(minutes=4)))
        old = self.query(as_known_at=(BASE+timedelta(minutes=1)).isoformat())
        latest = self.query()
        self.assertEqual(old["candidate_links"], [])
        self.assertGreaterEqual(len(latest["candidate_links"]), 1)
        self.assertEqual(len(old["receipt_time_only_observations"]), 1)

    def test_nws_outage_is_explicit_and_cannot_create_candidate(self):
        self.collect(air=conditions(nws_status="unavailable"),
                     quakes=quake(status="unavailable"))
        r = self.query()
        self.assertEqual(r["source_coverage"]["nws_point_alerts"]["status"],
                         "unavailable")
        self.assertEqual(r["candidate_links"], [])
        self.assertFalse(r["coverage_adequate_to_claim_no_world_events"])

    def test_narrow_radius_filters_source_reported_epicenter_not_model_grid(self):
        inside=quake(at=BASE-timedelta(minutes=8))
        inside["events"][0]["latitude"]=34.121
        inside["events"][0]["longitude"]=-118.161
        self.collect(quakes=inside)
        q=self.query(query_radius_km=1)
        self.assertEqual(len(q["timed_observations"]),2)
        self.assertEqual(len(q["candidate_links"]),1)
        self.assertIn("publisher_epicenter",
                      q["candidate_links"][0]["spatial_basis"])
        self.assertEqual(q["query_region"]["radius_km"],1.0)
        self.assertFalse(q["candidate_links"][0]["physical_colocation_verified"])

    def test_narrow_radius_excludes_far_epicenter_and_marks_unknown_separately(self):
        distant=quake(at=BASE-timedelta(minutes=8))
        distant["events"][0]["latitude"]=34.35
        distant["events"][0]["longitude"]=-118.16
        self.collect(quakes=distant)
        far=self.query(query_radius_km=2)
        self.assertEqual({x["source"] for x in far["timed_observations"]},
                         {"openmeteo_model"})
        self.assertEqual(far["candidate_links"],[])
        self.assertEqual(far["spatially_indeterminate_observations"],[])
        other=BASE+timedelta(minutes=20)
        unknown=quake(at=other-timedelta(minutes=8))
        self.collect(at=other,air=conditions(at=other),quakes=unknown)
        r=self.query(query_radius_km=2)
        self.assertEqual(len(r["spatially_indeterminate_observations"]),1)
        self.assertEqual(r["spatially_indeterminate_observations"][0]["source"],
                         "usgs_earthquakes")
        self.assertEqual(r["candidate_links"],[])
        # Missing epicenter still belongs to the original provider-radius
        # observation and is usable only at full enrolled query scope.
        full=self.query()
        self.assertGreaterEqual(len(full["candidate_links"]),1)

    def test_query_radius_cannot_expand_region_or_be_nan(self):
        for value in (0,31,-1,float("nan"),float("inf"),"2",True):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.query(query_radius_km=value)

    def test_source_filters_must_be_known_distinct_bounded(self):
        self.collect()
        good = self.query(source_ids=["usgs_earthquakes"])
        self.assertEqual(len(good["timed_observations"]), 1)
        self.assertEqual(good["source_ids"], ["usgs_earthquakes"])
        for sources in (
            [], ["unknown"], ["usgs_earthquakes", "usgs_earthquakes"],
            ["usgs_earthquakes", "nws_point_alerts",
             "openmeteo_model", "unknown"],
            "usgs_earthquakes",
        ):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                self.query(source_ids=sources)

    def test_reject_invalid_and_future_or_excessive_window_and_naive_cutoff(self):
        cases = [
            {"start_at": "2026-09-24T18:00:00"},
            {"end_at": "2026-09-24T18:00:00"},
            {"start_at": "2026-09-20T00:00:00Z"},
            {"end_at": "2026-09-24T23:00:00Z"},
            {"as_known_at": "2026-09-24T18:01:00"},
            {"as_known_at": "2026-09-24T23:00:00Z"},
        ]
        for opts in cases:
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                self.query(**opts)

    def test_default_off_prevents_query_and_does_not_call_providers(self):
        self.collect()
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED": "0"}), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   side_effect=AssertionError("unexpected provider access")):
            with self.assertRaises(armor.ArmorDisabled):
                self.query()
        self.assertEqual(self.query()["external_actions"], 0)

    def test_expired_investigation_cannot_replay_or_correlate(self):
        self.collect()
        with self.assertRaises(KeyError):
            self.query(now=BASE+timedelta(days=3))

    def test_replay_returns_real_sample_timeline_not_fabricated_continuity(self):
        self.collect()
        self.collect(at=LATER, air=conditions(at=LATER),
                     quakes=quake(at=LATER-timedelta(minutes=3)))
        r = armor.replay(self.key, db_path=self.db,
                         now=BASE+timedelta(hours=2))
        self.assertEqual(len(r["sample_timeline"]), 2)
        self.assertEqual(
            [x["received_at"] for x in r["sample_timeline"]],
            [BASE.isoformat(), LATER.isoformat()],
        )
        self.assertEqual({x["adapter_mode"] for x in r["sample_timeline"]},
                         {"fixture"})


if __name__ == "__main__":
    import unittest
    unittest.main()
