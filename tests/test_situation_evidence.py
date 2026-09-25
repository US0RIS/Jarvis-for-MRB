from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import situation_evidence as fusion
from jarvis_mrb import world_situation


NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
DUE = (NOW + timedelta(minutes=20)).isoformat()
EVENT = {
    "world_event_id": 41,
    "calendar_event_id": "cal-42",
    "source_ref": "cal-42",
    "title": "Quarterly budget planning",
    "start": (NOW + timedelta(minutes=12)).isoformat(),
    "location": "123 Main Street",
    "status": "confirmed",
}
INTENTIONS = [
    {"id": "intention-1", "title": "Quarterly budget planning",
     "next_action": "Review schedules", "due": DUE, "confidence": 1.0},
]
PROJECTS = [{"id": "project-1", "name": "Atlas Relaunch"}]


def watch(**overrides):
    base = {
        "id": "watch-1", "intention_id": "intention-1",
        "goal_title": "Quarterly budget planning", "deadline_at": DUE,
        "status": "active", "last_signal": "at_risk",
        "last_checked_at": (NOW - timedelta(minutes=2)).isoformat(),
    }
    return base | overrides


def task(**overrides):
    base = {
        "id": "task-1", "domain": "work", "title": "Quarterly budget draft",
        "data": {"description": "", "next_step": "", "depends_on": []},
        "deadline_at": DUE, "completion_state": "not_verified",
    }
    return base | overrides


