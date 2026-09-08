from __future__ import annotations

import unittest
from unittest.mock import patch

import jarvis_mrb.tts_client as tts_client


class TTSAutoStartModelRepairTests(unittest.TestCase):
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
        self.assertIn('"$PY" -m uvicorn api.src.main:app', shell)
        self.assertLess(
            shell.index('"$PY" "$DOWNLOAD" --output "$MODEL_DIR"'),
            shell.index('"$PY" -m uvicorn api.src.main:app'),
        )


if __name__ == "__main__":
    unittest.main()
