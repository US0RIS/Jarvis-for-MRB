import CoreLocation
import Foundation
import MapKit
import SwiftUI
import UIKit

/// Actual device/tool capabilities, never invented by model output.
struct MissionAffordance: Identifiable {
    let id: String
    let label: String
    let effect: String
    let authority: String
    let verification: String
}

enum MissionAffordances {
    static let appointment: [MissionAffordance] = [
        MissionAffordance(
            id: "calendar.read", label: "Recheck the exact calendar event",
            effect: "read_only", authority: "Authenticated primary Google Calendar",
            verification: "Exact event ID, start, and literal destination match"
        ),
        MissionAffordance(
            id: "location.read", label: "Observe fresh phone location",
            effect: "read_only", authority: "Separate iPhone Location opt-in",
            verification: "Timestamp, accuracy and two fixes for arrival"
        ),
        MissionAffordance(
            id: "mapkit.route", label: "Compare a current driving route",
            effect: "read_only", authority: "Apple MapKit receives origin and destination",
            verification: "Actual provider response and observation time"
        ),
        MissionAffordance(
            id: "maps.open", label: "Launch Apple Maps",
            effect: "external_handoff", authority: "User tap or one-use exact-mission grant",
            verification: "Maps accepted handoff; travel is NOT thereby verified"
        ),
        MissionAffordance(
            id: "eta.draft", label: "Prepare an ETA draft",
            effect: "local_draft_only", authority: "User tap",
            verification: "Local text only; no recipient or send capability"
        ),
    ]
}

struct MissionEvidence: Identifiable, Codable {
    let id: UUID
    let at: Date
    let source: String
    let kind: String
    let detail: String
    let verified: Bool
}

enum MissionPhase: String, Codable {
    case active
    case reviewRequired
    case achievedOnTime
    case arrivedLate
    case missedUnverified
    case cancelled

    var terminal: Bool {
        [.achievedOnTime, .arrivedLate, .missedUnverified, .cancelled].contains(self)
    }
}

struct JarvisMission: Identifiable, Codable {
    let id: UUID
    let calendarID: String
    let title: String
    let literalDestination: String
    let startsAt: Date
    let createdAt: Date
    let expiresAt: Date
    var phase: MissionPhase
    var status: String
    var observedTravelSeconds: TimeInterval?
    var routeCheckedAt: Date?
    var calendarCheckedAt: Date?
    var lastAlertAt: Date?
    var evidence: [MissionEvidence]

    var eligibleForReview: Bool { phase == .active || phase == .reviewRequired }
    var latestEvidence: MissionEvidence? { evidence.last }
}

/// The first Mission Control runtime is truly local to the phone: Calendar
/// contents and provider route metadata never become a Windows-side GPS trail.
@MainActor
final class JarvisMissionControl: ObservableObject {
    @Published private(set) var missions: [JarvisMission] = []
    @Published private(set) var calendarCandidates: [GuardianCalendarResponse.Event] = []
    @Published private(set) var status = "Mission Control is off. Enable it, then select a timed calendar destination."
    @Published private(set) var isChecking = false
    @Published private(set) var stagedDraft = ""

