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

    def test_usgs_geojson_epicenter_is_publisher_location_not_query_center(self) -> None:
        now_ms = int(time.time() * 1000)
        payload = {"features": [
            {"id": "us_geo_1", "properties": {
                "mag": 3.1, "time": now_ms, "place": "reported region",
                "url": "https://earthquake.usgs.gov/"
            }, "geometry": {"type": "Point",
                            "coordinates": [-118.15, 34.11, 7.2]}},
            {"id": "us_geo_2", "properties": {
                "mag": 3.2, "time": now_ms, "place": "unknown geometry"
            }, "geometry": {"type": "Point", "coordinates": [999, 34.1]}}
        ]}
        with patch("jarvis_mrb.public_incidents.httpx.Client") as client:
            stream=client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            stream.iter_bytes.return_value=[json.dumps(payload).encode()]
            result=regional_earthquakes(34.12,-118.16)
        self.assertEqual(result["status"],"ok")
        self.assertEqual(
            (result["events"][0]["latitude"],result["events"][0]["longitude"]),
            (34.11,-118.15),
        )
        self.assertIsNone(result["events"][1]["latitude"])
        self.assertIsNone(result["events"][1]["longitude"])

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
