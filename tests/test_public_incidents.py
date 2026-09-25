from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from jarvis_mrb.public_incidents import regional_earthquakes


class OfficialEarthquakeTests(unittest.TestCase):
    def test_global_region_query_and_event_provenance(self) -> None:
        now_ms = int(time.time() * 1000)
        payload = {
            "features": [
                {
                    "id": "us7000example",
                    "properties": {
                        "mag": 3.4, "time": now_ms,
                        "place": "Near Melbourne", "status": "reviewed",
                        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000example",
                    },
                },
            ],
        }
        with patch("jarvis_mrb.public_incidents.httpx.Client") as client:
            stream = client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            stream.iter_bytes.return_value = [json.dumps(payload).encode()]
            answer = regional_earthquakes(-37.8, 144.96)
            params = client.return_value.__enter__.return_value.stream.call_args.kwargs["params"]
        self.assertEqual(answer["status"], "ok")
        self.assertEqual(answer["events"][0]["magnitude"], 3.4)
        self.assertTrue(answer["events"][0]["reviewed"])
        self.assertLessEqual(params["maxradiuskm"], 300)
        self.assertEqual(params["limit"], 50)
        self.assertIn("not all local emergencies", answer["source_note"])

    def test_not_unbounded_or_emergency_all_clear(self) -> None:
        with self.assertRaises(ValueError):
            regional_earthquakes(0, 0, radius_km=1000)
        with patch("jarvis_mrb.public_incidents.httpx.Client") as client:
            stream = client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            stream.iter_bytes.return_value = [b'{"features": []}']
            answer = regional_earthquakes(34, -118)
        self.assertEqual(answer["events"], [])
        self.assertIn("not all local emergencies", answer["source_note"])


if __name__ == "__main__":
    unittest.main()
