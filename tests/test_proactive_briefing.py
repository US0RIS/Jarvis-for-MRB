from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.proactive_attention as attention
import jarvis_mrb.proactive_briefing as briefing
import jarvis_mrb.world_armor_push as push
import jarvis_mrb.world_model as world_model
from jarvis_mrb import event_bus
# Import the runtime service once at collection time, before any test patches the
# world-model path. Importing it lazily inside a patched test runs the migrations
# against the wrong database. The full suite does the same thing implicitly.
import jarvis_mrb.proactive_monitor as monitor  # runs the world migrations once, unpatched
from jarvis_mrb.voice_router import turn_context

# Local-aware so quiet-hours (evaluated in local time) are deterministic.
NOW = datetime(2026, 10, 21, 14, 0).astimezone()
START = NOW + timedelta(minutes=15)


def strong_doc_change():
    return {
        "message": "Before Dana sync: A connected draft changed: the term sheet now says 15 percent",
        "severity": "warning", "meeting_id": "evt1",
        "facts": ["A connected draft changed: the term sheet now says 15 percent"],
        "has_commitments": False, "has_intentions": False, "has_recent_evidence": True,
        "has_document_change": True, "has_term_conflict": False, "deduplicated_evidence_count": 0,
    }


def weak_update():
    return {
        "message": "Before Dana sync: Recent connected update: lunch notes",
        "severity": "info", "meeting_id": "evt1",
        "facts": ["Recent connected update: lunch notes"],
        "has_commitments": False, "has_intentions": False, "has_recent_evidence": True,
        "has_document_change": False, "has_term_conflict": False, "deduplicated_evidence_count": 0,
    }


class BriefingBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old = (world_model.APP_DIR, world_model.DB_PATH, push.PUSH_STORE)
        root = Path(self.temp.name)
        world_model.APP_DIR = root
        world_model.DB_PATH = root / "world_model.sqlite3"
        push.PUSH_STORE = root / "push.sqlite3"
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for key in ("JARVIS_WORLD_ARMOR_ENABLED", "JARVIS_WORLD_ARMOR_PUSH_ENABLED"):
            os.environ.pop(key, None)
        self.patch = patch.object(event_bus, "emit_proactive")
        self.emit = self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.env.stop()
        (world_model.APP_DIR, world_model.DB_PATH, push.PUSH_STORE) = self.old
        self.temp.cleanup()

    def consider(self, evidence, *, now=NOW, start=START, event_id="evt1", alerts=None):
        calls = []

        def provider(eid, summary):
            calls.append((eid, summary))
            return evidence() if callable(evidence) else evidence
        out = briefing.consider_event(
            event_id, "Dana sync", start, now=now, evidence_provider=provider,
            watch_alert_provider=lambda _now: alerts or [])
        out["provider_calls"] = calls
        return out

    def say(self, text):
        with turn_context("b", None) as turn:
            return briefing.handle(text, turn)


