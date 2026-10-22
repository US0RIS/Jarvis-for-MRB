"""Guard against the original Windows launcher font crash.

Tkinter's "Segoe UI 10" parser caused a launch-time TclError. The desktop
now uses Qt, which accepts the Segoe UI font-family name through CSS.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsDesktopFontTests(unittest.TestCase):
    def test_launcher_no_longer_uses_tcl_font_parser(self):
        launcher = (ROOT / "packaging" / "horus_desktop.py").read_text(encoding="utf-8")
        self.assertNotIn("tkinter", launcher.lower())
        self.assertNotIn('option_add("*Font"', launcher)
        ast.parse(launcher)

    def test_qt_stylesheet_quotes_multiword_family(self):
        ui = (ROOT / "packaging" / "mission_control.py").read_text(encoding="utf-8")
        self.assertIn('font-family: "Segoe UI"', ui)
        ast.parse(ui)


if __name__ == "__main__":
    unittest.main()