    private static let storeKey = "jarvis.missions.appointments.v1"
    private unowned let appModel: JarvisAppModel
    private weak var frontend: FrontendIntelligenceController?
    private var loop: Task<Void, Never>?
    private var began = false
    private var lastPoll = Date.distantPast
    private var destinations: [UUID: MKMapItem] = [:]
    private var arrivalFixes: [UUID: (firstAt: Date, firstObservedAt: Date)] = [:]
    // RAM-only. Disappears on restart, on pause and after one attempted handoff.
    private var grants: [UUID: (calendarID: String, start: Date, destination: String, expires: Date)] = [:]

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
        if let data = KeychainStore.readData(Self.storeKey),
           let decoded = try? JSONDecoder().decode([JarvisMission].self, from: data) {
            missions = Array(decoded.suffix(20))
        }
    }

    func attach(frontend: FrontendIntelligenceController) {
        self.frontend = frontend
    }

    func start() {
        guard !began else { return }
        began = true
        loop = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled && self.began {
                if !self.appModel.settings.missionControlEnabled
                    || !self.appModel.settings.guardianEnabled {
                    self.grants.removeAll()
                    self.destinations.removeAll()
                    self.arrivalFixes.removeAll()
                    self.calendarCandidates = []
                    self.stagedDraft = ""
                    self.status = "Mission Control paused. Existing missions are retained locally; no automatic checks or actions."
                } else if UIApplication.shared.applicationState == .active,
                          Date().timeIntervalSince(self.lastPoll) >= 100 {
                    await self.checkNow()
                }
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    func stop() {
        began = false
        loop?.cancel()
        loop = nil
        grants.removeAll()
        destinations.removeAll()
        arrivalFixes.removeAll()
    }

    func clearNavigationGrants() {
        grants.removeAll()
    }

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    private func save() {
        missions = Array(missions.suffix(20))
        if let data = try? JSONEncoder().encode(missions) {
            KeychainStore.saveData(data, account: Self.storeKey)
        }
    }

    private static func parse(_ raw: String) -> Date? {
        guard raw.contains("T") else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let timestamp = formatter.date(from: raw) { return timestamp }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: raw)
    }

    private static func virtual(_ raw: String) -> Bool {
        let location = raw.lowercased()
        return ["https://", "http://", "zoom.us", "meet.google",
                "teams.microsoft", "webex", "phone call", "virtual",
                "video call", "online", "dial-in"].contains(where: location.contains)
    }

    private func accurateLocation() -> CLLocation? {
        guard appModel.settings.localSensorContextEnabled,
              let sensor = frontend?.sensors,
              let coordinate = sensor.coordinate,
              let observed = sensor.lastLocationAt,
              let accuracy = sensor.horizontalAccuracyMeters,
              coordinate.latitude.isFinite, coordinate.longitude.isFinite,
              abs(coordinate.latitude) <= 90, abs(coordinate.longitude) <= 180,
              (0...30).contains(accuracy),
              (0...45).contains(Date().timeIntervalSince(observed)) else { return nil }
        return CLLocation(
            coordinate: coordinate, altitude: 0,
            horizontalAccuracy: accuracy, verticalAccuracy: -1,
            timestamp: observed
        )
    }

    private func resolveDestination(_ raw: String, near origin: CLLocation) async throws -> MKMapItem? {
        guard !Self.virtual(raw) else { return nil }
        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = raw
        request.region = MKCoordinateRegion(
            center: origin.coordinate,
            latitudinalMeters: 160_000, longitudinalMeters: 160_000
        )
        let items = try await MKLocalSearch(request: request).start().mapItems
        if items.count == 1 { return items.first }
        func normalize(_ text: String) -> String {
            text.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .joined(separator: " ")
        }
        let target = normalize(raw)
        let matches = items.filter {
            normalize($0.name ?? "") == target
                || normalize($0.placemark.title ?? "") == target
        }
        return matches.count == 1 ? matches.first : nil
    }

    private func actualRoute(from origin: CLLocation, to destination: MKMapItem) async throws -> MKRoute? {
        let request = MKDirections.Request()
        request.source = MKMapItem(placemark: MKPlacemark(coordinate: origin.coordinate))
        request.destination = destination
        request.transportType = .automobile
        request.requestsAlternateRoutes = true
        let routes = try await MKDirections(request: request).calculate().routes
        return routes.filter { $0.expectedTravelTime.isFinite && $0.expectedTravelTime > 0 }
            .min { $0.expectedTravelTime < $1.expectedTravelTime }
    }

    private func append(_ evidence: MissionEvidence, to mission: inout JarvisMission) {
        mission.evidence.append(evidence)
        if mission.evidence.count > 24 { mission.evidence.removeFirst(mission.evidence.count - 24) }
    }

    private func evidence(_ source: String, _ kind: String, _ detail: String,
                          verified: Bool = false, at: Date = Date()) -> MissionEvidence {
        MissionEvidence(
            id: UUID(), at: at, source: source, kind: kind,
            detail: String(detail.prefix(400)), verified: verified
        )
    }

    /// Read-only candidate retrieval; no mission is silently enrolled.
    func loadCandidates() async {
        guard appModel.settings.missionControlEnabled, appModel.settings.guardianEnabled else {
            status = "Enable Mission Control and Guardian before reading your calendar."
            return
        }
        do {
            let response = try await client.guardianCalendarExpectations()
            guard let checked = Self.parse(response.checkedAt),
                  abs(Date().timeIntervalSince(checked)) <= 120 else {
                status = "Calendar response timestamp unavailable or stale."
                return
            }
            let now = Date()
            calendarCandidates = response.events.filter {
                !$0.id.isEmpty && !Self.virtual($0.location)
                    && Self.parse($0.start).map {
                        (300...86400).contains($0.timeIntervalSince(now))
                    } == true
            }.sorted {
                (Self.parse($0.start) ?? .distantFuture)
                    < (Self.parse($1.start) ?? .distantFuture)
            }
            status = calendarCandidates.isEmpty
                ? "No precise physical appointment found in the bounded next-day calendar response."
                : "Select an exact appointment. Nothing has been enrolled automatically."
        } catch {
            calendarCandidates = []
            status = "Calendar unavailable; no mission has been created."
        }
    }

    func enroll(_ event: GuardianCalendarResponse.Event) async -> String {
        guard appModel.settings.missionControlEnabled, appModel.settings.guardianEnabled else {
            return "Mission Control and Guardian must be enabled."
        }
        guard calendarCandidates.contains(where: {
            $0.id == event.id && $0.start == event.start
                && $0.location == event.location
        }), let start = Self.parse(event.start),
              (300...86400).contains(start.timeIntervalSinceNow),
              !Self.virtual(event.location), !event.location.isEmpty else {
            return "Appointment source is no longer eligible. Reload the calendar."
        }
        guard missions.filter({ $0.eligibleForReview }).count < 5 else {
            return "Maximum of five active appointment missions. Cancel or finish one first."
        }
        if let existing = missions.first(where: {
            $0.calendarID == event.id && $0.startsAt == start
                && $0.literalDestination == event.location && $0.eligibleForReview
        }) {
            return "Already guarding this appointment: " + existing.title
        }
        let instant = Date()
        var mission = JarvisMission(
            id: UUID(), calendarID: event.id,
            title: String(event.summary.prefix(160)),
            literalDestination: String(event.location.prefix(300)),
            startsAt: start, createdAt: instant,
            expiresAt: start.addingTimeInterval(1800),
            phase: .active,
            status: "Objective enrolled; route and arrival have not yet been verified.",
            observedTravelSeconds: nil,
            routeCheckedAt: nil, calendarCheckedAt: nil, lastAlertAt: nil,
            evidence: []
        )
        append(evidence("User enrollment", "mission_created",
                        "Guard arrival by the exact calendar start at the literal destination.",
                        verified: true), to: &mission)
        missions.append(mission)
        save()
        await checkNow()
        return "Mission created: " + event.summary
    }

    func enrollNextAppointment() async -> String {
        await loadCandidates()
        guard let first = calendarCandidates.first,
              let start = Self.parse(first.start) else { return status }
        if calendarCandidates.dropFirst().contains(where: {
            Self.parse($0.start) == start
        }) {
            return "More than one event starts at the same time. Select the exact one in Physical → Mission Control."
        }
        return await enroll(first)
    }

    /// Evidence-driven convergence: revalidate exact source, route and arrival.
    /// Device-only receipts distinguish a route *estimate* from verified arrival.
    func checkNow() async {
        guard !isChecking, appModel.settings.missionControlEnabled,
              appModel.settings.guardianEnabled,
              UIApplication.shared.applicationState == .active else { return }
        isChecking = true
        lastPoll = Date()
        defer { isChecking = false }
        let live: GuardianCalendarResponse
        do {
            live = try await client.guardianCalendarExpectations()
        } catch {
            status = "Source unknown: Calendar is unavailable. No mission outcome asserted."
            return
        }
        guard let calendarTime = Self.parse(live.checkedAt),
              abs(Date().timeIntervalSince(calendarTime)) < 120 else {
            status = "Source unknown: Calendar timestamp is stale."
            return
        }
        guard appModel.settings.missionControlEnabled, appModel.settings.guardianEnabled,
              UIApplication.shared.applicationState == .active else { return }

        var updated = missions
        var destinationUpdates: [UUID: MKMapItem] = [:]
        var newAlert: String?
        var activeCount = 0
        for index in updated.indices {
            if Task.isCancelled { return }
            var mission = updated[index]
            guard mission.eligibleForReview else { continue }
            if Date() > mission.expiresAt {
                mission.phase = .missedUnverified
                mission.status = "Observation window expired without verified arrival; actual outcome unknown."
                append(evidence("Mission clock", "unverified",
                                "Deadline and 30-minute observation window passed. No arrival evidence.",
                                verified: false), to: &mission)
                updated[index] = mission
                continue
            }
            activeCount += 1
            if activeCount > 5 { break }
            let exact = live.events.first {
                $0.id == mission.calendarID
            }
            if let exact, Self.parse(exact.start) != mission.startsAt
                || exact?.location != nil && exact?.location != mission.literalDestination {
                mission.phase = .reviewRequired
                mission.status = "Calendar time or location changed. No automatic actions until the mission is replaced."
                append(evidence("Primary Google Calendar", "source_changed",
                                "Exact enrolled destination or start no longer matches the live event.",
                                verified: true), to: &mission)
                updated[index] = mission
                grants.removeValue(forKey: mission.id)
                continue
            }
            guard exact != nil else {
                mission.status = "Unknown: this event is missing from the bounded Calendar response, not proof it was cancelled."
                updated[index] = mission
                continue
            }
            mission.calendarCheckedAt = calendarTime
            guard mission.phase == .active else {
                updated[index] = mission
                continue
            }
            guard let phone = accurateLocation() else {
                mission.status = "Unknown: no fresh high-accuracy phone fix; no arrival claim."
                updated[index] = mission
                continue
            }
            do {
                guard let destination = try await resolveDestination(
                    mission.literalDestination, near: phone
                ) else {
                    mission.status = "Unknown: destination ambiguous or unavailable in MapKit."
                    updated[index] = mission
                    continue
                }
                let target = CLLocation(
                    latitude: destination.placemark.coordinate.latitude,
                    longitude: destination.placemark.coordinate.longitude
                )
                let distance = phone.distance(from: target)
                let now = Date()
                let fixAge = now.timeIntervalSince(phone.timestamp)
                guard (0...45).contains(fixAge) else {
                    mission.status = "Unknown: GPS fix expired during route calculation."
                    updated[index] = mission
                    continue
                }
                destinationUpdates[mission.id] = destination
                if distance <= max(45, phone.horizontalAccuracy * 1.3) {
                    if let first = arrivalFixes[mission.id],
                       phone.timestamp.timeIntervalSince(first.firstObservedAt) >= 8,
                       now.timeIntervalSince(first.firstAt) <= 180 {
                        mission.phase = phone.timestamp <= mission.startsAt
                            ? .achievedOnTime : .arrivedLate
                        mission.status = mission.phase == .achievedOnTime
                            ? "Arrival observed on time by two distinct accurate GPS fixes."
                            : "Arrival observed after the scheduled start by two distinct accurate GPS fixes."
                        append(evidence(
                            "iPhone Core Location", "arrival_observed",
                            "Two distinct accurate phone fixes near uniquely resolved destination, at least eight seconds apart. Not physical attendance proof.",
                            verified: true, at: phone.timestamp
                        ), to: &mission)
                        grants.removeValue(forKey: mission.id)
                        updated[index] = mission
                        continue
                    }
                    arrivalFixes[mission.id] = (
                        firstAt: now, firstObservedAt: phone.timestamp
                    )
                    mission.status = "Near destination. Awaiting a second independent GPS fix before recording arrival."
                    updated[index] = mission
                    continue
                }
                arrivalFixes.removeValue(forKey: mission.id)
                if Date() > mission.startsAt {
                    mission.status = "Past scheduled start; fresh GPS remains away from destination. No arrival asserted."
                    updated[index] = mission
                    continue
                }
                guard let route = try await actualRoute(from: phone, to: destination),
                      appModel.settings.missionControlEnabled,
                      UIApplication.shared.applicationState == .active else {
                    mission.status = "Unknown: no current provider driving route."
                    updated[index] = mission
                    continue
                }
                mission.observedTravelSeconds = route.expectedTravelTime
                mission.routeCheckedAt = now
                let remaining = mission.startsAt.timeIntervalSince(now)
                let margin = remaining - route.expectedTravelTime - 300
                let drive = Int(ceil(route.expectedTravelTime / 60))
                let minutes = Int(ceil(remaining / 60))
                let risk = margin <= 0
                mission.status = risk
                    ? "At risk: \(minutes) min until start; MapKit drive \(drive) min plus five-minute buffer."
                    : "Route presently feasible: \(minutes) min until start; MapKit drive \(drive) min plus five-minute buffer. Arrival NOT verified."
                append(evidence("Apple MapKit + iPhone GPS + primary Google Calendar",
                                risk ? "trajectory_at_risk" : "trajectory_feasible",
                                mission.status, verified: false), to: &mission)
                if risk, mission.lastAlertAt.map({
                    now.timeIntervalSince($0) > 1800
                }) ?? true {
                    mission.lastAlertAt = now
                    newAlert = "Mission \(mission.title): \(mission.status)"
                }
                updated[index] = mission
            } catch {
                mission.status = "Unknown: MapKit place or route provider unavailable."
                updated[index] = mission
            }
        }
        guard appModel.settings.missionControlEnabled,
              UIApplication.shared.applicationState == .active else { return }
        missions = updated
        destinations.merge(destinationUpdates) { _, recent in recent }
        save()
        status = "Checked \(activeCount) enrolled mission(s) against real Calendar and phone observations. Evidence is shown per mission."
        if let newAlert {
            appModel.memoMind.presentProactiveAlert(newAlert, severity: "warning")
            if appModel.settings.proactiveAnnouncements,
               !appModel.isSending, !appModel.isListening,
               !appModel.speechSynthesizer.isSpeaking,
               frontend?.isMeetingActive != true,
               frontend?.sensors.activity != "Driving" {
                await appModel.speakFrontendResponseIfEnabled(newAlert)
            }
        }
    }

    func canAutoNavigate(_ id: UUID) -> Bool {
        guard appModel.settings.missionControlEnabled,
              let mission = missions.first(where: { $0.id == id && $0.phase == .active }),
              let grant = grants[id] else { return false }
        return grant.calendarID == mission.calendarID
            && grant.start == mission.startsAt
            && grant.destination == mission.literalDestination
            && grant.expires > Date()
    }

    func authorizeOneMapsLaunch(_ id: UUID) {
        guard appModel.settings.missionControlEnabled,
              appModel.settings.guardianEnabled,
              let mission = missions.first(where: { $0.id == id && $0.phase == .active }),
              mission.startsAt > Date(),
              mission.calendarCheckedAt.map({ Date().timeIntervalSince($0) < 120 }) == true,
              destinations[id] != nil else { return }
        grants[id] = (
            mission.calendarID, mission.startsAt, mission.literalDestination,
            min(mission.startsAt, Date().addingTimeInterval(3600))
        )
        status = "One-use Maps permission bound to this exact mission, start and destination; expires at the appointment. Revoke anytime."
    }

    func revokeMaps(_ id: UUID) {
        grants.removeValue(forKey: id)
        status = "Mission's one-use Maps permission revoked."
    }

    @discardableResult
    func openDirections(_ id: UUID, automatically: Bool = false) -> Bool {
        guard appModel.settings.missionControlEnabled,
              appModel.settings.guardianEnabled,
              UIApplication.shared.applicationState == .active,
              let index = missions.firstIndex(where: { $0.id == id && $0.phase == .active }),
              missions[index].startsAt > Date(),
              missions[index].calendarCheckedAt.map({
                  (0...120).contains(Date().timeIntervalSince($0))
              }) == true,
              missions[index].routeCheckedAt.map({
                  (0...90).contains(Date().timeIntervalSince($0))
              }) == true,
              accurateLocation() != nil,
              let destination = destinations[id] else {
            status = "No verified fresh route to launch. Check the mission first."
            return false
        }
        if automatically {
            guard canAutoNavigate(id),
                  !appModel.isCurrentlyNavigating,
                  frontend?.isMeetingActive != true,
                  frontend?.sensors.activity != "Driving",
                  !appModel.isSending else { return false }
            // Consume before any side effect, including failed Maps handoff.
            grants.removeValue(forKey: id)
        }
        let accepted = destination.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving,
            MKLaunchOptionsShowsTrafficKey: true,
        ])
        var mission = missions[index]
        append(evidence("Apple Maps", "navigation_handoff",
                        accepted
                            ? "Apple Maps accepted the requested driving-directions handoff. Travel/arrival NOT verified."
                            : "Apple Maps did not accept the directions handoff. No execution success claimed.",
                        verified: accepted), to: &mission)
        missions[index] = mission
        save()
        status = mission.latestEvidence?.detail ?? "Navigation handoff result unavailable."
        return accepted
    }

    func stageETA(_ id: UUID) {
        guard appModel.settings.missionControlEnabled,
              let mission = missions.first(where: { $0.id == id && $0.phase == .active }),
              let seconds = mission.observedTravelSeconds,
              mission.routeCheckedAt.map({
                  Date().timeIntervalSince($0) <= 120
              }) == true else { return }
        let arrival = Date().addingTimeInterval(seconds)
            .formatted(date: .omitted, time: .shortened)
        stagedDraft = "I may arrive near \(arrival) for \(mission.title). My current route estimate may change."
        status = "Local text prepared. No recipient, account or send action selected."
    }

    func copyDraft() {
        guard !stagedDraft.isEmpty else { return }
        UIPasteboard.general.string = stagedDraft
        status = "Local draft copied. Nothing sent."
    }

    func cancel(_ id: UUID) {
        guard let index = missions.firstIndex(where: { $0.id == id }),
              !missions[index].phase.terminal else { return }
        grants.removeValue(forKey: id)
        destinations.removeValue(forKey: id)
        arrivalFixes.removeValue(forKey: id)
        missions[index].phase = .cancelled
        missions[index].status = "Cancelled by you. No further mission actions."
        append(evidence("User", "mission_cancelled",
                        "Explicit cancellation; no action inferred.",
                        verified: true), to: &missions[index])
        save()
    }

    func discardHistory() {
        // Retain active missions; erase only finished, locally stored receipts.
        missions.removeAll { $0.phase.terminal }
        save()
    }

    var spokenStatus: String {
        guard appModel.settings.missionControlEnabled else {
            return "Mission Control is off. Enable it in Physical to create a mission."
        }
        let active = missions.filter { $0.phase == .active }
        guard let first = active.sorted(by: { $0.startsAt < $1.startsAt }).first else {
            return "No active appointment mission. Select one in Physical → Mission Control."
        }
        return "\(active.count) active mission(s). \(first.title): \(first.status)"
    }
}

