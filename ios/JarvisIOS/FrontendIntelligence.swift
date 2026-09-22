import CoreLocation
import CoreMotion
import Foundation
import ImageIO
import SwiftUI
import UIKit
import Vision

struct FrontendConversationTurn: Identifiable, Codable, Equatable {
    let id: UUID
    let role: String
    let text: String
    let timestamp: Date
    let model: String?

    init(id: UUID = UUID(), role: String, text: String, timestamp: Date = Date(), model: String? = nil) {
        self.id = id
        self.role = role
        self.text = text
        self.timestamp = timestamp
        self.model = model
    }
}

struct JarvisLatencySnapshot: Equatable {
    var model = "—"
    var routeReason = ""
    var firstResponseMS: Int?
    var firstAudioReadyMS: Int?
    var totalTurnMS: Int?

    var compactDescription: String {
        var parts: [String] = []
        if model != "—" { parts.append(model) }
        if let firstResponseMS { parts.append("first response \(firstResponseMS) ms") }
        if let firstAudioReadyMS { parts.append("first audio \(firstAudioReadyMS) ms") }
        if let totalTurnMS { parts.append("turn \(totalTurnMS) ms") }
        return parts.isEmpty ? "No timing yet" : parts.joined(separator: " • ")
    }
}

enum FrontendConversationStore {
    private static let key = "jarvis.frontendConversationHistory"

    static func load() -> [FrontendConversationTurn] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let turns = try? JSONDecoder().decode([FrontendConversationTurn].self, from: data) else {
            return []
        }
        return Array(turns.suffix(120))
    }

    static func save(_ turns: [FrontendConversationTurn]) {
        let bounded = Array(turns.suffix(120))
        if let data = try? JSONEncoder().encode(bounded) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    static func clear() {
        UserDefaults.standard.removeObject(forKey: key)
    }
}

struct QueuedCommand: Identifiable, Codable, Equatable {
    let id: UUID
    let text: String
    let createdAt: Date

    init(id: UUID = UUID(), text: String, createdAt: Date = Date()) {
        self.id = id
        self.text = text
        self.createdAt = createdAt
    }
}

@MainActor
final class OfflineCommandQueueStore: ObservableObject {
    @Published private(set) var items: [QueuedCommand] = []
    private let key = "jarvis.offlineCommandQueue"

    init() {
        if let data = UserDefaults.standard.data(forKey: key),
           let saved = try? JSONDecoder().decode([QueuedCommand].self, from: data) {
            items = Array(saved.suffix(30))
        }
    }

    func enqueue(_ text: String) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        if let last = items.last, last.text == cleaned, Date().timeIntervalSince(last.createdAt) < 10 { return }
        items.append(QueuedCommand(text: cleaned))
        if items.count > 30 { items.removeFirst(items.count - 30) }
        persist()
    }

    func remove(_ id: UUID) {
        items.removeAll { $0.id == id }
        persist()
    }

    func clear() {
        items.removeAll()
        persist()
    }

    private func persist() {
        if let data = try? JSONEncoder().encode(items) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}

struct LocalVisualSnapshot: Identifiable, Equatable {
    let id = UUID()
    let capturedAt: Date
    let jpeg: Data
}

struct LocalPerceptionResult: Equatable {
    let text: String
    let barcodes: [String]
    let faceCount: Int
    let humanCount: Int
    let rectangleCount: Int
    let hasSalientRegion: Bool

    var summary: String {
        var parts: [String] = []
        if !text.isEmpty { parts.append("text") }
        if !barcodes.isEmpty { parts.append("\(barcodes.count) barcode/QR") }
        if humanCount > 0 { parts.append("\(humanCount) person\(humanCount == 1 ? "" : "s")") }
        if faceCount > 0 { parts.append("\(faceCount) face\(faceCount == 1 ? "" : "s")") }
        if rectangleCount > 0 { parts.append("\(rectangleCount) rectangle\(rectangleCount == 1 ? "" : "s")") }
        if hasSalientRegion { parts.append("salient region") }
        return parts.isEmpty ? "No fast-perception features detected" : parts.joined(separator: " • ")
    }
}

