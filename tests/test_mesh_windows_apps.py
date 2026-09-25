from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch, Mock
import os

from jarvis_mrb import mesh_windows_apps as apps
from jarvis_mrb import reality_mesh as mesh


class WindowsExactAppTests(TestCase):
    def setUp(self):
        self.previous = apps._LAST_CALL
        self.addCleanup(setattr, apps, "_LAST_CALL", self.previous)
        apps._LAST_CALL = 0.0

    def test_opt_in_is_independent_of_windows_screen(self):
        with patch.object(apps.platform, "system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_APP_ENABLED": "0",
                                     "JARVIS_MESH_WINDOWS_SCREEN_ENABLED": "1"}):
            self.assertFalse(apps.enabled())
            with self.assertRaises(apps.WindowsAppUnavailable):
                apps.launch_exact("Notepad")
        with patch.object(apps.platform, "system", return_value="Linux"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_APP_ENABLED": "1"}):
            self.assertFalse(apps.enabled())

    def test_exact_allowlist_even_when_opted_in_and_no_shell(self):
        with patch.object(apps.platform, "system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_APP_ENABLED": "1"}):
            for name in ["Terminal", "powershell.exe", "cmd.exe", "Notepad && whoami",
                         "..\\Windows\\System32\\cmd.exe", "https://example.org"]:
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        apps.launch_exact(name)
            with patch("jarvis_mrb.permissions.decide", return_value=Mock(
                allowed=True, needs_confirmation=True
            )), patch.object(apps, "_seen", return_value=True), \
                 patch.object(apps.subprocess, "Popen", return_value=Mock()) as spawn:
                receipt = apps.launch_exact("Notepad")
                self.assertEqual(receipt["node_id"], "windows")
                self.assertEqual(receipt["app_name"], "Notepad")
                self.assertTrue(receipt["process_observed"])
                self.assertEqual(receipt["status"], "launch_accepted_process_observed")
                args, kwargs = spawn.call_args
                self.assertEqual(args[0], ["notepad.exe"])
                self.assertIs(kwargs["shell"], False)
                self.assertFalse(any(x in args[0] for x in ["cmd.exe", "powershell.exe"]))
                with self.assertRaises(apps.WindowsAppUnavailable):
                    apps.launch_exact("Notepad")  # rate-limited, no second spawn
                spawn.assert_called_once()

    def test_policy_denial_vetoes_launch_and_unverified_is_not_proof(self):
        with patch.object(apps.platform, "system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_APP_ENABLED": "1"}):
            with patch("jarvis_mrb.permissions.decide", return_value=Mock(allowed=False)), \
                 patch.object(apps.subprocess, "Popen") as spawn:
                with self.assertRaises(apps.WindowsAppUnavailable):
                    apps.launch_exact("Paint")
                spawn.assert_not_called()
            with patch("jarvis_mrb.permissions.decide", return_value=Mock(allowed=True)), \
                 patch.object(apps.subprocess, "Popen", return_value=Mock()), \
                 patch.object(apps, "_seen", return_value=False):
                receipt = apps.launch_exact("Paint")
                self.assertFalse(receipt["process_observed"])
                self.assertEqual(receipt["status"], "launch_accepted_process_unverified")

    def test_mesh_coordinator_cannot_expand_windows_apps(self):
        with self.assertRaises(ValueError):
            mesh.launch_exact_windows_app("Terminal")
        with patch.object(apps.platform, "system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_APP_ENABLED": "1"}), \
             patch("jarvis_mrb.permissions.decide", return_value=Mock(allowed=True)), \
             patch.object(apps.subprocess, "Popen", return_value=Mock()), \
             patch.object(apps, "_seen", return_value=False):
            self.assertEqual(
                mesh.launch_exact_windows_app("Calculator")["node_id"], "windows"
            )
        with patch.object(apps.platform, "system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_APP_ENABLED": "0"}):
            with self.assertRaises(mesh.NodeUnavailable):
                mesh.launch_exact_windows_app("Notepad")


if __name__ == "__main__":
    import unittest
    unittest.main()
