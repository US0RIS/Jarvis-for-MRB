import AVFoundation
import Speech

@MainActor
enum JarvisAudioEnvironment {
    static var noiseFloorDBFS: Double = -55.0
}

private func jarvisAverageDBFS(_ buffer: AVAudioPCMBuffer) -> Double {
    guard let channels = buffer.floatChannelData,
          buffer.frameLength > 0 else { return -80.0 }
    let samples = channels[0]
    let count = Int(buffer.frameLength)
    var sum: Double = 0
    for index in 0..<count {
        let value = Double(samples[index])
        sum += value * value
    }
    let rms = sqrt(sum / Double(count))
    guard rms > 0.00001 else { return -80.0 }
    return max(-80.0, min(0.0, 20.0 * log10(rms)))
}

/// How much barge-in the current output route can safely support.
enum BargeInPolicy: Equatable {
    /// Private route (headphones/Bluetooth): free-form interruption and stop commands.
    case fullConversation
    /// Loudspeaker with echo-cancelled voice-chat mode requested: only stop/wait commands.
    case commandsOnly
    /// No private route and no voice-processing session: do not listen while speaking.
    case disabled
}

@MainActor
final class AudioRouteManager: ObservableObject {
    @Published private(set) var currentInputName = "No input"
    @Published private(set) var currentOutputName = "No output"
    @Published private(set) var isUsingBluetoothHFP = false
    @Published private(set) var isUsingBuiltInMic = false
    @Published private(set) var hasBluetoothHFP = false
    /// True while the output is headphones or a Bluetooth device (nobody else can hear it).
    @Published private(set) var isPrivateOutput = false
    /// Set when a private output disappeared (`.oldDeviceUnavailable`). While set, Horus
    /// refuses to speak so private speech never jumps to the loudspeaker.
    @Published private(set) var privateOutputLost = false

    /// Called immediately when headphones/Bluetooth output is lost.
    var onPrivateOutputLost: (() -> Void)?
    /// Called when a private output returns after a loss.
    var onPrivateOutputRestored: (() -> Void)?

    private var routeChangeTask: Task<Void, Never>?
    private var inputsChangeTask: Task<Void, Never>?

    /// Barge-in is only allowed on a private route, or (stop commands only) when the
    /// session is in echo-cancelling voice-chat mode. This is a request to iOS, not
    /// proof that the echo canceller removed Horus's own voice.
    var bargeInPolicy: BargeInPolicy {
        if isPrivateOutput { return .fullConversation }
        if AVAudioSession.sharedInstance().mode == .voiceChat { return .commandsOnly }
        return .disabled
    }

    /// Explicit user choice after a headphone disconnect: allow speech on the iPhone speaker.
    func allowSpeakerOutputAfterLoss() {
        privateOutputLost = false
    }

    private static func isPrivatePort(_ type: AVAudioSession.Port) -> Bool {
        switch type {
        case .headphones, .bluetoothA2DP, .bluetoothHFP, .bluetoothLE:
            return true
        default:
            return false
        }
    }

    init() {
        refresh()
        observeRouteChanges()
    }

    var routeSummary: String {
        if isUsingBuiltInMic {
            return "\(currentInputName) (iPhone built-in mic) → \(currentOutputName)"
        }
        if isUsingBluetoothHFP {
            return "\(currentInputName) (Bluetooth hands-free)"
        }
        return "\(currentInputName) → \(currentOutputName)"
    }

    func prepareForVoice(preferBluetooth: Bool) throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(
            .playAndRecord,
            mode: .voiceChat,
            // HFP carries the headset microphone. A2DP must also be allowed so that, when the
            // user chose the iPhone microphone, replies still go to the AirPods instead of
            // falling back to the loudspeaker.
            options: [.allowBluetoothHFP, .allowBluetoothA2DP, .defaultToSpeaker]
        )
        try session.setActive(true, options: .notifyOthersOnDeactivation)

        if preferBluetooth,
           let bluetoothInput = preferredBluetoothInput(in: session.availableInputs ?? []) {
            try session.setPreferredInput(bluetoothInput)
        } else if !preferBluetooth,
                  let builtInInput = preferredBuiltInInput(in: session.availableInputs ?? []) {
            // Explicitly leave HFP when the user has asked for the phone microphone.
            // Merely omitting setPreferredInput() can leave the previous Ray-Ban HFP
            // route active after a hands-free session.
            try session.setPreferredInput(builtInInput)
        }

