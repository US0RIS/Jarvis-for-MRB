from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_mrb.deterministic_dispatch import (
    note_model_planner,
    note_routed,
    routing_status,
)
from jarvis_mrb.workflow_engine import _deterministic_read_workflow, plan_workflow
from jarvis_mrb.tools.web import refine_query
from jarvis_mrb.search_integrity import _plan_queries, REQUIRED_FAMILIES

ROOT = Path(__file__).resolve().parents[1]


class ModelFreeSubsystemTests(unittest.TestCase):
    def test_two_source_reads_do_not_contact_ollama(self):
        with patch("jarvis_mrb.workflow_engine.httpx.Client", side_effect=AssertionError("Qwen called")):
            plan = plan_workflow("check my calendar and email")
        self.assertEqual([node["tool"] for node in plan["nodes"]],
                         ["calendar.list", "gmail.query"])
        self.assertTrue(all(not node["depends_on"] for node in plan["nodes"]))
        with patch("jarvis_mrb.workflow_engine.httpx.Client", side_effect=AssertionError("Qwen called")):
            plan = plan_workflow("check my unread emails and pc resources")
        self.assertEqual([node["tool"] for node in plan["nodes"]],
                         ["gmail.query", "system.resources"])

    def test_multistep_writes_and_ambiguous_targets_never_auto_plan(self):
        for text in (
            "send an email and delete the document",
            "check email and send it",
            "look up the contract and sign it",
            "check my calendar and calendar",
            "check my bank and my email",
        ):
            self.assertIsNone(_deterministic_read_workflow(text), text)

    def test_default_web_query_refinement_is_model_free_and_lossless(self):
        with (
            patch.dict(os.environ, {"JARVIS_WEB_QUERY_USE_QWEN": "0"}),
            patch("jarvis_mrb.tools.web.httpx.Client", side_effect=AssertionError("Qwen called")),
        ):
            self.assertEqual(
                refine_query("Can you find information about Project Apollo"),
                "information about Project Apollo",
            )
            self.assertEqual(
                refine_query("what's the latest on OpenAI"),
                "OpenAI latest",
            )
            complex_query = ("Find information about the precise contractual status "
                             "of Project Apollo in London, not the NASA program, "
                             "with regulatory context for September 2026")
            self.assertEqual(refine_query(complex_query), complex_query)

    def test_default_audited_research_plan_has_all_eight_families_no_model(self):
        with (
            patch.dict(os.environ, {"JARVIS_RESEARCH_PLAN_USE_QWEN": "0"}),
            patch("jarvis_mrb.search_integrity.httpx.Client", side_effect=AssertionError("Qwen called")),
        ):
            specs = _plan_queries("Compare all realistic options in Melbourne")
        self.assertEqual([item.family for item in specs], list(REQUIRED_FAMILIES))
        self.assertTrue(all("Melbourne" in item.query for item in specs))

    def test_briefing_and_journal_have_default_hardcoded_paths(self):
        briefing = (ROOT / "jarvis_mrb/briefing.py").read_text(encoding="utf-8")
        journal = (ROOT / "jarvis_mrb/daily_journal.py").read_text(encoding="utf-8")
        compiler = (ROOT / "jarvis_mrb/agency_goal_compiler.py").read_text(encoding="utf-8")
        self.assertNotIn('/api/chat', briefing)
        self.assertIn("JARVIS_JOURNAL_USE_QWEN", journal)
        self.assertIn("return _deterministic_render(day, source)", journal)
        self.assertLess(compiler.index("candidate = _fallback_contract("),
                        compiler.index("raw = _model_compile(prompt)"))

    def test_route_accounting_contains_no_prompt_content(self):
        before = routing_status()
        note_routed("calendar.day")
        note_model_planner()
        after = routing_status()
        self.assertEqual(after["model_bypass"], before["model_bypass"] + 1)
        self.assertEqual(after["model_planner_attempt"], before["model_planner_attempt"] + 1)
        self.assertNotIn("prompt", after)
        self.assertNotIn("command_text", after)


if __name__ == "__main__":
    unittest.main()
