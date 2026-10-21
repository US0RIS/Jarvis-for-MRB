from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.external_watches as ew
import jarvis_mrb.proactive_attention as attention
import jarvis_mrb.saved_places as saved_places
import jarvis_mrb.voice_watches as vw
import jarvis_mrb.world_armor_push as push
import jarvis_mrb.world_model as world_model
from jarvis_mrb import event_bus, voice_router
from jarvis_mrb.voice_router import turn_context

NOW = datetime(2026, 10, 21, 15, 10).astimezone()
PUSH_ENV = {
    "JARVIS_WORLD_ARMOR_ENABLED": "1",
    "JARVIS_WORLD_ARMOR_PUSH_ENABLED": "1",
    "JARVIS_APNS_TEAM_ID": "TEAM123456",
    "JARVIS_APNS_KEY_ID": "KEY1234567",
    "JARVIS_APNS_BUNDLE_ID": "com.example.horus",
    "JARVIS_APNS_KEY_FILE": "/not-read-in-tests.p8",
}


def fix(minutes_old: float = 1, lat: float = 37.77, lon: float = -122.42) -> dict:
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes_old)).isoformat()
    return {"latitude": lat, "longitude": lon, "location_accuracy_m": 25, "location_captured_at": stamp}


def nws_alert(ident, event="Flood Watch", severity="Moderate", urgency="Expected", headline=""):
    return {"id": ident, "event": event, "headline": headline or f"{event} issued for the county",
            "severity": severity, "urgency": urgency, "instruction": "", "expires": "2026-10-21T22:00:00+00:00",
            "sender": "National Weather Service"}


def nws_evidence(*alerts):
    payload = {"status": "ok", "alerts": list(alerts), "checked_at": "2026-10-21T15:20:00+00:00",
               "source_url": "https://www.weather.gov/documentation/services-web-api"}
    return {"status": "ok", "summary": f"{len(alerts)} active NWS point alerts",
            "source_url": payload["source_url"], "observed_at": payload["checked_at"],
            "signature": sorted(a["id"] for a in alerts), "payload": payload}


def quake(ident, mag, place="5 km SW of Ridgecrest, CA", lat=35.6, lon=-117.7):
    return {"id": ident, "magnitude": mag, "latitude": lat, "longitude": lon, "place": place,
            "occurred_at": "2026-10-21T15:00:00+00:00", "source_url": "https://earthquake.usgs.gov/e/" + ident,
            "reviewed": False}


def quake_evidence(*events):
    payload = {"status": "ok", "events": list(events), "checked_at": "2026-10-21T15:20:00+00:00",
               "source_url": "https://earthquake.usgs.gov/earthquakes/feed/"}
    return {"status": "ok", "summary": "quakes", "source_url": payload["source_url"],
            "observed_at": payload["checked_at"], "signature": sorted(e["id"] for e in events), "payload": payload}


def aqi_evidence(aqi, threshold=100):
    air = {"status": "ok", "us_aqi": aqi, "model_time_utc": "2026-10-21T15:00:00+00:00",
           "source_url": "https://open-meteo.com/en/docs/air-quality-api"}
    band = "above_threshold" if aqi >= threshold else "below_threshold"
    return {"status": "ok", "summary": f"AQI {aqi}", "source_url": air["source_url"],
            "observed_at": air["model_time_utc"], "signature": band, "payload": {"air_quality": air}}


