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

struct JarvisPhysicalControlView: View {
    @EnvironmentObject var appModel: JarvisAppModel
    @StateObject private var location = PublicCameraLocationRequest()
    @State private var cameras: [PublicCameraListing] = []
    @State private var sourceURL = ""
    @State private var coverage = ""
    @State private var feedback = "Use iPhone location to discover published nearby highway cameras."
    @State private var searching = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("PHYSICAL WORLD")
                .font(.headline)
            Text("Discover official public camera feeds near you. This does not scan Wi-Fi or access private CCTV.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button(searching ? "Searching…" : "Find nearby public cameras") {
                Task { await lookup() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(searching)

            Text(feedback)
                .font(.footnote)
                .foregroundStyle(.secondary)
            if !coverage.isEmpty {
                Text(coverage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ForEach(cameras) { camera in
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
                            @unknown default: EmptyView()
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                    if let stream = URL(string: camera.streamURL), !camera.streamURL.isEmpty {
                        Link("Open official public camera stream", destination: stream)
                            .font(.caption)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
            }
            if let source = URL(string: sourceURL), !sourceURL.isEmpty {
                Link("Official source / coverage details", destination: source)
                    .font(.caption)
            }
        }
        .padding(.vertical, 8)
    }

    @MainActor
    private func lookup() async {
        guard !searching else { return }
        searching = true
        defer { searching = false }
        cameras = []
        coverage = ""
        feedback = "Requesting a one-time location…"
        do {
            let position = try await location.locateOnce()
            feedback = "Checking official public camera catalogs…"
            let response = try await appModel.discoverNearbyPublicCameras(
                latitude: position.coordinate.latitude,
                longitude: position.coordinate.longitude
            )
            cameras = response.cameras
            sourceURL = response.sourceURL
            coverage = response.coverage
            feedback = response.cameras.isEmpty
                ? response.sourceNote
                : "\(response.cameras.count) published cameras nearby. Publisher service status is not proof the image is current."
        } catch {
            feedback = "Camera search unavailable: " + error.localizedDescription
        }
    }
}
