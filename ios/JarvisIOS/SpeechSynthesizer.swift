import AVFoundation
import Speech

/// A tiny handoff between the barge-in recognizer that runs while Jarvis is
/// speaking and the normal command recognizer that starts immediately after
/// speech stops. Keeping the prefix lets a sentence begun over Jarvis's voice
/// continue naturally once Jarvis has yielded the audio channel.
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
final class SpeechSynthesizer: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published private(set) var isSpeaking = false

    private let synthesizer = AVSpeechSynthesizer()
    private let audioRouteManager: AudioRouteManager
    private var completion: CheckedContinuation<Void, Never>?
    private var currentUtterance: AVSpeechUtterance?

    // A second, short-lived recognition pipeline is active only while Jarvis is
    // talking. It is intentionally separate from the normal SpeechRecognizer so
    // the user can barge in without waiting for TTS to finish.
    private let bargeInRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let bargeInAudioEngine = AVAudioEngine()
    private var bargeInRequest: SFSpeechAudioBufferRecognitionRequest?
    private var bargeInTask: SFSpeechRecognitionTask?
    private var bargeInTapInstalled = false
    private var spokenTextForEchoFilter = ""
    private var didBargeIn = false

    init(audioRouteManager: AudioRouteManager) {
        self.audioRouteManager = audioRouteManager
        super.init()
        synthesizer.delegate = self
    }

    func speak(_ text: String, preferBluetooth: Bool) async {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }

        if synthesizer.isSpeaking {
            let interrupted = currentUtterance
            synthesizer.stopSpeaking(at: .immediate)
            if let interrupted {
                finishSpeech(interrupted)
            }
        }

        do {
            try audioRouteManager.prepareForVoice(preferBluetooth: preferBluetooth)
        } catch {
            // AVSpeechSynthesizer can still speak over the current system route.
            // Route setup failures should not suppress a Jarvis response.
        }

        let utterance = AVSpeechUtterance(string: cleaned)
        utterance.voice = preferredJarvisVoice()
        // Use a neutral cadence and pitch. The previous deliberately lowered
        // British voice sounded synthetic on the target glasses.
        utterance.rate = 0.50
        utterance.pitchMultiplier = 1.0
        utterance.volume = 0.90
        utterance.preUtteranceDelay = 0.02
        utterance.postUtteranceDelay = 0.02

        currentUtterance = utterance
        isSpeaking = true
        spokenTextForEchoFilter = cleaned
        didBargeIn = false
        BargeInBuffer.store("")

        // Start TTS first, then open the full-duplex microphone. voiceChat mode
        // supplies iOS echo cancellation; the text filter below is a second guard
        // against Jarvis transcribing its own voice.
        await withCheckedContinuation { continuation in
            completion = continuation
            synthesizer.speak(utterance)
            startBargeInListening()
        }
    }

    private func preferredJarvisVoice() -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices()
        let usEnglish = voices.filter { $0.language.lowercased().hasPrefix("en-us") }

        // Prefer Apple's more natural US English voices when they are installed.
        // Alex is the first choice; the others are fallbacks. For a given name,
        // select the highest-quality installed variant rather than a compact one.
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
        guard let utterance = currentUtterance else { return }
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        finishSpeech(utterance)
    }

    private func startBargeInListening() {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized,
              let bargeInRecognizer,
              bargeInRecognizer.isAvailable else {
            return
        }

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

        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }
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
                guard let self, self.isSpeaking, !self.didBargeIn, let result else { return }
                let heard = result.bestTranscription.formattedString
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                guard self.shouldBargeIn(with: heard) else { return }

                self.didBargeIn = true
                BargeInBuffer.store(self.commandPayload(fromInterruption: heard))
                // Immediate stop is the key behavior: Jarvis yields as soon as the
                // user starts a distinct utterance instead of finishing its turn.
                self.stopSpeaking()
            }
        }
    }

    private func shouldBargeIn(with heard: String) -> Bool {
        let normalizedHeard = Self.normalizedWords(heard)
        guard !normalizedHeard.isEmpty else { return false }

        // Do not let the TTS output trigger its own interruption. HFP voiceChat
        // usually removes most echo, but this catches recognizable residual audio.
        if isLikelyEcho(heard) {
            return false
        }

        let joined = normalizedHeard.joined(separator: " ")
        let explicit = [
            "jarvis", "stop", "wait", "hold on", "actually", "no ", "no,",
            "but ", "what ", "why ", "how ", "when ", "where ", "who ",
            "which ", "can you", "could you", "don't", "do not"
        ]
        if explicit.contains(where: { joined == $0.trimmingCharacters(in: .punctuationCharacters) || joined.hasPrefix($0) }) {
            return true
        }

        // Two or more non-echo words are strong enough evidence that the wearer is
        // talking over Jarvis. This makes barge-in feel conversational rather than
        // requiring a special stop phrase every time.
        return normalizedHeard.count >= 2
    }

    private func isLikelyEcho(_ heard: String) -> Bool {
        let heardWords = Self.normalizedWords(heard)
        let spokenWords = Self.normalizedWords(spokenTextForEchoFilter)
        guard !heardWords.isEmpty, !spokenWords.isEmpty else { return false }

        let heardString = heardWords.joined(separator: " ")
        let spokenString = spokenWords.joined(separator: " ")
        if spokenString.contains(heardString) {
            return true
        }

        let spokenSet = Set(spokenWords)
        let overlap = heardWords.filter { spokenSet.contains($0) }.count
        return heardWords.count >= 2 && Double(overlap) / Double(heardWords.count) >= 0.75
    }

    private func commandPayload(fromInterruption heard: String) -> String {
        var text = heard.trimmingCharacters(in: .whitespacesAndNewlines)

        if let range = text.range(of: "jarvis", options: [.caseInsensitive, .diacriticInsensitive]) {
            let suffix = text[range.upperBound...]
                .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
            return suffix
        }

        let lower = text.lowercased()
        let yieldOnly = ["stop", "wait", "hold on", "hang on"]
        if yieldOnly.contains(lower.trimmingCharacters(in: .punctuationCharacters)) {
            return ""
        }

        // Remove pure turn-taking language while preserving the actual correction
        // or follow-up that came after it.
        for prefix in ["wait ", "hold on ", "hang on "] {
            if lower.hasPrefix(prefix) {
                text = String(text.dropFirst(prefix.count))
                    .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
                break
            }
        }
        return text
    }

    private static func normalizedWords(_ text: String) -> [String] {
        text.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
    }

    private func stopBargeInListening() {
        if bargeInAudioEngine.isRunning {
            bargeInAudioEngine.stop()
        }
        if bargeInTapInstalled {
            bargeInAudioEngine.inputNode.removeTap(onBus: 0)
            bargeInTapInstalled = false
        }
        bargeInRequest?.endAudio()
        bargeInRequest = nil
        bargeInTask?.cancel()
        bargeInTask = nil
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        finishSpeech(utterance)
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        finishSpeech(utterance)
    }

    private func finishSpeech(_ utterance: AVSpeechUtterance) {
        guard currentUtterance === utterance else { return }
        stopBargeInListening()
        currentUtterance = nil
        isSpeaking = false
        spokenTextForEchoFilter = ""
        completion?.resume()
        completion = nil
        audioRouteManager.refresh()
    }
}