class BriefingDecisionTests(BriefingBase):
    def test_strong_evidence_briefs_with_only_evidence_facts_and_truthful_delivery(self) -> None:
        out = self.consider(strong_doc_change)
        self.assertEqual(out["decision"], "emitted")
        self.assertGreaterEqual(out["score"], 40)
        self.assertEqual(out["text"], (
            "Dana sync starts in fifteen minutes. "
            "A connected draft changed: the term sheet now says 15 percent."))
        item = attention.ledger()[0]
        self.assertEqual(item["kind"], "briefing")
        self.assertEqual(item["push_state"], "not_configured")
        self.assertEqual(item["live_state"], "no_live_client")
        self.assertFalse(item["confirmed_delivery"])
        self.emit.assert_called_once()
        self.assertEqual(self.emit.call_args.args[0], out["text"])
        self.assertEqual(self.emit.call_args.kwargs["severity"], "warning")

    def test_weak_evidence_is_recorded_suppressed_and_never_spoken(self) -> None:
        out = self.consider(weak_update)
        self.assertEqual((out["decision"], out["reason"]), ("suppressed", "weak_evidence"))
        self.assertLess(out["score"], 40)
        self.emit.assert_not_called()
        rows = attention.ledger()
        self.assertEqual([(r["decision"], r["suppress_reason"]) for r in rows], [("suppressed", "weak_evidence")])
        self.assertEqual(rows[0]["push_state"], "")  # nothing was delivered
        # Re-evaluating every monitor cycle must not pile up rows.
        self.consider(weak_update, now=NOW + timedelta(minutes=1), start=START)
        self.assertEqual(len(attention.ledger()), 1)
        self.assertEqual(attention.ledger()[0]["seen_count"], 2)

    def test_pending_commitment_alone_is_below_threshold_until_flagged_overdue(self) -> None:
        pending = {**weak_update(), "has_recent_evidence": False, "has_commitments": True,
                   "facts": ["Dana still owes the revised term sheet"]}
        self.assertEqual(self.consider(pending)["decision"], "suppressed")
        overdue = {**pending, "severity": "warning"}
        out = self.consider(overdue, event_id="evt2")
        self.assertEqual(out["decision"], "emitted")
        self.assertIn("Dana still owes the revised term sheet.", out["text"])

    def test_recent_watch_alert_raises_relevance_and_is_cited(self) -> None:
        alert = {"id": "a1", "text": "Flood Warning near this area", "severity": "warning",
                 "created_at": (NOW - timedelta(minutes=20)).isoformat()}
        out = self.consider(weak_update, alerts=[alert])
        self.assertEqual(out["decision"], "emitted")
        self.assertIn("Flood Warning near this area", out["text"])

    def test_no_evidence_or_provider_failure_is_suppressed_not_invented(self) -> None:
        out = self.consider(None)
        self.assertEqual(out["reason"], "no_evidence")
        failing = briefing.consider_event(
            "evt9", "Other", START, now=NOW,
            evidence_provider=lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
            watch_alert_provider=lambda _n: [])
        self.assertEqual(failing["reason"], "no_evidence")
        self.emit.assert_not_called()

    def test_only_inside_the_lead_window(self) -> None:
        early = self.consider(strong_doc_change, start=NOW + timedelta(minutes=40))
        late = self.consider(strong_doc_change, start=NOW + timedelta(minutes=3))
        past = self.consider(strong_doc_change, start=NOW - timedelta(minutes=2))
        self.assertEqual([early["decision"], late["decision"], past["decision"]], ["skipped"] * 3)
        self.assertEqual(early["provider_calls"], [])
        self.emit.assert_not_called()

    def test_duplicate_briefing_for_same_event_is_suppressed(self) -> None:
        self.assertEqual(self.consider(strong_doc_change)["decision"], "emitted")
        again = self.consider(strong_doc_change, now=NOW + timedelta(minutes=1))
        self.assertEqual(again["decision"], "duplicate")
        self.assertEqual(self.emit.call_count, 1)
        # A rescheduled start is a different briefing.
        moved = self.consider(strong_doc_change, now=NOW + timedelta(minutes=30), start=NOW + timedelta(minutes=45))
        self.assertEqual(moved["decision"], "emitted")

    def test_shared_budget_with_watch_alerts(self) -> None:
        attention.set_prefs(hourly_budget=1)
        attention.submit(attention.ProactiveItem(
            kind="watch_alert", subject="w", dedupe_key="k", text="quake"), now=NOW)
        out = self.consider(strong_doc_change)
        self.assertEqual((out["decision"], out["reason"]), ("suppressed", "budget"))
        self.assertEqual(self.emit.call_count, 1)
        # It stays inspectable and "what did you hold back" can say so.
        with turn_context("b", None) as turn:
            said = attention.handle("what did I miss", turn)
        self.assertIn("hourly interruption limit", said)
        self.assertIn("Dana sync starts in fifteen minutes", said)