struct FrontendProactiveItem: Identifiable, Equatable {
    let id = UUID()
    let timestamp: Date
    let message: String
}

@MainActor
final class LocalContextSensorManager: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published private(set) var activity = "Off"
    @Published private(set) var speedMPS: Double?
    @Published private(set) var courseDegrees: Double?
    @Published private(set) var altitudeMeters: Double?
    @Published private(set) var coordinate: CLLocationCoordinate2D?
    @Published private(set) var lastUpdated: Date?
    @Published private(set) var lastLocationAt: Date?
    @Published private(set) var lastMotionAt: Date?

    private let motion = CMMotionActivityManager()
    private let location = CLLocationManager()
    private var started = false

    override init() {
        super.init()
        location.delegate = self
        location.desiredAccuracy = kCLLocationAccuracyHundredMeters
        location.distanceFilter = 20
        location.headingFilter = 10
    }

    func setEnabled(_ enabled: Bool) {
        if enabled { start() } else { stop() }
    }

    private func start() {
        guard !started else { return }
        started = true
        if CMMotionActivityManager.isActivityAvailable() {
            motion.startActivityUpdates(to: OperationQueue.main) { [weak self] sample in
                guard let sample else { return }
                Task { @MainActor in
                    guard let self else { return }
                    if sample.automotive { self.activity = "Driving" }
                    else if sample.cycling { self.activity = "Cycling" }
                    else if sample.running { self.activity = "Running" }
                    else if sample.walking { self.activity = "Walking" }
                    else if sample.stationary { self.activity = "Stationary" }
                    else { self.activity = "Unknown" }
                    self.lastMotionAt = Date()
                    self.lastUpdated = Date()
                }
            }
        } else {
            activity = "Motion unavailable"
        }

        if location.authorizationStatus == .notDetermined {
            location.requestWhenInUseAuthorization()
        }
        if location.authorizationStatus == .authorizedAlways || location.authorizationStatus == .authorizedWhenInUse {
            location.startUpdatingLocation()
            if CLLocationManager.headingAvailable() { location.startUpdatingHeading() }
        }
    }

    private func stop() {
        guard started else { return }
        started = false
        motion.stopActivityUpdates()
        location.stopUpdatingLocation()
        location.stopUpdatingHeading()
        activity = "Off"
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            if self.started,
               manager.authorizationStatus == .authorizedAlways || manager.authorizationStatus == .authorizedWhenInUse {
                manager.startUpdatingLocation()
                if CLLocationManager.headingAvailable() { manager.startUpdatingHeading() }
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let current = locations.last else { return }
        Task { @MainActor in
            coordinate = current.coordinate
            lastLocationAt = current.timestamp
            altitudeMeters = current.verticalAccuracy >= 0 ? current.altitude : nil
            speedMPS = current.speed >= 0 ? current.speed : nil
            if current.course >= 0 { courseDegrees = current.course }
            lastUpdated = Date()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        Task { @MainActor in
            courseDegrees = newHeading.trueHeading >= 0 ? newHeading.trueHeading : newHeading.magneticHeading
            lastUpdated = Date()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            if activity == "Off" { return }
            activity = "Location unavailable"
        }
    }
}

@MainActor
final class FrontendIntelligenceController: ObservableObject {
    @Published private(set) var visualSnapshots: [LocalVisualSnapshot] = []
    @Published private(set) var localOCRText = ""
    @Published private(set) var barcodeValues: [String] = []
    @Published private(set) var perceptionSummary = "Not scanned"
    @Published private(set) var perceptionStatus = "Idle"
    @Published private(set) var lastFrameAt: Date?
    @Published private(set) var estimatedCaptureFPS = 0.0
    @Published private(set) var lastJPEGBytes = 0
    @Published private(set) var primaryLatencyMS: Int?
    @Published private(set) var fallbackLatencyMS: Int?
    @Published private(set) var connectivityStatus = "Not probed"
    @Published private(set) var proactiveInbox: [FrontendProactiveItem] = []
    @Published private(set) var lastLocalAction = ""

    let offlineQueue = OfflineCommandQueueStore()
    let sensors = LocalContextSensorManager()

    private unowned let appModel: JarvisAppModel
    private weak var persistentPresence: PersistentPresenceController?
    private weak var meetingCapture: MeetingCaptureController?
    var isMeetingActive: Bool { meetingCapture?.isActive ?? false }
    private var loopTask: Task<Void, Never>?
    private var started = false
    private var lastSnapshotAt = Date.distantPast
    private var lastPerceptionAt = Date.distantPast
    private var perceptionBusy = false
    private var lastProbeAt = Date.distantPast
    private var lastProactiveSeen = ""

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
    }

    func attach(persistentPresence: PersistentPresenceController, meetingCapture: MeetingCaptureController) {
        self.persistentPresence = persistentPresence
        self.meetingCapture = meetingCapture
    }

    func start() async {
        guard !started else { return }
        started = true
        appModel.frontendCommandHandler = { [weak self] command in
            guard let self else { return nil }
            return await self.handleLocalCommand(command)
        }
        appModel.offlineQueueHandler = { [weak self] command in
            self?.offlineQueue.enqueue(command)
        }
        sensors.setEnabled(appModel.settings.localSensorContextEnabled)

        loopTask = Task { [weak self] in
            guard let self else { return }
            await self.runLoop()
        }
    }

    func stop() {
        started = false
        loopTask?.cancel()
        loopTask = nil
        sensors.setEnabled(false)
        AmbientSoundCapture.shared.stop()
    }

    private func runLoop() async {
        while !Task.isCancelled && started {
            sensors.setEnabled(appModel.settings.localSensorContextEnabled)
            // Primary camera-free perception. Reuse speech/meeting capture when
            // it owns the mic; only run a separate SoundAnalysis-only tap when
            // idle, in foreground, and both user opt-ins are still enabled.
            let ambientAllowed = appModel.settings.sensorOpportunitiesEnabled
                && appModel.settings.soundRecognitionEnabled
                && UIApplication.shared.applicationState == .active
                && !appModel.speechRecognizer.isActive
                && !appModel.speechSynthesizer.isSpeaking
                && !appModel.isSending
                && !(meetingCapture?.isActive ?? false)
            await AmbientSoundCapture.shared.refresh(
                enabled: ambientAllowed,
                audioRouteManager: appModel.audioRouteManager,
                preferBluetooth: appModel.settings.preferBluetoothAudio
            )
            if ambientAllowed {
                await persistentPresence?.observeAmbientSound()
            } else {
                persistentPresence?.clearAmbientOpportunityEvidence()
            }
            await captureLatestFrameIfNeeded()

            if appModel.settings.localFastPerceptionEnabled,
               Date().timeIntervalSince(lastPerceptionAt) >= 2.0,
               !perceptionBusy,
               visualSnapshots.last != nil {
                await scanLatestFrame(copyText: false, announce: false)
            }

            if appModel.settings.frontendDiagnosticsEnabled,
               Date().timeIntervalSince(lastProbeAt) >= 10 {
                lastProbeAt = Date()
                await probeConnections()
            }

            if let message = persistentPresence?.lastProactiveMessage,
               !message.isEmpty,
               message != lastProactiveSeen {
                lastProactiveSeen = message
                proactiveInbox.append(FrontendProactiveItem(timestamp: Date(), message: message))
                if proactiveInbox.count > 50 { proactiveInbox.removeFirst(proactiveInbox.count - 50) }
            }

            await processPendingShortcutAction()
            try? await Task.sleep(for: .milliseconds(350))
        }
    }

    private func captureLatestFrameIfNeeded() async {
        guard appModel.settings.localVisualHistoryEnabled,
              Date().timeIntervalSince(lastSnapshotAt) >= 0.5,
              let image = appModel.metaGlasses.currentFrame else {
            pruneVisualCache()
            return
        }
        lastSnapshotAt = Date()
        guard let jpeg = Self.makeJPEG(image, maxDimension: 640, quality: 0.30) else { return }
        let now = Date()
        visualSnapshots.append(LocalVisualSnapshot(capturedAt: now, jpeg: jpeg))
        lastFrameAt = now
        lastJPEGBytes = jpeg.count
        pruneVisualCache(now: now)
        let recent = visualSnapshots.filter { now.timeIntervalSince($0.capturedAt) <= 5 }
        if recent.count >= 2,
           let first = recent.first,
           let last = recent.last {
            let span = last.capturedAt.timeIntervalSince(first.capturedAt)
            estimatedCaptureFPS = span > 0 ? Double(recent.count - 1) / span : 0
        }
    }

    private func pruneVisualCache(now: Date = Date()) {
        visualSnapshots.removeAll { now.timeIntervalSince($0.capturedAt) > 30 }
        if visualSnapshots.count > 60 {
            visualSnapshots.removeFirst(visualSnapshots.count - 60)
        }
    }

    func ensureGlassesFrame() async -> Bool {
        if appModel.metaGlasses.streamState == "Stopped" {
            guard appModel.metaGlasses.isRegistered, appModel.metaGlasses.hasEligibleDevice else {
                perceptionStatus = "Glasses camera unavailable"
                return false
            }
            perceptionStatus = "Starting glasses camera…"
            await appModel.metaGlasses.startStream()
            try? await Task.sleep(for: .milliseconds(500))
        }
        await captureLatestFrameIfNeeded()
        return visualSnapshots.last != nil
    }

    @discardableResult
    func scanLatestFrame(copyText: Bool = false, announce: Bool = true) async -> LocalPerceptionResult? {
        guard !perceptionBusy else { return nil }
        guard await ensureGlassesFrame(), let snapshot = visualSnapshots.last else {
            perceptionStatus = "No recent glasses frame"
            return nil
        }
        perceptionBusy = true
        perceptionStatus = "Analyzing on iPhone…"
        defer { perceptionBusy = false }

        do {
            let result = try await Self.analyze(snapshot.jpeg)
            lastPerceptionAt = Date()
            localOCRText = result.text
            barcodeValues = result.barcodes
            perceptionSummary = result.summary
            perceptionStatus = "On-device scan complete"
            if copyText, !result.text.isEmpty {
                UIPasteboard.general.string = result.text
                lastLocalAction = "Copied recognized text to iPhone clipboard"
            } else if announce {
                lastLocalAction = result.summary
            }
            return result
        } catch {
            perceptionStatus = "On-device scan failed: \(error.localizedDescription)"
            return nil
        }
    }

    func copyRecognizedText() async -> String {
        if localOCRText.isEmpty {
            _ = await scanLatestFrame(copyText: false)
        }
        guard !localOCRText.isEmpty else { return "I couldn't find clearly readable text in the current glasses frame." }
        UIPasteboard.general.string = localOCRText
        lastLocalAction = "Copied recognized text to iPhone clipboard"
        return "I copied the visible text to the iPhone clipboard."
    }

    func readRecognizedText() async -> String {
        if localOCRText.isEmpty {
            _ = await scanLatestFrame(copyText: false)
        }
        guard !localOCRText.isEmpty else { return "I couldn't find clearly readable text in the current glasses frame." }
        let compact = localOCRText.replacingOccurrences(of: "\n", with: " ")
        return String(compact.prefix(1200))
    }

    func scanBarcode() async -> String {
        _ = await scanLatestFrame(copyText: false)
        guard let first = barcodeValues.first else { return "I don't see a readable QR code or barcode in the current frame." }
        UIPasteboard.general.string = first
        lastLocalAction = "Copied barcode/QR payload to iPhone clipboard"
        return "I found a code and copied its contents to the iPhone clipboard: \(String(first.prefix(500)))"
    }

    func probeConnections() async {
        async let primary = Self.probe(
            appModel.settings.baseURL,
            apiToken: appModel.settings.apiToken,
            timeout: 1.2
        )
        async let fallback = Self.probe(
            appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            timeout: 2.5
        )
        let values = await (primary, fallback)
        primaryLatencyMS = values.0
        fallbackLatencyMS = values.1
        if let p = values.0 {
            connectivityStatus = "LAN reachable • \(p) ms"
        } else if let f = values.1 {
            connectivityStatus = "Tailscale reachable • \(f) ms"
        } else {
            connectivityStatus = "Server unreachable"
        }
    }

    func sendNextQueuedCommand() async -> String {
        guard let item = offlineQueue.items.first else { return "There are no queued commands." }
        let client = JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
        do {
            let response = try await client.command(item.text)
            offlineQueue.remove(item.id)
            appModel.lastResponse = response.message
            return response.message
        } catch {
            return "The server is still unreachable. I left the queued command untouched."
        }
    }

    func diagnosticReport() -> String {
        let frameAge: String
        if let lastFrameAt {
            frameAge = String(format: "%.1fs", Date().timeIntervalSince(lastFrameAt))
        } else {
            frameAge = "none"
        }
        let primary = primaryLatencyMS.map { "\($0) ms" } ?? "unreachable"
        let fallback = fallbackLatencyMS.map { "\($0) ms" } ?? "unreachable"
        let route = persistentPresence?.companionStatus ?? "unknown"
        let health = persistentPresence?.healthContext.status ?? "unknown"
        return """
        Jarvis iPhone diagnostics
        Time: \(ISO8601DateFormatter().string(from: Date()))
        Voice state: \(appModel.voiceStatus)
        Audio: \(appModel.audioRouteManager.routeSummary)
        ASR confidence: \(Int(round(appModel.speechRecognizer.transcriptionConfidence * 100)))%
        Server: \(appModel.connectionStatus)
        Companion: \(route)
        LAN health: \(primary)
        Tailscale health: \(fallback)
        Ray-Ban registration: \(appModel.metaGlasses.registrationStatus)
        DAT eligible: \(appModel.metaGlasses.hasEligibleDevice)
        Camera stream: \(appModel.metaGlasses.streamState)
        Local visual cache: \(visualSnapshots.count) frames; ~\(String(format: "%.1f", estimatedCaptureFPS)) fps; newest \(frameAge) ago; \(lastJPEGBytes) bytes
        Local perception: \(perceptionStatus); \(perceptionSummary)
        Offline queue: \(offlineQueue.items.count)
        Motion: \(sensors.activity)
        Health context: \(health)
        Last model/timing: \(appModel.lastLatency.compactDescription)
        """
    }

    func copyDiagnostics() {
        UIPasteboard.general.string = diagnosticReport()
        lastLocalAction = "Copied diagnostics to iPhone clipboard"
    }

    func clearProactiveInbox() {
        proactiveInbox.removeAll()
    }

    private func handleLocalCommand(_ raw: String) async -> String? {
        guard appModel.settings.localCommandAliasesEnabled else { return nil }
        let text = " " + raw.lowercased().trimmingCharacters(in: .whitespacesAndNewlines) + " "

        if text.contains(" read this ") || text.contains(" read the text ") || text.contains(" read what i'm looking at ") || text.contains(" read what i am looking at ") {
            return await readRecognizedText()
        }
        if text.contains(" copy this text ") || text.contains(" copy the text ") || text.contains(" copy what i'm looking at ") || text.contains(" copy what i am looking at ") {
            return await copyRecognizedText()
        }
        if text.contains(" scan qr ") || text.contains(" scan the qr ") || text.contains(" scan barcode ") || text.contains(" scan the barcode ") {
            return await scanBarcode()
        }
        if text.contains(" passive vision off ") || text.contains(" turn vision off ") || text.contains(" vision off ") {
            appModel.settings.passiveVisionEnabled = false
            return "Passive vision is off."
        }
        if text.contains(" passive vision on ") || text.contains(" turn vision on ") || text.contains(" vision on ") {
            appModel.settings.passiveVisionEnabled = true
            return "Passive vision is on."
        }
        if text.contains(" mute alerts ") || text.contains(" stop proactive alerts ") {
            appModel.settings.proactiveAnnouncements = false
            return "Proactive spoken alerts are muted."
        }
        if text.contains(" unmute alerts ") || text.contains(" resume proactive alerts ") {
            appModel.settings.proactiveAnnouncements = true
            return "Proactive spoken alerts are enabled."
        }
        if text.contains(" mute responses ") || text.contains(" stop speaking responses ") {
            appModel.settings.speakResponses = false
            return "Spoken responses are muted."
        }
        if text.contains(" unmute responses ") || text.contains(" speak responses ") {
            appModel.settings.speakResponses = true
            return "Spoken responses are enabled."
        }
        if text.contains(" whisper for ") {
            let minutes = Self.firstInteger(in: text) ?? 10
            let bounded = max(1, min(minutes, 120))
            let until = Date().addingTimeInterval(Double(bounded) * 60)
            UserDefaults.standard.set(until.timeIntervalSince1970, forKey: "jarvis.forceWhisperUntil")
            return "Whisper mode is forced for \(bounded) minute\(bounded == 1 ? "" : "s")."
        }
        if text.contains(" stop whispering ") || text.contains(" normal voice ") {
            UserDefaults.standard.removeObject(forKey: "jarvis.forceWhisperUntil")
            return "Normal voice restored."
        }
        if text.contains(" connection diagnostics ") || text.contains(" network diagnostics ") {
            await probeConnections()
            return "\(connectivityStatus). The local visual cache has \(visualSnapshots.count) frames."
        }
        if text.contains(" send queued command ") || text.contains(" send the queued command ") {
            return await sendNextQueuedCommand()
        }
        return nil
    }

    private func processPendingShortcutAction() async {
        guard let action = FrontendActionMailbox.take() else { return }
        switch action {
        case "talk":
            await appModel.togglePushToTalk()
        case "scan":
            _ = await scanLatestFrame(copyText: false)
        case "read_text":
            let response = await readRecognizedText()
            appModel.lastResponse = response
            await appModel.speakFrontendResponseIfEnabled(response)
        case "toggle_vision":
            appModel.settings.passiveVisionEnabled.toggle()
        case "toggle_speech":
            appModel.settings.speakResponses.toggle()
        case "meeting":
            if let meetingCapture {
                if meetingCapture.isActive { await meetingCapture.stop() }
                else { await meetingCapture.start() }
            }
        default:
            break
        }
    }

    private static func firstInteger(in text: String) -> Int? {
        let pattern = #"\b(\d{1,3})\b"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text) else { return nil }
        return Int(text[range])
    }

    private static func makeJPEG(_ image: UIImage, maxDimension: CGFloat, quality: CGFloat) -> Data? {
        let size = image.size
        guard size.width > 0, size.height > 0 else { return nil }
        let scale = min(1, maxDimension / max(size.width, size.height))
        let target = CGSize(width: max(1, size.width * scale), height: max(1, size.height * scale))
        let renderer = UIGraphicsImageRenderer(size: target)
        let resized = renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: target)) }
        return resized.jpegData(compressionQuality: quality)
    }

    private static func probe(_ baseURL: String, apiToken: String, timeout: TimeInterval) async -> Int? {
        let cleaned = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, let url = URL(string: cleaned)?.appendingPathComponent("health") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        if !apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        }
        let started = Date()
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { return nil }
            return max(0, Int(Date().timeIntervalSince(started) * 1000))
        } catch {
            return nil
        }
    }

    private static func analyze(_ jpeg: Data) async throws -> LocalPerceptionResult {
        try await Task.detached(priority: .userInitiated) {
            guard let source = CGImageSourceCreateWithData(jpeg as CFData, nil),
                  let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                throw NSError(domain: "JarvisLocalVision", code: 1, userInfo: [NSLocalizedDescriptionKey: "Could not decode the glasses frame."])
            }

            let textRequest = VNRecognizeTextRequest()
            textRequest.recognitionLevel = .accurate
            textRequest.usesLanguageCorrection = true

            let barcodeRequest = VNDetectBarcodesRequest()
            let faceRequest = VNDetectFaceRectanglesRequest()
            let humanRequest = VNDetectHumanRectanglesRequest()
            let rectangleRequest = VNDetectRectanglesRequest()
            rectangleRequest.maximumObservations = 8
            rectangleRequest.minimumConfidence = 0.55
            let saliencyRequest = VNGenerateAttentionBasedSaliencyImageRequest()

            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            try handler.perform([
                textRequest,
                barcodeRequest,
                faceRequest,
                humanRequest,
                rectangleRequest,
                saliencyRequest,
            ])

            let textLines = (textRequest.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            let text = textLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            let barcodes = (barcodeRequest.results ?? []).compactMap { $0.payloadStringValue }.filter { !$0.isEmpty }

            return LocalPerceptionResult(
                text: String(text.prefix(8000)),
                barcodes: Array(barcodes.prefix(8)),
                faceCount: faceRequest.results?.count ?? 0,
                humanCount: humanRequest.results?.count ?? 0,
                rectangleCount: rectangleRequest.results?.count ?? 0,
                hasSalientRegion: !(saliencyRequest.results ?? []).isEmpty
            )
        }.value
    }
}

