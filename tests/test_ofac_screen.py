from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb import ofac_screen


class OFACCandidateTests(unittest.TestCase):
    def test_local_file_candidate_and_nonmatch_never_claim_clearance(self) -> None:
        records = [
            f"{i},Example Entity {i},entity,Other,,,,,,\r\n" for i in range(1, 102)
        ]
        data = ofac_screen._parse_sdn_csv(
            "".join(records).encode("utf-8"), retrieved_at="2026-09-19T00:00:00+00:00"
        )
        self.assertEqual(data["record_count"], 101)
        with patch("jarvis_mrb.ofac_screen._download", return_value=data):
            candidate = ofac_screen.screen_exact_name("example-ENTITY 9")
            absent = ofac_screen.screen_exact_name("Definitely Unlisted Firm")
        self.assertEqual(candidate["status"], "review_candidates")
        self.assertEqual(candidate["candidates"][0]["sdn_id"], "9")
        self.assertEqual(absent["status"], "no_exact_name_candidate_in_this_file")
        self.assertIn("NOT sanctions clearance", absent["source_note"])
        self.assertIn("non-SDN", candidate["source_note"])
        self.assertIn("50 Percent", candidate["source_note"])

    def test_bad_snapshot_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ofac_screen._parse_sdn_csv(b"no,valid,list\n", retrieved_at="today")


if __name__ == "__main__":
    unittest.main()
