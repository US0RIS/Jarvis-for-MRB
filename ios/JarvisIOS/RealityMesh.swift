import Foundation
import MapKit
import SwiftUI
import UIKit

struct MeshPlaceChoice: Identifiable {
    let id: UUID
    let name: String
    let address: String
}

/// User's iPad/iPhone becomes a view into explicit, connected Jarvis nodes.
@MainActor
final class RealityMeshController: ObservableObject {
    @Published var placeName = ""
    @Published private(set) var nodes: [RealityMeshNodesResponse.Node] = []
    @Published private(set) var sources: [RealityMeshSourceRegistry.Source] = []
    @Published private(set) var place: PhysicalAwarenessResponse?
    @Published private(set) var placeGraph: RealityGraphPlaceResponse?
    @Published private(set) var placeGraphStatus = "No Reality Graph snapshot for this place."
    @Published private(set) var isCheckingPlaceGraph = false
    @Published private(set) var lensReport: RealityLensReport?
    @Published private(set) var lensMemories: [RealityLensMemories.Memory] = []
    @Published private(set) var lensStatus = "Resolve one place to use the Reality Lens."
    @Published private(set) var lensBusy = false
    @Published private(set) var lensMemoryStatus = "Stored only when you explicitly tap Remember."
    @Published private(set) var worldStatus = "Name an exact place, then make a one-time public-world observation."
    @Published private(set) var placeCandidates: [MeshPlaceChoice] = []
    @Published private(set) var nodeStatus = "Check explicit devices; Jarvis never scans a network."
    @Published private(set) var isCheckingWorld = false
    @Published private(set) var isCheckingNodes = false
    @Published private(set) var activeNodeID: String?
    @Published private(set) var screenStatus = "No desktop viewing session."
    @Published private(set) var appActionStatus = "No remote app action requested."
    @Published private(set) var appActionBusy = false
    @Published private(set) var screenData: Data?
    @Published private(set) var screenExpiresAt: Date?
    @Published private(set) var publicWatches: [ExternalWatchSummary] = []
    @Published private(set) var watchStatus = "No place watch enrolled from this screen."
    @Published var conductorNodeID = "windows"
    @Published private(set) var conductorSelectedApps: [String] = []
    @Published var conductorShowScreen = false
    @Published private(set) var conductorMission: ConductorWorkstationMission?
    @Published private(set) var conductorStatus = "Select one device and up to three exact apps. Speech only requests preparation, not authority."
    @Published private(set) var conductorBusy = false
    @Published private(set) var conductorRecent: [ConductorWorkstationMission] = []
    var conductorHasOneUseGrant: Bool { conductorOneUseGrant != nil }
    private var conductorOneUseGrant: String?
    private var conductorLastPreparedID: String?

    // RAM-only until the user explicitly enrolls a three-hour external watch.
    private var placeCoordinate: CLLocationCoordinate2D?
    private var resolvedPlaceName = ""
    private var candidateItems: [UUID: MKMapItem] = [:]
    private var pendingQuery = ""
    private var isWatching = false

