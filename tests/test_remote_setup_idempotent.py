import unittest
from unittest.mock import patch

from jarvis_mrb.remote_setup import configure_remote_access
from jarvis_mrb.server_config import ServerConfig


class RemoteSetupTests(unittest.TestCase):
    def test_reuses_existing_token(self):
        existing = ServerConfig(bind_host="127.0.0.1", port=9001, api_token="prior-token")
        with patch("jarvis_mrb.remote_setup.load_server_config", return_value=existing), \
             patch("jarvis_mrb.remote_setup.save_server_config") as save, \
             patch("jarvis_mrb.remote_setup.secrets.token_urlsafe") as generate:
            configured, rotated = configure_remote_access()
        self.assertFalse(rotated)
        self.assertEqual(configured.api_token, "prior-token")
        self.assertEqual(configured.port, 9001)
        self.assertEqual(configured.bind_host, "0.0.0.0")
        generate.assert_not_called()
        save.assert_called_once_with(configured)

    def test_rotates_only_on_request_or_missing_token(self):
        for existing, rotate in [
            (ServerConfig(api_token="prior-token"), True),
            (ServerConfig(), False),
        ]:
            with self.subTest(existing=existing, rotate=rotate), \
                 patch("jarvis_mrb.remote_setup.load_server_config", return_value=existing), \
                 patch("jarvis_mrb.remote_setup.save_server_config"), \
                 patch("jarvis_mrb.remote_setup.secrets.token_urlsafe", return_value="new-token"):
                configured, rotated = configure_remote_access(rotate=rotate)
                self.assertTrue(rotated)
                self.assertEqual(configured.api_token, "new-token")


if __name__ == "__main__":
    unittest.main()
