from __future__ import annotations

import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


class AmbientFrontendContractTests(unittest.TestCase):
    def test_opt_in_defaults_off_and_privacy_mode_revokes_consent(self) -> None:
        settings = (_ROOT / "ios/JarvisIOS/SettingsStore.swift").read_text()
        local = (_ROOT / "ios/JarvisIOS/LocalPowerFeatures.swift").read_text()
        for setting in ("sensorOpportunitiesEnabled", "weatherContextEnabled"):
            self.assertIn(f'{setting} = defaults.object(forKey: "jarvis.{setting}") as? Bool ?? false', settings)
            self.assertIn(f"appModel.settings.{setting} = false", local)
            self.assertIn(f"appModel.settings.{setting} = snapshot.{setting}", local)

    def test_presence_uses_existing_microphone_and_separately_timestamped_gps(self) -> None:
        presence = (_ROOT / "ios/JarvisIOS/PersistentPresenceController.swift").read_text()
        sensors = (_ROOT / "ios/JarvisIOS/FrontendIntelligence.swift").read_text()
        sound = (_ROOT / "ios/JarvisIOS/LocalAudioMemory.swift").read_text()
        app = (_ROOT / "ios/JarvisIOS/JarvisIOSApp.swift").read_text()
        self.assertIn("presence.attach(frontend: frontend)", app)
        self.assertIn("lastLocationAt = current.timestamp", sensors)
        self.assertIn("lastMotionAt = Date()", sensors)
        self.assertIn("LocalSoundClassifier.shared.latestEvent(maxAge: 8)", presence)
        self.assertIn("appModel.settings.soundRecognitionEnabled", presence)
        self.assertIn('environment["sensor_snapshot"] = opportunity', presence)
        self.assertIn('"enabled": appModel.settings.sensorOpportunitiesEnabled', presence)
        self.assertIn('snapshot.get("enabled")', (_ROOT / "jarvis_mrb/sensor_opportunities.py").read_text())
        self.assertIn("UserDefaults.standard.object(forKey: \"jarvis.soundRecognitionEnabled\")", sound)
        self.assertNotIn("sendFrame(", presence[presence.index("private func sendEnvironmentState"):presence.index("private func thresholdRank")])

    def test_physical_actions_are_individually_preapproved_and_verified(self) -> None:
        home = (_ROOT / "ios/JarvisIOS/HomeEnvironmentController.swift").read_text()
        presence = (_ROOT / "ios/JarvisIOS/PersistentPresenceController.swift").read_text()
        self.assertIn("setArrivalControl(_ id: UUID, enabled: Bool)", home)
        self.assertIn("guard discovered, lights.contains(where: { $0.id == id })", home)
        self.assertIn("guard now.timeIntervalSince(lastArrivalRun) >= 300", home)
        self.assertIn("lights.filter({ arrivalLightIDs.contains($0.id) }).prefix(5)", home)
        self.assertIn("await setLight(light.id, on: true)", home)
        self.assertIn("characteristic.readValue", home)
        self.assertIn("self.lastKnownHomeState == false && isHome", presence)
        self.assertIn("settings.sensorOpportunitiesEnabled", presence)
        self.assertIn("settings.localSensorContextEnabled", presence)
        self.assertIn("settings.geofencedProfilesEnabled", presence)
        self.assertIn("runPreapprovedArrivalActions()", presence)
        self.assertNotIn("runPreapprovedArrivalActions()", (_ROOT / "jarvis_mrb/sensor_opportunities.py").read_text())

    def test_backend_transient_sensor_state_never_mirrors_raw_snapshot(self) -> None:
        environment = (_ROOT / "jarvis_mrb/environment_state.py").read_text()
        service = (_ROOT / "jarvis_mrb/service.py").read_text()
        self.assertIn('sensor_snapshot = working_patch.pop("sensor_snapshot", None)', environment)
        self.assertIn("ingest(sensor_snapshot)", environment)
        self.assertIn('@app.get("/ambient/status")', service)
        self.assertIn("_check_auth(authorization)", service[service.index('@app.get("/ambient/status")'):service.index('@app.post("/external/watch/create")')])


if __name__ == "__main__":
    unittest.main()
