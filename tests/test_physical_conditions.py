from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from jarvis_mrb.physical_conditions import (
    _air_quality,
    _official_alerts,
    physical_conditions,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes")


class PhysicalConditionsTests(unittest.TestCase):
    def test_air_quality_is_labelled_modelled_and_freshness_checked(self) -> None:
        payload = {
            "current": {
                "time": _now(), "us_aqi": 76, "european_aqi": 45,
                "pm2_5": 13.04, "uv_index": 4.2,
            }
        }
        result = _air_quality(payload, "checked")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["us_aqi"], 76)
        self.assertEqual(result["pm2_5_ug_m3"], 13.0)
        self.assertIn("NOT a local sensor", result["source_note"])
        payload["current"]["time"] = (
            datetime.now(timezone.utc) - timedelta(hours=12)
        ).replace(tzinfo=None).isoformat()
        self.assertEqual(_air_quality(payload, "checked")["status"], "stale")

    def test_nws_ignores_expired_alert_and_does_not_claim_all_clear(self) -> None:
        past = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        response = _official_alerts({"features": [
            {"properties": {"event": "Old Warning", "expires": past}},
            {"properties": {
                "event": "Heat Advisory", "expires": future,
                "severity": "Moderate", "instruction": "Take precautions",
            }},
        ]}, "checked")
        self.assertEqual(len(response["alerts"]), 1)
        self.assertEqual(response["alerts"][0]["event"], "Heat Advisory")
        self.assertIn("not an all-hazards clearance", response["source_note"])
        self.assertEqual(_official_alerts({"features": []}, "checked")["alerts"], [])

    def test_nws_result_cap_is_not_mislabeled_complete(self) -> None:
        response = _official_alerts({"features": [
            {"properties": {"id": f"NWS-{index}", "event": "Heat Advisory"}}
            for index in range(16)
        ]}, "checked")
        self.assertEqual(response["status"], "partial")
        self.assertTrue(response["source_limit_reached"])
        self.assertEqual(response["source_result_limit"], 15)
        self.assertEqual(len(response["alerts"]), 15)

    def test_melbourne_uses_air_quality_but_does_not_claim_nws_coverage(self) -> None:
        payload = {"current": {"time": _now(), "us_aqi": 36, "pm2_5": 6.1}}
        with patch("jarvis_mrb.physical_conditions._read_json", return_value=payload) as read:
            result = physical_conditions(-37.815, 144.963)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(result["air_quality"]["status"], "ok")
        self.assertEqual(result["weather_alerts"]["status"], "unsupported_region")
        self.assertIn("NOT an all clear", result["weather_alerts"]["source_note"])

    def test_partial_provider_failure_is_not_clear_skies(self) -> None:
        from httpx import ConnectError
        with patch(
            "jarvis_mrb.physical_conditions._read_json",
            side_effect=ConnectError("offline"),
        ):
            result = physical_conditions(34.1, -118.2)
        self.assertEqual(result["air_quality"]["status"], "unavailable")
        self.assertEqual(result["weather_alerts"]["status"], "unavailable")
        self.assertFalse(result["coordinates_stored"])

    def test_rejects_nan_coordinates(self) -> None:
        with self.assertRaises(ValueError):
            physical_conditions(float("nan"), 144.96)


if __name__ == "__main__":
    unittest.main()
