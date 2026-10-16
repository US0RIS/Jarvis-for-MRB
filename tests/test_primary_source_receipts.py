from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest
from unittest.mock import patch

from jarvis_mrb import search_integrity as integrity


class PrimarySourceReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"research.sqlite3"
        self.out=self.root/"receipts"
        self.settings=[
            patch.object(integrity,"APP_DIR",self.root),
            patch.object(integrity,"AUDIT_DB",self.db),
            patch.object(integrity,"RECEIPT_DIR",self.out),
        ]
        for setting in self.settings: setting.start()

    def tearDown(self):
        for setting in reversed(self.settings): setting.stop()
        self.tmp.cleanup()

    def test_verified_lookup_produces_inspectable_hash_linked_receipt(self):
        rid=integrity.record_primary_source_check(
            "Did Google announce Gemini 4 Argon today?",
            "primary_source_mentions_subject",
            [{"url":"https://blog.google/ai/product","host":"blog.google"}],
        )
        self.assertTrue(rid.startswith("V-"))
        receipt=integrity.load_receipt(rid)
        self.assertEqual(receipt["kind"],"primary_source_lookup")
        self.assertEqual(receipt["outcome"],"primary_source_mentions_subject")
        self.assertEqual(receipt["sources"][0]["id"],"E1")
        self.assertFalse(receipt["authenticated_social_post"])
        self.assertFalse(receipt["proves_absence"])
        self.assertEqual(receipt["claim_entailment"],"not_evaluated")
        ok,final_hash=integrity.verify_receipt_ledger(rid)
        self.assertTrue(ok)
        self.assertEqual(final_hash,receipt["final_hash"])
        on_disk=json.loads((self.out/(rid+".json")).read_text())
        self.assertEqual(on_disk["receipt_id"],rid)

    def test_absence_of_retrieval_can_never_be_mislabeled_as_negative_proof(self):
        rid=integrity.record_primary_source_check(
            "Did Google announce Gemini 4 Argon today?",
            "unverified",[],
        )
        receipt=integrity.load_receipt(rid)
        self.assertFalse(receipt["source_mentions_subject"])
        self.assertFalse(receipt["proves_absence"])
        self.assertEqual(receipt["sources"],[])

    def test_rejects_fabricated_provenance_for_failed_check(self):
        with self.assertRaises(ValueError):
            integrity.record_primary_source_check(
                "Did Google announce Gemini 4 Argon today?",
                "search_unavailable",
                [{"url":"https://blog.google/a","host":"blog.google"}],
            )
        with self.assertRaises(ValueError):
            integrity.record_primary_source_check("Q","primary_source_mentions_subject",[])
        with self.assertRaises(ValueError):
            integrity.record_primary_source_check("Q","definitely_fake",[])

    def test_event_tampering_breaks_receipt_verification(self):
        rid=integrity.record_primary_source_check(
            "Did Google announce Gemini 4 Argon today?",
            "unverified",[],
        )
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE research_events SET payload_json=? WHERE run_id=? AND seq=1",
                       ('{"changed":true}',rid))
        ok,message=integrity.verify_receipt_ledger(rid)
        self.assertFalse(ok)
        self.assertIn("hash mismatch",message)

    def test_agent_emits_receipt_only_after_attempting_verification(self):
        from jarvis_mrb import agent
        from jarvis_mrb.public_claim_verifier import verify_public_claim
        result={"ok":True,"status":"unverified",
                "message":"Official post unverified; cannot infer fakery.","sources":[]}
        with patch("jarvis_mrb.public_claim_verifier.verify_public_claim",return_value=result) as lookup:
            reply=agent._execute_unchecked(
                "web.verify",{"query":"Did Google announce Gemini 4 Argon today?"}
            )
        lookup.assert_called_once()
        self.assertIn("Official post unverified",reply.message)
        self.assertIn("Primary-source lookup receipt: V-",reply.message)
        self.assertTrue(reply.ok)


if __name__=="__main__":
    unittest.main()
