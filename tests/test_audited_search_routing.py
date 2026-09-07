from __future__ import annotations

import unittest

from jarvis_mrb.streaming_agent import _requires_audited_web, _tool_is_justified


class AuditedSearchRoutingTests(unittest.TestCase):
    def test_selection_risk_bypasses_planner(self) -> None:
        self.assertTrue(_requires_audited_web("What is the best watch under $7,500?"))
        self.assertTrue(_requires_audited_web("Recommend a compact SUV for my parents"))
        self.assertTrue(_requires_audited_web("Compare all available alternatives and rank them"))
        self.assertTrue(_requires_audited_web("Show me the latest research receipt"))

    def test_private_or_stable_reasoning_is_not_forced_to_public_web(self) -> None:
        self.assertFalse(_requires_audited_web("What is the best way to solve a quadratic equation?"))
        self.assertFalse(_requires_audited_web("Explain photosynthesis"))
        self.assertFalse(_requires_audited_web("Compare these two drafts from my email"))
        self.assertFalse(_requires_audited_web("Recommend what I should do based on my calendar"))

    def test_explicit_web_request_can_override_private_context_exclusion(self) -> None:
        self.assertTrue(_requires_audited_web("Search the web and compare these two drafts from my email"))

    def test_guard_allows_audited_web_intent(self) -> None:
        self.assertTrue(_tool_is_justified("web.search", "Recommend the best option for me"))
        self.assertTrue(_tool_is_justified("web.search", "Show me the research receipt"))


if __name__ == "__main__":
    unittest.main()
