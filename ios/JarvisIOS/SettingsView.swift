import SwiftUI

struct SettingsView: View {
    @ObservedObject var settings: SettingsStore
    @ObservedObject var geofence: GeofenceManager
    @Environment(\.dismiss) private var dismiss

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
                    Text("When enabled, Jarvis explicitly prefers an available Bluetooth hands-free microphone. Selecting a Bluetooth HFP input also routes Jarvis audio back to that headset on iOS.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
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
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
