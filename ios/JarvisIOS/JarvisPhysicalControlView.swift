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

/// Standalone iPhone control surface. No MemoMind SDK, device registration or
/// head-worn display is needed to use any function on this screen.
struct JarvisPhysicalHubView: View {
    @EnvironmentObject var appModel: JarvisAppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
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