        refresh()
    }

    /// Configure a far-field/room capture session.
    ///
    /// Ray-Ban HFP microphones are optimized for the wearer. Meeting Notes and other
    /// ambient capture need the microphones physically exposed to the room, so this
    /// profile deliberately removes HFP as an input option and selects the iPhone's
    /// built-in microphone. Bluetooth A2DP remains allowed for output where iOS can
    /// support it independently from the built-in input.
    func prepareForRoomCapture() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(
            .playAndRecord,
            mode: .measurement,
            options: [.allowBluetoothA2DP, .defaultToSpeaker]
        )
        try session.setActive(true, options: .notifyOthersOnDeactivation)

        guard let builtInInput = preferredBuiltInInput(in: session.availableInputs ?? []) else {
            throw NSError(
                domain: "JarvisAudio",
                code: 20,
                userInfo: [NSLocalizedDescriptionKey: "The iPhone built-in microphone is unavailable for room capture."]
            )
        }
        try session.setPreferredInput(builtInInput)
        refresh()
    }

    /// Release a finished one-shot input session instead of holding a
    /// playAndRecord route open while Horus is idle.
    @discardableResult
    func releaseOneShotVoiceSession() -> Bool {
        var released = true
        do {
            try AVAudioSession.sharedInstance().setActive(
                false, options: .notifyOthersOnDeactivation
            )
        } catch {
            // iOS refuses while audio I/O is still running; the caller may retry later.
            released = false
        }
        refresh()
        return released
    }

    func refresh() {
        let session = AVAudioSession.sharedInstance()
        let input = session.currentRoute.inputs.first
        let output = session.currentRoute.outputs.first

        currentInputName = input?.portName ?? "No input"
        currentOutputName = output?.portName ?? "No output"
        isUsingBuiltInMic = input?.portType == .builtInMic
        isUsingBluetoothHFP = input?.portType == .bluetoothHFP || output?.portType == .bluetoothHFP
        hasBluetoothHFP = (session.availableInputs ?? []).contains { $0.portType == .bluetoothHFP }
        isPrivateOutput = session.currentRoute.outputs.contains { Self.isPrivatePort($0.portType) }
    }

    private func handleRouteChange(_ note: Notification) {
        let wasPrivate = isPrivateOutput
        refresh()

        var reason: AVAudioSession.RouteChangeReason?
        if let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt {
            reason = AVAudioSession.RouteChangeReason(rawValue: raw)
        }
        var previousWasPrivate = wasPrivate
        if let previous = note.userInfo?[AVAudioSessionRouteChangePreviousRouteKey] as? AVAudioSessionRouteDescription {
            previousWasPrivate = previous.outputs.contains { Self.isPrivatePort($0.portType) }
        }

        if reason == .oldDeviceUnavailable, previousWasPrivate, !isPrivateOutput {
            // Headphones/earbuds were disconnected. Latch the loss before anything else
            // can start speaking, then let the app stop the current utterance.
            privateOutputLost = true
            onPrivateOutputLost?()
        } else if isPrivateOutput, privateOutputLost {
            privateOutputLost = false
            onPrivateOutputRestored?()
        }
    }

    private func preferredBluetoothInput(in inputs: [AVAudioSessionPortDescription]) -> AVAudioSessionPortDescription? {
        let bluetoothInputs = inputs.filter { $0.portType == .bluetoothHFP }
        return bluetoothInputs.first(where: {
            let name = $0.portName.lowercased()
            return name.contains("ray-ban") || name.contains("rayban") || name.contains("meta")
        }) ?? bluetoothInputs.first
    }

    private func preferredBuiltInInput(in inputs: [AVAudioSessionPortDescription]) -> AVAudioSessionPortDescription? {
        inputs.first { $0.portType == .builtInMic }
    }

    private func observeRouteChanges() {
        routeChangeTask?.cancel()
        routeChangeTask = Task { [weak self] in
            for await note in NotificationCenter.default.notifications(named: AVAudioSession.routeChangeNotification) {
                guard !Task.isCancelled, let self else { return }
                self.handleRouteChange(note)
            }
        }

        if #available(iOS 26.0, *) {
            inputsChangeTask?.cancel()
            inputsChangeTask = Task { [weak self] in
                for await _ in NotificationCenter.default.notifications(named: AVAudioSession.availableInputsChangeNotification) {
                    guard !Task.isCancelled, let self else { return }
                    self.refresh()
                }
            }
        }
    }
}

@MainActor
final class SpeechRecognizer: ObservableObject {
    @Published private(set) var transcript = ""
    @Published private(set) var isActive = false
    @Published private(set) var lastError: String?
    @Published private(set) var ambientLevelDBFS: Double = -80.0
    @Published private(set) var ambientNoiseFloorDBFS: Double = -55.0
    @Published private(set) var transcriptionConfidence: Double = 0
    @Published private(set) var lastResultWasFinal = false
    @Published private(set) var lastRecognitionUpdate: Date?

