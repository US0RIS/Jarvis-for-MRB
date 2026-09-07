from __future__ import annotations

import unittest

from jarvis_mrb.search_benchmark import score_cover


class CoverBenchmarkTests(unittest.TestCase):
    def test_complete_auditable_search_scores_one(self) -> None:
        gold = {
            "eligible_candidates": {
                "Alpha": {"utility": 0.7, "required_evidence": ["D1"]},
                "Beta": {"utility": 0.8, "required_evidence": ["D2"]},
                "Gamma": {"utility": 1.0, "required_evidence": ["D3"]},
            },
            "relevant_evidence": ["D1", "D2", "D3", "D4"],
            "contradictions": ["C1"],
            "constraints": {"budget": True, "size": True},
            "best_candidate": "Gamma",
            "query_budget": 8,
        }
        trace = {
            "queries": ["q1", "q2", "q3"],
            "opened_documents": ["D1", "D2", "D3", "D4"],
        }
        submission = {
            "found_candidates": ["Alpha", "Beta", "Gamma"],
            "cited_evidence": ["D1", "D2", "D3", "D4"],
            "found_contradictions": ["C1"],
            "constraint_findings": {"budget": True, "size": True},
            "recommendation": "Gamma",
            "claimed_completeness": 1.0,
            "reported_queries": ["q1", "q2", "q3"],
            "reported_opened_documents": ["D1", "D2", "D3", "D4"],
        }
        score = score_cover(gold, submission, trace)
        self.assertEqual(score.composite, 1.0)

    def test_lucky_answer_does_not_hide_incomplete_search(self) -> None:
        gold = {
            "eligible_candidates": ["Alpha", "Beta", "Gamma", "Delta"],
            "relevant_evidence": ["D1", "D2", "D3", "D4"],
            "contradictions": ["C1", "C2"],
            "constraints": {"budget": True, "size": True, "availability": True},
            "best_candidate": "Gamma",
            "candidate_utilities": {"Alpha": 0.6, "Beta": 0.7, "Gamma": 1.0, "Delta": 0.8},
            "query_budget": 8,
        }
        trace = {"queries": ["q1"], "opened_documents": ["D3"]}
        submission = {
            # It happened to find/recommend the gold best candidate, but did not
            # discover most of the option/evidence universe and overclaims certainty.
            "found_candidates": ["Gamma"],
            "cited_evidence": ["D3"],
            "found_contradictions": [],
            "constraint_findings": {"budget": True},
            "recommendation": "Gamma",
            "claimed_completeness": 1.0,
            "reported_queries": ["q1"],
            "reported_opened_documents": ["D3"],
        }
        score = score_cover(gold, submission, trace)
        self.assertEqual(score.decision_quality, 1.0)
        self.assertEqual(score.candidate_recall, 0.25)
        self.assertLess(score.composite, 0.35)

    def test_fabricated_search_trace_hard_zeros_composite(self) -> None:
        gold = {
            "eligible_candidates": ["Alpha"],
            "relevant_evidence": ["D1"],
            "best_candidate": "Alpha",
        }
        trace = {"queries": ["actual query"], "opened_documents": ["D1"]}
        submission = {
            "found_candidates": ["Alpha"],
            "cited_evidence": ["D1"],
            "recommendation": "Alpha",
            "claimed_completeness": 1.0,
            "reported_queries": ["invented query"],
            "reported_opened_documents": ["invented document"],
        }
        score = score_cover(gold, submission, trace)
        self.assertEqual(score.audit_fidelity, 0.0)
        self.assertEqual(score.composite, 0.0)


if __name__ == "__main__":
    unittest.main()
