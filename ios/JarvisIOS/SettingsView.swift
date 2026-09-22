import SwiftUI

struct SettingsView: View {
    @ObservedObject var settings: SettingsStore
    @ObservedObject var geofence: GeofenceManager
    @Environment(\.dismiss) private var dismiss

    @State private var allowedRecipients: [String] = []
    @State private var newAllowedRecipient = ""
    @State private var allowlistStatus = "Loading allowed recipients…"
    @State private var isSavingAllowlist = false
    @State private var neuralVoiceStatus = "Not checked"
    @State private var useFastPlanner = false
    @State private var autoRoutePlanner = true
    @State private var plannerModelStatus = "Loading planner model…"
    @State private var isSwitchingPlanner = false

    private let fastPlannerModel = "qwen3:8b"
    private let qualityPlannerModel = "qwen3.8:27b"

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: settings.baseURL,
            fallbackBaseURL: settings.fallbackBaseURL,
            apiToken: settings.apiToken,
            sessionID: settings.conversationSessionID
        )
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Jarvis Server") {
                    TextField("Home / LAN URL", text: $settings.baseURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    TextField("Tailscale URL", text: $settings.fallbackBaseURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    SecureField("API token", text: $settings.apiToken)
                        .textInputAutocapitalization(.never)
                    Text("Jarvis tries the LAN address first and falls back to your private Tailscale URL away from home. Do not forward port 8765 or enable Funnel.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("AI Planner") {
                    Toggle(
                        "Automatic model routing",
                        isOn: Binding(
                            get: { autoRoutePlanner },
                            set: { enabled in
                                let previous = autoRoutePlanner
                                autoRoutePlanner = enabled
                                Task { await switchAutoRouting(enabled, previousValue: previous) }
                            }
                        )
                    )
                    .disabled(isSwitchingPlanner)

                    Toggle(
                        "Fast mode (Qwen3 8B)",
                        isOn: Binding(
                            get: { useFastPlanner },
                            set: { enabled in
                                let previous = useFastPlanner
                                useFastPlanner = enabled
                                Task { await switchPlannerModel(fast: enabled, previousFastValue: previous) }
                            }
                        )
                    )
                    .disabled(isSwitchingPlanner || autoRoutePlanner)

                    HStack {
                        Text("Mode")
                        Spacer()
                        if isSwitchingPlanner { ProgressView().controlSize(.small) }
                        Text(autoRoutePlanner ? "Automatic 8B ↔ 27B" : (useFastPlanner ? "Qwen3 8B" : "Qwen3.8 27B"))
                            .foregroundStyle(.secondary)
                    }
                    Text(plannerModelStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(autoRoutePlanner
                         ? "Routine voice turns stay on 8B. Hard reasoning is routed to 27B, then 8B is rewarmed for the next conversational turn. Thinking remains disabled."
                         : "Manual mode pins the selected planner model. Thinking remains disabled.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Camera-free Ambient Presence") {
                    Toggle("Proactive microphone + sensor opportunities", isOn: $settings.sensorOpportunitiesEnabled)
                    Toggle("Motion / travel context and GPS", isOn: $settings.localSensorContextEnabled)
                    Toggle("Classify environmental sounds locally", isOn: $settings.soundRecognitionEnabled)
                    Toggle("Geofenced system profiles", isOn: $settings.geofencedProfilesEnabled)
                    Toggle("Apple Watch / Health context", isOn: $settings.healthContextEnabled)
                    Toggle("Use modelled outdoor temperature (Open-Meteo)", isOn: $settings.weatherContextEnabled)
                        .disabled(!settings.sensorOpportunitiesEnabled || !settings.localSensorContextEnabled)
                    Text("The iPhone can combine separately opted-in GPS/motion, geofence events and on-device sound labels from the normal voice microphone or a foreground-only idle classifier. Only explicit standing reminders or individually preauthorized HomeKit lights may be affected. Raw audio and transcripts are not transmitted by this sensor engine. Coordinates are rounded and transient; Apple Health is read-only; outdoor temperature is a source-labelled weather model, not a thermometer in the phone or glasses.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Persistent Presence") {
                    Toggle("Passive vision", isOn: $settings.passiveVisionEnabled)
                    Toggle("Adaptive remote vision bandwidth", isOn: $settings.adaptiveBandwidthEnabled)
                    Toggle("Ambient audio HUD cues", isOn: $settings.ambientCuesEnabled)
                    Toggle("Speak proactive alerts", isOn: $settings.proactiveAnnouncements)
                    Toggle("Smart PC audio damping", isOn: $settings.smartAudioDampingEnabled)
                    Toggle("Automatic local daily journal", isOn: $settings.dailyJournalEnabled)

                    Picker("Interrupt me at", selection: $settings.proactiveThreshold) {
                        Text("Info or higher").tag("info")
                        Text("Warning or higher").tag("warning")
                        Text("Urgent only").tag("urgent")
                    }

                    TextField("Current project focus", text: $settings.projectFocus)

                    Text("Passive vision sends sampled glasses frames to the existing PC backend. The separate iPhone visual cache below does not depend on the backend and is intentionally not presented as general scene understanding.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text("Smart audio damping temporarily lowers PC output while you are actively conversing with Jarvis and restores the previous volume afterward. Daily journaling writes a concise local Markdown entry under the Jarvis AppData folder near the end of the day.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text("Health context is opt-in and read-only. Jarvis can receive recent heart rate, HRV, and sleep data from Apple Health, but it does not infer diagnoses, stress, or emotional state from those values.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("iPhone-only Intelligence") {
                    NavigationLink {
                        LocalPowerFeaturesView()
                    } label: {
                        Label("Power Features", systemImage: "bolt.shield.fill")
                    }
                    NavigationLink {
                        LocalProductivityView()
                    } label: {
                        Label("Local Executive", systemImage: "list.bullet.clipboard.fill")
                    }

                    Toggle("30-second on-device visual cache", isOn: $settings.localVisualHistoryEnabled)
                    Toggle("Continuous on-device fast perception", isOn: $settings.localFastPerceptionEnabled)
                    Toggle("Offline command staging", isOn: $settings.offlineQueueEnabled)
                    Toggle("Local voice command aliases", isOn: $settings.localCommandAliasesEnabled)
                    Toggle("Frontend diagnostics", isOn: $settings.frontendDiagnosticsEnabled)
                    Toggle("Allow offline meeting capture", isOn: $settings.offlineMeetingCaptureEnabled)

                    Divider()

                    Toggle("Recognize explicitly enrolled people", isOn: $settings.knownPeopleRecognitionEnabled)
                    NavigationLink("Manage Known People") {
                        KnownPeopleView()
                    }
                    if settings.knownPeopleRecognitionEnabled {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Known-person match tolerance: \(String(format: "%.2f", settings.knownPeopleTolerance))×")
                                .font(.caption)
                            Slider(value: $settings.knownPeopleTolerance, in: 1.15 ... 2.2, step: 0.05)
                            Text("Lower is stricter. Keep this near the default unless a deliberately enrolled person is consistently missed.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Toggle("Prepare local known-person briefings", isOn: $settings.knownPersonBriefingsEnabled)
                    Toggle("Speak known-person briefings aloud", isOn: $settings.spokenKnownPersonBriefingsEnabled)
                        .disabled(!settings.knownPersonBriefingsEnabled)
                    Toggle("Capture local post-encounter context", isOn: $settings.localEncounterCaptureEnabled)

                    Divider()

                    Toggle("30-second RAM-only rolling audio memory", isOn: $settings.rollingAudioMemoryEnabled)
                    Toggle("Detect major visual scene changes", isOn: $settings.visualChangeDetectionEnabled)
                    if settings.visualChangeDetectionEnabled {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Visual-change sensitivity threshold: \(String(format: "%.2f", settings.visualChangeThreshold))")
                                .font(.caption)
                            Slider(value: $settings.visualChangeThreshold, in: 0.20 ... 0.80, step: 0.02)
                            Text("Lower values flag more changes. This compares whole-frame Apple Vision feature prints; it is not semantic object tracking.")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }

                    Toggle("Auto-recognize enrolled inventory items", isOn: $settings.personalInventoryAutoRecognitionEnabled)
                    Toggle("Alert on enrolled item notes/warnings", isOn: $settings.inventoryKnowledgeAlertsEnabled)
                        .disabled(!settings.personalInventoryAutoRecognitionEnabled)
                    Toggle("Use Apple on-device model when PC is offline", isOn: $settings.offlineAppleBrainEnabled)
                    Toggle("Speak contextual local reminders", isOn: $settings.speakContextualRemindersEnabled)
                    Toggle("Automatically recover frontend camera/voice", isOn: $settings.frontendAutoRecoveryEnabled)

                    Text("Known People remains closed-set and opt-in: the iPhone only compares visible faces with profiles you explicitly enroll. Feature prints stay private on this device; raw enrollment photos are discarded.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text("Rolling microphone audio is off by default and remains in RAM for roughly 30 seconds. It is written to storage only when you explicitly save an incident; incident files are encrypted on this device. Local post-encounter capture is also off by default.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text("On-device fast perception uses Apple's Vision framework for OCR, QR/barcode decoding, human/face counts without identity, rectangle detection and visual saliency. It does not replace Moondream for general scene understanding.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text("The Apple on-device fallback can answer suitable local/general requests when the PC is unreachable, but it has no network, Gmail, Calendar or PC-control authority and must not claim external actions occurred.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Text("Offline staging never executes commands automatically when connectivity returns. A queued command must be sent explicitly from the app or by asking Jarvis to send the queued command.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Voice & Privacy") {
                    Toggle("Speak Jarvis responses", isOn: $settings.speakResponses)
                    Toggle("Prefer Ray-Ban / Bluetooth microphone", isOn: $settings.preferBluetoothAudio)
                    Toggle("Adaptive whisper mode", isOn: $settings.adaptiveWhisperEnabled)
                    Toggle("Quiet-speech mode", isOn: $settings.subvocalModeEnabled)
                    Toggle("Adapt HUD cue volume to room noise", isOn: $settings.adaptiveCueVolumeEnabled)

                    VStack(alignment: .leading) {
                        Text("HUD cue volume: \(Int(settings.cueVolume * 100))%")
                            .font(.caption)
                        Slider(value: $settings.cueVolume, in: 0.1 ... 1.5, step: 0.05)
                    }

                    if settings.adaptiveWhisperEnabled {
                        VStack(alignment: .leading) {
                            Text("Whisper threshold: \(Int(settings.whisperThresholdDBFS)) dBFS")
                                .font(.caption)
                            Slider(value: $settings.whisperThresholdDBFS, in: -60 ... -25, step: 1)
                        }
                    }

                    HStack {
                        Text("Neural voice")
                        Spacer()
                        Text(neuralVoiceStatus)
                            .foregroundStyle(neuralVoiceStatus == "Kokoro ready" ? Color.green : Color.secondary)
                    }
                    Button("Check Neural Voice") { Task { await checkNeuralVoice() } }

                    Text("Adaptive whisper lowers Kokoro playback volume and apparent pitch when the measured noise floor is quiet. You can also say 'whisper for 10 minutes' as a local iPhone command. Quiet-speech mode remains acoustic speech, not EMG/subvocal thought decoding.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Email Safety") {
                    Text("Jarvis can send email only to exact addresses on this list. The PC enforces this after contact-name resolution, and outbound mail still requires confirmation by default.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    HStack {
                        TextField("person@example.com", text: $newAllowedRecipient)
                            .textInputAutocapitalization(.never)
                            .keyboardType(.emailAddress)
                            .autocorrectionDisabled()
                        Button("Add") { Task { await addAllowedRecipient() } }
                            .disabled(newAllowedRecipient.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSavingAllowlist)
                    }

                    if allowedRecipients.isEmpty {
                        Label("No recipients are allowed. Email sending is blocked.", systemImage: "lock.fill")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(allowedRecipients, id: \.self) { address in
                            HStack {
                                Text(address).textSelection(.enabled)
                                Spacer()
                                Button(role: .destructive) {
                                    Task { await removeAllowedRecipient(address) }
                                } label: { Image(systemName: "trash") }
                                .buttonStyle(.borderless)
                                .disabled(isSavingAllowlist)
                            }
                        }
                    }
                    Text(allowlistStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Reload Allowed Recipients") { Task { await loadAllowedRecipients() } }
                        .disabled(isSavingAllowlist)
                }

                Section("Home Geofence") {
                    TextField("Latitude", value: $settings.homeLatitude, format: .number.precision(.fractionLength(6)))
                        .keyboardType(.numbersAndPunctuation)
                    TextField("Longitude", value: $settings.homeLongitude, format: .number.precision(.fractionLength(6)))
                        .keyboardType(.numbersAndPunctuation)
                    TextField("Radius (meters)", value: $settings.homeRadius, format: .number)
                        .keyboardType(.decimalPad)

                    if let location = geofence.lastLocation {
                        Button("Use Current Location as Home") {
                            settings.homeLatitude = location.coordinate.latitude
                            settings.homeLongitude = location.coordinate.longitude
                        }
                    } else {
                        Button("Get Current Location") { geofence.requestCurrentLocation() }
                    }

                    Button("Enable Home Arrival Automation") {
                        geofence.requestAlwaysAuthorization()
                        geofence.configureHome(
                            latitude: settings.homeLatitude,
                            longitude: settings.homeLongitude,
                            radius: settings.homeRadius
                        )
                    }
                    if geofence.isMonitoringHome {
                        Button("Stop Home Monitoring", role: .destructive) { geofence.stopMonitoringHome() }
                    }
                    Text(geofence.statusMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .task {
                async let plannerLoad: Void = loadPlannerModel()
                async let voiceCheck: Void = checkNeuralVoice()
                async let recipientsLoad: Void = loadAllowedRecipients()
                _ = await (plannerLoad, voiceCheck, recipientsLoad)
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }

    private func loadPlannerModel() async {
        do {
            let response = try await client.plannerModel()
            useFastPlanner = response.model == fastPlannerModel
            autoRoutePlanner = response.autoRoute
            plannerModelStatus = autoRoutePlanner
                ? "Automatic routing is active."
                : (useFastPlanner ? "Fast 8B planner selected." : "27B planner selected.")
        } catch {
            plannerModelStatus = "Could not read planner mode: \(error.localizedDescription)"
        }
    }

    private func switchAutoRouting(_ enabled: Bool, previousValue: Bool) async {
        guard !isSwitchingPlanner else { return }
        isSwitchingPlanner = true
        plannerModelStatus = enabled ? "Enabling automatic routing…" : "Disabling automatic routing…"
        defer { isSwitchingPlanner = false }
        do {
            let response = try await client.setPlannerModel(autoRoute: enabled)
            autoRoutePlanner = response.autoRoute
            useFastPlanner = response.model == fastPlannerModel
            plannerModelStatus = response.autoRoute
                ? "Automatic routing enabled; 8B is warming for routine turns."
                : "Automatic routing disabled."
        } catch {
            autoRoutePlanner = previousValue
            plannerModelStatus = "Routing change failed: \(error.localizedDescription)"
        }
    }

    private func switchPlannerModel(fast: Bool, previousFastValue: Bool) async {
        guard !isSwitchingPlanner else { return }
        isSwitchingPlanner = true
        plannerModelStatus = fast ? "Switching to Qwen3 8B…" : "Switching to Qwen3.8 27B…"
        defer { isSwitchingPlanner = false }
        let requested = fast ? fastPlannerModel : qualityPlannerModel
        do {
            let response = try await client.setPlannerModel(model: requested)
            useFastPlanner = response.model == fastPlannerModel
            autoRoutePlanner = response.autoRoute
            plannerModelStatus = useFastPlanner
                ? "Fast 8B planner selected. Ollama is warming it in the background."
                : "27B planner selected. Ollama is warming it in the background."
        } catch {
            useFastPlanner = previousFastValue
            plannerModelStatus = "Model switch failed: \(error.localizedDescription)"
        }
    }

    private func checkNeuralVoice() async {
        neuralVoiceStatus = "Checking…"
        do {
            let status = try await client.ttsStatus()
            neuralVoiceStatus = status == "ready" ? "Kokoro ready" : "Starting / unavailable"
        } catch {
            neuralVoiceStatus = "Jarvis server offline"
        }
    }

    private func loadAllowedRecipients() async {
        isSavingAllowlist = true
        defer { isSavingAllowlist = false }
        do {
            allowedRecipients = try await client.emailAllowlist()
            allowlistStatus = allowedRecipients.isEmpty
                ? "Sending is currently blocked for every address."
                : "Allowed-recipient list is enforced by the PC backend."
        } catch {
            allowlistStatus = "Could not load allowed recipients: \(error.localizedDescription)"
        }
    }

    private func addAllowedRecipient() async {
        let value = newAllowedRecipient.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !value.isEmpty else { return }
        var updated = allowedRecipients
        if !updated.contains(value) { updated.append(value) }
        await saveAllowedRecipients(updated)
        if allowedRecipients.contains(value) { newAllowedRecipient = "" }
    }

    private func removeAllowedRecipient(_ address: String) async {
        await saveAllowedRecipients(allowedRecipients.filter { $0 != address })
    }

    private func saveAllowedRecipients(_ addresses: [String]) async {
        isSavingAllowlist = true
        defer { isSavingAllowlist = false }
        do {
            allowedRecipients = try await client.setEmailAllowlist(addresses)
            allowlistStatus = allowedRecipients.isEmpty
                ? "Sending is blocked for every address."
                : "Saved. Only these exact addresses can receive email from Jarvis."
        } catch {
            allowlistStatus = "Could not save allowed recipients: \(error.localizedDescription)"
        }
    }
}
