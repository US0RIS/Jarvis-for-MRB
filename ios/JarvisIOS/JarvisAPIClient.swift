import Foundation

struct RealityMeshNodesResponse: Decodable {
    struct Node: Decodable, Identifiable {
        let id: String
        let label: String
        let status: String
        let platform: String
        let evidence: String
        let capabilities: [String: String]
        let screenSessionActive: Bool
        let foregroundApp: String?

        enum CodingKeys: String, CodingKey {
            case id, label, status, platform, evidence, capabilities
            case screenSessionActive = "screen_session_active"
            case foregroundApp = "foreground_app"
        }
    }

    let checkedAt: String
    let nodes: [Node]

    enum CodingKeys: String, CodingKey {
        case nodes
        case checkedAt = "checked_at"
    }
}

struct RealityMeshSourceRegistry: Decodable {
    struct Source: Decodable, Identifiable {
        let id: String
        let label: String
        let coverage: String
        let kind: String
        let status: String
        let sourceURL: String

        enum CodingKeys: String, CodingKey {
            case id, label, coverage, kind, status
            case sourceURL = "source_url"
        }
    }

    let checkedAt: String
    let sources: [Source]

    enum CodingKeys: String, CodingKey {
        case sources
        case checkedAt = "checked_at"
    }
}

struct RealityMeshPlaceResponse: Decodable {
    let checkedAt: String
    let data: PhysicalAwarenessResponse

    enum CodingKeys: String, CodingKey {
        case data
        case checkedAt = "checked_at"
    }
}

struct RealityMeshScreenSession: Decodable {
    let nodeID: String
    let status: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case status
        case nodeID = "node_id"
        case expiresAt = "expires_at"
    }
}

struct MissionAffordanceCatalog: Decodable {
    struct Capability: Decodable, Identifiable {
        let id: String
        let label: String
        let effect: String
        let contractDefined: Bool
        let permissionAllowed: Bool
        let requiresConfirmation: Bool
        let agencyScopeImplemented: Bool
        let liveConnectionVerified: Bool
        let executionAuthorizedByCatalog: Bool

        enum CodingKeys: String, CodingKey {
            case id, label, effect
            case contractDefined = "contract_defined"
            case permissionAllowed = "permission_allowed"
            case requiresConfirmation = "requires_confirmation"
            case agencyScopeImplemented = "agency_scope_implemented"
            case liveConnectionVerified = "live_connection_verified"
            case executionAuthorizedByCatalog = "execution_authorized_by_catalog"
        }
    }

    let checkedAt: String
    let capabilities: [Capability]

    enum CodingKeys: String, CodingKey {
        case capabilities
        case checkedAt = "checked_at"
    }
}

struct GuardianObjectiveOverview: Decodable {
    struct Candidate: Decodable, Identifiable {
        let intentionID: String
        let title: String
        let deadlineAt: String
        let enrolled: Bool

        var id: String { intentionID }

        enum CodingKeys: String, CodingKey {
            case title, enrolled
            case intentionID = "intention_id"
            case deadlineAt = "deadline_at"
        }
    }

    struct Watch: Decodable, Identifiable {
        let id: String
        let intentionID: String
        let title: String
        let deadlineAt: String
        let status: String
        let lastSignal: String
        let snoozedUntil: String

        enum CodingKeys: String, CodingKey {
            case id, title, status
            case intentionID = "intention_id"
            case deadlineAt = "deadline_at"
            case lastSignal = "last_signal"
            case snoozedUntil = "snoozed_until"
        }
    }

    let phoneConsentLive: Bool
    let phoneAvailableForInterruption: Bool
    let enrollable: [Candidate]
    let watches: [Watch]

    enum CodingKeys: String, CodingKey {
        case enrollable, watches
        case phoneConsentLive = "phone_consent_live"
        case phoneAvailableForInterruption = "phone_available_for_interruption"
    }
}

struct GuardianObjectiveEvaluation: Decodable, Identifiable {
    let id: String
    let title: String
    let status: String
    let message: String
    let evidence: String
    let nextAction: String?
    let pendingDependencies: [Dependency]?
    let phoneConsentLive: Bool?

    struct Dependency: Decodable, Identifiable {
        let id: String
        let owner: String
        let action: String
    }

