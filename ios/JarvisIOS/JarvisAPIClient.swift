import Foundation

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
        seconds: Int, scope: String = "personal"
    ) async throws -> ExternalWatchSummary {
        let (data, response) = try await postData(
            path: "external/watch/create",
            body: [
                "scope": scope, "kind": kind, "label": label,
                "config": config, "interval_seconds": seconds,
                "expires_hours": 24,
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
            explanation = "I'm sorry, sir. The Jarvis backend completed that request but returned no answer."
        } else if backendOK == false {
            explanation = "I'm sorry, sir. The Jarvis backend failed that request before returning an answer. I did not retry it automatically because doing so could duplicate an action."
        } else {
            explanation = "I'm sorry, sir. The Jarvis backend returned no answer. I did not retry that request automatically because doing so could duplicate an action."
        }
        continuation.yield(.delta(explanation))
        continuation.yield(.done(ok: false))
    }

    private static func normalizeStreamText(_ raw: String, previousTail: String) -> String {
        var value = collapseRepeatedSir(raw)

        // The backend intentionally emits its transport-level “Sir, ” as one
        // streamed delta. If the model itself begins the next delta with another
        // “sir”, suppress that second address before the frontend ever displays or
        // speaks it. This makes the invariant hold even across packet boundaries.
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
