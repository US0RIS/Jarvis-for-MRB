import AVFoundation

@MainActor
final class SpeechSynthesizer: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published private(set) var isSpeaking = false

    private let synthesizer = AVSpeechSynthesizer()
    private let audioRouteManager: AudioRouteManager
    private var completion: CheckedContinuation<Void, Never>?

    init(audioRouteManager: AudioRouteManager) {
        self.audioRouteManager = audioRouteManager
        super.init()
        synthesizer.delegate = self
    }

    func speak(_ text: String, preferBluetooth: Bool) async {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }

        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
            finishPendingSpeech()
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

        isSpeaking = true
        await withCheckedContinuation { continuation in
            completion = continuation
            synthesizer.speak(utterance)
        }
    }

    func stopSpeaking() {
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        finishPendingSpeech()
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        finishPendingSpeech()
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        finishPendingSpeech()
    }

    private func finishPendingSpeech() {
        isSpeaking = false
        completion?.resume()
        completion = nil
        audioRouteManager.refresh()
    }
}
