"""Callless directional grants, truthful media state machine and revocation.

Everything here runs in-process with FastAPI's TestClient. No real network, no
real WebRTC and no real microphones: the "clients" are scripted WebSocket
sessions that send the same messages the browser client sends. Timings printed
by these tests are in-process TestClient timings, not network measurements.
"""
import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis_mrb import callless_api, callless_session
from jarvis_mrb.callless_core import CalllessError, CalllessStore


def bearer(token):
    return {"Authorization": "Bearer " + token}


class HubTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = CalllessStore(Path(self.temp.name) / "callless.sqlite3")
        self.a, self.ta = self.store.register("alice", "Alice Anders", "password-alice-123")
        self.b, self.tb = self.store.register("bob", "Bob Brown", "password-bob-123")
        self.store.accept_invitation(self.b["id"], self.store.invitation(self.a["id"]))
        patcher = patch.object(callless_api, "store", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        for container in (callless_api.connections, callless_api.sessions, callless_api.client_caps,
                          callless_api.failures):
            container.clear()
        callless_api.armed.clear()
        app = FastAPI()
        app.include_router(callless_api.router)
        app.include_router(callless_api.api_router)
        self.client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

    # -- helpers --------------------------------------------------------
    def connect(self, token, caps=("media-v1",), arm=False):
        ws = self.stack.enter_context(self.client.websocket_connect("/callless/v1/socket"))
        ws.send_json({"type": "auth", "token": token, "caps": list(caps)})
        ready = self.recv(ws)
        self.assertEqual(ready["type"], "ready")
        if arm:
            ws.send_json({"type": "arm", "armed": True})
            self.assertEqual(self.recv(ws), {"type": "armed", "armed": True})
        return ws

    @staticmethod
    def recv(ws, timeout=5.0):
        """receive_json with a timeout so a missing message fails instead of hanging."""
        if not (hasattr(ws, "_send_rx") and hasattr(ws, "portal")):
            return ws.receive_json()      # other Starlette layout: plain blocking receive
        import anyio

        async def _next():
            with anyio.fail_after(timeout):
                return await ws._send_rx.receive()
        try:
            message = ws.portal.call(_next)
        except TimeoutError:
            raise AssertionError("timed out waiting for a WebSocket message") from None
        if message["type"] != "websocket.send":
            raise AssertionError("socket closed: " + repr(message))
        return json.loads(message["text"])

    def sync(self, ws):
        """Round-trip a ping so every earlier message on this socket was handled.

        Returns messages that arrived meanwhile (they are also kept for wait_for).
        """
        ws.send_json({"type": "ping"})
        new = []
        buf = ws.__dict__.setdefault("_buf", [])
        while True:
            message = self.recv(ws)
            if message["type"] == "pong":
                return new
            new.append(message)
            buf.append(message)

    def wait_for(self, ws, kind, **match):
        buf = ws.__dict__.setdefault("_buf", [])
        fits = lambda m: m["type"] == kind and all(m.get(k) == v for k, v in match.items())
        for i, message in enumerate(buf):
            if fits(message):
                return buf.pop(i)
        for _ in range(30):
            message = self.recv(ws)
            if fits(message):
                return message
            buf.append(message)
        raise AssertionError("never received " + kind)

    def request(self, token, target, expect=200):
        r = self.client.post("/callless/v1/sessions", json={"target": target}, headers=bearer(token))
        self.assertEqual(r.status_code, expect, r.text)
        return r.json()

    def state_of(self, token, sid):
        r = self.client.get("/callless/v1/sessions/" + sid, headers=bearer(token))
        return r.json()["state"] if r.status_code == 200 else None

    def grant(self, token, handle, level):
        r = self.client.put("/callless/v1/grants", json={"handle": handle, "level": level}, headers=bearer(token))
        self.assertEqual(r.status_code, 200, r.text)

    def status(self, token, value):
        r = self.client.put("/callless/v1/presence", json={"status": value}, headers=bearer(token))
        self.assertEqual(r.status_code, 200, r.text)

    def open_for_alice(self):
        """Bob lets Alice connect directly; Bob's global status is open."""
        self.store.set_status(self.b["id"], "open")
        self.store.set_grant(self.b["id"], "alice", "open")

    def live_open_session(self):
        """Alice requests Bob, who granted Open and armed. Returns (alice, bob, sid, started)."""
        self.open_for_alice()
        alice = self.connect(self.ta)
        bob = self.connect(self.tb, arm=True)
        started = time.perf_counter()
        sid = self.request(self.ta, "bob")["session_id"]
        self.assertEqual(self.recv(bob)["state"], "authorized")
        return alice, bob, sid, started

    @staticmethod
    def signal(ws, sid, kind="ready", **extra):
        ws.send_json({"type": "signal", "session_id": sid, "payload": {"type": kind, **extra}})

    def go_signaling(self, alice, bob, sid):
        self.signal(bob, sid, "ready")
        self.assertEqual(self.wait_for(alice, "signal")["payload"]["type"], "ready")
        self.signal(alice, sid, "offer", sdp="v=0 test")
        self.assertEqual(self.wait_for(bob, "signal")["payload"]["type"], "offer")
        self.signal(bob, sid, "answer", sdp="v=0 test")
        self.assertEqual(self.wait_for(alice, "signal")["payload"]["type"], "answer")


class DirectionalPermissionTests(HubTestCase):
    def test_new_contacts_default_to_ask_both_directions(self):
        self.assertEqual(self.store.grant_level(self.a["id"], self.b["id"]), "ask")
        self.assertEqual(self.store.grant_level(self.b["id"], self.a["id"]), "ask")

    def test_precedence_is_most_restrictive_of_grant_and_global_status(self):
        expected = {
            ("open", "open"): "open", ("open", "ask"): "ask", ("open", "closed"): "closed",
            ("ask", "open"): "ask", ("ask", "ask"): "ask", ("ask", "closed"): "closed",
            ("closed", "open"): "closed", ("closed", "ask"): "closed", ("closed", "closed"): "closed",
        }
        for (grant, status), effective in expected.items():
            self.store.set_grant(self.b["id"], "alice", grant)
            self.store.set_status(self.b["id"], status)
            self.assertEqual(self.store.effective_access(self.a["id"], self.b["id"]), effective, (grant, status))

    def test_grants_are_directional(self):
        self.store.set_status(self.a["id"], "open")
        self.store.set_status(self.b["id"], "open")
        self.store.set_grant(self.b["id"], "alice", "open")     # Bob lets Alice in
        self.assertEqual(self.store.effective_access(self.a["id"], self.b["id"]), "open")
        self.assertEqual(self.store.effective_access(self.b["id"], self.a["id"]), "ask")   # Alice never granted Bob open
        self.store.set_grant(self.a["id"], "bob", "closed")
        self.assertEqual(self.store.effective_access(self.b["id"], self.a["id"]), "closed")
        self.assertEqual(self.store.effective_access(self.a["id"], self.b["id"]), "open")

    def test_non_contact_and_block_are_closed(self):
        c, _ = self.store.register("carol", "Carol", "password-carol-123")
        self.assertEqual(self.store.effective_access(self.a["id"], c["id"]), "closed")
        self.store.set_status(self.b["id"], "open")
        self.store.set_grant(self.b["id"], "alice", "open")
        self.store.block(self.a["id"], "bob")
        self.assertEqual(self.store.effective_access(self.a["id"], self.b["id"]), "closed")
        with self.assertRaises(CalllessError):
            self.store.set_grant(self.a["id"], "carol", "open")      # only contacts get grants
        with self.assertRaises(CalllessError):
            self.store.set_grant(self.a["id"], "bob", "always")

    def test_closed_refusals_are_indistinguishable_from_offline(self):
        self.store.set_status(self.b["id"], "open")
        alice = self.connect(self.ta)
        bob = self.connect(self.tb, arm=True)
        messages = set()
        # Bob closed globally.
        self.store.set_status(self.b["id"], "closed")
        messages.add(self.request(self.ta, "bob", 409)["detail"])
        # Bob's grant to Alice is closed.
        self.store.set_status(self.b["id"], "open")
        self.store.set_grant(self.b["id"], "alice", "closed")
        messages.add(self.request(self.ta, "bob", 409)["detail"])
        # Bob blocked Alice.
        self.store.set_grant(self.b["id"], "alice", "open")
        self.store.block(self.b["id"], "alice")
        messages.add(self.request(self.ta, "bob", 409)["detail"])
        # Bob offline (socket closed).
        self.store.block(self.b["id"], "alice", False)
        bob.close()
        for _ in range(50):
            if self.b["id"] not in callless_api.connections:
                break
            time.sleep(0.02)
        messages.add(self.request(self.ta, "bob", 409)["detail"])
        self.assertEqual(messages, {callless_api.UNREACHABLE})
        self.sync(alice)

    def test_contact_listing_hides_peer_status_and_shows_my_grant(self):
        self.grant(self.ta, "bob", "open")
        listing = self.client.get("/callless/v1/contacts", headers=bearer(self.ta)).json()["contacts"][0]
        self.assertEqual(listing["my_grant"], "open")
        self.assertNotIn("status", listing)

    def test_client_without_media_capability_cannot_connect(self):
        self.open_for_alice()
        self.connect(self.ta, caps=())       # old client
        self.connect(self.tb, arm=True)
        r = self.request(self.ta, "bob", 409)
        self.assertIn("up-to-date", r["detail"])


class ConnectionStateTests(HubTestCase):
    def test_open_pair_reaches_media_connected_only_after_both_report(self):
        alice, bob, sid, started = self.live_open_session()
        self.assertEqual(self.state_of(self.ta, sid), "authorized")
        self.go_signaling(alice, bob, sid)
        self.assertEqual(self.wait_for(alice, "state")["state"], "signaling")
        self.assertEqual(self.wait_for(bob, "state")["state"], "signaling")
        # WebSocket signaling is fully established, yet no audio has been attested.
        self.assertEqual(self.sync(alice), [])
        self.assertEqual(self.state_of(self.ta, sid), "signaling")
        alice.send_json({"type": "media", "session_id": sid, "state": "connected"})
        self.sync(alice)
        self.assertEqual(self.state_of(self.ta, sid), "signaling")      # one side only
        self.assertEqual(self.sync(bob), [])
        bob.send_json({"type": "media", "session_id": sid, "state": "connected"})
        done_a = self.wait_for(alice, "state", state="media_connected")
        done_b = self.wait_for(bob, "state", state="media_connected")
        wall_ms = (time.perf_counter() - started) * 1000
        self.assertIsInstance(done_a["connect_ms"], int)
        self.assertGreaterEqual(done_a["connect_ms"], 0)
        self.assertEqual(done_a["connect_ms"], done_b["connect_ms"])
        self.assertLessEqual(done_a["connect_ms"], wall_ms + 5)
        print(f"\n[in-process TestClient timing, not network] hub connect_ms={done_a['connect_ms']} "
              f"wall={wall_ms:.1f} ms", flush=True)
        recent = self.client.get("/callless/v1/sessions/recent", headers=bearer(self.ta)).json()["sessions"][0]
        self.assertEqual(recent["state"], "media_connected")
        self.assertTrue(recent["live"])
        self.assertEqual(recent["connect_ms"], done_a["connect_ms"])
        # Hangup: both sides get an explicit end.
        alice.send_json({"type": "hangup", "session_id": sid})
        end_a = self.wait_for(alice, "ended")
        end_b = self.wait_for(bob, "ended")
        for end in (end_a, end_b):
            self.assertEqual((end["state"], end["reason"]), ("ended", "hangup"))
        history = self.client.get("/callless/v1/sessions/recent", headers=bearer(self.tb)).json()["sessions"][0]
        self.assertEqual((history["state"], history["direction"], history["peer"]), ("ended", "incoming", "alice"))
        self.assertEqual(history["connect_ms"], done_a["connect_ms"])
        self.assertIsNotNone(history["duration_ms"])

    def test_signaling_alone_never_reports_connected(self):
        alice, bob, sid, _ = self.live_open_session()
        # Media attestation before any signaling is ignored.
        bob.send_json({"type": "media", "session_id": sid, "state": "connected"})
        alice.send_json({"type": "media", "session_id": sid, "state": "connected"})
        self.sync(alice); self.sync(bob)
        self.assertEqual(self.state_of(self.ta, sid), "authorized")
        self.go_signaling(alice, bob, sid)
        for _ in range(3):
            self.signal(alice, sid, "candidate", candidate={"candidate": "x"})
        self.sync(alice); self.sync(bob)
        self.assertEqual(self.state_of(self.ta, sid), "signaling")
        # Only Bob attests: still signaling.
        bob.send_json({"type": "media", "session_id": sid, "state": "connected"})
        self.sync(bob)
        self.assertEqual(self.state_of(self.tb, sid), "signaling")
        recent = self.client.get("/callless/v1/sessions/recent", headers=bearer(self.ta)).json()["sessions"][0]
        self.assertIsNone(recent["connect_ms"])

    def test_media_loss_demotes_state_and_recovery_keeps_first_connect_time(self):
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        for ws in (alice, bob):
            self.wait_for(ws, "state", state="signaling")
        for ws in (alice, bob):
            ws.send_json({"type": "media", "session_id": sid, "state": "connected"})
        first = self.wait_for(alice, "state", state="media_connected")
        self.wait_for(bob, "state", state="media_connected")
        alice.send_json({"type": "media", "session_id": sid, "state": "lost"})
        self.assertEqual(self.wait_for(bob, "state", state="signaling")["connect_ms"], first["connect_ms"])
        alice.send_json({"type": "media", "session_id": sid, "state": "connected"})
        again = self.wait_for(bob, "state", state="media_connected")
        self.assertEqual(again["connect_ms"], first["connect_ms"])

    def test_ask_mode_requires_accept(self):
        self.store.set_status(self.b["id"], "open")       # grant stays at the default "ask"
        alice = self.connect(self.ta)
        bob = self.connect(self.tb, arm=True)
        result = self.request(self.ta, "bob")
        sid = result["session_id"]
        self.assertEqual(result["state"], "ringing")
        incoming = self.recv(bob)
        self.assertEqual((incoming["type"], incoming["state"], incoming["access"]), ("incoming", "ringing", "ask"))
        # Signals and media reports while ringing are ignored.
        self.signal(bob, sid, "ready")
        bob.send_json({"type": "media", "session_id": sid, "state": "connected"})
        self.assertEqual(self.sync(alice), [])
        self.assertEqual(self.state_of(self.ta, sid), "ringing")
        # Only the callee can accept.
        self.assertEqual(self.client.post(f"/callless/v1/sessions/{sid}/accept", headers=bearer(self.ta)).status_code, 404)
        self.assertEqual(self.client.post(f"/callless/v1/sessions/{sid}/accept", headers=bearer(self.tb)).status_code, 200)
        self.assertEqual(self.wait_for(alice, "state")["state"], "authorized")

    def test_open_grant_without_armed_receiver_falls_back_to_ask(self):
        self.open_for_alice()
        self.connect(self.ta)
        self.connect(self.tb, arm=False)
        self.assertEqual(self.request(self.ta, "bob")["state"], "ringing")

    def test_global_ask_caps_open_grant(self):
        self.open_for_alice()
        self.store.set_status(self.b["id"], "ask")
        self.connect(self.ta)
        self.connect(self.tb, arm=True)
        self.assertEqual(self.request(self.ta, "bob")["state"], "ringing")

    def test_one_direction_grant_does_not_open_reverse(self):
        self.open_for_alice()                               # Bob lets Alice in
        self.store.set_status(self.a["id"], "open")
        alice = self.connect(self.ta, arm=True)
        self.connect(self.tb, arm=True)
        # Bob -> Alice: Alice's grant to Bob is still the default "ask".
        self.assertEqual(self.request(self.tb, "alice")["state"], "ringing")
        self.sync(alice)

    def test_decline_cancel_and_not_in_two_sessions(self):
        self.open_for_alice()
        self.store.set_grant(self.b["id"], "alice", "ask")
        alice = self.connect(self.ta)
        bob = self.connect(self.tb)
        sid = self.request(self.ta, "bob")["session_id"]
        self.request(self.ta, "bob", 409)                   # already in a session
        self.recv(bob)
        bob.send_json({"type": "hangup", "session_id": sid})
        ended = self.wait_for(alice, "ended")
        self.assertEqual((ended["reason"], ended["state"]), ("declined", "ended"))

    def test_ring_timeout_ends_unanswered_request(self):
        self.store.set_status(self.b["id"], "ask")
        alice = self.connect(self.ta)
        self.connect(self.tb)
        with patch.object(callless_session, "RING_TIMEOUT_SECONDS", 0.2):
            self.request(self.ta, "bob")
            ended = self.wait_for(alice, "ended")
        self.assertEqual(ended["reason"], "no_answer")

    def test_authorized_but_no_media_in_time_is_failed_timeout(self):
        self.open_for_alice()
        alice = self.connect(self.ta)
        bob = self.connect(self.tb, arm=True)
        with patch.object(callless_session, "MEDIA_TIMEOUT_SECONDS", 0.2):
            self.request(self.ta, "bob")
            ended = self.wait_for(alice, "ended")
        self.assertEqual((ended["state"], ended["reason"]), ("failed", "timeout"))
        self.assertEqual(self.wait_for(bob, "ended")["state"], "failed")
        recent = self.client.get("/callless/v1/sessions/recent", headers=bearer(self.ta)).json()["sessions"][0]
        self.assertEqual((recent["state"], recent["reason"], recent["connect_ms"]), ("failed", "timeout", None))


class EndAndRevokeTests(HubTestCase):
    def test_lowering_grant_during_active_session_ends_it_for_both(self):
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        for ws in (alice, bob):
            ws.send_json({"type": "media", "session_id": sid, "state": "connected"})
        self.wait_for(alice, "state", state="media_connected")
        self.grant(self.tb, "alice", "closed")              # Bob revokes
        end_a = self.wait_for(alice, "ended")
        end_b = self.wait_for(bob, "ended")
        self.assertEqual((end_a["reason"], end_a["state"]), ("revoked", "ended"))
        self.assertEqual(end_b["reason"], "revoked")
        self.assertNotIn(sid, callless_api.sessions)

    def test_downgrading_open_to_ask_ends_an_open_session(self):
        alice, bob, sid, _ = self.live_open_session()
        self.grant(self.tb, "alice", "ask")
        self.assertEqual(self.wait_for(alice, "ended")["reason"], "revoked")

    def test_block_ends_session_for_both_and_rejects_inflight_offer(self):
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        r = self.client.put("/callless/v1/block", json={"handle": "alice", "blocked": True}, headers=bearer(self.tb))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.wait_for(alice, "ended")["reason"], "revoked")
        self.assertEqual(self.wait_for(bob, "ended")["reason"], "revoked")
        # An offer already in flight from Alice is not relayed to Bob.
        self.signal(alice, sid, "offer", sdp="late")
        self.assertEqual(self.sync(bob), [])
        self.assertEqual(self.sync(alice), [])

    def test_revoking_while_ringing_rejects_accept(self):
        self.store.set_status(self.b["id"], "ask")
        alice = self.connect(self.ta)
        bob = self.connect(self.tb)
        sid = self.request(self.ta, "bob")["session_id"]
        self.recv(bob)
        self.grant(self.tb, "alice", "closed")
        self.assertEqual(self.wait_for(alice, "ended")["reason"], "revoked")
        self.assertEqual(self.client.post(f"/callless/v1/sessions/{sid}/accept", headers=bearer(self.tb)).status_code, 404)

    def test_global_closed_ends_session_as_unavailable(self):
        alice, bob, sid, _ = self.live_open_session()
        self.status(self.tb, "closed")
        self.assertEqual(self.wait_for(alice, "ended")["reason"], "unavailable")

    def test_mute_is_relayed_to_peer(self):
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        alice.send_json({"type": "mute", "session_id": sid, "muted": True})
        self.assertEqual(self.wait_for(bob, "peer_muted"), {"type": "peer_muted", "session_id": sid, "muted": True})
        alice.send_json({"type": "mute", "session_id": sid, "muted": False})
        self.assertFalse(self.wait_for(bob, "peer_muted")["muted"])

    def test_peer_disconnect_ends_session_for_the_other_side(self):
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        bob.close()
        ended = self.wait_for(alice, "ended")
        self.assertEqual((ended["reason"], ended["state"]), ("peer_left", "ended"))
        self.assertNotIn(sid, callless_api.sessions)

    def test_client_reported_network_failure_before_audio_is_failed(self):
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        alice.send_json({"type": "media", "session_id": sid, "state": "failed", "reason": "network"})
        for ws in (alice, bob):
            ended = self.wait_for(ws, "ended")
            self.assertEqual((ended["state"], ended["reason"]), ("failed", "network"))

    def test_network_end_after_audio_was_live_is_ended_network(self):
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        for ws in (alice, bob):
            ws.send_json({"type": "media", "session_id": sid, "state": "connected"})
        self.wait_for(bob, "state", state="media_connected")
        bob.send_json({"type": "hangup", "session_id": sid, "reason": "network"})
        ended = self.wait_for(alice, "ended")
        self.assertEqual((ended["state"], ended["reason"]), ("ended", "network"))
        self.assertIsNotNone(ended["connect_ms"])

    def test_second_tab_takeover_ends_old_session(self):
        alice, bob, sid, _ = self.live_open_session()
        self.connect(self.tb, arm=True)             # Bob opens a second tab
        self.assertEqual(self.wait_for(alice, "ended")["reason"], "peer_left")

    def test_recent_sessions_are_metadata_only(self):
        alice, bob, sid, _ = self.live_open_session()
        self.signal(bob, sid, "ready")
        self.signal(alice, sid, "offer", sdp="SECRET-SDP-TEXT")
        self.assertEqual(self.wait_for(bob, "signal")["payload"]["sdp"], "SECRET-SDP-TEXT")
        alice.send_json({"type": "hangup", "session_id": sid})
        self.wait_for(bob, "ended")
        raw = Path(self.temp.name, "callless.sqlite3").read_bytes()
        self.assertNotIn(b"SECRET-SDP-TEXT", raw)
        body = self.client.get("/callless/v1/sessions/recent", headers=bearer(self.ta)).text
        self.assertNotIn("SECRET-SDP-TEXT", body)
        self.assertNotIn("sdp", json.loads(body)["sessions"][0])


