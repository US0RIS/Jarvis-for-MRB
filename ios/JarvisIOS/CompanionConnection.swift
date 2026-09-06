import CryptoKit
import Foundation

@MainActor
final class CompanionConnection: ObservableObject {
    @Published private(set) var status = "Disconnected"
    @Published private(set) var activeServerURL = ""

    var onEvent: (([String: Any]) -> Void)?

    private static weak var activeConnection: CompanionConnection?
    private static var lastWorldSnapshotData: Data?
    private static var everConnected = false
    private let session = URLSession(configuration: .default)
    private var socket: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?

    var isConnected: Bool { socket != nil }

    func connect(client: JarvisAPIClient) async throws {
        disconnect()
        let base = try await client.activeBaseURL()
        WorldSyncTelemetry.shared.connectionAttempt(endpoint: base)
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
        let wasReconnect = Self.everConnected
        socket = task
        Self.activeConnection = self
        Self.lastWorldSnapshotData = nil
        activeServerURL = base
        status = "Connecting"
        task.resume()

        receiveTask = Task { [weak self] in
            guard let self else { return }
            await self.receiveLoop(task)
        }

        do {
            try await sendJSON(["type": "ping"])
            status = "Connected"
            Self.everConnected = true
            WorldSyncTelemetry.shared.connected(endpoint: base, wasReconnect: wasReconnect)
        } catch {
            WorldSyncTelemetry.shared.disconnected(error: error.localizedDescription)
            throw error
        }
    }

    func disconnect() {
        let wasConnected = socket != nil
        receiveTask?.cancel()
        receiveTask = nil
        socket?.cancel(with: .goingAway, reason: nil)
        socket = nil
        if Self.activeConnection === self {
            Self.activeConnection = nil
            Self.lastWorldSnapshotData = nil
        }
        status = "Disconnected"
        if wasConnected {
            WorldSyncTelemetry.shared.disconnected()
        }
    }

    func sendFrame(_ jpeg: Data) async throws {
        guard let socket else { throw URLError(.notConnectedToInternet) }
        try await socket.send(.data(jpeg))
    }

    func sendEnvironment(_ state: [String: Any]) async throws {
        try await sendJSON(["type": "environment", "state": state])
    }

    /// Publish an explicit metadata-only snapshot from iPhone-local Jarvis stores
    /// over the already-authenticated persistent companion socket. This deliberately
    /// reuses the existing connection rather than creating a second socket whose
    /// lifecycle could make the backend think the phone disconnected.
    static func sendWorldSnapshot(_ snapshot: [String: Any]) async throws {
        WorldSyncTelemetry.shared.snapshotAttempt()
        guard let activeConnection, activeConnection.isConnected else {
            let error = URLError(.notConnectedToInternet)
            WorldSyncTelemetry.shared.snapshotFailed(error.localizedDescription)
            throw error
        }

        // `captured_at` is useful to a caller as diagnostics but it must not turn an
        // unchanged semantic snapshot into network traffic every five seconds.
        var canonical = snapshot
        canonical.removeValue(forKey: "captured_at")

        if let violation = privacyViolation(in: canonical) {
            let detail = "World snapshot blocked: forbidden privacy field \(violation)."
            WorldSyncTelemetry.shared.privacyViolation(detail)
            throw JarvisAPIError.server(detail)
        }

        let data = try JSONSerialization.data(withJSONObject: canonical, options: [.sortedKeys])
        if data == lastWorldSnapshotData {
            WorldSyncTelemetry.shared.semanticNoop()
            return
        }

        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        let collectionNames = ["people", "goals", "waiting", "inventory", "reminders", "encounters", "events", "receipts"]
        var counts: [String: Int] = [:]
        for key in collectionNames {
            if let rows = canonical[key] as? [Any] { counts[key] = rows.count }
        }
        let schemaVersion: Int
        if let value = canonical["schema_version"] as? Int {
            schemaVersion = value
        } else if let value = canonical["schema_version"] as? NSNumber {
            schemaVersion = value.intValue
        } else {
            schemaVersion = 0
        }

        do {
            try await activeConnection.sendEnvironment(["world_snapshot": canonical])
            lastWorldSnapshotData = data
            WorldSyncTelemetry.shared.snapshotSent(
                hash: digest,
                bytes: data.count,
                counts: counts,
                schemaVersion: schemaVersion
            )
        } catch {
            WorldSyncTelemetry.shared.snapshotFailed(error.localizedDescription)
            throw error
        }
    }

    private static func privacyViolation(in value: Any, path: String = "snapshot") -> String? {
        let forbiddenExact: Set<String> = [
            "feature_print", "feature_prints", "biometric", "biometrics",
            "raw_camera", "raw_camera_frame", "raw_camera_frames", "camera_frame", "camera_frames",
            "raw_audio", "rolling_audio", "audio_buffer", "microphone_buffer",
            "clipboard", "clipboard_text", "privacy_zone", "privacy_zones", "privacy_zone_coordinates",
            "incident_media", "enrollment_image", "enrollment_images",
        ]

        if let dictionary = value as? [String: Any] {
            for (key, child) in dictionary {
                let normalized = key.lowercased().replacingOccurrences(of: "-", with: "_")
                if forbiddenExact.contains(normalized) {
                    return "\(path).\(key)"
                }
                if let violation = privacyViolation(in: child, path: "\(path).\(key)") {
                    return violation
                }
            }
        } else if let array = value as? [Any] {
            for (index, child) in array.enumerated() {
                if let violation = privacyViolation(in: child, path: "\(path)[\(index)]") {
                    return violation
                }
            }
        }
        return nil
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
                    if Self.activeConnection === self {
                        Self.activeConnection = nil
                        Self.lastWorldSnapshotData = nil
                    }
                    WorldSyncTelemetry.shared.disconnected(error: error.localizedDescription)
                }
                return
            }
        }
    }
}
