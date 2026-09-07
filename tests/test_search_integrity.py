from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis_mrb import search_integrity as si


class SearchIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.old_app = si.APP_DIR
        self.old_db = si.AUDIT_DB
        self.old_receipts = si.RECEIPT_DIR
        si.APP_DIR = base
        si.AUDIT_DB = base / "search_integrity.sqlite3"
        si.RECEIPT_DIR = base / "research_receipts"

    def tearDown(self) -> None:
        si.APP_DIR = self.old_app
        si.AUDIT_DB = self.old_db
        si.RECEIPT_DIR = self.old_receipts
        self.temp.cleanup()

    def test_high_selection_risk_detection(self) -> None:
        self.assertTrue(si.requires_audited_research("Find the best watch under $7,500"))
        self.assertTrue(si.requires_audited_research("Compare all of the realistic options"))
        self.assertFalse(si.requires_audited_research("What is the current score?"))

    def test_research_receipt_records_all_query_families_and_hash_chain(self) -> None:
        specs = [si.QuerySpec(family, f"query {family}") for family in si.REQUIRED_FAMILIES]
        family_index = {family: index for index, family in enumerate(si.REQUIRED_FAMILIES)}

        def fake_search(query: str, *, num: int, refine: bool):
            family = query.split(" ", 1)[1]
            index = family_index[family]
            rows = []
            if index < 6:
                for offset in range(4):
                    doc = index * 4 + offset
                    domain = f"source{doc % 10}.example"
                    rows.append({
                        "kind": "organic",
                        "title": f"Document {doc}",
                        "text": f"Evidence for document {doc}",
                        "domain": domain,
                        "date": "2026-09-01",
                        "link": f"https://{domain}/doc/{doc}",
                    })
            else:
                # The final independent search families find no new URLs, showing
                # measurable saturation rather than merely exhausting a query count.
                for doc in range((index - 6) * 4, (index - 6) * 4 + 4):
                    domain = f"source{doc % 10}.example"
                    rows.append({
                        "kind": "organic",
                        "title": f"Document {doc}",
                        "text": f"Evidence for document {doc}",
                        "domain": domain,
                        "date": "2026-09-01",
                        "link": f"https://{domain}/doc/{doc}",
                    })
            return SimpleNamespace(ok=True, message="ok", data={"evidence": rows})

        with patch.object(si, "_extract_candidates", return_value=[]):
            result = si.audited_research(
                "Find the best example option",
                search_fn=fake_search,
                query_specs=specs,
                num_per_query=10,
                synthesize=False,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.data["coverage"]["grade"], "A")
        self.assertEqual(result.data["coverage"]["successful_families"], 8)
        self.assertEqual(result.data["coverage"]["unique_results"], 24)
        self.assertGreaterEqual(result.data["coverage"]["unique_domains"], 8)
        self.assertEqual(result.data["coverage"]["late_query_novelty"], 0.0)
        self.assertFalse(result.data["open_web_completeness_claim"])

        ok, final_hash = si.verify_receipt_ledger(result.receipt_id)
        self.assertTrue(ok)
        self.assertEqual(final_hash, result.data["ledger_final_hash"])

        receipt_path = si.RECEIPT_DIR / f"{result.receipt_id}.json"
        self.assertTrue(receipt_path.exists())
        summary = si.research_receipt(result.receipt_id)
        self.assertIn(result.receipt_id, summary)
        self.assertIn("Query trace", summary)
        self.assertIn("Open-web", result.message)

    def test_provider_failure_prevents_high_coverage_grade(self) -> None:
        specs = [si.QuerySpec(family, f"query {family}") for family in si.REQUIRED_FAMILIES]

        def fake_search(query: str, *, num: int, refine: bool):
            if query.endswith("disconfirming"):
                return SimpleNamespace(ok=False, message="provider failure", data={"evidence": []})
            family = query.split(" ", 1)[1]
            return SimpleNamespace(ok=True, message="ok", data={"evidence": [{
                "kind": "organic",
                "title": family,
                "text": "evidence",
                "domain": f"{family}.example",
                "date": "",
                "link": f"https://{family}.example/item",
            }]})

        with patch.object(si, "_extract_candidates", return_value=[]):
            result = si.audited_research(
                "Compare every option rigorously",
                search_fn=fake_search,
                query_specs=specs,
                synthesize=False,
            )
        self.assertNotEqual(result.data["coverage"]["grade"], "A")
        self.assertGreater(result.data["coverage"]["provider_failures"], 0)
        self.assertIn("failures", result.data["stop_reason"])


if __name__ == "__main__":
    unittest.main()