class MigrationTests(unittest.TestCase):
    def test_old_schema_database_migrates_to_ask_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.sqlite3"
            db = sqlite3.connect(str(path))
            db.executescript("""
                CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'closed', created REAL NOT NULL);
                CREATE TABLE contacts (user_id INTEGER NOT NULL, peer_id INTEGER NOT NULL,
                    blocked INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, peer_id));
                INSERT INTO users(handle,name,salt,password_hash,status,created) VALUES
                    ('alice','Alice','00','00','open',1),('bob','Bob','00','00','open',1);
                INSERT INTO contacts(user_id,peer_id) VALUES (1,2),(2,1);
            """)
            db.commit(); db.close()
            store = CalllessStore(path)
            self.assertEqual(store.grant_level(1, 2), "ask")
            self.assertEqual(store.grant_level(2, 1), "ask")
            # Even though both users' global status was already "open", the migration
            # must not turn that into immediate access.
            self.assertEqual(store.effective_access(1, 2), "ask")
            self.assertEqual(store.effective_access(2, 1), "ask")
            self.assertEqual([c["my_grant"] for c in store.contacts(1)], ["ask"])
            again = CalllessStore(path)          # re-running the migration is a no-op
            self.assertEqual(again.grant_level(1, 2), "ask")
            with contextlib.closing(sqlite3.connect(str(path))) as db:
                columns = [row[1] for row in db.execute("PRAGMA table_info(contacts)")]
            self.assertEqual(columns.count("grant_level"), 1)

    def test_fresh_database_has_grant_column_and_session_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new.sqlite3"
            CalllessStore(path)
            with contextlib.closing(sqlite3.connect(str(path))) as db:
                self.assertIn("grant_level", [row[1] for row in db.execute("PRAGMA table_info(contacts)")])
                self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='session_log'").fetchone())


