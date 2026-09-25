from __future__ import annotations

import ast
from pathlib import Path
import unittest

_ROOT = Path(__file__).resolve().parents[1]


class CounterfactualGuardianContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.swift = (_ROOT / "ios/JarvisIOS/CounterfactualGuardian.swift").read_text(encoding="utf-8")
        self.api = (_ROOT / "ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")
        self.app = (_ROOT / "ios/JarvisIOS/JarvisIOSApp.swift").read_text(encoding="utf-8")
        self.model = (_ROOT / "ios/JarvisIOS/JarvisAppModel.swift").read_text(encoding="utf-8")
        self.settings = (_ROOT / "ios/JarvisIOS/SettingsStore.swift").read_text(encoding="utf-8")
        self.service = (_ROOT / "jarvis_mrb/service.py").read_text(encoding="utf-8")

    def test_calendar_endpoint_is_read_only_authenticated_bounded_and_does_not_request_gps(self) -> None:
        module = ast.parse(self.service)
        methods = [
            node for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "guardian_calendar_expectations"
        ]
        self.assertEqual(len(methods), 1)
        node = methods[0]
        code = ast.get_source_segment(self.service, node)
        self.assertIn('@app.get("/guardian/calendar")', self.service)
        self.assertIn("_check_auth(authorization)", code)
        self.assertIn('response.headers["Cache-Control"] = "private, no-store"', code)
        self.assertIn('query_calendar_events(direction="future", days=1, limit=12)', code)
        self.assertIn('raise HTTPException(status_code=503', code)
        self.assertIn('if "T" not in start', code)
        for forbidden in ('latitude', 'longitude', 'gps_coordinates', 'insert(', 'execute_tool'):
            self.assertNotIn(forbidden, code.lower())

    def test_opt_in_phone_lifecycle_and_privacy_revocation(self) -> None:
        project = (_ROOT / "ios/JarvisIOS.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
        power = (_ROOT / "ios/JarvisIOS/LocalPowerFeatures.swift").read_text(encoding="utf-8")
        physical = (_ROOT / "ios/JarvisIOS/JarvisPhysicalControlView.swift").read_text(encoding="utf-8")
        self.assertIn(
            'guardianEnabled = defaults.object(forKey: "jarvis.guardianEnabled") as? Bool ?? false',
            self.settings
        )
        self.assertIn("guardianEnabled: appModel.settings.guardianEnabled", power)
        self.assertIn("appModel.settings.guardianEnabled = false", power)
        self.assertIn("appModel.settings.guardianEnabled = snapshot.guardianEnabled", power)
        self.assertIn("model.guardian.attach(frontend: frontend)", self.app)
        self.assertIn("appModel.guardian.start()", self.app)
        self.assertIn(".environmentObject(appModel.guardian)", self.app)
        self.assertIn("lazy var guardian = CounterfactualGuardianController(appModel: self)", self.model)
        self.assertIn("if Self.isGuardianIntent(text)", self.model)
        self.assertIn('"will i make my next meeting"', self.model)
        self.assertIn("await guardian.checkNow(manual: true)", self.model)
        self.assertIn("if appModel.settings.guardianEnabled && !manual {", self.swift)
        self.assertIn("CounterfactualGuardian.swift in Sources", project)
        self.assertIn("self.grants.removeAll()", self.swift)
        self.assertIn('status = "Guardian is off. Enable it before checking', self.swift)
        self.assertIn("!appModel.settings.guardianEnabled", self.swift)
        self.assertIn('GroupBox("JARVIS • Counterfactual Guardian")', physical)

    def test_stale_unknown_ambiguous_or_virtual_evidence_never_makes_a_confident_risk(self) -> None:
        sensors = (_ROOT / "ios/JarvisIOS/FrontendIntelligence.swift").read_text(encoding="utf-8")
        self.assertIn("horizontalAccuracyMeters = current.horizontalAccuracy", sensors)
        self.assertIn("lastLocationAt = current.timestamp", sensors)
        for required in (
            "guard (240...7200).contains(until)",
            "drivingSeconds.isFinite",
            "distanceMeters > 200",
            "(0...75).contains(locationAge)",
            "(0...150).contains(horizontalAccuracy)",
            "Apple MapKit driving route checked",
            'guard !Self.virtualLocation(location)',
            "return exact.count == 1 ? exact.first : nil",
            "freshLocation()",
            'status = "Unknown — Jarvis Calendar is unavailable.',
            "No departure prediction made.",
            "distanceMeters: actualDistance",
            "route.expectedTravelTime",
            "MKDirections(request: request).calculate()",
        ):
            self.assertIn(required, self.swift)
        self.assertIn('guard raw.contains("T")', self.swift)
        self.assertNotIn("Moondream", self.swift)
        self.assertNotIn("sendFrame(", self.swift)

    def test_proactive_navigation_cannot_infer_authority(self) -> None:
        for required in (
            "private struct GuardianNavigationGrant: Codable",
            "guard appModel.settings.guardianEnabled,",
            "grant.calendarID == candidate.calendarID",
            "grant.location == candidate.calendarLocation",
            "grant.startsAt == candidate.startsAt",
            "grant.expiresAt > Date()",
            "grants.removeValue(forKey: id)",
            "persistGrants()",
            "if automatically {",
            "guard appModel.settings.guardianEnabled, hasGrant(for: candidate)",
            "freshLocation() != nil",
            "UIApplication.shared.applicationState == .active",
            "destination.openInMaps(launchOptions:",
            "Route start and arrival have not been independently verified.",
            "KeychainStore.saveData(data, account: Self.receiptsKey)",
            "func revokeNavigation(for id: String)",
            "func dismiss(_ id: String)",
            "func clearHistory()",
        ):
            self.assertIn(required, self.swift)
        self.assertLess(
            self.swift.index("grants.removeValue(forKey: id)", self.swift.index("if automatically {")),
            self.swift.index("destination.openInMaps(launchOptions:")
        )

    def test_draft_is_local_and_messages_cannot_be_sent_by_inference(self) -> None:
        self.assertIn("func stageETA(for id: String)", self.swift)
        self.assertIn("func copyDraft()", self.swift)
        self.assertIn("UIPasteboard.general.string = stagedMessage", self.swift)
        self.assertIn("Nothing was sent.", self.swift)
        for forbidden in ("sendEmail(", "sendMessage(", "MFMessageCompose", "gmail.send",
                          "unrestricted actuator", "healthContext.heartRateBPM"):
            self.assertNotIn(forbidden, self.swift)
        self.assertIn('containsPrivateData: true', (_ROOT / "ios/JarvisIOS/MemoMindBridge.swift").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
