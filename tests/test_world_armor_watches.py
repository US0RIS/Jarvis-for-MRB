from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from jarvis_mrb import world_armor_phase1 as armor
from jarvis_mrb import world_armor_watches as watches

NOW = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)


def air() -> dict:
    return {
        "checked_at": NOW.isoformat(),
        "air_quality": {"status": "ok", "model_time_utc": NOW.isoformat(),
                        "us_aqi": 43},
        "weather_alerts": {"status": "ok", "alerts": []},
    }


def earthquakes() -> dict:
    return {"status": "ok", "checked_at": NOW.isoformat(), "events": []}


class WorldArmorStandingWatchTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "world_armor.sqlite3"
        enabled = patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "1",
        })
        enabled.start()
        self.addCleanup(enabled.stop)
        self.region = armor.create_investigation(
            "Selected public infrastructure", 34.12, -118.16,
            lifetime_hours=6, db_path=self.db, now=NOW,
        )["id"]

    def enroll(self, **kw):
        return watches.create_watch(
            self.region, interval_minutes=kw.pop("interval_minutes", 30),
            max_checks=kw.pop("max_checks", 2),
            lifetime_hours=kw.pop("lifetime_hours", 2),
            db_path=self.db, now=kw.pop("now", NOW), **kw,
        )

    def tick(self, at=NOW, *, conditions=None, quakes=None):
        with patch.object(armor, "_clock", return_value=at), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   return_value=conditions if conditions is not None else air()), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=quakes if quakes is not None else earthquakes()):
            return watches.run_due_once(db_path=self.db, now=at)

    def test_default_off_does_not_enroll_or_fetch(self):
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "0"
        }), patch("jarvis_mrb.physical_conditions.physical_conditions",
                 side_effect=AssertionError("provider called")):
            with self.assertRaises(armor.ArmorDisabled):
                self.enroll()
            with self.assertRaises(armor.ArmorDisabled):
                watches.run_due_once(db_path=self.db, now=NOW)
        self.assertEqual(watches.list_watches(db_path=self.db,now=NOW)["watches"], [])

    def test_typed_limits_expiry_and_remaining_investigation_budget(self):
        for interval in (0, 29, 361, True, "60"):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.enroll(interval_minutes=interval)
        for checks in (0, 13, True, "3"):
            with self.subTest(checks=checks), self.assertRaises(ValueError):
                self.enroll(max_checks=checks)
        for lifetime in (0, 73, True, "4"):
            with self.subTest(lifetime=lifetime), self.assertRaises(ValueError):
                self.enroll(lifetime_hours=lifetime)
        self.assertEqual(watches.list_watches(db_path=self.db,now=NOW)["watches"], [])
        bounded = self.enroll(lifetime_hours=72)
        self.assertEqual(bounded["expires_at"],
                         (NOW + timedelta(hours=6)).isoformat())
        self.assertEqual(bounded["check_count"], 0)
        self.assertFalse(bounded["notifications_enabled"])
        self.assertNotIn("lease_token", bounded)

    def test_two_local_ticks_stop_at_budget_without_auto_restart(self):
        watch = self.enroll()
        first = self.tick()
        self.assertEqual(first["outcome"], "sample_coverage_ok")
        self.assertEqual(first["sample_id"], armor.replay(
            self.region, db_path=self.db, now=NOW + timedelta(minutes=1)
        )["sample_timeline"][0]["id"])
        self.assertEqual(first["check_count"], 1)
        self.assertEqual(first["state"], "active")
        self.assertEqual(first["next_due_at"],
                         (NOW + timedelta(minutes=30)).isoformat())
        self.assertEqual(self.tick(at=NOW + timedelta(minutes=1))["reason"],
                         "no_due_authorized_watch")
        second = self.tick(at=NOW + timedelta(minutes=30))
        self.assertEqual(second["state"], "exhausted")
        self.assertEqual(second["check_count"], 2)
        self.assertEqual(self.tick(at=NOW + timedelta(hours=1))["reason"],
                         "no_due_authorized_watch")
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM watch_receipts WHERE watch_id=?",
                (watch["id"],),
            ).fetchone()[0], 2)

    def test_standing_watch_marks_source_report_delta_not_physical_onset(self):
        watch = self.enroll()
        first = self.tick()
        self.assertEqual(first["change_state"],
                         "baseline_or_incomparable_receipts")
        second_air = air()
        second_air["air_quality"]["us_aqi"] = 58
        second = self.tick(
            at=NOW + timedelta(minutes=30), conditions=second_air
        )
        self.assertEqual(second["outcome"], "sample_coverage_ok")
        self.assertEqual(second["change_state"], "retained_source_report_delta")
        self.assertEqual(second["last_change_state"],
                         "retained_source_report_delta")
        with closing(sqlite3.connect(self.db)) as con:
            rows = con.execute(
                "SELECT change_state FROM watch_receipts WHERE watch_id=? "
                "ORDER BY collected_at", (watch["id"],)
            ).fetchall()
        self.assertEqual([row[0] for row in rows], [
            "baseline_or_incomparable_receipts",
            "retained_source_report_delta",
        ])

    def test_repeated_identical_reports_do_not_claim_no_world_events(self):
        self.enroll()
        self.tick()
        second = self.tick(at=NOW + timedelta(minutes=30))
        self.assertEqual(
            second["change_state"],
            "no_report_delta_in_two_receipts_not_all_clear",
        )
        self.assertFalse(second.get("notifications_enabled", False))

    def test_partial_provider_retained_but_no_all_clear(self):
        self.enroll(max_checks=1)
        partial = air()
        partial["weather_alerts"]["status"] = "partial"
        result = self.tick(conditions=partial)
        self.assertEqual(result["outcome"], "sample_degraded_or_partial")
        self.assertEqual(result["change_state"], "coverage_degraded_or_unknown")
        self.assertEqual(result["state"], "exhausted")
        replay = armor.replay(self.region, db_path=self.db,
                              now=NOW + timedelta(minutes=1))
        self.assertEqual(replay["coverage"]["nws_point_alerts"]["status"],
                         "partial")

    def test_stop_during_http_prevents_late_observation_storage(self):
        watch = self.enroll()
        def revoke_inside_adapter(*args, **kwargs):
            stopped = watches.stop_watch(
                watch["id"], db_path=self.db, now=NOW
            )
            self.assertEqual(stopped["state"], "revoked")
            return air()
        with patch.object(armor, "_clock", return_value=NOW), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   side_effect=revoke_inside_adapter) as provider, \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=earthquakes()):
            result = watches.run_due_once(db_path=self.db, now=NOW)
        self.assertEqual(result["outcome"],
                         "revoked_or_superseded_no_watch_completion")
        self.assertEqual(provider.call_count, 1)
        stored = armor.replay(
            self.region, db_path=self.db, now=NOW + timedelta(minutes=1)
        )
        self.assertEqual(stored["samples_retained"], 0)
        self.assertEqual(self.tick(at=NOW + timedelta(hours=1))["reason"],
                         "no_due_authorized_watch")

    def test_pause_resume_revocation_and_disabled_cleanup(self):
        watch = self.enroll()
        paused = watches.pause_watch(watch["id"], db_path=self.db, now=NOW)
        self.assertEqual(paused["state"], "paused")
        self.assertEqual(self.tick()["reason"], "no_due_authorized_watch")
        resumed = watches.resume_watch(watch["id"], db_path=self.db,
                                       now=NOW + timedelta(minutes=1))
        self.assertEqual(resumed["state"], "active")
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "0",
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "0",
        }):
            self.assertEqual(len(watches.list_watches(
                db_path=self.db, investigation_id=self.region, now=NOW
            )["watches"]), 1)
            stopped = watches.stop_watch(watch["id"], db_path=self.db,
                                         now=NOW+timedelta(minutes=2))
            self.assertEqual(stopped["state"], "revoked")
            with self.assertRaises(armor.ArmorDisabled):
                watches.resume_watch(watch["id"], db_path=self.db)
        with self.assertRaises(ValueError):
            watches.resume_watch(watch["id"], db_path=self.db)
        self.assertEqual(self.tick()["reason"], "no_due_authorized_watch")

    def test_lease_prevents_duplicate_due_claim(self):
        watch = self.enroll()
        first = watches._claim(self.db, NOW)
        second = watches._claim(self.db, NOW)
        self.assertEqual(first["id"], watch["id"])
        self.assertIsNone(second)
        with closing(sqlite3.connect(self.db)) as con:
            count = con.execute(
                "SELECT check_count FROM watches WHERE id=?", (watch["id"],)
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_region_forget_cascades_watch_grant_and_receipt(self):
        watch = self.enroll(max_checks=1)
        self.tick()
        self.assertEqual(armor.forget(self.region, db_path=self.db)["deleted"],
                         1)
        self.assertEqual(watches.list_watches(db_path=self.db,now=NOW)["watches"], [])
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM watch_receipts WHERE watch_id=?",
                (watch["id"],),
            ).fetchone()[0], 0)

    def test_watch_grant_forget_does_not_delete_region_samples(self):
        watch = self.enroll(max_checks=1)
        self.tick()
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "0",
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "0",
        }):
            result = watches.forget_watch(watch["id"], db_path=self.db)
            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["investigation_samples_deleted"], 0)
            self.assertEqual(watches.forget_watch(
                watch["id"], db_path=self.db,
            )["deleted"], 0)
        replayed = armor.replay(
            self.region, db_path=self.db,
            now=NOW + timedelta(minutes=1),
        )
        self.assertEqual(replayed["samples_retained"], 1)
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM watch_receipts WHERE watch_id=?",
                (watch["id"],),
            ).fetchone()[0], 0)

    def test_does_not_start_background_thread_or_provider_on_creation(self):
        with patch("jarvis_mrb.physical_conditions.physical_conditions",
                   side_effect=AssertionError("background collection")):
            watch = self.enroll(max_checks=1)
            self.assertFalse(watch["notifications_enabled"])
            self.assertFalse(watches.list_watches(
                db_path=self.db, now=NOW
            )["runner_auto_started"])


if __name__ == "__main__":
    import unittest
    unittest.main()
