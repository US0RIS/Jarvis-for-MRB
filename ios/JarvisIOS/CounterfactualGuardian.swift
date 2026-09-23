import CoreLocation
import Foundation
import MapKit
import SwiftUI
import UIKit

/// A current, evidence-backed risk to reaching an explicitly scheduled place.
/// The route is estimated by Apple MapKit, NOT a guess from calendar text or an LLM.
struct GuardianTrajectory: Identifiable {
    let id: String
    let calendarID: String
    let title: String
    let calendarLocation: String
    let startsAt: Date
    let checkedAt: Date
    let drivingSeconds: TimeInterval
    let distanceMeters: CLLocationDistance
    let secondsUntilStart: TimeInterval
    let marginSeconds: TimeInterval

    var estimatedArrival: Date { checkedAt.addingTimeInterval(drivingSeconds) }
    var predictedLateMinutes: Int {
        max(0, Int(ceil((drivingSeconds - secondsUntilStart) / 60)))
    }
    var brief: String {
        let until = max(1, Int(ceil(secondsUntilStart / 60)))
        let travel = max(1, Int(ceil(drivingSeconds / 60)))
        if predictedLateMinutes > 0 {
            return "\(title) begins in \(until) minutes. Apple MapKit estimates a \(travel)-minute drive, about \(predictedLateMinutes) minutes beyond the start. I'd leave now."
        }
        return "\(title) begins in \(until) minutes. Apple MapKit estimates a \(travel)-minute drive. That leaves under five minutes to depart and still have a small buffer."
    }
    var evidence: String {
        "Calendar event \(startsAt.formatted(date: .abbreviated, time: .shortened)) • calendar location: \(calendarLocation) • fresh iPhone GPS • Apple MapKit driving route checked \(checkedAt.formatted(date: .omitted, time: .shortened)). Driving conditions may change."
    }
}

/// Enrollment is exact to one Calendar event, timestamp and location; expires
/// at the event start (or earlier) and cannot silently transfer to another
/// meeting that happens to have a similar title.
private struct GuardianNavigationGrant: Codable {
    let calendarID: String
    let startsAt: Date
    let location: String
    let expiresAt: Date
}

struct GuardianHandoffReceipt: Identifiable, Codable {
    let id: UUID
    let at: Date
    let title: String
    let source: String
    let outcome: String
    let authorizedAutomatically: Bool
}

enum GuardianTrajectoryPolicy {
    /// A deterministic, testable evaluator: missing/stale observations and
    /// merely close-by destinations cannot turn into fabricated late alerts.
    static func departureRisk(
        now: Date, startsAt: Date, drivingSeconds: TimeInterval,
        distanceMeters: CLLocationDistance, locationAge: TimeInterval,
        horizontalAccuracy: CLLocationAccuracy
    ) -> (until: TimeInterval, margin: TimeInterval)? {
        let until = startsAt.timeIntervalSince(now)
        guard (240...7200).contains(until),
              drivingSeconds.isFinite, drivingSeconds > 30,
              distanceMeters.isFinite, distanceMeters > 200,
              (0...75).contains(locationAge),
              (0...150).contains(horizontalAccuracy) else { return nil }
        // Five minutes is a stated buffer, not a forecast error bound.
        let margin = until - drivingSeconds - 300
        guard margin <= 0 else { return nil }
        return (until, margin)
    }
}

@MainActor
final class CounterfactualGuardianController: ObservableObject {
    @Published private(set) var trajectories: [GuardianTrajectory] = []
    @Published private(set) var status = "Off — enable Counterfactual Guardian under Settings."
    @Published private(set) var isChecking = false
    @Published private(set) var handoffHistory: [GuardianHandoffReceipt] = []
    @Published private(set) var stagedMessage = ""
    @Published private(set) var lastAlert = ""
    @Published private(set) var lastCheckedAt: Date?

    private static let grantsKey = "jarvis.guardian.navigationGrants.v1"
    private static let dismissedKey = "jarvis.guardian.dismissals.v1"
    private static let receiptsKey = "jarvis.guardian.handoffReceipts.v1"

