from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from jarvis_mrb import world_armor_attention as attention
from jarvis_mrb import world_armor_phase1 as armor
from jarvis_mrb import world_armor_watches as watches

NOW = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)


def conditions(at=NOW, *, aqi=43, status="ok", alerts=None,
               nws_status="ok"):
    return {
        "checked_at": at.isoformat(),
        "air_quality": {
            "status": status, "us_aqi": aqi, "model_time_utc": at.isoformat(),
        },
        "weather_alerts": {
            "status": nws_status, "alerts": alerts if alerts is not None else [],
        },
    }


def quakes(at=NOW, events=None, status="ok"):
    return {"status": status, "checked_at": at.isoformat(),
            "events": events if events is not None else []}


def quake(identifier, at=NOW, magnitude=4.1):
    return {"id": identifier, "magnitude": magnitude,
            "occurred_at": at.isoformat(),
            "place": "bounded query region", "source_url":
                "https://earthquake.usgs.gov/"}


class WorldArmorAttentionTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "armor.sqlite3"
        env = patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        self.region = armor.create_investigation(
            "User-enrolled public region", 34.12, -118.16,
            db_path=self.db, now=NOW,
        )["id"]

    def enroll(self, kind, threshold=None, *, cooldown=30, checks=5):
        return watches.create_watch(
            self.region, interval_minutes=30,
            max_checks=checks, lifetime_hours=6,
            attention_kind=kind, attention_threshold=threshold,
            attention_cooldown_minutes=cooldown,
            db_path=self.db, now=NOW,
        )

    def tick(self, at, *, air=None, earthquake=None, callback=None):
        with patch.object(armor, "_clock", return_value=at), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   side_effect=callback,
                   return_value=air if air is not None
                   else conditions(at)), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=earthquake if earthquake is not None
                   else quakes(at)):
            return watches.run_due_once(db_path=self.db, now=at)

    def inbox(self, *, at=NOW + timedelta(hours=3), **kw):
        return attention.list_notices(
            investigation_id=self.region, db_path=self.db, now=at, **kw,
        )

    def test_typed_rules_reject_unknown_and_invalid_ranges(self):
        for kind, threshold in [
            ("arbitrary_python", 100), ("modelled_aqi_threshold_crossed", None),
            ("modelled_aqi_threshold_crossed", 500), ("new_usgs_report", 1),
            ("new_usgs_report", float("nan")), ("off", 42),
            ("new_nws_alert", 100),
        ]:
            with self.subTest(kind=kind, threshold=threshold), self.assertRaises(ValueError):
                self.enroll(kind, threshold)
        for cooldown in (0, 29, 361, True, "60"):
            with self.subTest(cooldown=cooldown), self.assertRaises(ValueError):
                self.enroll("new_nws_alert", cooldown=cooldown)
        self.assertEqual(watches.list_watches(
            db_path=self.db, now=NOW,
        )["watches"], [])

    def test_opt_in_off_by_default_no_notice_even_when_reports_change(self):
        self.enroll("off", checks=2)
        self.tick(NOW)
        self.tick(NOW + timedelta(minutes=30),
                  air=conditions(NOW + timedelta(minutes=30), aqi=152))
        self.assertEqual(self.inbox()["notices"], [])

    def test_aqi_crossing_creates_one_traceable_notice_after_baseline(self):
        watch = self.enroll("modelled_aqi_threshold_crossed", 100, checks=3)
        first = self.tick(NOW)
        self.assertEqual(first["notices_created"], 0)
        second_at = NOW + timedelta(minutes=30)
        second = self.tick(second_at,
                           air=conditions(second_at, aqi=113))
        self.assertEqual(second["notices_created"], 1)
        self.assertEqual(second["attention_state"], "inbox_notice_saved")
        notice = self.inbox()["notices"][0]
        self.assertEqual(notice["watch_id"], watch["id"])
        self.assertEqual(notice["sample_id"], second["sample_id"])
        self.assertEqual(notice["source"], "openmeteo_model")
        self.assertEqual(notice["kind"], "modelled_aqi_threshold_crossed")
        self.assertIn("Modelled US AQI crossed", notice["summary"])
        self.assertNotIn("user-enrolled public region", notice["summary"].lower())
        self.assertIsNone(notice["read_at"])
        self.assertEqual(self.inbox()["unread_count"], 1)
        third_at = NOW + timedelta(minutes=60)
        third = self.tick(third_at,
                          air=conditions(third_at, aqi=121))
        self.assertEqual(third["notices_created"], 0)
        self.assertEqual(self.inbox()["unread_count"], 1)

    def test_aqi_freshness_and_partial_coverage_prevent_notice(self):
        self.enroll("modelled_aqi_threshold_crossed", 100, checks=2)
        self.tick(NOW)
        second = NOW + timedelta(minutes=30)
        self.tick(second, air=conditions(second, aqi=150, status="stale"))
        self.assertEqual(self.inbox()["notices"], [])

    def test_nws_requires_newly_received_identifier_not_receipt_baseline(self):
        self.enroll("new_nws_alert", checks=3)
        old = {"id": "NWS-1", "event": "Wind Advisory",
               "severity": "Moderate"}
        first = self.tick(NOW, air=conditions(NOW, alerts=[old]))
        self.assertEqual(first["notices_created"], 0)
        moment = NOW + timedelta(minutes=30)
        newer = {"id": "NWS-2", "event": "Heat Advisory",
                 "severity": "Severe"}
        second = self.tick(moment,
                           air=conditions(moment, alerts=[old, newer]))
        self.assertEqual(second["notices_created"], 1)
        notice = self.inbox()["notices"][0]
        self.assertEqual(notice["source_key"], "NWS-2")
        self.assertIsNone(notice["observed_at"])
        self.assertIn("not retained", notice["summary"])
        moment += timedelta(minutes=30)
        third = self.tick(moment,
                          air=conditions(moment, alerts=[old, newer]))
        self.assertEqual(third["notices_created"], 0)

    def test_usgs_report_requires_real_recent_magnitude_threshold(self):
        self.enroll("new_usgs_report", 4.0, checks=4)
        first = self.tick(NOW, earthquake=quakes(
            NOW, [quake("old", NOW, 4.2)]
        ))
        self.assertEqual(first["notices_created"], 0)
        moment = NOW + timedelta(minutes=30)
        second = self.tick(moment, earthquake=quakes(moment, [
            quake("old", NOW, 4.2), quake("small", moment, 3.7),
        ]))
        self.assertEqual(second["notices_created"], 0)
        moment += timedelta(minutes=30)
        third = self.tick(moment, earthquake=quakes(moment, [
            quake("old", NOW, 4.2), quake("small", moment, 3.7),
            quake("large", moment, 4.4),
        ]))
        self.assertEqual(third["notices_created"], 1)
        notice = self.inbox()["notices"][0]
        self.assertEqual(notice["source_key"], "large")
        self.assertEqual(notice["observed_at"], moment.isoformat())
        self.assertIn("First received", notice["summary"])

    def test_cooldown_suppresses_different_new_nws_reports(self):
        self.enroll("new_nws_alert", cooldown=120, checks=3)
        self.tick(NOW)
        first = NOW + timedelta(minutes=30)
        self.assertEqual(self.tick(
            first, air=conditions(first, alerts=[
                {"id": "A", "event": "Wind Advisory"}
            ])
        )["notices_created"], 1)
        second = NOW + timedelta(minutes=60)
        result = self.tick(second, air=conditions(second, alerts=[
            {"id": "A", "event": "Wind Advisory"},
            {"id": "B", "event": "Heat Advisory"},
        ]))
        self.assertEqual(result["attention_state"], "cooldown_suppressed")
        self.assertEqual(self.inbox()["unread_count"], 1)

    def test_degraded_nws_while_usgs_healthy_blocks_nws_only(self):
        self.enroll("new_nws_alert", checks=2)
        self.tick(NOW)
        second = NOW + timedelta(minutes=30)
        result = self.tick(second, air=conditions(
            second, nws_status="partial",
            alerts=[{"id": "unverified", "event": "Flood Warning"}],
        ))
        self.assertEqual(result["outcome"], "sample_degraded_or_partial")
        self.assertEqual(result["notices_created"], 0)

    def test_fixture_samples_never_generate_notifications(self):
        self.enroll("modelled_aqi_threshold_crossed", 100)
        armor.ingest_fixture(
            self.region, conditions(NOW, aqi=45), quakes(NOW),
            db_path=self.db, now=NOW,
        )
        moment = NOW + timedelta(minutes=30)
        result = self.tick(moment, air=conditions(moment, aqi=120))
        self.assertEqual(result["notices_created"], 0)

    def test_revocation_during_http_blocks_sample_and_notice(self):
        watch = self.enroll("new_nws_alert")
        self.tick(NOW)
        moment = NOW + timedelta(minutes=30)
        def revoke(*args, **kwargs):
            watches.stop_watch(watch["id"], db_path=self.db, now=moment)
            return conditions(moment, alerts=[
                {"id": "late", "event": "Heat Warning"},
            ])
        result = self.tick(moment, callback=revoke)
        self.assertFalse(result["sample_saved"])
        self.assertEqual(result["notices_created"], 0)
        self.assertEqual(self.inbox()["notices"], [])

    def test_read_and_forget_work_after_feature_flag_revocation(self):
        self.enroll("new_nws_alert", checks=2)
        self.tick(NOW)
        second = NOW + timedelta(minutes=30)
        self.tick(second, air=conditions(second, alerts=[
            {"id": "NWS-A", "event": "Heat Advisory"},
        ]))
        ident = self.inbox()["notices"][0]["id"]
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "0",
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "0",
        }):
            read = attention.mark_read(
                ident, db_path=self.db, now=NOW + timedelta(hours=1),
            )
            self.assertIsNotNone(read["read_at"])
            self.assertEqual(self.inbox()["unread_count"], 0)
            self.assertEqual(attention.forget_notice(
                ident, db_path=self.db,
            )["deleted"], 1)
            self.assertEqual(attention.forget_notice(
                ident, db_path=self.db,
            )["deleted"], 0)
        self.assertEqual(armor.replay(
            self.region, db_path=self.db,
            now=NOW + timedelta(hours=2),
        )["samples_retained"], 2)

    def test_watch_and_region_forget_cascade_attention_inbox(self):
        watch = self.enroll("new_nws_alert", checks=2)
        self.tick(NOW)
        moment = NOW + timedelta(minutes=30)
        self.tick(moment, air=conditions(moment, alerts=[
            {"id": "NWS-B", "event": "Wind Advisory"}
        ]))
        self.assertEqual(self.inbox()["unread_count"], 1)
        self.assertEqual(watches.forget_watch(
            watch["id"], db_path=self.db,
        )["deleted"], 1)
        self.assertEqual(self.inbox()["unread_count"], 0)
        self.assertEqual(armor.replay(
            self.region, db_path=self.db,
            now=NOW + timedelta(hours=1),
        )["samples_retained"], 2)

    def test_empty_store_does_not_initialize_or_contact_providers(self):
        absent = self.db.with_name("missing.sqlite3")
        result = attention.list_notices(db_path=absent)
        self.assertFalse(absent.exists())
        self.assertEqual(result["unread_count"], 0)
        self.assertEqual(result["delivery"], "private_inbox_only_no_remote_push")
