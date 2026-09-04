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
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = 0.5
        utterance.preUtteranceDelay = 0.04

        currentUtterance = utterance
        isSpeaking = true
        await withCheckedContinuation { continuation in
            completion = continuation
            synthesizer.speak(utterance)
        }
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
