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

@MainActor
final class AudioRouteManager: ObservableObject {
    @Published private(set) var currentInputName = "No input"
    @Published private(set) var currentOutputName = "No output"
    @Published private(set) var isUsingBluetoothHFP = false
    @Published private(set) var isUsingBuiltInMic = false
    @Published private(set) var hasBluetoothHFP = false

    private var routeChangeTask: Task<Void, Never>?
    private var inputsChangeTask: Task<Void, Never>?

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
            options: [.allowBluetoothHFP, .defaultToSpeaker]
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

    func refresh() {
        let session = AVAudioSession.sharedInstance()
        let input = session.currentRoute.inputs.first
        let output = session.currentRoute.outputs.first

        currentInputName = input?.portName ?? "No input"
        currentOutputName = output?.portName ?? "No output"
        isUsingBuiltInMic = input?.portType == .builtInMic
        isUsingBluetoothHFP = input?.portType == .bluetoothHFP || output?.portType == .bluetoothHFP
        hasBluetoothHFP = (session.availableInputs ?? []).contains { $0.portType == .bluetoothHFP }
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
            for await _ in NotificationCenter.default.notifications(named: AVAudioSession.routeChangeNotification) {
                guard !Task.isCancelled, let self else { return }
                self.refresh()
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

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
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

    func requestPermissions() async throws {
        let speechStatus = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard speechStatus == .authorized else {
            throw NSError(domain: "JarvisSpeech", code: 1, userInfo: [NSLocalizedDescriptionKey: "Speech recognition permission is required."])
        }

        let micGranted = await AVAudioApplication.requestRecordPermission()
        guard micGranted else {
            throw NSError(domain: "JarvisSpeech", code: 2, userInfo: [NSLocalizedDescriptionKey: "Microphone permission is required."])
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

        guard let recognizer, recognizer.isAvailable else {
            throw NSError(domain: "JarvisSpeech", code: 3, userInfo: [NSLocalizedDescriptionKey: "Speech recognition is temporarily unavailable."])
        }

        try prepareAudio()

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        request.contextualStrings = Array(Set(["Jarvis", "Dubeck", "Emmett Dubeck"] + PersonalVocabularyStore.values()))
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
                }
            }
        }

        mediaResetTask?.cancel()
        mediaResetTask = Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: AVAudioSession.mediaServicesWereResetNotification) {
                guard !Task.isCancelled, let self else { return }
                self.lastError = "Audio system restarted"
                self.stopAudioOnly(cancelRecognition: true)
            }
        }
    }
}
