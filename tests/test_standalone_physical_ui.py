from __future__ import annotations

import re
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


class StandalonePhysicalExperienceTests(unittest.TestCase):
    def test_physical_tab_is_first_class_not_hidden_in_future_glasses(self) -> None:
        app = (_ROOT / "ios/JarvisIOS/JarvisIOSApp.swift").read_text(encoding="utf-8")
        self.assertIn("JarvisPhysicalHubView()", app)
        self.assertIn('Label("Physical", systemImage:', app)
        self.assertNotIn('Label("Glasses", systemImage:', app)

    def test_public_camera_voice_path_precedes_generic_frontend(self) -> None:
        model = (_ROOT / "ios/JarvisIOS/JarvisAppModel.swift").read_text(encoding="utf-8")
        route = model[model.index("private func performCommand("):]
        self.assertLess(route.index("if Self.isPublicCameraIntent(text) {"), route.index("if let frontendCommandHandler,"))
        self.assertIn("searchNearbyPublicCameras()", route)
        self.assertIn("fromHandsFree: fromHandsFree", route)
        self.assertIn("iPhone location + official public camera discovery", route)

    def test_conditions_and_facilities_voice_routes_precede_generic_frontend(self) -> None:
        model = (_ROOT / "ios/JarvisIOS/JarvisAppModel.swift").read_text(encoding="utf-8")
        route = model[model.index("private func performCommand("):]
        for handler in ("isPhysicalConditionsIntent", "isNearbyFacilitiesIntent"):
            self.assertLess(route.index("if Self." + handler + "(text) {"), route.index("if let frontendCommandHandler,"))
        client = (_ROOT / "ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")
        self.assertIn('path: "physical/conditions"', client)
        self.assertIn('path: "physical/facilities"', client)
        physical = (_ROOT / "ios/JarvisIOS/JarvisPhysicalControlView.swift").read_text(encoding="utf-8")
        self.assertIn("JarvisPhysicalConditionsView()", physical)
        self.assertIn("JarvisPublicFacilitiesView()", physical)

    def test_home_control_and_camera_view_are_not_duplicate_swift_structs(self) -> None:
        home = (_ROOT / "ios/JarvisIOS/HomeEnvironmentController.swift").read_text(encoding="utf-8")
        camera = (_ROOT / "ios/JarvisIOS/JarvisPhysicalControlView.swift").read_text(encoding="utf-8")
        self.assertIn("struct AppleHomeControlView: View", home)
        self.assertNotIn("struct JarvisPhysicalControlView: View", home)
        self.assertIn("struct JarvisPhysicalHubView: View", camera)
        self.assertIn("struct JarvisPhysicalControlView: View", camera)
        self.assertIn("AppleHomeControlView()", camera)

    def test_project_references_for_home_and_cameras_are_unique(self) -> None:
        project = (_ROOT / "ios/JarvisIOS.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
        refs = re.findall(
            r"(?m)^\s*([A-F0-9]{24}) /\* (HomeEnvironmentController|JarvisPhysicalControlView)\.swift \*/"
            r" = \{isa = PBXFileReference",
            project,
        )
        self.assertEqual(len(refs), 2, refs)
        self.assertEqual(len({identifier for identifier, _ in refs}), 2)


if __name__ == "__main__":
    unittest.main()
