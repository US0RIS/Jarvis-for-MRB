from __future__ import annotations

import pathlib
import subprocess
import unittest
from unittest.mock import patch

import jarvis_mrb.service as service


class FeatureAcceptanceBackendTests(unittest.TestCase):
    def test_preview_batch_is_pure_and_never_executes_side_effects(self):
        request = service.AcceptancePreviewBatchRequest(
            items=[
                service.AcceptancePreviewItem(
                    id="clock",
                    text="What time is it",
                ),
                service.AcceptancePreviewItem(
                    id="email",
                    text="Send an email to test@example.com saying hello",
                ),
                service.AcceptancePreviewItem(
                    id="novel",
                    text="Reason through this novel architecture problem",
                ),
            ]
        )
        result = service.acceptance_preview_batch(request, authorization=None)
        self.assertTrue(result["ok"])
        self.assertFalse(result["side_effects_executed"])
        rows = {row["id"]: row for row in result["items"]}
        self.assertEqual(rows["clock"]["mode"], "deterministic")
        self.assertEqual(rows["email"]["tool"], "gmail.send")
        self.assertFalse(rows["email"]["side_effects_executed"])
        self.assertEqual(rows["novel"]["mode"], "model_planner")

    def test_synthetic_harness_runs_in_isolated_child_process(self):
        fake = subprocess.CompletedProcess(
            args=["python"], returncode=0, stdout='{"ok": true, "criteria": {}}', stderr=""
        )
        with patch("jarvis_mrb.service.subprocess.run", return_value=fake) as run:
            result = service._run_acceptance_subprocess(
                "jarvis_mrb.world_acceptance_check", compact=True
            )
        self.assertTrue(result["ok"])
        kwargs = run.call_args.kwargs
        self.assertIn("APPDATA", kwargs["env"])
        self.assertIn("--compact", run.call_args.args[0])

    def test_live_service_does_not_import_world_acceptance_in_process_for_endpoint(self):
        source = pathlib.Path(service.__file__).read_text(encoding="utf-8")
        start = source.index('@app.post("/acceptance/synthetic")')
        end = source.index('@app.get("/health")', start)
        endpoint = source[start:end]
        self.assertNotIn("from jarvis_mrb.world_acceptance import", endpoint)
        self.assertNotIn("from jarvis_mrb.agency_acceptance import", endpoint)
        self.assertIn("_run_acceptance_subprocess", endpoint)


class FeatureAcceptanceIOSSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.guide = (root / "ios/JarvisIOS/FeatureGuide.swift").read_text(encoding="utf-8")
        cls.api = (root / "ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")

    def test_one_button_acceptance_surface_exists(self):
        self.assertIn("Run Every Feature Test", self.guide)
        self.assertIn("FullFeatureAcceptanceView", self.guide)
        self.assertIn("Copy Full Report", self.guide)

    def test_full_runner_uses_dry_run_routes_not_send_command(self):
        start = self.guide.index("private struct FullFeatureAcceptanceView")
        runner = self.guide[start:]
        self.assertIn("previewRoute(for:", runner)
        self.assertIn("acceptancePreviewBatch", runner)
        self.assertIn("syntheticAcceptance", runner)
        self.assertNotIn("appModel.sendCommand(feature.examplePrompt)", runner)

    def test_api_client_has_acceptance_methods(self):
        self.assertIn("func acceptancePreviewBatch", self.api)
        self.assertIn("func syntheticAcceptance", self.api)

    def test_negative_control_canaries_are_present(self):
        self.assertIn("Impossible iPhone route expectation", self.guide)
        self.assertIn("Impossible backend route expectation", self.guide)
        self.assertIn("Deliberately unreachable endpoint", self.guide)
        self.assertIn("Nonexistent Groq model rejection", self.guide)
        self.assertIn("__negative_control_pack_\\(UUID().uuidString)__", self.guide)
        self.assertIn("__negative_control_backend_family_\\(UUID().uuidString)__", self.guide)
        self.assertIn("127.0.0.1:1/__jarvis_negative_control__", self.guide)
        self.assertIn("jarvis-negative-control-\\(UUID().uuidString.lowercased())", self.guide)

    def test_negative_controls_invert_success_semantics(self):
        self.assertIn("actualPack == impossiblePack ? .fail : .expectedFail", self.guide)
        self.assertIn("row.family == impossibleFamily ? .fail : .expectedFail", self.guide)
        self.assertIn("state: unexpectedlyHealthy ? .fail : .expectedFail", self.guide)
        self.assertIn("state: wronglyAccepted ? .fail : .expectedFail", self.guide)
        self.assertIn('case expectedFail = "EXPECTED FAIL"', self.guide)


if __name__ == "__main__":
    unittest.main()
