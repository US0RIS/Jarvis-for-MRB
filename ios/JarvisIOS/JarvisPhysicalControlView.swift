import CoreLocation
import Foundation
import SwiftUI

struct PublicCameraListing: Decodable, Identifiable {
    let id: String
    let title: String
    let nearbyPlace: String
    let distanceKM: Double
    let imageURL: String
    let streamURL: String
    let provider: String

    enum CodingKeys: String, CodingKey {
        case id, title, provider
        case nearbyPlace = "nearby_place"
        case distanceKM = "distance_km"
        case imageURL = "image_url"
        case streamURL = "stream_url"
    }
}

struct PublicCameraDiscoveryResponse: Decodable {
    let status: String
    let coverage: String
    let cameras: [PublicCameraListing]
    let sourceURL: String
    let sourceNote: String
    let coordinatesStored: Bool

    enum CodingKeys: String, CodingKey {
        case status, coverage, cameras
        case sourceURL = "source_url"
        case sourceNote = "source_note"
        case coordinatesStored = "coordinates_stored"
    }
}

struct PublicCameraAnalysisResponse: Decodable {
    let status: String
    let cameraID: String
    let cameraName: String
    let description: String
    let retrievedAt: String
    let model: String
    let sourceNote: String

    enum CodingKeys: String, CodingKey {
        case status, description, model
        case cameraID = "camera_id"
        case cameraName = "camera_name"
        case retrievedAt = "retrieved_at"
        case sourceNote = "source_note"
    }
}

struct PhysicalAwarenessResponse: Decodable {
    let status: String
    let summary: String
    let checkedAt: String
    let cameras: PublicCameraDiscoveryResponse
    let conditions: PhysicalConditionsResponse
    let facilities: NearbyFacilitiesResponse
    let locationNote: String

    enum CodingKeys: String, CodingKey {
        case status, summary, cameras, conditions, facilities
        case checkedAt = "checked_at"
        case locationNote = "location_note"
    }
}

struct NearbyFacility: Decodable, Identifiable {
    let id: String
    let title: String
    let category: String
    let distanceM: Int
    let latitude: Double
    let longitude: Double
    let access: String
    let openingHours: String
    let sourceURL: String

    enum CodingKeys: String, CodingKey {
        case id, title, category, latitude, longitude, access
        case distanceM = "distance_m"
        case openingHours = "opening_hours"
        case sourceURL = "source_url"
    }

    var appleMapsURL: URL? {
        URL(string: "https://maps.apple.com/?daddr=\(latitude),\(longitude)&dirflg=w")
    }
}

struct NearbyFacilitiesResponse: Decodable {
    let status: String
    let facilities: [NearbyFacility]
    let sourceURL: String
    let attributionURL: String?
    let sourceNote: String

    enum CodingKeys: String, CodingKey {
        case status, facilities
        case sourceURL = "source_url"
        case attributionURL = "attribution_url"
        case sourceNote = "source_note"
    }
}

struct PhysicalConditionsResponse: Decodable {
    struct AirQuality: Decodable {
        let status: String
        let usAQI: Double?
        let europeanAQI: Double?
        let pm25: Double?
        let uvIndex: Double?
        let modelTimeUTC: String?
        let sourceURL: String
        let sourceNote: String

        enum CodingKeys: String, CodingKey {
            case status
            case usAQI = "us_aqi"
            case europeanAQI = "european_aqi"
            case pm25 = "pm2_5_ug_m3"
            case uvIndex = "uv_index"
            case modelTimeUTC = "model_time_utc"
            case sourceURL = "source_url"
            case sourceNote = "source_note"
        }
    }

    struct WeatherAlert: Decodable, Identifiable {
        let id: String
        let event: String
        let headline: String
        let severity: String
        let instruction: String
        let expires: String
    }

    struct WeatherAlerts: Decodable {
        let status: String
        let alerts: [WeatherAlert]
        let sourceURL: String
        let sourceNote: String

        enum CodingKeys: String, CodingKey {
            case status, alerts
            case sourceURL = "source_url"
            case sourceNote = "source_note"
        }
    }

    let airQuality: AirQuality
    let weatherAlerts: WeatherAlerts
    let checkedAt: String
    let locationSharingNote: String

    enum CodingKeys: String, CodingKey {
        case airQuality = "air_quality"
        case weatherAlerts = "weather_alerts"
        case checkedAt = "checked_at"
        case locationSharingNote = "location_sharing_note"
    }
}

