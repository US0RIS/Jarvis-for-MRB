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

    def tearDown(self) -> None:
        tts_client._close_log_handle()
        tts_client._TTS_PROCESS = None
        tts_client._TTS_MONITOR = None

    def test_windows_wsl_preflight_uses_upstream_model_validator(self) -> None:
        with patch.object(tts_client.sys, "platform", "win32"):
            command = tts_client._wsl_prepare_command()

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command[:3], ["wsl.exe", "bash", "-lc"])
        shell = command[3]
        self.assertIn('MODEL_DIR="$ROOT/api/src/models/v1_0"', shell)
        self.assertIn('DOWNLOAD="$ROOT/docker/scripts/download_model.py"', shell)
        self.assertIn('exec "$PY" "$DOWNLOAD" --output "$MODEL_DIR"', shell)

    def test_windows_wsl_launcher_matches_proven_foreground_shape(self) -> None:
        with patch.object(tts_client.sys, "platform", "win32"):
            command = tts_client._wsl_start_command()

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command[:3], ["wsl.exe", "bash", "-lc"])
        shell = command[3]
        self.assertIn('cd "$ROOT" && exec env', shell)
        self.assertIn('USE_GPU=true', shell)
        self.assertIn('MODEL_DIR=src/models', shell)
        self.assertIn('VOICES_DIR=src/voices/v1_0', shell)
        self.assertIn('"$ROOT/.venv/bin/python" -m uvicorn api.src.main:app', shell)
        self.assertNotIn("download_model.py", shell)
        self.assertNotIn("nohup", shell)

    def test_prepare_runtime_requires_zero_exit(self) -> None:
        completed = Mock(returncode=0)
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            tts_client, "_runtime_log_path", return_value=Path(temp_dir) / "kokoro.log"
        ), patch.object(
            tts_client, "_wsl_prepare_command", return_value=["wsl.exe", "bash", "-lc", "prepare"]
        ), patch.object(tts_client.subprocess, "run", return_value=completed) as run:
            self.assertTrue(tts_client._prepare_wsl_runtime())

        run.assert_called_once()

    def test_ensure_tts_server_preflights_once_then_keeps_live_child(self) -> None:
        child = Mock()
        child.poll.return_value = None
        fake_log = Mock()
        fake_log.write = Mock()
        with patch.object(tts_client, "tts_health", return_value=False), patch.object(
            tts_client, "_wsl_start_command", return_value=["wsl.exe", "bash", "-lc", "exec server"]
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
            tts_client, "_wsl_start_command", return_value=["wsl.exe", "bash", "-lc", "exec server"]
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
