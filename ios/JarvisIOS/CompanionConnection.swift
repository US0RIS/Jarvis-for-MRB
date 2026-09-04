import Foundation

@MainActor
final class CompanionConnection: ObservableObject {
    @Published private(set) var status = "Disconnected"
    @Published private(set) var activeServerURL = ""

    var onEvent: (([String: Any]) -> Void)?

    private let session = URLSession(configuration: .default)
    private var socket: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?

    var isConnected: Bool { socket != nil }

    func connect(client: JarvisAPIClient) async throws {
        disconnect()
        let base = try await client.activeBaseURL()
        guard var components = URLComponents(string: base) else { throw JarvisAPIError.badURL }
        if components.scheme == "https" {
            components.scheme = "wss"
        } else if components.scheme == "http" {
            components.scheme = "ws"
        }
        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + ([basePath, "ws/companion"].filter { !$0.isEmpty }.joined(separator: "/"))
        guard let url = components.url else { throw JarvisAPIError.badURL }

        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        if !client.apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(client.apiToken)", forHTTPHeaderField: "Authorization")
        }

        let task = session.webSocketTask(with: request)
        socket = task
        activeServerURL = base
        status = "Connecting"
        task.resume()

        receiveTask = Task { [weak self] in
            guard let self else { return }
            await self.receiveLoop(task)
        }

        try await sendJSON(["type": "ping"])
        status = "Connected"
    }

    func disconnect() {
        receiveTask?.cancel()
        receiveTask = nil
        socket?.cancel(with: .goingAway, reason: nil)
        socket = nil
        status = "Disconnected"
    }

    func sendFrame(_ jpeg: Data) async throws {
        guard let socket else { throw URLError(.notConnectedToInternet) }
        try await socket.send(.data(jpeg))
    }

    func sendEnvironment(_ state: [String: Any]) async throws {
        try await sendJSON(["type": "environment", "state": state])
    }

    private func sendJSON(_ object: [String: Any]) async throws {
        guard let socket else { throw URLError(.notConnectedToInternet) }
        let data = try JSONSerialization.data(withJSONObject: object)
        guard let text = String(data: data, encoding: .utf8) else { throw JarvisAPIError.badResponse }
        try await socket.send(.string(text))
    }

    private func receiveLoop(_ task: URLSessionWebSocketTask) async {
        while !Task.isCancelled {
            do {
                let message = try await task.receive()
                switch message {
                case .string(let text):
                    guard let data = text.data(using: .utf8),
                          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                        continue
                    }
                    onEvent?(object)
                case .data:
                    continue
                @unknown default:
                    continue
                }
            } catch {
                if !Task.isCancelled {
                    status = "Disconnected"
                    socket = nil
                }
                return
            }
        }
    }
}