struct JarvisMissionBoard: View {
    @EnvironmentObject var appModel: JarvisAppModel
    @EnvironmentObject var missions: JarvisMissionControl

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("JARVIS • Mission Control")
                .font(.headline)
            Text("Give Jarvis a specific outcome and he maintains a live, evidence-backed mission. This first execution pack guards arriving at one exact calendar appointment: Calendar + fresh GPS + real MapKit routing, with one-use directions and local-only ETA drafts.")
                .font(.caption)
            Toggle(
                "Enable foreground Mission Control",
                isOn: Binding(
                    get: { appModel.settings.missionControlEnabled },
                    set: { value in
                        appModel.settings.missionControlEnabled = value
                        if !value { missions.clearNavigationGrants() }
                    }
                )
            )
            Text("Requires separately enabled Guardian and high-accuracy Motion / travel context. Apple MapKit receives origin and destination; the Jarvis PC does not receive or store Mission Control GPS fixes. Not an always-on background location service.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(missions.status)
                .font(.footnote)
                .accessibilityIdentifier("mission-control-status")
            HStack {
                Button("Find appointment missions") {
                    Task { await missions.loadCandidates() }
                }
                Button(missions.isChecking ? "Checking…" : "Check missions now") {
                    Task { await missions.checkNow() }
                }
                .disabled(missions.isChecking)
            }
            .buttonStyle(.bordered)
            .disabled(!appModel.settings.missionControlEnabled
                      || !appModel.settings.guardianEnabled)
            ForEach(missions.calendarCandidates) { event in
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.summary)
                        .font(.subheadline.weight(.medium))
                    Text(event.start + " • " + event.location)
                        .font(.caption)
                    Button("Guard arrival for this exact appointment") {
                        Task { _ = await missions.enroll(event) }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding(8)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
            }
            ForEach(missions.missions.filter { $0.eligibleForReview }) { mission in
                VStack(alignment: .leading, spacing: 7) {
                    Text(mission.title)
                        .font(.subheadline.weight(.semibold))
                    Text("Outcome: arrive by "
                         + mission.startsAt.formatted(date: .abbreviated, time: .shortened)
                         + " at " + mission.literalDestination)
                        .font(.caption)
                    Text(mission.status)
                        .font(.callout)
                        .accessibilityIdentifier("mission-evidence")
                    ForEach(Array(mission.evidence.suffix(3).reversed())) { row in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.kind + " • " + row.source)
                                .font(.caption.weight(.medium))
                            Text(row.detail)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text(row.at.formatted(date: .omitted, time: .shortened))
                                .font(.caption2)
                        }
                    }
                    if mission.phase == .active {
                        Button("Start verified directions") {
                            _ = missions.openDirections(mission.id)
                        }
                        Button(missions.canAutoNavigate(mission.id)
                               ? "Revoke one-use Maps grant"
                               : "Allow one automatic Maps launch") {
                            if missions.canAutoNavigate(mission.id) {
                                missions.revokeMaps(mission.id)
                            } else {
                                missions.authorizeOneMapsLaunch(mission.id)
                            }
                        }
                        Button("Prepare local ETA message") {
                            missions.stageETA(mission.id)
                        }
                        .buttonStyle(.bordered)
                    }
                    Button("Cancel this mission", role: .destructive) {
                        missions.cancel(mission.id)
                    }
                    .font(.caption)
                }
                .buttonStyle(.bordered)
                .padding(10)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
            }
            if !missions.stagedDraft.isEmpty {
                Text(missions.stagedDraft)
                    .font(.callout)
                    .textSelection(.enabled)
                Button("Copy local draft — do not send") {
                    missions.copyDraft()
                }
                .buttonStyle(.bordered)
            }
            if !missions.missions.filter({ $0.phase.terminal }).isEmpty {
                Text("Finished and unverified missions")
                    .font(.subheadline.weight(.semibold))
                ForEach(missions.missions.filter { $0.phase.terminal }) { mission in
                    Text(mission.title + " • " + mission.status)
                        .font(.caption)
                }
                Button("Clear finished mission history") {
                    missions.discardHistory()
                }
                .buttonStyle(.bordered)
            }
            DisclosureGroup("Actual capabilities and authority") {
                ForEach(MissionAffordances.appointment) { affordance in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(affordance.label)
                            .font(.subheadline.weight(.medium))
                        Text(affordance.effect + " • " + affordance.authority)
                            .font(.caption)
                        Text("Proof: " + affordance.verification)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 5)
                }
            }
        }
    }
}
