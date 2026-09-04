import Foundation

struct JarvisAPIResponse: Decodable {
    let ok: Bool
    let message: String
}

struct EmailAllowlistResponse: Decodable {
    let addresses: [String]
}

private struct APIErrorDetail: Decodable {
    let detail: String
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
        let (_, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw JarvisAPIError.badResponse }
        return (200..<300).contains(http.statusCode)
    }

    func command(_ text: String) async throws -> JarvisAPIResponse {
        try await post(path: "command", body: ["text": text, "session_id": sessionID])
    }

    func event(_ name: String) async throws -> JarvisAPIResponse {
        try await post(path: "event", body: ["event": name])
    }

    func emailAllowlist() async throws -> [String] {
        guard let url = URL(string: baseURL)?.appendingPathComponent("settings/email-allowlist") else {
            throw JarvisAPIError.badURL
        }
        var request = URLRequest(url: url)
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