    /// Called after an interruption (call, Siri, other app) or media-services reset has
    /// already stopped capture. The Bool is true for a media-services reset.
    var onAudioSessionInterrupted: ((String, Bool) -> Void)?
    /// Called when iOS reports the interruption ended. Capture is never resumed automatically.
    var onAudioSessionInterruptionEnded: ((Bool) -> Void)?

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var audioEngine = AVAudioEngine()
    private let audioRouteManager: AudioRouteManager
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var tapInstalled = false
    private var recognitionPrefix = ""
    private var interruptionTask: Task<Void, Never>?
    private var mediaResetTask: Task<Void, Never>?

    var recognitionDebugSummary: String {
        let confidence = Int(round(transcriptionConfidence * 100))
        let state = isActive ? "active" : "idle"
        let final = lastResultWasFinal ? "final" : "partial"
        return "ASR \(state) • \(confidence)% confidence • \(final)"
    }

    init(audioRouteManager: AudioRouteManager) {
        self.audioRouteManager = audioRouteManager
        observeAudioLifecycle()
    }

    /// Domain/codes of the permission errors thrown by `requestPermissions()`.
    /// Code 1 = speech recognition denied/restricted, code 2 = microphone denied.
    /// Callers treat both as "fall back to typed input", never as a crash.
    static let permissionErrorDomain = "JarvisSpeech"
    static func isPermissionError(_ error: Error) -> Bool {
        let ns = error as NSError
        return ns.domain == permissionErrorDomain && (ns.code == 1 || ns.code == 2)
    }

    func requestPermissions() async throws {
        let speechStatus = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard speechStatus == .authorized else {
            let message: String
            switch speechStatus {
            case .restricted:
                message = "Speech recognition is restricted on this iPhone (Screen Time or a device policy)."
            case .denied:
                message = "Speech recognition is turned off for Horus in iOS Settings."
            default:
                message = "Speech recognition permission is required."
            }
            throw NSError(domain: Self.permissionErrorDomain, code: 1, userInfo: [NSLocalizedDescriptionKey: message])
        }

        let micGranted = await AVAudioApplication.requestRecordPermission()
        guard micGranted else {
            throw NSError(domain: Self.permissionErrorDomain, code: 2, userInfo: [NSLocalizedDescriptionKey: "Microphone access is turned off for Horus in iOS Settings."])
        }
    }

    func startListening(preferBluetooth: Bool) throws {
        try startListening {
            try audioRouteManager.prepareForVoice(preferBluetooth: preferBluetooth)
        }
    }

    /// Start speech recognition using the iPhone as a room-facing microphone.
    /// This is deliberately separate from wearer-command capture so Meeting Notes
    /// cannot silently inherit the Ray-Ban HFP input selected by hands-free mode.
    func startRoomListening() throws {
        try startListening {
            try audioRouteManager.prepareForRoomCapture()
        }
    }

    private func startListening(prepareAudio: () throws -> Void) throws {
        AmbientSoundCapture.shared.stop()
        LocalSoundClassifier.shared.resetStream()
        stopAudioOnly(cancelRecognition: true)
        recognitionPrefix = BargeInBuffer.take()
        transcript = recognitionPrefix
        lastError = nil
        transcriptionConfidence = 0
        lastResultWasFinal = false
        lastRecognitionUpdate = nil

        guard let recognizer, recognizer.isAvailable else {
            throw NSError(domain: "JarvisSpeech", code: 3, userInfo: [NSLocalizedDescriptionKey: "Speech recognition is temporarily unavailable."])
        }

        try prepareAudio()

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        request.contextualStrings = Array(Set(["Horus", "Dubeck", "Emmett Dubeck"] + PersonalVocabularyStore.values()))
        if recognizer.supportsOnDeviceRecognition {
            request.requiresOnDeviceRecognition = true
        }
        self.request = request

        let input = audioEngine.inputNode
        let format = input.inputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            self.request = nil
            recognitionPrefix = ""
            throw NSError(domain: "JarvisSpeech", code: 4, userInfo: [NSLocalizedDescriptionKey: "The selected microphone is not ready yet. Try again in a moment."])
        }

