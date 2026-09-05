import Foundation
import UIKit

@MainActor
final class PersistentPresenceController: ObservableObject {
    @Published private(set) var companionStatus = "Stopped"
    @Published private(set) var activeServerURL = ""
    @Published private(set) var visionStatus = "Off"
    @Published private(set) var lastVisionScene = ""
    @Published private(set) var lastProactiveMessage = ""

    private unowned let appModel: JarvisAppModel
    private let companion: CompanionConnection
    private let cuePlayer: AmbientCuePlayer
    private var reconnectTask: Task<Void, Never>?
    private var visionTask: Task<Void, Never>?
    private var started = false
    private var locationLabel = "unknown"
    private var announcing = false
    private var pendingAnnouncements: [(String, String)] = []

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
        companion = CompanionConnection()
        cuePlayer = AmbientCuePlayer(audioRouteManager: appModel.audioRouteManager)

        companion.onEvent = { [weak self] event in
            Task { @MainActor in
                await self?.handleCompanionEvent(event)
            }
        }

        appModel.geofenceManager.onHomeStateChanged = { [weak self] isHome in
            Task { @MainActor in
                guard let self else { return }
                self.locationLabel = isHome ? "home" : "away"
                await self.sendEnvironmentState()
            }
        }
    }

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    func start() async {
        guard !started else { return }
        started = true
        companionStatus = "Connecting"

        reconnectTask = Task { [weak self] in
            guard let self else { return }
            await self.reconnectLoop()
        }
        visionTask = Task { [weak self] in
            guard let self else { return }
            await self.visionLoop()
        }
    }

    func stop() {
        started = false
        reconnectTask?.cancel()
        visionTask?.cancel()
        reconnectTask = nil
        visionTask = nil
        cuePlayer.stopThinking()
        companion.disconnect()
        companionStatus = "Stopped"
        visionStatus = "Off"
    }

    private func reconnectLoop() async {
        while !Task.isCancelled && started {
            if !companion.isConnected {
                do {
                    try await companion.connect(client: client)
                    activeServerURL = companion.activeServerURL
                    companionStatus = activeServerURL == appModel.settings.baseURL
                        ? "Connected over LAN"
                        : "Connected over Tailscale"
                    await sendEnvironmentState()
                } catch {
                    companionStatus = "Waiting for Jarvis server"
                    activeServerURL = ""
                }
            } else {
                activeServerURL = companion.activeServerURL
                companionStatus = activeServerURL == appModel.settings.baseURL
                    ? "Connected over LAN"
                    : "Connected over Tailscale"
                await sendEnvironmentState()
            }
            try? await Task.sleep(for: .seconds(companion.isConnected ? 10 : 2))
        }
    }

    private func visionLoop() async {
        while !Task.isCancelled && started {
            guard appModel.settings.passiveVisionEnabled else {
                visionStatus = "Off"
                try? await Task.sleep(for: .seconds(1))
                continue
            }

            guard companion.isConnected else {
                visionStatus = "Waiting for server"
                try? await Task.sleep(for: .seconds(1))
                continue
            }

            if appModel.metaGlasses.streamState == "Stopped",
               appModel.metaGlasses.isRegistered,
               appModel.metaGlasses.hasEligibleDevice {
                visionStatus = "Starting glasses camera"
                await appModel.metaGlasses.startStream()
            }

            guard appModel.metaGlasses.streamState != "Stopped" else {
                visionStatus = "Waiting for glasses camera"
                try? await Task.sleep(for: .seconds(1))
                continue
            }

            if let frame = appModel.metaGlasses.currentFrame,
               let jpeg = Self.sampledJPEG(from: frame) {
                do {
                    try await companion.sendFrame(jpeg)
                    if visionStatus == "Starting glasses camera" || visionStatus == "Waiting for frame" {
                        visionStatus = "Frame sent to PC"
                    }
                } catch {
                    visionStatus = "Reconnect pending"
                    companion.disconnect()
                }
            } else {
                visionStatus = "Waiting for frame"
            }
            try? await Task.sleep(for: .seconds(1))
        }
    }

    private func sendEnvironmentState() async {
        guard companion.isConnected else { return }
        let rayBanState: String
        if appModel.metaGlasses.hasEligibleDevice {
            rayBanState = appModel.metaGlasses.streamState == "Stopped" ? "connected" : "streaming"
        } else if appModel.metaGlasses.isRegistered {
            rayBanState = "registered_waiting"
        } else {
            rayBanState = "unavailable"
        }

        do {
            try await companion.sendEnvironment([
                "location": locationLabel,
                "project_focus": appModel.settings.projectFocus,
                "devices": [
                    "ray_ban_meta": rayBanState,
                    "passive_vision": appModel.settings.passiveVisionEnabled,
                    "companion_endpoint": companion.activeServerURL,
                ],
            ])
        } catch {
            companion.disconnect()
        }
    }

    private func handleCompanionEvent(_ event: [String: Any]) async {
        let type = String(describing: event["type"] ?? "")
        let cue = String(describing: event["cue"] ?? "attention")
        let message = String(describing: event["message"] ?? "")

        if type == "thinking_start" {
            if appModel.settings.ambientCuesEnabled {
                cuePlayer.startThinking(preferBluetooth: appModel.settings.preferBluetoothAudio)
            }
            return
        }
        if type == "thinking_stop" {
            cuePlayer.stopThinking()
            return
        }

        // Vision-state telemetry can arrive multiple times per analysis. Never play
        // an ambient sound for telemetry; cues are reserved for actual attention,
        // completion, and error events.
        if appModel.settings.ambientCuesEnabled,
           ["cue", "proactive_alert", "background_complete", "background_failed"].contains(type) {
            cuePlayer.play(cue, preferBluetooth: appModel.settings.preferBluetoothAudio)
        }

        switch type {
        case "vision_state":
            let state = String(describing: event["state"] ?? "")
            switch state {
            case "received":
                visionStatus = "Frame received by PC"
            case "analyzing":
                visionStatus = "Analyzing on PC…"
            case "ready":
                if let scene = event["scene"] as? String, !scene.isEmpty {
                    lastVisionScene = scene
                }
                if let milliseconds = event["analysis_ms"] as? Int {
                    visionStatus = "Active • \(milliseconds) ms analysis"
                } else if let number = event["analysis_ms"] as? NSNumber {
                    visionStatus = "Active • \(number.intValue) ms analysis"
                } else {
                    visionStatus = "Active"
                }
            case "error":
                visionStatus = message.isEmpty ? "Vision model error" : "Vision error: \(message)"
            default:
                break
            }

        case "proactive_alert", "background_complete", "background_failed":
            guard !message.isEmpty else { return }
            lastProactiveMessage = message
            if appModel.settings.proactiveAnnouncements {
                pendingAnnouncements.append((message, cue))
                await drainAnnouncements()
            }
        default:
            break
        }
    }

    private func drainAnnouncements() async {
        guard !announcing else { return }
        announcing = true
        defer { announcing = false }

        while !pendingAnnouncements.isEmpty {
            if appModel.isSending || appModel.speechSynthesizer.isSpeaking {
                try? await Task.sleep(for: .milliseconds(500))
                continue
            }
            if appModel.handsFreeEnabled,
               !appModel.speechRecognizer.transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                try? await Task.sleep(for: .milliseconds(450))
                continue
            }

            let (message, _) = pendingAnnouncements.removeFirst()
            let wasHandsFree = appModel.handsFreeEnabled
            if wasHandsFree {
                appModel.stopWakeWordMode()
            } else if appModel.isListening || appModel.speechRecognizer.isActive {
                _ = appModel.speechRecognizer.stopListening()
                appModel.isListening = false
            }

            await speakProactive(message)
            appModel.lastResponse = message

            if wasHandsFree {
                try? await Task.sleep(for: .milliseconds(160))
                await appModel.startWakeWordMode()
            }
        }
    }

    private func speakProactive(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let spoken: String
        if trimmed.range(of: "sir", options: [.caseInsensitive, .diacriticInsensitive]) != nil {
            spoken = trimmed
        } else {
            spoken = "Sir, " + trimmed.prefix(1).lowercased() + String(trimmed.dropFirst())
        }

        do {
            let audio = try await client.synthesizeSpeech(spoken)
            try await appModel.speechSynthesizer.speakRemoteAudio(
                audio,
                text: spoken,
                preferBluetooth: appModel.settings.preferBluetoothAudio
            )
        } catch {
            await appModel.speechSynthesizer.speak(
                spoken,
                preferBluetooth: appModel.settings.preferBluetoothAudio
            )
        }
    }

    private static func sampledJPEG(from image: UIImage) -> Data? {
        let size = image.size
        guard size.width > 0, size.height > 0 else { return nil }
        let maxDimension: CGFloat = 512
        let scale = min(1, maxDimension / max(size.width, size.height))
        let target = CGSize(width: max(1, size.width * scale), height: max(1, size.height * scale))

        let renderer = UIGraphicsImageRenderer(size: target)
        let resized = renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
        return resized.jpegData(compressionQuality: 0.35)
    }
}
