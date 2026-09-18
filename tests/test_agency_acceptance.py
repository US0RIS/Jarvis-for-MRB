from __future__ import annotations

import unittest

from jarvis_mrb.agency_acceptance import run_synthetic_acceptance


class AgencyAcceptanceTests(unittest.TestCase):
    def test_synthetic_preflight_restores_all_global_storage_bindings(self) -> None:
        import jarvis_mrb.agency_attention as agency_attention
        import jarvis_mrb.agency_capability as agency_capability
        import jarvis_mrb.agency_plan as agency_plan
        import jarvis_mrb.agency_runtime as agency_runtime
        import jarvis_mrb.custom_tools as custom_tools
        import jarvis_mrb.desired_state as desired_state
        import jarvis_mrb.permissions as permissions
        import jarvis_mrb.world_model as world_model
        import jarvis_mrb.world_verification as world_verification

        before = {
            "world_app": world_model.APP_DIR,
            "world_db": world_model.DB_PATH,
            "desired_db": desired_state.DB_PATH,
            "plan_db": agency_plan.DB_PATH,
            "runtime_db": agency_runtime.DB_PATH,
            "attention_db": agency_attention.DB_PATH,
            "capability_db": agency_capability.DB_PATH,
            "verification_db": world_verification.DB_PATH,
            "permission_app": permissions.APP_DIR,
            "permission_path": permissions.POLICY_PATH,
            "custom_tools_app": custom_tools.APP_DIR,
            "custom_tools_dir": custom_tools.TOOLS_DIR,
        }

        run_synthetic_acceptance()

        after = {
            "world_app": world_model.APP_DIR,
            "world_db": world_model.DB_PATH,
            "desired_db": desired_state.DB_PATH,
            "plan_db": agency_plan.DB_PATH,
            "runtime_db": agency_runtime.DB_PATH,
            "attention_db": agency_attention.DB_PATH,
            "capability_db": agency_capability.DB_PATH,
            "verification_db": world_verification.DB_PATH,
            "permission_app": permissions.APP_DIR,
            "permission_path": permissions.POLICY_PATH,
            "custom_tools_app": custom_tools.APP_DIR,
            "custom_tools_dir": custom_tools.TOOLS_DIR,
        }
        self.assertEqual(after, before)

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
