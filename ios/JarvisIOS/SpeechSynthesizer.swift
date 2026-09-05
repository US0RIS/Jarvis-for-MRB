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

@MainActor
final class SpeechSynthesizer: NSObject, ObservableObject, AVSpeechSynthesizerDelegate, AVAudioPlayerDelegate {
    @Published private(set) var isSpeaking = false
    @Published private(set) var lastOutputInterrupted = false
    @Published private(set) var isWhispering = false

    private let synthesizer = AVSpeechSynthesizer()
    private let audioRouteManager: AudioRouteManager
    private var audioPlayer: AVAudioPlayer?
    private var completion: CheckedContinuation<Void, Never>?
    private var currentUtterance: AVSpeechUtterance?

    private let bargeInRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let bargeInAudioEngine = AVAudioEngine()
    private var bargeInRequest: SFSpeechAudioBufferRecognitionRequest?
    private var bargeInTask: SFSpeechRecognitionTask?
    private var bargeInTapInstalled = false
    private var bargeInFinalizeTask: Task<Void, Never>?
    private var spokenTextForEchoFilter = ""
    private var latestBargeInTranscript = ""
    private var lastBargeInTranscriptChange = Date.distantPast
    private var didBargeIn = false

    init(audioRouteManager: AudioRouteManager) {
        self.audioRouteManager = audioRouteManager
        super.init()
        synthesizer.delegate = self
    }

    private func resolveWhisper(_ override: Bool?) -> Bool {
        if let override { return override }
        let defaults = UserDefaults.standard
        let enabled = defaults.object(forKey: "jarvis.adaptiveWhisperEnabled") as? Bool ?? true
        let threshold = defaults.object(forKey: "jarvis.whisperThresholdDBFS") as? Double ?? -42.0
        return enabled && JarvisAudioEnvironment.noiseFloorDBFS <= threshold
    }

    func speak(_ text: String, preferBluetooth: Bool, whisper: Bool? = nil) async {
        let cleaned = Self.respectfulSpeechText(
            text.trimmingCharacters(in: .whitespacesAndNewlines)
        )
        guard !cleaned.isEmpty else { return }
        let quiet = resolveWhisper(whisper)

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
        let quiet = resolveWhisper(whisper)

        stopSpeaking()
        prepareOutput(text: cleaned, preferBluetooth: preferBluetooth, whisper: quiet)

        let player = try AVAudioPlayer(data: data)
        player.delegate = self
        player.enableRate = true
        player.rate = quiet ? 0.92 : 1.0
        player.volume = quiet ? 0.34 : 1.0
        player.prepareToPlay()
        audioPlayer = player

        await withCheckedContinuation { continuation in
            completion = continuation
            if player.play() {
                startBargeInListening()
            } else {
                finalizeCurrentOutput()
            }
        }
    }

    private func prepareOutput(text: String, preferBluetooth: Bool, whisper: Bool) {
        do {
            try audioRouteManager.prepareForVoice(preferBluetooth: preferBluetooth)
        } catch {
            // Playback can still succeed on the current route.
        }
        isSpeaking = true
        isWhispering = whisper
        lastOutputInterrupted = false
        spokenTextForEchoFilter = text
        latestBargeInTranscript = ""
        lastBargeInTranscriptChange = Date.distantPast
        didBargeIn = false
        BargeInBuffer.store("")
    }

    private static func respectfulSpeechText(_ text: String) -> String {
        guard !text.isEmpty else { return text }
        if text.range(of: "sir", options: [.caseInsensitive, .diacriticInsensitive]) != nil {
            return text
        }
        if text == "Yes?" { return "Yes, sir?" }
        if text == "Ready. Say confirm or cancel." { return "Ready, sir. Say confirm or cancel." }
        return "Sir, " + text.prefix(1).lowercased() + String(text.dropFirst())
    }

