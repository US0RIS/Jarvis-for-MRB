import CoreLocation
import Foundation
import MapKit

@MainActor
final class JarvisNavigationController: NSObject, ObservableObject, CLLocationManagerDelegate {
    enum TravelMode: String {
        case driving
        case walking

        var transportType: MKDirectionsTransportType {
            switch self {
            case .driving: return .automobile
            case .walking: return .walking
            }
        }

        var mapsLaunchMode: String {
            switch self {
            case .driving: return MKLaunchOptionsDirectionsModeDriving
            case .walking: return MKLaunchOptionsDirectionsModeWalking
            }
        }

        var activityType: CLActivityType {
            switch self {
            case .driving: return .automotiveNavigation
            case .walking: return .fitness
            }
        }
    }

    @Published private(set) var isNavigating = false
    @Published private(set) var status = "Navigation idle"
    @Published private(set) var destinationName = ""
    @Published private(set) var destinationAddress = ""
    @Published private(set) var nextInstruction = ""
    @Published private(set) var distanceRemainingMeters: CLLocationDistance = 0
    @Published private(set) var expectedArrival: Date?
    @Published private(set) var travelMode: TravelMode = .driving
    @Published private(set) var lastRerouteAt: Date?

    private static var retainedController: JarvisNavigationController?

    @discardableResult
    static func install(appModel: JarvisAppModel) -> JarvisNavigationController {
        if let retainedController {
            retainedController.start()
            return retainedController
        }
        let controller = JarvisNavigationController(appModel: appModel)
        retainedController = controller
        controller.start()
        return controller
    }

    static var current: JarvisNavigationController? { retainedController }

    private struct PendingGuidance {
        let text: String
        let createdAt: Date
    }

    private unowned let appModel: JarvisAppModel
    private let locationManager = CLLocationManager()

