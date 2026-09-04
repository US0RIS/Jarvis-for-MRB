import Foundation

struct JarvisAPIResponse: Decodable {
    let ok: Bool
    let message: String
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

    func health() async throws -> Bool {
        guard let url = URL(string: baseURL)?.appendingPathComponent("health") else { throw JarvisAPIError.badURL }
        let (_, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw JarvisAPIError.badResponse }
        return (200..<300).contains(http.statusCode)
    }

    func command(_ text: String) async throws -> JarvisAPIResponse {
        try await post(path: "command", body: ["text": text])
    }

    func event(_ name: String) async throws -> JarvisAPIResponse {
        try await post(path: "event", body: ["event": name])
    }

    private func post(path: String, body: [String: String]) async throws -> JarvisAPIResponse {
        guard let url = URL(string: baseURL)?.appendingPathComponent(path) else { throw JarvisAPIError.badURL }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw JarvisAPIError.badResponse }
        let decoded = try JSONDecoder().decode(JarvisAPIResponse.self, from: data)
        guard (200..<300).contains(http.statusCode) else { throw JarvisAPIError.server(decoded.message) }
        return decoded
    }
}
