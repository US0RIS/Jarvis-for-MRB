from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from jarvis_mrb import mesh_windows_screen as win


class WindowsMeshScreenTests(unittest.TestCase):
    def setUp(self):
        self.initial = win._EXPIRES_AT
        self.addCleanup(setattr, win, "_EXPIRES_AT", self.initial)
        win._EXPIRES_AT = None

    def test_default_off_and_explicit_process_opt_in(self):
        with patch("jarvis_mrb.mesh_windows_screen.platform.system", return_value="Windows"), \
             patch.dict(os.environ, {}, clear=True):
            self.assertFalse(win.enabled())
            with self.assertRaises(win.WindowsScreenUnavailable):
                win.begin()
            with self.assertRaises(win.WindowsScreenUnavailable):
                win.frame()
        with patch("jarvis_mrb.mesh_windows_screen.platform.system", return_value="Linux"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_SCREEN_ENABLED": "1"}):
            self.assertFalse(win.enabled())

    def test_explicit_short_lived_permission_and_revoke(self):
        with patch("jarvis_mrb.mesh_windows_screen.platform.system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_SCREEN_ENABLED": "1"}):
            for seconds in (0, True, -100, 301, "120"):
                with self.assertRaises(ValueError):
                    win.begin(seconds)
            status = win.begin(120)
            self.assertEqual(status["node_id"], "windows")
            self.assertTrue(win.active())
            self.assertEqual(win.stop(), {"node_id": "windows", "status": "closed"})
            self.assertFalse(win.active())
            win.begin(15)
            win._EXPIRES_AT = datetime.now(timezone.utc) - timedelta(seconds=1)
            self.assertFalse(win.active())

    def test_fixed_ram_only_capture_and_jpeg_signature(self):
        image = Mock(width=1024, height=768)
        decoded = Mock()
        payload = bytes.fromhex("ffd8ff") + b"n" * 128
        def save(memory, *, format, quality, optimize):
            self.assertIsInstance(memory, BytesIO)
            self.assertEqual(format, "JPEG")
            self.assertEqual(quality, 58)
            memory.write(payload)
        decoded.save.side_effect = save
        image.convert.return_value = decoded
        imagegrab = ModuleType("PIL.ImageGrab")
        imagegrab.grab = Mock(return_value=image)
        pil = ModuleType("PIL")
        pil.ImageGrab = imagegrab
        with patch("jarvis_mrb.mesh_windows_screen.platform.system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_SCREEN_ENABLED": "1"}), \
             patch.dict(sys.modules, {"PIL": pil, "PIL.ImageGrab": imagegrab}):
            with self.assertRaises(win.WindowsScreenUnavailable):
                win.frame()
            win.begin(120)
            frame, mime = win.frame()
            self.assertEqual(mime, "image/jpeg")
            self.assertEqual(frame, payload)
            imagegrab.grab.assert_called_once_with(all_screens=False)
            image.close.assert_called()
            win.stop()
            with self.assertRaises(win.WindowsScreenUnavailable):
                win.frame()

    def test_capture_failure_is_not_fake_arrival_or_success(self):
        imagegrab = ModuleType("PIL.ImageGrab")
        imagegrab.grab = Mock(side_effect=RuntimeError("headless Windows session"))
        pil = ModuleType("PIL")
        pil.ImageGrab = imagegrab
        with patch("jarvis_mrb.mesh_windows_screen.platform.system", return_value="Windows"), \
             patch.dict(os.environ, {"JARVIS_MESH_WINDOWS_SCREEN_ENABLED": "1"}), \
             patch.dict(sys.modules, {"PIL": pil, "PIL.ImageGrab": imagegrab}):
            win.begin(120)
            with self.assertRaisesRegex(win.WindowsScreenUnavailable, "interactive session"):
                win.frame()


if __name__ == "__main__":
    unittest.main()
