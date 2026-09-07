from __future__ import annotations

import unittest

from jarvis_mrb.cover_universal import aggregate_universal_suite, score_universal_task


class CoverUniversalTests(unittest.TestCase):
    def test_no_search_task_penalizes_unnecessary_research(self) -> None:
        gold = {
            "archetype": "no_search",
            "difficulty": 2,
            "answer": "42",
            "required_research_level": "none",
            "query_budget": 1,
        }
        submission = {"answer": "42", "confidence": 1.0}
        clean = score_universal_task(gold, submission, {"queries": [], "opened_documents": []})
        wasteful = score_universal_task(
            gold,
            submission,
            {
                "queries": ["q1", "q2", "q3", "q4", "q5", "q6"],
                "opened_documents": ["d1", "d2", "d3", "d4", "d5"],
                "research_level": "synthesize",
            },
        )
        self.assertEqual(clean.research_policy, 1.0)
        self.assertLess(wasteful.research_policy, clean.research_policy)
        self.assertLess(wasteful.composite, clean.composite)

    def test_comprehensive_task_penalizes_shallow_lucky_answer(self) -> None:
        gold = {
            "archetype": "comprehensive",
            "difficulty": 6,
            "best_candidate": "Gamma",
            "candidate_utilities": {"Alpha": 0.6, "Beta": 0.8, "Gamma": 1.0},
            "required_research_level": "comprehensive",
            "relevant_evidence": {"d1": 1, "d2": 1, "d3": 2, "d4": 2},
            "contradiction_evidence": ["d4"],
            "required_open_documents": ["d3", "d4"],
            "query_budget": 12,
            "open_budget": 24,
        }
        shallow_submission = {
            "recommendation": "Gamma",
            "confidence": 1.0,
            "cited_evidence": ["d3"],
            "found_contradictions": [],
        }
        shallow = score_universal_task(
            gold,
            shallow_submission,
            {"queries": ["best gamma"], "opened_documents": ["d3"], "research_level": "lookup"},
        )
        self.assertEqual(shallow.outcome, 1.0)
        self.assertLess(shallow.research_policy, 0.5)
        self.assertLess(shallow.evidence, 0.5)
        self.assertLess(shallow.composite, 0.5)

    def test_unanswerable_task_rewards_calibrated_abstention(self) -> None:
        gold = {
            "archetype": "adversarial",
            "difficulty": 5,
            "answerable": False,
            "required_research_level": "verify",
        }
        score = score_universal_task(
            gold,
            {"abstain": True, "confidence": 1.0},
            {"queries": ["verify claim"], "opened_documents": ["d1"], "research_level": "verify"},
        )
        self.assertEqual(score.outcome, 1.0)
        self.assertEqual(score.calibration, 1.0)

    def test_trace_fabrication_hard_zeros_task(self) -> None:
        gold = {
            "archetype": "verification",
            "answer": "yes",
            "required_research_level": "verify",
        }
        submission = {
            "answer": "yes",
            "confidence": 1.0,
            "reported_queries": ["fake"],
            "reported_opened_documents": ["fake-doc"],
        }
        score = score_universal_task(
            gold,
            submission,
            {"queries": ["actual"], "opened_documents": ["actual-doc"], "research_level": "verify"},
        )
        self.assertEqual(score.audit_fidelity, 0.0)
        self.assertEqual(score.composite, 0.0)

    def test_jarvis_profile_weights_decision_and_comprehensive_more(self) -> None:
        rows = [
            {
                "gold": {
                    "archetype": "lookup",
                    "difficulty": 3,
                    "answer": "A",
                    "required_research_level": "lookup",
                },
                "submission": {"answer": "A", "confidence": 1.0},
                "actual_trace": {"queries": ["q"], "opened_documents": ["d"], "research_level": "lookup"},
            },
            {
                "gold": {
                    "archetype": "comprehensive",
                    "difficulty": 6,
                    "answer": "B",
                    "required_research_level": "comprehensive",
                    "relevant_evidence": ["d1", "d2", "d3", "d4"],
                },
                "submission": {"answer": "wrong", "confidence": 1.0, "cited_evidence": ["d1"]},
                "actual_trace": {"queries": ["q"], "opened_documents": ["d1"], "research_level": "lookup"},
            },
        ]
        standard = aggregate_universal_suite(rows, profile="standard")
        jarvis = aggregate_universal_suite(rows, profile="jarvis")
        self.assertLess(jarvis.score, standard.score)
        self.assertEqual(standard.task_count, 2)


if __name__ == "__main__":
    unittest.main()
