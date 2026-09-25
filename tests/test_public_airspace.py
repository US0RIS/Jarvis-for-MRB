from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from jarvis_mrb.public_airspace import airspace_region


class AirspaceTests(unittest.TestCase):
    def test_regional_state_vectors_aggregate_not_person_tracking(self) -> None:
        payload = {
            "time": time.time(),
            "states": [
                ["abcdef", "JET123", None, time.time(), time.time(), -118.2, 34.1, 1000, False],
                ["fedcba", "GROUND", None, time.time(), time.time(), -118.3, 34.2, 0, True],
            ],
        }
        with patch("jarvis_mrb.public_airspace.httpx.Client") as client:
            stream = client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            stream.iter_bytes.return_value = [json.dumps(payload).encode()]
            result = airspace_region(34.1, -118.2)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["aircraft_count"], 1)
        self.assertNotIn("JET123", str(result))
        self.assertNotIn("abcdef", str(result))
        self.assertIn("not proof", result["source_note"])

    def test_old_states_are_not_live(self) -> None:
        payload = {"time": time.time() - 1000, "states": []}
        with patch("jarvis_mrb.public_airspace.httpx.Client") as client:
            stream = client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            stream.iter_bytes.return_value = [json.dumps(payload).encode()]
            result = airspace_region(-37.8, 145)
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["aircraft_count"])

    def test_out_of_bounds_rejected(self) -> None:
        with self.assertRaises(ValueError):
            airspace_region(float("nan"), 0)
        with self.assertRaises(ValueError):
            airspace_region(0, 0, radius_km=1000)


if __name__ == "__main__":
    unittest.main()
