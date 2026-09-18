from __future__ import annotations

import unittest

from jarvis_mrb.agency_acceptance import run_synthetic_acceptance


class AgencyAcceptanceTests(unittest.TestCase):
    def test_a1_through_a12_synthetic_preflight(self) -> None:
        result = run_synthetic_acceptance()
        self.assertTrue(result["ok"], result["failed_checks"])
        self.assertFalse(result["release_ready"])
        self.assertTrue(result["real_deployment_required"])
        for gate in [f"A{index}" for index in range(1, 13)]:
            self.assertTrue(
                result["synthetic_gate_results"][gate]["synthetic_passed"],
                f"{gate}: {result['synthetic_gate_results'][gate]}",
            )
        self.assertEqual(result["traces"]["A12"]["final_plan_status"], "completed")
        self.assertEqual(result["traces"]["A12"]["desired_state"], "satisfied")


if __name__ == "__main__":
    unittest.main()
