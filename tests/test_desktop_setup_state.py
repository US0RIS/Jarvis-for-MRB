from __future__ import annotations
import unittest

# Import the standalone implementation without requiring PySide6 on Linux CI.
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "packaging" / "desktop_setup_state.py"
spec = importlib.util.spec_from_file_location("desktop_setup_state", SOURCE)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules["desktop_setup_state"] = module
spec.loader.exec_module(module)


class SetupStateTests(unittest.TestCase):
    def test_stopped_backend_is_never_reported_as_phone_ready(self):
        info = {"online": False, "health": {}, "phone": {"recent_authenticated_app_checkin": True}}
        status = module.derive_setup_state(
            info, {"provider": "openai", "model": "gpt-test", "key_configured": True},
            "0.0.0.0", True, False)
        self.assertEqual(status.checks, (False, True, False, False, False))
        self.assertEqual(status.next_step, 0)

    def test_saved_lan_config_does_not_prove_server_restarted(self):
        info = {"online": True, "health": {"bind": "127.0.0.1"},
                "phone": {"recent_authenticated_app_checkin": True}}
        status = module.derive_setup_state(
            info, {"provider": "anthropic", "model": "claude-model", "key_configured": True},
            "0.0.0.0", True, False)
        self.assertTrue(status.engine_online)
        self.assertFalse(status.lan_ready)
        self.assertFalse(status.phone_recent)

    def test_hosted_missing_key_is_not_ready(self):
        status = module.derive_setup_state(
            {"online": True, "health": {"bind": "0.0.0.0"}},
            {"provider": "openai", "model": "gpt-test", "key_configured": False},
            "0.0.0.0", True, False)
        self.assertFalse(status.provider_configured)

    def test_phone_checkin_not_equal_airpods_verified(self):
        info = {"online": True, "health": {"bind": "0.0.0.0"},
                "phone": {"recent_authenticated_app_checkin": True,
                          "airpods_verified": False}}
        result = module.derive_setup_state(
            info, {"provider": "anthropic", "model": "test", "key_configured": True},
            "0.0.0.0", True, False)
        self.assertTrue(result.phone_recent)
        self.assertFalse(result.audio_user_confirmed)
        self.assertEqual(result.completed, 4)
        self.assertEqual(result.next_step, 4)

    def test_manual_audio_confirmation_is_not_inferred_from_backend(self):
        status = module.derive_setup_state(
            {"online": False}, {"provider": "ollama", "model": "qwen3:8b"},
            "127.0.0.1", False, True)
        self.assertTrue(status.audio_user_confirmed)
        self.assertFalse(status.phone_recent)
        self.assertEqual(status.completed, 2)


if __name__ == "__main__":
    unittest.main()