class PreferenceTests(BriefingBase):
    def test_disable_and_enable_by_voice(self) -> None:
        reply = self.say("stop proactive briefings")
        self.assertIn("off", reply)
        self.assertFalse(attention.get_prefs()["briefings_enabled"])
        out = self.consider(strong_doc_change)
        self.assertEqual((out["decision"], out["reason"]), ("suppressed", "disabled"))
        self.emit.assert_not_called()
        self.assertIn("off", self.say("are proactive briefings on"))
        back = self.say("turn briefings back on")
        self.assertIn("back on", back)
        self.assertEqual(self.consider(strong_doc_change, event_id="evt3")["decision"], "emitted")

    def test_snooze_for_an_hour_then_expires(self) -> None:
        real_now = datetime.now().astimezone()
        reply = self.say("snooze briefings for an hour")
        self.assertIn("no proactive briefings until", reply)
        self.assertIn("Watch alerts you asked for still come through", reply)
        prefs = attention.get_prefs()
        self.assertTrue(prefs["snoozed"])
        snooze_end = datetime.fromisoformat(prefs["snooze_until"])
        self.assertAlmostEqual((snooze_end - real_now).total_seconds(), 3600, delta=5)
        start = real_now + timedelta(minutes=15)
        out = self.consider(strong_doc_change, now=real_now, start=start)
        self.assertEqual((out["decision"], out["reason"]), ("suppressed", "snoozed"))
        later = real_now + timedelta(minutes=70)
        out = self.consider(strong_doc_change, now=later, start=later + timedelta(minutes=15))
        self.assertEqual(out["decision"], "emitted")
        self.assertIn("For how long", self.say("snooze briefings"))

    def test_snooze_does_not_silence_watch_alerts(self) -> None:
        self.say("snooze proactive briefings for two hours")
        out = attention.submit(attention.ProactiveItem(
            kind="watch_alert", subject="w", dedupe_key="k-snooze", text="earthquake"))
        self.assertEqual(out["decision"], "emitted")

    def test_quiet_hours_suppress_briefings_only(self) -> None:
        self.assertIn("10:00 PM to 7:00 AM", self.say("set quiet hours from 10 pm to 7 am"))
        night = datetime(2026, 10, 21, 23, 0).astimezone()
        out = self.consider(strong_doc_change, now=night, start=night + timedelta(minutes=15))
        self.assertEqual((out["decision"], out["reason"]), ("suppressed", "quiet_hours"))
        noon = datetime(2026, 10, 21, 12, 0).astimezone()
        ok = self.consider(strong_doc_change, now=noon, start=noon + timedelta(minutes=15), event_id="evt4")
        self.assertEqual(ok["decision"], "emitted")
        alert = attention.submit(attention.ProactiveItem(
            kind="watch_alert", subject="w", dedupe_key="kq", text="quake"), now=night)
        self.assertEqual(alert["decision"], "emitted")
        self.assertIn("Quiet hours are off", self.say("turn off quiet hours"))
        self.assertEqual(attention.get_prefs()["quiet_start"], "")

    def test_interruption_limit_by_voice_and_validation(self) -> None:
        self.assertIn("at most 2", self.say("limit proactive alerts to 2 an hour"))
        self.assertEqual(attention.get_prefs()["hourly_budget"], 2)
        with self.assertRaises(ValueError):
            attention.set_prefs(hourly_budget=0)
        with self.assertRaises(ValueError):
            attention.set_prefs(quiet_start="25:00", quiet_end="07:00")
        with self.assertRaises(ValueError):
            attention.set_prefs(quiet_start="22:00")

    def test_unrelated_briefing_requests_are_not_captured(self) -> None:
        for text in ("give me my briefing", "give me my daily briefing at 8", "stop", "snooze", "cancel", "morning briefing"):
            self.assertIsNone(self.say(text), text)

    def test_status_does_not_claim_monitoring_when_monitor_is_not_running(self) -> None:
        self.assertIn("background monitor is not running", self.say("turn briefings back on"))
        with patch.object(briefing, "_monitor_running", return_value=True):
            self.assertNotIn("not running", self.say("turn briefings back on"))


class WhyTests(BriefingBase):
    def test_why_after_briefing_gives_rule_score_threshold_and_evidence(self) -> None:
        self.consider(strong_doc_change)
        with turn_context("w", None) as turn:
            answer = attention.handle("why did you tell me that", turn)
        self.assertIn("I briefed you at", answer)
        self.assertIn("pre-meeting briefing", answer)
        self.assertIn("scored 45 against a threshold of 40", answer)
        self.assertIn("the term sheet now says 15 percent", answer)
        self.assertIn("Source: Horus world model", answer)

    def test_why_reports_the_most_recent_item_across_watch_and_briefing(self) -> None:
        self.consider(strong_doc_change)
        attention.submit(attention.ProactiveItem(
            kind="watch_alert", subject="w", dedupe_key="kw", text="Quake near you", rule="your earthquake watch",
            source="USGS", evidence_lines=["M4.8 somewhere"]), now=NOW + timedelta(minutes=1))
        with turn_context("w", None) as turn:
            answer = attention.handle("why did you alert me", turn)
        self.assertIn("I alerted you at", answer)
        self.assertIn("your earthquake watch", answer)
        self.assertIn("Source: USGS", answer)


class MonitorIntegrationTests(BriefingBase):
    def test_calendar_check_routes_prebrief_through_scored_briefing(self) -> None:

        class Result:
            ok = True
            message = ""
            data = {"events": [{"id": "evt1", "summary": "Dana sync", "start": START.isoformat()}]}

        with patch.object(monitor, "query_calendar_events", return_value=Result()), \
                patch.object(monitor, "_contextual_prebrief", return_value=strong_doc_change()), \
                patch.object(monitor, "_prefetch_for_event"), \
                patch.object(monitor, "datetime") as fake_dt:
            fake_dt.now.return_value = NOW
            fake_dt.fromisoformat.side_effect = datetime.fromisoformat
            monitor._check_calendar()
        texts = [call.args[0] for call in self.emit.call_args_list]
        self.assertEqual(len([t for t in texts if "term sheet now says 15 percent" in t]), 1)
        self.assertEqual(attention.ledger(kind="briefing")[0]["decision"], "emitted")


if __name__ == "__main__":
    unittest.main()
