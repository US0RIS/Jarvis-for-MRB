from __future__ import annotations

import os
import pathlib
import unittest
from unittest.mock import patch

from jarvis_mrb.cloud_cognition import (
    CloudProposal,
    GroqProvider,
    compile_cloud_context,
    prepare_cloud_task,
    redact_secrets,
    route_cognition,
    server_cloud_reason,
    validate_proposal,
)


class CloudCognitionRoutingTests(unittest.TestCase):
    def test_deterministic_capability_bypasses_llm(self):
        decision = route_cognition("open Safari", deterministic_available=True)
        self.assertEqual(decision.tier, "deterministic")

    def test_ordinary_simple_request_remains_local(self):
        decision = route_cognition("Tell me a short joke about a penguin.")
        self.assertEqual(decision.tier, "local")

    def test_genuinely_difficult_request_escalates(self):
        decision = route_cognition(
            "Debug this subtle race condition, identify the root cause, and derive a robust architecture fix."
        )
        self.assertEqual(decision.tier, "cloud")

    def test_harmless_difficult_request_can_escalate(self):
        decision = route_cognition(
            "Prove this combinatorics identity, derive a second proof, and compare the tradeoffs."
        )
        self.assertEqual(decision.tier, "cloud")

    def test_uncertainty_and_conflicting_evidence_escalate(self):
        decision = route_cognition(
            "Synthesize these conflicting evidence sources; the situation is ambiguous and uncertain."
        )
        self.assertEqual(decision.tier, "cloud")

    def test_repeated_qwen_failure_escalates(self):
        decision = route_cognition("Explain this result.", prior_local_failures=2)
        self.assertEqual(decision.tier, "cloud")

    def test_malformed_local_result_escalates(self):
        decision = route_cognition("Continue the analysis.", malformed_local_result=True)
        self.assertEqual(decision.tier, "cloud")

    def test_consequential_complex_case_gets_high_effort(self):
        decision = route_cognition(
            "Investigate this security incident with conflicting evidence and build a multi-step recovery plan."
        )
        self.assertEqual(decision.tier, "cloud")
        self.assertEqual(decision.reasoning_effort, "high")

    def test_authoritative_simple_case_does_not_blindly_escalate(self):
        decision = route_cognition("What is the official procedure for a gas leak?")
        self.assertEqual(decision.tier, "local")
        self.assertTrue(decision.signals["authoritative_retrieval_expected"])

    def test_force_local(self):
        self.assertEqual(route_cognition(
            "Debug this difficult architecture", force="local"
        ).tier, "local")

    def test_force_cloud(self):
        self.assertEqual(route_cognition("hello", force="cloud").tier, "cloud")

    def test_reasoning_effort_selection(self):
        medium = route_cognition(
            "Debug this architecture and reason through the tradeoff."
        )
        high = route_cognition(
            "Investigate this emergency security incident with conflicting evidence, "
            "a root cause analysis, counterfactual reasoning, and a multi-step recovery architecture."
        )
        self.assertEqual(medium.reasoning_effort, "medium")
        self.assertEqual(high.reasoning_effort, "high")


class CloudContextTests(unittest.TestCase):
    def test_secret_redaction(self):
        clean, count = redact_secrets(
            "password=hunter2 GROQ API key: gsk_abcdefghijklmnopqrstuvwxyz123456"
        )
        self.assertGreaterEqual(count, 1)
        self.assertNotIn("hunter2", clean)
        self.assertNotIn("gsk_", clean)

    def test_sensitive_and_local_only_context_excluded(self):
        compiled = compile_cloud_context(
            "Analyze this",
            [
                {"role": "user", "content": "[local-only] private diary entry"},
                {"role": "assistant", "content": "API key: gsk_abcdefghijklmnopqrstuvwxyz123456"},
                {"role": "user", "content": "Relevant ordinary fact"},
            ],
        )
        self.assertNotIn("private diary entry", compiled.prompt)
        self.assertNotIn("gsk_", compiled.prompt)
        self.assertIn("Relevant ordinary fact", compiled.prompt)
        self.assertGreaterEqual(compiled.classifications["local_only"], 1)

    def test_explicit_sensitive_context_is_local_by_default(self):
        compiled = compile_cloud_context(
            "Analyze the architecture",
            [
                {"role": "user", "content": "[sensitive] architecture note with private detail"},
                {"role": "assistant", "content": "Architecture has three tiers."},
            ],
        )
        self.assertNotIn("private detail", compiled.prompt)
        self.assertGreaterEqual(compiled.classifications["sensitive"], 1)

    def test_older_nearby_but_irrelevant_context_is_minimized_out(self):
        compiled = compile_cloud_context(
            "Debug the database race condition",
            [
                {"role": "user", "content": "My unrelated vacation itinerary has a hotel reservation."},
                {"role": "assistant", "content": "The database transaction can deadlock under concurrency."},
                {"role": "user", "content": "Which locking order fixes the database race condition?"},
            ],
        )
        self.assertNotIn("vacation itinerary", compiled.prompt)
        self.assertIn("database", compiled.prompt)

    def test_irrelevant_old_history_is_not_uploaded(self):
        history = [
            {"role": "user", "content": f"irrelevant old item {i}"}
            for i in range(20)
        ]
        compiled = compile_cloud_context("current question", history)
        self.assertNotIn("irrelevant old item 0", compiled.prompt)
        self.assertIn("irrelevant old item 19", compiled.prompt)
        self.assertLessEqual(compiled.included_messages, 8)

    def test_context_reports_redaction_and_fingerprint(self):
        compiled = compile_cloud_context("token: abcdefghijklmnopqrstuvwxyz1234")
        self.assertTrue(compiled.fingerprint)
        self.assertGreaterEqual(compiled.redactions, 1)


