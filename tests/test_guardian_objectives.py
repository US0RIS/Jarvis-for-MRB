from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import jarvis_mrb.guardian_objectives as guardian

NOW = datetime(2026, 9, 22, 20, 0, tzinfo=timezone.utc)


class GuardianObjectiveTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        original = guardian.DB_PATH
        guardian.DB_PATH = Path(self.temp.name) / "guardian.sqlite3"
        self.addCleanup(setattr, guardian, "DB_PATH", original)
        guardian._PRESENCE.clear()
        self.addCleanup(guardian._PRESENCE.clear)
        self.goal = {
            "id": "goal:real", "title": "Deliver signed documents",
            "source_kind": "explicit_goal", "confidence": 1.0,
            "due_at": (NOW + timedelta(minutes=25)).isoformat(),
            "next_action": "Review final signature pages",
            "commitments": [
                {"id": "wait:one", "owner": "Counsel", "action": "Send final pages",
                 "confidence": 0.9},
            ],
        }
        self.goals = [self.goal]
        p = patch.object(guardian, "_active_goals", side_effect=lambda limit=30: self.goals)
        p.start()
        self.addCleanup(p.stop)

    def enable(self, observed=NOW, enabled=True, source="phone-a"):
        guardian.ingest_presence({
            "source_id": source, "enabled": enabled,
            "observed_at": observed.isoformat()
        }, now=observed)

    def test_only_exact_explicit_precise_goal_is_eligible(self):
        self.assertEqual(len(guardian.eligible(now=NOW)), 1)
        self.goal["source_kind"] = "inferred_goal"
        self.assertEqual(guardian.eligible(now=NOW), [])
        with self.assertRaisesRegex(ValueError, "precise timezone-aware"):
            guardian.enroll("goal:real", now=NOW)
        self.goal["source_kind"] = "explicit_goal"
        self.goal["due_at"] = "tomorrow"
        self.assertEqual(guardian.eligible(now=NOW), [])
        with self.assertRaisesRegex(ValueError, "precise timezone-aware"):
            guardian.enroll("goal:real", now=NOW)

    def test_enrollment_opt_in_and_no_auto_tool_dispatch(self):
        self.assertEqual(guardian.evaluate_once(now=NOW), [])
        record = guardian.enroll("goal:real", now=NOW)
        self.assertEqual(record["status"], "active")
        self.assertTrue(guardian.eligible(now=NOW)[0]["enrolled"])
        with patch("jarvis_mrb.agency_attention.consider", return_value={"emitted": True}) as attention, \
             patch("jarvis_mrb.environment_state.get_state", return_value={
                 "preferences": {"proactive_monitoring": True}
             }):
            passive = guardian.evaluate_once(now=NOW)
            self.assertEqual(passive[0]["status"], "at_risk")
            self.assertFalse(passive[0]["phone_consent_live"])
            self.assertIn("linked dependency", passive[0]["evidence"])
            self.assertEqual(passive[0]["options"][-1]["effect"], "local_draft_only")
            attention.assert_not_called()
            self.enable()
            active = guardian.evaluate_once(now=NOW)
            self.assertEqual(active[0]["status"], "at_risk")
            attention.assert_called_once()
            self.assertFalse(active[0]["can_actuate"])
            self.assertEqual(attention.call_args.kwargs["dedup_seconds"], 4 * 3600)

    def test_heartbeat_is_fresh_anonymous_location_free_and_replay_resistant(self):
        self.enable()
        self.assertTrue(guardian._has_live_consent(NOW + timedelta(seconds=60)))
        self.assertFalse(guardian._has_live_consent(NOW + timedelta(seconds=91)))
        guardian.ingest_presence({
            "source_id": "phone-a", "enabled": True,
            "observed_at": (NOW - timedelta(seconds=50)).isoformat()
        }, now=NOW)
        self.assertEqual(guardian._PRESENCE["phone-a"], NOW)
        guardian.ingest_presence({
            "source_id": "phone-a", "enabled": False,
            "observed_at": (NOW + timedelta(seconds=2)).isoformat()
        }, now=NOW + timedelta(seconds=2))
        self.assertFalse(guardian._has_live_consent(NOW + timedelta(seconds=2)))
        guardian.ingest_presence({
            "source_id": "private location: 34.1,-118.1",
            "enabled": True, "observed_at": NOW.isoformat()
        }, now=NOW)
        self.assertFalse(guardian._PRESENCE)

    def test_changed_deadline_blocks_until_reenrolled(self):
        guardian.enroll("goal:real", now=NOW)
        self.enable()
        self.goal["due_at"] = (NOW + timedelta(minutes=65)).isoformat()
        self.assertFalse(guardian.eligible(now=NOW)[0]["enrolled"])
        with patch("jarvis_mrb.agency_attention.consider") as attention:
            value = guardian.evaluate_once(now=NOW)
        self.assertEqual(value[0]["status"], "needs_reconfirmation")
        attention.assert_not_called()
        guardian.enroll("goal:real", now=NOW)
        self.assertTrue(guardian.eligible(now=NOW)[0]["enrolled"])

    def test_goal_completion_revocation_and_long_past_deadline(self):
        item = guardian.enroll("goal:real", now=NOW)
        self.assertEqual(guardian.revoke(item["id"])["status"], "revoked")
        self.assertEqual(guardian.evaluate_once(now=NOW), [])
        guardian.enroll("goal:real", now=NOW)
        self.goals = []
        result = guardian.evaluate_once(now=NOW)
        self.assertEqual(result[0]["status"], "no_longer_active")
        self.assertEqual(guardian.evaluate_once(now=NOW), [])
        self.goals = [self.goal]
        guardian.enroll("goal:real", now=NOW)
        self.assertEqual(guardian.evaluate_once(now=NOW + timedelta(hours=25)), [])
        statuses = {v["id"]: v["status"] for v in guardian.overview(now=NOW)["watches"]}
        self.assertEqual(statuses[item["id"]], "expired")

    def test_snooze_and_proactive_monitoring_veto(self):
        item = guardian.enroll("goal:real", now=NOW)
        self.enable()
        guardian.snooze(item["id"], hours=1, now=NOW)
        with patch("jarvis_mrb.agency_attention.consider") as attention, \
             patch("jarvis_mrb.environment_state.get_state", return_value={
                 "preferences": {"proactive_monitoring": True}
             }):
            report = guardian.evaluate_once(now=NOW)
            self.assertEqual(report[0]["status"], "at_risk")
            attention.assert_not_called()
        with patch("jarvis_mrb.agency_attention.consider") as attention, \
             patch("jarvis_mrb.environment_state.get_state", return_value={
                 "preferences": {"proactive_monitoring": False}
             }):
            report = guardian.evaluate_once(now=NOW + timedelta(hours=1, minutes=1))
            self.assertFalse(report[0]["phone_consent_live"])
            attention.assert_not_called()

    def test_full_and_invalid_enrollment_and_unknown(self):
        with self.assertRaisesRegex(ValueError, "no longer active"):
            guardian.enroll("inferred-other", now=NOW)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            guardian.revoke("missing")
        with self.assertRaisesRegex(ValueError, "between 1 and 24"):
            guardian.snooze("missing", hours=48, now=NOW)

    def test_only_verified_date_and_explicit_goal_no_unsafe_fallback(self):
        self.goal["due_at"] = (NOW + timedelta(days=400)).isoformat()
        self.assertEqual(guardian.eligible(now=NOW), [])
        self.goal["due_at"] = (NOW + timedelta(minutes=30)).replace(tzinfo=None).isoformat()
        self.assertEqual(guardian.eligible(now=NOW), [])
        self.goal["due_at"] = (NOW + timedelta(minutes=30)).isoformat()
        self.goal["confidence"] = 0.5
        self.assertEqual(guardian.eligible(now=NOW), [])
