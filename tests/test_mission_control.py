from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class MissionControlContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mission = (ROOT / "ios/JarvisIOS/MissionControl.swift").read_text()
        self.app = (ROOT / "ios/JarvisIOS/JarvisIOSApp.swift").read_text()
        self.model = (ROOT / "ios/JarvisIOS/JarvisAppModel.swift").read_text()
        self.settings = (ROOT / "ios/JarvisIOS/SettingsStore.swift").read_text()
        self.power = (ROOT / "ios/JarvisIOS/LocalPowerFeatures.swift").read_text()
        self.api = (ROOT / "ios/JarvisIOS/JarvisAPIClient.swift").read_text()

    def test_source_compiles_in_phone_with_first_class_mission_board(self):
        pbx = (ROOT / "ios/JarvisIOS.xcodeproj/project.pbxproj").read_text()
        physical = (ROOT / "ios/JarvisIOS/JarvisPhysicalControlView.swift").read_text()
        self.assertIn('MissionControl.swift in Sources', pbx)
        self.assertIn('GroupBox("JARVIS • Mission Control")', physical)
        self.assertIn('JarvisMissionBoard()', physical)
        self.assertIn('model.missionControl.attach(frontend: frontend)', self.app)
        self.assertIn('appModel.missionControl.start()', self.app)
        self.assertIn('.environmentObject(appModel.missionControl)', self.app)
        self.assertIn('Label("Missions", systemImage: "target")', self.app)
        self.assertIn('lazy var missionControl = JarvisMissionControl(appModel: self)', self.model)
        self.assertIn('if let missionAction = Self.missionIntent(text)', self.model)
        self.assertIn('await missionControl.enrollNextAppointment()', self.model)
        self.assertIn('return "status"', self.model)

    def test_separate_privacy_consent_and_device_only_evidence(self):
        self.assertIn('missionControlEnabled = defaults.object(forKey: "jarvis.missionControlEnabled") as? Bool ?? false', self.settings)
        self.assertIn('appModel.settings.missionControlEnabled = false', self.power)
        self.assertIn('appModel.missionControl.clearNavigationGrants()', self.power)
        self.assertIn('missionControlEnabled: appModel.settings.missionControlEnabled', self.power)
        self.assertIn('missionControlEnabled = snapshot.missionControlEnabled', self.power)
        for value in (
            'appModel.settings.guardianEnabled', 'UIApplication.shared.applicationState == .active',
            'KeychainStore.saveData(data, account: Self.storeKey)',
            'accurateLocation()', '(0...45).contains(Date().timeIntervalSince(observed))',
            '(0...30).contains(accuracy)', 'No raw GPS history',
            'missions.filter({ $0.eligibleForReview }).count < 5',
        ):
            if value == 'No raw GPS history':
                self.assertIn('No raw GPS history', (ROOT / 'MISSION_CONTROL.md').read_text())
            else:
                self.assertIn(value, self.mission)
        self.assertNotIn('sendEnvironment(', self.mission)
        self.assertNotIn('gmail.send(', self.mission)
        self.assertNotIn('MFMessageCompose', self.mission)

    def test_exact_event_source_routes_and_arrival_verification(self):
        for value in (
            '$0.id == event.id && $0.start == event.start',
            '$0.location == event.location',
            '$0.id == mission.calendarID',
            'exact.location != mission.literalDestination',
            'mission.phase = .reviewRequired',
            'grants.removeValue(forKey: mission.id)',
            'MissionPhase', 'missedUnverified', 'Observation window expired without verified arrival;',
            'MKLocalSearch(request: request).start()', 'MKDirections(request: request).calculate()',
            'route.expectedTravelTime', 'remaining - route.expectedTravelTime - 300',
            'phone.timestamp.timeIntervalSince(first.firstObservedAt) >= 8',
            '.achievedOnTime : .arrivedLate',
            'No arrival evidence.',
        ):
            self.assertIn(value, self.mission)
        self.assertIn('return matches.count == 1 ? matches.first : nil', self.mission)
        self.assertIn('mission.status = "Unknown: no fresh high-accuracy phone fix;', self.mission)
        self.assertIn('route estimates', (ROOT / "MISSION_CONTROL.md").read_text())

    def test_narrow_automatic_intervention_and_receipt_are_not_faked(self):
        for value in (
            'private var grants: [UUID:', 'RAM-only',
            'grant.calendarID == mission.calendarID',
            'grant.start == mission.startsAt',
            'grant.destination == mission.literalDestination',
            'grant.expires > Date()',
            'grants.removeValue(forKey: id)',
            'if openDirections(id, automatically: true) { return }',
            '!appModel.isCurrentlyNavigating',
            'frontend?.isMeetingActive != true',
            'frontend?.sensors.activity != "Driving"',
            'let accepted = destination.openInMaps(launchOptions:',
            'Travel/arrival NOT verified.',
            'UIPasteboard.general.string = stagedDraft',
        ):
            self.assertIn(value, self.mission)
        self.assertLess(
            self.mission.index('grants.removeValue(forKey: id)',
                               self.mission.index('func openDirections(')),
            self.mission.index('let accepted = destination.openInMaps(')
        )

    def test_tool_graph_is_real_read_only_contract_not_authority(self):
        module = __import__('jarvis_mrb.mission_affordances', fromlist=['catalog'])
        result = module.catalog()
        self.assertTrue(result['catalog_is_read_only'])
        self.assertFalse(result['model_may_add_tools'])
        self.assertFalse(result['phone_local_permissions_included'])
        self.assertEqual(len(result['capabilities']), 11)
        for cap in result['capabilities']:
            self.assertFalse(cap['execution_authorized_by_catalog'])
            self.assertFalse(cap['actual_external_outcome_verified'])
            self.assertFalse(cap['live_connection_verified'])
            self.assertIn(cap['effect'], {'read_only', 'local_write', 'external_write'})
        source = (ROOT / 'jarvis_mrb/service.py').read_text()
        self.assertIn('@app.get("/missions/affordances")', source)
        self.assertIn('def mission_affordance_catalog(', source)
        self.assertIn('_check_auth(authorization)', source)
        self.assertIn('path: "missions/affordances"', self.api)
        self.assertIn('MissionAffordanceCatalog', self.api)


if __name__ == '__main__':
    unittest.main()