enum FrontendActionMailbox {
    private static let key = "jarvis.pendingFrontendAction"

    static func post(_ action: String) {
        UserDefaults.standard.set(action, forKey: key)
    }

    static func take() -> String? {
        let value = UserDefaults.standard.string(forKey: key)
        if value != nil { UserDefaults.standard.removeObject(forKey: key) }
        return value
    }
}

struct FrontendIntelligenceCard: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @EnvironmentObject private var frontend: FrontendIntelligenceController

    var body: some View {
        GroupBox("On-device Intelligence") {
            VStack(alignment: .leading, spacing: 10) {
                LabeledContent("Connection", value: frontend.connectivityStatus)
                LabeledContent(
                    "Local visual cache",
                    value: appModel.settings.localVisualHistoryEnabled ? "\(frontend.visualSnapshots.count) frames" : "Off"
                )
                LabeledContent("Capture rate", value: String(format: "%.1f fps", frontend.estimatedCaptureFPS))
                LabeledContent("Fast perception", value: frontend.perceptionStatus)
                LabeledContent("Motion", value: frontend.sensors.activity)
                LabeledContent("Offline queue", value: "\(frontend.offlineQueue.items.count)")

                if !frontend.visualSnapshots.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(Array(frontend.visualSnapshots.suffix(6))) { snapshot in
                                if let image = UIImage(data: snapshot.jpeg) {
                                    VStack(spacing: 2) {
                                        Image(uiImage: image)
                                            .resizable()
                                            .scaledToFill()
                                            .frame(width: 72, height: 46)
                                            .clipShape(RoundedRectangle(cornerRadius: 6))
                                            .clipped()
                                        Text("-\(max(0, Int(Date().timeIntervalSince(snapshot.capturedAt))))s")
                                            .font(.caption2.monospacedDigit())
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }

                if !frontend.perceptionSummary.isEmpty && frontend.perceptionSummary != "Not scanned" {
                    Text(frontend.perceptionSummary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if !frontend.localOCRText.isEmpty {
                    Text(frontend.localOCRText)
                        .font(.caption.monospaced())
                        .lineLimit(4)
                        .textSelection(.enabled)
                }

                HStack {
                    Button("Read Text") {
                        Task {
                            let response = await frontend.readRecognizedText()
                            appModel.lastResponse = response
                            await appModel.speakFrontendResponseIfEnabled(response)
                        }
                    }
                    Button("Copy Text") {
                        Task { appModel.lastResponse = await frontend.copyRecognizedText() }
                    }
                    Button("Scan QR") {
                        Task {
                            let response = await frontend.scanBarcode()
                            appModel.lastResponse = response
                        }
                    }
                }
                .buttonStyle(.bordered)

                if !frontend.barcodeValues.isEmpty {
                    Text("Code: \(frontend.barcodeValues[0])")
                        .font(.caption.monospaced())
                        .lineLimit(2)
                        .textSelection(.enabled)
                }

                if let queued = frontend.offlineQueue.items.first {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Queued: \(queued.text)")
                            .font(.caption)
                            .lineLimit(2)
                        HStack {
                            Button("Send Next") {
                                Task { appModel.lastResponse = await frontend.sendNextQueuedCommand() }
                            }
                            Button("Clear Queue", role: .destructive) { frontend.offlineQueue.clear() }
                        }
                        .buttonStyle(.bordered)
                    }
                }

                Text(appModel.lastLatency.compactDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    NavigationLink("Session History") {
                        ConversationHistoryView()
                    }
                    .buttonStyle(.bordered)
                    Button("Copy Diagnostics") { frontend.copyDiagnostics() }
                        .buttonStyle(.bordered)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct ConversationHistoryView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @EnvironmentObject private var frontend: FrontendIntelligenceController
    @State private var search = ""

    private var filtered: [FrontendConversationTurn] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return appModel.conversationLog }
        return appModel.conversationLog.filter { $0.text.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        List {
            Section("Latest timing") {
                Text(appModel.lastLatency.compactDescription)
                if !appModel.lastLatency.routeReason.isEmpty {
                    Text(appModel.lastLatency.routeReason).font(.caption).foregroundStyle(.secondary)
                }
            }

            Section("Device session transcript") {
                if filtered.isEmpty {
                    Text("No matching turns.").foregroundStyle(.secondary)
                } else {
                    ForEach(Array(filtered.reversed())) { turn in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(turn.role == "user" ? "You" : "Jarvis").bold()
                                Spacer()
                                if let model = turn.model, !model.isEmpty {
                                    Text(model).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            Text(turn.text).textSelection(.enabled)
                            Text(turn.timestamp.formatted(date: .abbreviated, time: .standard))
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }

            Section("Proactive inbox") {
                if frontend.proactiveInbox.isEmpty {
                    Text("No captured proactive events this app session.").foregroundStyle(.secondary)
                } else {
                    ForEach(Array(frontend.proactiveInbox.reversed())) { item in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.message)
                            Text(item.timestamp.formatted(date: .omitted, time: .standard))
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    Button("Clear proactive inbox", role: .destructive) { frontend.clearProactiveInbox() }
                }
            }

            Section("Diagnostics") {
                Text(frontend.diagnosticReport())
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
                Button("Copy diagnostics") { frontend.copyDiagnostics() }
                Button("Clear local conversation history", role: .destructive) {
                    appModel.clearFrontendConversationHistory()
                }
            }
        }
        .navigationTitle("Jarvis History")
        .searchable(text: $search, prompt: "Search this device session")
    }
}