class StateMachineUnitTests(unittest.TestCase):
    def make(self, access="open"):
        s = callless_session.Session(sid="s", caller=1, callee=2, access=access)
        s.advance("authorized" if access == "open" else "ringing")
        return s

    def test_legal_transitions_only(self):
        s = self.make("ask")
        self.assertFalse(s.advance("signaling"))          # cannot skip approval
        self.assertTrue(s.advance("authorized"))
        self.assertFalse(s.advance("media_connected"))    # cannot skip signaling
        self.assertTrue(s.advance("signaling"))

    def test_media_connected_needs_both_attestations(self):
        s = self.make()
        self.assertIsNone(s.report_media(1, True))        # not signaling yet
        s.advance("signaling")
        self.assertIsNone(s.report_media(1, True))
        self.assertEqual(s.state, "signaling")
        self.assertIsNone(s.report_media(3, True))        # outsider ignored
        self.assertEqual(s.report_media(2, True), "media_connected")
        self.assertIsNotNone(s.connect_ms)
        self.assertEqual(s.report_media(2, False), "signaling")

    def test_terminal_classification(self):
        s = self.make()
        self.assertEqual(s.terminal_state("network"), "failed")
        self.assertEqual(s.terminal_state("hangup"), "ended")
        s.advance("signaling")
        s.report_media(1, True); s.report_media(2, True)
        self.assertEqual(s.terminal_state("network"), "ended")
        self.assertEqual(s.finish("network"), "ended")
        self.assertEqual(s.finish("hangup"), "ended")      # idempotent
        self.assertEqual(s.reason, "network")