/// Location is requested only after an explicit button press; no continuous
/// tracking, background camera search, or raw location telemetry is added.
@MainActor
final class PublicCameraLocationRequest: NSObject, ObservableObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocation, Error>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func locateOnce() async throws -> CLLocation {
        guard continuation == nil else {
            throw NSError(domain: "JarvisPhysical", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "Location lookup already in progress."
            ])
        }
        return try await withCheckedThrowingContinuation { next in
            continuation = next
            switch manager.authorizationStatus {
            case .authorizedWhenInUse, .authorizedAlways:
                manager.requestLocation()
            case .notDetermined:
                manager.requestWhenInUseAuthorization()
            case .denied, .restricted:
                finish(.failure(NSError(domain: "JarvisPhysical", code: 2, userInfo: [
                    NSLocalizedDescriptionKey: "Enable location for Jarvis in iPhone Settings to find nearby published traffic cameras."
                ])))
            @unknown default:
                finish(.failure(NSError(domain: "JarvisPhysical", code: 3, userInfo: [
                    NSLocalizedDescriptionKey: "Location authorization is unavailable."
                ])))
            }
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard continuation != nil else { return }
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways:
            manager.requestLocation()
        case .denied, .restricted:
            finish(.failure(NSError(domain: "JarvisPhysical", code: 2, userInfo: [
                NSLocalizedDescriptionKey: "Location access was declined."
            ])))
        default: break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        if let last = locations.last {
            finish(.success(last))
        } else {
            finish(.failure(NSError(domain: "JarvisPhysical", code: 4, userInfo: [
                NSLocalizedDescriptionKey: "iPhone returned no location."
            ])))
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        finish(.failure(error))
    }

    private func finish(_ value: Result<CLLocation, Error>) {
        guard let continuation else { return }
        self.continuation = nil
        continuation.resume(with: value)
    }
}

/// Standalone iPhone control surface. No MemoMind SDK, device registration or
/// head-worn display is needed to use any function on this screen.
struct JarvisPhysicalHubView: View {
    @EnvironmentObject var appModel: JarvisAppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                GroupBox("JARVIS • Situational briefing") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("A single deliberate lookup across available public cameras, modelled air quality, official point alerts, and mapped facilities.")
                            .font(.callout)
                        Button(appModel.physicalAwarenessBusy ? "Checking sources…" : "Establish situational awareness") {
                            Task { _ = await appModel.establishPhysicalAwareness() }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(appModel.physicalAwarenessBusy)
                        Text(appModel.physicalAwarenessStatus)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        if let overview = appModel.latestPhysicalAwareness {
                            Text("Checked: " + overview.checkedAt)
                                .font(.caption)
                            Text(overview.locationNote)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text("Voice: “Jarvis, establish situational awareness.”")
                            .font(.caption.weight(.medium))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Portable physical-world access") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Works on iPhone alone. With your Gen 1 Ray-Ban Meta glasses, speak through Jarvis’s existing Bluetooth hands-free connection.")
                            .font(.callout)
                        LabeledContent("Audio route", value: appModel.audioRouteManager.routeSummary)
                            .font(.caption)
                        Text("The Ray-Bans supply microphone, speakers and the existing Meta camera integration. They do not display a HUD.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("Try: “Jarvis, find nearby public cameras.”")
                            .font(.caption.weight(.medium))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Air and weather signals") {
                    JarvisPhysicalConditionsView()
                }

                GroupBox("Nearby mapped resources") {
                    JarvisPublicFacilitiesView()
                }

                GroupBox("Public viewpoints") {
                    JarvisPhysicalControlView()
                }

                GroupBox("Authorized physical control") {
                    AppleHomeControlView()
                }

                GroupBox("Optional future HUD") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("MemoMind is optional. None of the controls above require it.")
                            .font(.callout)
                        NavigationLink("Open experimental glasses simulator") {
                            MemoMindPreviewView()
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding()
        }
        .navigationTitle("Physical")
    }
}

