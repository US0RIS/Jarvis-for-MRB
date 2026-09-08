from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import jarvis_mrb.tts_client as tts_client


class TTSAutoStartModelRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        tts_client._TTS_PROCESS = None
        tts_client._TTS_MONITOR = None
        tts_client._TTS_LOG_HANDLE = None
        tts_client._WSL_HOME = None

    def tearDown(self) -> None:
        tts_client._close_log_handle()
        tts_client._TTS_PROCESS = None
        tts_client._TTS_MONITOR = None
        tts_client._WSL_HOME = None

    def test_wsl_home_uses_direct_printenv_without_shell(self) -> None:
        completed = Mock(returncode=0, stdout="/home/tester\n")
        with patch.object(tts_client.sys, "platform", "win32"), patch.object(
            tts_client.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(tts_client._wsl_home(), "/home/tester")

        self.assertEqual(
            run.call_args.args[0],
            ["wsl.exe", "--exec", "printenv", "HOME"],
        )

    def test_windows_wsl_preflight_uses_direct_upstream_model_validator(self) -> None:
        with patch.object(tts_client, "_wsl_home", return_value="/home/tester"):
            command = tts_client._wsl_prepare_command()

        self.assertEqual(
            command,
            [
                "wsl.exe",
                "--exec",
                "/home/tester/.local/share/jarvis/kokoro-fastapi/.venv/bin/python",
                "/home/tester/.local/share/jarvis/kokoro-fastapi/docker/scripts/download_model.py",
                "--output",
                "/home/tester/.local/share/jarvis/kokoro-fastapi/api/src/models/v1_0",
            ],
        )
        self.assertNotIn("bash", command or [])
        self.assertNotIn("-lc", command or [])

    def test_windows_wsl_launcher_is_direct_argv_not_shell_text(self) -> None:
        with patch.object(tts_client, "_wsl_home", return_value="/home/tester"):
            command = tts_client._wsl_start_command()

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command[:3], ["wsl.exe", "--exec", "env"])
        self.assertIn("USE_GPU=true", command)
        self.assertIn(
            "PYTHONPATH=/home/tester/.local/share/jarvis/kokoro-fastapi:/home/tester/.local/share/jarvis/kokoro-fastapi/api",
            command,
        )
        self.assertIn("MODEL_DIR=src/models", command)
        self.assertIn("VOICES_DIR=src/voices/v1_0", command)
        self.assertIn(
            "WEB_PLAYER_PATH=/home/tester/.local/share/jarvis/kokoro-fastapi/web",
            command,
        )
        self.assertIn(
            "/home/tester/.local/share/jarvis/kokoro-fastapi/.venv/bin/python",
            command,
        )
        self.assertIn("api.src.main:app", command)
        self.assertNotIn("bash", command)
        self.assertNotIn("-lc", command)
        self.assertFalse(any('"' in part or "'" in part for part in command))

    def test_prepare_runtime_requires_zero_exit(self) -> None:
        completed = Mock(returncode=0)
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            tts_client, "_runtime_log_path", return_value=Path(temp_dir) / "kokoro.log"
        ), patch.object(
            tts_client, "_wsl_prepare_command", return_value=["wsl.exe", "--exec", "prepare"]
        ), patch.object(tts_client.subprocess, "run", return_value=completed) as run:
            self.assertTrue(tts_client._prepare_wsl_runtime())

        run.assert_called_once()

    def test_ensure_tts_server_preflights_once_then_keeps_live_child(self) -> None:
        child = Mock()
        child.poll.return_value = None
        fake_log = Mock()
        fake_log.write = Mock()
        with patch.object(tts_client, "tts_health", return_value=False), patch.object(
            tts_client, "_wsl_start_command", return_value=["wsl.exe", "--exec", "server"]
        ), patch.object(tts_client, "_prepare_wsl_runtime", return_value=True) as prepare, patch.object(
            tts_client, "_close_log_handle"
        ), patch.object(tts_client, "_runtime_log_path") as log_path, patch.object(
            tts_client.subprocess, "Popen", return_value=child
        ) as popen, patch.object(tts_client, "_ensure_monitor") as ensure_monitor:
            log_path.return_value.open.return_value = fake_log
            self.assertFalse(tts_client.ensure_tts_server(wait_seconds=0.0))
            self.assertFalse(tts_client.ensure_tts_server(wait_seconds=0.0))

        self.assertIs(tts_client._TTS_PROCESS, child)
        prepare.assert_called_once()
        popen.assert_called_once()
        self.assertEqual(ensure_monitor.call_count, 2)

    def test_ensure_tts_server_restarts_exited_wsl_child(self) -> None:
        dead = Mock()
        dead.poll.return_value = 1
        fresh = Mock()
        fresh.poll.return_value = None
        fake_log = Mock()
        fake_log.write = Mock()
        tts_client._TTS_PROCESS = dead

        with patch.object(tts_client, "tts_health", return_value=False), patch.object(
            tts_client, "_wsl_start_command", return_value=["wsl.exe", "--exec", "server"]
        ), patch.object(tts_client, "_prepare_wsl_runtime", return_value=True) as prepare, patch.object(
            tts_client, "_close_log_handle"
        ), patch.object(tts_client, "_runtime_log_path") as log_path, patch.object(
            tts_client.subprocess, "Popen", return_value=fresh
        ) as popen, patch.object(tts_client, "_ensure_monitor") as ensure_monitor:
            log_path.return_value.open.return_value = fake_log
            self.assertFalse(tts_client.ensure_tts_server(wait_seconds=0.0))

        self.assertIs(tts_client._TTS_PROCESS, fresh)
        prepare.assert_called_once()
        popen.assert_called_once()
        ensure_monitor.assert_called_once_with(fresh)

    def test_monitor_exits_after_health_recovery(self) -> None:
        child = Mock()
        child.poll.return_value = None
        with patch.object(tts_client, "tts_health", side_effect=[False, True]) as health, patch.object(
            tts_client.time, "sleep"
        ):
            tts_client._monitor_tts_child(child, timeout_seconds=5.0)

        self.assertEqual(health.call_count, 2)


if __name__ == "__main__":
    unittest.main()