class VoiceHandlerTests(HubTestCase):
    def setUp(self):
        super().setUp()
        from jarvis_mrb import callless_voice
        self.voice = callless_voice
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(callless_voice.LOCAL_HANDLE_ENV, None)

    def test_unlinked_backend_is_honest_and_ignores_places(self):
        reply = self.voice.handle("get me to Alex on Callless")
        self.assertIn("iPhone app opens Callless", reply)
        self.assertNotIn("connected to", reply.lower())
        self.assertIsNone(self.voice.handle("get me to the airport"))
        self.assertIsNone(self.voice.handle("what time is it"))

    def test_linked_account_resolves_display_name_without_claiming_connection(self):
        os.environ[self.voice.LOCAL_HANDLE_ENV] = "alice"
        callless_api.connections[self.a["id"]] = object()
        callless_api.connections[self.b["id"]] = object()
        self.store.set_status(self.b["id"], "ask")
        reply = self.voice.handle("Horus, get me to Bob")
        self.assertIn("Bob Brown looks reachable", reply)
        self.assertIn("can't start or confirm audio", reply)
        self.assertNotIn("connected to bob", reply.lower())
        self.assertEqual(self.voice.handle("connect me to bob brown"), reply)

    def test_closed_or_offline_contact_gets_nonrevealing_answer(self):
        os.environ[self.voice.LOCAL_HANDLE_ENV] = "alice"
        callless_api.connections[self.a["id"]] = object()
        closed = self.voice.handle("get me to Bob")           # Bob offline and closed
        callless_api.connections[self.b["id"]] = object()     # online but status still closed
        also_closed = self.voice.handle("get me to Bob")
        self.assertEqual(closed, also_closed)
        self.assertIn("isn't reachable", closed)

    def test_unknown_name_only_answered_when_callless_is_named(self):
        os.environ[self.voice.LOCAL_HANDLE_ENV] = "alice"
        self.assertIsNone(self.voice.handle("get me to Zed"))
        self.assertIn("don't have an approved Callless contact", self.voice.handle("callless with Zed"))

    def test_end_command_ends_live_session_via_hub(self):
        os.environ[self.voice.LOCAL_HANDLE_ENV] = "alice"
        self.assertIn("no live Callless conversation", self.voice.handle("end the Callless conversation"))
        alice, bob, sid, _ = self.live_open_session()
        self.go_signaling(alice, bob, sid)
        reply = self.voice.handle("end the Callless conversation")
        self.assertIn("ended your Callless conversation", reply)
        self.assertEqual(self.wait_for(alice, "ended")["reason"], "hangup")
        self.assertEqual(self.wait_for(bob, "ended")["reason"], "hangup")

    def test_end_without_linked_account_is_honest(self):
        self.assertIn("isn't linked", self.voice.handle("end the callless conversation"))

    def test_registers_with_router_when_present(self):
        try:
            from jarvis_mrb import voice_router
        except ImportError:
            self.skipTest("voice_router not present in this branch")
        self.assertIn("callless", [name for name, _ in voice_router._HANDLERS])


class ClientSourceTests(unittest.TestCase):
    JS = Path(__file__).resolve().parents[1] / "jarvis_mrb" / "callless_ui.js"

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_client_javascript_syntax(self):
        result = subprocess.run(["node", "--check", str(self.JS)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_connect_tone_is_only_triggered_by_hub_media_connected(self):
        source = self.JS.read_text(encoding="utf-8")
        self.assertEqual(source.count("connectTone();"), 1)    # a single call site
        branch = source.index('data.state === "media_connected"')
        self.assertGreater(source.index("connectTone();", branch), branch)
        self.assertIn("packetsReceived", source)             # media is attested from inbound audio stats
        self.assertIn("iceRestart:true", source)
        self.assertIn("Conversation ended", source)


if __name__ == "__main__":
    unittest.main()
