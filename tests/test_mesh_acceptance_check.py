from __future__ import annotations

import unittest
from unittest.mock import patch
from jarvis_mrb import mesh_acceptance_check as acceptance
from jarvis_mrb import reality_mesh as mesh


class MeshAcceptanceCheckTests(unittest.TestCase):
    def test_default_never_queries_node_or_captures_screen_and_reports_no_secrets(self):
        with patch.object(mesh, "probe", side_effect=AssertionError("network probe")),
             patch.object(mesh, "begin_screen", side_effect=AssertionError("screen capture")):
            result = acceptance.report()
        self.assertFalse(result["probe_live_nodes_requested"])
        self.assertFalse(result["screen_captured"])
        self.assertFalse(result["screenshots_persisted"])
        self.assertFalse(result["arbitrary_device_execution"])
        self.assertIn("macmini_configured", result)
        self.assertNotIn("node_token", str(result))
        self.assertNotIn("secret", str(result).lower())

    def test_explicit_one_shot_capture_revokes_and_returns_metadata_only(self):
        with patch.object(mesh, "begin_screen", return_value={"status": "active"}) as begin,
             patch.object(mesh, "frame", return_value=(b"image contents", "image/png")),
             patch.object(mesh, "finish_screen", return_value={"status": "closed"}) as stop:
            result = acceptance.report(exercise_screen="macbook")
        begin.assert_called_once_with("macbook", seconds=15)
        stop.assert_called_once_with("macbook")
        self.assertTrue(result["screen_captured"])
        self.assertEqual(result["screen_exercise"]["frame_bytes"], 14)
        self.assertEqual(result["screen_exercise"]["media_type"], "image/png")
        self.assertTrue(result["screen_exercise"]["remote_revoke_confirmed"])
        self.assertNotIn("image contents", str(result))

    def test_fails_closed_on_capture_and_reports_unconfirmed_revoke(self):
        with patch.object(mesh, "begin_screen", side_effect=mesh.NodeUnavailable("unavailable")),
             patch.object(mesh, "finish_screen", side_effect=mesh.NodeUnavailable("offline")):
            result = acceptance.report(exercise_screen="windows")
        self.assertFalse(result["screen_captured"])
        self.assertEqual(result["screen_exercise"]["status"], "unavailable")
        self.assertFalse(result["screen_exercise"]["remote_revoke_confirmed"])
        self.assertIn("15-second", result["screen_exercise"]["safety_note"])

    def test_live_probe_never_returns_private_ip_or_token(self):
        with patch.object(mesh, "probe", return_value={
            "status": "unavailable", "evidence": "node could not be reached",
            "capabilities": {},
        }) as probed:
            result = acceptance.report(probe=True)
        self.assertEqual(probed.call_count, 2)
        self.assertEqual(result["macbook"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
