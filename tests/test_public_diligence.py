from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.world_model as world_model
from jarvis_mrb import public_diligence as sec
from jarvis_mrb import matter_diligence as matters


class SECDiligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = world_model.APP_DIR
        world_model.APP_DIR = Path(self.temp.name)

    def tearDown(self) -> None:
        world_model.APP_DIR = self.old_dir
        self.temp.cleanup()

    def test_exact_cik_and_public_filing_accession_provenance(self) -> None:
        with patch("jarvis_mrb.public_diligence._get", return_value={
            "cik": 320193, "name": "Apple Inc.", "tickers": ["AAPL"],
            "filings": {"recent": {
                "form": ["10-K", "8-K"],
                "accessionNumber": ["0000320193-26-000001", "invalid"],
                "filingDate": ["2026-09-19", "2026-09-18"],
                "primaryDocument": ["a10k.htm", "bad"],
            }},
        }) as network:
            response = sec.fetch_company_filings("320193")
        self.assertEqual(response["cik"], "0000320193")
        self.assertEqual(len(response["filings"]), 1)
        self.assertIn("000032019326000001", response["filings"][0]["document_url"])
        network.assert_called_once_with("/submissions/CIK0000320193.json")
        with self.assertRaises(ValueError):
            sec.normalize_cik("Apple Inc.")

    def test_comparisons_not_made_across_durations_or_mismatched_units(self) -> None:
        facts = {
            "unit": "USD",
            "facts": [
                {"value": 100, "end": "2026-06-30", "start": "2026-04-01", "filed": "2026-08-01"},
                {"value": 200, "end": "2026-06-30", "start": "2026-01-01", "filed": "2026-08-01"},
            ],
        }
        ambiguous = sec.compare_explicit_claim(
            claim_value=100, claim_end="2026-06-30", claim_unit="USD",
            concept_result=facts,
        )
        self.assertEqual(ambiguous["status"], "not_comparable")
        precise = sec.compare_explicit_claim(
            claim_value=99, claim_end="2026-06-30", claim_start="2026-04-01",
            claim_unit="USD", concept_result=facts,
        )
        self.assertEqual(precise["status"], "candidate_discrepancy")
        self.assertEqual(
            sec.compare_explicit_claim(
                claim_value=100, claim_end="2026-06-30", claim_unit="shares",
                concept_result=facts,
            )["status"], "not_comparable",
        )

    def test_matter_requires_explicit_cik_and_claim_source(self) -> None:
        matter = matters.create_matter("Private matter")
        with self.assertRaises(ValueError):
            matters.add_numeric_claim(
                matter["id"], "320193", taxonomy="us-gaap", tag="LongTermDebt",
                unit="USD", value=123, end="2026-06-30", source_ref="Agreement § 2",
            )
        issuer = matters.add_issuer(matter["id"], "320193", "Apple Inc.")
        self.assertEqual(issuer["cik"], "0000320193")
        claim = matters.add_numeric_claim(
            matter["id"], "320193", taxonomy="us-gaap", tag="LongTermDebt",
            unit="USD", value=123, end="2026-06-30",
            source_ref="Deal doc v2 page 12",
        )
        with (
            patch("jarvis_mrb.matter_diligence.fetch_company_filings", return_value={
                "status": "ok", "registrant_name": "Apple Inc.", "filings": [],
                "source_url": "https://data.sec.gov",
                "source_note": "meta",
            }),
            patch("jarvis_mrb.matter_diligence.fetch_company_fact", return_value={
                "unit": "USD", "facts": [
                    {"value": 456, "end": "2026-06-30", "start": "",
                     "filed": "2026-08-01", "accession": "1"},
                ],
            }),
        ):
            report = matters.check_matter(matter["id"])
        self.assertEqual(report["claim_checks"][0]["comparison"]["status"], "candidate_discrepancy")
        self.assertEqual(report["claim_checks"][0]["source_ref"], "Deal doc v2 page 12")
        self.assertEqual(len(matters.get_matter(matter["id"])["claims"]), 1)
        self.assertEqual(claim["matter_id"], matter["id"])

    def test_sec_user_agent_required_before_request(self) -> None:
        with patch.dict("os.environ", {"JARVIS_SEC_USER_AGENT": ""}):
            with self.assertRaises(ValueError):
                sec._headers()


if __name__ == "__main__":
    unittest.main()
