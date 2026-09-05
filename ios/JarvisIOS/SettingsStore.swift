import Foundation

@MainActor
final class SettingsStore: ObservableObject {
    @Published var baseURL: String { didSet { defaults.set(baseURL, forKey: "jarvis.baseURL") } }
    @Published var fallbackBaseURL: String { didSet { defaults.set(fallbackBaseURL, forKey: "jarvis.fallbackBaseURL") } }
    @Published var apiToken: String { didSet { KeychainStore.save(apiToken, account: "jarvis.apiToken") } }
    @Published var homeLatitude: Double { didSet { defaults.set(homeLatitude, forKey: "jarvis.homeLatitude") } }
    @Published var homeLongitude: Double { didSet { defaults.set(homeLongitude, forKey: "jarvis.homeLongitude") } }
    @Published var homeRadius: Double { didSet { defaults.set(homeRadius, forKey: "jarvis.homeRadius") } }
    @Published var speakResponses: Bool { didSet { defaults.set(speakResponses, forKey: "jarvis.speakResponses") } }
    @Published var preferBluetoothAudio: Bool { didSet { defaults.set(preferBluetoothAudio, forKey: "jarvis.preferBluetoothAudio") } }
    @Published var passiveVisionEnabled: Bool { didSet { defaults.set(passiveVisionEnabled, forKey: "jarvis.passiveVisionEnabled") } }
    @Published var adaptiveBandwidthEnabled: Bool { didSet { defaults.set(adaptiveBandwidthEnabled, forKey: "jarvis.adaptiveBandwidthEnabled") } }
    @Published var ambientCuesEnabled: Bool { didSet { defaults.set(ambientCuesEnabled, forKey: "jarvis.ambientCuesEnabled") } }
    @Published var proactiveAnnouncements: Bool { didSet { defaults.set(proactiveAnnouncements, forKey: "jarvis.proactiveAnnouncements") } }
    @Published var proactiveThreshold: String { didSet { defaults.set(proactiveThreshold, forKey: "jarvis.proactiveThreshold") } }
    @Published var adaptiveWhisperEnabled: Bool { didSet { defaults.set(adaptiveWhisperEnabled, forKey: "jarvis.adaptiveWhisperEnabled") } }
    @Published var whisperThresholdDBFS: Double { didSet { defaults.set(whisperThresholdDBFS, forKey: "jarvis.whisperThresholdDBFS") } }
    @Published var subvocalModeEnabled: Bool { didSet { defaults.set(subvocalModeEnabled, forKey: "jarvis.subvocalModeEnabled") } }
    @Published var geofencedProfilesEnabled: Bool { didSet { defaults.set(geofencedProfilesEnabled, forKey: "jarvis.geofencedProfilesEnabled") } }
    @Published var healthContextEnabled: Bool { didSet { defaults.set(healthContextEnabled, forKey: "jarvis.healthContextEnabled") } }
    @Published var smartAudioDampingEnabled: Bool { didSet { defaults.set(smartAudioDampingEnabled, forKey: "jarvis.smartAudioDampingEnabled") } }
    @Published var dailyJournalEnabled: Bool { didSet { defaults.set(dailyJournalEnabled, forKey: "jarvis.dailyJournalEnabled") } }
    @Published var projectFocus: String { didSet { defaults.set(projectFocus, forKey: "jarvis.projectFocus") } }

    // Frontend-only capabilities. These remain useful even when the PC backend
    // cannot be changed: on-device Vision OCR/barcodes, a RAM-only visual cache,
    // connection telemetry, offline command staging, local sensor context and
    // local command aliases.
    @Published var localVisualHistoryEnabled: Bool { didSet { defaults.set(localVisualHistoryEnabled, forKey: "jarvis.localVisualHistoryEnabled") } }
    @Published var localFastPerceptionEnabled: Bool { didSet { defaults.set(localFastPerceptionEnabled, forKey: "jarvis.localFastPerceptionEnabled") } }
    @Published var offlineQueueEnabled: Bool { didSet { defaults.set(offlineQueueEnabled, forKey: "jarvis.offlineQueueEnabled") } }
    @Published var localCommandAliasesEnabled: Bool { didSet { defaults.set(localCommandAliasesEnabled, forKey: "jarvis.localCommandAliasesEnabled") } }
    @Published var localSensorContextEnabled: Bool { didSet { defaults.set(localSensorContextEnabled, forKey: "jarvis.localSensorContextEnabled") } }
    @Published var frontendDiagnosticsEnabled: Bool { didSet { defaults.set(frontendDiagnosticsEnabled, forKey: "jarvis.frontendDiagnosticsEnabled") } }
    @Published var offlineMeetingCaptureEnabled: Bool { didSet { defaults.set(offlineMeetingCaptureEnabled, forKey: "jarvis.offlineMeetingCaptureEnabled") } }
    @Published var adaptiveCueVolumeEnabled: Bool { didSet { defaults.set(adaptiveCueVolumeEnabled, forKey: "jarvis.adaptiveCueVolumeEnabled") } }
    @Published var cueVolume: Double { didSet { defaults.set(cueVolume, forKey: "jarvis.cueVolume") } }

