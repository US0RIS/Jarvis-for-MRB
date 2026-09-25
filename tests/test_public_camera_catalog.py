from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb.public_camera_catalog import _parse_caltrans, _public_media_url, discover_public_cameras


_SAMPLE = {
    "data": [
        {"cctv": {
            "index": "196", "inService": "true",
            "location": {
                "locationName": "I-110 at Avenue 26", "nearbyPlace": "Cypress Park",
                "latitude": "34.0837", "longitude": "-118.2215",
                "direction": "South",
            },
            "imageData": {
                "streamingVideoURL": "https://wzmedia.dot.ca.gov/D7/CCTV-196.stream/playlist.m3u8",
                "static": {
                    "currentImageURL": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/sample.jpg",
                },
            },
        }},
        {"cctv": {
            "index": "200", "inService": "false",
            "location": {"latitude": "34.1", "longitude": "-118.2"},
            "imageData": {"streamingVideoURL": "https://wzmedia.dot.ca.gov/camera.m3u8"},
        }},
        {"cctv": {
            "index": "bad", "inService": "true",
            "location": {"latitude": "34.1", "longitude": "-118.2"},
            "imageData": {"streamingVideoURL": "http://192.168.0.2/feed"},
        }},
    ]
}


class OfficialCameraDiscoveryTests(unittest.TestCase):
    def test_official_feed_shape_status_and_media_domain(self) -> None:
        items = _parse_caltrans(_SAMPLE, 7)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "caltrans-d7-196")
        self.assertIn("dot.ca.gov", items[0]["stream_url"])
        self.assertFalse(_public_media_url("http://192.168.1.3/camera"))
        self.assertFalse(_public_media_url("https://attacker.example/video"))
        self.assertFalse(_public_media_url("https://cwwp2.dot.ca.gov.evil.com/camera"))
        self.assertFalse(_public_media_url("https://user@wzmedia.dot.ca.gov/camera"))

    def test_location_search_uses_only_provider_and_does_not_claim_footage_is_live(self) -> None:
        record = _parse_caltrans(_SAMPLE, 7)[0]
        with patch(
            "jarvis_mrb.public_camera_catalog._get_district",
            side_effect=lambda district: (
                ([record] if district == 7 else []),
                "2026-09-19T00:00:00+00:00",
            ),
        ):
            result = discover_public_cameras(
                34.084, -118.222, radius_km=2.0, limit=3
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["matching_count"], 1)
        self.assertLess(result["cameras"][0]["distance_km"], 1)
        self.assertIn("not proof", result["source_note"])
        self.assertFalse(result["coordinates_stored"])
        self.assertEqual(len(result["provider_fetched_at"]), 12)

    def test_melbourne_does_not_invent_open_municipal_cctv(self) -> None:
        with patch("jarvis_mrb.public_camera_catalog._get_district") as provider:
            result = discover_public_cameras(-37.814, 144.963, radius_km=5)
        provider.assert_not_called()
        self.assertEqual(result["status"], "unsupported_region")
        self.assertEqual(result["cameras"], [])
        self.assertIn("VicTraffic", result["source_note"])

    def test_reject_bad_coordinates_and_unbounded_search(self) -> None:
        for kwargs in (
            {"latitude": 999, "longitude": 0},
            {"latitude": 0, "longitude": 0, "radius_km": 100},
            {"latitude": 0, "longitude": 0, "limit": 999},
            {"latitude": float("nan"), "longitude": 0},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    discover_public_cameras(**kwargs)


if __name__ == "__main__":
    unittest.main()
