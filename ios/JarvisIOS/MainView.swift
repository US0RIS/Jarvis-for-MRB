import SwiftUI

struct MainView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @EnvironmentObject private var persistentPresence: PersistentPresenceController
    @EnvironmentObject private var meetingCapture: MeetingCaptureController
    @EnvironmentObject private var frontend: FrontendIntelligenceController
    @State private var showingSettings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    connectionCard
                    commandCard
                    meetingCard
                    responseCard
                    persistentPresenceCard
                    FrontendIntelligenceCard()
                    MetaGlassesCard(manager: appModel.metaGlasses)
                    GeofenceCard(manager: appModel.geofenceManager)
                }
                .padding()
            }
            .navigationTitle("Jarvis")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingSettings = true } label: { Image(systemName: "gearshape") }
                }
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView(settings: appModel.settings, geofence: appModel.geofenceManager)
            }
            .alert("Jarvis", isPresented: Binding(
                get: { appModel.errorMessage != nil },
                set: { if !$0 { appModel.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { appModel.errorMessage = nil }
            } message: {
                Text(appModel.errorMessage ?? "")
            }
            .onOpenURL { url in Task { await appModel.metaGlasses.handleURL(url) } }
        }
    }

    private var connectionCard: some View {
        GroupBox("Jarvis Server") {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(appModel.connectionStatus).font(.headline)
                        Text(persistentPresence.activeServerURL.isEmpty ? appModel.settings.baseURL : persistentPresence.activeServerURL)
                            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer()
                    Button("Check") {
                        Task {
                            await appModel.checkConnection()
                            await frontend.probeConnections()
                        }
                    }
                    .buttonStyle(.bordered)
                }
                LabeledContent("Companion", value: persistentPresence.companionStatus)
                    .font(.caption).foregroundStyle(.secondary)
                LabeledContent("Route probe", value: frontend.connectivityStatus)
                    .font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private var commandCard: some View {
        GroupBox("Voice & Commands") {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    TextField("Ask Jarvis to do something…", text: $appModel.commandText, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .submitLabel(.send)
                        .onSubmit { Task { await appModel.sendCurrentCommand() } }
                    Button { Task { await appModel.sendCurrentCommand() } } label: {
                        Image(systemName: "arrow.up.circle.fill").font(.title2)
                    }
                    .disabled(appModel.commandText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || appModel.isSending)
                }

                HStack(spacing: 12) {
                    Button {
                        Task { await appModel.togglePushToTalk() }
                    } label: {
                        Label(appModel.isListening && !appModel.handsFreeEnabled ? "Stop & Send" : "Push to Talk", systemImage: appModel.isListening && !appModel.handsFreeEnabled ? "stop.circle.fill" : "mic.circle.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(appModel.handsFreeEnabled || meetingCapture.isActive)

                    Toggle("Hands-free Jarvis", isOn: Binding(
                        get: { appModel.handsFreeEnabled },
                        set: { enabled in Task { await appModel.setHandsFreeEnabled(enabled) } }
                    ))
                    .labelsHidden()
                    .disabled(meetingCapture.isActive)
                }

                HStack(spacing: 8) {
                    Image(systemName: appModel.handsFreeEnabled ? "waveform.circle.fill" : "waveform.circle")
                    Text(meetingCapture.isActive ? "Meeting capture owns the microphone" : appModel.voiceStatus).font(.callout)
                }

                LabeledContent("Audio route", value: appModel.audioRouteManager.routeSummary)
                    .font(.caption).foregroundStyle(.secondary)
                LabeledContent("Noise floor", value: "\(Int(round(appModel.speechRecognizer.ambientNoiseFloorDBFS))) dBFS")
                    .font(.caption).foregroundStyle(.secondary)
                LabeledContent("Speech recognition", value: appModel.speechRecognizer.recognitionDebugSummary)
                    .font(.caption).foregroundStyle(.secondary)

                if appModel.speechSynthesizer.isWhispering {
                    Label("Adaptive/forced whisper active", systemImage: "speaker.wave.1")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if appModel.settings.subvocalModeEnabled {
                    Label("Quiet-speech mode enabled", systemImage: "waveform.badge.mic")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if appModel.settings.preferBluetoothAudio && !appModel.audioRouteManager.hasBluetoothHFP && appModel.handsFreeEnabled {
                    Text("No Bluetooth hands-free microphone is currently available, so Jarvis is using the iPhone audio route.")
                        .font(.caption).foregroundStyle(.orange)
                }
                if appModel.isListening && !meetingCapture.isActive {
                    SpeechTranscriptView(recognizer: appModel.speechRecognizer, wakeMode: appModel.handsFreeEnabled)
                }
                if !appModel.lastHeardCommand.isEmpty {
                    Text("Last heard: \(appModel.lastHeardCommand)").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
    }

    private var meetingCard: some View {
        GroupBox("Meeting Notes") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label(
                        meetingCapture.isActive ? (meetingCapture.isPaused ? "Paused" : "Recording locally") : "Off",
                        systemImage: meetingCapture.isActive ? "record.circle.fill" : "record.circle"
                    )
                    .foregroundStyle(meetingCapture.isActive && !meetingCapture.isPaused ? .red : .secondary)
                    Spacer()
                    if meetingCapture.isActive {
                        Text(meetingCapture.elapsedText)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }

                HStack {
                    if meetingCapture.isActive {
                        Button(meetingCapture.isPaused ? "Resume" : "Pause") {
                            Task {
                                if meetingCapture.isPaused { await meetingCapture.resume() }
                                else { await meetingCapture.pause() }
                            }
                        }
                        .buttonStyle(.bordered)

                        Button("Bookmark") { meetingCapture.addBookmark() }
                            .buttonStyle(.bordered)
                            .disabled(meetingCapture.isPaused)

                        Button("Stop", role: .destructive) {
                            Task { await meetingCapture.stop() }
                        }
                        .buttonStyle(.bordered)
                    } else {
                        Button("Start Meeting Notes") {
                            Task { await meetingCapture.start() }
                        }
                        .buttonStyle(.borderedProminent)

                        if meetingCapture.syncPending {
                            Button("Sync & Extract") {
                                Task { await meetingCapture.syncOfflineTranscript() }
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }

                Text(meetingCapture.status)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if meetingCapture.isActive && !meetingCapture.liveTranscript.isEmpty {
                    Text(meetingCapture.liveTranscript)
                        .font(.caption)
                        .lineLimit(4)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                if !meetingCapture.bookmarks.isEmpty {
                    Text("Bookmarks: " + meetingCapture.bookmarks.map { $0.label }.joined(separator: " • "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                if !meetingCapture.exportText.isEmpty {
                    ShareLink(item: meetingCapture.exportText) {
                        Label("Share Local Transcript", systemImage: "square.and.arrow.up")
                    }
                    .font(.caption)
                }

                Text("Meeting transcription is explicit opt-in and visibly active. The iPhone now keeps its own local transcript buffer, pause/resume state and bookmarks. If the PC is unreachable, capture can continue locally and be synchronized later. It does not identify speakers by voiceprint or infer emotion/stress. Use recording only where permitted and with appropriate participant notice/consent.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var responseCard: some View {
        GroupBox("Last Response") {
            VStack(alignment: .leading, spacing: 6) {
                Text(appModel.lastResponse.isEmpty ? "No response yet." : appModel.lastResponse)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
                Text(appModel.lastLatency.compactDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var persistentPresenceCard: some View {
        GroupBox("Persistent Presence") {
            VStack(alignment: .leading, spacing: 8) {
                LabeledContent("Passive vision", value: appModel.settings.passiveVisionEnabled ? persistentPresence.visionStatus : "Off")
                LabeledContent("Remote path", value: persistentPresence.companionStatus)
                LabeledContent("Interrupt threshold", value: appModel.settings.proactiveThreshold.capitalized)

                Button {
                    Task { await persistentPresence.requestSilentScan() }
                } label: {
                    Label("Send Backend Visual Scan", systemImage: "eye")
                }
                .buttonStyle(.bordered)
                .disabled(!appModel.metaGlasses.isRegistered || !appModel.metaGlasses.hasEligibleDevice)

                if !persistentPresence.lastVisionScene.isEmpty {
                    Text("Backend scene: \(persistentPresence.lastVisionScene)")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if !persistentPresence.lastProactiveMessage.isEmpty {
                    Text("Last proactive observation: \(persistentPresence.lastProactiveMessage)")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if appModel.settings.healthContextEnabled {
                    LabeledContent("Apple Health", value: persistentPresence.healthContext.status)
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct MeetingBookmark: Identifiable, Equatable {
    let id = UUID()
    let seconds: Int
    let snippet: String

    var label: String {
        let minutes = seconds / 60
        let remainder = seconds % 60
        let time = String(format: "%d:%02d", minutes, remainder)
        return snippet.isEmpty ? time : "\(time) \(snippet)"
    }
}

@MainActor
final class MeetingCaptureController: ObservableObject {
    @Published private(set) var isActive = false
    @Published private(set) var isPaused = false
    @Published private(set) var status = "Not recording"
    @Published private(set) var meetingID: Int?
    @Published private(set) var liveTranscript = ""
    @Published private(set) var localTranscript = ""
    @Published private(set) var elapsedSeconds: Int = 0
    @Published private(set) var bookmarks: [MeetingBookmark] = []
    @Published private(set) var syncPending = false

    private unowned let appModel: JarvisAppModel
    private let recognizer: SpeechRecognizer
    private var captureTask: Task<Void, Never>?
    private var resumeHandsFree = false
    private var isStopping = false
    private var startedAt: Date?
    private var currentChunkStartedAt = Date()

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
        recognizer = SpeechRecognizer(audioRouteManager: appModel.audioRouteManager)
    }

    var elapsedText: String {
        let minutes = elapsedSeconds / 60
        let seconds = elapsedSeconds % 60
        return String(format: "%d:%02d", minutes, seconds)
    }

    var exportText: String {
        guard !localTranscript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return "" }
        var value = localTranscript
        if !bookmarks.isEmpty {
            value += "\n\nBookmarks:\n" + bookmarks.map { "- \($0.label)" }.joined(separator: "\n")
        }
        return value
    }

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    func start(title: String = "") async {
        guard !isActive, !isStopping else { return }
        status = "Starting…"
        do {
            try await recognizer.requestPermissions()
            resumeHandsFree = appModel.handsFreeEnabled
            if appModel.handsFreeEnabled { appModel.stopWakeWordMode() }
            if appModel.speechRecognizer.isActive {
                _ = appModel.speechRecognizer.stopListening()
                appModel.isListening = false
            }

            localTranscript = ""
            liveTranscript = ""
            bookmarks = []
            syncPending = false
            elapsedSeconds = 0
            startedAt = Date()
            currentChunkStartedAt = Date()

            do {
                let response = try await client.startMeeting(title: title)
                meetingID = response.meetingID
                status = "Recording locally • session \(response.meetingID)"
            } catch {
                guard appModel.settings.offlineMeetingCaptureEnabled else { throw error }
                meetingID = nil
                syncPending = true
                status = "Recording locally • PC unavailable"
            }

            try recognizer.startListening(preferBluetooth: appModel.settings.preferBluetoothAudio)
            isActive = true
            isPaused = false
            captureTask = Task { [weak self] in
                guard let self else { return }
                await self.captureLoop()
            }
        } catch {
            status = "Could not start meeting notes: \(error.localizedDescription)"
            meetingID = nil
            isActive = false
            startedAt = nil
            if resumeHandsFree {
                resumeHandsFree = false
                await appModel.startWakeWordMode()
            }
        }
    }

    func pause() async {
        guard isActive, !isPaused else { return }
        await persistCurrentChunk()
        isPaused = true
        status = meetingID == nil ? "Paused • local-only" : "Paused"
    }

    func resume() async {
        guard isActive, isPaused else { return }
        do {
            try recognizer.startListening(preferBluetooth: appModel.settings.preferBluetoothAudio)
            currentChunkStartedAt = Date()
            isPaused = false
            status = meetingID.map { "Recording locally • session \($0)" } ?? "Recording locally • PC unavailable"
        } catch {
            status = "Could not resume microphone: \(error.localizedDescription)"
        }
    }

    func addBookmark() {
        guard isActive else { return }
        let snippet = liveTranscript.split(separator: " ").suffix(8).joined(separator: " ")
        bookmarks.append(MeetingBookmark(seconds: elapsedSeconds, snippet: snippet))
        if bookmarks.count > 40 { bookmarks.removeFirst(bookmarks.count - 40) }
    }

    func stop() async {
        guard isActive, !isStopping else { return }
        isStopping = true
        isActive = false
        isPaused = false
        captureTask?.cancel()
        captureTask = nil
        await persistCurrentChunk()
        _ = saveLocalTranscriptSnapshot()

        if syncPending || meetingID == nil {
            status = "Meeting saved locally • sync pending"
            meetingID = nil
            isStopping = false
            startedAt = nil
            await restoreHandsFreeIfNeeded()
            return
        }

        guard let id = meetingID else {
            status = "Meeting capture stopped"
            isStopping = false
            startedAt = nil
            await restoreHandsFreeIfNeeded()
            return
        }

        status = "Extracting action items…"
        do {
            let response = try await client.finishMeeting(meetingID: id)
            status = "Completed • session \(id)"
            appModel.lastResponse = response.message
        } catch {
            status = "Meeting saved locally • extraction unavailable"
            syncPending = true
        }
        meetingID = nil
        isStopping = false
        startedAt = nil
        await restoreHandsFreeIfNeeded()
    }

    func syncOfflineTranscript() async {
        guard !isActive,
              syncPending,
              !localTranscript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        status = "Synchronizing local transcript…"
        do {
            let response = try await client.startMeeting(title: "Synced iPhone meeting")
            try await client.appendMeetingTranscript(meetingID: response.meetingID, text: localTranscript)
            let finished = try await client.finishMeeting(meetingID: response.meetingID)
            syncPending = false
            status = "Synchronized • session \(response.meetingID)"
            appModel.lastResponse = finished.message
        } catch {
            status = "Sync still unavailable: \(error.localizedDescription)"
        }
    }

    private func captureLoop() async {
        while !Task.isCancelled && isActive {
            try? await Task.sleep(for: .milliseconds(250))
            guard !Task.isCancelled && isActive else { return }
            if let startedAt { elapsedSeconds = max(0, Int(Date().timeIntervalSince(startedAt))) }
            guard !isPaused else { continue }

            let current = recognizer.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            liveTranscript = current

            if Self.containsStopCommand(current) {
                Task { @MainActor [weak self] in await self?.stop() }
                return
            }

            if !recognizer.isActive || Date().timeIntervalSince(currentChunkStartedAt) >= 20 {
                await persistCurrentChunk()
                guard isActive, !isPaused else { continue }
                do {
                    try recognizer.startListening(preferBluetooth: appModel.settings.preferBluetoothAudio)
                    currentChunkStartedAt = Date()
                    liveTranscript = ""
                    if let id = meetingID { status = "Recording locally • session \(id)" }
                    else { status = "Recording locally • PC unavailable" }
                } catch {
                    status = "Microphone interrupted • retrying"
                    try? await Task.sleep(for: .seconds(1))
                }
            }
        }
    }

    private func persistCurrentChunk() async {
        let chunk = Self.cleanedMeetingText(recognizer.stopListening())
        liveTranscript = ""
        guard !chunk.isEmpty else { return }
        localTranscript = localTranscript.isEmpty ? chunk : localTranscript + "\n" + chunk
        guard let id = meetingID, !syncPending else { return }
        do {
            try await client.appendMeetingTranscript(meetingID: id, text: chunk)
        } catch {
            syncPending = true
            status = "Recording locally • transcript sync pending"
        }
    }

    @discardableResult
    private func saveLocalTranscriptSnapshot() -> URL? {
        guard !exportText.isEmpty else { return nil }
        do {
            let fm = FileManager.default
            let base = try fm.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            let folder = base.appendingPathComponent("JarvisMeetingNotes", isDirectory: true)
            try fm.createDirectory(at: folder, withIntermediateDirectories: true)
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd-HHmmss"
            let url = folder.appendingPathComponent("meeting-\(formatter.string(from: Date())).txt")
            try exportText.write(to: url, atomically: true, encoding: .utf8)
            return url
        } catch {
            return nil
        }
    }

    private func restoreHandsFreeIfNeeded() async {
        if resumeHandsFree {
            resumeHandsFree = false
            try? await Task.sleep(for: .milliseconds(180))
            await appModel.startWakeWordMode()
        }
    }

    private static func containsStopCommand(_ text: String) -> Bool {
        let normalized = text.lowercased()
            .replacingOccurrences(of: ",", with: "")
            .replacingOccurrences(of: ".", with: "")
        return normalized.contains("jarvis stop meeting notes")
            || normalized.contains("jarvis end meeting notes")
    }

    private static func cleanedMeetingText(_ text: String) -> String {
        var value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        for phrase in ["jarvis stop meeting notes", "jarvis end meeting notes"] {
            if let range = value.range(of: phrase, options: [.caseInsensitive, .diacriticInsensitive]) {
                value = String(value[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return value
    }
}

private struct SpeechTranscriptView: View {
    @ObservedObject var recognizer: SpeechRecognizer
    let wakeMode: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                ProgressView()
                Text(wakeMode ? "Microphone active" : "Listening")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if !recognizer.transcript.isEmpty {
                Text(recognizer.transcript).font(.callout).frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct MetaGlassesCard: View {
    @ObservedObject var manager: MetaGlassesManager

    var body: some View {
        GroupBox("Meta Ray-Ban") {
            VStack(alignment: .leading, spacing: 10) {
                LabeledContent("Registration", value: manager.registrationStatus)
                LabeledContent("Glasses available", value: String(manager.availableDeviceCount))
                LabeledContent("DAT eligible", value: manager.hasEligibleDevice ? "Yes" : "Waiting")
                LabeledContent("Camera permission", value: manager.cameraPermissionStatus)
                LabeledContent("Stream", value: manager.streamState)

                if let frame = manager.currentFrame {
                    Image(uiImage: frame)
                        .resizable().scaledToFit().frame(maxWidth: .infinity)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }

                HStack {
                    if manager.isRegistered {
                        Label("Registered", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                    } else {
                        Button("Register") { Task { await manager.startRegistration() } }
                    }
                    Button("Camera Access") { Task { await manager.requestCameraPermission() } }
                        .disabled(!manager.isRegistered)
                }
                .buttonStyle(.bordered)

                HStack {
                    if manager.streamState == "Stopped" {
                        Button("Start Camera") { Task { await manager.startStream() } }
                            .disabled(!manager.isRegistered || !manager.hasEligibleDevice)
                    } else {
                        Button("Stop Camera", role: .destructive) { manager.stopStream() }
                    }
                    Button("Photo") { manager.capturePhoto() }.disabled(manager.streamState == "Stopped")
                }
                .buttonStyle(.bordered)

                if let error = manager.errorMessage {
                    Text(error).font(.caption).foregroundStyle(.red)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct GeofenceCard: View {
    @ObservedObject var manager: GeofenceManager

    var body: some View {
        GroupBox("Home Automation") {
            VStack(alignment: .leading, spacing: 8) {
                Text(manager.statusMessage).font(.callout)
                Text("Home arrival/departure can also switch the home/mobile Jarvis profile when geofenced profiles are enabled.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