    private var activeDestination: MKMapItem?
    private var activeRoute: MKRoute?
    private var steps: [MKRoute.Step] = []
    private var currentStepIndex = 0
    private var minDistanceToCurrentStep = CLLocationDistance.greatestFiniteMagnitude
    private var preparedStepIndex: Int?
    private var immediateStepIndex: Int?
    private var offRouteSamples = 0
    private var rerouteTask: Task<Void, Never>?
    private var guidanceTask: Task<Void, Never>?
    private var pendingGuidance: PendingGuidance?
    private var lastLocation: CLLocation?
    private var locationWaiter: CheckedContinuation<CLLocation?, Never>?
    private var locationRequestID: UUID?
    private var installed = false

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        locationManager.distanceFilter = 5
        locationManager.pausesLocationUpdatesAutomatically = false
    }

    func start() {
        guard !installed else { return }
        installed = true
        let previousHandler = appModel.frontendCommandHandler
        appModel.frontendCommandHandler = { [weak self] command in
            if let self, let response = await self.handle(command) {
                return response
            }
            return await previousHandler?(command)
        }
    }

    func stop() {
        installed = false
        stopNavigation(speakArrival: false)
    }

    func handle(_ rawCommand: String) async -> String? {
        let command = Self.normalize(rawCommand)

        if Self.isStopCommand(command) {
            guard isNavigating else { return "Navigation is not currently active." }
            stopNavigation(speakArrival: false)
            return "Navigation stopped."
        }

        if Self.isStatusCommand(command) {
            return navigationStatusText()
        }

        if Self.isNextTurnCommand(command) {
            guard isNavigating else { return "Navigation is not currently active." }
            let distance = currentStepDistance(from: lastLocation)
            if let distance {
                return "Next: \(nextInstruction). \(Self.distancePhrase(distance)) away."
            }
            return nextInstruction.isEmpty ? "I am recalculating the next maneuver." : "Next: \(nextInstruction)."
        }

        if Self.isMapsHandoffCommand(command) {
            guard let activeDestination else { return "There is no active route to open in Apple Maps." }
            activeDestination.openInMaps(launchOptions: [
                MKLaunchOptionsDirectionsModeKey: travelMode.mapsLaunchMode,
                MKLaunchOptionsShowsTrafficKey: travelMode == .driving,
            ])
            return "I opened the active route to \(destinationName) in Apple Maps."
        }

        if Self.isRerouteCommand(command) {
            guard isNavigating, let activeDestination else { return "There is no active route to recalculate." }
            guard let origin = await currentLocation() else { return locationUnavailableMessage() }
            do {
                let route = try await calculateRoute(from: origin, to: activeDestination, mode: travelMode)
                activate(route: route, destination: activeDestination, mode: travelMode, announceFirstStepInResponse: false)
                lastRerouteAt = Date()
                return "Route recalculated. Next: \(nextInstruction)."
            } catch {
                status = "Reroute failed: \(error.localizedDescription)"
                return "I could not recalculate the route right now. The current route is still active."
            }
        }

        guard let request = Self.navigationRequest(from: command) else { return nil }
        let destinationQuery = request.destination.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !destinationQuery.isEmpty else { return "Tell me the destination after ‘take me to’." }

        status = "Resolving \(destinationQuery)…"
        guard let origin = await currentLocation() else { return locationUnavailableMessage() }

        do {
            let destination = try await resolveDestination(destinationQuery, near: origin)
            status = "Calculating route to \(destination.name ?? destinationQuery)…"
            let route = try await calculateRoute(from: origin, to: destination, mode: request.mode)
            activate(route: route, destination: destination, mode: request.mode, announceFirstStepInResponse: true)

            let distance = Self.distancePhrase(route.distance)
            let duration = Self.durationPhrase(route.expectedTravelTime)
            let eta = Date().addingTimeInterval(route.expectedTravelTime)
            expectedArrival = eta
            let resolved = destinationAddress.isEmpty ? destinationName : "\(destinationName), \(destinationAddress)"
            let first = nextInstruction.isEmpty ? "" : " First direction: \(nextInstruction)."
            return "Starting \(request.mode.rawValue) navigation to \(resolved). \(distance), about \(duration). ETA \(Self.timePhrase(eta)).\(first)"
        } catch let error as NavigationError {
            status = error.localizedDescription
            return error.localizedDescription
        } catch {
            status = "Navigation unavailable: \(error.localizedDescription)"
            return "I could not calculate a route to \(destinationQuery) right now."
        }
    }

    private func activate(
        route: MKRoute,
        destination: MKMapItem,
        mode: TravelMode,
        announceFirstStepInResponse: Bool
    ) {
        activeRoute = route
        activeDestination = destination
        travelMode = mode
        destinationName = destination.name?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty
            ?? destination.placemark.title?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty
            ?? "destination"
        destinationAddress = Self.address(for: destination)
        steps = route.steps.filter { !$0.instructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        currentStepIndex = 0
        minDistanceToCurrentStep = .greatestFiniteMagnitude
        preparedStepIndex = announceFirstStepInResponse && !steps.isEmpty ? 0 : nil
        immediateStepIndex = announceFirstStepInResponse && !steps.isEmpty ? 0 : nil
        offRouteSamples = 0
        distanceRemainingMeters = route.distance
        expectedArrival = Date().addingTimeInterval(route.expectedTravelTime)
        nextInstruction = steps.first?.instructions.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Continue on the route"
        isNavigating = true
        status = "Navigating to \(destinationName)"

        locationManager.activityType = mode.activityType
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        locationManager.distanceFilter = mode == .driving ? 8 : 4
        locationManager.pausesLocationUpdatesAutomatically = false
        locationManager.allowsBackgroundLocationUpdates = true
        locationManager.showsBackgroundLocationIndicator = true
        locationManager.startUpdatingLocation()
    }

    private func stopNavigation(speakArrival: Bool) {
        rerouteTask?.cancel()
        rerouteTask = nil
        guidanceTask?.cancel()
        guidanceTask = nil
        pendingGuidance = nil
        locationManager.stopUpdatingLocation()
        locationManager.allowsBackgroundLocationUpdates = false
        locationManager.showsBackgroundLocationIndicator = false
        activeRoute = nil
        activeDestination = nil
        steps = []
        currentStepIndex = 0
        nextInstruction = ""
        distanceRemainingMeters = 0
        expectedArrival = nil
        offRouteSamples = 0
        isNavigating = false
        status = speakArrival ? "Arrived at \(destinationName)" : "Navigation idle"
    }

    private func currentLocation() async -> CLLocation? {
        if let lastLocation,
           Date().timeIntervalSince(lastLocation.timestamp) < 20,
           lastLocation.horizontalAccuracy >= 0,
           lastLocation.horizontalAccuracy <= 150 {
            return lastLocation
        }

        if locationManager.authorizationStatus == .notDetermined {
            locationManager.requestWhenInUseAuthorization()
            for _ in 0..<40 where locationManager.authorizationStatus == .notDetermined {
                try? await Task.sleep(for: .milliseconds(250))
            }
        }

        guard locationManager.authorizationStatus == .authorizedAlways
                || locationManager.authorizationStatus == .authorizedWhenInUse else {
            return nil
        }

        let requestID = UUID()
        locationRequestID = requestID
        return await withCheckedContinuation { continuation in
            locationWaiter = continuation
            locationManager.requestLocation()
            Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(8))
                guard let self, self.locationRequestID == requestID else { return }
                self.locationRequestID = nil
                let waiter = self.locationWaiter
                self.locationWaiter = nil
                waiter?.resume(returning: self.lastLocation)
            }
        }
    }

    private func resolveDestination(_ query: String, near origin: CLLocation) async throws -> MKMapItem {
        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = query
        request.region = MKCoordinateRegion(
            center: origin.coordinate,
            latitudinalMeters: 160_000,
            longitudinalMeters: 160_000
        )
        let response = try await MKLocalSearch(request: request).start()
        guard !response.mapItems.isEmpty else {
            throw NavigationError.destinationNotFound(query)
        }

        let normalizedQuery = Self.normalizeName(query)
        let ranked = response.mapItems.map { item -> (MKMapItem, Double) in
            let name = Self.normalizeName(item.name ?? "")
            let title = Self.normalizeName(item.placemark.title ?? "")
            var score = 0.0
            if name == normalizedQuery { score += 300 }
            if !name.isEmpty && (normalizedQuery.contains(name) || name.contains(normalizedQuery)) { score += 130 }
            if !title.isEmpty && title.contains(normalizedQuery) { score += 90 }
            let place = CLLocation(latitude: item.placemark.coordinate.latitude, longitude: item.placemark.coordinate.longitude)
            let kilometers = origin.distance(from: place) / 1000
            score -= min(kilometers, 500) * 0.35
            return (item, score)
        }.sorted { $0.1 > $1.1 }

        return ranked[0].0
    }

    private func calculateRoute(from origin: CLLocation, to destination: MKMapItem, mode: TravelMode) async throws -> MKRoute {
        let request = MKDirections.Request()
        request.source = MKMapItem(placemark: MKPlacemark(coordinate: origin.coordinate))
        request.destination = destination
        request.transportType = mode.transportType
        request.requestsAlternateRoutes = true
        let response = try await MKDirections(request: request).calculate()
        guard let route = response.routes.min(by: { $0.expectedTravelTime < $1.expectedTravelTime }) else {
            throw NavigationError.noRoute(destination.name ?? "destination")
        }
        return route
    }

    private func processLocation(_ location: CLLocation) {
        guard isNavigating,
              location.horizontalAccuracy >= 0,
              location.horizontalAccuracy <= 120,
              let route = activeRoute,
              let destination = activeDestination else { return }

        lastLocation = location
        let destinationLocation = CLLocation(
            latitude: destination.placemark.coordinate.latitude,
            longitude: destination.placemark.coordinate.longitude
        )
        let destinationDistance = location.distance(from: destinationLocation)

        if destinationDistance <= max(28, location.horizontalAccuracy * 1.2) {
            let arrivalName = destinationName
            stopNavigation(speakArrival: true)
            queueGuidance("You have arrived at \(arrivalName).")
            return
        }

        distanceRemainingMeters = max(0, approximateRemainingDistance(from: location, route: route))
        if location.speed >= 0 {
            let speed = max(location.speed, travelMode == .driving ? 8 : 1.2)
            expectedArrival = Date().addingTimeInterval(distanceRemainingMeters / speed)
        }

        let offRouteDistance = Self.distance(from: location.coordinate, to: route.polyline)
        let allowedDeviation = max(90, location.horizontalAccuracy * 2.2)
        if offRouteDistance > allowedDeviation {
            offRouteSamples += 1
        } else {
            offRouteSamples = 0
        }
        if offRouteSamples >= 3 {
            scheduleReroute(from: location)
            offRouteSamples = 0
        }

        guard !steps.isEmpty, currentStepIndex < steps.count else { return }
        let step = steps[currentStepIndex]
        let distance = Self.distanceToEnd(of: step, from: location)
        minDistanceToCurrentStep = min(minDistanceToCurrentStep, distance)
        nextInstruction = step.instructions.trimmingCharacters(in: .whitespacesAndNewlines)

        let prepareThreshold = preparationThreshold(speed: max(0, location.speed), mode: travelMode)
        let immediateThreshold = immediateThreshold(speed: max(0, location.speed), mode: travelMode)

        if preparedStepIndex != currentStepIndex,
           distance <= prepareThreshold,
           distance > immediateThreshold * 1.15 {
            preparedStepIndex = currentStepIndex
            queueGuidance("In \(Self.distancePhrase(distance)), \(Self.lowercasedInstruction(nextInstruction)).")
        }

        if immediateStepIndex != currentStepIndex,
           distance <= immediateThreshold {
            immediateStepIndex = currentStepIndex
            queueGuidance(nextInstruction)
        }

        let passedManeuver = minDistanceToCurrentStep <= max(35, location.horizontalAccuracy * 1.2)
            && distance >= minDistanceToCurrentStep + max(35, location.horizontalAccuracy)
        if distance <= max(18, location.horizontalAccuracy * 0.8) || passedManeuver {
            advanceStep()
        }
    }

    private func advanceStep() {
        guard currentStepIndex + 1 < steps.count else { return }
        currentStepIndex += 1
        minDistanceToCurrentStep = .greatestFiniteMagnitude
        nextInstruction = steps[currentStepIndex].instructions.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func scheduleReroute(from location: CLLocation) {
        guard rerouteTask == nil,
              let destination = activeDestination,
              lastRerouteAt.map({ Date().timeIntervalSince($0) >= 20 }) ?? true else { return }

        status = "Off route • recalculating"
        queueGuidance("Rerouting.")
        rerouteTask = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.rerouteTask = nil }
            do {
                let route = try await self.calculateRoute(from: location, to: destination, mode: self.travelMode)
                self.activate(route: route, destination: destination, mode: self.travelMode, announceFirstStepInResponse: false)
                self.lastRerouteAt = Date()
                self.status = "Rerouted to \(self.destinationName)"
                if !self.nextInstruction.isEmpty {
                    self.queueGuidance("New route. \(self.nextInstruction)")
                }
            } catch {
                self.status = "Reroute failed • continuing current route"
            }
        }
    }

    private func queueGuidance(_ raw: String) {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, appModel.settings.speakResponses else { return }
        pendingGuidance = PendingGuidance(text: text, createdAt: Date())
        guard guidanceTask == nil else { return }

        guidanceTask = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.guidanceTask = nil }
            while !Task.isCancelled {
                guard let pending = self.pendingGuidance else { return }
                if Date().timeIntervalSince(pending.createdAt) > 18 {
                    self.pendingGuidance = nil
                    continue
                }
                let pushToTalkBusy = self.appModel.isListening && !self.appModel.handsFreeEnabled
                if self.appModel.isSending || pushToTalkBusy || self.appModel.speechSynthesizer.isSpeaking {
                    try? await Task.sleep(for: .milliseconds(250))
                    continue
                }
                self.pendingGuidance = nil
                await self.speakGuidance(pending.text)
            }
        }
    }

    private func speakGuidance(_ text: String) async {
        let wasHandsFree = appModel.handsFreeEnabled
        if wasHandsFree {
            appModel.stopWakeWordMode()
        } else if appModel.isListening || appModel.speechRecognizer.isActive {
            _ = appModel.speechRecognizer.stopListening()
            appModel.isListening = false
        }

        await appModel.speakFrontendResponseIfEnabled(text)

        if wasHandsFree {
            try? await Task.sleep(for: .milliseconds(180))
            await appModel.startWakeWordMode()
        }
    }

    private func navigationStatusText() -> String {
        guard isNavigating else { return "Navigation is not currently active." }
        var parts = ["Navigating to \(destinationName)."]
        if distanceRemainingMeters > 0 { parts.append("About \(Self.distancePhrase(distanceRemainingMeters)) remaining.") }
        if let expectedArrival { parts.append("ETA \(Self.timePhrase(expectedArrival)).") }
        if !nextInstruction.isEmpty { parts.append("Next: \(nextInstruction).") }
        return parts.joined(separator: " ")
    }

    private func currentStepDistance(from location: CLLocation?) -> CLLocationDistance? {
        guard let location, currentStepIndex < steps.count else { return nil }
        return Self.distanceToEnd(of: steps[currentStepIndex], from: location)
    }

    private func approximateRemainingDistance(from location: CLLocation, route: MKRoute) -> CLLocationDistance {
        guard !steps.isEmpty, currentStepIndex < steps.count else {
            let destination = route.steps.last.flatMap { Self.finalCoordinate(of: $0.polyline) }
                ?? route.polyline.coordinate
            return CLLocation(latitude: destination.latitude, longitude: destination.longitude).distance(from: location)
        }
        let current = Self.distanceToEnd(of: steps[currentStepIndex], from: location)
        let after = steps.dropFirst(currentStepIndex + 1).reduce(0.0) { $0 + $1.distance }
        return current + after
    }

    private func preparationThreshold(speed: CLLocationSpeed, mode: TravelMode) -> CLLocationDistance {
        switch mode {
        case .walking: return 85
        case .driving:
            if speed >= 24 { return 900 }
            if speed >= 15 { return 550 }
            return 300
        }
    }

    private func immediateThreshold(speed: CLLocationSpeed, mode: TravelMode) -> CLLocationDistance {
        switch mode {
        case .walking: return 22
        case .driving:
            if speed >= 24 { return 180 }
            if speed >= 15 { return 110 }
            return 65
        }
    }

    private func locationUnavailableMessage() -> String {
        switch locationManager.authorizationStatus {
        case .denied, .restricted:
            status = "Location permission required"
            return "I need iPhone location permission to start turn-by-turn navigation. Enable Location for Jarvis in Settings, then ask again."
        default:
            status = "Current location unavailable"
            return "I could not get a reliable current location yet. Try again when the iPhone has a GPS fix."
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            if manager.authorizationStatus == .authorizedAlways || manager.authorizationStatus == .authorizedWhenInUse {
                status = isNavigating ? "Navigating to \(destinationName)" : "Location ready for navigation"
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        Task { @MainActor in
            lastLocation = location
            if let waiter = locationWaiter {
                locationWaiter = nil
                locationRequestID = nil
                waiter.resume(returning: location)
            }
            processLocation(location)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            if let waiter = locationWaiter {
                locationWaiter = nil
                locationRequestID = nil
                waiter.resume(returning: lastLocation)
            }
            if isNavigating {
                status = "Navigation location warning: \(error.localizedDescription)"
            }
        }
    }

    private static func navigationRequest(from normalizedCommand: String) -> (destination: String, mode: TravelMode)? {
        let patterns: [(String, TravelMode)] = [
            ("take me to ", .driving),
            ("navigate me to ", .driving),
            ("navigate to ", .driving),
            ("drive me to ", .driving),
            ("drive to ", .driving),
            ("get me to ", .driving),
            ("directions to ", .driving),
            ("walk me to ", .walking),
            ("walk to ", .walking),
            ("walking directions to ", .walking),
        ]
        for (prefix, mode) in patterns where normalizedCommand.hasPrefix(prefix) {
            return (String(normalizedCommand.dropFirst(prefix.count)), mode)
        }
        return nil
    }

    static func isNavigationIntent(_ raw: String) -> Bool {
        let n = normalize(raw)
        return navigationRequest(from: n) != nil
            || isStopCommand(n)
            || isStatusCommand(n)
            || isNextTurnCommand(n)
            || isMapsHandoffCommand(n)
            || isRerouteCommand(n)
    }

    private static func isStopCommand(_ n: String) -> Bool {
        ["stop navigation", "cancel navigation", "end navigation", "stop directions", "cancel directions"].contains(n)
    }

    private static func isStatusCommand(_ n: String) -> Bool {
        ["navigation status", "where are we going", "how much farther", "how much further", "what is our eta", "what's our eta", "eta"].contains(n)
    }

    private static func isNextTurnCommand(_ n: String) -> Bool {
        ["next turn", "what is the next turn", "what's the next turn", "next direction", "what do i do next on this route"].contains(n)
    }

    private static func isMapsHandoffCommand(_ n: String) -> Bool {
        ["open route in maps", "open this route in maps", "open in apple maps", "show route in apple maps"].contains(n)
    }

    private static func isRerouteCommand(_ n: String) -> Bool {
        ["reroute", "recalculate route", "recalculate navigation", "find another route"].contains(n)
    }

    private static func normalize(_ raw: String) -> String {
        raw.lowercased()
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
    }

    private static func normalizeName(_ raw: String) -> String {
        raw.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private static func address(for item: MKMapItem) -> String {
        let placemark = item.placemark
        let street = [placemark.subThoroughfare, placemark.thoroughfare]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty }
            .joined(separator: " ")
        let cityLine = [placemark.locality, placemark.administrativeArea, placemark.postalCode]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty }
            .joined(separator: ", ")
        return [street, cityLine].filter { !$0.isEmpty }.joined(separator: ", ")
    }

    private static func distanceToEnd(of step: MKRoute.Step, from location: CLLocation) -> CLLocationDistance {
        guard let coordinate = finalCoordinate(of: step.polyline) else { return step.distance }
        return location.distance(from: CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude))
    }

    private static func finalCoordinate(of polyline: MKPolyline) -> CLLocationCoordinate2D? {
        guard polyline.pointCount > 0 else { return nil }
        return polyline.points()[polyline.pointCount - 1].coordinate
    }

    private static func distance(from coordinate: CLLocationCoordinate2D, to polyline: MKPolyline) -> CLLocationDistance {
        guard polyline.pointCount > 0 else { return .greatestFiniteMagnitude }
        let target = MKMapPoint(coordinate)
        let points = polyline.points()
        if polyline.pointCount == 1 {
            return target.distance(to: points[0])
        }
        var minimum = CLLocationDistance.greatestFiniteMagnitude
        for index in 0..<(polyline.pointCount - 1) {
            minimum = min(minimum, pointToSegmentDistance(target, points[index], points[index + 1]))
        }
        return minimum
    }

    private static func pointToSegmentDistance(_ point: MKMapPoint, _ a: MKMapPoint, _ b: MKMapPoint) -> CLLocationDistance {
        let dx = b.x - a.x
        let dy = b.y - a.y
        let lengthSquared = dx * dx + dy * dy
        if lengthSquared <= 0 { return point.distance(to: a) }
        let t = max(0, min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSquared))
        let projection = MKMapPoint(x: a.x + t * dx, y: a.y + t * dy)
        return point.distance(to: projection)
    }

    private static func distancePhrase(_ meters: CLLocationDistance) -> String {
        let miles = meters / 1609.344
        if miles >= 10 { return "\(Int(miles.rounded())) miles" }
        if miles >= 0.2 { return String(format: "%.1f miles", miles) }
        let feet = max(10, Int((meters * 3.28084 / 10).rounded() * 10))
        return "\(feet) feet"
    }

    private static func durationPhrase(_ seconds: TimeInterval) -> String {
        let minutes = max(1, Int((seconds / 60).rounded()))
        if minutes < 60 { return "\(minutes) minutes" }
        let hours = minutes / 60
        let remainder = minutes % 60
        if remainder == 0 { return hours == 1 ? "1 hour" : "\(hours) hours" }
        return "\(hours) hour\(hours == 1 ? "" : "s") \(remainder) minutes"
    }

    private static func timePhrase(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }

    private static func lowercasedInstruction(_ instruction: String) -> String {
        guard let first = instruction.first else { return instruction }
        return first.lowercased() + instruction.dropFirst()
    }

    enum NavigationError: LocalizedError {
        case destinationNotFound(String)
        case noRoute(String)

        var errorDescription: String? {
            switch self {
            case .destinationNotFound(let query):
                return "I could not find a destination matching \(query). Try a business name plus city, or a street address."
            case .noRoute(let destination):
                return "I found \(destination), but MapKit could not calculate a route from your current location."
            }
        }
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}