class SituationEvidenceTests(unittest.TestCase):

    def test_absent_enrollment_does_not_mean_all_clear(self):
        with patch.object(fusion, "_guardian_rows", return_value=([], "no_enrolled_data")), \
             patch.object(fusion, "_life_rows", return_value=([], "no_enrolled_data")):
            result = fusion.compile_evidence(EVENT, INTENTIONS, PROJECTS, now=NOW)
        self.assertEqual(result["sections"]["guardian"], [])
        self.assertEqual(result["sections"]["life_fabric"], [])
        self.assertEqual(result["source_status"]["guardian"], "no_enrolled_data")
        self.assertEqual(result["source_status"]["mission_control"], "phone_local_not_shared")
        self.assertEqual(result["source_status"]["reality_lens"], "exact_place_not_linked")
        self.assertEqual(result["external_actions"], 0)
        self.assertEqual(result["model_calls"], 0)

    def test_guardian_requires_exact_linked_goal_fresh_signal_and_same_deadline(self):
        rows = [
            watch(),
            watch(id="wrong-goal", intention_id="other"),
            watch(id="stale", last_checked_at=(NOW-timedelta(minutes=17)).isoformat()),
            watch(id="changed-date", deadline_at=(NOW+timedelta(hours=2)).isoformat()),
            watch(id="fabricated-risk", last_signal=""),
            watch(id="future", last_checked_at=(NOW+timedelta(minutes=3)).isoformat()),
        ]
        with patch.object(fusion, "_guardian_rows", return_value=(rows, "available")):
            value, status = fusion._guardian(EVENT, INTENTIONS, NOW)
        self.assertEqual(status, "available")
        self.assertEqual([x["watch_id"] for x in value], ["watch-1"])
        self.assertEqual(value[0]["evidence_kind"], "previous_enrolled_goal_evaluation")
        self.assertIn("not a live route", value[0]["qualifier"].lower())

    def test_guardian_never_emits_or_evaluates_live_monitor(self):
        with patch.object(fusion, "_guardian_rows", return_value=([watch()], "available")), \
             patch("jarvis_mrb.guardian_objectives.evaluate_once",
                   side_effect=AssertionError("Guardian side effect forbidden")):
            result = fusion.compile_evidence(EVENT, INTENTIONS, PROJECTS, now=NOW)
        self.assertEqual(len(result["sections"]["guardian"]), 1)

    def test_life_fabric_exact_reference_or_two_terms_but_not_unrelated_tasks(self):
        rows = [
            task(),
            task(id="exact-ref", title="Upload final materials",
                 data={"source_ref": "calendar:cal-42", "depends_on": ["missing"]},
                 completion_state="provider_reported"),
            task(id="other", title="Refill a prescription", domain="health"),
            task(id="oneword", title="Pay quarterly expense", domain="money"),
            task(id="completed", completion_state="user_confirmed"),
            task(id="no-deadline", deadline_at=None),
            task(id="future", deadline_at=(NOW+timedelta(days=9)).isoformat()),
        ]
        with patch.object(fusion, "_life_rows", return_value=(rows, "available")):
            found, status = fusion._life(EVENT, PROJECTS, NOW)
        self.assertEqual(status, "available")
        self.assertEqual({x["task_id"] for x in found}, {"task-1", "exact-ref"})
        exact = next(x for x in found if x["task_id"] == "exact-ref")
        self.assertTrue(exact["blocked"])
        self.assertEqual(exact["completion_state"], "provider_reported")
        self.assertEqual(exact["link"], "exact_calendar_event_reference")

    def test_life_fabric_does_not_treat_document_or_provider_as_completed(self):
        row = task(data={"source_ref": "cal-42", "depends_on": []},
                   completion_state="document_supported")
        with patch.object(fusion, "_life_rows", return_value=([row], "available")):
            found, _ = fusion._life(EVENT, PROJECTS, NOW)
        self.assertEqual(found[0]["completion_state"], "document_supported")

    def test_unavailable_provider_isolated_without_suppressing_others(self):
        with patch.object(fusion, "_guardian_rows", side_effect=sqlite3.OperationalError("closed")), \
             patch.object(fusion, "_life_rows", return_value=([task()], "available")):
            result = fusion.compile_evidence(EVENT, INTENTIONS, PROJECTS, now=NOW)
        self.assertEqual(result["source_status"]["guardian"], "unavailable")
        self.assertEqual(len(result["sections"]["life_fabric"]), 1)

    def test_phone_mission_remains_local_absent_opt_in_exact_event_snapshot(self):
        mission = {
            "calendarID": "cal-42", "startsAt": EVENT["start"],
            "literalDestination": EVENT["location"],
            "checkedAt": NOW.isoformat(), "phase": "reviewRequired",
            "routeCheckedAt": (NOW-timedelta(seconds=20)).isoformat(),
        }
        self.assertEqual(fusion._mission(EVENT, None, NOW)[1], "phone_local_not_shared")
        self.assertEqual(fusion._mission(EVENT, mission | {"calendarID": "another"}, NOW)[1], "different_event")
        self.assertEqual(fusion._mission(EVENT, mission | {"startsAt": DUE}, NOW)[1], "event_time_mismatch")
        self.assertEqual(fusion._mission(EVENT, mission | {"literalDestination": "Other road"}, NOW)[1], "destination_mismatch")
        self.assertEqual(fusion._mission(EVENT, mission | {"checkedAt": (NOW-timedelta(minutes=3)).isoformat()}, NOW)[1], "stale_phone_snapshot")
        results, status = fusion._mission(EVENT, mission, NOW)
        self.assertEqual(status, "provided_for_exact_event")
        self.assertEqual(results[0]["phase"], "reviewRequired")
        self.assertNotIn("gps", str(results).lower())

    def test_reality_lens_requires_exact_resolved_location_and_two_saved_snapshots(self):
        old, new = (NOW-timedelta(hours=1)), (NOW-timedelta(minutes=10))
        metrics = lambda aq: json.dumps({
            "fact:air_quality": {
                "label": "Modelled US AQI", "value": aq,
                "source": "Open-Meteo Air Quality",
                "observed_at": NOW.isoformat(),
            },
            "fact:active_weather_alert_count": {
                "value": 0, "source": "NWS", "observed_at": NOW.isoformat(),
            },
        })
        rows = [
            {"id": "s2", "captured_at": new.isoformat(), "metrics_json": metrics(65)},
            {"id": "s1", "captured_at": old.isoformat(), "metrics_json": metrics(44)},
        ]
        place = {"literal_location": EVENT["location"], "latitude": 34.1,
                 "longitude": -118.1}
        self.assertEqual(fusion._lens(EVENT, None, NOW)[1], "exact_place_not_linked")
        self.assertEqual(fusion._lens(EVENT, place | {"literal_location": "Somewhere else"}, NOW)[1], "location_mismatch")
        with patch.object(fusion, "_lens_rows", return_value=(rows, "available")):
            found, status = fusion._lens(EVENT, place, NOW)
        self.assertEqual(status, "historical_diff")
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["before"], found[0]["after"]), (44, 65))
        self.assertIn("NOT current", found[0]["qualifier"])
        with patch.object(fusion, "_lens_rows", return_value=(
            [rows[0] | {"captured_at": (NOW-timedelta(hours=3)).isoformat()}, rows[1]],
            "available"
        )):
            self.assertEqual(fusion._lens(EVENT, place, NOW)[1], "no_recent_pair")

    def test_no_implicit_db_file_created_for_unenrolled_adapters(self):
        with TemporaryDirectory() as temp:
            wdb, ldb, rdb = (Path(temp)/x for x in ("world.db", "life.db", "lens.db"))
            with patch("jarvis_mrb.world_model.DB_PATH", wdb), \
                 patch("jarvis_mrb.life_fabric.STORE", ldb), \
                 patch("jarvis_mrb.reality_lens.STORE", rdb):
                self.assertEqual(fusion._guardian_rows()[1], "no_enrolled_data")
                self.assertEqual(fusion._life_rows()[1], "no_enrolled_data")
                self.assertEqual(fusion._lens_rows("unknown")[1], "no_enrolled_data")
            self.assertFalse(any(Path(temp).iterdir()))

    def test_context_for_query_uses_all_source_tags_and_preserves_old_content(self):
        cross = {
            "sections": {
                "guardian": [{
                    "watch_id": "watch-1", "observed_at": NOW.isoformat(),
                    "title": "Quarterly budget planning",
                    "signal": "at_risk", "deadline_at": DUE,
                    "qualifier": "Not a live route calculation.",
                }],
                "life_fabric": [{
                    "task_id": "task-1", "link": "two_distinct_event_title_terms",
                    "title": "Quarterly budget draft", "due_state": "next_24h",
                    "completion_state": "not_verified", "blocked": True,
                    "qualifier": "Manually enrolled.",
                }],
                "mission_control": [],
                "reality_lens": [],
            },
            "source_status": {
                "mission_control": "phone_local_not_shared",
                "reality_lens": "exact_place_not_linked",
            },
        }
        with patch.object(world_situation, "_refresh_near_term_if_needed"), \
             patch.object(world_situation, "_select_event",
                          return_value=(EVENT, [], ["starts within 2 hours"])), \
             patch.object(world_situation, "_related_projects", return_value=[]), \
             patch.object(world_situation, "_pending_commitments", return_value=[]), \
             patch.object(world_situation, "_linked_intentions", return_value=INTENTIONS), \
             patch.object(world_situation, "_recent_evidence", return_value=[]), \
             patch.object(world_situation, "compile_evidence", return_value=cross):
            rendered = world_situation.context_for_query("anything I need to know before I go in?")
            structured = world_situation.compile_situation("anything I need to know before I go in?")
        self.assertIn("Meeting: Quarterly budget planning", rendered)
        self.assertIn("Guardian enrolled watch", rendered)
        self.assertIn("Life Fabric user-enrolled task", rendered)
        self.assertIn("phone-local Mission Control was not shared", rendered)
        self.assertIn("No all-clear may be inferred", rendered)
        self.assertIn("cross_source_evidence", structured)

    def test_irrelevant_query_never_pulls_additional_private_data(self):
        with patch.object(world_situation, "compile_evidence",
                          side_effect=AssertionError("must not fetch")):
            self.assertIsNone(world_situation.compile_situation("Hello there."))

    def test_status_discloses_absent_phone_auto_sync(self):
        with patch.object(world_situation, "_latest_calendar_events", return_value=[]):
            value = world_situation.status()
        self.assertTrue(value["additional_source_qualified_evidence"])
        self.assertFalse(value["iphone_mission_auto_sync"])
        self.assertFalse(value["lens_location_label_only_join"])


if __name__ == "__main__":
    unittest.main()
