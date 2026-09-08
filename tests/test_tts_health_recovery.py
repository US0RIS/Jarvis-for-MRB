from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import jarvis_mrb.tts_client as tts_client


class TTSHealthRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        tts_client._TTS_LAST_HEALTHY = None

    def test_healthy_transition_records_runtime_success_once(self) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": "healthy"}

        with patch("jarvis_mrb.tts_client.httpx.get", return_value=response), patch(
            "jarvis_mrb.runtime_health.record_success"
        ) as record_success:
            self.assertTrue(tts_client.tts_health())
            self.assertTrue(tts_client.tts_health())

        record_success.assert_called_once_with("tts_start")

    def test_recovery_after_unhealthy_probe_records_success(self) -> None:
        bad = Mock()
        bad.status_code = 503
        good = Mock()
        good.status_code = 200
        good.json.return_value = {"backend": {"ready": True}}

        with patch("jarvis_mrb.tts_client.httpx.get", side_effect=[bad, good]), patch(
            "jarvis_mrb.runtime_health.record_success"
        ) as record_success:
            self.assertFalse(tts_client.tts_health())
            self.assertTrue(tts_client.tts_health())

        record_success.assert_called_once_with("tts_start")

    def test_qwen_health_is_not_treated_as_kokoro_recovery(self) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"backend": {"model_id": "Qwen3-TTS", "ready": True}}

        with patch("jarvis_mrb.tts_client.httpx.get", return_value=response), patch(
            "jarvis_mrb.runtime_health.record_success"
        ) as record_success:
            self.assertFalse(tts_client.tts_health())

        record_success.assert_not_called()


if __name__ == "__main__":
    unittest.main()