        removeInputTapIfNeeded()
        // Bluetooth HFP can renegotiate its format asynchronously. A nil tap
        // format binds to the node's live native format and avoids iOS 27's
        // uncaught "Failed to create tap due to format mismatch" exception.
        input.installTap(onBus: 0, bufferSize: 1024, format: nil) { [weak self] buffer, when in
            request.append(buffer)
            LocalAudioRingBuffer.shared.append(buffer)
            LocalSoundClassifier.shared.analyze(buffer, at: when.sampleTime)
            let db = jarvisAverageDBFS(buffer)
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.ambientLevelDBFS = (self.ambientLevelDBFS * 0.82) + (db * 0.18)
                if self.transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    self.ambientNoiseFloorDBFS = (self.ambientNoiseFloorDBFS * 0.94) + (db * 0.06)
                    JarvisAudioEnvironment.noiseFloorDBFS = self.ambientNoiseFloorDBFS
                }
            }
        }
        tapInstalled = true

        audioEngine.prepare()
        do {
            try audioEngine.start()
            isActive = true
        } catch {
            stopAudioOnly(cancelRecognition: true)
            throw error
        }

        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor in
                guard let self else { return }
                if let result {
                    let corrected = Self.applyPersonalVocabulary(
                        to: result.bestTranscription.formattedString
                    )
                    self.transcript = Self.joinPrefix(self.recognitionPrefix, corrected)
                    let segments = result.bestTranscription.segments
                    if !segments.isEmpty {
                        let total = segments.reduce(0.0) { $0 + Double($1.confidence) }
                        self.transcriptionConfidence = max(0, min(1, total / Double(segments.count)))
                    }
                    self.lastResultWasFinal = result.isFinal
                    self.lastRecognitionUpdate = Date()
                    LocalSpeechHistoryStore.shared.record(self.transcript, confidence: self.transcriptionConfidence)
                }
                if let error {
                    self.lastError = error.localizedDescription
                }
                if error != nil || result?.isFinal == true {
                    self.stopAudioOnly(cancelRecognition: false)
                }
            }
        }
    }

    @discardableResult
    func stopListening() -> String {
        let final = transcript
        stopAudioOnly(cancelRecognition: true)
        return final
    }

    private static func applyPersonalVocabulary(to text: String) -> String {
        var corrected = text
        corrected = corrected.replacingOccurrences(
            of: "\\b(?:dubek|du beck)\\b",
            with: "Dubeck",
            options: [.regularExpression, .caseInsensitive]
        )
        return corrected
    }

    private static func joinPrefix(_ prefix: String, _ continuation: String) -> String {
        let a = prefix.trimmingCharacters(in: .whitespacesAndNewlines)
        let b = continuation.trimmingCharacters(in: .whitespacesAndNewlines)
        if a.isEmpty { return b }
        if b.isEmpty { return a }

        let aWords = a.split(separator: " ")
        let bWords = b.split(separator: " ")
        if let last = aWords.last, let first = bWords.first,
           last.compare(first, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame {
            return a + " " + bWords.dropFirst().joined(separator: " ")
        }
        return a + " " + b
    }

    private func stopAudioOnly(cancelRecognition: Bool) {
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        removeInputTapIfNeeded()
        request?.endAudio()
        request = nil
        if cancelRecognition {
            task?.cancel()
        }
        task = nil
        isActive = false
        recognitionPrefix = ""
        audioRouteManager.refresh()
    }

    private func removeInputTapIfNeeded() {
        guard tapInstalled else { return }
        audioEngine.inputNode.removeTap(onBus: 0)
        tapInstalled = false
    }

    private func observeAudioLifecycle() {
        interruptionTask?.cancel()
        interruptionTask = Task { [weak self] in
            for await note in NotificationCenter.default.notifications(named: AVAudioSession.interruptionNotification) {
                guard !Task.isCancelled, let self else { return }
                guard let rawType = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                      let type = AVAudioSession.InterruptionType(rawValue: rawType) else { continue }
                if type == .began {
                    self.lastError = "Audio interrupted"
                    self.stopAudioOnly(cancelRecognition: true)
                    self.onAudioSessionInterrupted?("Audio interrupted by a call, Siri or another app.", false)
                } else if type == .ended {
                    var shouldResume = false
                    if let rawOptions = note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt {
                        shouldResume = AVAudioSession.InterruptionOptions(rawValue: rawOptions).contains(.shouldResume)
                    }
                    self.onAudioSessionInterruptionEnded?(shouldResume)
                }
            }
        }

        mediaResetTask?.cancel()
        mediaResetTask = Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: AVAudioSession.mediaServicesWereResetNotification) {
                guard !Task.isCancelled, let self else { return }
                self.lastError = "Audio system restarted"
                self.stopAudioOnly(cancelRecognition: true)
                // Every AVFoundation object is invalid after a reset: rebuild the engine.
                self.audioEngine = AVAudioEngine()
                self.tapInstalled = false
                self.onAudioSessionInterrupted?("The iOS audio system restarted.", true)
            }
        }
    }
}
