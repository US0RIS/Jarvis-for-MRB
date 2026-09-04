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

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: settings.baseURL,
            apiToken: settings.apiToken,
            sessionID: settings.conversationSessionID
        )
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Jarvis Server") {
                    TextField("Base URL", text: $settings.baseURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    SecureField("API token", text: $settings.apiToken)
                        .textInputAutocapitalization(.never)
                    Text("Example: http://192.168.1.50:8765 or your private Tailscale address.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Voice") {
                    Toggle("Speak Jarvis responses", isOn: $settings.speakResponses)
                    Toggle("Prefer Ray-Ban / Bluetooth microphone", isOn: $settings.preferBluetoothAudio)

                    HStack {
                        Text("Neural voice")
                        Spacer()
                        Text(neuralVoiceStatus)
                            .foregroundStyle(neuralVoiceStatus == "Qwen3-TTS ready" ? Color.green : Color.secondary)
                    }

                    Button("Check Neural Voice") {
                        Task { await checkNeuralVoice() }
                    }

                    Text("Jarvis prefers the local Qwen3-TTS model running on the PC's RTX GPU. Apple speech is used only as a fallback. The Ray-Ban hands-free route is still used for playback and interruption detection.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Email Safety") {
                    Text("Jarvis can send email only to exact addresses on this list. The backend enforces this after contact-name resolution, so even a speech-to-text error plus an accidental confirmation cannot send to a different address.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    HStack {
                        TextField("person@example.com", text: $newAllowedRecipient)
                            .textInputAutocapitalization(.never)
                            .keyboardType(.emailAddress)
                            .autocorrectionDisabled()

                        Button("Add") {
                            Task { await addAllowedRecipient() }
                        }
                        .disabled(newAllowedRecipient.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSavingAllowlist)
                    }

                    if allowedRecipients.isEmpty {
                        Label("No recipients are allowed. Email sending is blocked.", systemImage: "lock.fill")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(allowedRecipients, id: \.self) { address in
                            HStack {
                                Text(address)
                                    .textSelection(.enabled)
                                Spacer()
                                Button(role: .destructive) {
                                    Task { await removeAllowedRecipient(address) }
                                } label: {
                                    Image(systemName: "trash")
                                }
                                .buttonStyle(.borderless)
                                .disabled(isSavingAllowlist)
                            }
                        }
                    }

                    Text(allowlistStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Button("Reload Allowed Recipients") {
                        Task { await loadAllowedRecipients() }
                    }
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
                        Button("Get Current Location") {
                            geofence.requestCurrentLocation()
                        }
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
                        Button("Stop Home Monitoring", role: .destructive) {
                            geofence.stopMonitoringHome()
                        }
                    }

                    Text(geofence.statusMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .task {
                async let voiceCheck: Void = checkNeuralVoice()
                async let recipientsLoad: Void = loadAllowedRecipients()
                _ = await (voiceCheck, recipientsLoad)
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private func checkNeuralVoice() async {
        neuralVoiceStatus = "Checking…"
        do {
            let status = try await client.ttsStatus()
            neuralVoiceStatus = status == "ready" ? "Qwen3-TTS ready" : "Starting / unavailable"
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
        let value = newAllowedRecipient
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard !value.isEmpty else { return }
        var updated = allowedRecipients
        if !updated.contains(value) {
            updated.append(value)
        }
        await saveAllowedRecipients(updated)
        if allowedRecipients.contains(value) {
            newAllowedRecipient = ""
        }
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
