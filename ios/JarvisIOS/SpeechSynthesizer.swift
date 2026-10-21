import AVFoundation
import Speech

@MainActor
enum BargeInBuffer {
    private static var pendingText = ""

    static func store(_ text: String) {
        pendingText = text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func take() -> String {
        let value = pendingText
        pendingText = ""
        return value
    }
}

/// Input path of a turn. Sent to the backend as `context.channel`.
enum VoiceChannel: String {
    case voice
    case conversation
    case text
}

/// Single user-visible state of the earpiece interaction.
enum EarpieceState: String {
    case idle
    case listening
    case thinking
    case speaking

    var label: String {
        switch self {
        case .idle: return "Idle - microphone off"
        case .listening: return "Listening"
        case .thinking: return "Thinking"
        case .speaking: return "Speaking"
        }
    }

    var symbolName: String {
        switch self {
        case .idle: return "ear"
        case .listening: return "mic.fill"
        case .thinking: return "ellipsis.circle"
        case .speaking: return "speaker.wave.2.fill"
        }
    }
}

/// Why the most recent spoken output ended early.
enum SpokenInterruptionKind: Equatable {
    case none
    /// "wait" / "hold on": speech stopped, nothing was asked.
    case pause
    /// "stop" / "cancel" / "never mind" / "be quiet": speech stopped and the turn is dropped.
    case cancel
    /// The user spoke a real follow-up over the answer.
    case utterance
    /// Headphones/earbuds disconnected; speech was stopped so it never reaches the loudspeaker.
    case routeLost
    /// A phone call, Siri or another app took the audio session, or media services reset.
    case systemInterrupted
}

/// Pure text helpers shared by barge-in, conversation mode and the stop commands.
enum EarpieceVoiceCommands {
    private static let cancelPhrases: Set<String> = [
        "stop", "cancel", "never mind", "nevermind", "be quiet", "quiet",
        "stop talking", "stop it", "enough", "thats enough", "that is enough", "shut up",
    ]
    private static let dismissalPhrases: Set<String> = [
        "never mind", "nevermind", "be quiet", "quiet", "stop talking",
        "enough", "thats enough", "that is enough",
    ]
    private static let pausePhrases: Set<String> = [
        "wait", "hold on", "hang on", "one moment", "one second", "pause",
    ]
    private static let fillerWords: Set<String> = ["please", "now", "horus", "jarvis", "ok", "okay", "hey"]

    static func normalizedWords(_ text: String) -> [String] {
        text.lowercased()
            .replacingOccurrences(of: "'", with: "")
            .replacingOccurrences(of: "\u{2019}", with: "")
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
    }

    private static func corePhrase(_ text: String) -> String {
        normalizedWords(text).filter { !fillerWords.contains($0) }.joined(separator: " ")
    }

    /// True only when the whole utterance is a stop-type command.
    static func isCancelCommand(_ text: String) -> Bool {
        cancelPhrases.contains(corePhrase(text))
    }

    /// Stop-type commands that carry no request at all ("never mind", "be quiet").
    static func isDismissal(_ text: String) -> Bool {
        dismissalPhrases.contains(corePhrase(text))
    }

    static func isPauseCommand(_ text: String) -> Bool {
        let words = normalizedWords(text)
        guard !words.isEmpty else { return false }
        let core = corePhrase(text)
        if core.isEmpty { return words.contains("horus") || words.contains("jarvis") }
        return pausePhrases.contains(core)
    }

    /// True when `heard` is (nearly) the text Horus itself is speaking.
    static func isLikelyEcho(heard: String, spoken: String) -> Bool {
        let heardWords = normalizedWords(heard)
        let spokenWords = normalizedWords(spoken)
        guard !heardWords.isEmpty, !spokenWords.isEmpty else { return false }
        let heardString = heardWords.joined(separator: " ")
        let spokenString = spokenWords.joined(separator: " ")
        // Whole-word containment, so "so" is not an echo of "also".
        if (" " + spokenString + " ").contains(" " + heardString + " ") { return true }
        let spokenSet = Set(spokenWords)
        let overlap = heardWords.filter { spokenSet.contains($0) }.count
        return heardWords.count >= 2 && Double(overlap) / Double(heardWords.count) >= 0.75
    }
}

@MainActor
final class SpeechSynthesizer: NSObject, ObservableObject, AVSpeechSynthesizerDelegate, AVAudioPlayerDelegate {
    @Published private(set) var isSpeaking = false
    @Published private(set) var lastOutputInterrupted = false
    @Published private(set) var isWhispering = false
    /// Why the last output ended early (see `SpokenInterruptionKind`). Reset on every new utterance.
    @Published private(set) var lastInterruptionKind: SpokenInterruptionKind = .none

