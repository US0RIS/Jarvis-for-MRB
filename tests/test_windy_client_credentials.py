from __future__ import annotations

import pathlib
import unittest
from unittest.mock import patch

from jarvis_mrb import public_camera_windy as windy
from jarvis_mrb import world_armor_cameras as armor_cameras


class WindyRequestCredentialTests(unittest.TestCase):
    def test_request_key_enables_windy_without_environment_variable(self):
        payload = {
            "webcams": [{
                "webcamId": 42,
                "status": "active",
                "title": "Test webcam",
                "location": {"latitude": 34.1, "longitude": -118.2},
                "images": {"current": {"preview": "https://example.com/frame.jpg"}},
                "urls": {"detail": "https://www.windy.com/webcams/42"},
            }],
            "total": 1,
        }
        with patch.object(windy, "_get", return_value=payload) as provider:
            result = windy.discover_windy_cameras(
                34.1, -118.2, limit=1, api_key="ios-test-secret"
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["cameras"][0]["id"], "windy-42")
        self.assertEqual(provider.call_args.kwargs["api_key"], "ios-test-secret")
        self.assertNotIn("ios-test-secret", repr(result))

    def test_world_armor_threads_request_key_to_windy_provider(self):
        with patch.object(
            armor_cameras, "_require_enabled", return_value=None
        ), patch(
            "jarvis_mrb.public_camera_windy.discover_windy_cameras",
            return_value={"status": "ok", "cameras": [], "reported_total": 0},
        ) as provider:
            armor_cameras.discover_public_cameras_global(
                0.0, 0.0, radius_km=10, limit=5,
                windy_api_key="phone-secret",
            )
        self.assertEqual(provider.call_args.kwargs["api_key"], "phone-secret")


class WindyIOSCredentialSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.settings = (root / "ios/JarvisIOS/SettingsStore.swift").read_text(encoding="utf-8")
        cls.view = (root / "ios/JarvisIOS/SettingsView.swift").read_text(encoding="utf-8")
        cls.api = (root / "ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")

    def test_windy_key_is_keychain_backed(self):
        self.assertIn('account: "jarvis.windyWebcamsAPIKey"', self.settings)
        self.assertIn("func windyAPIKeyForRequest()", self.settings)
        self.assertIn("Worldwide Public Cameras / Windy", self.view)

    def test_camera_requests_use_dedicated_header(self):
        self.assertIn('["X-Jarvis-Windy-Key": windyAPIKey]', self.api)
        self.assertIn("headers: windyRequestHeaders()", self.api)
        self.assertIn("func testWindyConnection(apiKey: String)", self.api)


if __name__ == "__main__":
    unittest.main()
