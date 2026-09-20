import CoreLocation
import Foundation
import MapKit
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

struct DiligenceMatterSummary: Decodable, Identifiable {
    let id: String
    let label: String
    let projectEntityID: String

    enum CodingKeys: String, CodingKey {
        case id, label
        case projectEntityID = "project_entity_id"
    }
}

struct DiligenceMatterList: Decodable {
    let matters: [DiligenceMatterSummary]
}

struct ExternalWatchSummary: Decodable, Identifiable {
    let id: String
    let scope: String
    let kind: String
    let label: String
    let enabled: Bool
    let lastStatus: String
    let lastSummary: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case id, scope, kind, label, enabled
        case lastStatus = "last_status"
        case lastSummary = "last_summary"
        case expiresAt = "expires_at"
    }
}

struct ExternalWatchListResponse: Decodable {
    let watches: [ExternalWatchSummary]
}

struct ExternalWatchCheckResponse: Decodable {
    let status: String
    let summary: String?
    let changeKind: String?

    enum CodingKeys: String, CodingKey {
        case status, summary
        case changeKind = "change_kind"
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

                GroupBox("Independent public-record diligence") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Matter-isolated SEC filing checks and source-linked XBRL comparisons. Requires exact CIKs and explicit client/matter authorization.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        NavigationLink("Open local diligence workbench") {
                            JarvisPublicDiligenceView()
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Remote observation and standing watches") {
                    JarvisWorldWatchesView()
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


/// The user can select any location, not only where the phone is standing.
/// No MemoMind hardware or geolocation permission is required for this view.
struct JarvisWorldWatchesView: View {
    @EnvironmentObject var appModel: JarvisAppModel
    @State private var placeQuery = ""
    @State private var latitude = ""
    @State private var longitude = ""
    @State private var remoteCameras: [PublicCameraListing] = []
    @State private var cameraCondition = ""
    @State private var watches: [ExternalWatchSummary] = []
    @State private var status = "No active remote view selected."
    @State private var sourceNote = ""
    @State private var working = false

    private var coordinates: (Double, Double)? {
        guard let lat = Double(latitude), let lon = Double(longitude),
              lat.isFinite, lon.isFinite, abs(lat) <= 90, abs(lon) <= 180 else {
            return nil
        }
        return (lat, lon)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Choose a remote location or published official camera. Watches expire automatically; stop or recheck at any time.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            TextField("Remote place name (e.g. Mount Hotham, Victoria)", text: $placeQuery)
                .textFieldStyle(.roundedBorder)
            Button("Resolve place to coordinates") {
                Task { await resolvePlace() }
            }
            .buttonStyle(.bordered)
            .disabled(working || placeQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            HStack {
                TextField("Latitude", text: $latitude)
                    .keyboardType(.numbersAndPunctuation)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("remote-watch-latitude")
                TextField("Longitude", text: $longitude)
                    .keyboardType(.numbersAndPunctuation)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("remote-watch-longitude")
            }
            Button("Find official cameras at these coordinates") {
                Task { await findRemoteCameras() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(coordinates == nil || working)
            HStack(spacing: 8) {
                Button("Watch weather warnings") {
                    Task { await createLocationWatch("nws_alerts") }
                }
                Button("Watch regional air quality") {
                    Task { await createLocationWatch("air_quality") }
                }
            }
            .font(.caption)
            .buttonStyle(.bordered)
            .disabled(coordinates == nil || working)
            Button("Watch regional USGS earthquakes") {
                Task { await createLocationWatch("usgs_earthquakes") }
            }
            .font(.caption)
            .buttonStyle(.bordered)
            .disabled(coordinates == nil || working)
            Button("Watch regional aircraft count") {
                Task { await createLocationWatch("airspace_region") }
            }
            .font(.caption)
            .buttonStyle(.bordered)
            .disabled(coordinates == nil || working)
            Text(status)
                .font(.footnote)
                .foregroundStyle(.secondary)
            if !sourceNote.isEmpty {
                Text(sourceNote)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Picker("Camera watch condition", selection: $cameraCondition) {
                Text("Change log only").tag("")
                Text("Possible visible smoke").tag("smoke_visible")
                Text("Apparent road congestion").tag("road_congestion")
            }
            .font(.caption)
            ForEach(remoteCameras) { camera in
                VStack(alignment: .leading, spacing: 5) {
                    Text(camera.title).font(.callout.weight(.medium))
                    Text(camera.provider + " • " + String(format: "%.1f km from selected location", camera.distanceKM))
                        .font(.caption)
                    if !camera.imageURL.isEmpty {
                        Button("Create 24-hour camera watch") {
                            Task {
                                await createWatch(
                                    kind: "camera", label: camera.title,
                                    config: [
                                        "camera_id": camera.id,
                                        "condition": cameraCondition
                                    ],
                                    seconds: cameraCondition.isEmpty ? 3600 : 900
                                )
                            }
                        }
                        .font(.caption)
                        .buttonStyle(.bordered)
                        .disabled(working)
                    }
                    if let url = URL(string: camera.streamURL), !camera.streamURL.isEmpty {
                        Link("Published stream", destination: url).font(.caption)
                    }
                }
                .padding(.vertical, 5)
            }

            Divider()
            Button("Refresh my standing watches") {
                Task { await refreshWatches() }
            }
            .buttonStyle(.bordered)
            .disabled(working)
            ForEach(watches) { watch in
                VStack(alignment: .leading, spacing: 5) {
                    Text(watch.label)
                        .font(.callout.weight(.medium))
                    Text(watch.kind + " • " + watch.lastStatus
                         + (watch.enabled ? "" : " • stopped"))
                        .font(.caption)
                    if !watch.lastSummary.isEmpty {
                        Text(watch.lastSummary)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text("Expires: " + watch.expiresAt)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    HStack {
                        Button("Check now") {
                            Task { await checkWatch(watch.id) }
                        }
                        Button("Stop watch") {
                            Task { await stopWatch(watch.id) }
                        }
                        .disabled(!watch.enabled)
                    }
                    .font(.caption)
                    .buttonStyle(.bordered)
                    .disabled(working)
                }
                .padding(.vertical, 5)
            }
            Text("Only published feeds, NWS warnings, modelled AQI, and regional aircraft counts are integrated. A camera's capture time is not verified; ML descriptions are not confirmed emergencies. Airspace counts identify no passengers.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 8)
        .task { await refreshWatches() }
    }

    @MainActor
    private func resolvePlace() async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            let query = MKLocalSearch.Request()
            query.naturalLanguageQuery = placeQuery
            let response = try await MKLocalSearch(request: query).start()
            guard let place = response.mapItems.first else {
                status = "MapKit did not resolve that place. Add city/region and retry."
                return
            }
            let point = place.placemark.coordinate
            latitude = String(format: "%.6f", point.latitude)
            longitude = String(format: "%.6f", point.longitude)
            status = "MapKit selected " + (place.name ?? placeQuery)
                + " at " + latitude + ", " + longitude
                + ". Verify the location before starting a watch."
            remoteCameras = []
        } catch {
            status = "Place resolution unavailable: " + error.localizedDescription
        }
    }

    @MainActor
    private func findRemoteCameras() async {
        guard let (lat, lon) = coordinates, !working else { return }
        working = true
        defer { working = false }
        do {
            let data = try await appModel.findPublicCamerasAt(latitude: lat, longitude: lon)
            remoteCameras = data.cameras
            sourceNote = data.sourceNote
            status = data.status == "unsupported_region"
                ? "No integrated published camera provider at this location."
                : "\(data.cameras.count) published cameras at selected remote location."
        } catch {
            status = "Remote camera lookup unavailable: " + error.localizedDescription
        }
    }

    @MainActor
    private func createLocationWatch(_ kind: String) async {
        guard let (lat, lon) = coordinates else { return }
        let seconds = kind == "nws_alerts" ? 900 : 3600
        var config: [String: Any] = ["latitude": lat, "longitude": lon]
        if kind == "air_quality" { config["us_aqi_threshold"] = 100 }
        if kind == "airspace_region" { config["radius_km"] = 20 }
        await createWatch(
            kind: kind, label: kind + " at " + latitude + ", " + longitude,
            config: config, seconds: seconds
        )
    }

    @MainActor
    private func createWatch(kind: String, label: String, config: [String: Any], seconds: Int) async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            let watch = try await appModel.createExternalWatch(
                kind: kind, label: label, config: config, seconds: seconds
            )
            status = "Created \(watch.kind) watch. Automatic expiry: \(watch.expiresAt)."
            watches = try await appModel.getExternalWatches()
        } catch {
            status = "Could not create watch: " + error.localizedDescription
        }
    }

    @MainActor
    private func refreshWatches() async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            watches = try await appModel.getExternalWatches()
        } catch {
            status = "Watch list unavailable: " + error.localizedDescription
        }
    }

    @MainActor
    private func checkWatch(_ id: String) async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            let result = try await appModel.checkExternalWatch(id)
            status = result.summary ?? result.status
            watches = try await appModel.getExternalWatches()
        } catch {
            status = "Watch check unavailable: " + error.localizedDescription
        }
    }