    /// Minimum evidence before free-form speech over Horus counts as a barge-in.
    /// Stop/cancel/wait commands are exempt because they are single words by nature.
    static let minimumBargeInWords = 3
    static let minimumTwoWordBargeInDuration: TimeInterval = 0.35

    private var synthesizer = AVSpeechSynthesizer()
    private let audioRouteManager: AudioRouteManager
    private var audioPlayer: AVAudioPlayer?
    private var completion: CheckedContinuation<Void, Never>?
    private var currentUtterance: AVSpeechUtterance?

    private let bargeInRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var bargeInAudioEngine = AVAudioEngine()
    private var bargeInRequest: SFSpeechAudioBufferRecognitionRequest?
    private var bargeInTask: SFSpeechRecognitionTask?
    private var bargeInTapInstalled = false
    private var bargeInFinalizeTask: Task<Void, Never>?
    private var spokenTextForEchoFilter = ""
    private var latestBargeInTranscript = ""
    private var lastBargeInTranscriptChange = Date.distantPast
    private var didBargeIn = false
    private var bargeInCandidateSince: Date?

    init(audioRouteManager: AudioRouteManager) {
        self.audioRouteManager = audioRouteManager
        super.init()
        synthesizer.delegate = self
    }

    private func resolveWhisper(_ override: Bool?) -> Bool {
        if let override { return override }
        let defaults = UserDefaults.standard
        let forcedUntil = defaults.double(forKey: "jarvis.forceWhisperUntil")
        if forcedUntil > Date().timeIntervalSince1970 { return true }
        if forcedUntil > 0 { defaults.removeObject(forKey: "jarvis.forceWhisperUntil") }
        let enabled = defaults.object(forKey: "jarvis.adaptiveWhisperEnabled") as? Bool ?? true
        let threshold = defaults.object(forKey: "jarvis.whisperThresholdDBFS") as? Double ?? -42.0
        return enabled && JarvisAudioEnvironment.noiseFloorDBFS <= threshold
    }

    func speak(_ text: String, preferBluetooth: Bool, whisper: Bool? = nil) async {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        guard !refuseSpeechAfterPrivateRouteLoss() else { return }
        let quiet = resolveWhisper(whisper)

        AmbientSoundCapture.shared.stop()
        stopSpeaking()
        prepareOutput(text: cleaned, preferBluetooth: preferBluetooth, whisper: quiet)

        let utterance = AVSpeechUtterance(string: cleaned)
        utterance.voice = preferredJarvisVoice()
        utterance.rate = quiet ? 0.46 : 0.50
        utterance.pitchMultiplier = quiet ? 0.86 : 1.0
        utterance.volume = quiet ? 0.36 : 0.90
        utterance.preUtteranceDelay = 0.02
        utterance.postUtteranceDelay = 0.02
        currentUtterance = utterance

        await withCheckedContinuation { continuation in
            completion = continuation
            synthesizer.speak(utterance)
            startBargeInListening()
        }
    }

    func speakRemoteAudio(
        _ data: Data,
        text: String,
        preferBluetooth: Bool,
        whisper: Bool? = nil
    ) async throws {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        guard !refuseSpeechAfterPrivateRouteLoss() else { return }
        let quiet = resolveWhisper(whisper)

        AmbientSoundCapture.shared.stop()
        stopSpeaking()
        prepareOutput(text: cleaned, preferBluetooth: preferBluetooth, whisper: quiet)

        let player = try AVAudioPlayer(data: data)
        player.delegate = self
        player.enableRate = true
        player.rate = quiet ? 0.92 : 1.0
        player.volume = quiet ? 0.34 : 1.0
        player.pan = quiet ? -0.14 : 0.0
        player.prepareToPlay()
        audioPlayer = player

        await withCheckedContinuation { continuation in
            completion = continuation
            if player.play() { startBargeInListening() } else { finalizeCurrentOutput() }
        }
    }

    private func prepareOutput(text: String, preferBluetooth: Bool, whisper: Bool) {
        do { try audioRouteManager.prepareForVoice(preferBluetooth: preferBluetooth) } catch { }
        isSpeaking = true
        isWhispering = whisper
        lastOutputInterrupted = false
        lastInterruptionKind = .none
        spokenTextForEchoFilter = text
        latestBargeInTranscript = ""
        lastBargeInTranscriptChange = Date.distantPast
        bargeInCandidateSince = nil
        didBargeIn = false
        BargeInBuffer.store("")
    }

    /// A private (headphone/Bluetooth) output was lost. Never let queued speech
    /// continue on the loudspeaker: refuse it and tell the caller the output was cut.
    private func refuseSpeechAfterPrivateRouteLoss() -> Bool {
        guard audioRouteManager.privateOutputLost else { return false }
        lastOutputInterrupted = true
        lastInterruptionKind = .routeLost
        BargeInBuffer.store("")
        return true
    }

