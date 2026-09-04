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
    @Published var ambientCuesEnabled: Bool { didSet { defaults.set(ambientCuesEnabled, forKey: "jarvis.ambientCuesEnabled") } }
    @Published var proactiveAnnouncements: Bool { didSet { defaults.set(proactiveAnnouncements, forKey: "jarvis.proactiveAnnouncements") } }
    @Published var projectFocus: String { didSet { defaults.set(projectFocus, forKey: "jarvis.projectFocus") } }

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
        ambientCuesEnabled = defaults.object(forKey: "jarvis.ambientCuesEnabled") as? Bool ?? true
        proactiveAnnouncements = defaults.object(forKey: "jarvis.proactiveAnnouncements") as? Bool ?? true
        projectFocus = defaults.string(forKey: "jarvis.projectFocus") ?? "Jarvis"
    }
}
