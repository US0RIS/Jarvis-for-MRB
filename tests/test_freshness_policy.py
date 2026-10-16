"""Regression tests for current-public-claim routing and explicit AirPods wiring."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from jarvis_mrb.freshness_policy import FreshnessDecision, freshness_decision


ROOT = Path(__file__).resolve().parents[1]


class FreshnessPolicyTests(unittest.TestCase):
    def test_new_public_model_release_forces_lookup(self) -> None:
        self.assertEqual(
            freshness_decision("Did Google announce Gemini 4 Argon today?").kind,
            "verify",
        )
        self.assertEqual(
            freshness_decision("Gemma 4 was just released - is it any good?").kind,
            "search",
        )

    def test_suspect_public_screenshot_is_verified_not_forged_from_pixels(self) -> None:
        decision = freshness_decision("Is the Gemini 4 Argon announcement fake?")
        self.assertEqual(decision.kind, "verify")
        self.assertIn("Gemini 4 Argon", decision.query)
        self.assertNotIn("fake", decision.query)
        ambiguous = freshness_decision("Is this screenshot fake?")
        self.assertEqual(ambiguous.kind, "clarify")

    def test_user_supplied_public_screenshot_triggers_verification(self) -> None:
        decision=freshness_decision("I have a screenshot that shows Google announced Gemini 4 Argon.")
        self.assertEqual(decision.kind,"verify")
        self.assertEqual(decision.query,"Google Gemini 4 Argon official announcement post")
        self.assertIsNone(freshness_decision(
            "My private screenshots show my email about Gemini 4 Argon."
        ))

    def test_current_availability_forces_lookup(self) -> None:
        self.assertEqual(
            freshness_decision("Is the iPhone 18 currently available?").kind,
            "search",
        )
        self.assertEqual(
            freshness_decision("What's the latest Gemini model?").kind,
            "search",
        )

    def test_disputed_public_post_without_referent_cannot_be_denied(self) -> None:
        decision = freshness_decision("How do you know they didn't post it?")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "clarify")
        self.assertIn("cannot establish", decision.message)

    def test_disputed_public_post_uses_safe_user_context(self) -> None:
        decision = freshness_decision(
            "How do you know they didn't post it?",
            history=[
                {"role": "user", "content": "Google announced Gemini 4 Argon today"},
                {"role": "assistant", "content": "That sounds fabricated."},
            ],
        )
        self.assertEqual(decision.kind, "verify")
        self.assertIn("Google Gemini 4 Argon official announcement post", decision.query)
        self.assertNotIn("announced", decision.query)

    def test_no_private_context_is_sent_to_public_search(self) -> None:
        decision = freshness_decision(
            "How do you know they didn't post it?",
            history=[
                {"role": "user", "content": "My private email to Google about Gemini 4 Argon"},
            ],
        )
        self.assertEqual(decision.kind, "clarify")
        self.assertIsNone(freshness_decision("What's in my calendar today?"))
        self.assertIsNone(freshness_decision("Has my email about the release been sent?"))

    def test_stable_and_nonpublic_requests_do_not_use_web(self) -> None:
        for question in (
            "Explain Newton's laws",
            "What is 12 times 34?",
            "Why do you prefer this design?",
            "What did I say about the product last week?",
            "Who was the president in 1863?",
            "Launch the Apple Notes application",
        ):
            with self.subTest(question=question):
                self.assertIsNone(freshness_decision(question))

    def test_both_conversation_paths_enforce_gate_before_model(self) -> None:
        agent = (ROOT / "jarvis_mrb/agent.py").read_text(encoding="utf-8")
        streaming = (ROOT / "jarvis_mrb/streaming_agent.py").read_text(encoding="utf-8")
        agent_entry = agent[agent.index("def handle_natural_language("):]
        stream_entry = streaming[streaming.index("def stream_natural_language("):]
        for text in (agent_entry, stream_entry):
            self.assertLess(text.index("freshness_decision("), text.index("_fast_path("))
            self.assertIn('tool_name = "web.verify"', text)
            self.assertIn("execute_tool(tool_name", text)

    def test_normal_chat_calls_search_before_model(self) -> None:
        from jarvis_mrb import agent

        with (
            patch.object(agent, "_ollama_plan", side_effect=AssertionError("model ran")) as planner,
            patch.object(agent, "execute_tool", return_value=agent.AgentReply(True, "Verified by web search")) as tool,
        ):
            result = agent.handle_natural_language("Did Google announce Gemini 4 Argon today?")
        self.assertIn("Verified by web search", result.message)
        tool.assert_called_once_with(
            "web.verify", {"query": "Did Google announce Gemini 4 Argon today?", "num": 8}
        )
        planner.assert_not_called()

    def test_streaming_chat_calls_search_before_model(self) -> None:
        from jarvis_mrb import streaming_agent

        with patch.object(
            streaming_agent, "execute_tool",
            return_value=streaming_agent.AgentReply(True, "Verified by web search"),
        ) as tool:
            response = list(streaming_agent.stream_natural_language("Did Google announce Gemini 4 Argon today?"))
        self.assertIn("Verified by web search", " ".join(response))
        tool.assert_called_once_with(
            "web.verify", {"query": "Did Google announce Gemini 4 Argon today?", "num": 8}
        )

    def test_airpods_selection_is_not_just_ui_label(self) -> None:
        settings = (ROOT / "ios/JarvisIOS/SettingsStore.swift").read_text(encoding="utf-8")
        route = (ROOT / "ios/JarvisIOS/SpeechRecognizer.swift").read_text(encoding="utf-8")
        ui = (ROOT / "ios/JarvisIOS/SettingsView.swift").read_text(encoding="utf-8")
        self.assertIn("bluetoothAudioDevicePreference", settings)
        self.assertIn('case "airpods":', route)
        self.assertIn("session.setPreferredInput(selectedBluetooth)", route)
        self.assertIn("try session.setPreferredInput(builtInInput)", route)
        self.assertIn('Text("AirPods").tag("airpods")', ui)
        self.assertIn("audioRouteManager.routeSummary", ui)


if __name__ == "__main__":
    unittest.main()
