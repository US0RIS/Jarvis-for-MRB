import CoreLocation

@MainActor
final class GeofenceManager: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published private(set) var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published private(set) var isMonitoringHome = false
    @Published private(set) var lastLocation: CLLocation?
    @Published private(set) var statusMessage = "Home geofence not configured"

    var onHomeArrival: (() -> Void)?

    private let manager = CLLocationManager()
    private static let homeIdentifier = "jarvis.home"

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        authorizationStatus = manager.authorizationStatus
    }

    func requestAlwaysAuthorization() {
        manager.requestAlwaysAuthorization()
    }

    func requestCurrentLocation() {
        if manager.authorizationStatus == .notDetermined {
            manager.requestWhenInUseAuthorization()
        }
        manager.requestLocation()
    }

    func configureHome(latitude: Double, longitude: Double, radius: Double) {
        guard CLLocationCoordinate2DIsValid(.init(latitude: latitude, longitude: longitude)),
              latitude != 0 || longitude != 0 else {
            statusMessage = "Set a valid home latitude and longitude first"
            return
        }

        if manager.authorizationStatus != .authorizedAlways {
            manager.requestAlwaysAuthorization()
        }

        for region in manager.monitoredRegions where region.identifier == Self.homeIdentifier {
            manager.stopMonitoring(for: region)
        }

        let maxRadius = manager.maximumRegionMonitoringDistance
        let boundedRadius = min(max(50, radius), maxRadius)
        let region = CLCircularRegion(
            center: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            radius: boundedRadius,
            identifier: Self.homeIdentifier
        )
        region.notifyOnEntry = true
        region.notifyOnExit = false
        manager.startMonitoring(for: region)
        manager.requestState(for: region)
        isMonitoringHome = true
        statusMessage = "Monitoring home arrival within \(Int(boundedRadius)) m"
    }

    func stopMonitoringHome() {
        for region in manager.monitoredRegions where region.identifier == Self.homeIdentifier {
            manager.stopMonitoring(for: region)
        }
        isMonitoringHome = false
        statusMessage = "Home geofence stopped"
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            authorizationStatus = manager.authorizationStatus
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didEnterRegion region: CLRegion) {
        guard region.identifier == "jarvis.home" else { return }
        Task { @MainActor in
            statusMessage = "Home arrival detected"
            onHomeArrival?()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didDetermineState state: CLRegionState, for region: CLRegion) {
        guard region.identifier == "jarvis.home" else { return }
        Task { @MainActor in
            statusMessage = state == .inside ? "Currently inside home geofence" : "Home geofence active"
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        Task { @MainActor in
            lastLocation = location
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            statusMessage = error.localizedDescription
        }
    }
}