class Isolated(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old = (world_model.APP_DIR, world_model.DB_PATH, saved_places.DB_PATH, push.PUSH_STORE)
        root = Path(self.temp.name)
        world_model.APP_DIR = root
        world_model.DB_PATH = root / "world_model.sqlite3"
        saved_places.DB_PATH = root / "saved_places.sqlite3"
        push.PUSH_STORE = root / "push.sqlite3"
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for key in list(PUSH_ENV) + ["JARVIS_APNS_ENVIRONMENT"]:
            os.environ.pop(key, None)
        self.notify = patch.object(event_bus, "emit_proactive")
        self.emit = self.notify.start()
        ew._RUNNER["last_tick"] = None

    def tearDown(self) -> None:
        self.notify.stop()
        self.env.stop()
        (world_model.APP_DIR, world_model.DB_PATH, saved_places.DB_PATH, push.PUSH_STORE) = self.old
        self.temp.cleanup()

    def say(self, text: str, context=None, session="sess", now=None) -> str | None:
        with turn_context(session, context) as turn:
            return vw.handle(text, turn)

    def expire_row(self, watch_id: str, when: datetime) -> None:
        with ew._database() as conn:
            conn.execute("UPDATE watches SET expires_at=? WHERE id=?", (when.astimezone(timezone.utc).isoformat(), watch_id))

    def only_watch(self, kind: str | None = None) -> dict:
        rows = [w for w in ew.list_watches("personal") if kind is None or w["kind"] == kind]
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def check(self, watch, evidence):
        with patch.object(ew, "_fetch", return_value=evidence):
            return ew.check_watch(watch["id"], "personal")


class CompileTests(Isolated):
    def test_severe_weather_near_saved_home_for_three_hours(self) -> None:
        saved_places.save_place("home", 37.77, -122.42)
        with turn_context("c1", None) as turn:
            result = vw.compile_utterance(
                "Watch for new severe weather alerts near home for the next three hours", turn, now=NOW)
        self.assertEqual(result.status, "ok")
        plan = result.plans[0]
        self.assertEqual(plan.kind, "nws_alerts")
        self.assertEqual(plan.place_label, "home")
        self.assertEqual(plan.place_provenance, "saved_place")
        self.assertEqual(plan.expires_at, NOW + timedelta(hours=3))
        self.assertEqual(plan.interval_seconds, 900)
        reply = self.say("Watch for new severe weather alerts near home for the next three hours")
        self.assertIn("official NWS alerts", reply)
        self.assertIn("every 15 minutes", reply)
        self.assertIn("Say 'cancel the weather watch' anytime.", reply)
        watch = self.only_watch("nws_alerts")
        self.assertEqual(watch["config"]["latitude"], 37.77)
        self.assertEqual(watch["state"], "active")
        self.assertEqual(vw.get_meta(watch["id"])["place_label"], "home")

    def test_confirmation_does_not_claim_monitoring_when_runner_is_not_running(self) -> None:
        saved_places.save_place("home", 37.77, -122.42)
        reply = self.say("watch for severe weather alerts near home for two hours")
        self.assertIn("has not checked in", reply)
        ew._RUNNER["last_tick"] = datetime.now(timezone.utc)
        self.assertNotIn("has not checked in", self.say("watch for earthquakes near home for two hours"))

    def test_no_location_asks_one_clarification_and_stores_nothing(self) -> None:
        reply = self.say("Watch for new severe weather alerts near me for the next three hours")
        self.assertIn("I don't have your location", reply)
        self.assertIn("near home", reply)
        self.assertEqual(ew.list_watches("personal"), [])
        stale = self.say("tell me if there's an earthquake near me tonight", fix(minutes_old=90))
        self.assertIn("I don't have your location", stale)
        self.assertIn("90 minutes old", stale)
        self.assertEqual(ew.list_watches("personal"), [])

    def test_named_place_not_saved_is_not_guessed_from_phone_fix(self) -> None:
        reply = self.say("watch for severe weather near home for two hours", fix())
        self.assertIn("don't have home saved", reply)
        self.assertEqual(ew.list_watches("personal"), [])
        other = self.say("watch the airspace near the airport for two hours", fix())
        self.assertIn("can't look up 'airport'", other)
        self.assertEqual(ew.list_watches("personal"), [])

    def test_earthquake_tonight_from_fresh_phone_fix(self) -> None:
        with turn_context("c2", fix()) as turn:
            result = vw.compile_utterance("tell me if there's an earthquake near me tonight", turn, now=NOW)
        plan = result.plans[0]
        self.assertEqual((plan.kind, plan.place_provenance), ("usgs_earthquakes", "phone_fix"))
        self.assertEqual(plan.expires_at, NOW.replace(hour=6, minute=0) + timedelta(days=1))
        reply = self.say("tell me if there's an earthquake near me tonight", fix())
        self.assertIn("USGS earthquake reports", reply)
        self.assertIn("100 kilometers", reply)
        self.assertIn("until ", reply)
        self.assertIn("6:00 AM", reply)

    def test_air_quality_until_six_with_threshold(self) -> None:
        with turn_context("c3", fix()) as turn:
            plan = vw.compile_utterance(
                "watch air quality here until 6 and tell me if it goes above 150", turn, now=NOW).plans[0]
        self.assertEqual(plan.kind, "air_quality")
        self.assertEqual(plan.rule["us_aqi_threshold"], 150.0)
        self.assertEqual(plan.expires_at, NOW.replace(hour=18, minute=0))
        self.assertEqual(plan.interval_seconds, 1800)

    def test_airspace_two_hours_and_cadence_floor(self) -> None:
        with turn_context("c4", fix()) as turn:
            plan = vw.compile_utterance(
                "watch the airspace around here for two hours every 5 minutes", turn, now=NOW).plans[0]
        self.assertEqual(plan.kind, "airspace_region")
        self.assertEqual(plan.expires_at, NOW + timedelta(hours=2))
        self.assertEqual(plan.interval_seconds, 1800)
        self.assertTrue(any("more often" in n for n in plan.notes))

    def test_duration_defaults_are_disclosed(self) -> None:
        reply = self.say("keep an eye on earthquakes near me", fix())
        self.assertIn("didn't say how long", reply)

    def test_unsupported_domains_are_refused_plainly_without_storing(self) -> None:
        for text, fragment in (
            ("watch my flight UA 100 for delays", "no flight-status source"),
            ("tell me if my train is delayed", "no transit-status source"),
            ("watch the bitcoin price", "no market-price source"),
        ):
            reply = self.say(text, fix())
            self.assertIn(fragment, reply, text)
            self.assertIn("haven't stored a watch", reply)
        self.assertEqual(ew.list_watches("personal"), [])

    def test_ordinary_requests_are_not_captured(self) -> None:
        for text in ("cancel", "cancel job 3", "watch a youtube video", "tell me a joke", "what time is it",
                     "cancel the world armor watch", "monitor my cpu"):
            self.assertIsNone(self.say(text, fix()), text)

    def test_non_us_point_is_refused_for_nws(self) -> None:
        reply = self.say("watch for severe weather alerts near me for 2 hours", fix(lat=48.85, lon=2.35))
        self.assertIn("only covers the United States", reply)
        self.assertEqual(ew.list_watches("personal"), [])

    def test_identical_request_does_not_create_a_second_watch(self) -> None:
        first = self.say("watch for severe weather alerts near me for 2 hours", fix())
        self.assertIn("I'll watch", first)
        second = self.say("watch for severe weather alerts near me for 3 hours", fix())
        self.assertIn("already watching", second)
        self.assertEqual(len(ew.list_watches("personal")), 1)


class AlertTests(Isolated):
    def make(self, text="watch for severe weather alerts near me for 3 hours", kind="nws_alerts"):
        self.say(text, fix())
        return self.only_watch(kind)

    def test_baseline_is_silent_then_new_alert_is_queued_with_evidence_and_truthful_ledger(self) -> None:
        watch = self.make()
        baseline = self.check(watch, nws_evidence(nws_alert("urn:old", "Wind Advisory")))
        self.assertEqual(baseline["change_kind"], "baseline")
        self.assertEqual(attention.ledger(), [])
        self.assertIn("1 NWS alert(s) already active", vw.get_meta(watch["id"])["baseline_summary"])
        changed = self.check(watch, nws_evidence(
            nws_alert("urn:old", "Wind Advisory"),
            nws_alert("urn:new", "Tornado Warning", "Extreme", "Immediate", "Tornado Warning for the county")))
        self.assertEqual(changed["change_kind"], "changed")
        items = attention.ledger()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["decision"], "emitted")
        self.assertIn("Tornado Warning", item["text"])
        self.assertNotIn("Wind Advisory", item["text"])  # pre-existing alert is not re-announced
        self.assertIn("National Weather Service", item["text"])
        self.assertIn("checked", item["text"])
        self.assertTrue(item["source_url"].startswith("https://www.weather.gov"))
        self.assertTrue(item["observed_at"])
        self.assertTrue(item["critical"])
        self.assertEqual(item["evidence"]["data"]["new_alert_ids"], ["urn:new"])
        # Truth: no APNs credentials and nobody connected -> neither is "delivered".
        self.assertEqual(item["push_state"], "not_configured")
        self.assertEqual(item["live_state"], "no_live_client")
        self.assertFalse(item["confirmed_delivery"])
        self.emit.assert_called_once()
        self.assertEqual(self.emit.call_args.args[0], item["text"])

    def test_cancel_stops_all_further_alerts(self) -> None:
        watch = self.make()
        self.check(watch, nws_evidence())
        self.check(watch, nws_evidence(nws_alert("urn:a", "Flood Warning", "Severe", "Expected")))
        self.assertEqual(len(attention.ledger(decision="emitted")), 1)
        reply = self.say("cancel the weather watch")
        self.assertIn("Cancelled the weather watch", reply)
        self.assertEqual(ew.get_watch(watch["id"], "personal")["state"], "cancelled")
        result = self.check(watch, nws_evidence(nws_alert("urn:b", "Tornado Warning", "Extreme", "Immediate")))
        self.assertEqual(result["status"], "stopped_or_expired")
        self.assertEqual(len(attention.ledger(decision="emitted")), 1)
        self.assertEqual(ew.run_due_watches(), [])

    def test_earthquake_alert_has_magnitude_place_distance_source(self) -> None:
        watch = self.make("tell me if there's an earthquake near me tonight", "usgs_earthquakes")
        self.check(watch, quake_evidence(quake("ci1", 2.7)))
        self.check(watch, quake_evidence(quake("ci1", 2.7), quake("ci2", 4.6)))
        item = attention.ledger(decision="emitted")[0]
        self.assertIn("magnitude 4.6", item["text"])
        self.assertIn("Ridgecrest", item["text"])
        self.assertIn("kilometers from the watched point", item["text"])
        self.assertIn("preliminary", item["text"])
        self.assertEqual(item["source_url"], "https://earthquake.usgs.gov/e/ci2")
        self.assertNotIn("2.7", item["text"])

    def test_earthquake_minimum_magnitude_filters_small_events(self) -> None:
        watch = self.make("tell me if there's an earthquake of magnitude 4 or higher near me for 2 hours", "usgs_earthquakes")
        self.check(watch, quake_evidence())
        self.check(watch, quake_evidence(quake("small", 3.1)))
        self.assertEqual(attention.ledger(), [])

    def test_air_quality_alert_only_on_threshold_crossing(self) -> None:
        watch = self.make("watch air quality here for 3 hours and tell me if it goes above 100", "air_quality")
        self.check(watch, aqi_evidence(80))
        self.assertEqual(attention.ledger(), [])
        self.check(watch, aqi_evidence(135))
        item = attention.ledger()[0]
        self.assertIn("US AQI 135", item["text"])
        self.assertIn("above your threshold of 100", item["text"])
        self.assertIn("model estimate", item["text"])
        self.assertEqual(item["evidence"]["data"]["previous_us_aqi"], 80)

    def test_airspace_small_change_is_quiet_large_change_alerts(self) -> None:
        watch = self.make("watch the airspace around here for 2 hours", "airspace_region")

        def air(count):
            payload = {"status": "ok", "aircraft_count": count, "states_at": 1788000000,
                       "source_url": "https://opensky-network.org/"}
            return {"status": "ok", "summary": "x", "source_url": payload["source_url"],
                    "observed_at": "1788000000", "signature": count, "payload": payload}
        self.check(watch, air(10))
        self.check(watch, air(12))
        self.assertEqual(attention.ledger(), [])
        self.check(watch, air(30))
        text = attention.ledger()[0]["text"]
        self.assertIn("from 12 to 30", text)
        self.assertIn("not identification", text)

    def test_removed_alert_is_not_announced_and_returning_alert_never_realerts(self) -> None:
        watch = self.make()
        self.check(watch, nws_evidence())
        self.check(watch, nws_evidence(nws_alert("urn:a", "Flood Warning", "Severe", "Expected")))
        self.check(watch, nws_evidence())  # alert expired: a change, but nothing new
        self.check(watch, nws_evidence(nws_alert("urn:a", "Flood Warning", "Severe", "Expected")))  # flaps back
        self.assertEqual(len(attention.ledger(decision="emitted")), 1)
        self.assertEqual(self.emit.call_count, 1)

    def test_same_dedupe_key_never_realerts(self) -> None:
        item = attention.ProactiveItem(kind="watch_alert", subject="w", dedupe_key="k1", text="hello")
        self.assertEqual(attention.submit(item)["decision"], "emitted")
        again = attention.submit(item)
        self.assertEqual(again["decision"], "duplicate")
        self.assertEqual(self.emit.call_count, 1)
        self.assertEqual(len(attention.ledger()), 1)

    def test_per_watch_cooldown_holds_back_and_records(self) -> None:
        watch = self.make()
        self.check(watch, nws_evidence())
        self.check(watch, nws_evidence(nws_alert("urn:a", "Flood Warning", "Moderate", "Expected")))
        self.check(watch, nws_evidence(nws_alert("urn:a", "Flood Warning", "Moderate", "Expected"),
                                       nws_alert("urn:b", "Wind Advisory", "Minor", "Expected")))
        emitted = attention.ledger(decision="emitted")
        held = attention.ledger(decision="suppressed")
        self.assertEqual(len(emitted), 1)
        self.assertEqual([h["suppress_reason"] for h in held], ["cooldown"])
        self.assertIn("Wind Advisory", held[0]["text"])
        self.assertEqual(self.emit.call_count, 1)
        with turn_context("hb", None) as turn:
            said = attention.handle("what did you hold back", turn)
        self.assertIn("held back 1 item", said)
        self.assertIn("watch cooldown", said)

    def test_critical_alert_bypasses_cooldown_but_not_dedupe(self) -> None:
        watch = self.make()
        self.check(watch, nws_evidence())
        self.check(watch, nws_evidence(nws_alert("urn:a", "Flood Watch", "Minor", "Expected")))
        self.check(watch, nws_evidence(nws_alert("urn:a", "Flood Watch", "Minor", "Expected"),
                                       nws_alert("urn:t", "Tornado Warning", "Extreme", "Immediate")))
        self.assertEqual(len(attention.ledger(decision="emitted")), 2)

    def test_global_interruption_budget_suppresses_excess_with_reason(self) -> None:
        attention.set_prefs(hourly_budget=2)
        results = [attention.submit(attention.ProactiveItem(
            kind="watch_alert", subject="w", dedupe_key=f"k{i}", text=f"alert {i}")) for i in range(4)]
        self.assertEqual([r["decision"] for r in results], ["emitted", "emitted", "suppressed", "suppressed"])
        self.assertEqual(results[2]["reason"], "budget")
        self.assertEqual(self.emit.call_count, 2)
        self.assertEqual(attention.budget_status()["remaining"], 0)
        crit = attention.submit(attention.ProactiveItem(
            kind="watch_alert", subject="w", dedupe_key="kc", text="quake", critical=True))
        self.assertEqual(crit["decision"], "emitted")
        later = datetime.now(timezone.utc) + timedelta(minutes=61)
        after = attention.submit(attention.ProactiveItem(
            kind="watch_alert", subject="w", dedupe_key="k9", text="later"), now=later)
        self.assertEqual(after["decision"], "emitted")


