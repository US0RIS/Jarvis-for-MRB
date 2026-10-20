import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_mrb.callless_core import CalllessError, CalllessStore


class CalllessStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = CalllessStore(Path(self.temp.name) / "callless.sqlite3")
        self.a, self.ta = self.store.register("alice", "Alice", "password-alice-123")
        self.b, self.tb = self.store.register("bob", "Bob", "password-bob-123")

    def test_default_closed_and_auth_token(self):
        self.assertEqual(self.a["status"], "closed")
        self.assertEqual(self.store.authenticate(self.ta)["id"], self.a["id"])
        self.assertIsNone(self.store.authenticate(self.ta+"x"))
        self.store.logout(self.ta)
        self.assertIsNone(self.store.authenticate(self.ta))

    def test_invite_one_use_and_mutual_approval(self):
        self.assertFalse(self.store.permitted(self.a["id"], self.b["id"]))
        code = self.store.invitation(self.a["id"])
        self.assertEqual(self.store.accept_invitation(self.b["id"], code)["handle"], "alice")
        with self.assertRaises(CalllessError):
            self.store.accept_invitation(self.b["id"], code)
        self.assertTrue(self.store.permitted(self.a["id"], self.b["id"]))

    def test_blocks_are_bilateral_safety_barrier(self):
        code = self.store.invitation(self.a["id"])
        self.store.accept_invitation(self.b["id"], code)
        self.store.block(self.a["id"], "bob")
        self.assertFalse(self.store.permitted(self.a["id"], self.b["id"]))
        self.store.block(self.a["id"], "bob", False)
        self.assertTrue(self.store.permitted(self.a["id"], self.b["id"]))

    def test_open_status_must_be_explicit(self):
        self.assertEqual(self.store.set_status(self.a["id"], "open")["status"], "open")
        with self.assertRaises(CalllessError):
            self.store.set_status(self.b["id"], "always")
        self.assertEqual(self.store.lookup("bob")["status"], "closed")

    def test_passwords_not_plaintext_in_database(self):
        raw = Path(self.temp.name, "callless.sqlite3").read_bytes()
        self.assertNotIn(b"password-alice-123", raw)
        self.assertNotIn(self.ta.encode(), raw)

    def test_password_login_and_rejection(self):
        user, token = self.store.login("alice", "password-alice-123")
        self.assertEqual(user["handle"], "alice")
        self.assertTrue(self.store.authenticate(token))
        with self.assertRaises(CalllessError):
            self.store.login("alice", "wrong-password")

    def test_expired_invites_rejected(self):
        code = self.store.invitation(self.a["id"])
        with patch("jarvis_mrb.callless_core.time.time", return_value=99999999999):
            with self.assertRaises(CalllessError):
                self.store.accept_invitation(self.b["id"], code)

    def test_session_api_enforces_pairing_presence_and_signaling(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from jarvis_mrb import callless_api
        app = FastAPI()
        app.include_router(callless_api.router)
        app.include_router(callless_api.api_router)
        with patch.object(callless_api, "store", self.store):
            callless_api.connections.clear()
            callless_api.sessions.clear()
            callless_api.failures.clear()
            self.store.accept_invitation(self.b["id"], self.store.invitation(self.a["id"]))
            self.store.set_status(self.b["id"], "open")
            with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
                header_a = {"Authorization": "Bearer " + self.ta}
                header_b = {"Authorization": "Bearer " + self.tb}
                unavailable = client.post("/callless/v1/sessions", json={"target": "bob"}, headers=header_a)
                self.assertEqual(unavailable.status_code, 409)
                with client.websocket_connect("/callless/v1/socket") as alice:
                    alice.send_json({"type": "auth", "token": self.ta})
                    self.assertEqual(alice.receive_json()["type"], "ready")
                    with client.websocket_connect("/callless/v1/socket") as bob:
                        bob.send_json({"type": "auth", "token": self.tb})
                        self.assertEqual(bob.receive_json()["type"], "ready")
                        result = client.post("/callless/v1/sessions", json={"target": "bob"}, headers=header_a)
                        self.assertEqual(result.status_code, 200, result.text)
                        sid = result.json()["session_id"]
                        self.assertEqual(result.json()["status"], "connected")
                        incoming = bob.receive_json()
                        self.assertEqual(incoming["type"], "incoming")
                        self.assertEqual(incoming["session_id"], sid)
                        attacker = client.post("/callless/v1/sessions/" + sid + "/end", headers={"Authorization": "Bearer unknown"})
                        self.assertEqual(attacker.status_code, 401)
                        bob.send_json({"type": "signal", "session_id": sid, "payload": {"type": "ready"}})
                        message = alice.receive_json()
                        self.assertEqual(message["type"], "signal")
                        self.assertEqual(message["payload"]["type"], "ready")
                        self.assertEqual(client.post("/callless/v1/sessions/" + sid + "/end", headers=header_a).status_code, 200)
                        self.assertEqual(bob.receive_json()["type"], "ended")

    def test_insecure_remote_account_request_rejected(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from jarvis_mrb import callless_api
        app = FastAPI()
        app.include_router(callless_api.router)
        app.include_router(callless_api.api_router)
        with TestClient(app, base_url="http://example.invalid", client=("203.0.113.55", 50000)) as client:
            result = client.get("/callless/v1/me")
            self.assertEqual(result.status_code, 403)


if __name__ == "__main__":
    unittest.main()