    private unowned let appModel: JarvisAppModel
    private var screenLoop: Task<Void, Never>?

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
    }

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    func refreshFabric() async {
        guard appModel.settings.meshEnabled, !isCheckingNodes,
              UIApplication.shared.applicationState == .active else { return }
        isCheckingNodes = true
        defer { isCheckingNodes = false }
        do {
            async let connected = client.realityMeshNodes()
            async let registry = client.realityMeshSources()
            let fetchedNodes = try await connected
            let fetchedSources = try await registry
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active else { return }
            nodes = fetchedNodes.nodes
            sources = fetchedSources.sources
            let live = nodes.filter { $0.status == "online" }.count
            nodeStatus = "\(live) directly observed online node(s). Mac nodes require explicit setup; capability does not mean authorization to control."
        } catch {
            nodes = []
            nodeStatus = "Mesh fabric unavailable. No remote machine status assumed."
        }
    }

    private static func exact(_ text: String) -> String {
        text.lowercased()
            .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .joined(separator: " ")
    }

    func establishWorldPresence() async {
        guard appModel.settings.meshEnabled, !isCheckingWorld,
              UIApplication.shared.applicationState == .active else { return }
        let query = placeName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (3...120).contains(query.count) else {
            worldStatus = "Give a specific place name (3–120 characters)."
            return
        }
        isCheckingWorld = true
        defer { isCheckingWorld = false }
        place = nil
        placeGraph = nil
        placeGraphStatus = "No Reality Graph snapshot for this place."
        lensReport = nil
        lensStatus = "New place; prior reality observations cleared from this view."
        placeCoordinate = nil
        resolvedPlaceName = ""
        placeCandidates = []
        candidateItems = [:]
        pendingQuery = query
        worldStatus = "Resolving the named place with Apple MapKit…"
        do {
            let request = MKLocalSearch.Request()
            request.naturalLanguageQuery = query
            let matches = try await MKLocalSearch(request: request).start().mapItems
            let exact = matches.filter {
                Self.exact($0.name ?? "") == Self.exact(query)
                    || Self.exact($0.placemark.title ?? "") == Self.exact(query)
            }
            let chosen: MKMapItem?
            if exact.count == 1 {
                chosen = exact.first
            } else if matches.count == 1 {
                chosen = matches.first
            } else {
                chosen = nil
            }
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active,
                  pendingQuery == query,
                  placeName.trimmingCharacters(in: .whitespacesAndNewlines) == query
            else { return }
            guard let item = chosen else {
                var locations = Set<String>()
                for result in matches.prefix(12) {
                    let coordinate = result.placemark.coordinate
                    let key = String(format: "%.4f,%.4f",
                                     coordinate.latitude, coordinate.longitude)
                    if locations.insert(key).inserted {
                        let id = UUID()
                        let choice = MeshPlaceChoice(
                            id: id,
                            name: result.name ?? "Unnamed public map result",
                            address: result.placemark.title ?? "No address provided"
                        )
                        placeCandidates.append(choice)
                        candidateItems[id] = result
                    }
                    if placeCandidates.count >= 6 { break }
                }
                worldStatus = placeCandidates.isEmpty
                    ? "No location resolved; no public source lookup performed."
                    : "Multiple map results. Choose the exact place below before sharing a coordinate with Jarvis."
                return
            }
            await observeResolvedPlace(item, query: query)
        } catch {
            worldStatus = "Place lookup/provider unavailable. No observations asserted."
        }
    }

    func selectPlace(_ id: UUID) async {
        guard appModel.settings.meshEnabled, !isCheckingWorld,
              UIApplication.shared.applicationState == .active,
              let item = candidateItems[id],
              !pendingQuery.isEmpty,
              placeName.trimmingCharacters(in: .whitespacesAndNewlines) == pendingQuery else {
            worldStatus = "Place selection expired or query changed. Search again."
            return
        }
        isCheckingWorld = true
        defer { isCheckingWorld = false }
        let query = pendingQuery
        placeCandidates = []
        candidateItems = [:]
        await observeResolvedPlace(item, query: query)
    }

    private func observeResolvedPlace(_ item: MKMapItem, query: String) async {
        let coordinate = item.placemark.coordinate
        worldStatus = "Checking the sources actually integrated for \(item.name ?? query)…"
        do {
            let report = try await client.realityMeshPlace(
                latitude: coordinate.latitude, longitude: coordinate.longitude
            )
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active,
                  placeName.trimmingCharacters(in: .whitespacesAndNewlines) == query
            else { return }
            place = report.data
            placeCoordinate = coordinate
            resolvedPlaceName = String((item.name ?? query).prefix(100))
            worldStatus = (item.name ?? query)
                + " • " + report.checkedAt
                + ". Unsupported or stale sources remain unknown, not a safety clearance."
        } catch {
            worldStatus = "Public provider lookup unavailable. No observations asserted."
        }
    }

    func refreshPlaceGraph() async {
        guard appModel.settings.meshEnabled, !isCheckingPlaceGraph,
              UIApplication.shared.applicationState == .active,
              place != nil, let coordinate = placeCoordinate else {
            placeGraphStatus = "Select one exact observed place first; no graph lookup performed."
            return
        }
        let selectedName = resolvedPlaceName
        isCheckingPlaceGraph = true
        placeGraphStatus = "Compiling current provider evidence without Qwen…"
        defer { isCheckingPlaceGraph = false }
        do {
            let graph = try await client.realityGraphPlace(
                latitude: coordinate.latitude, longitude: coordinate.longitude
            )
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active,
                  let current = placeCoordinate,
                  current.latitude == coordinate.latitude,
                  current.longitude == coordinate.longitude,
                  selectedName == resolvedPlaceName else { return }
            placeGraph = graph
            let fresh = Set(graph.evidence.filter { $0.freshness == "fresh" }.map(\.id))
            let supported = graph.derivedFacts.filter {
                !$0.evidenceIDs.isEmpty && $0.evidenceIDs.allSatisfy { fresh.contains($0) }
            }.count
            placeGraphStatus = "\(supported) fresh evidence-backed fact(s); "
                + "\(graph.modelCalls) model calls. Snapshot "
                + graph.generatedAt + ". Unavailable sources remain unknown."
        } catch {
            placeGraph = nil
            placeGraphStatus = "Graph lookup unavailable. No current facts inferred."
        }
    }

    /// The user directs one fresh public-world observation at an exact MapKit
    /// place. A separate Remember tap persists only small numeric source facts.
    func senseSelectedPlace(remember: Bool) async {
        guard !lensBusy, appModel.settings.meshEnabled,
              UIApplication.shared.applicationState == .active,
              place != nil, let coordinate = placeCoordinate,
              !resolvedPlaceName.isEmpty else {
            lensStatus = "Choose a uniquely resolved, observed place first."
            return
        }
        let selectedName = resolvedPlaceName
        lensBusy = true
        lensStatus = remember
            ? "Observing and explicitly saving a 30-day source-qualified baseline…"
            : "Sensing fresh sources and comparing to your last saved baseline…"
        defer { lensBusy = false }
        do {
            let received = try await client.realityLensSense(
                latitude: coordinate.latitude, longitude: coordinate.longitude,
                label: selectedName, remember: remember
            )
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active,
                  let current = placeCoordinate,
                  current.latitude == coordinate.latitude,
                  current.longitude == coordinate.longitude,
                  resolvedPlaceName == selectedName else { return }
            lensReport = received
            let baselineText = received.baselineAvailable
                ? "Comparison baseline: " + (received.baselineAt ?? "unknown") + ". "
                : "No previously saved baseline for this exact place. "
            lensStatus = baselineText
                + "\(received.observations.count) fresh scalar observations, "
                + "\(received.changes.count) supported changes. "
                + (received.remembered
                   ? "New memory saved for up to \(received.retentionDays) days."
                   : "This observation was NOT saved.")
            if remember { await refreshLensMemories() }
            // An intentional foreground Sense tap can encode a verified
            // provider-value change as a tactile cue. No background alerts.
            if !remember, received.suggestedHapticPulses > 0 {
                for n in 0..<min(received.suggestedHapticPulses, 3) {
                    guard appModel.settings.meshEnabled,
                          UIApplication.shared.applicationState == .active,
                          resolvedPlaceName == selectedName else { break }
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    if n < received.suggestedHapticPulses - 1 {
                        try? await Task.sleep(for: .milliseconds(180))
                    }
                }
            }
        } catch {
            lensReport = nil
            lensStatus = remember
                ? "Memory write could not be confirmed. Check saved memories before retrying."
                : "Reality sensing unavailable. No change or all-clear is inferred."
        }
    }

    func refreshLensMemories() async {
        guard appModel.settings.meshEnabled,
              UIApplication.shared.applicationState == .active else { return }
        do {
            let report = try await client.realityLensMemories()
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active else { return }
            lensMemories = report.memories
            lensMemoryStatus = "\(report.memories.count) recent manually saved snapshot(s). "
                + "Only labels and source-backed numeric facts persist; "
                + "excluded from results and pruned on access after \(report.retentionDays) days."
        } catch {
            lensMemories = []
            lensMemoryStatus = "Could not read saved lens memories; status unknown."
        }
    }

    func forgetSelectedLensPlace() async {
        guard !lensBusy, appModel.settings.meshEnabled,
              UIApplication.shared.applicationState == .active,
              let coordinate = placeCoordinate else { return }
        lensBusy = true
        defer { lensBusy = false }
        do {
            let result = try await client.realityLensForget(
                latitude: coordinate.latitude, longitude: coordinate.longitude
            )
            lensReport = nil
            lensStatus = "Confirmed deletion of \(result.deleted) snapshot(s) "
                + "for the selected exact place. Other places are unchanged."
            await refreshLensMemories()
        } catch {
            lensStatus = "Could not verify memory deletion. Inspect the memory list."
        }
    }

    func refreshPublicWatches() async {
        guard appModel.settings.meshEnabled else { return }
        do {
            let fetched = try await client.getExternalWatches()
            guard appModel.settings.meshEnabled else { return }
            publicWatches = fetched.filter {
                ["airspace_region", "usgs_earthquakes"].contains($0.kind)
                    && $0.label.hasPrefix("Mesh: ")
                    && $0.enabled
            }
            watchStatus = "\(publicWatches.count) time-bounded user-enrolled public watches. They are not live proof of events."
        } catch {
            watchStatus = "Could not verify existing public watches. Unknown, not empty."
        }
    }

    func watchSelectedPlace(kind: String) async {
        guard !isWatching, appModel.settings.meshEnabled,
              UIApplication.shared.applicationState == .active,
              let coordinate = placeCoordinate,
              ["airspace_region", "usgs_earthquakes"].contains(kind) else {
            watchStatus = "Resolve one unambiguous place and explicitly choose a supported watch."
            return
        }
        isWatching = true
        defer { isWatching = false }
        let flight = kind == "airspace_region"
        let label = "Mesh: " + resolvedPlaceName
            + (flight ? " aircraft" : " reported earthquakes")
        let configuration: [String: Any] = [
            "latitude": coordinate.latitude,
            "longitude": coordinate.longitude,
            "radius_km": flight ? 20.0 : 100.0,
        ]
        do {
            let result = try await client.createExternalWatch(
                kind: kind, label: label,
                config: configuration, seconds: flight ? 1800 : 900,
                expiresHours: 3
            )
            watchStatus = "Created three-hour " + kind
                + " watch: " + result.id
                + ". This stores the selected location in Jarvis's bounded external-watch ledger."
            await refreshPublicWatches()
        } catch {
            watchStatus = "Watch creation failed. No recurring watch assumed."
        }
    }

    func stopPublicWatch(_ id: String) async {
        guard appModel.settings.meshEnabled,
              publicWatches.contains(where: { $0.id == id }) else { return }
        do {
            _ = try await client.stopExternalWatch(id)
            watchStatus = "Public watch stopped and confirmed by Jarvis."
            await refreshPublicWatches()
        } catch {
            watchStatus = "Could not confirm watch revocation; check the watch list before relying on it."
        }
    }

    func openExactMacApp(nodeID: String, appName: String) async {
        // Only an explicit named-button action; no Qwen, goal, watch or
        // voice path delegates automatically to a remote Mac app.
        guard !appActionBusy, appModel.settings.meshEnabled,
              UIApplication.shared.applicationState == .active,
              ((["macbook", "macmini"].contains(nodeID)
                  && ["Safari", "Notes", "Calendar", "Preview", "Finder"].contains(appName))
               || (nodeID == "windows"
                   && ["Notepad", "Calculator", "File Explorer", "Paint"].contains(appName))),
              nodes.contains(where: {
                  $0.id == nodeID && $0.status == "online"
                      && $0.capabilities["app_launch"] == "exact_user_tap_only"
              }) else {
            appActionStatus = "Device not online or separately authorized for exact app launch."
            return
        }
        appActionBusy = true
        defer { appActionBusy = false }
        appActionStatus = "Requesting one exact " + appName + " launch on " + nodeID + "…"
        do {
            let result = try await client.realityMeshOpenMacApp(
                nodeID: nodeID, appName: appName
            )
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active else { return }
            appActionStatus = result.processObserved
                ? nodeID + " accepted launch of " + appName
                    + "; process is observed running. Foreground focus/window not verified."
                : nodeID + " accepted launch of " + appName
                    + "; process not independently observed. Foreground focus/window unknown."
        } catch {
            appActionStatus = "Cannot confirm the exact host app launch; do not assume it failed or retry automatically."
        }
    }

    static func conductorApps(for nodeID: String) -> [String] {
        nodeID == "windows"
            ? ["Notepad", "Calculator", "File Explorer", "Paint"]
            : ["Safari", "Notes", "Calendar", "Preview", "Finder"]
    }

    func selectConductorNode(_ nodeID: String) {
        guard !conductorBusy, conductorMission == nil,
              ["windows", "macbook", "macmini"].contains(nodeID) else { return }
        conductorNodeID = nodeID
        conductorSelectedApps = []
        conductorShowScreen = false
    }

    func toggleConductorApp(_ app: String) {
        guard !conductorBusy, conductorMission == nil,
              Self.conductorApps(for: conductorNodeID).contains(app) else { return }
        if let at = conductorSelectedApps.firstIndex(of: app) {
            conductorSelectedApps.remove(at: at)
        } else if conductorSelectedApps.count < 3 {
            conductorSelectedApps.append(app)
        }
    }

    func requestWorkstationPreparation() -> String {
        guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled else {
            return "Enable both Reality Mesh and Conductor in Settings, then open the Mesh tab."
        }
        return "Conductor is ready on the Mesh tab. Choose your exact computer and up to "
            + "three apps, then review and explicitly approve the one-use workstation mission. "
            + "I have not launched any applications or opened a private screen."
    }

    func executeSpokenExactApp(nodeID: String, appName: String) async -> String {
        // Different consent from tap-to-approve multi-app mission.
        // This command may only open ONE of ten literal benign apps on one
        // already configured host. Bystander voice is not authenticated.
        guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
              appModel.settings.exactVoiceAppActionsEnabled,
              UIApplication.shared.applicationState == .active else {
            return "Exact spoken app actions are off. Opt in separately in Settings. "
                + "No application was launched."
        }
        guard ["windows", "macbook", "macmini"].contains(nodeID),
              Self.conductorApps(for: nodeID).contains(appName) else {
            return "That exact device/application is not in my safe voice registry."
        }
        guard !conductorBusy else {
            return "A workstation mission is already running; no overlapping voice action."
        }
        conductorBusy = true
        defer { conductorBusy = false }
        await refreshFabric()
        guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
              appModel.settings.exactVoiceAppActionsEnabled,
              UIApplication.shared.applicationState == .active,
              nodes.contains(where: {
                  $0.id == nodeID && $0.status == "online"
                      && $0.capabilities["app_launch"] == "exact_user_tap_only"
              }) else {
            return "Exact device is unavailable or voice action permission was revoked. "
                + "No launch attempted."
        }
        do {
            let draft = try await client.conductorPlanWorkstation(
                nodeID: nodeID, apps: [appName], screen: false
            )
            guard let grant = draft.oneUseGrant,
                  appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
                  appModel.settings.exactVoiceAppActionsEnabled,
                  UIApplication.shared.applicationState == .active else {
                _ = try? await client.conductorRevoke(id: draft.id)
                return "Voice permission changed. Workstation draft revoked."
            }
            // The opt-in is standing, but each exact recognized utterance
            // still mints and spends a separate server one-use grant.
            let result = try await client.conductorExecuteWorkstation(
                id: draft.id, grant: grant,
                nodeID: nodeID, apps: [appName]
            )
            guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
                  appModel.settings.exactVoiceAppActionsEnabled,
                  UIApplication.shared.applicationState == .active else {
                _ = try? await client.conductorRevoke(id: draft.id)
                return "The voice action's server result is not current after privacy changed."
            }
            let verified = result.steps.first?.result ?? "unverified"
            conductorStatus = "Spoken exact action on " + nodeID + ": " + verified
                + " for " + appName + ". " + (result.steps.first?.receipt ?? "")
            return verified == "verified_running" || verified == "already_running"
                ? appName + " is observed running on " + nodeID
                    + ". I cannot claim it has focus or a new window."
                : "I attempted the exact app request, but its outcome is "
                    + verified + ". I won't retry automatically."
        } catch {
            return "I couldn't confirm that exact remote app action. "
                + "Do not assume the app did not open or issue an automatic retry."
        }
    }

    func stageConductor() async {
        guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
              UIApplication.shared.applicationState == .active, !conductorBusy,
              conductorMission == nil,
              !conductorSelectedApps.isEmpty,
              conductorSelectedApps.count <= 3,
              nodes.contains(where: {
                  $0.id == conductorNodeID && $0.status == "online"
                  && $0.capabilities["app_launch"] == "exact_user_tap_only"
                  && (!conductorShowScreen ||
                      $0.capabilities["screen"] == "session_opt_in")
              }) else {
            conductorStatus = "Check online devices and exact app/screen permissions. No mission launched."
            return
        }
        conductorBusy = true
        defer { conductorBusy = false }
        do {
            let planned = try await client.conductorPlanWorkstation(
                nodeID: conductorNodeID, apps: conductorSelectedApps,
                screen: conductorShowScreen
            )
            guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
                  UIApplication.shared.applicationState == .active,
                  conductorNodeID == planned.nodeID,
                  conductorSelectedApps == planned.apps,
                  conductorShowScreen == planned.screenRequested,
                  let grant = planned.oneUseGrant else {
                _ = try? await client.conductorRevoke(id: planned.id)
                conductorStatus = "Configuration changed; one-use mission draft revoked."
                return
            }
            conductorMission = planned
            conductorOneUseGrant = grant  // RAM only, never UserDefaults/logs
            conductorLastPreparedID = planned.id
            conductorStatus = "Review exact device and apps below. Nothing executed yet. "
                + "One-use grant expires in two minutes."
        } catch {
            conductorStatus = "Unable to stage an exact-device Conductor mission. "
                + "Check Windows JARVIS_CONDUCTOR_ENABLED=1 and node opt-ins."
        }
    }

    func executeConductor() async {
        guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
              UIApplication.shared.applicationState == .active, !conductorBusy,
              let planned = conductorMission,
              planned.status == "planned",
              let grant = conductorOneUseGrant,
              planned.nodeID == conductorNodeID,
              planned.apps == conductorSelectedApps,
              planned.screenRequested == conductorShowScreen else {
            conductorStatus = "Mission expired, changed or no live exact approval remains."
            return
        }
        // The SwiftUI confirmation button is the explicit user approval.
        // Consume locally before network IO, even when response is lost.
        conductorOneUseGrant = nil
        conductorBusy = true
        conductorStatus = "Exact mission authorized once. Checking node and applying bounded steps…"
        defer { conductorBusy = false }
        do {
            let result = try await client.conductorExecuteWorkstation(
                id: planned.id, grant: grant,
                nodeID: planned.nodeID, apps: planned.apps
            )
            guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
                  UIApplication.shared.applicationState == .active else {
                _ = try? await client.conductorRevoke(id: planned.id)
                conductorStatus = "Phone moved out of authorized foreground; mission state must be checked."
                return
            }
            conductorMission = result
            conductorStatus = "Conductor: " + result.status
                + ". Read each independent process receipt; accepted launch does not prove focus."
            if result.status == "verified_apps" && result.screenRequested {
                await refreshFabric()
                await startScreen(nodeID: result.nodeID)
                if activeNodeID == result.nodeID {
                    await refreshScreen()
                }
                conductorStatus += screenData == nil
                    ? " Private screen display unavailable/unverified."
                    : " Fresh private view is available in Mesh; 2-minute expiry."
            }
        } catch {
            conductorStatus = "Exact one-use mission request had no confirmed response. "
                + "Do not press again: inspect status for an uncertain or partial effect."
            await refreshConductorStatus()
        }
    }

    func refreshConductorStatus() async {
        guard let id = conductorLastPreparedID else {
            conductorStatus = "No local Conductor mission ID. No outcome asserted."
            return
        }
        do {
            conductorMission = try await client.conductorStatus(id: id)
            conductorStatus = "Server reports " + (conductorMission?.status ?? "unknown")
                + ". This is persisted source evidence, not proof of desktop focus."
        } catch {
            conductorStatus = "Cannot retrieve exact mission receipt; result unknown."
        }
    }

    func refreshConductorHistory() async {
        guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled else {
            return
        }
        do {
            let records = try await client.conductorRecent()
            guard appModel.settings.meshEnabled,
                  appModel.settings.conductorEnabled else { return }
            conductorRecent = Array(records.prefix(15))
        } catch {
            conductorStatus = "Recent workstation evidence cannot be loaded."
        }
    }

    func inspectConductorReceipt(_ id: String) async {
        guard appModel.settings.meshEnabled, appModel.settings.conductorEnabled,
              !conductorBusy,
              conductorRecent.contains(where: { $0.id == id }) else { return }
        do {
            let receipt = try await client.conductorStatus(id: id)
            // A persisted draft from a prior app session cannot be redeemed
            // without its original RAM-only grant.
            conductorOneUseGrant = nil
            conductorMission = receipt
            conductorLastPreparedID = receipt.id
            conductorNodeID = receipt.nodeID
            conductorSelectedApps = receipt.apps
            conductorShowScreen = receipt.screenRequested
            conductorStatus = "Showing persisted source receipts; historical approval tokens are not recovered."
        } catch {
            conductorStatus = "That exact historical Conductor receipt is unavailable."
        }
    }

    func revokeConductor() async {
        conductorOneUseGrant = nil
        guard let id = conductorLastPreparedID else {
            conductorMission = nil
            return
        }
        do {
            let result = try await client.conductorRevoke(id: id)
            conductorMission = result
            conductorStatus = "Conductor: " + result.status
                + ". In-flight external actions cannot be rolled back."
        } catch {
            conductorMission = nil
            conductorStatus = "Local mission grant cleared. Backend revoke unconfirmed; "
                + "no automatic retry and grant expires in two minutes."
        }
    }

    func resetConductorSelection() {
        conductorOneUseGrant = nil
        conductorMission = nil
        conductorLastPreparedID = nil
        conductorSelectedApps = []
        conductorShowScreen = false
        conductorStatus = "Select an exact device and new apps. Past side effects are not undone."
    }

    func startScreen(nodeID: String) async {
        guard appModel.settings.meshEnabled, activeNodeID == nil,
              UIApplication.shared.applicationState == .active,
              ["windows", "macbook", "macmini"].contains(nodeID),
              nodes.contains(where: {
                  $0.id == nodeID && $0.status == "online"
                      && $0.capabilities["screen"] == "session_opt_in"
              }) else {
            screenStatus = "Host is offline, not explicitly opted in, or cannot share its interactive screen."
            return
        }
        screenStatus = "Requesting a bounded, user-initiated private host screen session…"
        do {
            let response = try await client.realityMeshStartScreen(nodeID: nodeID)
            guard appModel.settings.meshEnabled,
                  UIApplication.shared.applicationState == .active else {
                try? await client.realityMeshStopScreen(nodeID: nodeID)
                return
            }
            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var expires = iso.date(from: response.expiresAt)
            if expires == nil {
                iso.formatOptions = [.withInternetDateTime]
                expires = iso.date(from: response.expiresAt)
            }
            guard let expiry = expires, expiry > Date(), expiry <= Date().addingTimeInterval(310)
            else {
                try? await client.realityMeshStopScreen(nodeID: nodeID)
                screenStatus = "Host did not return a valid short-lived consent deadline."
                return
            }
            activeNodeID = nodeID
            screenExpiresAt = expiry
            screenStatus = "Screen session enabled on \(nodeID), expires at \(expiry.formatted(date: .omitted, time: .shortened)). View-only snapshots."
            screenLoop?.cancel()
            screenLoop = Task { [weak self] in
                guard let self else { return }
                while !Task.isCancelled,
                      self.activeNodeID == nodeID,
                      self.appModel.settings.meshEnabled,
                      UIApplication.shared.applicationState == .active,
                      Date() < expiry {
                    await self.refreshScreen()
                    try? await Task.sleep(for: .seconds(5))
                }
                if self.activeNodeID == nodeID { await self.stopScreen() }
            }
        } catch {
            screenData = nil
            screenStatus = "Could not open a host screen session. Check exact opt-in, pairing, macOS Screen Recording or interactive Windows desktop."
        }
    }

    func refreshScreen() async {
        guard appModel.settings.meshEnabled,
              UIApplication.shared.applicationState == .active,
              let id = activeNodeID, let expiry = screenExpiresAt,
              Date() < expiry else { return }
        do {
            let frame = try await client.realityMeshScreenFrame(nodeID: id)
            guard appModel.settings.meshEnabled, activeNodeID == id,
                  UIApplication.shared.applicationState == .active,
                  Date() < expiry else { return }
            guard UIImage(data: frame) != nil else {
                screenData = nil
                screenStatus = "Node returned an unrenderable image; no screen content accepted."
                return
            }
            screenData = frame
            screenStatus = "View-only Mac screen snapshot received. Session expires at "
                + expiry.formatted(date: .omitted, time: .shortened)
                + ". No remote keyboard/mouse control exists yet."
        } catch {
            screenData = nil
            screenStatus = "Host screenshot unavailable or session expired. Check screen consent and interactive desktop; no image inferred."
        }
    }

    func stopScreen() async {
        let prior = activeNodeID
        activeNodeID = nil
        screenExpiresAt = nil
        screenData = nil
        screenLoop?.cancel()
        screenLoop = nil
        screenStatus = "Private screen view closed locally; remote Mac consent is time-limited."
        if let id = prior {
            do {
                try await client.realityMeshStopScreen(nodeID: id)
                screenStatus = "Private screen session revoked on the host."
            } catch {
                screenStatus = "Local view cleared; remote stop was not confirmed. Its consent expires automatically within 120 seconds."
            }
        }
    }

    func clearSensitiveViews() {
        nodes = []
        sources = []
        place = nil
        placeGraph = nil
        placeGraphStatus = "Reality Mesh off; graph cleared."
        lensReport = nil
        lensMemories = []
        lensStatus = "Local lens view cleared. Saved backend memories are unchanged until forgotten."
        lensMemoryStatus = "Reality Mesh off."
        placeCoordinate = nil
        resolvedPlaceName = ""
        pendingQuery = ""
        placeCandidates = []
        candidateItems = [:]
        publicWatches = []
        conductorRecent = []
        conductorOneUseGrant = nil
        conductorSelectedApps = []
        conductorMission = nil
        conductorLastPreparedID = nil
        conductorStatus = "Conductor disabled and local one-use grant discarded."
        screenData = nil
        appActionStatus = "No remote app action requested."
        placeName = ""
        screenLoop?.cancel()
        screenLoop = nil
        worldStatus = "Reality Mesh off; previous location/source observations cleared."
    }
}

