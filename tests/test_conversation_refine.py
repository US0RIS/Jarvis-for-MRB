from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest import mock

from jarvis_mrb.agent import AgentReply, handle_natural_language
from jarvis_mrb.voice_router import clear_focus, turn_context


def at(hour, minute=0, days=1):
    base = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days)
    return (base + timedelta(hours=hour, minutes=minute)).isoformat()


EVENTS = [
    {"summary": "Standup", "start": at(9), "end": at(9, 15), "location": ""},
    {"summary": "Design review", "start": at(14), "end": at(15), "location": "Room 4"},
    {"summary": "1:1 with Dana", "start": at(16), "end": at(16, 30), "location": ""},
]


class ConversationRefineTests(unittest.TestCase):
    def setUp(self):
        self.session = "refine-" + self.id()
        self.calls = []

        def fake_execute(tool, args, **_):
            self.calls.append((tool, args))
            return AgentReply(True, "Calendar events: long listing.", {"events": EVENTS})
        self.patch = mock.patch("jarvis_mrb.agent.execute_tool", side_effect=fake_execute)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        clear_focus(session_id=self.session)

    def say(self, text, channel="voice"):
        with turn_context(self.session, {"channel": channel}):
            return handle_natural_language(text).message

    def test_calendar_then_narrow_correct_and_ordinal(self):
        first = self.say("What's on my calendar tomorrow?")
        self.assertEqual(first, "You have three events tomorrow. The first is Standup at 9 AM, then "
                                "Design review at 2 PM and 1:1 with Dana at 4 PM.")
        self.assertEqual(self.calls[0][0], "calendar.query")
        self.assertEqual(self.say("Just the afternoon."), "Two in the afternoon: Design review at 2 PM and 1:1 with Dana at 4 PM.")
        self.assertEqual(self.say("the first one"), "Design review, 2 PM, at Room 4.")
        self.assertEqual(len(self.calls), 1)  # narrowing filters, never re-fetches or invents
        self.assertEqual(self.say("what about the morning"), "Nothing in the morning.")

    def test_typed_turns_keep_full_listing_and_narrowing_still_works(self):
        self.assertEqual(self.say("what's on my calendar tomorrow", channel="text"), "Calendar events: long listing.")
        self.assertIn("Standup", self.say("only the morning", channel="text"))

    def test_after_time_filter(self):
        self.say("what's on my calendar tomorrow")
        self.assertEqual(self.say("just after 3"), "One: 1:1 with Dana at 4 PM.")

    def test_narrowing_without_prior_calendar_is_not_captured(self):
        with mock.patch("jarvis_mrb.agent._ollama_plan", return_value=(None, "planner offline")):
            reply = handle_natural_language("just the afternoon")
        self.assertEqual(reply.message, "planner offline")

    def test_cut_off_voice_utterance_asks_to_finish(self):
        self.assertIn("cut off", self.say("remind me to"))
        with mock.patch("jarvis_mrb.agent._ollama_plan", return_value=(None, "planner offline")):
            with turn_context(self.session, {"channel": "text"}):
                self.assertEqual(handle_natural_language("remind me to").message, "planner offline")


if __name__ == "__main__":
    unittest.main()
