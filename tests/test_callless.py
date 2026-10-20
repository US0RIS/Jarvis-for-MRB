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


if __name__ == "__main__":
    unittest.main()
