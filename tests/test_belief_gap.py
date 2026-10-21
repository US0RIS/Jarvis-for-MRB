from __future__ import annotations

"""Belief-gap acceptance on the real world-model + document-version pipeline
(temporary database). Conversation turns are recorded exactly as the service
records them; nothing here reads a person's mind."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import jarvis_mrb.world_document_versions as wdv
import jarvis_mrb.world_linker as world_linker
import jarvis_mrb.world_model as world_model
from jarvis_mrb import belief_gap
# Import the runtime service once at collection time, before any test patches the
# world-model path. Importing it lazily inside a patched test runs the migrations
# against the wrong database. The full suite does the same thing implicitly.
import jarvis_mrb.proactive_monitor  # noqa: F401  (runs the world migrations once, unpatched)
from jarvis_mrb import service
from jarvis_mrb.voice_router import clear_focus, current_turn, observe, turn_context

NOW = datetime.now(timezone.utc)


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


class BeliefGapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        db = base / "world_model.sqlite3"
        self.patches = [
            mock.patch.object(world_model, "APP_DIR", base),
            mock.patch.object(world_model, "DB_PATH", db),
            mock.patch.object(world_linker, "DB_PATH", db),
            mock.patch.object(wdv, "DB_PATH", db),
            mock.patch.object(belief_gap, "DB_PATH", base / "gaps.sqlite3"),
        ]
        for p in self.patches:
            p.start()
        world_model.status()
        world_linker.status()
        wdv.status()
        self.session = "gap-" + self.id()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        clear_focus(session_id=self.session)
        self.tmp.cleanup()

    def attachment(self, ref, filename, text, occurred_at):
        event_id = world_model.record_knowledge_source(
            "gmail_attachment", ref, title=filename, text=text, occurred_at=occurred_at,
            metadata={"message_id": ref.split(":", 1)[0], "thread_id": "t", "filename": filename,
                      "email_subject": "Chronos purchase agreement"})
        world_linker.link_event(event_id)
        return event_id

    def versions(self):
        self.attachment("m1:a1", "Project Chronos Purchase Agreement Draft v1.docx",
                        "Project Chronos. The indemnity cap shall equal 10% of the Purchase Price. Survival is 18 months.",
                        ago(10))
        self.attachment("m2:a2", "Project Chronos Purchase Agreement Revised v2.docx",
                        "Project Chronos. The indemnity cap shall equal 15% of the Purchase Price. Survival is 18 months.",
                        ago(3))
        self.assertEqual(wdv.refresh()["pairs_with_changes"], 1)

    def turn(self, user, assistant, days):
        from jarvis_mrb.world_occurrence import record_conversation_occurrence
        record_conversation_occurrence(self.session, user, assistant, occurred_at=ago(days))

    def warn(self, text):
        with turn_context(self.session, {"channel": "voice"}):
            return observe(text)

    def test_change_plus_prior_exposure_plus_reliance_produces_explainable_warning(self):
        self.versions()
        self.turn("What's the indemnity cap in the Chronos purchase agreement?",
                  "The Chronos purchase agreement sets the indemnity cap at 10% of the purchase price.", 7)
        warning = self.warn("Draft a note saying the Chronos purchase agreement caps indemnity at ten percent")
        self.assertIn("One important thing", warning)
        self.assertIn("now says 15%", warning)
        self.assertIn("used 10%", warning)
        self.assertIn("I told you", warning)
        self.assertIn("I don't know whether you've seen the update", warning)
        self.assertNotIn("believe", warning)
        with turn_context(self.session, {"channel": "voice"}):
            why = belief_gap.handle("Why did you warn me?", current_turn())
            self.assertIn("changed 10% to 15%", why)
            self.assertIn("about to rely on the old figure", why)
            self.assertIn("won't warn", belief_gap.handle("dismiss that", current_turn()))
        self.assertEqual(self.warn("the Chronos purchase agreement cap is 10 percent"), "")

    def test_missing_exposure_evidence_never_fabricates_a_belief(self):
        self.versions()
        self.turn("What's for lunch?", "I don't have your lunch plans.", 7)
        self.assertEqual(self.warn("the Chronos purchase agreement cap is 10%"), "")
        self.assertEqual(belief_gap.find_gaps(), [])

    def test_exposure_after_the_change_closes_the_gap(self):
        self.versions()
        self.turn("Chronos purchase agreement cap?", "The Chronos purchase agreement cap is 10%.", 7)
        self.turn("Did the Chronos purchase agreement change?", "Yes, the Chronos purchase agreement cap is now 15%.", 1)
        self.assertEqual(self.warn("the Chronos purchase agreement cap is 10%"), "")

    def test_exposure_must_reference_the_same_document(self):
        self.versions()
        self.turn("What's our tip rate?", "Your usual tip is 10%.", 7)
        self.assertEqual(belief_gap.find_gaps(), [])
        self.turn("Chronos purchase agreement cap?", "The Chronos purchase agreement cap is 10%.", 7)
        self.assertEqual(self.warn("my tip is 10%"), "")  # no document reference = no reliance signal

    def test_user_statement_counts_as_exposure_with_correct_attribution(self):
        self.versions()
        self.turn("Remind me the Chronos purchase agreement cap is 10 percent", "Noted.", 6)
        self.assertIn("you said", self.warn("so the Chronos purchase agreement cap is 10%, right?"))

    def test_upcoming_decision_context_from_calendar(self):
        self.versions()
        self.turn("Chronos purchase agreement cap?", "The Chronos purchase agreement cap is 10%.", 7)
        soon = {"title": "Chronos purchase agreement signing", "start": (NOW + timedelta(hours=3)).isoformat()}
        later = {"title": "Chronos purchase agreement signing", "start": (NOW + timedelta(days=3)).isoformat()}
        unrelated = {"title": "Dentist", "start": (NOW + timedelta(hours=2)).isoformat()}
        self.assertEqual(belief_gap.upcoming_decision_gaps([later, unrelated]), [])
        found = belief_gap.upcoming_decision_gaps([soon])
        self.assertEqual(len(found), 1)
        text = belief_gap.deliver_upcoming(*found[0])
        self.assertIn("One important thing", text)
        self.assertEqual(belief_gap.upcoming_decision_gaps([soon]), [])  # cooldown after delivery

    def test_upcoming_meeting_briefing_carries_the_gap_and_is_silent_without_it(self):
        from jarvis_mrb import event_bus, proactive_briefing

        start = NOW + timedelta(minutes=15)
        with mock.patch.object(event_bus, "emit_proactive") as emit:
            quiet = proactive_briefing.consider_event(
                "evt-1", "Chronos purchase agreement signing", start, now=NOW,
                evidence_provider=lambda *_: None, watch_alert_provider=lambda _n: [])
            self.assertNotEqual(quiet["decision"], "emitted")   # no change/exposure evidence yet
            emit.assert_not_called()

            self.versions()
            self.turn("Chronos purchase agreement cap?", "The Chronos purchase agreement cap is 10%.", 7)
            result = proactive_briefing.consider_event(
                "evt-2", "Chronos purchase agreement signing", start, now=NOW,
                evidence_provider=lambda *_: None, watch_alert_provider=lambda _n: [])
        self.assertEqual(result["decision"], "emitted")
        self.assertIn("starts in fifteen minutes", result["text"])
        self.assertIn("now says 15%", result["text"])
        self.assertIn("I don't know whether you've seen the update", result["text"])
        emit.assert_called_once()
        # Delivered once; the same gap is not repeated for a second event right away.
        self.assertEqual(belief_gap.upcoming_decision_gaps(
            [{"title": "Chronos purchase agreement signing", "start": start.isoformat()}], now=NOW), [])

    def test_unrelated_document_sharing_generic_words_never_creates_a_gap(self):
        self.versions()
        # Same two generic words ("purchase agreement") and the same old figure,
        # but a different document. Must not be read as exposure to Chronos.
        self.turn("Acme purchase agreement cap?", "The Acme purchase agreement cap is 10%.", 7)
        self.assertEqual(belief_gap.find_gaps(), [])
        self.assertEqual(self.warn("the Acme purchase agreement cap is 10%"), "")

    def test_no_document_change_no_warning(self):
        self.turn("Chronos purchase agreement cap?", "The Chronos purchase agreement cap is 10%.", 7)
        self.assertEqual(self.warn("the Chronos purchase agreement cap is 10%"), "")

    def test_spoken_number_normalization(self):
        self.assertEqual(belief_gap.value_keys("ten percent"), {"10%"})
        self.assertEqual(belief_gap.value_keys("10 percent and 15%"), {"10%", "15%"})
        self.assertIn("$2.5million", belief_gap.value_keys("$2.5 million"))

    def test_command_endpoint_prefixes_warning_without_replacing_answer(self):
        from fastapi.testclient import TestClient
        from jarvis_mrb.agent import AgentReply

        self.versions()
        self.turn("Chronos purchase agreement cap?", "The Chronos purchase agreement cap is 10%.", 7)
        client = TestClient(service.app)
        with mock.patch.object(service, "API_TOKEN", "secret"), \
                mock.patch.object(service, "remember_exchange_async"), \
                mock.patch.object(service, "append_message"), \
                mock.patch.object(service, "handle_natural_language", return_value=AgentReply(True, "Drafted.")):
            body = client.post("/command", headers={"Authorization": "Bearer secret"}, json={
                "text": "write that the Chronos purchase agreement cap is 10%", "session_id": self.session,
                "context": {"channel": "voice"}}).json()
        self.assertTrue(body["message"].startswith("One important thing"))
        self.assertTrue(body["message"].endswith("Drafted."))



if __name__ == "__main__":
    unittest.main()
