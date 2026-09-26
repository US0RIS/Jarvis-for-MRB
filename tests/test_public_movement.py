from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import time
import unittest
from unittest.mock import patch

from jarvis_mrb import public_movement


class OpenSkyMovementTests(unittest.TestCase):
    def test_current_states_preserve_transport_ids_not_people(self):
        now = time.time()
        payload = {
            "time": now,
            "states": [
                [
                    "abc123", "AAL100", "United States", now - 1, now,
                    -118.25, 34.05, 3048.0, False, 210.0, 92.0,
                    0.0, None, None, False, False, 0, 4,
                ],
                [
                    "bad999", "BAD", None, now, now,
                    None, None, None, False, None, None, None,
                    None, None, False, False, 0, 0,
                ],
            ],
        }
        with patch.object(public_movement, "_opensky_request",
                          return_value=payload):
            result = public_movement.opensky_state_vectors(
                latitude=34.05, longitude=-118.25, radius_km=50,
            )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["entities"]), 1)
        item = result["entities"][0]
        self.assertEqual(item["entity_id"], "icao24:abc123")
        self.assertEqual(item["callsign"], "AAL100")
        self.assertEqual(item["entity_type"], "aircraft")
        self.assertEqual(item["category"], 4)
        self.assertNotIn("passenger", item)
        self.assertIn("not person identities", result["source_note"])

    def test_global_opensky_scope_has_no_local_bbox(self):
        now = time.time()
        captured = {}
        def fake(params):
            captured.update(params)
            return {"time": now, "states": []}
        with patch.object(public_movement, "_opensky_request",
                          side_effect=fake):
            result = public_movement.opensky_state_vectors(
                global_scope=True
            )
        self.assertTrue(result["global_scope"])
        self.assertNotIn("lamin", captured)
        self.assertEqual(captured["extended"], 1)
        with self.assertRaises(ValueError):
            public_movement.opensky_state_vectors(
                global_scope=True, latitude=0, longitude=0, radius_km=10,
            )

    def test_stale_opensky_never_claims_current_states(self):
        with patch.object(
            public_movement, "_opensky_request",
            return_value={"time": time.time() - 600, "states": [
                ["abc123"] * 18
            ]},
        ):
            result = public_movement.opensky_state_vectors(
                latitude=0, longitude=0, radius_km=10,
            )
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["entities"], [])

    def test_opensky_oauth_secrets_are_optional_and_not_returned(self):
        public_movement._TOKEN.update(value=None, expires_at=0)
        with patch.dict(os.environ, {
            "OPENSKY_CLIENT_ID": "client",
            "OPENSKY_CLIENT_SECRET": "top-secret",
        }), patch.object(public_movement.httpx, "Client") as client:
            response = client.return_value.__enter__.return_value.post.return_value
            response.json.return_value = {
                "access_token": "bearer-secret", "expires_in": 1800,
            }
            token = public_movement._oauth_token()
        self.assertEqual(token, "bearer-secret")
        request = client.return_value.__enter__.return_value.post.call_args
        self.assertEqual(request.kwargs["data"]["client_secret"], "top-secret")
        public_movement._TOKEN.update(value=None, expires_at=0)


class AISMovementTests(unittest.TestCase):
    def test_no_key_is_explicit_not_configured(self):
        with patch.dict(os.environ, {"AISSTREAM_API_KEY": ""}):
            result = public_movement.aisstream_position_burst(
                latitude=34.0, longitude=-118.2, radius_km=20,
                duration_seconds=0.5,
            )
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["entities"], [])

    def test_ais_position_normalization(self):
        position = {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 368207620,
                "ShipName": "EXAMPLE VESSEL",
                "Latitude": 33.74,
                "Longitude": -118.25,
            },
            "Message": {
                "PositionReport": {
                    "UserID": 368207620,
                    "Sog": 12.4,
                    "Cog": 86.7,
                    "TrueHeading": 87,
                    "Valid": True,
                }
            },
        }

        class Socket:
            def __init__(self):
                self.calls = 0
                self.sent = None
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def send(self, payload):
                self.sent = json.loads(payload)
            def recv(self, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({
                        "MessageType": "SubscriptionConfirmation",
                        "Message": {"CompressionEnabled": True},
                    }).encode()
                if self.calls == 2:
                    return json.dumps(position).encode()
                raise TimeoutError()

        socket = Socket()
        with patch.dict(os.environ, {
            "AISSTREAM_API_KEY": "server-secret",
        }), patch("websockets.sync.client.connect",
                  return_value=socket) as connect:
            result = public_movement.aisstream_position_burst(
                latitude=33.75, longitude=-118.25, radius_km=30,
                duration_seconds=0.5,
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["entities"]), 1)
        vessel = result["entities"][0]
        self.assertEqual(vessel["entity_id"], "mmsi:368207620")
        self.assertEqual(vessel["name"], "EXAMPLE VESSEL")
        self.assertAlmostEqual(vessel["speed_knots"], 12.4)
        self.assertNotIn("server-secret", str(result))
        sent = socket.sent
        self.assertEqual(sent["APIKey"], "server-secret")
        self.assertEqual(sent["FilterMessageTypes"], ["PositionReport"])
        self.assertEqual(connect.call_args.args[0],
                         "wss://stream.aisstream.io/v0/stream")

    def test_bbox_can_expand_to_global_without_private_network_access(self):
        self.assertEqual(
            public_movement._bbox(0, 0, 20_000),
            [-90.0, -180.0, 90.0, 180.0],
        )


if __name__ == "__main__":
    unittest.main()
