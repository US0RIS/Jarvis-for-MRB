import SwiftUI

struct MainView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @EnvironmentObject private var persistentPresence: PersistentPresenceController
    @State private var showingSettings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    connectionCard
                    commandCard
                    responseCard
                    persistentPresenceCard
                    MetaGlassesCard(manager: appModel.metaGlasses)
                    GeofenceCard(manager: appModel.geofenceManager)
                }
                .padding()
            }
            .navigationTitle("Jarvis")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
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
            .onOpenURL { url in
                Task { await appModel.metaGlasses.handleURL(url) }
            }
        }
    }

    private var connectionCard: some View {
        GroupBox("Jarvis Server") {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(appModel.connectionStatus)
                            .font(.headline)
                        Text(
                            persistentPresence.activeServerURL.isEmpty
                                ? appModel.settings.baseURL
                                : persistentPresence.activeServerURL
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    }
                    Spacer()
                    Button("Check") {
                        Task { await appModel.checkConnection() }
                    }
                    .buttonStyle(.bordered)
                }
                LabeledContent("Companion", value: persistentPresence.companionStatus)
                    .font(.caption)
                    .foregroundStyle(.secondary)
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

                    Button {
                        Task { await appModel.sendCurrentCommand() }
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
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
                    .disabled(appModel.handsFreeEnabled)

                    Toggle("Hands-free Jarvis", isOn: Binding(
                        get: { appModel.handsFreeEnabled },
                        set: { enabled in
                            Task { await appModel.setHandsFreeEnabled(enabled) }
                        }
                    ))
                    .labelsHidden()
                }

                HStack(spacing: 8) {
                    Image(systemName: appModel.handsFreeEnabled ? "waveform.circle.fill" : "waveform.circle")
                    Text(appModel.voiceStatus)
                        .font(.callout)
                }

                LabeledContent("Audio route", value: appModel.audioRouteManager.routeSummary)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if appModel.settings.preferBluetoothAudio && !appModel.audioRouteManager.hasBluetoothHFP && appModel.handsFreeEnabled {
                    Text("No Bluetooth hands-free microphone is currently available, so Jarvis is using the iPhone audio route.")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }

                if appModel.isListening {
                    SpeechTranscriptView(recognizer: appModel.speechRecognizer, wakeMode: appModel.handsFreeEnabled)
                }

                if !appModel.lastHeardCommand.isEmpty {
                    Text("Last heard: \(appModel.lastHeardCommand)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var responseCard: some View {
        GroupBox("Last Response") {
            Text(appModel.lastResponse.isEmpty ? "No response yet." : appModel.lastResponse)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
    }

    private var persistentPresenceCard: some View {
        GroupBox("Persistent Presence") {
            VStack(alignment: .leading, spacing: 8) {
                LabeledContent(
                    "Passive vision",
                    value: appModel.settings.passiveVisionEnabled ? persistentPresence.visionStatus : "Off"
                )
                LabeledContent(
                    "Remote path",
                    value: persistentPresence.companionStatus
                )
                if !persistentPresence.lastProactiveMessage.isEmpty {
                    Text("Last proactive observation: \(persistentPresence.lastProactiveMessage)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
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
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if !recognizer.transcript.isEmpty {
                Text(recognizer.transcript)
                    .font(.callout)
                    .frame(maxWidth: .infinity, alignment: .leading)
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
                        .resizable()
                        .scaledToFit()
                        .frame(maxWidth: .infinity)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }

                HStack {
                    if manager.isRegistered {
                        Label("Registered", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
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
                    Button("Photo") { manager.capturePhoto() }
                        .disabled(manager.streamState == "Stopped")
                }
                .buttonStyle(.bordered)

                if let error = manager.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
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
                Text(manager.statusMessage)
                    .font(.callout)
                Text("When iOS detects home arrival, the app posts the `home_arrival` event to Jarvis and updates its environmental state.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
