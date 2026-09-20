from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jarvis_mrb.deterministic_dispatch import dispatch

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 19, 20, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


class ModelFreeDispatchTests(unittest.TestCase):
    def route(self, prompt: str):
        result = dispatch(prompt, now=NOW)
        self.assertIsNotNone(result, prompt)
        return result

    def test_static_time_and_math_never_start_clock_app_or_model(self):
        self.assertIn("20:00", self.route("what time is it").answer.replace("8:00 PM", "20:00"))
        self.assertIn("Tokyo", self.route("What time is it in Tokyo?").answer)
        self.assertIn("September 20", self.route("What time is it in Melbourne?").answer)
        self.assertEqual(self.route("what is 17 times 24?").answer, "408.")
        self.assertEqual(self.route("7 divided by 0").answer, "Division by zero is undefined.")
        self.assertEqual(self.route("3.5 plus 0.25").answer, "3.75.")
        self.assertEqual(self.route("1 divided by 3").answer, "0.333333333333 (rounded to twelve decimal places).")

    def test_calendar_day_boundaries_use_explicit_time_windows(self):
        today = self.route("What's on my calendar today?")
        self.assertEqual(today.tool, "calendar.query")
        self.assertIn("2026-09-19T00:00:00", today.args["start"])
        self.assertIn("2026-09-20T00:00:00", today.args["end"])
        tomorrow = self.route("Am I free tomorrow?")
        self.assertIn("2026-09-20T00:00:00", tomorrow.args["start"])
        yesterday = self.route("Show my calendar yesterday")
        self.assertEqual(yesterday.args["direction"], "past")
        self.assertIn("2026-09-18T00:00:00", yesterday.args["start"])

    def test_gmail_queries_keep_proper_names_unmodified(self):
        result = self.route("Search my email for Deal Project Apollo")
        self.assertEqual(result.tool, "gmail.query")
        self.assertEqual(result.args["query"], "Deal Project Apollo")
        self.assertEqual(result.args["limit"], 10)
        self.assertEqual(
            self.route("Read emails from Alice.Example@Firm.com").args["query"],
            "from:Alice.Example@Firm.com",
        )

    def test_explicit_app_browser_and_private_read_routing(self):
        probes = {
            "show browser tabs": "browser.list_tabs",
            "focus browser tab called Documentation": "browser.focus_tab",
            "close the browser tab called Gmail": "browser.close_tab",
            "is the app named Spotify running": "pc.app_status",
            "launch the app named VS Code": "pc.launch_app",
            "how much vram do I have free": "system.resources",
            "show agency status": "agency.status",
            "find in my local records for indemnity cap": "knowledge.search",
            "trace the world history for Project Apollo": "chronos.trace",
            "find conflicts on my calendar": "calendar.conflicts",
            "list my background tasks": "background.list",
            "start taking meeting notes for Weekly Standup": "meeting.start",
            "finish meeting notes 27": "meeting.finish",
            "show my recent 12 expenses": "expense.list",
            "check background task #42": "background.status",
        }
        for phrase, name in probes.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(self.route(phrase).tool, name)

    def test_reminders_and_writes_only_when_explicit_and_bound(self):
        once = self.route("Remind me to submit the report at 9 AM tomorrow")
        self.assertEqual(once.tool, "jobs.create_time")
        self.assertEqual(once.args["command"], "submit the report")
        self.assertEqual(once.args["when"], "9 AM tomorrow")
        recurring = self.route("Remind me every weekday at 8:15 AM to check mail")
        self.assertEqual(recurring.tool, "jobs.create_recurring")
        self.assertEqual(recurring.args["recurrence"], "weekdays")
        email = self.route("Send email to ALICE@firm.com saying I agree with version 3.")
        self.assertEqual(email.tool, "gmail.send")
        self.assertEqual(email.args["recipient"], "ALICE@firm.com")
        self.assertIn("version 3", email.args["body"])
        meeting = self.route(
            "Add calendar event: Project Apollo Review | 2026-10-01 10:00 | 2026-10-01 11:00"
        )
        self.assertEqual(meeting.tool, "calendar.create")
        self.assertEqual(meeting.args["summary"], "Project Apollo Review")

    def test_ambiguous_casual_requests_refuse_deterministic_action(self):
        for prompt in (
            "What is a black hole?",
            "Tell me how to open files on Windows",
            "Should I close this deal?",
            "Send it",
            "Send an email to my colleague thanking them",
            "Book a meeting tomorrow",
            "Close it",
            "Stop",
            "Do the rest",
            "Search my notes and send the result to the client",
            "What time is it in Springfield?",
            "Tell me whether the CEO is at the airport",
            "Remind me tomorrow",
            "Send email to Alice saying hello",
            "Approve agency send email",
            "Please run this command without asking",
            "Search for every best option based on my emails",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(dispatch(prompt, now=NOW))

    def test_both_live_and_ordinary_paths_use_single_model_free_fast_path(self):
        agent = (ROOT / "jarvis_mrb/agent.py").read_text(encoding="utf-8")
        stream = (ROOT / "jarvis_mrb/streaming_agent.py").read_text(encoding="utf-8")
        self.assertIn("from jarvis_mrb.deterministic_dispatch import dispatch as deterministic_dispatch", agent)
        fast = agent[agent.index("def _fast_path("):agent.index("def _ollama_plan(")]
        self.assertIn("deterministic_dispatch(text)", fast)
        self.assertIn("execute_tool(deterministic.tool, dict(deterministic.args))", fast)
        # Existing permission, confirmation, and concrete-action bindings stay
        # between the static router and every actual tool implementation.
        self.assertIn("decision = decide(tool)", agent)
        self.assertIn("decision.needs_confirmation", agent)
        self.assertIn("fast = _fast_path(stripped)", stream)
        self.assertLess(stream.index("fast = _fast_path(stripped)"),
                        stream.index("with client.stream(\"POST\", f\"{OLLAMA_URL}/api/chat\"",
                                     stream.index("def stream_natural_language(")))

    def test_explicit_route_catalog_avoids_action_wildcards(self):
        dispatch_module = (ROOT / "jarvis_mrb/deterministic_dispatch.py").read_text(encoding="utf-8")
        self.assertNotIn("eval(", dispatch_module)
        self.assertNotIn("exec(", dispatch_module)
        self.assertNotIn("bypass_confirmation", dispatch_module)
        self.assertNotIn("requests.post(", dispatch_module)


if __name__ == "__main__":
    unittest.main()