    private unowned let appModel: JarvisAppModel
    private weak var frontend: FrontendIntelligenceController?
    private var loopTask: Task<Void, Never>?
    private var started = false
    private var lastPoll = Date.distantPast
    private var grants: [String: GuardianNavigationGrant] = [:]
    private var dismissed: [String: Date] = [:]
    private var announced: Set<String> = []
    private var destinationByRisk: [String: MKMapItem] = [:]

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
        if let data = KeychainStore.readData(Self.grantsKey),
           let saved = try? JSONDecoder().decode([String: GuardianNavigationGrant].self, from: data) {
            grants = saved
        }
        if let data = KeychainStore.readData(Self.dismissedKey),
           let saved = try? JSONDecoder().decode([String: Date].self, from: data) {
            dismissed = saved
        }
        if let data = KeychainStore.readData(Self.receiptsKey),
           let saved = try? JSONDecoder().decode([GuardianHandoffReceipt].self, from: data) {
            handoffHistory = Array(saved.suffix(30))
        }
    }

    func attach(frontend: FrontendIntelligenceController) {
        self.frontend = frontend
    }

    func start() {
        guard !started else { return }
        started = true
        loopTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled && self.started {
                if !self.appModel.settings.guardianEnabled {
                    // Off (including Privacy mode) means no latent automatic
                    // grant survives a later re-enable.
                    if !self.grants.isEmpty {
                        self.grants.removeAll()
                        self.persistGrants()
                    }
                    self.trajectories = []
                    self.destinationByRisk = [:]
                    self.stagedMessage = ""
                    self.status = "Off — enable Counterfactual Guardian under Settings."
                }
                if self.appModel.settings.guardianEnabled,
                   self.appModel.settings.localSensorContextEnabled,
                   UIApplication.shared.applicationState == .active,
                   Date().timeIntervalSince(self.lastPoll) >= 120 {
                    await self.checkNow(manual: false)
                }
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    func stop() {
        started = false
        loopTask?.cancel()
        loopTask = nil
        trajectories = []
        destinationByRisk = [:]
        stagedMessage = ""
    }

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    private static func parseStart(_ raw: String) -> Date? {
        guard raw.contains("T") else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let parsed = formatter.date(from: raw) { return parsed }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: raw)
    }

    private static func eventKey(_ event: GuardianCalendarResponse.Event, start: Date) -> String {
        event.id + "|" + String(Int(start.timeIntervalSince1970)) + "|" + event.location
    }

    private static func virtualLocation(_ raw: String) -> Bool {
        let words = raw.lowercased()
        return ["zoom.us", "meet.google", "teams.microsoft", "webex",
                "https://", "http://", "video call", "phone call",
                "virtual", "online", "dial-in"].contains(where: words.contains)
    }

    private func freshLocation() -> CLLocation? {
        guard appModel.settings.localSensorContextEnabled,
              let sensors = frontend?.sensors,
              let coordinate = sensors.coordinate,
              let at = sensors.lastLocationAt,
              coordinate.latitude.isFinite, coordinate.longitude.isFinite,
              abs(coordinate.latitude) <= 90, abs(coordinate.longitude) <= 180,
              (0...75).contains(Date().timeIntervalSince(at)),
              let accuracy = sensors.horizontalAccuracyMeters,
              (0...150).contains(accuracy) else { return nil }
        return CLLocation(
            coordinate: coordinate,
            altitude: 0,
            horizontalAccuracy: accuracy,
            verticalAccuracy: -1,
            timestamp: at
        )
    }

    private func resolveExactly(_ location: String, near phone: CLLocation) async throws -> MKMapItem? {
        guard !Self.virtualLocation(location) else { return nil }
        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = location
        request.region = MKCoordinateRegion(
            center: phone.coordinate,
            latitudinalMeters: 160_000,
            longitudinalMeters: 160_000
        )
        let response = try await MKLocalSearch(request: request).start()
        guard !response.mapItems.isEmpty else { return nil }
        if response.mapItems.count == 1 { return response.mapItems.first }
        // Multiple matching places are not authority to choose one: require
        // a unique literal name/address match or mark the route unresolved.
        func normalized(_ value: String) -> String {
            value.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .joined(separator: " ")
        }
        let target = normalized(location)
        let exact = response.mapItems.filter {
            normalized($0.name ?? "") == target
                || normalized($0.placemark.title ?? "") == target
        }
        return exact.count == 1 ? exact.first : nil
    }

    private func drivingRoute(from phone: CLLocation, to item: MKMapItem) async throws -> MKRoute? {
        let request = MKDirections.Request()
        request.source = MKMapItem(placemark: MKPlacemark(coordinate: phone.coordinate))
        request.destination = item
        request.transportType = .automobile
        request.requestsAlternateRoutes = true
        let response = try await MKDirections(request: request).calculate()
        return response.routes
            .filter { $0.expectedTravelTime.isFinite && $0.expectedTravelTime > 0 }
            .min { $0.expectedTravelTime < $1.expectedTravelTime }
    }

    func checkNow(manual: Bool = true) async {
        guard !isChecking else { return }
        guard appModel.settings.guardianEnabled else {
            status = "Guardian is off. Enable it before checking your calendar or location."
            return
        }
        guard UIApplication.shared.applicationState == .active else {
            status = "Guardian cannot check while the app is suspended."
            return
        }
        guard let origin = freshLocation() else {
            trajectories = []
            destinationByRisk = [:]
            status = "Unknown — enable Motion / travel context and obtain a fresh accurate GPS fix. No departure prediction made."
            return
        }
        isChecking = true
        lastPoll = Date()
        status = "Checking your next calendar destinations against live driving routes…"
        defer { isChecking = false }

        let calendar: GuardianCalendarResponse
        do {
            calendar = try await client.guardianCalendarExpectations()
        } catch {
            status = "Unknown — Jarvis Calendar is unavailable. No departure prediction made."
            trajectories = []
            destinationByRisk = [:]
            return
        }
        guard let checked = Self.parseStart(calendar.checkedAt),
              abs(Date().timeIntervalSince(checked)) <= 120 else {
            status = "Unknown — Calendar response lacks a fresh timestamp."
            trajectories = []
            destinationByRisk = [:]
            return
        }
        guard let currentPosition = freshLocation() else {
            status = "Unknown — location expired during the calendar lookup."
            trajectories = []
            destinationByRisk = [:]
            return
        }
        _ = origin // position has been rechecked after remote calendar access.

        let now = Date()
        let upcoming = calendar.events.compactMap { event -> (GuardianCalendarResponse.Event, Date)? in
            guard !event.id.isEmpty, !event.location.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  let start = Self.parseStart(event.start),
                  (240...7200).contains(start.timeIntervalSince(now)),
                  !Self.virtualLocation(event.location) else { return nil }
            return (event, start)
        }.sorted { $0.1 < $1.1 }
        // A bounded local pass: avoid hammering MapKit for a full-day agenda.
        var found: [GuardianTrajectory] = []
        var resolved: [String: MKMapItem] = [:]
        var unresolved = 0
        for (event, begins) in upcoming.prefix(3) {
            if Task.isCancelled { return }
            guard let phone = freshLocation() else {
                status = "Unknown — GPS expired during route calculation."
                trajectories = []
                destinationByRisk = [:]
                return
            }
            do {
                guard let place = try await resolveExactly(event.location, near: phone),
                      let route = try await drivingRoute(from: phone, to: place) else {
                    unresolved += 1
                    continue
                }
                let destination = CLLocation(
                    latitude: place.placemark.coordinate.latitude,
                    longitude: place.placemark.coordinate.longitude
                )
                let actualDistance = phone.distance(from: destination)
                let evaluationTime = Date()
                guard let decision = GuardianTrajectoryPolicy.departureRisk(
                    now: evaluationTime, startsAt: begins,
                    drivingSeconds: route.expectedTravelTime,
                    distanceMeters: actualDistance,
                    locationAge: evaluationTime.timeIntervalSince(phone.timestamp),
                    horizontalAccuracy: phone.horizontalAccuracy
                ) else { continue }
                let id = Self.eventKey(event, start: begins)
                let candidate = GuardianTrajectory(
                    id: id, calendarID: event.id,
                    title: event.summary.isEmpty ? "Appointment" : event.summary,
                    calendarLocation: event.location,
                    startsAt: begins, checkedAt: evaluationTime,
                    drivingSeconds: route.expectedTravelTime,
                    distanceMeters: actualDistance,
                    secondsUntilStart: decision.until,
                    marginSeconds: decision.margin
                )
                found.append(candidate)
                resolved[id] = place
            } catch {
                unresolved += 1
            }
        }

        // A route/calendar request can outlive an iOS foreground session or
        // explicit consent. Never fire an interruption from a stale session.
        guard UIApplication.shared.applicationState == .active,
              appModel.settings.guardianEnabled else {
            trajectories = []
            destinationByRisk = [:]
            status = "Guardian paused — app inactive or automatic monitoring disabled."
            return
        }
        trajectories = found
        destinationByRisk = resolved
        lastCheckedAt = Date()
        if found.isEmpty {
            status = unresolved > 0
                ? "No confirmed departure risk from the routes I could resolve. \(unresolved) destination(s) remain unknown; this is not an all-clear."
                : "No departure risk found in the next two hours from the first three usable calendar destinations. Estimates can change."
        } else {
            status = "\(found.count) current departure risk(s). Apple MapKit driving ETA and event timing were checked on this iPhone."
        }
        pruneGrantsAndDismissals()
        if appModel.settings.guardianEnabled && !manual {
            for candidate in found {
                if dismissed[candidate.id].map({ $0 > Date() }) == true { continue }
                if hasGrant(for: candidate), !appModel.isSending,
                   !appModel.isCurrentlyNavigating,
                   frontend?.isMeetingActive != true,
                   frontend?.sensors.activity != "Driving",
                   !appModel.speechSynthesizer.isSpeaking {
                    let result = startDirections(for: candidate.id, automatically: true)
                    if result {
                        // Starting external Maps ends the foreground polling
                        // session. Never execute another action in this cycle.
                        return
                    }
                }
                if !announced.contains(candidate.id) {
                    announced.insert(candidate.id)
                    lastAlert = candidate.brief
                    appModel.memoMind.presentProactiveAlert(candidate.brief, severity: "warning")
                    if appModel.settings.proactiveAnnouncements,
                       !appModel.isSending, !appModel.isListening,
                       !appModel.speechSynthesizer.isSpeaking,
                       frontend?.isMeetingActive != true,
                       frontend?.sensors.activity != "Driving" {
                        await appModel.speakFrontendResponseIfEnabled(candidate.brief)
                    }
                }
            }
        }
    }

    func hasGrant(for candidate: GuardianTrajectory) -> Bool {
        guard let grant = grants[candidate.id] else { return false }
        return grant.calendarID == candidate.calendarID
            && grant.location == candidate.calendarLocation
            && grant.startsAt == candidate.startsAt
            && grant.expiresAt > Date()
    }

    func authorizeNavigationOnce(for id: String) {
        guard appModel.settings.guardianEnabled,
              let candidate = trajectories.first(where: { $0.id == id }),
              candidate.startsAt > Date(), destinationByRisk[id] != nil else { return }
        let expiry = min(candidate.startsAt, Date().addingTimeInterval(2 * 3600))
        grants[id] = GuardianNavigationGrant(
            calendarID: candidate.calendarID,
            startsAt: candidate.startsAt,
            location: candidate.calendarLocation,
            expiresAt: expiry
        )
        persistGrants()
        status = "One-time Apple Maps handoff enrolled only for \(candidate.title) at \(candidate.startsAt.formatted(date: .omitted, time: .shortened)). Revoke it below if plans change."
    }

    func revokeNavigation(for id: String) {
        grants.removeValue(forKey: id)
        persistGrants()
        status = "Automatic directions authorization revoked."
    }

    func dismiss(_ id: String) {
        guard let candidate = trajectories.first(where: { $0.id == id }) else { return }
        grants.removeValue(forKey: id)
        persistGrants()
        dismissed[id] = candidate.startsAt.addingTimeInterval(3600)
        persistDismissals()
        trajectories.removeAll { $0.id == id }
        destinationByRisk.removeValue(forKey: id)
        status = "Dismissed for this event and revoked its navigation grant."
    }

    func stageETA(for id: String) {
        guard appModel.settings.guardianEnabled,
              let candidate = trajectories.first(where: { $0.id == id }) else { return }
        let arrival = candidate.estimatedArrival.formatted(date: .omitted, time: .shortened)
        stagedMessage = candidate.predictedLateMinutes > 0
            ? "I may be late for \(candidate.title). Current driving directions estimate my arrival around \(arrival)."
            : "Travel time looks tight for \(candidate.title). I may arrive close to the start."
        // A local draft only. No recipient, email account or messaging app is
        // selected; nothing is sent or written to the Windows backend.
    }

    func copyDraft() {
        guard !stagedMessage.isEmpty else { return }
        UIPasteboard.general.string = stagedMessage
        status = "Copied local draft. Nothing was sent."
    }

    @discardableResult
    func startDirections(for id: String, automatically: Bool = false) -> Bool {
        guard appModel.settings.guardianEnabled,
              let candidate = trajectories.first(where: { $0.id == id }),
              let destination = destinationByRisk[id],
              (0...90).contains(Date().timeIntervalSince(candidate.checkedAt)),
              candidate.startsAt > Date(),
              freshLocation() != nil,
              UIApplication.shared.applicationState == .active else {
            status = "No current verified route to hand off. Check again first."
            return false
        }
        if automatically {
            guard appModel.settings.guardianEnabled, hasGrant(for: candidate),
                  !appModel.isCurrentlyNavigating,
                  frontend?.isMeetingActive != true,
                  frontend?.sensors.activity != "Driving" else { return false }
            // Consume BEFORE the side effect; a cancelled/failed handoff does
            // not silently retry or consume a different event grant.
            grants.removeValue(forKey: id)
            persistGrants()
        }
        let didOpen = destination.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving,
            MKLaunchOptionsShowsTrafficKey: true,
        ])
        let result = didOpen
            ? "Apple Maps accepted the directions handoff. Route start and arrival have not been independently verified."
            : "Apple Maps did not accept the directions handoff. No navigation outcome is claimed."
        let receipt = GuardianHandoffReceipt(
            id: UUID(), at: Date(), title: candidate.title,
            source: "iPhone calendar + fresh GPS + Apple MapKit route",
            outcome: result, authorizedAutomatically: automatically
        )
        handoffHistory.append(receipt)
        if handoffHistory.count > 30 { handoffHistory.removeFirst(handoffHistory.count - 30) }
        if let data = try? JSONEncoder().encode(handoffHistory) {
            KeychainStore.saveData(data, account: Self.receiptsKey)
        }
        status = result
        return didOpen
    }

    func clearHistory() {
        handoffHistory = []
        KeychainStore.delete(Self.receiptsKey)
    }

    private func pruneGrantsAndDismissals() {
        let now = Date()
        grants = grants.filter { $0.value.expiresAt > now }
        dismissed = dismissed.filter { $0.value > now }
        persistGrants()
        persistDismissals()
    }

    private func persistGrants() {
        if let data = try? JSONEncoder().encode(grants) {
            KeychainStore.saveData(data, account: Self.grantsKey)
        }
    }

    private func persistDismissals() {
        if let data = try? JSONEncoder().encode(dismissed) {
            KeychainStore.saveData(data, account: Self.dismissedKey)
        }
    }
}

