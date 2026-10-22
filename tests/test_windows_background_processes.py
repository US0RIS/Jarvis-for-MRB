"""Background probes must never flash a new console over the Windows desktop.

These calls execute from the frozen --windowed Horus backend. Regression
tests verify the Windows creation flag is explicitly supplied, rather than
depending on whether the invoking terminal happens to exist.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock

import jarvis_mrb.resource_monitor as resource_monitor
import jarvis_mrb.sandbox as sandbox
import jarvis_mrb.agency_release as agency_release


WINDOWS_HIDE_CONSOLE = 0x08000000


class BackgroundConsoleTests(TestCase):
    def test_nvidia_gpu_monitor_disables_console_windows(self):
        response = SimpleNamespace(
            returncode=0, stdout="GeForce RTX, 300, 16384, 15, 50\n",
        )
        with mock.patch.object(resource_monitor.shutil, "which",
                               return_value="C:\\Windows\\System32\\nvidia-smi.exe"), \
             mock.patch.object(resource_monitor.subprocess, "CREATE_NO_WINDOW",
                               WINDOWS_HIDE_CONSOLE, create=True), \
             mock.patch.object(resource_monitor.subprocess, "run",
                               return_value=response) as run:
            actual = resource_monitor._gpu_sample()
        self.assertEqual(actual["memory_used_mib"], 300)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["creationflags"], WINDOWS_HIDE_CONSOLE)

    def test_docker_health_probe_disables_console_windows(self):
        response = SimpleNamespace(returncode=0, stdout="27.0.0")
        with mock.patch.object(sandbox.shutil, "which", return_value="docker.exe"), \
             mock.patch.object(sandbox.subprocess, "CREATE_NO_WINDOW",
                               WINDOWS_HIDE_CONSOLE, create=True), \
             mock.patch.object(sandbox.subprocess, "run",
                               return_value=response) as run:
            self.assertTrue(sandbox.docker_available())
        self.assertEqual(run.call_args.kwargs["creationflags"], WINDOWS_HIDE_CONSOLE)

    def test_git_deployment_probe_disables_console_windows(self):
        response = SimpleNamespace(returncode=0, stdout="a" * 40)
        with mock.patch.object(agency_release.subprocess, "CREATE_NO_WINDOW",
                               WINDOWS_HIDE_CONSOLE, create=True), \
             mock.patch.object(agency_release.subprocess, "run",
                               return_value=response) as run:
            self.assertEqual(agency_release._git_head_sha(Path(".")), "a" * 40)
        self.assertEqual(run.call_args.kwargs["creationflags"], WINDOWS_HIDE_CONSOLE)


if __name__ == "__main__":
    import unittest
    unittest.main()
