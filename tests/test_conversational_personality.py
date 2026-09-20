from __future__ import annotations

import ast
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


class ConversationalVoiceTests(unittest.TestCase):
    def test_shared_personality_encourages_reasoned_opinions_not_generic_agreement(self) -> None:
        persona = (_ROOT / "jarvis_mrb/personality.py").read_text(encoding="utf-8")
        for principle in (
            "HAVE A POINT OF VIEW",
            "what you'd choose",
            "change your mind",
            "subjective judgments",
            '"Sir" is an occasional form of address',
            "CONVERSATION IS NOT A PRESS RELEASE",
            "do not confuse subjective judgments with established facts",
        ):
            with self.subTest(principle=principle):
                self.assertIn(principle, persona)

    def test_ordinary_and_streaming_planners_share_personality(self) -> None:
        agent = (_ROOT / "jarvis_mrb/agent.py").read_text(encoding="utf-8")
        stream = (_ROOT / "jarvis_mrb/streaming_agent.py").read_text(encoding="utf-8")
        self.assertIn("system = f\"\"\"{full_personality_context()}", agent)
        self.assertIn("return f\"\"\"{full_personality_context()}", stream)
        self.assertIn("with a discernible point of view", agent)
        self.assertIn("have an actual opinion when asked", stream)

    def test_no_compulsory_sir_or_uncapitalizing_streamed_sentences(self) -> None:
        agent = (_ROOT / "jarvis_mrb/agent.py").read_text(encoding="utf-8")
        stream = (_ROOT / "jarvis_mrb/streaming_agent.py").read_text(encoding="utf-8")
        tree = ast.parse(agent)
        respectful = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_respectful"
        )
        self.assertEqual(len(respectful.body), 2)  # docstring + return
        self.assertIsInstance(respectful.body[-1], ast.Return)
        self.assertIsInstance(respectful.body[-1].value, ast.Name)
        self.assertEqual(respectful.body[-1].value.id, "reply")
        self.assertNotIn('yield "Sir, "', stream)
        self.assertEqual(stream.count("_lower_first_alpha("), 1)
        self.assertIn("yield remainder", stream)
        self.assertIn("yield chunk", stream)

    def test_existing_ideas_get_opinions_not_unrequested_global_research(self) -> None:
        from jarvis_mrb.streaming_agent import _requires_audited_web

        local_opinion_prompts = (
            "Which of these ideas would you recommend?",
            "Compare this design with that plan",
            "Which is the best option from the options we discussed?",
            "Recommend an approach for this project",
        )
        for prompt in local_opinion_prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(_requires_audited_web(prompt))
        public_discovery_prompts = (
            "Recommend the best laptop available now",
            "Compare all available cameras for travel",
            "Search online for alternatives to this idea",
            "Recommend new options for this project",
        )
        for prompt in public_discovery_prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(_requires_audited_web(prompt))

    def test_guarded_actions_are_unaffected_by_personality(self) -> None:
        agent = (_ROOT / "jarvis_mrb/agent.py").read_text(encoding="utf-8")
        stream = (_ROOT / "jarvis_mrb/streaming_agent.py").read_text(encoding="utf-8")
        self.assertIn("decision = decide(tool)", agent)
        self.assertIn("decision.needs_confirmation", agent)
        self.assertIn("execute_tool(tool_name, safe_args)", stream)
        self.assertIn("fast = _fast_path(stripped)", stream)
        self.assertIn('"options": {"temperature": 0.2}', stream)
        self.assertIn('"options": {"temperature": 0.45}', stream)


if __name__ == "__main__":
    unittest.main()