    enum CodingKeys: String, CodingKey {
        case id, title, status, message, evidence
        case nextAction = "next_action"
        case pendingDependencies = "pending_dependencies"
        case phoneConsentLive = "phone_consent_live"
    }
}

private struct GuardianObjectiveEvaluationEnvelope: Decodable {
    let evaluations: [GuardianObjectiveEvaluation]
}

struct GuardianCalendarResponse: Decodable {
    struct Event: Decodable, Identifiable {
        let id: String
        let summary: String
        let start: String
        let location: String
    }
    let ok: Bool
    let checkedAt: String
    let events: [Event]

    enum CodingKeys: String, CodingKey {
        case ok, events
        case checkedAt = "checked_at"
    }
}

struct JarvisAPIResponse: Decodable {
    let ok: Bool
    let message: String
}

struct EmailAllowlistResponse: Decodable {
    let addresses: [String]
}

struct TTSStatusResponse: Decodable {
    let status: String
}

struct PlannerModelResponse: Decodable {
    let model: String
    let autoRoute: Bool
    let options: [String]

    enum CodingKeys: String, CodingKey {
        case model
        case autoRoute = "auto_route"
        case options
    }
}

struct MeetingStartResponse: Decodable {
    let ok: Bool
    let meetingID: Int
    let message: String

    enum CodingKeys: String, CodingKey {
        case ok
        case meetingID = "meeting_id"
        case message
    }
}

enum JarvisStreamEvent {
    case start(model: String?, routeReason: String?)
    case delta(String)
    case done(ok: Bool?)
}

private struct APIErrorDetail: Decodable {
    let detail: String
}

private struct JarvisStreamPacket: Decodable {
    let type: String
    let text: String?
    let ok: Bool?
    let model: String?
    let routeReason: String?

    enum CodingKeys: String, CodingKey {
        case type
        case text
        case ok
        case model
        case routeReason = "route_reason"
    }
}

private actor JarvisEndpointResolver {
    static let shared = JarvisEndpointResolver()

    private var cachedURL: String?
    private var cachedUntil = Date.distantPast

    func resolve(primary: String, fallback: String, apiToken: String) async throws -> String {
        let candidates = [primary, fallback]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .reduce(into: [String]()) { result, item in
                if !result.contains(item) { result.append(item) }
            }

        guard !candidates.isEmpty else { throw JarvisAPIError.badURL }

        if let cachedURL, cachedUntil > Date(), candidates.contains(cachedURL) {
            return cachedURL
        }

        for (index, candidate) in candidates.enumerated() {
            let timeout: TimeInterval = index == 0 ? 0.25 : 1.5
            if await probe(candidate, apiToken: apiToken, timeout: timeout) {
                cachedURL = candidate
                cachedUntil = Date().addingTimeInterval(30)
                return candidate
            }
        }

        cachedURL = nil
        cachedUntil = .distantPast
        throw URLError(.cannotConnectToHost)
    }

    func invalidate(_ url: String) {
        if cachedURL == url {
            cachedURL = nil
            cachedUntil = .distantPast
        }
    }

    private func probe(_ baseURL: String, apiToken: String, timeout: TimeInterval) async -> Bool {
        guard let url = URL(string: baseURL)?.appendingPathComponent("health") else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        if !apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        }
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200..<300).contains(http.statusCode)
        } catch {
            return false
        }
    }
}

enum JarvisAPIError: LocalizedError {
    case badURL
    case badResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .badURL: return "The Jarvis server URL is invalid."
        case .badResponse: return "Jarvis returned an invalid response."
        case .server(let message): return message
        }
    }
}

struct JarvisAPIClient {
    let baseURL: String
    let fallbackBaseURL: String
    let apiToken: String
    let sessionID: String

    init(baseURL: String, fallbackBaseURL: String = "", apiToken: String, sessionID: String) {
        self.baseURL = baseURL
        let explicitFallback = fallbackBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        self.fallbackBaseURL = explicitFallback.isEmpty
            ? (UserDefaults.standard.string(forKey: "jarvis.fallbackBaseURL") ?? "")
            : explicitFallback
        self.apiToken = apiToken
        self.sessionID = sessionID
    }

    func activeBaseURL() async throws -> String {
        try await JarvisEndpointResolver.shared.resolve(
            primary: baseURL,
            fallback: fallbackBaseURL,
            apiToken: apiToken
        )
    }

