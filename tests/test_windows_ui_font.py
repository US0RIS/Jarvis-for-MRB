"""Regression test for the Tk font that crashed the packaged Windows UI.

The headless Tcl parser must see the entire Segoe UI family as a single
word and the second word as the numeric point size.
"""
from __future__ import annotations

import runpy
import tkinter
import unittest
from pathlib import Path


class WindowsDesktopFontTests(unittest.TestCase):
    def test_default_font_has_a_single_family_token_and_numeric_size(self):
        source = Path(__file__).resolve().parents[1] / "packaging" / "horus_desktop.py"
        module = runpy.run_path(str(source), run_name="horus_font_regression")
        font_spec = module["UI_FONT_SPEC"]
        self.assertEqual(tkinter.Tcl().splitlist(font_spec), ("Segoe UI", "10"))


if __name__ == "__main__":
    unittest.main()
