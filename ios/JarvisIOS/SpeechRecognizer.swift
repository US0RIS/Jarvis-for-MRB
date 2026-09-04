import AVFoundation
import Speech

@MainActor
final class AudioRouteManager: ObservableObject {
    @Published private(set) var currentInputName = "No input"
    @Published private(set) var currentOutputName = "No output"
    @Published private(set) var isUsingBluetoothHFP = false
    @Published private(set) var hasBluetoothHFP = false

    private var routeChangeTask: Task<Void, Never>?
    private var inputsChangeTask: Task<Void, Never>?

    init() {
        refresh()
        observeRouteChanges()
    }

    var routeSummary: String {
        if isUsingBluetoothHFP {
            return "\(currentInputName) (Bluetooth hands-free)"
        }
        return "\(currentInputName) → \(currentOutputName)"
    }

    /// Configures one full-duplex voice session. When a Bluetooth HFP microphone
    /// is available, explicitly selecting it also moves output to the matching
    /// Bluetooth HFP route on iOS. This prevents Jarvis from silently listening
    /// through the phone microphone while the Ray-Bans are connected.
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
        }

        refresh()
    }

    func refresh() {
        let session = AVAudioSession.sharedInstance()
        let input = session.currentRoute.inputs.first
        let output = session.currentRoute.outputs.first

        currentInputName = input?.portName ?? "No input"
        currentOutputName = output?.portName ?? "No output"
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

    private func observeRouteChanges() {
        routeChangeTask?.cancel()
        routeChangeTask = Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: AVAudioSession.routeChangeNotification) {
                guard !Task.isCancelled, let self else { return }
                self.refresh()
            }
        }

        // availableInputsChangeNotification was introduced in iOS 26. The app's
        // deployment target remains iOS 17+, so guard the observer even when the
        // development phone itself is running a newer iOS beta.
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

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private let audioRouteManager: AudioRouteManager
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var tapInstalled = false
    private var interruptionTask: Task<Void, Never>?
    private var mediaResetTask: Task<Void, Never>?

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
        stopAudioOnly(cancelRecognition: true)
        transcript = ""
        lastError = nil

        guard let recognizer, recognizer.isAvailable else {
            throw NSError(domain: "JarvisSpeech", code: 3, userInfo: [NSLocalizedDescriptionKey: "Speech recognition is temporarily unavailable."])
        }

        try audioRouteManager.prepareForVoice(preferBluetooth: preferBluetooth)

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        // Bias Apple's recognizer toward the words this personal assistant uses
        // frequently. This does not force a result, but materially improves names
        // and the wake word on the target user's device.
        request.contextualStrings = ["Jarvis", "Dubeck", "Emmett Dubeck"]
        if recognizer.supportsOnDeviceRecognition {
            request.requiresOnDeviceRecognition = true
        }
        self.request = request

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            self.request = nil
            throw NSError(domain: "JarvisSpeech", code: 4, userInfo: [NSLocalizedDescriptionKey: "The selected microphone is not ready yet. Try again in a moment."])
        }

        removeInputTapIfNeeded()
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
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
                    self.transcript = Self.applyPersonalVocabulary(
                        to: result.bestTranscription.formattedString
                    )
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
        // Apple Speech commonly renders the family name phonetically as "Dubek"
        // (and occasionally as two words). Jarvis is a personal assistant, so use
        // the known spelling before the transcript ever reaches the agent.
        corrected = corrected.replacingOccurrences(
            of: "\\b(?:dubek|du beck)\\b",
            with: "Dubeck",
            options: [.regularExpression, .caseInsensitive]
        )
        return corrected
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
        audioRouteManager.refresh()
    }

    private func removeInputTapIfNeeded() {
        guard tapInstalled else { return }
        audioEngine.inputNode.removeTap(onBus: 0)
        tapInstalled = false
    }

    /// Interruptions (calls, Siri, another app taking the microphone) can leave
    /// an AVAudioEngine looking active even though no more buffers arrive. Force
    /// the current recognition task to finish so Jarvis's outer hands-free loop
    /// can establish a fresh Ray-Ban route when the interruption is over.
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