    /// Immediately silence speech because headphones disconnected.
    func stopSpeakingForPrivateRouteLoss() {
        stopSpeakingBecause(.routeLost)
    }

    /// Immediately silence speech because a call/Siri/another app took audio, or media services reset.
    func stopSpeakingForSystemInterruption() {
        stopSpeakingBecause(.systemInterrupted)
    }

    private func stopSpeakingBecause(_ kind: SpokenInterruptionKind) {
        guard currentUtterance != nil || audioPlayer != nil || isSpeaking else { return }
        bargeInFinalizeTask?.cancel()
        bargeInFinalizeTask = nil
        didBargeIn = false
        lastOutputInterrupted = true
        lastInterruptionKind = kind
        BargeInBuffer.store("")
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        if audioPlayer?.isPlaying == true { audioPlayer?.stop() }
        finalizeCurrentOutput()
    }

    /// Clear the previous output's interruption verdict before a new turn begins.
    func resetInterruptionState() {
        guard !isSpeaking else { return }
        lastOutputInterrupted = false
        lastInterruptionKind = .none
    }

    /// AVAudioSession media services were reset: every AV object is invalid and must be rebuilt.
    func resetAfterMediaServicesReset() {
        stopSpeakingBecause(.systemInterrupted)
        stopBargeInListening()
        synthesizer = AVSpeechSynthesizer()
        synthesizer.delegate = self
        bargeInAudioEngine = AVAudioEngine()
        bargeInTapInstalled = false
    }

    private func preferredJarvisVoice() -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices()
        let usEnglish = voices.filter { $0.language.lowercased().hasPrefix("en-us") }
        let preferredNames = ["Alex", "Ava", "Samantha", "Nathan", "Evan", "Tom"]
        for name in preferredNames {
            let matches = usEnglish.filter {
                $0.name.compare(name, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
            }
            if let best = matches.max(by: { $0.quality.rawValue < $1.quality.rawValue }) { return best }
        }
        return AVSpeechSynthesisVoice(language: "en-US")
    }

    func stopSpeaking() {
        guard currentUtterance != nil || audioPlayer != nil || isSpeaking else { return }
        bargeInFinalizeTask?.cancel()
        bargeInFinalizeTask = nil
        didBargeIn = false
        lastOutputInterrupted = false
        lastInterruptionKind = .none
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        if audioPlayer?.isPlaying == true { audioPlayer?.stop() }
        finalizeCurrentOutput()
    }

    private func startBargeInListening() {
        // Barge-in only listens while output is on a private route or the session
        // asks iOS for echo-cancelled voice processing. Otherwise Horus would hear
        // and answer itself.
        guard audioRouteManager.bargeInPolicy != .disabled else { return }
        guard SFSpeechRecognizer.authorizationStatus() == .authorized,
              let bargeInRecognizer,
              bargeInRecognizer.isAvailable else { return }

        stopBargeInListening()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        request.contextualStrings = ["Horus", "Jarvis", "stop", "cancel", "never mind", "be quiet", "wait", "hold on", "actually", "Dubeck"]
        if bargeInRecognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
        bargeInRequest = request

        let input = bargeInAudioEngine.inputNode
        let format = input.inputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            bargeInRequest = nil
            return
        }
        // HFP routes can renegotiate while output begins. Bind the tap to the
        // node's current native format rather than a stale format snapshot.
        input.installTap(onBus: 0, bufferSize: 1024, format: nil) { buffer, _ in request.append(buffer) }
        bargeInTapInstalled = true
        bargeInAudioEngine.prepare()
        do { try bargeInAudioEngine.start() } catch {
            stopBargeInListening()
            return
        }

        bargeInTask = bargeInRecognizer.recognitionTask(with: request) { [weak self] result, _ in
            Task { @MainActor in
                // Keep reading partials while the interruption settles (isSpeaking is already false then).
                guard let self, self.isSpeaking || self.didBargeIn, let result else { return }
                let heard = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !heard.isEmpty else { return }

                if heard != self.latestBargeInTranscript {
                    self.latestBargeInTranscript = heard
                    self.lastBargeInTranscriptChange = Date()
                }
                if self.didBargeIn {
                    BargeInBuffer.store(self.commandPayload(fromInterruption: heard))
                    return
                }
                guard self.shouldBargeIn(with: heard) else { return }
                self.didBargeIn = true
                self.lastOutputInterrupted = true
                self.lastInterruptionKind = EarpieceVoiceCommands.isCancelCommand(heard) ? .cancel : .pause
                BargeInBuffer.store(self.commandPayload(fromInterruption: heard))
                if self.synthesizer.isSpeaking { self.synthesizer.stopSpeaking(at: .immediate) }
                if self.audioPlayer?.isPlaying == true {
                    self.audioPlayer?.stop()
                    self.beginBargeInFinalize()
                }
            }
        }
    }

