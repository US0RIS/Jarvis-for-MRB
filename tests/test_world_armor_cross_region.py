from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from jarvis_mrb import world_armor_phase1 as armor
from jarvis_mrb import world_armor_cross_region as cross


BASE = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def weather(at=BASE, aqi=45.0, status="ok"):
    return {
        "checked_at": at.isoformat(),
        "air_quality": {
            "status": status, "model_time_utc": at.isoformat(), "us_aqi": aqi,
        },
        "weather_alerts": {
            "status": "ok", "alerts": [{
                "id": "official-point-alert", "event": "Weather Advisory",
                "severity": "Moderate", "headline": "Test fixture only",
            }],
        },
    }


def earthquake(key="quake-shared", at=None, *, mag=3.1,
               lat=34.12, lon=-118.16, status="ok"):
    at = at or (BASE-timedelta(minutes=10))
    return {
        "status": status, "checked_at": BASE.isoformat(),
        "events": [] if status != "ok" else [{
            "id": key, "magnitude": mag, "occurred_at": at.isoformat(),
            "latitude": lat, "longitude": lon,
            "place": "source-reported point", "reviewed": False,
            "source_url": "https://earthquake.usgs.gov/",
        }],
    }


class CrossRegionTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "armor.sqlite3"
        env = patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"1"})
        env.start()
        self.addCleanup(env.stop)
        self.one = armor.create_investigation(
            "Pasadena corridor", 34.12, -118.16,
            radius_km=30, db_path=self.path, now=BASE,
        )["id"]
        self.two = armor.create_investigation(
            "Second corridor", 34.13, -118.17,
            radius_km=30, db_path=self.path, now=BASE,
        )["id"]

    def capture(self, investigation_id, *, at=BASE, aqi=45,
                key="quake-shared", quake_at=None, qstatus="ok",
                air_status="ok", lat=34.12, lon=-118.16):
        return armor.ingest_fixture(
            investigation_id, weather(at, aqi, air_status),
            earthquake(key, quake_at, lat=lat,lon=lon,status=qstatus),
            db_path=self.path,now=at,
        )

    def query(self, **kwargs):
        params = {
            "primary_id":self.one,
            "secondary_id":self.two,
            "start_at": (BASE-timedelta(hours=1)).isoformat(),
            "end_at": (BASE+timedelta(hours=1)).isoformat(),
            "now": BASE+timedelta(hours=2),
            "db_path": self.path,
        }
        params.update(kwargs)
        return cross.compare_regions(**params)

    def test_two_retained_regions_cross_match_same_model_period(self):
        self.capture(self.one,aqi=41)
        self.capture(self.two,aqi=67)
        r=self.query()
        self.assertEqual(len(r["modelled_aqi_comparisons"]),1)
        match=r["modelled_aqi_comparisons"][0]
        self.assertEqual(match["difference_secondary_minus_primary"],26)
        self.assertEqual(match["model_time"],BASE.isoformat())
        self.assertFalse(match["independent_measurements"])
        self.assertEqual(r["external_requests"],0)
        self.assertEqual(r["external_actions"],0)
        self.assertEqual(r["primary"]["investigation_id"],self.one)
        self.assertEqual(r["secondary"]["investigation_id"],self.two)
        self.assertTrue(r["enrolled_regions_overlap_geometrically"])

    def test_shared_earthquake_is_one_source_record_not_two_events(self):
        self.capture(self.one)
        self.capture(self.two)
        shared=self.query()["shared_usgs_source_events"]
        self.assertEqual(len(shared),1)
        self.assertEqual(shared[0]["provider_key"],"quake-shared")
        self.assertEqual(shared[0]["independent_confirmations"],1)
        self.assertEqual(self.query()["independent_corroboration_from_shared_event"],0)

    def test_disjoint_regions_do_not_imply_a_global_map(self):
        distant=armor.create_investigation(
            "Southern hemisphere", -37.81, 144.96,
            db_path=self.path,now=BASE,
        )["id"]
        self.capture(self.one)
        self.capture(distant,key="quake-elsewhere",aqi=70,lat=-37.81,lon=144.96)
        r=self.query(secondary_id=distant)
        self.assertFalse(r["enrolled_regions_overlap_geometrically"])
        self.assertGreater(r["center_separation_km"],1000)
        self.assertEqual(r["shared_usgs_source_events"],[])
        self.assertEqual(len(r["modelled_aqi_comparisons"]),1)
        self.assertFalse(r["physical_colocation_verified"])
        self.assertEqual(r["cross_region_causation_claims"],0)

    def test_model_times_must_match_not_just_receive_close(self):
        self.capture(self.one)
        self.capture(self.two,at=BASE+timedelta(minutes=15),
                     quake_at=BASE-timedelta(minutes=10))
        r=self.query()
        self.assertEqual(r["modelled_aqi_comparisons"],[])
        self.assertEqual(len(r["shared_usgs_source_events"]),1)

    def test_same_provider_key_can_be_a_different_revision_across_regions(self):
        self.capture(self.one)
        self.capture(self.two)
        later=BASE+timedelta(minutes=20)
        armor.ingest_fixture(
            self.two,
            weather(later,60),
            earthquake("quake-shared",mag=3.5),
            db_path=self.path,now=later,
        )
        r=self.query()
        self.assertEqual(len(r["shared_usgs_source_events"]),1)
        item=r["shared_usgs_source_events"][0]
        self.assertTrue(item["revision_or_receipt_disagreement"])
        self.assertEqual(item["primary_magnitude"],3.1)
        self.assertEqual(item["secondary_magnitude"],3.5)
        self.assertEqual(item["independent_confirmations"],1)

    def test_one_region_stale_producing_sample_never_compares(self):
        self.capture(self.one)
        self.capture(self.two,air_status="stale",qstatus="unavailable")
        r=self.query()
        self.assertEqual(r["modelled_aqi_comparisons"],[])
        self.assertEqual(r["shared_usgs_source_events"],[])
        self.assertEqual(r["secondary"]["degraded_observation_count"],1)
        self.assertFalse(r["absence_is_not_an_all_clear"] is False)

    def test_unknown_and_no_samples_do_not_masquerade_as_all_clear(self):
        self.capture(self.one)
        r=self.query()
        self.assertFalse(r["comparison_eligible"])
        self.assertEqual(r["shared_usgs_source_events"],[])
        self.assertEqual(r["modelled_aqi_comparisons"],[])
        self.assertEqual(r["source_coverage"]["usgs_earthquakes"]["secondary"],
                         "not_checked")
        self.assertTrue(r["absence_is_not_an_all_clear"])

    def test_real_fixture_mixing_cannot_support_comparative_findings(self):
        self.capture(self.one)
        with patch.object(armor, "_clock",
                          return_value=BASE+timedelta(minutes=5)), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   return_value=weather()), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=earthquake()):
            armor.observe_once(self.two,db_path=self.path)
        r=self.query()
        self.assertFalse(r["comparison_eligible"])
        self.assertEqual(r["shared_usgs_source_events"],[])
        self.assertEqual(r["modelled_aqi_comparisons"],[])
        self.assertIn("Fixture and real-adapter",r["comparison_block_reason"])

    def test_replay_identity_stable_until_evidence_changes(self):
        self.capture(self.one)
        self.capture(self.two)
        a=self.query(now=BASE+timedelta(hours=1,minutes=5))
        b=self.query(now=BASE+timedelta(hours=3))
        self.assertEqual(a["query_id"],b["query_id"])
        self.assertEqual(a["query_plan"],b["query_plan"])
        later=BASE+timedelta(minutes=20)
        self.capture(self.two,at=later,aqi=60,
                     quake_at=BASE-timedelta(minutes=10))
        c=self.query()
        self.assertNotEqual(a["query_id"],c["query_id"])

    def test_explicit_as_known_cutoff_reconstructs_prior_revision(self):
        self.capture(self.one)
        self.capture(self.two)
        later=BASE+timedelta(minutes=20)
        self.capture(self.two,at=later,aqi=60,
                     quake_at=BASE-timedelta(minutes=10))
        old=self.query(as_known_at=(BASE+timedelta(minutes=1)).isoformat())
        new=self.query()
        self.assertFalse(old["shared_usgs_source_events"][0]["revision_or_receipt_disagreement"])
        self.assertFalse(new["shared_usgs_source_events"][0]["revision_or_receipt_disagreement"])
        self.assertEqual(len(old["modelled_aqi_comparisons"]),1)
        self.assertEqual(len(new["modelled_aqi_comparisons"]),1)

    def test_same_region_id_disallowed_and_disabled_mode_blocks(self):
        with self.assertRaises(ValueError):
            self.query(secondary_id=self.one)
        with patch.dict(os.environ,{"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
            with self.assertRaises(armor.ArmorDisabled):
                self.query()

    def test_expiry_and_invalid_or_future_window_fail_closed(self):
        self.capture(self.one)
        self.capture(self.two)
        for overrides in [
            {"secondary_id":"bad"},
            {"secondary_id":"0"*32},
            {"start_at":"2026-09-25T10:00:00"},
            {"start_at":"2026-09-25T13:00:00Z"},
            {"end_at":"2026-09-25T18:00:00Z"},
        ]:
            with self.subTest(overrides=overrides),self.assertRaises((KeyError,ValueError)):
                self.query(**overrides)
        with self.assertRaises(KeyError):
            self.query(now=BASE+timedelta(hours=25))


if __name__=="__main__":
    import unittest
    unittest.main()