    private func preferredJarvisVoice() -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices()
        let usEnglish = voices.filter { $0.language.lowercased().hasPrefix("en-us") }
        let preferredNames = ["Alex", "Ava", "Samantha", "Nathan", "Evan", "Tom"]
        for name in preferredNames {
            let matches = usEnglish.filter {
                $0.name.compare(name, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
            }
            if let best = matches.max(by: { $0.quality.rawValue < $1.quality.rawValue }) {
                return best
            }
        }
        return AVSpeechSynthesisVoice(language: "en-US")
    }

    func stopSpeaking() {
        guard currentUtterance != nil || audioPlayer != nil || isSpeaking else { return }
        bargeInFinalizeTask?.cancel()
        bargeInFinalizeTask = nil
        didBargeIn = false
        lastOutputInterrupted = false
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        if audioPlayer?.isPlaying == true { audioPlayer?.stop() }
        finalizeCurrentOutput()
    }

    private func startBargeInListening() {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized,
              let bargeInRecognizer,
              bargeInRecognizer.isAvailable else { return }

        stopBargeInListening()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        request.contextualStrings = ["Jarvis", "stop", "wait", "hold on", "actually", "Dubeck"]
        if bargeInRecognizer.supportsOnDeviceRecognition {
            request.requiresOnDeviceRecognition = true
        }
        bargeInRequest = request

        let input = bargeInAudioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            bargeInRequest = nil
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }
        bargeInTapInstalled = true
        bargeInAudioEngine.prepare()
        do {
            try bargeInAudioEngine.start()
        } catch {
            stopBargeInListening()
            return
        }

        bargeInTask = bargeInRecognizer.recognitionTask(with: request) { [weak self] result, _ in
            Task { @MainActor in
                guard let self, self.isSpeaking, let result else { return }
                let heard = result.bestTranscription.formattedString
                    .trimmingCharacters(in: .whitespacesAndNewlines)
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
        let normalizedHeard = Self.normalizedWords(heard)
        guard !normalizedHeard.isEmpty else { return false }
        if isLikelyEcho(heard) { return false }
        let joined = normalizedHeard.joined(separator: " ")
        let explicit = [
            "jarvis", "stop", "wait", "hold on", "actually", "no", "but",
            "what", "why", "how", "when", "where", "who", "which",
            "can you", "could you", "don't", "do not"
        ]
        if explicit.contains(where: { cue in joined == cue || joined.hasPrefix(cue + " ") }) { return true }
        return normalizedHeard.count >= 2
    }

    private func isLikelyEcho(_ heard: String) -> Bool {
        let heardWords = Self.normalizedWords(heard)
        let spokenWords = Self.normalizedWords(spokenTextForEchoFilter)
        guard !heardWords.isEmpty, !spokenWords.isEmpty else { return false }
        let heardString = heardWords.joined(separator: " ")
        let spokenString = spokenWords.joined(separator: " ")
        if spokenString.contains(heardString) { return true }
        let spokenSet = Set(spokenWords)
        let overlap = heardWords.filter { spokenSet.contains($0) }.count
        return heardWords.count >= 2 && Double(overlap) / Double(heardWords.count) >= 0.75
    }

    private func commandPayload(fromInterruption heard: String) -> String {
        var text = heard.trimmingCharacters(in: .whitespacesAndNewlines)
        if let range = text.range(of: "jarvis", options: [.caseInsensitive, .diacriticInsensitive]) {
            return text[range.upperBound...]
                .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
        }
        let lower = text.lowercased()
        if ["stop", "wait", "hold on", "hang on"].contains(lower.trimmingCharacters(in: .punctuationCharacters)) {
            return ""
        }
        for prefix in ["wait ", "hold on ", "hang on "] where lower.hasPrefix(prefix) {
            text = String(text.dropFirst(prefix.count))
                .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
            break
        }
        return text
    }

    private static func normalizedWords(_ text: String) -> [String] {
        text.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
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
            if now.timeIntervalSince(lastBargeInTranscriptChange) >= 0.9 || now.timeIntervalSince(started) >= 4.0 { break }
            try? await Task.sleep(for: .milliseconds(80))
        }
        if !latestBargeInTranscript.isEmpty {
            BargeInBuffer.store(commandPayload(fromInterruption: latestBargeInTranscript))
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
