"""Static wiring checks; physical iPhone capture requires separate device acceptance."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ios" / "JarvisIOS"


class ActionButtonVoiceWiringTests(unittest.TestCase):
    def test_shortcut_activates_capture(self):
        shortcuts = (ROOT / "JarvisShortcuts.swift").read_text(encoding="utf-8")
        frontend = (ROOT / "FrontendIntelligence.swift").read_text(encoding="utf-8")
        self.assertIn('static var openAppWhenRun = true', shortcuts)
        self.assertIn('FrontendActionMailbox.post("talk")', shortcuts)
        handling = frontend.split('case "talk":', 1)[1].split('case "scan":', 1)[0]
        self.assertIn('await appModel.activatePushToTalk()', handling)
        self.assertNotIn('togglePushToTalk()', handling)
        self.assertIn('roomListening.isActive', handling)

    def test_bounded_explicit_capture(self):
        model = (ROOT / "JarvisAppModel.swift").read_text(encoding="utf-8")
        self.assertIn('func activatePushToTalk() async', model)
        self.assertIn('guard !isListening && !speechRecognizer.isActive else { return }', model)
        self.assertIn('func cancelPushToTalk()', model)
        self.assertIn('audioRouteManager.releaseOneShotVoiceSession()', model)
        self.assertIn('now.timeIntervalSince(updated) >= 2.3', model)
        self.assertIn('(spoken ? 90 : 15)', model)
        app = (ROOT / "JarvisIOSApp.swift").read_text(encoding="utf-8")
        self.assertIn('if phase != .active && appModel.isListening && !appModel.handsFreeEnabled', app)

    def test_timestamp_reset(self):
        speech = (ROOT / "SpeechRecognizer.swift").read_text(encoding="utf-8")
        self.assertIn('lastRecognitionUpdate = nil', speech)


if __name__ == "__main__":
    unittest.main()
