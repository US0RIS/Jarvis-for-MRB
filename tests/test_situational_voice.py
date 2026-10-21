from __future__ import annotations

"""Feature 6 acceptance with MOCKED providers (no network). Live-provider
behavior is exercised separately and is not claimed by these tests."""

import tempfile
from contextlib import closing
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from jarvis_mrb import saved_places, situational_voice as sv
from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.voice_router import clear_focus, turn_context

NOW = datetime.now(timezone.utc)


def fix():
    return {"latitude": 39.74, "longitude": -104.99, "location_accuracy_m": 25,
            "location_captured_at": NOW.isoformat(), "channel": "voice"}


def conditions(alerts=(), aqi=35, alert_status="ok", air_status="ok"):
    return {
        "checked_at": NOW.isoformat(),
        "air_quality": {"status": air_status, "us_aqi": aqi, "uv_index": 3,
                        "model_time_utc": NOW.isoformat(), "source_url": "https://open-meteo.com/en/docs/air-quality-api"},
        "weather_alerts": {"status": alert_status, "alerts": list(alerts), "checked_at": NOW.isoformat(),
                           "source_url": "https://www.weather.gov/documentation/services-web-alerts"},
    }


def quakes(events=(), status="ok"):
    return {"status": status, "events": list(events), "checked_at": NOW.isoformat(),
            "source_url": "https://earthquake.usgs.gov/fdsnws/event/1/"}


def airspace(count=12, status="ok"):
    return {"status": status, "aircraft_count": count, "states_at": NOW.timestamp(),
            "source_url": "https://openskynetwork.github.io/opensky-api/rest.html"}


WINTER = {"id": "urn:nws:1", "event": "Winter Storm Warning", "severity": "Severe", "headline": "x"}


class SituationalBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(sv, "DB_PATH", root / "snap.sqlite3"),
            mock.patch.object(saved_places, "DB_PATH", root / "places.sqlite3"),
            mock.patch("jarvis_mrb.object_memory.DB_PATH", root / "objects.sqlite3"),
        ]
        for p in self.patches:
            p.start()
        sv._CACHE.clear()
        self.calls: list[str] = []
        self.data = {"conditions": conditions(), "quakes": quakes(), "airspace": airspace(),
                     "facilities": {"status": "ok", "facilities": [{"category": "pharmacy"}] * 2}}
        providers = {k: self._provider(k) for k in sv.PROVIDERS}
        self.patches.append(mock.patch.dict(sv.PROVIDERS, providers))
        self.patches[-1].start()
        self.session = "sit-" + self.id()

    def _provider(self, name):
        def call(lat, lon):
            self.calls.append(name)
            value = self.data[name]
            if isinstance(value, Exception):
                raise value
            return value
        return call

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        sv._CACHE.clear()
        clear_focus(session_id=self.session)
        self.tmp.cleanup()

    def say(self, text, context=None):
        with turn_context(self.session, fix() if context is None else context):
            return handle_natural_language(text).message


