"""Phone setup receipt is authenticated, ephemeral and not a Bluetooth claim."""
from __future__ import annotations
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from jarvis_mrb import phone_pairing, service


class PhonePairingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(service.app)
        self.old = phone_pairing._last_checkin
        phone_pairing._last_checkin = None
        self.token = patch.object(service, "API_TOKEN", "integration-secret")
        self.token.start()

    def tearDown(self):
        self.token.stop()
        phone_pairing._last_checkin = self.old

    def test_only_authenticated_app_request_can_set_receipt(self):
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            self.assertEqual(self.client.post("/desktop/phone-checkin", headers=headers).status_code, 401)
        status = self.client.get("/desktop/phone-status",
                                 headers={"Authorization": "Bearer integration-secret"})
        self.assertFalse(status.json()["recent_authenticated_app_checkin"])
        self.assertEqual(self.client.post("/desktop/phone-checkin",
                          headers={"Authorization": "Bearer integration-secret"}).status_code, 200)
        body = self.client.get("/desktop/phone-status",
                   headers={"Authorization": "Bearer integration-secret"}).json()
        self.assertTrue(body["recent_authenticated_app_checkin"])
        self.assertFalse(body["airpods_verified"])
        self.assertNotIn("ip_address", body)
        self.assertNotIn("token", body)

    def test_time_window_and_no_permanent_false_pairing(self):
        phone_pairing.check_in(now=100.0)
        self.assertTrue(phone_pairing.status(now=399.0)["recent_authenticated_app_checkin"])
        self.assertFalse(phone_pairing.status(now=401.0)["recent_authenticated_app_checkin"])

    def test_no_phone_pairing_when_server_has_no_bearer_token(self):
        with patch.object(service, "API_TOKEN", ""):
            self.assertEqual(self.client.post("/desktop/phone-checkin").status_code, 503)
            self.assertEqual(self.client.get("/desktop/phone-status").status_code, 503)


if __name__ == "__main__":
    unittest.main()