    private func shouldBargeIn(with heard: String) -> Bool {
        let words = EarpieceVoiceCommands.normalizedWords(heard)
        guard !words.isEmpty else { return false }
        let policy = audioRouteManager.bargeInPolicy
        if policy == .disabled { return false }

        let isStopCommand = EarpieceVoiceCommands.isCancelCommand(heard)
        let isCommand = isStopCommand || EarpieceVoiceCommands.isPauseCommand(heard)

        // Echo guard. On a private route (earbuds) a deliberate "stop" is trusted even
        // when the answer itself contains the word; on the loudspeaker it is not.
        if isLikelyEcho(heard) && !(isCommand && audioRouteManager.isPrivateOutput) {
            bargeInCandidateSince = nil
            return false
        }
        if isCommand { return true }

        // Free-form interruption requires a private route and enough evidence.
        guard policy == .fullConversation else { return false }
        if words.count >= Self.minimumBargeInWords { return true }
        if words.count >= 2 {
            let since = bargeInCandidateSince ?? Date()
            bargeInCandidateSince = since
            return Date().timeIntervalSince(since) >= Self.minimumTwoWordBargeInDuration
        }
        return false
    }

    private func isLikelyEcho(_ heard: String) -> Bool {
        EarpieceVoiceCommands.isLikelyEcho(heard: heard, spoken: spokenTextForEchoFilter)
    }

    private func commandPayload(fromInterruption heard: String) -> String {
        var text = heard.trimmingCharacters(in: .whitespacesAndNewlines)
        for wakeWord in ["horus", "jarvis"] {
            if let range = text.range(of: wakeWord, options: [.caseInsensitive, .diacriticInsensitive]) {
                return text[range.upperBound...].trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
            }
        }
        let lower = text.lowercased()
        if EarpieceVoiceCommands.isCancelCommand(text) || EarpieceVoiceCommands.isPauseCommand(text) { return "" }
        for prefix in ["wait ", "hold on ", "hang on "] where lower.hasPrefix(prefix) {
            text = String(text.dropFirst(prefix.count)).trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
            break
        }
        return text
    }

    private func beginBargeInFinalize() {
        isSpeaking = false
        if bargeInFinalizeTask == nil {
            bargeInFinalizeTask = Task { [weak self] in
                guard let self else { return }
                await self.finishBargeInAfterUserPauses()
            }
        }
    }

    private func finishBargeInAfterUserPauses() async {
        let started = Date()
        while !Task.isCancelled {
            let now = Date()
            // A bare "stop" settles quickly; a longer interruption waits for the user to finish.
            let quiet: TimeInterval = EarpieceVoiceCommands.isCancelCommand(latestBargeInTranscript) ? 0.45 : 0.9
            if now.timeIntervalSince(lastBargeInTranscriptChange) >= quiet || now.timeIntervalSince(started) >= 4.0 { break }
            try? await Task.sleep(for: .milliseconds(80))
        }
        // stopSpeaking()/route loss already finalized this output; do not overwrite its verdict.
        guard !Task.isCancelled else { return }
        if !latestBargeInTranscript.isEmpty {
            let payload = commandPayload(fromInterruption: latestBargeInTranscript)
            BargeInBuffer.store(payload)
            if EarpieceVoiceCommands.isCancelCommand(latestBargeInTranscript) {
                lastInterruptionKind = .cancel
            } else {
                lastInterruptionKind = payload.isEmpty ? .pause : .utterance
            }
        }
        bargeInFinalizeTask = nil
        finalizeCurrentOutput()
    }

    private func stopBargeInListening() {
        if bargeInAudioEngine.isRunning { bargeInAudioEngine.stop() }
        if bargeInTapInstalled {
            bargeInAudioEngine.inputNode.removeTap(onBus: 0)
            bargeInTapInstalled = false
        }
        bargeInRequest?.endAudio()
        bargeInRequest = nil
        bargeInTask?.cancel()
        bargeInTask = nil
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) { finishSpeechOutput(utterance) }
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) { finishSpeechOutput(utterance) }

    private func finishSpeechOutput(_ utterance: AVSpeechUtterance) {
        guard currentUtterance === utterance else { return }
        if didBargeIn { beginBargeInFinalize(); return }
        finalizeCurrentOutput()
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            guard let self, self.audioPlayer === player else { return }
            if self.didBargeIn { self.beginBargeInFinalize() } else { self.finalizeCurrentOutput() }
        }
    }

    private func finalizeCurrentOutput() {
        stopBargeInListening()
        currentUtterance = nil
        audioPlayer?.delegate = nil
        audioPlayer = nil
        isSpeaking = false
        isWhispering = false
        spokenTextForEchoFilter = ""
        latestBargeInTranscript = ""
        let pending = completion
        completion = nil
        pending?.resume()
        audioRouteManager.refresh()
    }
}
