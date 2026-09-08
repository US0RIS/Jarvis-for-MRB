from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import jarvis_mrb.tts_client as tts_client


class TTSAutoStartModelRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        tts_client._TTS_PROCESS = None
        tts_client._TTS_MONITOR = None

    def tearDown(self) -> None:
        tts_client._TTS_PROCESS = None
        tts_client._TTS_MONITOR = None

    def test_windows_wsl_launcher_repairs_missing_model_before_uvicorn(self) -> None:
        with patch.object(tts_client.sys, "platform", "win32"):
            command = tts_client._wsl_start_command()

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command[:3], ["wsl.exe", "bash", "-lc"])
        shell = command[3]
        self.assertIn('MODEL="$MODEL_DIR/kokoro-v1_0.pth"', shell)
        self.assertIn('CONFIG="$MODEL_DIR/config.json"', shell)
        self.assertIn('DOWNLOAD="$ROOT/docker/scripts/download_model.py"', shell)
        self.assertIn('"$PY" "$DOWNLOAD" --output "$MODEL_DIR"', shell)
        self.assertIn('exec env', shell)
        self.assertIn('"$PY" -m uvicorn api.src.main:app', shell)
        self.assertNotIn('nohup env', shell)
        self.assertLess(
            shell.index('"$PY" "$DOWNLOAD" --output "$MODEL_DIR"'),
            shell.index('"$PY" -m uvicorn api.src.main:app'),
        )

    def test_ensure_tts_server_keeps_one_live_wsl_child_while_warming(self) -> None:
        child = Mock()
        child.poll.return_value = None
        with patch.object(tts_client, "tts_health", return_value=False), patch.object(
            tts_client, "_wsl_start_command", return_value=["wsl.exe", "bash", "-lc", "exec server"]
        ), patch.object(tts_client.subprocess, "Popen", return_value=child) as popen, patch.object(
            tts_client, "_ensure_monitor"
        ) as ensure_monitor:
            self.assertFalse(tts_client.ensure_tts_server(wait_seconds=0.0))
            self.assertFalse(tts_client.ensure_tts_server(wait_seconds=0.0))

        self.assertIs(tts_client._TTS_PROCESS, child)
        popen.assert_called_once()
        self.assertEqual(ensure_monitor.call_count, 2)

    def test_ensure_tts_server_restarts_exited_wsl_child(self) -> None:
        dead = Mock()
        dead.poll.return_value = 1
        fresh = Mock()
        fresh.poll.return_value = None
        tts_client._TTS_PROCESS = dead

        with patch.object(tts_client, "tts_health", return_value=False), patch.object(
            tts_client, "_wsl_start_command", return_value=["wsl.exe", "bash", "-lc", "exec server"]
        ), patch.object(tts_client.subprocess, "Popen", return_value=fresh) as popen, patch.object(
            tts_client, "_ensure_monitor"
        ) as ensure_monitor:
            self.assertFalse(tts_client.ensure_tts_server(wait_seconds=0.0))

        self.assertIs(tts_client._TTS_PROCESS, fresh)
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