class RaceAndLifecycleTests(Isolated):
    def make(self):
        self.say("watch for severe weather alerts near me for 3 hours", fix())
        watch = self.only_watch("nws_alerts")
        self.check(watch, nws_evidence())
        return watch

    def test_cancel_during_remote_io_discards_the_sample(self) -> None:
        watch = self.make()

        def fetch_then_cancel(row):
            ew.stop_watch(row["id"], "personal")
            return nws_evidence(nws_alert("urn:x", "Tornado Warning", "Extreme", "Immediate"))
        with patch.object(ew, "_fetch", side_effect=fetch_then_cancel):
            result = ew.check_watch(watch["id"], "personal")
        self.assertEqual(result["status"], "stopped_or_expired")
        self.assertEqual(attention.ledger(), [])
        self.emit.assert_not_called()

    def test_pause_during_remote_io_discards_the_sample(self) -> None:
        watch = self.make()

        def fetch_then_pause(row):
            ew.pause_watch(row["id"], "personal")
            return nws_evidence(nws_alert("urn:x", "Tornado Warning", "Extreme", "Immediate"))
        with patch.object(ew, "_fetch", side_effect=fetch_then_pause):
            result = ew.check_watch(watch["id"], "personal")
        self.assertEqual(result["status"], "paused")
        self.assertEqual(attention.ledger(), [])
        self.emit.assert_not_called()

    def test_expiry_during_remote_io_discards_the_sample(self) -> None:
        watch = self.make()

        def fetch_then_expire(row):
            self.expire_row(row["id"], datetime.now(timezone.utc) - timedelta(seconds=1))
            return nws_evidence(nws_alert("urn:x", "Tornado Warning", "Extreme", "Immediate"))
        with patch.object(ew, "_fetch", side_effect=fetch_then_expire):
            result = ew.check_watch(watch["id"], "personal")
        self.assertEqual(result["status"], "stopped_or_expired")
        self.assertEqual(attention.ledger(), [])

    def test_cancel_or_pause_after_check_but_before_emission_is_blocked(self) -> None:
        for how, expected in ((ew.stop_watch, "cancelled"), (ew.pause_watch, "paused")):
            with self.subTest(how=how.__name__):
                for w in ew.list_watches("personal"):
                    ew.stop_watch(w["id"], "personal")
                self.say("watch for severe weather alerts near me for 3 hours", fix(lat=40.0 + len(how.__name__) / 10))
                watch = [w for w in ew.list_watches("personal") if w["state"] == "active"][0]
                self.check(watch, nws_evidence())
                real = vw._compose

                def compose_then_revoke(*args, **kwargs):
                    item = real(*args, **kwargs)
                    how(watch["id"], "personal")
                    return item
                before = self.emit.call_count
                with patch.object(vw, "_compose", side_effect=compose_then_revoke):
                    self.check(watch, nws_evidence(nws_alert("urn:" + how.__name__, "Tornado Warning", "Extreme", "Immediate")))
                self.assertEqual(self.emit.call_count, before)
                held = [i for i in attention.ledger(decision="suppressed") if i["suppress_reason"] == expected]
                self.assertEqual(len(held), 1)

    def test_pause_keeps_expiry_blocks_checks_and_resume_rebaselines(self) -> None:
        watch = self.make()
        expiry = ew.get_watch(watch["id"], "personal")["expires_at"]
        reply = self.say("pause the weather watch")
        self.assertIn("Paused the weather watch", reply)
        self.assertIn("still expires", reply)
        paused = ew.get_watch(watch["id"], "personal")
        self.assertEqual((paused["state"], paused["expires_at"], paused["enabled"]), ("paused", expiry, True))
        with ew._database() as conn:
            conn.execute("UPDATE watches SET next_check_at=?", ("2000-01-01T00:00:00+00:00",))
        with patch.object(ew, "_fetch") as fetch:
            self.assertEqual(ew.run_due_watches(), [])
            self.assertEqual(ew.check_watch(watch["id"], "personal")["status"], "paused")
            fetch.assert_not_called()
        self.assertIn("paused", vw.list_answer(NOW))
        resumed = self.say("resume the weather watch")
        self.assertIn("Resumed the weather watch", resumed)
        self.assertIn("fresh baseline", resumed)
        # Something changed while paused: the first check after resume is a baseline, not an alert.
        result = self.check(watch, nws_evidence(nws_alert("urn:p", "Flood Warning", "Severe", "Expected")))
        self.assertEqual(result["change_kind"], "baseline")
        self.assertEqual(attention.ledger(), [])
        self.assertEqual(ew.get_watch(watch["id"], "personal")["expires_at"], expiry)

    def test_cannot_resume_expired_or_cancelled_watch(self) -> None:
        watch = self.make()
        self.expire_row(watch["id"], datetime.now(timezone.utc) - timedelta(minutes=1))
        self.assertEqual(ew.get_watch(watch["id"], "personal")["state"], "expired")
        with self.assertRaises(ValueError):
            ew.resume_watch(watch["id"], "personal")
        self.assertEqual(ew.run_due_watches(), [])
        self.assertIn("can't be resumed", self.say("resume the weather watch"))

    def test_expiry_stops_alerts_and_is_reported_as_expired_not_cancelled(self) -> None:
        watch = self.make()
        self.expire_row(watch["id"], datetime.now(timezone.utc) - timedelta(seconds=1))
        result = self.check(watch, nws_evidence(nws_alert("urn:e", "Tornado Warning", "Extreme", "Immediate")))
        self.assertEqual(result["status"], "stopped_or_expired")
        self.assertEqual(attention.ledger(), [])
        self.assertEqual(ew.get_watch(watch["id"], "personal")["state"], "expired")
        self.assertEqual(vw.list_answer(NOW).split(".")[0], "I'm not watching anything for you right now")

    def test_restart_recovery_resumes_from_sqlite(self) -> None:
        watch = self.make()
        meta_before = vw.get_meta(watch["id"])
        # Simulate a process restart: no in-memory runner, focus or heartbeat survives.
        ew._RUNNER["last_tick"] = None
        voice_router._FOCUS.clear()
        with ew._database() as conn:
            conn.execute("UPDATE watches SET next_check_at=?", ("2000-01-01T00:00:00+00:00",))
        self.assertFalse(ew.runner_status()["active"])
        with patch.object(ew, "_fetch", return_value=nws_evidence(
                nws_alert("urn:r", "Flood Warning", "Severe", "Expected"))):
            results = ew.run_due_watches()
        self.assertEqual([r["change_kind"] for r in results], ["changed"])
        self.assertTrue(ew.runner_status()["active"])
        self.assertEqual(vw.get_meta(watch["id"])["rule"], meta_before["rule"])
        self.assertEqual(len(attention.ledger(decision="emitted")), 1)
        # A fresh raw connection sees the same persisted watch and ledger.
        raw = sqlite3.connect(Path(self.temp.name) / "external_watches.sqlite3")
        self.assertEqual(raw.execute("SELECT count(*) FROM watches").fetchone()[0], 1)
        raw.close()

    def test_cancel_that_uses_focus_only_right_after_creation(self) -> None:
        self.say("watch for severe weather alerts near me for 3 hours", fix(), session="focus")
        self.assertIsNone(self.say("cancel that", session="other-session"))
        reply = self.say("cancel that", session="focus")
        self.assertIn("Cancelled the weather watch", reply)
        self.assertIsNone(self.say("cancel that", session="focus"))

    def test_list_pause_cancel_all_and_ambiguity(self) -> None:
        self.say("watch for severe weather alerts near me for 3 hours", fix())
        self.say("tell me if there's an earthquake near me tonight", fix())
        ew._RUNNER["last_tick"] = datetime.now(timezone.utc)
        listing = self.say("what are you watching?")
        self.assertIn("I have 2 watches", listing)
        self.assertIn("NWS alerts", listing)
        self.assertIn("USGS earthquake reports", listing)
        self.assertIn("not checked yet", listing)
        self.assertNotIn("has not checked in", listing)
        voice_router._FOCUS.clear()
        self.assertIn("Which watch", self.say("cancel the watch"))
        self.assertIn("Cancelled the earthquake watch", self.say("stop watching earthquakes"))
        self.assertIn("Cancelled the weather watch", self.say("cancel all watches"))
        self.assertIn("not watching anything", self.say("what are you watching"))

    def test_failed_check_is_reported_as_unknown_not_clear(self) -> None:
        self.say("watch for severe weather alerts near me for 3 hours", fix())
        watch = self.only_watch()
        self.check(watch, {"status": "unavailable", "summary": "Source check failed", "source_url": ""})
        listing = self.say("what are you watching")
        self.assertIn("did not succeed", listing)
        self.assertIn("unknown", listing)


