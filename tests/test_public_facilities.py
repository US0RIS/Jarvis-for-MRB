from __future__ import annotations

import unittest
from unittest.mock import patch

import jarvis_mrb.public_facilities as facilities


class PublicFacilitiesTests(unittest.TestCase):
    def setUp(self) -> None:
        facilities._next_request = 0.0

    def test_query_is_bounded_and_without_user_injection(self) -> None:
        query = facilities._query(-37.814, 144.963, 1500)
        self.assertIn("out center 90", query)
        self.assertIn('["emergency"="defibrillator"]', query)
        self.assertIn('["amenity"="drinking_water"]', query)
        self.assertIn('["amenity"="toilets"]', query)
        with self.assertRaises(ValueError):
            facilities.nearby_mapped_facilities(float("inf"), 10)

    def test_geographic_distance_and_unverified_access(self) -> None:
        data = {"elements": [
            {
                "type": "node", "id": 12, "lat": -37.8141, "lon": 144.9631,
                "tags": {"amenity": "drinking_water", "name": "Water fountain"},
            },
            {
                "type": "way", "id": 13, "center": {"lat": -37.815, "lon": 144.964},
                "tags": {"amenity": "toilets", "access": "customers", "opening_hours": "09:00-17:00"},
            },
            {
                "type": "node", "id": 14, "lat": -38.5, "lon": 144.963,
                "tags": {"emergency": "defibrillator"},
            },
            {
                "type": "node", "id": 15, "lat": -37.814, "lon": 144.963,
                "tags": {"amenity": "restaurant"},
            },
        ]}
        output = facilities._parse(data, -37.814, 144.963, 1500, 20)
        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["title"], "Water fountain")
        self.assertEqual(output[1]["access"], "customers")
        self.assertEqual(output[1]["opening_hours"], "09:00-17:00")
        self.assertEqual(output[0]["source_url"], "https://www.openstreetmap.org/node/12")

    def test_public_provider_failure_not_reported_as_no_facilities(self) -> None:
        from httpx import ConnectError
        with patch("jarvis_mrb.public_facilities.httpx.Client") as client:
            client.return_value.__enter__.return_value.stream.side_effect = ConnectError("offline")
            result = facilities.nearby_mapped_facilities(-37.814, 144.963)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("unavailable", result["source_note"])
        self.assertFalse(result["coordinates_stored"])

    def test_shared_public_provider_not_hammered(self) -> None:
        with patch("jarvis_mrb.public_facilities.httpx.Client") as client:
            client.return_value.__enter__.return_value.stream.side_effect = ValueError("down")
            facilities.nearby_mapped_facilities(-37.814, 144.963)
            second = facilities.nearby_mapped_facilities(-37.814, 144.963)
        self.assertEqual(second["status"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