class SituationalTests(SituationalBase):
    def test_two_real_source_adapters_contribute_and_answer_is_concise(self):
        self.data["conditions"] = conditions(alerts=[WINTER])
        self.data["quakes"] = quakes([{"id": "us1", "magnitude": 4.6, "place": "12 km N of Golden",
                                       "occurred_at": (NOW - timedelta(minutes=40)).isoformat()}])
        answer = self.say("Horus, anything interesting happening around me?")
        self.assertIn("Winter Storm Warning", answer)
        self.assertIn("magnitude 4.6", answer)
        self.assertIn("tell me more", answer)
        self.assertLess(len(answer.split()), 60)
        self.assertEqual(sorted(self.calls), ["conditions", "quakes"])  # no camera, no airspace
        detail = self.say("tell me more")
        self.assertIn("NWS point alerts", detail)
        self.assertIn("USGS", detail)
        self.assertIn("Location came from your iPhone", detail)
        self.assertIn("None of this is a camera view", detail)

    def test_total_outage_is_never_an_all_clear(self):
        self.data["conditions"] = RuntimeError("down")
        self.data["quakes"] = RuntimeError("down")
        answer = self.say("anything happening around here?")
        self.assertIn("couldn't reach any of my sources", answer)
        self.assertIn("not an all-clear", answer)

    def test_partial_outage_names_the_gap(self):
        self.data["quakes"] = quakes(status="unavailable")
        answer = self.say("what's going on around me")
        self.assertIn("Nothing notable around you", answer)
        self.assertIn("no NWS weather alerts", answer)
        self.assertIn("couldn't reach USGS", answer)

    def test_unsupported_region_is_stated(self):
        self.data["conditions"] = conditions(alert_status="unsupported_region")
        self.assertIn("aren't integrated for this region", self.say("is anything unusual happening near me?"))

    def test_no_location_asks_instead_of_guessing(self):
        answer = self.say("anything interesting happening around me?", context={"channel": "voice"})
        self.assertIn("I don't know where you are", answer)
        self.assertEqual(self.calls, [])
        stale = fix(); stale["location_captured_at"] = (NOW - timedelta(hours=2)).isoformat()
        self.assertIn("minutes old", self.say("anything happening near me?", context=stale))
        self.assertEqual(self.calls, [])

    def test_named_saved_place_and_missing_home(self):
        self.assertIn("don't have home saved", self.say("Is anything unusual happening near home?"))
        self.say("save this place as home")
        self.assertIn("near home", self.say("Is anything unusual happening near home?",
                                            context={"channel": "voice"}))

    def test_airspace_question_uses_only_airspace(self):
        answer = self.say("What's happening in the airspace around here?")
        self.assertIn("12 airborne aircraft", answer)
        self.assertIn("don't identify flights", answer)
        self.assertEqual(self.calls, ["airspace"])

    def test_cache_avoids_repeat_provider_calls(self):
        self.say("anything happening around me?")
        self.say("anything happening around me?")
        self.assertEqual(sorted(self.calls), ["conditions", "quakes"])

    def test_outage_is_not_cached_so_the_next_question_retries(self):
        self.data["conditions"] = {"air_quality": {"status": "unavailable"},
                                   "weather_alerts": {"status": "unavailable"}}
        first = self.say("anything happening around me?")
        self.assertIn("couldn't reach", first)
        self.data["conditions"] = conditions()
        second = self.say("anything happening around me?")
        self.assertEqual(self.calls.count("conditions"), 2)
        self.assertNotIn("couldn't reach NWS", second)

    def test_whats_changed_compares_against_previous_check(self):
        first = self.say("What's changed since I was here?")
        self.assertIn("don't have an earlier check", first)
        old = (NOW - timedelta(hours=3)).isoformat()
        with closing(sv._connect()) as conn, conn:
            conn.execute("UPDATE snapshots SET checked_at=?", (old,))
            conn.commit()
        sv._CACHE.clear()
        self.data["conditions"] = conditions(alerts=[WINTER], aqi=90)
        changed = self.say("what's changed since I was here?")
        self.assertIn("Since you last asked here", changed)
        self.assertIn("new weather alert: Winter Storm Warning", changed)
        self.assertIn("AQI 35 to 90", changed)
        self.assertIn("Deleted", self.say("forget my place history"))

    def test_new_alert_flagged_as_new_relative_to_last_check(self):
        self.say("anything happening around me?")
        with closing(sv._connect()) as conn, conn:
            conn.execute("UPDATE snapshots SET checked_at=?", ((NOW - timedelta(hours=1)).isoformat(),))
            conn.commit()
        sv._CACHE.clear()
        self.data["conditions"] = conditions(alerts=[WINTER])
        self.assertIn("New: the National Weather Service has a Winter Storm Warning", self.say("anything happening around me?"))

    def test_before_leaving_combines_personal_context(self):
        with mock.patch.object(sv, "_personal_before_leaving",
                               return_value=["Your next event, Dentist, is in 40 minutes (from your synced calendar)."]):
            answer = self.say("What should I know before leaving?")
        self.assertTrue(answer.startswith("Your next event, Dentist"))
        self.assertIn("Nothing notable", answer)

    def test_watch_requests_are_not_answered_as_questions(self):
        with turn_context(self.session, fix()):
            from jarvis_mrb.voice_router import current_turn
            self.assertIsNone(sv.handle("watch the airspace around here for two hours", current_turn()))

    def test_camera_sources_are_never_queried(self):
        for text in ("anything interesting happening around me?", "is anything unusual near me",
                     "what's changed since I was here", "what should I know before I leave"):
            sv._CACHE.clear()
            self.say(text)
        self.assertNotIn("cameras", self.calls)


if __name__ == "__main__":
    unittest.main()