    // Closed-set known-people recognition is explicit opt-in. The iPhone only
    // compares a visible face against profiles that the user deliberately enrolled.
    @Published var knownPeopleRecognitionEnabled: Bool { didSet { defaults.set(knownPeopleRecognitionEnabled, forKey: "jarvis.knownPeopleRecognitionEnabled") } }
    @Published var knownPeopleContextInjectionEnabled: Bool { didSet { defaults.set(knownPeopleContextInjectionEnabled, forKey: "jarvis.knownPeopleContextInjectionEnabled") } }
    @Published var knownPeopleTolerance: Double { didSet { defaults.set(knownPeopleTolerance, forKey: "jarvis.knownPeopleTolerance") } }

    let conversationSessionID: String

    private let defaults: UserDefaults

    init() {
        let defaults = UserDefaults.standard
        self.defaults = defaults

        if let savedSessionID = defaults.string(forKey: "jarvis.conversationSessionID"), !savedSessionID.isEmpty {
            conversationSessionID = savedSessionID
        } else {
            let newSessionID = UUID().uuidString
            defaults.set(newSessionID, forKey: "jarvis.conversationSessionID")
            conversationSessionID = newSessionID
        }

        baseURL = defaults.string(forKey: "jarvis.baseURL") ?? "http://127.0.0.1:8765"
        fallbackBaseURL = defaults.string(forKey: "jarvis.fallbackBaseURL") ?? ""
        apiToken = KeychainStore.read("jarvis.apiToken") ?? ""
        homeLatitude = defaults.object(forKey: "jarvis.homeLatitude") as? Double ?? 0
        homeLongitude = defaults.object(forKey: "jarvis.homeLongitude") as? Double ?? 0
        homeRadius = defaults.object(forKey: "jarvis.homeRadius") as? Double ?? 150
        speakResponses = defaults.object(forKey: "jarvis.speakResponses") as? Bool ?? true
        preferBluetoothAudio = defaults.object(forKey: "jarvis.preferBluetoothAudio") as? Bool ?? true
        passiveVisionEnabled = defaults.object(forKey: "jarvis.passiveVisionEnabled") as? Bool ?? false
        adaptiveBandwidthEnabled = defaults.object(forKey: "jarvis.adaptiveBandwidthEnabled") as? Bool ?? true
        ambientCuesEnabled = defaults.object(forKey: "jarvis.ambientCuesEnabled") as? Bool ?? true
        proactiveAnnouncements = defaults.object(forKey: "jarvis.proactiveAnnouncements") as? Bool ?? true
        proactiveThreshold = defaults.string(forKey: "jarvis.proactiveThreshold") ?? "warning"
        adaptiveWhisperEnabled = defaults.object(forKey: "jarvis.adaptiveWhisperEnabled") as? Bool ?? true
        whisperThresholdDBFS = defaults.object(forKey: "jarvis.whisperThresholdDBFS") as? Double ?? -42.0
        subvocalModeEnabled = defaults.object(forKey: "jarvis.subvocalModeEnabled") as? Bool ?? false
        geofencedProfilesEnabled = defaults.object(forKey: "jarvis.geofencedProfilesEnabled") as? Bool ?? true
        healthContextEnabled = defaults.object(forKey: "jarvis.healthContextEnabled") as? Bool ?? false
        smartAudioDampingEnabled = defaults.object(forKey: "jarvis.smartAudioDampingEnabled") as? Bool ?? true
        dailyJournalEnabled = defaults.object(forKey: "jarvis.dailyJournalEnabled") as? Bool ?? false
        projectFocus = defaults.string(forKey: "jarvis.projectFocus") ?? "Jarvis"

        localVisualHistoryEnabled = defaults.object(forKey: "jarvis.localVisualHistoryEnabled") as? Bool ?? true
        localFastPerceptionEnabled = defaults.object(forKey: "jarvis.localFastPerceptionEnabled") as? Bool ?? false
        offlineQueueEnabled = defaults.object(forKey: "jarvis.offlineQueueEnabled") as? Bool ?? true
        localCommandAliasesEnabled = defaults.object(forKey: "jarvis.localCommandAliasesEnabled") as? Bool ?? true
        localSensorContextEnabled = defaults.object(forKey: "jarvis.localSensorContextEnabled") as? Bool ?? false
        frontendDiagnosticsEnabled = defaults.object(forKey: "jarvis.frontendDiagnosticsEnabled") as? Bool ?? true
        offlineMeetingCaptureEnabled = defaults.object(forKey: "jarvis.offlineMeetingCaptureEnabled") as? Bool ?? true
        adaptiveCueVolumeEnabled = defaults.object(forKey: "jarvis.adaptiveCueVolumeEnabled") as? Bool ?? true
        cueVolume = defaults.object(forKey: "jarvis.cueVolume") as? Double ?? 1.0

        knownPeopleRecognitionEnabled = defaults.object(forKey: "jarvis.knownPeopleRecognitionEnabled") as? Bool ?? false
        knownPeopleContextInjectionEnabled = defaults.object(forKey: "jarvis.knownPeopleContextInjectionEnabled") as? Bool ?? true
        knownPeopleTolerance = defaults.object(forKey: "jarvis.knownPeopleTolerance") as? Double ?? 1.65
    }
}
