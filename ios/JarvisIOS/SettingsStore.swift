import Foundation

@MainActor
final class SettingsStore: ObservableObject {
    @Published var baseURL: String { didSet { defaults.set(baseURL, forKey: "jarvis.baseURL") } }
    @Published var apiToken: String { didSet { KeychainStore.save(apiToken, account: "jarvis.apiToken") } }
    @Published var homeLatitude: Double { didSet { defaults.set(homeLatitude, forKey: "jarvis.homeLatitude") } }
    @Published var homeLongitude: Double { didSet { defaults.set(homeLongitude, forKey: "jarvis.homeLongitude") } }
    @Published var homeRadius: Double { didSet { defaults.set(homeRadius, forKey: "jarvis.homeRadius") } }
    @Published var speakResponses: Bool { didSet { defaults.set(speakResponses, forKey: "jarvis.speakResponses") } }

    private let defaults = UserDefaults.standard

    init() {
        baseURL = defaults.string(forKey: "jarvis.baseURL") ?? "http://127.0.0.1:8765"
        apiToken = KeychainStore.read("jarvis.apiToken") ?? ""
        homeLatitude = defaults.object(forKey: "jarvis.homeLatitude") as? Double ?? 0
        homeLongitude = defaults.object(forKey: "jarvis.homeLongitude") as? Double ?? 0
        homeRadius = defaults.object(forKey: "jarvis.homeRadius") as? Double ?? 150
        speakResponses = defaults.object(forKey: "jarvis.speakResponses") as? Bool ?? true
    }
}
