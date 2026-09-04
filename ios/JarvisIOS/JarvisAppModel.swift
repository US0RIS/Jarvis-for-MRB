import Foundation

@MainActor
final class JarvisAppModel: ObservableObject {
    @Published var commandText = ""
    @Published var lastResponse = ""
    @Published var isSending = false
    @Published var isListening = false
    @Published var connectionStatus = "Not checked"
    @Published var errorMessage: String?
    @Published private(set) var handsFreeEnabled = false
    @Published private(set) var voiceStatus = "Hands-free Jarvis is off"
    @Published private(set) var lastHeardCommand = ""

    let settings: SettingsStore
    let audioRouteManager: AudioRouteManager
    let speechRecognizer: SpeechRecognizer
    let speechSynthesizer: SpeechSynthesizer
    let geofenceManager: GeofenceManager
    let metaGlasses: MetaGlassesManager

    private var wakeWordTask: Task<Void, Never>?

    private enum VoicePhase {
        case waitingForWake
        case collectingAfterWake
        case awaitingFollowUp(deadline: Date)
    }

    init() {
        settings = SettingsStore()
        let audioRouteManager = AudioRouteManager()
        self.audioRouteManager = audioRouteManager
        speechRecognizer = SpeechRecognizer(audioRouteManager: audioRouteManager)
        speechSynthesizer = SpeechSynthesizer(audioRouteManager: audioRouteManager)
        geofenceManager = GeofenceManager()
        metaGlasses = MetaGlassesManager()

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
        await performCommand(text, fromHandsFree: false)
    }

    private func performCommand(_ text: String, fromHandsFree: Bool) async {
        guard !isSending else { return }
        isSending = true
        if fromHandsFree {
            voiceStatus = "Thinking…"
        }
        defer { isSending = false }

        do {
            let response = try await client.command(text)
            lastResponse = response.message
            if settings.speakResponses && !response.message.isEmpty {
                if fromHandsFree {
                    voiceStatus = "Speaking…"
                }
                await speechSynthesizer.speak(
                    response.message,
                    preferBluetooth: settings.preferBluetoothAudio
                )
            }
        } catch {
            errorMessage = error.localizedDescription
            if fromHandsFree {
                voiceStatus = "Command failed"
            }
        }
    }

    func sendEvent(_ name: String) async {
        do {
            let response = try await client.event(name)
            lastResponse = response.message
            if settings.speakResponses && !response.message.isEmpty {
                await speechSynthesizer.speak(
                    response.message,
                    preferBluetooth: settings.preferBluetoothAudio
                )
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func togglePushToTalk() async {
        guard !handsFreeEnabled else { return }

        if isListening {
            stopListeningAndSend()
            return
        }

        do {
            try await speechRecognizer.requestPermissions()
            try speechRecognizer.startListening(preferBluetooth: settings.preferBluetoothAudio)
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

    func setHandsFreeEnabled(_ enabled: Bool) async {
        if enabled {
            await startWakeWordMode()
        } else {
            stopWakeWordMode()
        }
    }

    func startWakeWordMode() async {
        stopWakeWordMode()
        do {
            try await speechRecognizer.requestPermissions()
        } catch {
            errorMessage = error.localizedDescription
            voiceStatus = "Microphone unavailable"
            return
        }

        handsFreeEnabled = true
        voiceStatus = "Listening for “Jarvis”…"
        wakeWordTask = Task { [weak self] in
            guard let self else { return }
            await self.runHandsFreeLoop()
        }
    }

    func stopWakeWordMode() {
        wakeWordTask?.cancel()
        wakeWordTask = nil
        handsFreeEnabled = false
        speechSynthesizer.stopSpeaking()
        if isListening || speechRecognizer.isActive {
            _ = speechRecognizer.stopListening()
        }
        isListening = false
        voiceStatus = "Hands-free Jarvis is off"
    }

    private func runHandsFreeLoop() async {
        var phase: VoicePhase = .waitingForWake
        var lastTranscript = ""
        var lastTranscriptChange = Date()

        guard await restartVoiceRecognition() else { return }

        while !Task.isCancelled && handsFreeEnabled {
            try? await Task.sleep(for: .milliseconds(120))
            guard !Task.isCancelled && handsFreeEnabled else { return }

            let now = Date()
            let transcript = speechRecognizer.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            if transcript != lastTranscript {
                lastTranscript = transcript
                lastTranscriptChange = now
            }
            let silence = now.timeIntervalSince(lastTranscriptChange)
            let recognitionEnded = !speechRecognizer.isActive

            switch phase {
            case .waitingForWake:
                if let command = Self.commandAfterWakeWord(in: transcript) {
                    phase = .collectingAfterWake
                    voiceStatus = "Listening for command…"
                    if (silence >= 0.9 || recognitionEnded), !command.isEmpty {
                        await submitHandsFreeCommand(command)
                        phase = .waitingForWake
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }
                } else if Self.containsWakeWord(transcript) && (silence >= 0.65 || recognitionEnded) {
                    await promptForFollowUp()
                    phase = .awaitingFollowUp(deadline: Date().addingTimeInterval(8))
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

            case .collectingAfterWake:
                let command = Self.commandAfterWakeWord(in: transcript) ?? ""
                if !command.isEmpty && (silence >= 0.9 || recognitionEnded) {
                    await submitHandsFreeCommand(command)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

            case .awaitingFollowUp(let deadline):
                if !transcript.isEmpty && (silence >= 0.9 || recognitionEnded) {
                    await submitHandsFreeCommand(transcript)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }
                if now >= deadline {
                    phase = .waitingForWake
                    voiceStatus = "Listening for “Jarvis”…"
                    _ = speechRecognizer.stopListening()
                    isListening = false
                    _ = await restartVoiceRecognition()
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }
            }

            if recognitionEnded {
                let restarted = await restartVoiceRecognition()
                if restarted {
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                } else {
                    try? await Task.sleep(for: .seconds(1))
                }
            }
        }
    }

    private func promptForFollowUp() async {
        _ = speechRecognizer.stopListening()
        isListening = false
        voiceStatus = "Listening for command…"
        await speechSynthesizer.speak("Yes?", preferBluetooth: settings.preferBluetoothAudio)
        _ = await restartVoiceRecognition()
    }

    private func submitHandsFreeCommand(_ rawCommand: String) async {
        let command = rawCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !command.isEmpty else { return }

        _ = speechRecognizer.stopListening()
        isListening = false
        lastHeardCommand = command
        await performCommand(command, fromHandsFree: true)

        guard handsFreeEnabled && !Task.isCancelled else { return }
        voiceStatus = "Listening for “Jarvis”…"
        _ = await restartVoiceRecognition()
    }

    @discardableResult
    private func restartVoiceRecognition() async -> Bool {
        guard handsFreeEnabled && !Task.isCancelled else { return false }
        if speechRecognizer.isActive {
            isListening = true
            return true
        }

        do {
            try speechRecognizer.startListening(preferBluetooth: settings.preferBluetoothAudio)
            isListening = true
            audioRouteManager.refresh()
            return true
        } catch {
            isListening = false
            voiceStatus = "Waiting for microphone…"
            return false
        }
    }

    static func containsWakeWord(_ transcript: String) -> Bool {
        transcript.range(of: "jarvis", options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }

    static func commandAfterWakeWord(in transcript: String) -> String? {
        guard let range = transcript.range(of: "jarvis", options: [.caseInsensitive, .diacriticInsensitive]) else {
            return nil
        }
        let suffix = transcript[range.upperBound...]
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
        return suffix.isEmpty ? nil : suffix
    }
}
