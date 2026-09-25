from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from jarvis_mrb.public_epa import fetch_epa_facility, normalize_frs


class EPAFacilityTests(unittest.TestCase):
    def test_exact_frs_query_reports_source_limited_enforcement_summary(self) -> None:
        frs = "110000123456"
        payload = {"features": [{"attributes": {
            "REGISTRY_ID": frs, "FAC_NAME": "Example Facility",
            "FAC_CITY": "Pasadena", "FAC_STATE": "CA",
            "FAC_FORMAL_ACTION_COUNT": 2, "FAC_TOTAL_PENALTIES": 1000,
            "FAC_CURR_COMPLIANCE_STATUS": "No Violation Identified",
            "DFR_URL": "https://echo.epa.gov/detailed-facility-report",
        }}]}
        with patch("jarvis_mrb.public_epa.httpx.Client") as client:
            handle = client.return_value.__enter__.return_value
            stream = handle.stream.return_value.__enter__.return_value
            stream.iter_bytes.return_value = [json.dumps(payload).encode()]
            report = fetch_epa_facility(frs)
            params = handle.stream.call_args.kwargs["params"]
        self.assertEqual(params["where"], "REGISTRY_ID='110000123456'")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["facilities"][0]["formal_action_count"], 2)
        self.assertIn("not clearance", report["source_note"])

    def test_absence_is_not_clearance_and_name_is_not_identity(self) -> None:
        with self.assertRaises(ValueError):
            normalize_frs("EPA Corporate Co.")
        with patch("jarvis_mrb.public_epa.httpx.Client") as client:
            stream = client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            stream.iter_bytes.return_value = [b'{"features":[]}']
            report = fetch_epa_facility("110000123456")
        self.assertEqual(report["status"], "no_record_for_exact_frs_id")
        self.assertIn("not clearance", report["source_note"])


if __name__ == "__main__":
    unittest.main()