class DeliveryTests(Isolated):
    def make(self):
        self.say("watch for severe weather alerts near me for 3 hours", fix())
        watch = self.only_watch()
        self.check(watch, nws_evidence())
        return watch

    def alert(self, watch, ident="urn:z"):
        self.check(watch, nws_evidence(nws_alert(ident, "Tornado Warning", "Extreme", "Immediate")))

    def test_apns_queued_then_sent_only_after_apns_accepts(self) -> None:
        with patch.dict(os.environ, PUSH_ENV), patch.object(push, "start_worker", return_value=False):
            push.register_device("ab" * 32)
            watch = self.make()
            self.alert(watch)
            item = attention.ledger()[0]
            self.assertEqual(item["push_state"], "queued")
            self.assertFalse(item["confirmed_delivery"])
            self.assertIn("weather.gov", push.delivery_state(item["push_event_id"]) and
                          sqlite3.connect(push.PUSH_STORE).execute("SELECT body FROM push_outbox").fetchone()[0])
            self.assertEqual(push.delivery_state(item["push_event_id"])["pending"], 1)
            with patch.object(push, "_send_one", return_value=(True, "")) as sent:
                push.drain_once()
            self.assertEqual(sent.call_args.args[3:], ("horus-watch", "watch"))
            settled = attention.ledger()[0]
            self.assertEqual(settled["push_state"], "sent")
            self.assertTrue(settled["confirmed_delivery"])

    def test_apns_failure_is_recorded_as_failed(self) -> None:
        with patch.dict(os.environ, PUSH_ENV), patch.object(push, "start_worker", return_value=False):
            push.register_device("cd" * 32)
            watch = self.make()
            self.alert(watch)
            with patch.object(push, "_send_one", return_value=(False, "BadDeviceToken")):
                push.drain_once()
            item = attention.ledger()[0]
            self.assertEqual(item["push_state"], "failed")
            self.assertIn("BadDeviceToken", item["push_detail"])
            self.assertFalse(item["confirmed_delivery"])

    def test_still_pending_push_stays_queued(self) -> None:
        with patch.dict(os.environ, PUSH_ENV), patch.object(push, "start_worker", return_value=False):
            push.register_device("ef" * 32)
            watch = self.make()
            self.alert(watch)
            with patch.object(push, "_send_one", return_value=(False, "ConnectError")):
                push.drain_once()
            self.assertEqual(attention.ledger()[0]["push_state"], "queued")

    def test_enabled_without_credentials_or_device_is_not_configured(self) -> None:
        with patch.dict(os.environ, {k: v for k, v in PUSH_ENV.items() if k in (
                "JARVIS_WORLD_ARMOR_ENABLED", "JARVIS_WORLD_ARMOR_PUSH_ENABLED")}):
            watch = self.make()
            self.alert(watch)
            item = attention.ledger()[0]
            self.assertEqual(item["push_state"], "not_configured")
            self.assertIn("credentials", item["push_detail"])
        with patch.dict(os.environ, PUSH_ENV), patch.object(push, "start_worker", return_value=False):
            self.alert(watch, "urn:y")
            item = attention.ledger()[0]
            self.assertEqual(item["push_state"], "not_configured")
            self.assertIn("no iPhone", item["push_detail"])

    def test_live_publish_records_connected_client_count_without_claiming_receipt(self) -> None:
        self.notify.stop()  # use the real bus for this test
        loop = asyncio.new_event_loop()
        sid, _queue = event_bus.companion_events.register(loop)
        try:
            watch = self.make()
            self.alert(watch)
            item = attention.ledger()[0]
            self.assertEqual(item["live_state"], "live_published")
            self.assertEqual(item["live_clients"], 1)
            self.assertIn("receipt is not confirmed", item["live_detail"])
            self.assertFalse(item["confirmed_delivery"])
        finally:
            event_bus.companion_events.unregister(sid)
            loop.close()
            self.emit = self.notify.start()

    def test_why_did_you_tell_me_that_gives_rule_evidence_and_source(self) -> None:
        watch = self.make()
        self.assertIsNone(self.say("why did you tell me that"))  # nothing proactive yet
        with turn_context("why0", None) as turn:
            self.assertIsNone(attention.handle("why did you tell me that", turn))
        self.alert(watch)
        with turn_context("why1", None) as turn:
            answer = attention.handle("Why did you tell me that?", turn)
            explicit = attention.handle("why did you alert me", turn)
        self.assertEqual(answer, explicit)
        self.assertIn("because your voice watch for new official NWS alerts", answer)
        self.assertIn("Tornado Warning", answer)
        self.assertIn("Source: National Weather Service", answer)
        self.assertIn("observed", answer)

    def test_service_background_runner_and_api(self) -> None:
        import inspect
        from fastapi import HTTPException
        from jarvis_mrb import service
        self.assertIn("run_due_watches", inspect.getsource(service._external_watch_loop))
        self.assertIn("_ensure_external_watch_runner()", inspect.getsource(service.startup))
        watch = self.make()
        self.alert(watch)
        with patch.object(service, "API_TOKEN", "secret"):
            with self.assertRaises(HTTPException) as ctx:
                service.proactive_ledger(authorization=None)
            self.assertEqual(ctx.exception.status_code, 401)
            ok = service.proactive_ledger(authorization="Bearer secret")
            self.assertEqual(ok["items"][0]["push_state"], "not_configured")
            watches = service.proactive_watches(authorization="Bearer secret")
            self.assertEqual(watches["watches"][0]["voice"]["rule"], {})
            req = service.ExternalWatchLookupRequest(id=watch["id"], scope="personal")
            self.assertEqual(service.external_watch_pause(req, authorization="Bearer secret")["state"], "paused")
            self.assertEqual(service.external_watch_resume(req, authorization="Bearer secret")["state"], "active")
            prefs = service.proactive_preferences_set(
                service.ProactivePreferencesRequest(hourly_budget=3, snooze_minutes=30), authorization="Bearer secret")
            self.assertEqual(prefs["preferences"]["hourly_budget"], 3)
            self.assertTrue(prefs["preferences"]["snoozed"])
            self.assertIn("Tornado Warning", service.proactive_why(authorization="Bearer secret")["explanation"])
            with self.assertRaises(HTTPException):
                service.proactive_preferences_set(
                    service.ProactivePreferencesRequest(hourly_budget=500), authorization="Bearer secret")


if __name__ == "__main__":
    unittest.main()
