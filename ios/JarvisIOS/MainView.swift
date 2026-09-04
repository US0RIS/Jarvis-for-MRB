import SwiftUI

struct MainView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @State private var showingSettings = false
    @State private var wakeMode = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    connectionCard
                    commandCard
                    responseCard
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
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(appModel.connectionStatus)
                        .font(.headline)
                    Text(appModel.settings.baseURL)
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
            .frame(maxWidth: .infinity)
        }
    }

    private var commandCard: some View {
        GroupBox("Command") {
            VStack(spacing: 12) {
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
                        Label(appModel.isListening && !wakeMode ? "Stop & Send" : "Push to Talk", systemImage: appModel.isListening && !wakeMode ? "stop.circle.fill" : "mic.circle.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Toggle("Jarvis wake", isOn: $wakeMode)
                        .labelsHidden()
                        .onChange(of: wakeMode) { _, enabled in
                            Task {
                                if enabled {
                                    await appModel.startWakeWordMode()
                                } else {
                                    appModel.stopWakeWordMode()
                                }
                            }
                        }
                }

                if appModel.isListening {
                    SpeechTranscriptView(recognizer: appModel.speechRecognizer, wakeMode: wakeMode)
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
}

private struct SpeechTranscriptView: View {
    @ObservedObject var recognizer: SpeechRecognizer
    let wakeMode: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                ProgressView()
                Text(wakeMode ? "Listening for “Jarvis …”" : "Listening")
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
                    Button("Register") { Task { await manager.startRegistration() } }
                    Button("Camera Access") { Task { await manager.requestCameraPermission() } }
                }
                .buttonStyle(.bordered)

                HStack {
                    if manager.streamState == "Stopped" {
                        Button("Start Camera") { Task { await manager.startStream() } }
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
                Text("When iOS detects home arrival, the app posts the `home_arrival` event to Jarvis.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