struct JarvisPhysicalControlView: View {
    @EnvironmentObject var appModel: JarvisAppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Find officially published highway cameras near your current location. Search is opt-in; no nearby Wi-Fi devices or private CCTV are scanned.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button(appModel.nearbyCameraBusy ? "Searching…" : "Find nearby public cameras") {
                Task { _ = await appModel.searchNearbyPublicCameras() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(appModel.nearbyCameraBusy)

            Text(appModel.nearbyCameraStatus)
                .font(.footnote)
                .foregroundStyle(.secondary)
            if !appModel.nearbyCameraCoverage.isEmpty {
                Text(appModel.nearbyCameraCoverage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ForEach(appModel.nearbyPublicCameras) { camera in
                VStack(alignment: .leading, spacing: 5) {
                    Text(camera.title).font(.subheadline.weight(.medium))
                    Text(String(format: "%.1f km away • %@", camera.distanceKM, camera.provider))
                        .font(.caption).foregroundStyle(.secondary)
                    if let still = URL(string: camera.imageURL), !camera.imageURL.isEmpty {
                        AsyncImage(url: still) { state in
                            switch state {
                            case .success(let image):
                                image.resizable().scaledToFit()
                            case .failure:
                                Text("Publisher image unavailable")
                                    .font(.caption).foregroundStyle(.secondary)
                            case .empty:
                                ProgressView()
                            @unknown default:
                                EmptyView()
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                    if let stream = URL(string: camera.streamURL), !camera.streamURL.isEmpty {
                        Link("Open official public camera stream", destination: stream)
                            .font(.caption)
                    }
                    if !camera.imageURL.isEmpty {
                        Button(appModel.analyzingPublicCameraID == camera.id ? "Analyzing published still…" : "Analyze this public still with Jarvis") {
                            Task { _ = await appModel.analyzePublishedCameraStill(camera.id) }
                        }
                        .font(.caption)
                        .buttonStyle(.bordered)
                        .disabled(appModel.analyzingPublicCameraID != nil)
                    }
                    if let analysis = appModel.publicCameraAnalyses[camera.id] {
                        Text(analysis)
                            .font(.caption)
                            .accessibilityIdentifier("public-camera-analysis")
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
            }
            if let source = URL(string: appModel.nearbyCameraSourceURL),
               !appModel.nearbyCameraSourceURL.isEmpty {
                Link("Official source / coverage details", destination: source)
                    .font(.caption)
            }
        }
        .padding(.vertical, 8)
    }
}


struct JarvisPhysicalConditionsView: View {
    @EnvironmentObject var appModel: JarvisAppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("One-time location check: global modelled air quality / UV, plus official NWS point alerts where supported.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button(appModel.nearbyConditionsBusy ? "Checking…" : "Check conditions around me") {
                Task { _ = await appModel.searchPhysicalConditions() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(appModel.nearbyConditionsBusy)
            Text(appModel.nearbyConditionsStatus)
                .font(.footnote)
                .foregroundStyle(.secondary)

            if let data = appModel.nearbyConditions {
                VStack(alignment: .leading, spacing: 6) {
                    Text("AIR QUALITY • " + data.airQuality.status.uppercased())
                        .font(.subheadline.weight(.semibold))
                    if let value = data.airQuality.usAQI {
                        Text("Modelled US AQI: " + String(format: "%.0f", value))
                    }
                    if let value = data.airQuality.pm25 {
                        Text("PM₂.₅: " + String(format: "%.1f μg/m³", value))
                    }
                    if let value = data.airQuality.uvIndex {
                        Text("UV index: " + String(format: "%.1f", value))
                    }
                    if let modelTime = data.airQuality.modelTimeUTC {
                        Text("Model time: " + modelTime)
                            .font(.caption)
                    }
                    Text(data.airQuality.sourceNote)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let url = URL(string: data.airQuality.sourceURL) {
                        Link("Air-quality source", destination: url)
                            .font(.caption)
                    }
                }

                Divider()

                VStack(alignment: .leading, spacing: 7) {
                    Text("OFFICIAL WEATHER ALERTS • " + data.weatherAlerts.status.uppercased())
                        .font(.subheadline.weight(.semibold))
                    if data.weatherAlerts.status == "ok", data.weatherAlerts.alerts.isEmpty {
                        Text("No active NWS point alerts returned. Not an all-hazards clearance.")
                    }
                    ForEach(data.weatherAlerts.alerts) { alert in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(alert.event + " • " + alert.severity)
                                .font(.callout.weight(.medium))
                            Text(alert.headline)
                                .font(.caption)
                            if !alert.instruction.isEmpty {
                                Text(alert.instruction)
                                    .font(.caption)
                            }
                            if !alert.expires.isEmpty {
                                Text("Expires: " + alert.expires).font(.caption)
                            }
                        }
                        .padding(.vertical, 3)
                    }
                    Text(data.weatherAlerts.sourceNote)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let url = URL(string: data.weatherAlerts.sourceURL) {
                        Link("Official weather-alert source", destination: url)
                            .font(.caption)
                    }
                }
                Text(data.locationSharingNote)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 8)
    }
}


struct JarvisPublicFacilitiesView: View {
    @EnvironmentObject var appModel: JarvisAppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Find community-mapped drinking water, toilets and public defibrillators wherever OpenStreetMap has coverage.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button(appModel.nearbyFacilitiesBusy ? "Searching…" : "Find public resources near me") {
                Task { _ = await appModel.searchNearbyPublicFacilities() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(appModel.nearbyFacilitiesBusy)
            Text(appModel.nearbyFacilitiesStatus)
                .font(.footnote)
                .foregroundStyle(.secondary)

            if let response = appModel.nearbyFacilities {
                ForEach(response.facilities) { facility in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(facility.title)
                            .font(.subheadline.weight(.medium))
                        Text("\(facility.category) • \(facility.distanceM) m")
                            .font(.caption)
                        if facility.access != "unknown" {
                            Text("Mapped access: " + facility.access)
                                .font(.caption)
                        }
                        if facility.openingHours != "unknown" {
                            Text("Mapped hours: " + facility.openingHours)
                                .font(.caption)
                        }
                        HStack(spacing: 12) {
                            if let route = facility.appleMapsURL {
                                Link("Walking directions", destination: route)
                                    .font(.caption)
                            }
                            if let source = URL(string: facility.sourceURL) {
                                Link("Map record", destination: source)
                                    .font(.caption)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
                Text(response.sourceNote)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let attribution = response.attributionURL,
                   let url = URL(string: attribution) {
                    Link("© OpenStreetMap contributors", destination: url)
                        .font(.caption)
                }
            }
        }
        .padding(.vertical, 8)
    }
}