struct RealityMeshView: View {
    @EnvironmentObject var appModel: JarvisAppModel
    @EnvironmentObject var mesh: RealityMeshController
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Reality Mesh")
                    .font(.largeTitle.weight(.semibold))
                Text("One Jarvis, multiple explicitly paired devices and accurately attributed public-world observations. No network scans, arbitrary computer control, invented cameras or assumed global coverage.")
                    .font(.callout)
                Toggle(
                    "Enable Reality Mesh on this phone",
                    isOn: Binding(
                        get: { appModel.settings.meshEnabled },
                        set: { appModel.settings.meshEnabled = $0 }
                    )
                )
                if !appModel.settings.meshEnabled {
                    Text("Off — no device probing, place requests or Mac screen sessions.")
                        .font(.caption)
                }
                Divider()
                Text("My device fabric")
                    .font(.headline)
                Button(mesh.isCheckingNodes ? "Checking exact devices…" : "Check connected nodes") {
                    Task { await mesh.refreshFabric() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(mesh.isCheckingNodes || !appModel.settings.meshEnabled)
                Text(mesh.nodeStatus)
                    .font(.caption)
                    .accessibilityIdentifier("mesh-node-status")
                HStack {
                    Image(systemName: "iphone")
                    Text("This iPhone/iPad • local command interface; does not assert MemoMind hardware or a remote screen.")
                        .font(.caption)
                }
                ForEach(mesh.nodes) { node in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(node.label + " • " + node.status)
                            .font(.subheadline.weight(.medium))
                        Text(node.evidence)
                            .font(.caption)
                        if let app = node.foregroundApp, !app.isEmpty {
                            Text("Observed foreground process: " + app)
                                .font(.caption2)
                        }
                        Text(node.capabilities
                            .map { $0.key + "=" + $0.value }
                            .sorted()
                            .joined(separator: " • "))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if node.status == "online",
                           node.capabilities["app_launch"] == "exact_user_tap_only",
                           ["windows", "macbook", "macmini"].contains(node.id) {
                            Menu("Open an exact app on this device") {
                                ForEach(
                                    node.id == "windows"
                                        ? ["Notepad", "Calculator", "File Explorer", "Paint"]
                                        : ["Safari", "Notes", "Calendar", "Preview", "Finder"],
                                    id: \.self
                                ) { appName in
                                    Button("Open " + appName + " on " + node.label) {
                                        Task {
                                            await mesh.openExactMacApp(
                                                nodeID: node.id, appName: appName
                                            )
                                        }
                                    }
                                }
                            }
                            .disabled(mesh.appActionBusy)
                        }
                        if node.status == "online",
                           node.capabilities["screen"] == "session_opt_in",
                           ["windows", "macbook", "macmini"].contains(node.id) {
                            Button("View host screen for 2 minutes") {
                                Task { await mesh.startScreen(nodeID: node.id) }
                            }
                            .buttonStyle(.bordered)
                            .disabled(mesh.activeNodeID != nil)
                        }
                    }
                    .padding(10)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }
                Text(mesh.appActionStatus)
                    .font(.caption)
                if let id = mesh.activeNodeID {
                    Divider()
                    Text("Private view-only desktop • " + id)
                        .font(.headline)
                    Text(mesh.screenStatus)
                        .font(.caption)
                    if let imageBytes = mesh.screenData, let image = UIImage(data: imageBytes) {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFit()
                            .accessibilityLabel("Current private Mac screen snapshot")
                    }
                    HStack {
                        Button("Refresh image") { Task { await mesh.refreshScreen() } }
                        Button("Stop host screen", role: .destructive) {
                            Task { await mesh.stopScreen() }
                        }
                    }
                    .buttonStyle(.bordered)
                } else {
                    Text(mesh.screenStatus)
                        .font(.caption)
                }
                Divider()
                ConductorPanelView()
                Divider()
                Text("Presence anywhere")
                    .font(.headline)
                Text("Resolve an exact named place on the phone; then ask Jarvis to check public sources already integrated for that coordinate. No location is automatically monitored or added to an ongoing mission.")
                    .font(.caption)
                TextField("e.g. Melbourne Airport, Victoria", text: $mesh.placeName)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                Button(mesh.isCheckingWorld ? "Checking world sources…" : "Establish remote presence") {
                    Task { await mesh.establishWorldPresence() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(mesh.isCheckingWorld || !appModel.settings.meshEnabled)
                Text(mesh.worldStatus)
                    .font(.caption)
                    .accessibilityIdentifier("mesh-world-status")
                ForEach(mesh.placeCandidates) { choice in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(choice.name)
                            .font(.subheadline.weight(.medium))
                        Text(choice.address)
                            .font(.caption)
                        Button("Select this exact place") {
                            Task { await mesh.selectPlace(choice.id) }
                        }
                        .buttonStyle(.bordered)
                        .disabled(mesh.isCheckingWorld)
                    }
                    .padding(8)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 9))
                }
                if let place = mesh.place {
                    Text(place.summary)
                        .font(.callout)
                    Text("Camera coverage: " + place.cameras.coverage)
                        .font(.caption)
                    Text(place.cameras.sourceNote)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(place.conditions.airQuality.sourceNote)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(place.conditions.weatherAlerts.sourceNote)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ForEach(place.cameras.cameras.prefix(6)) { camera in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(camera.title + " • " + camera.provider)
                                .font(.subheadline.weight(.medium))
                            if let imageURL = URL(string: camera.imageURL),
                               imageURL.scheme == "https" {
                                AsyncImage(url: imageURL) { phase in
                                    if let image = phase.image {
                                        image.resizable().scaledToFit()
                                    } else {
                                        Text("Published still unavailable; this is not live video.")
                                            .font(.caption)
                                    }
                                }
                            }
                            if let stream = URL(string: camera.streamURL),
                               stream.scheme == "https" {
                                Link("Open provider-published stream", destination: stream)
                                    .font(.caption)
                            }
                        }
                        .padding(8)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 9))
                    }
                }
                if mesh.place != nil {
                    RealityGraphPlacePanelView()
                    RealityLensPanelView()
                }
                Divider()
                Text("Time-bounded watch at my selected place")
                    .font(.headline)
                Text("An exact three-hour public-source watch runs on the Jarvis PC even when the iPhone app suspends. Explicitly enrolling one stores the chosen coordinate in Jarvis's separate external-watch ledger. These are ADS-B aircraft reports and USGS earthquake reports, not live worldwide CCTV.")
                    .font(.caption)
                HStack {
                    Button("Watch aircraft • 3h") {
                        Task { await mesh.watchSelectedPlace(kind: "airspace_region") }
                    }
                    Button("Watch USGS events • 3h") {
                        Task { await mesh.watchSelectedPlace(kind: "usgs_earthquakes") }
                    }
                }
                .buttonStyle(.bordered)
                .disabled(!appModel.settings.meshEnabled || mesh.place == nil)
                Button("Refresh my mesh watches") {
                    Task { await mesh.refreshPublicWatches() }
                }
                .buttonStyle(.bordered)
                .disabled(!appModel.settings.meshEnabled)
                Text(mesh.watchStatus)
                    .font(.caption)
                ForEach(mesh.publicWatches) { watch in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(watch.label)
                            .font(.subheadline.weight(.medium))
                        Text("Expires: " + watch.expiresAt + " • " + watch.lastStatus)
                            .font(.caption2)
                        Text(watch.lastSummary)
                            .font(.caption2)
                        Button("Stop exact watch", role: .destructive) {
                            Task { await mesh.stopPublicWatch(watch.id) }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(8)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 9))
                }
                Divider()
                DisclosureGroup("Registered public sensors and actual coverage") {
                    ForEach(mesh.sources) { source in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(source.label)
                                .font(.subheadline.weight(.medium))
                            Text(source.coverage + " • " + source.kind)
                                .font(.caption)
                            Text(source.status + " — not a live measurement")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
                Text("A registered feed is not proof of a working stream. Reality Mesh supplies evidence; Mission Control still requires an explicitly enrolled goal and separate action authorization.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding()
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase != .active {
                Task {
                    await mesh.stopScreen()
                    if ["planned", "running"].contains(mesh.conductorMission?.status ?? "") {
                        await mesh.revokeConductor()
                    }
                }
            }
        }
        .onChange(of: appModel.settings.meshEnabled) { _, enabled in
            if !enabled {
                Task {
                    await mesh.stopScreen()
                    await mesh.revokeConductor()
                    mesh.clearSensitiveViews()
                }
            }
        }
        .onChange(of: appModel.settings.conductorEnabled) { _, enabled in
            if !enabled {
                Task { await mesh.revokeConductor() }
            }
        }
        .onDisappear {
            Task {
                await mesh.stopScreen()
                if ["planned", "running"].contains(mesh.conductorMission?.status ?? "") {
                    await mesh.revokeConductor()
                }
            }
        }
    }
}



