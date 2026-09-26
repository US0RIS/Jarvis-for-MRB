from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import os
import sqlite3

from jarvis_mrb import world_armor_phase1 as armor

NOW = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)


def conditions(*, aqi=44.0, model=None, status="ok", nws_status="ok", alerts=None):
    return {
        "checked_at": NOW.isoformat(),
        "air_quality": {"status": status, "us_aqi": aqi,
                        "model_time_utc": (model or NOW).isoformat()},
        "weather_alerts": {
            "status": nws_status,
            "alerts": alerts if alerts is not None else [
                {"id": "official-weather-42", "event": "Wind Advisory",
                 "headline": "Conditions may change", "severity": "Moderate",
                 "expires": (NOW+timedelta(hours=4)).isoformat()}
            ],
        },
    }


def quakes(*, mag=3.1, status="ok", events=None):
    return {
        "status":status,"checked_at":NOW.isoformat(),
        "events": events if events is not None else [
            {"id":"us-123","magnitude":mag,
             "place":"12 km from sample area",
             "occurred_at":(NOW-timedelta(hours=1)).isoformat(),
             "reviewed":False, "source_url":"https://earthquake.usgs.gov/"}
        ],
    }


class WorldArmorKernelTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/"world_armor.sqlite3"
        self.env = patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def new(self, **kwargs):
        return armor.create_investigation("Test corridor",34.12,-118.16,
                    db_path=self.db,now=NOW,**kwargs)["id"]

    def ingest(self, key, air=None, quake=None, time=None):
        return armor.ingest_fixture(key,
            air if air is not None else conditions(),
            quake if quake is not None else quakes(),
            db_path=self.db,now=time or NOW)

    def replay(self, key, *, at=None, now=None):
        return armor.replay(key,db_path=self.db,
                            as_known_at=at,now=now or NOW+timedelta(hours=1))

    def test_default_off_blocks_create_and_no_database_is_created(self):
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
            self.assertFalse(armor.capabilities()["enabled"])
            with self.assertRaises(armor.ArmorDisabled):
                self.new()
        self.assertFalse(self.db.exists())

    def test_explicit_optin_creates_separate_bounded_database_but_no_collection(self):
        key=self.new()
        self.assertTrue(self.db.is_file())
        rows=armor.list_investigations(db_path=self.db,now=NOW)["investigations"]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["id"],key)
        self.assertEqual(rows[0]["sample_count"],0)
        self.assertEqual(self.replay(key)["mode"],"no_samples")
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute("select count(*) from coverage").fetchone()[0],0)

    def test_reject_invalid_region_and_labels_and_ttl(self):
        for lat,lon,radius in [(float("nan"),0,20),(91,0,20),
                               (0,181,20),(0,0,101),(0,0,0)]:
            with self.subTest((lat,lon,radius)),self.assertRaises(ValueError):
                armor.create_investigation("A",lat,lon,radius_km=radius,db_path=self.db,now=NOW)
        for title in ("", "\n", "X"*121):
            with self.subTest(title),self.assertRaises(ValueError):
                armor.create_investigation(title,34,-118,db_path=self.db,now=NOW)
        with self.assertRaises(ValueError):
            self.new(lifetime_hours=0)
        with self.assertRaises(ValueError):
            self.new(lifetime_hours=73)

    def test_one_capture_preserves_three_source_families_and_unknown_observation_time(self):
        key=self.new()
        receipt=self.ingest(key)
        self.assertEqual(receipt["new_observations"],3)
        self.assertEqual(receipt["mode"],"fixture")
        view=self.replay(key)
        self.assertEqual(view["observation_count"],3)
        self.assertEqual(view["mode"],"fixture_only")
        self.assertTrue(view["coverage_complete_for_integrated_sources"])
        providers={r["source"]:r for r in view["observations"]}
        self.assertEqual(set(providers),set(armor._PROVIDERS))
        self.assertEqual(providers["openmeteo_model"]["observed_at"],NOW.isoformat())
        self.assertEqual(providers["openmeteo_model"]["geometry_basis"],
                         "query_point_model_grid_not_local_sensor")
        self.assertIsNone(providers["nws_point_alerts"]["observed_at"])
        self.assertIsNone(providers["nws_point_alerts"]["published_at"])
        self.assertEqual(providers["usgs_earthquakes"]["observed_at"],
                         (NOW-timedelta(hours=1)).isoformat())
        self.assertNotIn("all_hazards_clear",str(view))

    def test_no_fabricated_no_events_when_provider_unavailable(self):
        key=self.new()
        receipt=self.ingest(key,air=conditions(nws_status="unsupported_region",
                                                status="unavailable"),
                                  quake=quakes(status="unavailable"))
        self.assertEqual(receipt["new_observations"],0)
        self.assertFalse(receipt["all_sources_available"])
        view=self.replay(key)
        self.assertEqual(view["observation_count"],0)
        self.assertFalse(view["coverage_complete_for_integrated_sources"])
        self.assertEqual(view["coverage"]["nws_point_alerts"]["status"],
                         "unsupported_region")
        self.assertEqual(view["coverage"]["usgs_earthquakes"]["status"],
                         "unavailable")
        self.assertTrue(view["unknown_is_not_all_clear"])

    def test_replay_as_known_before_and_after_provider_revision(self):
        key=self.new()
        self.ingest(key,time=NOW)
        later=NOW+timedelta(minutes=10)
        updated=conditions(aqi=65,model=later)
        updated["weather_alerts"]["alerts"][0]["headline"]="Updated warning"
        self.ingest(key,air=updated,quake=quakes(mag=3.3),time=later)
        early=self.replay(key,at=(NOW+timedelta(minutes=1)).isoformat())
        after=self.replay(key,at=(later+timedelta(seconds=1)).isoformat())
        self.assertEqual(early["samples_retained"],1)
        self.assertEqual(early["observation_count"],3)
        self.assertEqual(after["samples_retained"],2)
        self.assertEqual(after["observation_count"],4)
        self.assertEqual(len(after["revisions"]),2)
        quake_after=next(x for x in after["observations"]
                         if x["source"]=="usgs_earthquakes")
        quake_before=next(x for x in early["observations"]
                          if x["source"]=="usgs_earthquakes")
        self.assertEqual(quake_after["values"]["magnitude"],3.3)
        self.assertEqual(quake_before["values"]["magnitude"],3.1)
        self.assertEqual(quake_after["supersedes_id"],quake_before["id"])
        self.assertEqual(quake_after["revision"],2)
        self.assertEqual(min(row["received_at"] for row in after["observations"]),
                         NOW.isoformat())

    def test_source_revision_reversion_is_new_evidence_not_old_duplicate(self):
        key=self.new()
        self.ingest(key,time=NOW)
        self.ingest(key,quake=quakes(mag=3.3),
                    time=NOW+timedelta(minutes=10))
        self.ingest(key,quake=quakes(mag=3.1),
                    time=NOW+timedelta(minutes=20))
        current=self.replay(key)
        quake=next(x for x in current["observations"]
                   if x["source"]=="usgs_earthquakes")
        self.assertEqual(quake["values"]["magnitude"],3.1)
        self.assertEqual(quake["revision"],3)
        self.assertEqual(len(current["revisions"]),2)
        older=self.replay(
            key,at=(NOW+timedelta(minutes=15)).isoformat())
        self.assertEqual(next(x for x in older["observations"]
                        if x["source"]=="usgs_earthquakes")["revision"],2)

    def test_malformed_success_body_is_unavailable_not_a_zero_observation(self):
        key=self.new()
        bad=conditions()
        bad["weather_alerts"]["alerts"]="invalid"
        q=quakes()
        q["events"]=None
        self.ingest(key,air=bad,quake=q)
        view=self.replay(key)
        self.assertEqual(view["coverage"]["nws_point_alerts"]["status"],"unavailable")
        self.assertEqual(view["coverage"]["usgs_earthquakes"]["status"],"unavailable")
        self.assertFalse(view["coverage_complete_for_integrated_sources"])

    def test_future_dated_air_and_earthquake_not_presented_as_current(self):
        key=self.new()
        future=NOW+timedelta(hours=2)
        bad=conditions(model=future)
        q=quakes(events=[{
            "id":"future-usgs","magnitude":3.2,
            "occurred_at":future.isoformat()}])
        self.ingest(key,air=bad,quake=q)
        view=self.replay(key)
        self.assertEqual({x["source"] for x in view["observations"]},
                         {"nws_point_alerts"})
        self.assertFalse(view["coverage_complete_for_integrated_sources"])

    def test_duplicate_capture_is_idempotent_for_observations_not_for_collection(self):
        key=self.new()
        self.ingest(key,time=NOW)
        receipt=self.ingest(key,time=NOW+timedelta(seconds=10))
        self.assertEqual(receipt["new_observations"],0)
        view=self.replay(key)
        self.assertEqual(view["samples_retained"],2)
        self.assertEqual(view["observation_count"],3)
        self.assertEqual(len(view["revisions"]),0)

    def test_data_validation_never_stores_nan_or_missing_source_time_as_now(self):
        key=self.new()
        air=conditions(aqi=float("nan"))
        quake=quakes(events=[{"id":"us-a","magnitude":2.9,
                              "occurred_at":"missing time"}])
        self.ingest(key,air=air,quake=quake)
        v=self.replay(key)
        self.assertEqual(v["observation_count"],1)
        self.assertIsNone(v["observations"][0]["observed_at"])
        self.assertEqual(v["coverage"]["openmeteo_model"]["status"],"unavailable")

    def test_limit_12_active_investigations_and_delete_when_off(self):
        ids=[self.new() for _ in range(12)]
        with self.assertRaises(ValueError):
            self.new()
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
            receipt=armor.forget(ids[0],db_path=self.db)
            self.assertEqual(receipt["deleted"],1)
            self.assertEqual(armor.forget(ids[0],db_path=self.db)["deleted"],0)
        self.new()

    def test_feature_off_still_allows_listing_for_explicit_deletion(self):
        key=self.new()
        self.ingest(key)
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
            records=armor.list_investigations(db_path=self.db,now=NOW)
            self.assertEqual([x["id"] for x in records["investigations"]],[key])
            with self.assertRaises(armor.ArmorDisabled):
                self.ingest(key,time=NOW+timedelta(minutes=5))
            with self.assertRaises(armor.ArmorDisabled):
                self.replay(key)
            self.assertEqual(armor.forget(key,db_path=self.db)["deleted"],1)
        self.assertEqual(armor.list_investigations(
            db_path=self.db,now=NOW)["investigations"],[])

    def test_expiry_prunes_rows_and_child_rows_without_claiming_backup_erasure(self):
        key=self.new(lifetime_hours=1)
        self.ingest(key)
        with self.assertRaises(KeyError):
            self.replay(key,now=NOW+timedelta(hours=2))
        rows=armor.list_investigations(db_path=self.db,
                 now=NOW+timedelta(hours=2))["investigations"]
        self.assertEqual(rows,[])
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute("select count(*) from observations").fetchone()[0],0)

    def test_invalid_replay_time_and_identifier_fail_closed(self):
        key=self.new()
        with self.assertRaises(ValueError):
            self.replay(key,at="2026-09-24T21:00:00")
        with self.assertRaises(ValueError):
            self.replay(key,at=(NOW+timedelta(days=2)).isoformat())
        with self.assertRaises(ValueError):
            self.replay("../wrong")
        with self.assertRaises(KeyError):
            self.replay("0"*32)

    def test_one_shot_runs_only_existing_two_bounded_adapters(self):
        key=self.new()
        with patch.object(armor, "_clock",
                          return_value=NOW+timedelta(minutes=5)), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   return_value=conditions()) as p, \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=quakes()) as q:
            receipt=armor.observe_once(key,db_path=self.db)
        p.assert_called_once_with(34.12,-118.16)
        q.assert_called_once_with(34.12,-118.16,radius_km=30.0,
                                  hours=24,minimum_magnitude=2.5)
        self.assertEqual(receipt["mode"],"real_adapter")
        # A controlled clock keeps this test valid after the fixture date.
        self.assertEqual(self.replay(key)["mode"],"real_adapter_only")
        self.assertEqual(receipt["new_observations"],3)

    def test_one_provider_exception_does_not_hide_other_sources(self):
        key=self.new()
        with patch.object(armor, "_clock",
                          return_value=NOW+timedelta(minutes=5)), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   side_effect=RuntimeError("provider failed")), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=quakes()):
            receipt=armor.observe_once(key,db_path=self.db)
        self.assertEqual(receipt["new_observations"],1)
        self.assertEqual(receipt["coverage"][0]["status"],"unavailable")
        self.assertEqual(receipt["coverage"][2]["status"],"ok")


    def test_changes_requires_two_receipts_not_a_fabricated_baseline(self):
        key=self.new()
        empty=armor.compare_recent(key,db_path=self.db,
                                   now=NOW+timedelta(minutes=30))
        self.assertEqual(empty["comparison"],
                         "requires_two_distinct_received_samples")
        self.assertEqual(empty["source_record_changes"],[])
        self.ingest(key)
        one=armor.compare_recent(key,db_path=self.db,
                                 now=NOW+timedelta(minutes=30))
        self.assertIsNone(one["modelled_air_quality_change"])
        self.assertFalse(one["disappearances_inferred"])

    def test_changes_model_measurement_and_revision_and_first_received_event(self):
        key=self.new()
        self.ingest(key,time=NOW)
        later=NOW+timedelta(minutes=10)
        updated=conditions(aqi=65,model=later)
        updated["weather_alerts"]["alerts"][0]["headline"]="Alert source revised headline"
        newer_quakes=quakes(events=quakes()["events"]+[{
            "id":"us-456","magnitude":2.8,"place":"Previous hours",
            "occurred_at":(NOW-timedelta(hours=2)).isoformat(),
            "reviewed":True,"source_url":"https://earthquake.usgs.gov/",
        }])
        self.ingest(key,air=updated,quake=newer_quakes,time=later)
        changed=armor.compare_recent(key,db_path=self.db,
                                     now=NOW+timedelta(minutes=30))
        self.assertEqual(changed["comparison"],"two_received_samples")
        aqi=changed["modelled_air_quality_change"]
        self.assertEqual((aqi["before"],aqi["after"],aqi["delta"]),(44,65,21))
        self.assertEqual(aqi["after_model_at"],later.isoformat())
        changes=changed["source_record_changes"]
        self.assertEqual(len(changes),2)
        self.assertEqual({x["kind"] for x in changes},
                         {"source_record_revision",
                          "newly_received_record_not_newly_occurred_event"})
        fresh=next(x for x in changes if x["record_key"]=="us-456")
        self.assertIn("not proof of onset",fresh["note"])
        self.assertEqual(fresh["observed_at"],
                         (NOW-timedelta(hours=2)).isoformat())
        self.assertFalse(changed["disappearances_inferred"])
        self.assertEqual(changed["causal_claims"],0)

    def test_changes_never_turn_provider_outage_into_world_event(self):
        key=self.new()
        self.ingest(key,time=NOW)
        self.ingest(key,air=conditions(aqi=44,nws_status="unavailable"),
                    quake=quakes(status="unavailable"),
                    time=NOW+timedelta(minutes=15))
        changed=armor.compare_recent(key,db_path=self.db,
                                     now=NOW+timedelta(minutes=30))
        self.assertEqual(changed["sources_with_comparable_coverage"],
                         ["openmeteo_model"])
        self.assertEqual(
            {x["source"] for x in changed["source_changes"]},
            {"nws_point_alerts","usgs_earthquakes"},
        )
        self.assertEqual(changed["source_record_changes"],[])
        self.assertIn("all-clear",changed["qualifier"])
        self.assertEqual(changed["modelled_air_quality_change"],None)

    def test_changes_duplicate_reports_never_claim_world_delta(self):
        key=self.new()
        self.ingest(key,time=NOW)
        self.ingest(key,time=NOW+timedelta(minutes=10))
        changed=armor.compare_recent(key,db_path=self.db,
                                     now=NOW+timedelta(minutes=30))
        self.assertEqual(changed["source_record_changes"],[])
        self.assertIsNone(changed["modelled_air_quality_change"])
        self.assertEqual(changed["sources_with_comparable_coverage"],
                         sorted(armor._PROVIDERS))



if __name__ == "__main__":
    import unittest
    unittest.main()
