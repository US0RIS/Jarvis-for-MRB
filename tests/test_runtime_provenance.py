from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import unittest

from fastapi import HTTPException, Response

from jarvis_mrb import runtime_provenance


class RuntimeProvenanceTests(unittest.TestCase):
    def test_on_disk_fingerprints_are_reproducible_but_not_claimed_as_loaded_bytecode(self):
        with TemporaryDirectory() as root:
            home=Path(root)
            target=home/"jarvis_mrb"/"agent.py"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"def version(): return 1\n")
            info=runtime_provenance.inspect(
                root=home, started_at="2026-10-15T19:00:00+00:00",
                runtime_nonce="test-runtime",
            )
            self.assertEqual(info["runtime_instance"],"test-runtime")
            self.assertEqual(info["checkout_commit"],None)
            self.assertEqual(info["checkout_state"],"unknown")
            self.assertEqual(
                info["filesystem_sources"]["jarvis_mrb/agent.py"]["sha256"],
                hashlib.sha256(target.read_bytes()).hexdigest(),
            )
            self.assertFalse(info["filesystem_sources"]["jarvis_mrb/service.py"]["present"])
            self.assertIn("Disk hashes may change",info["limitations"][1])

    def test_process_identity_remains_same_within_current_python_process(self):
        a=runtime_provenance.inspect()
        b=runtime_provenance.inspect()
        self.assertEqual(a["runtime_instance"],b["runtime_instance"])
        self.assertEqual(a["process_started_at"],b["process_started_at"])

    def test_service_requires_private_bearer_token(self):
        from jarvis_mrb import service
        with patch.object(service,"API_TOKEN","private-example-token"):
            with self.assertRaises(HTTPException) as ctx:
                service.runtime_build_provenance(Response(),authorization=None)
            self.assertEqual(ctx.exception.status_code,401)
            out=Response()
            info=service.runtime_build_provenance(
                out,authorization="Bearer private-example-token"
            )
            self.assertEqual(info["scope"],"server process identity and live disk hashes only")
            self.assertEqual(out.headers["cache-control"],"private, no-store")

    def test_service_does_not_expose_build_without_token_configured(self):
        from jarvis_mrb import service
        with patch.object(service,"API_TOKEN",""):
            with self.assertRaises(HTTPException) as ctx:
                service.runtime_build_provenance(Response(),authorization=None)
            self.assertEqual(ctx.exception.status_code,503)

    def test_ios_settings_reads_actual_backend_response(self):
        root=Path(__file__).resolve().parents[1]
        client=(root/"ios/JarvisIOS/JarvisAPIClient.swift").read_text()
        ui=(root/"ios/JarvisIOS/SettingsView.swift").read_text()
        self.assertIn('path: "build/provenance"',client)
        self.assertIn('case checkoutCommit = "checkout_commit"',client)
        self.assertIn("await client.runtimeProvenance()",ui)
        self.assertIn("Cannot verify PC backend",ui)
        self.assertIn('path: "capabilities/evidence"',client)
        self.assertIn("await client.capabilityEvidence()",ui)
        self.assertIn("fully verified",ui)
        self.assertIn("No current acceptance readback",ui)


if __name__=="__main__":
    unittest.main()
