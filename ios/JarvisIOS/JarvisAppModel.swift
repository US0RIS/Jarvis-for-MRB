import Foundation

@MainActor
final class JarvisAppModel: ObservableObject {
    @Published var commandText = ""
    @Published var lastResponse = ""
    @Published var isSending = false
    @Published var isListening = false
    @Published var connectionStatus = "Not checked"
    @Published var errorMessage: String?

    let settings = SettingsStore()
    let speechRecognizer = SpeechRecognizer()
    let speechSynthesizer = SpeechSynthesizer()
    let geofenceManager = GeofenceManager()
    let metaGlasses = MetaGlassesManager()

    private var wakeWordTask: Task<Void, Never>?

    init() {
        geofenceManager.onHomeArrival = { [weak self] in
            Task { @MainActor in
                await self?.sendEvent("home_arrival")
            }
        }
    }

    private var client: JarvisAPIClient {
        JarvisAPIClient(baseURL: settings.baseURL, apiToken: settings.apiToken)
    }

    func checkConnection() async {
        do {
            let healthy = try await client.health()
            connectionStatus = healthy ? "Connected" : "Server unavailable"
        } catch {
            connectionStatus = "Connection failed"
            errorMessage = error.localizedDescription
        }
    }

    func sendCurrentCommand() async {
        let text = commandText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        commandText = ""
        await sendCommand(text)
    }

    func sendCommand(_ text: String) async {
        guard !isSending else { return }
        isSending = true
        defer { isSending = false }
        do {
            let response = try await client.command(text)
            lastResponse = response.message
            if settings.speakResponses && !response.message.isEmpty {
                speechSynthesizer.speak(response.message)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func sendEvent(_ name: String) async {
        do {
            let response = try await client.event(name)
            lastResponse = response.message
            if settings.speakResponses && !response.message.isEmpty {
                speechSynthesizer.speak(response.message)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func togglePushToTalk() async {
        if isListening {
            stopListeningAndSend()
            return
        }
        do {
            try await speechRecognizer.requestPermissions()
            speechRecognizer.startListening()
            isListening = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func stopListeningAndSend() {
        let text = speechRecognizer.stopListening().trimmingCharacters(in: .whitespacesAndNewlines)
        isListening = false
        guard !text.isEmpty else { return }
        Task { await sendCommand(text) }
    }

    func configureHomeGeofence() {
        geofenceManager.configureHome(
            latitude: settings.homeLatitude,
            longitude: settings.homeLongitude,
            radius: settings.homeRadius
        )
    }

    func startWakeWordMode() async {
        stopWakeWordMode()
        do {
            try await speechRecognizer.requestPermissions()
            speechRecognizer.startListening()
            isListening = true
        } catch {
            errorMessage = error.localizedDescription
            return
        }

        wakeWordTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(250))
                guard let self else { return }
                let transcript = self.speechRecognizer.transcript
                if let command = Self.commandAfterWakeWord(in: transcript) {
                    _ = self.speechRecognizer.stopListening()
                    self.isListening = false
                    await self.sendCommand(command)
                    if !Task.isCancelled {
                        self.speechRecognizer.startListening()
                        self.isListening = true
                    }
                }
            }
        }
    }

    func stopWakeWordMode() {
        wakeWordTask?.cancel()
        wakeWordTask = nil
        if isListening {
            _ = speechRecognizer.stopListening()
            isListening = false
        }
    }

    static func commandAfterWakeWord(in transcript: String) -> String? {
        let lowered = transcript.lowercased()
        guard let range = lowered.range(of: "jarvis") else { return nil }
        let suffix = transcript[range.upperBound...]
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
        return suffix.isEmpty ? nil : suffix
    }
}
