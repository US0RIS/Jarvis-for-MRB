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

private struct APIErrorDetail: Decodable {
    let detail: String
}

private struct JarvisStreamPacket: Decodable {
    let type: String
    let text: String?
    let ok: Bool?
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
    let apiToken: String
    let sessionID: String

    func health() async throws -> Bool {
        guard let url = URL(string: baseURL)?.appendingPathComponent("health") else { throw JarvisAPIError.badURL }
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw JarvisAPIError.badResponse }
        return (200..<300).contains(http.statusCode)
    }

    func command(_ text: String) async throws -> JarvisAPIResponse {
        try await post(path: "command", body: ["text": text, "session_id": sessionID])
    }

    /// Streams response text as soon as the backend has made its tool decision.
    /// The wire format is newline-delimited JSON, but callers only see text deltas.
    func streamCommand(_ text: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    guard let url = URL(string: baseURL)?.appendingPathComponent("command/stream") else {
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
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    func ttsStatus() async throws -> String {
        guard let url = URL(string: baseURL)?.appendingPathComponent("tts/status") else {
            throw JarvisAPIError.badURL
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        addAuthorization(to: &request)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(TTSStatusResponse.self, from: data).status
    }

    func synthesizeSpeech(_ text: String) async throws -> Data {
        guard let url = URL(string: baseURL)?.appendingPathComponent("tts") else {
            throw JarvisAPIError.badURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("audio/wav", forHTTPHeaderField: "Accept")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: ["text": text])

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        guard !data.isEmpty else { throw JarvisAPIError.badResponse }
        return data
    }

    func event(_ name: String) async throws -> JarvisAPIResponse {
        try await post(path: "event", body: ["event": name])
    }

    func emailAllowlist() async throws -> [String] {
        guard let url = URL(string: baseURL)?.appendingPathComponent("settings/email-allowlist") else {
            throw JarvisAPIError.badURL
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 10
        addAuthorization(to: &request)

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(EmailAllowlistResponse.self, from: data).addresses
    }

    func setEmailAllowlist(_ addresses: [String]) async throws -> [String] {
        guard let url = URL(string: baseURL)?.appendingPathComponent("settings/email-allowlist") else {
            throw JarvisAPIError.badURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: ["addresses": addresses])

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(EmailAllowlistResponse.self, from: data).addresses
    }

    private func post(path: String, body: [String: String]) async throws -> JarvisAPIResponse {
        guard let url = URL(string: baseURL)?.appendingPathComponent(path) else { throw JarvisAPIError.badURL }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        return try JSONDecoder().decode(JarvisAPIResponse.self, from: data)
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
