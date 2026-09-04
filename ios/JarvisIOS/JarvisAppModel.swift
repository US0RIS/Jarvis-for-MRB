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
    private var confirmationFollowUpDeadline: Date?
    private var conversationalFollowUpDeadline: Date?

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
        JarvisAPIClient(
            baseURL: settings.baseURL,
            apiToken: settings.apiToken,
            sessionID: settings.conversationSessionID
        )
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
        lastResponse = ""
        if fromHandsFree {
            voiceStatus = "Thinking…"
        }
        defer { isSending = false }

        var fullResponse = ""
        var speechBuffer = ""
        var appleFallbackBuffer = ""
        var qwenTTSAvailable = true
        var confirmationSpoken = false
        var interrupted = false

        do {
            for try await delta in client.streamCommand(text) {
                fullResponse += delta
                lastResponse = fullResponse

                guard settings.speakResponses && !interrupted else { continue }

                // Protected tool calls arrive as one atomic tool-result delta. Do
                // not start reading the recipient/body before noticing that this is
                // a confirmation prompt; keep the spoken version deliberately short.
                if Self.responseRequestsConfirmation(fullResponse) {
                    if !confirmationSpoken {
                        speechBuffer = ""
                        appleFallbackBuffer = ""
                        confirmationSpoken = true
                        if fromHandsFree { voiceStatus = "Speaking…" }
                        let prompt = Self.spokenResponse(for: fullResponse)
                        if !(await speakQwenChunk(prompt)) {
                            await speechSynthesizer.speak(
                                prompt,
                                preferBluetooth: settings.preferBluetoothAudio
                            )
                        }
                        interrupted = speechSynthesizer.lastOutputInterrupted
                    }
                    continue
                }

                if qwenTTSAvailable {
                    speechBuffer += delta
                    while let segment = Self.takeSpeechSegment(from: &speechBuffer, flush: false) {
                        if fromHandsFree { voiceStatus = "Speaking…" }
                        let success = await speakQwenChunk(segment)
                        if speechSynthesizer.lastOutputInterrupted {
                            interrupted = true
                            break
                        }
                        if !success {
                            qwenTTSAvailable = false
                            appleFallbackBuffer = Self.joinCommandParts(segment, speechBuffer)
                            speechBuffer = ""
                            break
                        }
                    }
                } else {
                    appleFallbackBuffer += delta
                }

                if interrupted {
                    break
                }
            }

            if settings.speakResponses && !interrupted && !confirmationSpoken {
                if qwenTTSAvailable {
                    if let tail = Self.takeSpeechSegment(from: &speechBuffer, flush: true), !tail.isEmpty {
                        if fromHandsFree { voiceStatus = "Speaking…" }
                        let success = await speakQwenChunk(tail)
                        interrupted = speechSynthesizer.lastOutputInterrupted
                        if !success && !interrupted {
                            await speechSynthesizer.speak(
                                tail,
                                preferBluetooth: settings.preferBluetoothAudio
                            )
                        }
                    }
                } else {
                    let fallback = Self.joinCommandParts(appleFallbackBuffer, speechBuffer)
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if !fallback.isEmpty {
                        if fromHandsFree { voiceStatus = "Speaking…" }
                        await speechSynthesizer.speak(
                            fallback,
                            preferBluetooth: settings.preferBluetoothAudio
                        )
                        interrupted = speechSynthesizer.lastOutputInterrupted
                    }
                }
            }

            if fromHandsFree && Self.responseRequestsConfirmation(fullResponse) {
                confirmationFollowUpDeadline = Date().addingTimeInterval(15)
                conversationalFollowUpDeadline = nil
                voiceStatus = "Say confirm or cancel"
            } else if fromHandsFree && !fullResponse.isEmpty {
                confirmationFollowUpDeadline = nil
                // Start this after the final audio chunk finishes. If the user
                // barged in, their captured speech is already waiting in the
                // BargeInBuffer and this window lets it become the next turn.
                conversationalFollowUpDeadline = Date().addingTimeInterval(5)
                voiceStatus = "Listening for follow-up…"
            } else {
                confirmationFollowUpDeadline = nil
                conversationalFollowUpDeadline = nil
            }
        } catch {
            // A pre-0.9 backend or transient stream failure still gets a complete
            // response through the proven non-streaming endpoint.
            do {
                let response = try await client.command(text)
                fullResponse = response.message
                lastResponse = response.message
                if settings.speakResponses && !response.message.isEmpty {
                    if fromHandsFree { voiceStatus = "Speaking…" }
                    await speakOneResponse(Self.spokenResponse(for: response.message))
                }
                if fromHandsFree && Self.responseRequestsConfirmation(response.message) {
                    confirmationFollowUpDeadline = Date().addingTimeInterval(15)
                    conversationalFollowUpDeadline = nil
                    voiceStatus = "Say confirm or cancel"
                } else if fromHandsFree && !response.message.isEmpty {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = Date().addingTimeInterval(5)
                    voiceStatus = "Listening for follow-up…"
                }
            } catch {
                confirmationFollowUpDeadline = nil
                conversationalFollowUpDeadline = nil
                errorMessage = error.localizedDescription
                if fromHandsFree {
                    voiceStatus = "Command failed"
                }
            }
        }
    }

    private func speakQwenChunk(_ text: String) async -> Bool {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return true }
        do {
            let audio = try await client.synthesizeSpeech(cleaned)
            try await speechSynthesizer.speakRemoteAudio(
                audio,
                text: cleaned,
                preferBluetooth: settings.preferBluetoothAudio
            )
            return true
        } catch {
            return false
        }
    }

    private func speakOneResponse(_ text: String) async {
        if !(await speakQwenChunk(text)) {
            await speechSynthesizer.speak(
                text,
                preferBluetooth: settings.preferBluetoothAudio
            )
        }
    }

    func sendEvent(_ name: String) async {
        do {
            let response = try await client.event(name)
            lastResponse = response.message
            if settings.speakResponses && !response.message.isEmpty {
                await speakOneResponse(response.message)
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
        confirmationFollowUpDeadline = nil
        conversationalFollowUpDeadline = nil
        voiceStatus = "Listening for “Jarvis”…"
        wakeWordTask = Task { [weak self] in
            guard let self else { return }
            await self.runHandsFreeLoop()
        }
    }

    func stopWakeWordMode() {
        wakeWordTask?.cancel()
        wakeWordTask = nil
        confirmationFollowUpDeadline = nil
        conversationalFollowUpDeadline = nil
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
        var commandBuffer = ""
        var followUpBuffer = ""

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

            if let deadline = confirmationFollowUpDeadline, now >= deadline {
                confirmationFollowUpDeadline = nil
                if case .waitingForWake = phase, conversationalFollowUpDeadline == nil {
                    voiceStatus = "Listening for “Jarvis”…"
                }
            }

            if let deadline = conversationalFollowUpDeadline, now >= deadline {
                conversationalFollowUpDeadline = nil
                if case .waitingForWake = phase, confirmationFollowUpDeadline == nil {
                    voiceStatus = "Listening for “Jarvis”…"
                }
            }

            switch phase {
            case .waitingForWake:
                commandBuffer = ""
                followUpBuffer = ""

                if let deadline = confirmationFollowUpDeadline,
                   now < deadline,
                   let confirmation = Self.confirmationCommand(from: transcript),
                   silence >= 0.55 || recognitionEnded {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await submitHandsFreeCommand(confirmation)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if let deadline = conversationalFollowUpDeadline, now < deadline {
                    phase = .awaitingFollowUp(deadline: deadline)
                    voiceStatus = "Listening for follow-up…"
                    continue
                }

                if let command = Self.commandAfterWakeWord(in: transcript) {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    phase = .collectingAfterWake
                    voiceStatus = "Listening for command…"
                    let requiredSilence = Self.commandSilenceWindow(for: command)

                    if !command.isEmpty && silence >= requiredSilence {
                        await submitHandsFreeCommand(command)
                        phase = .waitingForWake
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }

                    if recognitionEnded {
                        if Self.needsExtendedDictation(command) {
                            commandBuffer = command
                            _ = await restartVoiceRecognition()
                            lastTranscript = ""
                            lastTranscriptChange = Date()
                            continue
                        }

                        if !command.isEmpty {
                            await submitHandsFreeCommand(command)
                            phase = .waitingForWake
                            lastTranscript = ""
                            lastTranscriptChange = Date()
                            continue
                        }
                    }
                } else if Self.containsWakeWord(transcript) && (silence >= 0.65 || recognitionEnded) {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await promptForFollowUp()
                    phase = .awaitingFollowUp(deadline: Date().addingTimeInterval(20))
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                } else if !transcript.isEmpty && silence >= 1.2 {
                    _ = speechRecognizer.stopListening()
                    isListening = false
                    _ = await restartVoiceRecognition()
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

            case .collectingAfterWake:
                let segment: String
                if commandBuffer.isEmpty {
                    segment = Self.commandAfterWakeWord(in: transcript) ?? ""
                } else {
                    segment = transcript
                }

                let command = Self.joinCommandParts(commandBuffer, segment)
                let requiredSilence = Self.commandSilenceWindow(for: command)

                if !command.isEmpty && silence >= requiredSilence {
                    commandBuffer = ""
                    await submitHandsFreeCommand(command)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if recognitionEnded {
                    if Self.needsExtendedDictation(command) {
                        commandBuffer = command
                        _ = await restartVoiceRecognition()
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }

                    if !command.isEmpty {
                        commandBuffer = ""
                        await submitHandsFreeCommand(command)
                        phase = .waitingForWake
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }
                }

            case .awaitingFollowUp(let deadline):
                let command = Self.joinCommandParts(followUpBuffer, transcript)
                let requiredSilence = Self.commandSilenceWindow(for: command)

                if !command.isEmpty && silence >= requiredSilence {
                    followUpBuffer = ""
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await submitHandsFreeCommand(command)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if recognitionEnded && !command.isEmpty {
                    if Self.needsExtendedDictation(command) {
                        followUpBuffer = command
                        _ = await restartVoiceRecognition()
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }

                    followUpBuffer = ""
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await submitHandsFreeCommand(command)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if now >= deadline && command.isEmpty {
                    followUpBuffer = ""
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
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
        conversationalFollowUpDeadline = nil
        voiceStatus = "Listening for command…"
        await speakOneResponse("Yes, sir?")
        try? await Task.sleep(for: .milliseconds(180))
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
        try? await Task.sleep(for: .milliseconds(180))
        if confirmationFollowUpDeadline != nil {
            voiceStatus = "Say confirm or cancel"
        } else if conversationalFollowUpDeadline != nil {
            voiceStatus = "Listening for follow-up…"
        } else {
            voiceStatus = "Listening for “Jarvis”…"
        }
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

    private static func joinCommandParts(_ first: String, _ second: String) -> String {
        let a = first.trimmingCharacters(in: .whitespacesAndNewlines)
        let b = second.trimmingCharacters(in: .whitespacesAndNewlines)
        if a.isEmpty { return b }
        if b.isEmpty { return a }
        return "\(a) \(b)"
    }

    /// Pull one voice-sized segment out of a growing streamed answer. Normally a
    /// sentence boundary wins. Very long punctuation-free output is cut at a word
    /// boundary so TTS can start rather than waiting for an entire paragraph.
    private static func takeSpeechSegment(from buffer: inout String, flush: Bool) -> String? {
        let trimmedLeading = buffer.drop(while: { $0.isWhitespace })
        if trimmedLeading.count != buffer.count {
            buffer = String(trimmedLeading)
        }
        guard !buffer.isEmpty else { return nil }

        let chars = Array(buffer)
        for index in chars.indices {
            let character = chars[index]
            let isSentenceEnd = character == "." || character == "!" || character == "?" || character == "\n"
            guard isSentenceEnd else { continue }
            let nextIsBoundary = index == chars.index(before: chars.endIndex)
                || chars[chars.index(after: index)].isWhitespace
            if nextIsBoundary && index >= 18 {
                let end = chars.index(after: index)
                let segment = String(chars[..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
                buffer = String(chars[end...]).trimmingCharacters(in: .whitespacesAndNewlines)
                return segment
            }
        }

        if chars.count >= 220 {
            let upper = min(chars.count - 1, 190)
            let lower = min(110, upper)
            if lower <= upper {
                for index in stride(from: upper, through: lower, by: -1) {
                    if chars[index].isWhitespace || chars[index] == "," || chars[index] == ";" || chars[index] == ":" {
                        let end = chars.index(after: index)
                        let segment = String(chars[..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
                        buffer = String(chars[end...]).trimmingCharacters(in: .whitespacesAndNewlines)
                        return segment
                    }
                }
            }
        }

        if flush {
            let segment = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
            buffer = ""
            return segment.isEmpty ? nil : segment
        }
        return nil
    }

    static func commandSilenceWindow(for command: String) -> TimeInterval {
        if needsExtendedDictation(command) {
            return 3.0
        }
        if command.count > 100 {
            return 1.65
        }
        return 1.15
    }

    static func needsExtendedDictation(_ command: String) -> Bool {
        let lower = command.lowercased()
        let cues = [
            "email", "e-mail", "email address", "address is", "my address",
            "gmail", "icloud", "outlook", "dot com", "dot net", "dot org",
            " at ", " underscore ", "spell", "spelling", "url", "website"
        ]
        return cues.contains(where: { lower.contains($0) })
    }

    static func confirmationCommand(from transcript: String) -> String? {
        let normalized = transcript
            .lowercased()
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
        guard !normalized.isEmpty else { return nil }

        if normalized == "confirm" || normalized == "yes confirm" || normalized == "confirm it" || normalized == "yes" {
            return "confirm"
        }
        if normalized == "cancel" || normalized == "no cancel" || normalized == "cancel it" || normalized == "no" {
            return "cancel"
        }
        return nil
    }

    static func responseRequestsConfirmation(_ response: String) -> Bool {
        let lower = response.lowercased()
        return lower.contains("say 'confirm'")
            || lower.contains("say “confirm”")
            || lower.contains("say confirm")
            || (lower.contains("confirm") && lower.contains("cancel"))
    }

    static func spokenResponse(for response: String) -> String {
        if responseRequestsConfirmation(response) {
            return "Ready, sir. Say confirm or cancel."
        }
        return response
    }
}