struct CounterfactualGuardianView: View {
    @EnvironmentObject var guardian: CounterfactualGuardianController
    @EnvironmentObject var appModel: JarvisAppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Notice an endangered objective before its deadline. The current first slice compares your next timed calendar destinations with fresh iPhone GPS and live Apple MapKit driving estimates.")
                .font(.callout)
            LabeledContent(
                "Automatic checking",
                value: appModel.settings.guardianEnabled ? "Opted in • foreground only" : "Off"
            )
            .font(.caption)
            Toggle("Guard upcoming calendar departures", isOn: $appModel.settings.guardianEnabled)
            Text("Also enable Motion / travel context and GPS under Settings. This does not monitor other people's calendars or infer a meeting place from its title.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Button(guardian.isChecking ? "Comparing routes…" : "Check next departures now") {
                Task { await guardian.checkNow() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(guardian.isChecking || !appModel.settings.guardianEnabled
                      || !appModel.settings.localSensorContextEnabled)
            Text(guardian.status)
                .font(.footnote)
                .accessibilityIdentifier("guardian-evidence-status")
            ForEach(guardian.trajectories) { trajectory in
                VStack(alignment: .leading, spacing: 7) {
                    Text(trajectory.brief)
                        .font(.callout.weight(.medium))
                    Text(trajectory.evidence)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    HStack {
                        Button("Start directions") {
                            _ = guardian.startDirections(for: trajectory.id)
                        }
                        Button(guardian.hasGrant(for: trajectory)
                               ? "Revoke automatic Maps"
                               : "Allow one automatic Maps launch") {
                            if guardian.hasGrant(for: trajectory) {
                                guardian.revokeNavigation(for: trajectory.id)
                            } else {
                                guardian.authorizeNavigationOnce(for: trajectory.id)
                            }
                        }
                        Button("Dismiss") { guardian.dismiss(trajectory.id) }
                    }
                    .buttonStyle(.bordered)
                    Text("A navigation grant is event-, time- and destination-specific, expires by its start, and is consumed before one attempted handoff. No message is sent.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Button("Prepare local ETA message") { guardian.stageETA(for: trajectory.id) }
                        .buttonStyle(.bordered)
                }
                .padding(10)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
            }
            if !guardian.stagedMessage.isEmpty {
                Text(guardian.stagedMessage)
                    .font(.callout)
                    .textSelection(.enabled)
                Button("Copy draft — do not send") { guardian.copyDraft() }
                    .buttonStyle(.bordered)
            }
            if !guardian.handoffHistory.isEmpty {
                HStack {
                    Text("Navigation handoff receipts")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Button("Clear") { guardian.clearHistory() }
                }
                ForEach(Array(guardian.handoffHistory.suffix(3).reversed())) { entry in
                    VStack(alignment: .leading) {
                        Text(entry.title + (entry.authorizedAutomatically ? " • preauthorized" : " • manually requested"))
                            .font(.caption.weight(.semibold))
                        Text(entry.outcome)
                            .font(.caption)
                        Text(entry.at.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
}
