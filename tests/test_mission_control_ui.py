"""Native Horus Mission Control regression checks, with a Windows UI smoke."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "packaging" / "mission_control.py"
ENTRY = ROOT / "packaging" / "horus_desktop.py"


class MissionControlSourceTests(unittest.TestCase):
    def test_native_qt_and_real_endpoints(self):
        source = GUI.read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertTrue(any(isinstance(n, ast.ImportFrom) and n.module == "PySide6.QtWidgets"
                            for n in tree.body))
        self.assertIn("class MissionControlWindow(", source)
        for name in ("Conversation", "Awareness", "Control", "Settings"):
            with self.subTest(page=name):
                self.assertIn(name, source)
        for route in ("proactive/watches", "proactive/ledger?limit=8",
                      "memory/objects", "command", "health"):
            with self.subTest(route=route):
                self.assertIn(route, source)
        self.assertNotIn("tkinter", source.lower())
        self.assertNotIn("sample_activity", source.lower())

    def test_entrypoint_constructs_real_qt_ui_in_frozen_smoke(self):
        source = ENTRY.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("from mission_control import start_qt", source)
        self.assertIn('"--self-test"', source)
        self.assertIn("self_test=True", source)
        self.assertIn('"--service"', source)
        self.assertNotIn("tkinter", source.lower())

    @unittest.skipUnless(sys.platform == "win32", "Qt widget smoke runs on Windows")
    def test_all_qt_pages_construct_offscreen(self):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, str(ENTRY), "--self-test"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, (result.stderr + "\n" + result.stdout)[-4000:])


if __name__ == "__main__":
    unittest.main()
