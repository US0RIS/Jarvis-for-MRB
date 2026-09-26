from __future__ import annotations

import unittest

from jarvis_mrb.cognitive_benchmark import CASES, evaluate


class CognitiveRoutingBenchmarkTests(unittest.TestCase):
    def test_representative_routing_matrix(self):
        categories = {case.category for case in CASES}
        required = {
            "deterministic", "ordinary conversation", "simple reasoning",
            "difficult reasoning", "coding/debugging", "ambiguous situation",
            "Reality Graph synthesis", "World Armor", "investigation",
            "privacy-sensitive", "consequential", "emergency-authoritative",
        }
        self.assertTrue(required.issubset(categories))
        result = evaluate()
        failures = [row for row in result["rows"] if not row["matched"]]
        self.assertEqual(failures, [], failures)


if __name__ == "__main__":
    unittest.main()
