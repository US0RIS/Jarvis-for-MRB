from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest


class FixedEndpointAcceptanceTests(unittest.TestCase):
    def test_fixed_endpoint_acceptance_harness(self) -> None:
        # Run in a fresh interpreter so module-level SQLite paths and permission paths
        # cannot leak from any earlier unit test. APPDATA is isolated as an additional
        # guard; the acceptance harness itself also redirects its world database.
        with tempfile.TemporaryDirectory() as appdata:
            env = dict(os.environ)
            env["APPDATA"] = appdata
            completed = subprocess.run(
                [sys.executable, "-m", "jarvis_mrb.world_acceptance_check", "--compact"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"Acceptance command did not emit JSON (exit {completed.returncode}). "
                f"stdout={completed.stdout[-2000:]} stderr={completed.stderr[-2000:]} error={exc}"
            )
            return

        failures = result.get("failed_checks") or []
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"Acceptance command failed. failures={failures} stderr={completed.stderr[-2000:]}",
        )
        self.assertTrue(result.get("ok"), msg=f"Acceptance failures: {failures}")
        self.assertFalse(result.get("mutates_user_data"))
        self.assertFalse(result.get("uses_external_services"))
        criteria = result.get("criteria") or {}
        self.assertEqual({int(key) for key in criteria}, set(range(1, 13)))
        self.assertTrue(all(bool(item.get("passed")) for item in criteria.values()))


if __name__ == "__main__":
    unittest.main()