// An intentional extra sense: fresh public measurements, explicit short-term
// source memory and tactile change feedback, without voice or model planning.
private struct RealityLensPanelView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @EnvironmentObject private var mesh: RealityMeshController
    @State private var confirmForget = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Reality Lens • sense and remember", systemImage: "eye.circle")
                .font(.headline)
            Text("Feel whether supported public measurements changed since an "
                 + "explicitly saved observation of this exact place. "
                 + "Two or three light taps mean a recorded value changed; "
                 + "silence is NOT proof the place is safe or unchanged.")
                .font(.caption)
            HStack {
                Button(mesh.lensBusy ? "Sensing…" : "Sense and compare") {
                    Task { await mesh.senseSelectedPlace(remember: false) }
                }
                .buttonStyle(.borderedProminent)
                Button("Remember now • 30 days") {
                    Task { await mesh.senseSelectedPlace(remember: true) }
                }
                .buttonStyle(.bordered)
            }
            .disabled(!appModel.settings.meshEnabled || mesh.lensBusy)
            Text("Remember stores the selected place's label and small, source-backed "
                 + "numeric facts on your private Jarvis PC; no photos, GPS trail, "
                 + "raw feed or continuous recording. Sense alone does not save.")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(mesh.lensStatus)
                .font(.caption)
                .accessibilityIdentifier("reality-lens-status")
            if let report = mesh.lensReport {
                Text("Observed \(report.checkedAt) • \(report.modelCalls) Qwen calls")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                ForEach(report.observations) { item in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(item.label): \(item.value.display)")
                            .font(.subheadline)
                        Text("\(item.source) • \(item.observedAt)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                ForEach(report.changes) { change in
                    Label(
                        "\(change.label): \(change.before.display) → \(change.after.display)",
                        systemImage: "arrow.triangle.2.circlepath"
                    )
                    .font(.callout)
                    Text("\(change.source) • \(change.qualifier)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if !report.unknownMetrics.isEmpty {
                    Text("Unknown or stale: \(report.unknownMetrics.joined(separator: ", "))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            HStack {
                Button("Show my saved observations") {
                    Task { await mesh.refreshLensMemories() }
                }
                .buttonStyle(.bordered)
                Button("Forget this place", role: .destructive) {
                    confirmForget = true
                }
                .buttonStyle(.bordered)
                .disabled(mesh.lensBusy)
            }
            Text(mesh.lensMemoryStatus)
                .font(.caption2)
                .foregroundStyle(.secondary)
            ForEach(mesh.lensMemories) { memory in
                Text("\(memory.label) • \(memory.capturedAt) • \(memory.factCount) sourced facts")
                    .font(.caption2)
            }
        }
        .padding(10)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
        .confirmationDialog(
            "Delete saved observations for this exact place?",
            isPresented: $confirmForget,
            titleVisibility: .visible
        ) {
            Button("Delete only this place's saved observations", role: .destructive) {
                Task { await mesh.forgetSelectedLensPlace() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the Reality Lens memory on your Jarvis PC "
                 + "for the selected coordinates. It does not delete separate "
                 + "public watches or world-model records.")
        }
    }
}

private struct ConductorPanelView: View {
    @EnvironmentObject var appModel: JarvisAppModel
    @EnvironmentObject var mesh: RealityMeshController
    @State private var confirmConductorExecution = false

    private var approvalMessage: String {
        let screen = mesh.conductorShowScreen
            ? ". Includes temporary private screen viewing."
            : ". No screen viewing."
        return "One exact device: \(mesh.conductorNodeID). Apps: "
            + mesh.conductorSelectedApps.joined(separator: ", ")
            + screen
            + " No terminal, email, file transfer, weapon or general OS input."
    }

    var body: some View {
        conductorContent
            .confirmationDialog(
                "Approve exact workstation actions?",
                isPresented: $confirmConductorExecution,
                titleVisibility: .visible
            ) {
                Button("Run exactly these device and app actions once") {
                    Task { await mesh.executeConductor() }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text(approvalMessage)
            }
    }

    private var conductorContent: some View {
        VStack(alignment: .leading, spacing: 12) {
                Text("Conductor • Prepare my workstation")
                    .font(.headline)
                Toggle(
                    "Enable exact workstation missions on this phone",
                    isOn: Binding(
                        get: { appModel.settings.conductorEnabled },
                        set: { appModel.settings.conductorEnabled = $0 }
                    )
                )
                Text("Say 'Jarvis, prepare my workstation' to open this workflow. "
                     + "Choose one exact paired machine, 1–3 registered apps and optional "
                     + "two-minute view. Speaking does not grant remote execution.")
                    .font(.caption)
                Picker("Workstation", selection: Binding(
                    get: { mesh.conductorNodeID },
                    set: { mesh.selectConductorNode($0) }
                )) {
                    Text("Windows PC").tag("windows")
                    Text("MacBook Air").tag("macbook")
                    Text("Mac mini").tag("macmini")
                }
                .pickerStyle(.segmented)
                .disabled(mesh.conductorBusy || mesh.conductorMission != nil)
                ForEach(
                    RealityMeshController.conductorApps(for: mesh.conductorNodeID),
                    id: \.self
                ) { app in
                    Button {
                        mesh.toggleConductorApp(app)
                    } label: {
                        Label(
                            app,
                            systemImage: mesh.conductorSelectedApps.contains(app)
                                ? "checkmark.square.fill" : "square"
                        )
                    }
                    .disabled(
                        mesh.conductorBusy || mesh.conductorMission != nil
                        || (!mesh.conductorSelectedApps.contains(app)
                            && mesh.conductorSelectedApps.count >= 3)
                    )
                }
                Toggle("Also show this exact machine's private desktop for 2 minutes",
                       isOn: $mesh.conductorShowScreen)
                    .disabled(mesh.conductorBusy || mesh.conductorMission != nil)
                if mesh.conductorMission == nil {
                    Button("Review exact workstation mission") {
                        Task { await mesh.stageConductor() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        !appModel.settings.meshEnabled
                        || !appModel.settings.conductorEnabled
                        || mesh.conductorBusy || mesh.conductorSelectedApps.isEmpty
                    )
                }
                Text(mesh.conductorStatus)
                    .font(.caption)
                    .accessibilityIdentifier("conductor-status")
                if let mission = mesh.conductorMission {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Exact node: " + mission.nodeID)
                        Text("Exact apps: " + mission.apps.joined(separator: ", "))
                        Text("Private screen: " + (mission.screenRequested ? "yes" : "no"))
                        Text("State: " + mission.status + " • expiry " + mission.expiresAt)
                        if mission.status == "planned" {
                            Button("Approve these exact actions once") {
                                confirmConductorExecution = true
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(mesh.conductorBusy
                                || !appModel.settings.conductorEnabled
                                || !mesh.conductorHasOneUseGrant)
                        }
                        if ["planned", "running"].contains(mission.status) {
                            Button("Revoke remaining Conductor actions",
                                   role: .destructive) {
                                Task { await mesh.revokeConductor() }
                            }
                            .buttonStyle(.bordered)
                        } else {
                            Button("Start a new workstation mission") {
                                mesh.resetConductorSelection()
                            }
                            .buttonStyle(.bordered)
                        }
                        Button("Inspect persisted mission state") {
                            Task { await mesh.refreshConductorStatus() }
                        }
                        .buttonStyle(.bordered)
                        ForEach(mission.steps) { step in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(step.appName + " • " + step.result)
                                    .font(.subheadline.weight(.medium))
                                Text("Before: " + step.beforeState
                                     + " (" + step.beforeObservedAt + ")")
                                Text("After: " + step.afterState
                                     + " (" + step.afterObservedAt + ")")
                                Text(step.receipt)
                                Text("Evidence: " + step.source)
                                    .foregroundStyle(.secondary)
                            }
                            .font(.caption2)
                            .padding(7)
                            .background(.thinMaterial,
                                        in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                    .padding(9)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }
                Button("View recent Conductor receipts after restart") {
                    Task { await mesh.refreshConductorHistory() }
                }
                .buttonStyle(.bordered)
                .disabled(!appModel.settings.meshEnabled
                    || !appModel.settings.conductorEnabled)
                ForEach(mesh.conductorRecent) { receipt in
                    Button {
                        Task { await mesh.inspectConductorReceipt(receipt.id) }
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(receipt.nodeID + " • " + receipt.status)
                            Text(receipt.apps.joined(separator: ", ")
                                + " • " + receipt.updatedAt)
                                .font(.caption2)
                        }
                    }
                    .buttonStyle(.bordered)
                }
        }
    }
}


private struct RealityGraphPlacePanelView: View {
    @EnvironmentObject var appModel: JarvisAppModel
    @EnvironmentObject var mesh: RealityMeshController

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Reality Graph • model-free place facts")
                .font(.headline)
            Text("A fresh independent provider check for the exact selected place. "
                 + "Catalog entries are not confirmed live video, and an absent alert "
                 + "is not an all-hazards clearance.")
                .font(.caption)
            Button(mesh.isCheckingPlaceGraph ? "Compiling graph…" : "Compile Reality Graph") {
                Task { await mesh.refreshPlaceGraph() }
            }
            .buttonStyle(.bordered)
            .disabled(mesh.isCheckingPlaceGraph || !appModel.settings.meshEnabled)
            Text(mesh.placeGraphStatus)
                .font(.caption)
                .accessibilityIdentifier("mesh-place-graph-status")
            if let graph = mesh.placeGraph {
                let fresh = Set(graph.evidence.filter { $0.freshness == "fresh" }.map(\.id))
                ForEach(graph.derivedFacts) { fact in
                    let supported = fact.evidenceIDs.isEmpty
                        || fact.evidenceIDs.allSatisfy { fresh.contains($0) }
                    VStack(alignment: .leading, spacing: 3) {
                        Text(fact.id.replacingOccurrences(of: "fact:", with: "")
                            .replacingOccurrences(of: "_", with: " ")
                            + ": " + fact.value.display)
                            .font(.subheadline.weight(.medium))
                        Text((supported ? "" : "Historical/stale — not current. ")
                             + fact.explanation)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(7)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
                }
                ForEach(graph.providerStates.keys.sorted(), id: \.self) { key in
                    Text(key + " • " + (graph.providerStates[key] ?? "unknown"))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}