    @MainActor
    private func stopWatch(_ id: String) async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            _ = try await appModel.stopExternalWatch(id)
            watches = try await appModel.getExternalWatches()
            status = "Watch stopped."
        } catch {
            status = "Unable to stop watch: " + error.localizedDescription
        }
    }
}


/// Entirely optional workbench; matter labels and claim source references are
/// kept in a separate backend matter ledger, not used for name-based searches.
struct JarvisPublicDiligenceView: View {
    @EnvironmentObject var appModel: JarvisAppModel
    @State private var matters: [DiligenceMatterSummary] = []
    @State private var matterLabel = ""
    @State private var selectedMatterID = ""
    @State private var projectEntityID = ""
    @State private var issuerName = ""
    @State private var issuerCIK = ""
    @State private var claimTag = ""
    @State private var claimValue = ""
    @State private var claimUnit = "USD"
    @State private var claimStart = ""
    @State private var claimEnd = ""
    @State private var claimSource = ""
    @State private var includeSanctions = false
    @State private var working = false
    @State private var message = "Select a local matter and explicitly confirm the issuer's SEC CIK."
    @State private var evidenceLines: [String] = []
    @State private var sourceLinks: [(title: String, url: String)] = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                GroupBox("Scope and limitations") {
                    Text("Only use this with appropriate client/organization authorization. Exact CIK queries reach the SEC; your private matter label and document-source references stay in Jarvis's separate local matter ledger. This is an evidence review aid, not sanctions clearance, legal advice or a finding of misrepresentation.")
                        .font(.footnote)
                }
                GroupBox("Local matter") {
                    VStack(alignment: .leading, spacing: 9) {
                        TextField("New matter label", text: $matterLabel)
                            .textFieldStyle(.roundedBorder)
                        TextField("Existing world project entity ID (optional)", text: $projectEntityID)
                            .textFieldStyle(.roundedBorder)
                        Button("Create isolated matter") { Task { await createMatter() } }
                            .buttonStyle(.borderedProminent)
                            .disabled(working || matterLabel.trimmingCharacters(in: .whitespaces).isEmpty)
                        if !matters.isEmpty {
                            Picker("Matter", selection: $selectedMatterID) {
                                ForEach(matters) { matter in
                                    Text(matter.label).tag(matter.id)
                                }
                            }
                        }
                        Button("Refresh local matter list") { Task { await refreshMatters() } }
                            .buttonStyle(.bordered)
                            .disabled(working)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("Explicit SEC issuer") {
                    VStack(alignment: .leading, spacing: 8) {
                        TextField("CIK (digits only)", text: $issuerCIK)
                            .keyboardType(.numberPad)
                            .textFieldStyle(.roundedBorder)
                        TextField("Company name as supplied", text: $issuerName)
                            .textFieldStyle(.roundedBorder)
                        Button("Register exact CIK in selected matter") {
                            Task { await registerIssuer() }
                        }
                        .buttonStyle(.bordered)
                        .disabled(working || selectedMatterID.isEmpty
                                  || issuerCIK.isEmpty || issuerName.isEmpty)
                        Text("Jarvis does not guess a CIK from a company name or infer that similarly named legal entities are the same.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("Optional source-linked numeric claim") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Compare only a deliberately selected SEC XBRL concept, unit and identical reporting period.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        TextField("US-GAAP tag, e.g. LongTermDebt", text: $claimTag)
                            .textFieldStyle(.roundedBorder)
                        HStack {
                            TextField("Claim value", text: $claimValue)
                                .keyboardType(.decimalPad)
                                .textFieldStyle(.roundedBorder)
                            Picker("Unit", selection: $claimUnit) {
                                Text("USD").tag("USD")
                                Text("shares").tag("shares")
                                Text("pure").tag("pure")
                            }
                        }
                        TextField("Start YYYY-MM-DD (duration facts)", text: $claimStart)
                            .textFieldStyle(.roundedBorder)
                        TextField("End YYYY-MM-DD", text: $claimEnd)
                            .textFieldStyle(.roundedBorder)
                        TextField("Document citation/source reference", text: $claimSource)
                            .textFieldStyle(.roundedBorder)
                        Button("Record claim for independent comparison") {
                            Task { await addClaim() }
                        }
                        .buttonStyle(.bordered)
                        .disabled(working || selectedMatterID.isEmpty
                                  || issuerCIK.isEmpty || claimTag.isEmpty
                                  || claimValue.isEmpty || claimEnd.isEmpty
                                  || claimSource.isEmpty)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("Independent evidence check") {
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("Include local OFAC SDN name-candidate check", isOn: $includeSanctions)
                        Text("OFAC check downloads the primary-name SDN list for local matching. Neither a candidate nor an exact-name nonmatch determines legal status; other lists, aliases, and ownership remain unreviewed.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Button(working ? "Checking…" : "Check selected matter") {
                            Task { await checkMatter() }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(working || selectedMatterID.isEmpty)
                        Text(message).font(.footnote).foregroundStyle(.secondary)
                        ForEach(Array(evidenceLines.enumerated()), id: \.offset) { _, line in
                            Text(line).font(.caption)
                        }
                        ForEach(Array(sourceLinks.enumerated()), id: \.offset) { _, source in
                            if let url = URL(string: source.url) {
                                Link(source.title, destination: url)
                                    .font(.caption)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding()
        }
        .navigationTitle("Public Diligence")
        .task { await refreshMatters() }
    }

    @MainActor
    private func refreshMatters() async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            matters = try await appModel.listDiligenceMatters()
            if !matters.contains(where: { $0.id == selectedMatterID }) {
                selectedMatterID = matters.first?.id ?? ""
            }
        } catch {
            message = "Matter registry unavailable: " + error.localizedDescription
        }
    }

    @MainActor
    private func createMatter() async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            let created = try await appModel.createDiligenceMatter(
                label: matterLabel, projectEntityID: projectEntityID
            )
            matters = try await appModel.listDiligenceMatters()
            selectedMatterID = created.id
            matterLabel = ""
            message = "Created local matter " + created.label + "."
        } catch {
            message = "Matter creation failed: " + error.localizedDescription
        }
    }

    @MainActor
    private func registerIssuer() async {
        guard !working else { return }
        working = true
        defer { working = false }
        do {
            try await appModel.registerDiligenceIssuer(
                matterID: selectedMatterID, cik: issuerCIK, name: issuerName
            )
            message = "Registered user-confirmed SEC CIK. No name-based external lookup performed."
        } catch {
            message = "CIK registration failed: " + error.localizedDescription
        }
    }

    @MainActor
    private func addClaim() async {
        guard !working, let value = Double(claimValue), value.isFinite else { return }
        working = true
        defer { working = false }
        do {
            try await appModel.registerNumericDiligenceClaim(
                matterID: selectedMatterID, cik: issuerCIK,
                taxonomy: "us-gaap", tag: claimTag,
                value: value, unit: claimUnit, start: claimStart,
                end: claimEnd, sourceRef: claimSource
            )
            message = "Saved cited numeric assertion for review, not yet verified."
        } catch {
            message = "Claim registration failed: " + error.localizedDescription
        }
    }

    @MainActor
    private func checkMatter() async {
        guard !working else { return }
        working = true
        defer { working = false }
        evidenceLines = []
        sourceLinks = []
        do {
            let result = try await appModel.checkDiligenceMatter(
                matterID: selectedMatterID, includeSanctions: includeSanctions
            )
            message = "Independent sources checked • " + String(describing: result["status"] ?? "unknown")
            for issuer in (result["issuer_checks"] as? [[String: Any]] ?? []) {
                let name = issuer["registrant_name"] as? String ?? issuer["cik"] as? String ?? "Issuer"
                let state = issuer["status"] as? String ?? "unknown"
                evidenceLines.append(name + " • SEC " + state)
                if issuer["name_review_needed"] as? Bool == true {
                    evidenceLines.append("Registrant name differs from asserted name: verify legal-entity history.")
                }
                for filing in (issuer["filings"] as? [[String: Any]] ?? []).prefix(5) {
                    let title = (filing["form"] as? String ?? "Filing")
                        + " • " + (filing["filed"] as? String ?? "")
                    if let url = filing["document_url"] as? String, !url.isEmpty {
                        sourceLinks.append((title: title, url: url))
                    }
                }
                if let reason = issuer["reason"] as? String {
                    evidenceLines.append("Source unavailable: " + reason)
                }
            }
            for claim in result["claim_checks"] as? [[String: Any]] ?? [] {
                let comparison = claim["comparison"] as? [String: Any] ?? [:]
                let kind = comparison["status"] as? String ?? "unavailable"
                evidenceLines.append(
                    "Claim " + (claim["source_ref"] as? String ?? "")
                    + " • " + (claim["concept"] as? String ?? "") + ": " + kind
                )
                if let reason = comparison["reason"] as? String {
                    evidenceLines.append(reason)
                }
            }
            for sanctions in result["sanctions_candidate_reviews"] as? [[String: Any]] ?? [] {
                let screening = sanctions["screening"] as? [String: Any] ?? [:]
                evidenceLines.append(
                    "OFAC primary-name review • "
                    + (sanctions["asserted_name"] as? String ?? "")
                    + ": " + (screening["status"] as? String ?? "unavailable")
                )
                if let note = screening["source_note"] as? String {
                    evidenceLines.append(note)
                }
                if let source = screening["source_url"] as? String {
                    sourceLinks.append((title: "OFAC sanctions source", url: source))
                }
            }
            if let note = result["scope_note"] as? String {
                evidenceLines.append(note)
            }
        } catch {
            message = "Diligence check unavailable: " + error.localizedDescription
        }
    }
}