    func health() async throws -> Bool {
        let base = try await activeBaseURL()
        guard let url = URL(string: base)?.appendingPathComponent("health") else { throw JarvisAPIError.badURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        addAuthorization(to: &request)
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw JarvisAPIError.badResponse }
            return (200..<300).contains(http.statusCode)
        } catch {
            await JarvisEndpointResolver.shared.invalidate(base)
            throw error
        }
    }

    func listDiligenceMatters() async throws -> [DiligenceMatterSummary] {
        let (data, response) = try await postData(
            path: "external/diligence/list", body: [:]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(DiligenceMatterList.self, from: data).matters
    }

    func createDiligenceMatter(label: String, projectEntityID: String) async throws -> DiligenceMatterSummary {
        let (data, response) = try await postData(
            path: "external/diligence/matter",
            body: ["label": label, "project_entity_id": projectEntityID]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(DiligenceMatterSummary.self, from: data)
    }

    func registerDiligenceIssuer(matterID: String, cik: String, name: String) async throws {
        let (data, response) = try await postData(
            path: "external/diligence/issuer",
            body: ["matter_id": matterID, "cik": cik, "asserted_name": name]
        )
        try validate(response: response, data: data)
    }

    func registerDiligenceEPAFacility(
        matterID: String, cik: String, frsID: String, label: String
    ) async throws {
        let (data, response) = try await postData(
            path: "external/diligence/epa-facility",
            body: [
                "matter_id": matterID, "cik": cik,
                "frs_id": frsID, "label": label,
            ]
        )
        try validate(response: response, data: data)
    }

    func registerNumericDiligenceClaim(
        matterID: String, cik: String, taxonomy: String, tag: String,
        value: Double, unit: String, start: String, end: String, sourceRef: String
    ) async throws {
        let (data, response) = try await postData(
            path: "external/diligence/claim",
            body: [
                "matter_id": matterID, "cik": cik, "taxonomy": taxonomy,
                "tag": tag, "value": value, "unit": unit,
                "start": start, "end": end, "source_ref": sourceRef,
            ]
        )
        try validate(response: response, data: data)
    }

    func checkDiligenceMatter(matterID: String, includeSanctions: Bool) async throws -> [String: Any] {
        let (data, response) = try await postData(
            path: "external/diligence/check",
            body: ["matter_id": matterID, "include_sanctions": includeSanctions]
        )
        try validate(response: response, data: data)
        guard let parsed = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NSError(domain: "JarvisDiligence", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "Diligence response is not an object."
            ])
        }
        return parsed
    }

    func createExternalWatch(
        kind: String, label: String, config: [String: Any],
        seconds: Int, scope: String = "personal", expiresHours: Int = 24
    ) async throws -> ExternalWatchSummary {
        let (data, response) = try await postData(
            path: "external/watch/create",
            body: [
                "scope": scope, "kind": kind, "label": label,
                "config": config, "interval_seconds": seconds,
                "expires_hours": expiresHours,
            ]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(ExternalWatchSummary.self, from: data)
    }

    func getExternalWatches(scope: String = "personal") async throws -> [ExternalWatchSummary] {
        let (data, response) = try await postData(
            path: "external/watch/list", body: ["scope": scope]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(ExternalWatchListResponse.self, from: data).watches
    }

    func checkExternalWatch(_ id: String, scope: String = "personal") async throws -> ExternalWatchCheckResponse {
        let (data, response) = try await postData(
            path: "external/watch/check", body: ["id": id, "scope": scope]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(ExternalWatchCheckResponse.self, from: data)
    }

    func stopExternalWatch(_ id: String, scope: String = "personal") async throws -> ExternalWatchSummary {
        let (data, response) = try await postData(
            path: "external/watch/stop", body: ["id": id, "scope": scope]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(ExternalWatchSummary.self, from: data)
    }

    func physicalAwareness(latitude: Double, longitude: Double) async throws -> PhysicalAwarenessResponse {
        let (data, response) = try await postData(
            path: "physical/awareness",
            body: ["latitude": latitude, "longitude": longitude]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(PhysicalAwarenessResponse.self, from: data)
    }

    func analyzeOfficialPublicCamera(_ cameraID: String) async throws -> PublicCameraAnalysisResponse {
        let (data, response) = try await postData(
            path: "physical/public-cameras/analyze",
            body: ["camera_id": cameraID]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(PublicCameraAnalysisResponse.self, from: data)
    }

    func discoverNearbyFacilities(latitude: Double, longitude: Double) async throws -> NearbyFacilitiesResponse {
        let (data, response) = try await postData(
            path: "physical/facilities",
            body: [
                "latitude": latitude, "longitude": longitude,
                "radius_m": 1500, "limit": 18,
            ]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(NearbyFacilitiesResponse.self, from: data)
    }

    func discoverPhysicalConditions(latitude: Double, longitude: Double) async throws -> PhysicalConditionsResponse {
        let (data, response) = try await postData(
            path: "physical/conditions",
            body: ["latitude": latitude, "longitude": longitude]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(PhysicalConditionsResponse.self, from: data)
    }

    func discoverNearbyPublicCameras(latitude: Double, longitude: Double) async throws -> PublicCameraDiscoveryResponse {
        let (data, response) = try await postData(
            path: "physical/public-cameras",
            body: [
                "latitude": latitude,
                "longitude": longitude,
                "radius_km": 10.0,
                "limit": 8,
            ]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(PublicCameraDiscoveryResponse.self, from: data)
    }

    func realityMeshNodes() async throws -> RealityMeshNodesResponse {
        let (data, response) = try await get(path: "mesh/nodes", timeout: 12)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(RealityMeshNodesResponse.self, from: data)
    }

    func realityMeshSources() async throws -> RealityMeshSourceRegistry {
        let (data, response) = try await get(path: "mesh/public-sources", timeout: 9)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(RealityMeshSourceRegistry.self, from: data)
    }

    func realityMeshPlace(latitude: Double, longitude: Double) async throws -> RealityMeshPlaceResponse {
        let (data, response) = try await postData(
            path: "mesh/place",
            body: ["latitude": latitude, "longitude": longitude]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(RealityMeshPlaceResponse.self, from: data)
    }

    func realityMeshStartScreen(nodeID: String) async throws -> RealityMeshScreenSession {
        let (data, response) = try await postData(
            path: "mesh/screen/begin",
            body: ["node_id": nodeID, "duration_seconds": 120]
        )
        try validate(response: response, data: data)
        return try JSONDecoder().decode(RealityMeshScreenSession.self, from: data)
    }

    func realityMeshStopScreen(nodeID: String) async throws {
        let (data, response) = try await postData(
            path: "mesh/screen/stop", body: ["node_id": nodeID]
        )
        try validate(response: response, data: data)
    }

    func realityMeshScreenFrame(nodeID: String) async throws -> Data {
        guard ["windows", "macbook", "macmini"].contains(nodeID) else { throw JarvisAPIError.badResponse }
        let (data, response) = try await get(
            path: "mesh/screen/" + nodeID, timeout: 10
        )
        try validate(response: response, data: data)
        guard data.count >= 80, data.count <= 4_000_000,
              let http = response as? HTTPURLResponse,
              ["image/jpeg", "image/png"].contains(
                  http.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first.map(String.init)
              ) else {
            throw JarvisAPIError.badResponse
        }
        return data
    }

    func missionAffordanceCatalog() async throws -> MissionAffordanceCatalog {
        let (data, response) = try await get(path: "missions/affordances", timeout: 9)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(MissionAffordanceCatalog.self, from: data)
    }

    func guardianObjectiveOverview() async throws -> GuardianObjectiveOverview {
        let (data, response) = try await get(path: "guardian/objectives", timeout: 9)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(GuardianObjectiveOverview.self, from: data)
    }

    func guardianObjectiveEvaluations() async throws -> [GuardianObjectiveEvaluation] {
        let (data, response) = try await get(path: "guardian/objectives/evaluate", timeout: 9)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(
            GuardianObjectiveEvaluationEnvelope.self, from: data
        ).evaluations
    }

    func guardianObjectiveEnroll(_ intentionID: String) async throws {
        let (data, response) = try await postData(
            path: "guardian/objectives/enroll", body: ["id": intentionID]
        )
        try validate(response: response, data: data)
    }

    func guardianObjectiveRevoke(_ watchID: String) async throws {
        let (data, response) = try await postData(
            path: "guardian/objectives/revoke", body: ["id": watchID]
        )
        try validate(response: response, data: data)
    }

    func guardianObjectiveSnooze(_ watchID: String, hours: Int = 1) async throws {
        let (data, response) = try await postData(
            path: "guardian/objectives/snooze",
            body: ["id": watchID, "hours": hours]
        )
        try validate(response: response, data: data)
    }

    func guardianCalendarExpectations() async throws -> GuardianCalendarResponse {
        let (data, response) = try await get(path: "guardian/calendar", timeout: 9)
        try validate(response: response, data: data)
        let result = try JSONDecoder().decode(GuardianCalendarResponse.self, from: data)
        guard result.ok else { throw JarvisAPIError.badResponse }
        return result
    }

    func agencyCommandView() async throws -> MemoMindCommandSnapshot {
        let (data, response) = try await get(path: "agency/command-view", timeout: 15)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(MemoMindCommandSnapshot.self, from: data)
    }

    func command(_ text: String) async throws -> JarvisAPIResponse {
        let response = try await post(path: "command", body: ["text": text, "session_id": sessionID])
        return JarvisAPIResponse(ok: response.ok, message: Self.collapseRepeatedSir(response.message))
    }

    func streamCommandEvents(_ text: String) -> AsyncThrowingStream<JarvisStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                var resolvedBase = ""
                do {
                    resolvedBase = try await activeBaseURL()
                    guard let url = URL(string: resolvedBase)?.appendingPathComponent("command/stream") else {
                        throw JarvisAPIError.badURL
                    }
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.timeoutInterval = 120
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("application/x-ndjson", forHTTPHeaderField: "Accept")
                    addAuthorization(to: &request)
                    request.httpBody = try JSONSerialization.data(withJSONObject: [
                        "text": text,
                        "session_id": sessionID,
                    ])

                    let (bytes, response) = try await URLSession.shared.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw JarvisAPIError.badResponse
                    }
                    guard (200..<300).contains(http.statusCode) else {
                        var data = Data()
                        for try await byte in bytes {
                            data.append(byte)
                            if data.count > 16_384 { break }
                        }
                        try validate(response: response, data: data)
                        throw JarvisAPIError.badResponse
                    }

                    var sawTextDelta = false
                    var reachedDonePacket = false
                    var emittedTextTail = ""

                    for try await line in bytes.lines {
                        guard !line.isEmpty, let data = line.data(using: .utf8) else { continue }
                        let packet = try JSONDecoder().decode(JarvisStreamPacket.self, from: data)
                        switch packet.type {
                        case "start":
                            continuation.yield(.start(model: packet.model, routeReason: packet.routeReason))

                        case "delta":
                            if let raw = packet.text, !raw.isEmpty {
                                let cleaned = Self.normalizeStreamText(raw, previousTail: emittedTextTail)
                                if !cleaned.isEmpty {
                                    sawTextDelta = true
                                    continuation.yield(.delta(cleaned))
                                    emittedTextTail = String((emittedTextTail + cleaned).suffix(64))
                                }
                            }

                        case "done":
                            reachedDonePacket = true
                            if !sawTextDelta {
                                try await recoverFromEmptyStream(
                                    originalText: text,
                                    backendOK: packet.ok,
                                    continuation: continuation
                                )
                            } else {
                                continuation.yield(.done(ok: packet.ok))
                            }
                            continuation.finish()
                            return

                        default:
                            if let raw = packet.text, !raw.isEmpty {
                                let cleaned = Self.normalizeStreamText(raw, previousTail: emittedTextTail)
                                if !cleaned.isEmpty {
                                    sawTextDelta = true
                                    continuation.yield(.delta(cleaned))
                                    emittedTextTail = String((emittedTextTail + cleaned).suffix(64))
                                }
                            }
                        }
                    }

                    if !sawTextDelta && !reachedDonePacket {
                        try await recoverFromEmptyStream(
                            originalText: text,
                            backendOK: nil,
                            continuation: continuation
                        )
                    }
                    continuation.finish()
                } catch {
                    if !resolvedBase.isEmpty {
                        await JarvisEndpointResolver.shared.invalidate(resolvedBase)
                    }
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    private func recoverFromEmptyStream(
        originalText: String,
        backendOK: Bool?,
        continuation: AsyncThrowingStream<JarvisStreamEvent, Error>.Continuation
    ) async throws {
        if Self.safeToRetryAsReadOnlyRequest(originalText) {
            let response = try await command(originalText)
            let message = response.message.trimmingCharacters(in: .whitespacesAndNewlines)
            if !message.isEmpty {
                continuation.yield(.delta(response.message))
                continuation.yield(.done(ok: response.ok))
                return
            }
        }

        let explanation: String
        if Self.safeToRetryAsReadOnlyRequest(originalText) {
            explanation = "Jarvis finished without returning an answer."
        } else if backendOK == false {
            explanation = "The backend failed before returning an answer. I didn't retry automatically because that could duplicate an action."
        } else {
            explanation = "The backend returned no answer. I didn't retry automatically because that could duplicate an action."
        }
        continuation.yield(.delta(explanation))
        continuation.yield(.done(ok: false))
    }

    private static func normalizeStreamText(_ raw: String, previousTail: String) -> String {
        var value = collapseRepeatedSir(raw)

        // A model or legacy backend may still produce an honorific at a chunk
        // boundary. Collapse adjacent duplicates without adding any new address.
        let tail = previousTail.lowercased().trimmingCharacters(in: .newlines)
        let tailEndsInSir = tail.range(
            of: #"sir\s*[,;:!.-]?\s*$"#,
            options: .regularExpression
        ) != nil
        if tailEndsInSir {
            value = value.replacingOccurrences(
                of: #"(?i)^\s*sir\b[\s,;:!\.\-–—]*"#,
                with: "",
                options: .regularExpression
            )
        }
        return collapseRepeatedSir(value)
    }

    private static func collapseRepeatedSir(_ raw: String) -> String {
        raw.replacingOccurrences(
            of: #"(?i)\b(sir)\b(?:[\s,;:!\.\-–—]*\bsir\b)+"#,
            with: "$1",
            options: .regularExpression
        )
    }

    private static func safeToRetryAsReadOnlyRequest(_ raw: String) -> Bool {
        let normalized = " " + raw.lowercased()
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\t", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines) + " "

        let mutationMarkers = [
            " send ", " reply ", " forward ", " create ", " schedule ", " remind ",
            " cancel ", " delete ", " remove ", " open ", " close ", " launch ",
            " start ", " stop ", " set ", " change ", " update ", " write ",
            " log ", " export ", " run ", " execute ", " apply ", " enable ",
            " disable ", " turn on ", " turn off ", " move ", " rename ",
            " archive ", " trash ", " post ", " submit ", " book ", " call ",
            " text ", " upload ", " download ", " install ", " restart ",
        ]
        if mutationMarkers.contains(where: { normalized.contains($0) }) {
            return false
        }

        let trimmed = normalized.trimmingCharacters(in: .whitespaces)
        let readOnlyPrefixes = [
            "what ", "who ", "when ", "where ", "why ", "how ", "which ",
            "is ", "are ", "am ", "do ", "does ", "did ", "can ", "could ",
            "should ", "would ", "tell me ", "explain ", "compare ", "summarize ",
            "search ", "find ", "check ", "list ", "show ", "give me ",
        ]
        return readOnlyPrefixes.contains(where: { trimmed.hasPrefix($0) })
            || trimmed.hasSuffix("?")
    }

    func streamCommand(_ text: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await event in streamCommandEvents(text) {
                        if case .delta(let text) = event { continuation.yield(text) }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    func ttsStatus() async throws -> String {
        let (data, response) = try await get(path: "tts/status", timeout: 5)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(TTSStatusResponse.self, from: data).status
    }

    func plannerModel() async throws -> PlannerModelResponse {
        let (data, response) = try await get(path: "settings/planner-model", timeout: 10)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(PlannerModelResponse.self, from: data)
    }

    func setPlannerModel(model: String? = nil, autoRoute: Bool? = nil) async throws -> PlannerModelResponse {
        let base = try await activeBaseURL()
        guard let url = URL(string: base)?.appendingPathComponent("settings/planner-model") else {
            throw JarvisAPIError.badURL
        }
        var payload: [String: Any] = [:]
        if let model { payload["model"] = model }
        if let autoRoute { payload["auto_route"] = autoRoute }

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            try validate(response: response, data: data)
            return try JSONDecoder().decode(PlannerModelResponse.self, from: data)
        } catch {
            await JarvisEndpointResolver.shared.invalidate(base)
            throw error
        }
    }

    func synthesizeSpeech(_ text: String) async throws -> Data {
        let base = try await activeBaseURL()
        guard let url = URL(string: base)?.appendingPathComponent("tts") else {
            throw JarvisAPIError.badURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("audio/wav", forHTTPHeaderField: "Accept")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: ["text": text])

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            try validate(response: response, data: data)
            guard !data.isEmpty else { throw JarvisAPIError.badResponse }
            return data
        } catch {
            await JarvisEndpointResolver.shared.invalidate(base)
            throw error
        }
    }

    func event(_ name: String) async throws -> JarvisAPIResponse {
        try await post(path: "event", body: ["event": name])
    }

    func startMeeting(title: String = "") async throws -> MeetingStartResponse {
        let (data, response) = try await postData(path: "meeting/start", body: ["title": title])
        try validate(response: response, data: data)
        return try JSONDecoder().decode(MeetingStartResponse.self, from: data)
    }

    func appendMeetingTranscript(meetingID: Int, text: String) async throws {
        let (data, response) = try await postData(path: "meeting/transcript", body: [
            "meeting_id": meetingID,
            "text": text,
        ])
        try validate(response: response, data: data)
    }

    func finishMeeting(meetingID: Int) async throws -> JarvisAPIResponse {
        let (data, response) = try await postData(path: "meeting/finish", body: ["meeting_id": meetingID])
        try validate(response: response, data: data)
        let decoded = try JSONDecoder().decode(JarvisAPIResponse.self, from: data)
        return JarvisAPIResponse(ok: decoded.ok, message: Self.collapseRepeatedSir(decoded.message))
    }

    func emailAllowlist() async throws -> [String] {
        let (data, response) = try await get(path: "settings/email-allowlist", timeout: 10)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(EmailAllowlistResponse.self, from: data).addresses
    }

    func setEmailAllowlist(_ addresses: [String]) async throws -> [String] {
        let base = try await activeBaseURL()
        guard let url = URL(string: base)?.appendingPathComponent("settings/email-allowlist") else {
            throw JarvisAPIError.badURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: ["addresses": addresses])

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            try validate(response: response, data: data)
            return try JSONDecoder().decode(EmailAllowlistResponse.self, from: data).addresses
        } catch {
            await JarvisEndpointResolver.shared.invalidate(base)
            throw error
        }
    }

    private func get(path: String, timeout: TimeInterval) async throws -> (Data, URLResponse) {
        let base = try await activeBaseURL()
        guard let url = URL(string: base)?.appendingPathComponent(path) else { throw JarvisAPIError.badURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        addAuthorization(to: &request)
        do {
            return try await URLSession.shared.data(for: request)
        } catch {
            await JarvisEndpointResolver.shared.invalidate(base)
            throw error
        }
    }

    private func post(path: String, body: [String: String]) async throws -> JarvisAPIResponse {
        let (data, response) = try await postData(path: path, body: body)
        try validate(response: response, data: data)
        let decoded = try JSONDecoder().decode(JarvisAPIResponse.self, from: data)
        return JarvisAPIResponse(ok: decoded.ok, message: Self.collapseRepeatedSir(decoded.message))
    }

    private func postData(path: String, body: [String: Any]) async throws -> (Data, URLResponse) {
        let base = try await activeBaseURL()
        guard let url = URL(string: base)?.appendingPathComponent(path) else { throw JarvisAPIError.badURL }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        do {
            return try await URLSession.shared.data(for: request)
        } catch {
            await JarvisEndpointResolver.shared.invalidate(base)
            throw error
        }
    }

    private func addAuthorization(to request: inout URLRequest) {
        if !apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        }
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw JarvisAPIError.badResponse }
        guard (200..<300).contains(http.statusCode) else {
            if let detail = try? JSONDecoder().decode(APIErrorDetail.self, from: data).detail {
                throw JarvisAPIError.server(detail)
            }
            if let jarvis = try? JSONDecoder().decode(JarvisAPIResponse.self, from: data) {
                throw JarvisAPIError.server(Self.collapseRepeatedSir(jarvis.message))
            }
            throw JarvisAPIError.server("Jarvis returned HTTP \(http.statusCode).")
        }
    }
}
