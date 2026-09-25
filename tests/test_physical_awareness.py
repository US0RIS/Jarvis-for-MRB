from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb.physical_awareness import physical_awareness


class PhysicalAwarenessTests(unittest.TestCase):
    def test_parallel_briefing_preserves_source_bounds_and_partial_coverage(self) -> None:
        with (
            patch(
                "jarvis_mrb.public_camera_catalog.discover_public_cameras",
                return_value={
                    "status": "unsupported_region", "source_url": "official",
                    "cameras": [], "coverage": "not integrated",
                    "source_note": "No access", "coordinates_stored": False,
                },
            ),
            patch(
                "jarvis_mrb.physical_conditions.physical_conditions",
                return_value={
                    "air_quality": {"status": "ok", "us_aqi": 42, "source_url": "source", "source_note": "model"},
                    "weather_alerts": {
                        "status": "unsupported_region", "alerts": [],
                        "source_url": "source", "source_note": "not in region",
                    },
                    "checked_at": "2026-09-19",
                    "location_sharing_note": "no persistence",
                },
            ),
            patch(
                "jarvis_mrb.public_facilities.nearby_mapped_facilities",
                return_value={
                    "status": "ok", "facilities": [{"title": "Water", "distance_m": 100}],
                    "source_url": "osm", "source_note": "unverified",
                },
            ),
        ):
            result = physical_awareness(-37.814, 144.963)
        self.assertEqual(result["status"], "partial")
        self.assertIn("No published camera provider", result["summary"])
        self.assertIn("modelled US AQI 42", result["summary"])
        self.assertIn("official weather alerts not integrated", result["summary"])
        self.assertIn("1 nearby community-mapped", result["summary"])
        self.assertIn("not observe through walls", result["location_note"])

    def test_provider_exception_is_typed_unavailable_not_all_clear(self) -> None:
        with (
            patch(
                "jarvis_mrb.public_camera_catalog.discover_public_cameras",
                side_effect=RuntimeError("backend"),
            ),
            patch(
                "jarvis_mrb.physical_conditions.physical_conditions",
                side_effect=RuntimeError("backend"),
            ),
            patch(
                "jarvis_mrb.public_facilities.nearby_mapped_facilities",
                side_effect=RuntimeError("backend"),
            ),
        ):
            result = physical_awareness(34.1, -118.2)
        self.assertEqual(result["cameras"]["status"], "unavailable")
        self.assertEqual(result["conditions"]["weather_alerts"]["status"], "unavailable")
        self.assertEqual(result["facilities"]["status"], "unavailable")
        self.assertIn("unavailable", result["summary"])
        self.assertNotIn("no active NWS point alerts returned", result["summary"])


if __name__ == "__main__":
    unittest.main()
