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

private struct APIErrorDetail: Decodable {
    let detail: String
}

private struct JarvisStreamPacket: Decodable {
    let type: String
    let text: String?
    let ok: Bool?
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
            // A healthy home-LAN Jarvis responds essentially immediately. Fail over
            // quickly when that address is unreachable, then cache the working path
            // for 30 seconds so voice turns do not pay a health-probe tax repeatedly.
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

    func command(_ text: String) async throws -> JarvisAPIResponse {
        try await post(path: "command", body: ["text": text, "session_id": sessionID])
    }

    func streamCommand(_ text: String) -> AsyncThrowingStream<String, Error> {
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

                    for try await line in bytes.lines {
                        guard !line.isEmpty, let data = line.data(using: .utf8) else { continue }
                        let packet = try JSONDecoder().decode(JarvisStreamPacket.self, from: data)
                        switch packet.type {
                        case "delta":
                            if let text = packet.text, !text.isEmpty {
                                continuation.yield(text)
                            }
                        case "done":
                            continuation.finish()
                            return
                        default:
                            continue
                        }
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
        let base = try await activeBaseURL()
        guard let url = URL(string: base)?.appendingPathComponent(path) else { throw JarvisAPIError.badURL }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            try validate(response: response, data: data)
            return try JSONDecoder().decode(JarvisAPIResponse.self, from: data)
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
                throw JarvisAPIError.server(jarvis.message)
            }
            throw JarvisAPIError.server("Jarvis returned HTTP \(http.statusCode).")
        }
    }
}
