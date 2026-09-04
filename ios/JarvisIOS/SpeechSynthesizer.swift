import AVFoundation

@MainActor
final class SpeechSynthesizer: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published private(set) var isSpeaking = false

    private let synthesizer = AVSpeechSynthesizer()
    private let audioRouteManager: AudioRouteManager
    private var completion: CheckedContinuation<Void, Never>?
    private var currentUtterance: AVSpeechUtterance?

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
        // Slightly slower and lower than the generic iOS default. The aim is a
        // calm assistant voice rather than the bright accessibility-style default.
        utterance.rate = 0.46
        utterance.pitchMultiplier = 0.88
        utterance.volume = 0.92
        utterance.preUtteranceDelay = 0.03
        utterance.postUtteranceDelay = 0.03

        currentUtterance = utterance
        isSpeaking = true
        await withCheckedContinuation { continuation in
            completion = continuation
            synthesizer.speak(utterance)
        }
    }

    private func preferredJarvisVoice() -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices()

        // Daniel is Apple's long-standing British English male voice and gives
        // Jarvis a substantially less grating default. Prefer it when installed;
        // otherwise pick another British English voice before falling back to the
        // platform default.
        let preferredNames = ["Daniel", "Arthur", "Oliver"]
        for name in preferredNames {
            if let voice = voices.first(where: {
                $0.name.compare(name, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
            }) {
                return voice
            }
        }

        if let britishEnglish = voices.first(where: { $0.language.lowercased().hasPrefix("en-gb") }) {
            return britishEnglish
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

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        finishSpeech(utterance)
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        finishSpeech(utterance)
    }

    private func finishSpeech(_ utterance: AVSpeechUtterance) {
        guard currentUtterance === utterance else { return }
        currentUtterance = nil
        isSpeaking = false
        completion?.resume()
        completion = nil
        audioRouteManager.refresh()
    }
}