class ProposalTests(unittest.TestCase):
    def good(self):
        return {
            "response": "Answer",
            "tool": None,
            "arguments_json": "{}",
            "evidence_requests": [],
            "assumptions": [],
            "uncertainties": [],
            "expected_outcomes": [],
            "verification_criteria": [],
            "confidence": 0.8,
        }

    def test_structured_proposal_validates(self):
        proposal = validate_proposal(self.good())
        self.assertIsInstance(proposal, CloudProposal)

    def test_malformed_proposal_rejected(self):
        raw = self.good()
        raw["arguments_json"] = "not json"
        with self.assertRaises(ValueError):
            validate_proposal(raw)

    def test_unauthorized_proposal_is_only_a_proposal(self):
        raw = self.good()
        raw["tool"] = "pc.launch_app"
        raw["arguments_json"] = "{\"name\": \"Example\"}"
        proposal = validate_proposal(raw)
        self.assertEqual(proposal.tool, "pc.launch_app")
        # Validation never executes the proposed tool.
        self.assertEqual(proposal.arguments["name"], "Example")


class ProviderAbstractionTests(unittest.TestCase):
    def test_missing_api_key_keeps_provider_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(GroqProvider().available())

    def test_timeout_outage_rate_limit_and_malformed_fail_gracefully(self):
        for failure in (
            RuntimeError("Groq unavailable."),
            RuntimeError("Groq rate limited."),
            RuntimeError("Cloud reasoning failed safely: timeout"),
            ValueError("malformed structured output"),
        ):
            with self.subTest(failure=str(failure)), \
                 patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True), \
                 patch.object(GroqProvider, "reason", side_effect=failure):
                decision, proposal, metadata = server_cloud_reason(
                    "Debug this difficult root cause and architecture tradeoff.",
                    force="cloud",
                )
                self.assertEqual(decision.tier, "cloud")
                self.assertIsNone(proposal)
                self.assertIn("fallback", metadata)

    def test_mock_alternative_provider_matches_contract(self):
        class MockProvider:
            name = "mock"
            model = "mock/strong-model"
            def available(self, credential=None):
                return True
            def reason(self, compiled, *, effort, credential=None):
                return CloudProposal("ok", None, {}, [], [], [], [], [], 1.0), {
                    "provider": self.name, "model": self.model, "reasoning_effort": effort
                }

        provider = MockProvider()
        compiled = compile_cloud_context("hard problem")
        proposal, meta = provider.reason(compiled, effort="medium")
        self.assertEqual(proposal.response, "ok")
        self.assertEqual(meta["provider"], "mock")

    def test_prepare_records_routing_reason(self):
        result = prepare_cloud_task(
            "Debug this root cause and architecture tradeoff",
            session_id="test",
        )
        self.assertEqual(result["tier"], "cloud")
        self.assertTrue(result["reason"])
        self.assertEqual(result["model"], "openai/gpt-oss-120b")
        self.assertIn(result["reasoning_effort"], {"medium", "high"})


class IOSCredentialSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.settings = (root / "ios/JarvisIOS/SettingsStore.swift").read_text(encoding="utf-8")
        cls.api = (root / "ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")
        cls.view = (root / "ios/JarvisIOS/SettingsView.swift").read_text(encoding="utf-8")

    def test_keychain_save_retrieve_replace_delete_paths_exist(self):
        self.assertIn('KeychainStore.save(value, account: "jarvis.groqAPIKey")', self.settings)
        self.assertIn('KeychainStore.read("jarvis.groqAPIKey")', self.settings)
        self.assertIn('KeychainStore.delete("jarvis.groqAPIKey")', self.settings)

    def test_api_key_is_not_written_to_userdefaults(self):
        self.assertNotIn('defaults.set(groq', self.settings.lower())
        self.assertNotIn('setvalue(groq', self.api.lower())

    def test_global_cloud_disable_stops_normal_cloud_calls(self):
        self.assertIn('if cloudEnabled && cognition.mode != "local"', self.api)
        self.assertNotIn('if cloudEnabled || cognition.mode == "cloud"', self.api)

    def test_disabling_cloud_does_not_delete_key(self):
        enable_line = '@Published var cloudCognitionEnabled'
        self.assertIn(enable_line, self.settings)
        segment = self.settings[self.settings.index(enable_line):self.settings.index(enable_line)+300]
        self.assertNotIn("KeychainStore.delete", segment)

    def test_delete_key_disables_cloud(self):
        delete_start = self.settings.index("func deleteGroqAPIKey")
        segment = self.settings[delete_start:delete_start+450]
        self.assertIn('KeychainStore.delete("jarvis.groqAPIKey")', segment)
        self.assertIn("cloudCognitionEnabled = false", segment)

    def test_test_connection_and_settings_surface_exist(self):
        self.assertIn("func testGroqConnection", self.api)
        self.assertIn('Section("Cloud Intelligence / Groq")', self.view)
        self.assertIn("Test Connection", self.view)
        self.assertIn("Delete Key", self.view)


if __name__ == "__main__":
    unittest.main()
