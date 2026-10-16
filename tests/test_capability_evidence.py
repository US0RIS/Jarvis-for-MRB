from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import subprocess
import unittest
from unittest.mock import patch, Mock

from jarvis_mrb import capability_evidence as evidence
from jarvis_mrb.deterministic_dispatch import dispatch
from jarvis_mrb.permissions import TOOL_RISK


COMMIT = "a" * 40


class CapabilityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.path=Path(self.temp.name)/"evidence.json"
        self.now=datetime.now(timezone.utc).replace(microsecond=0)

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_ledger_reports_all_as_unverified(self):
        state=evidence.inspect(path=self.path,at=self.now,commit=COMMIT)
        self.assertEqual(set(state["capabilities"]),set(evidence.CATALOG))
        for row in state["capabilities"].values():
            self.assertEqual(row["status"],"implemented_but_unverified")
            self.assertNotEqual(row["missing_scopes"],[])

    def test_unit_pass_does_not_claim_physical_airpods(self):
        fixture=evidence._SOURCE_ROOT/"tests"/"test_freshness_policy.py"
        self.assertTrue(fixture.is_file())
        self.path.parent.mkdir(parents=True,exist_ok=True)
        record={
            "id":"r_receipt1","capability_id":"airpods_voice","scope":"unit",
            "result":"passed","commit":COMMIT,
            "fixture_sha256":hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "observed_at":self.now.isoformat(),"runner":"local_python_unittest",
        }
        evidence._write([record],self.path)
        result=evidence.inspect(path=self.path,at=self.now,commit=COMMIT)["capabilities"]["airpods_voice"]
        self.assertIn("unit",result["verified_scopes"])
        self.assertIn("physical_airpods",result["missing_scopes"])
        self.assertNotEqual(result["status"],"verified")

    def test_forged_hardware_receipt_does_not_promote(self):
        fake={
            "id":"r_bad","capability_id":"airpods_voice","scope":"physical_airpods",
            "result":"passed","commit":COMMIT,
            "observed_at":self.now.isoformat(),"runner":"local_python_unittest",
        }
        evidence._write([fake],self.path)
        result=evidence.inspect(path=self.path,at=self.now,commit=COMMIT)["capabilities"]["airpods_voice"]
        self.assertEqual(result["verified_scopes"],[])

    def test_stale_and_wrong_commit_receipts_do_not_verify(self):
        entry={
            "id":"r_stale","capability_id":"airpods_voice","scope":"unit","result":"passed",
            "commit":"b"*40,"fixture_sha256":"0"*64,
            "observed_at":(self.now-timedelta(days=9)).isoformat(),
            "runner":"local_python_unittest",
        }
        evidence._write([entry],self.path)
        result=evidence.inspect(path=self.path,at=self.now,commit=COMMIT)["capabilities"]["airpods_voice"]
        self.assertEqual(result["verified_scopes"],[])

    def test_runner_uses_fixed_test_suite_not_shell(self):
        fake_git=Mock(returncode=0,stdout=COMMIT)
        fake_test=Mock(returncode=0,stdout="OK",stderr="")
        with patch.object(evidence.subprocess,"run",side_effect=[fake_git,fake_test]) as runner:
            output=evidence.run_unit_acceptance("user_belief_model",path=self.path)
        self.assertEqual(output["result"],"passed")
        self.assertEqual(output["scope"],"unit")
        unit_args=runner.call_args_list[1].args[0]
        self.assertEqual(unit_args[:4],[evidence.sys.executable,"-m","unittest","discover"])
        self.assertEqual(unit_args[-2],"test_user_belief_model.py")
        self.assertFalse(runner.call_args_list[1].kwargs.get("shell",False))

    def test_voice_self_description_uses_permissioned_deterministic_route(self):
        route=dispatch("What capabilities are verified?")
        self.assertEqual(route.tool,"capabilities.status")
        self.assertEqual(TOOL_RISK["capabilities.status"],"read")

    def test_invalid_capability_does_not_execute_anything(self):
        with patch.object(evidence.subprocess,"run",side_effect=AssertionError("ran")):
            with self.assertRaises(ValueError):
                evidence.run_unit_acceptance("arbitrary command",path=self.path)


if __name__=="__main__":
    unittest.main()
