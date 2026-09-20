import CoreLocation
import Foundation
import MapKit

@MainActor
final class JarvisAppModel: ObservableObject {
    @Published var commandText = ""
    @Published var lastResponse = ""
    @Published var isSending = false
    @Published var isListening = false
    @Published var connectionStatus = "Not checked"
    @Published var errorMessage: String?
    @Published private(set) var handsFreeEnabled = false
    @Published private(set) var voiceStatus = "Hands-free Jarvis is off"
    @Published private(set) var lastHeardCommand = ""
    @Published private(set) var conversationLog: [FrontendConversationTurn] = FrontendConversationStore.load()
    @Published private(set) var lastLatency = JarvisLatencySnapshot()

    let settings: SettingsStore
    let audioRouteManager: AudioRouteManager
    let speechRecognizer: SpeechRecognizer
    let speechSynthesizer: SpeechSynthesizer
    let geofenceManager: GeofenceManager
    let metaGlasses: MetaGlassesManager
    let memoMind: MemoMindBridge
    let homeEnvironment: HomeEnvironmentController

    // Physical-world observations belong to the iPhone session, not a HUD
    // accessory. The same state is used by buttons and Gen 1 Meta voice input.
    @Published private(set) var nearbyPublicCameras: [PublicCameraListing] = []
    @Published private(set) var nearbyCameraStatus = "Tap Search or ask Jarvis to find nearby public cameras."
    @Published private(set) var nearbyCameraCoverage = ""
    @Published private(set) var nearbyCameraSourceURL = ""
    @Published private(set) var nearbyCameraBusy = false
    @Published private(set) var analyzingPublicCameraID: String?
    @Published private(set) var publicCameraAnalyses: [String: String] = [:]
    @Published private(set) var nearbyConditions: PhysicalConditionsResponse?
    @Published private(set) var nearbyConditionsStatus = "Tap Check or ask Jarvis for nearby conditions."
    @Published private(set) var nearbyConditionsBusy = false
    @Published private(set) var nearbyFacilities: NearbyFacilitiesResponse?
    @Published private(set) var nearbyFacilitiesStatus = "Tap Find or ask Jarvis about nearby public resources."
    @Published private(set) var nearbyFacilitiesBusy = false
    @Published private(set) var latestPhysicalAwareness: PhysicalAwarenessResponse?
    @Published private(set) var physicalAwarenessStatus = "Tap Brief or say: Jarvis, establish situational awareness."
    @Published private(set) var physicalAwarenessBusy = false
    private lazy var nearbyCameraLocation = PublicCameraLocationRequest()

    var frontendCommandHandler: ((String) async -> String?)?
    var offlineQueueHandler: ((String) -> Void)?
    var offlineResponseHandler: ((String) async -> String?)?

    private lazy var navigationController = JarvisNavigationController(appModel: self)
    private var wakeWordTask: Task<Void, Never>?
    private var confirmationFollowUpDeadline: Date?
    private var conversationalFollowUpDeadline: Date?
    private var currentCommandStartedAt: Date?
    private var currentFirstAudioAt: Date?

    private enum VoicePhase {
        case waitingForWake
        case collectingAfterWake
        case awaitingFollowUp(deadline: Date)
    }

    init() {
        settings = SettingsStore()
        let audioRouteManager = AudioRouteManager()
        self.audioRouteManager = audioRouteManager
        speechRecognizer = SpeechRecognizer(audioRouteManager: audioRouteManager)
        speechSynthesizer = SpeechSynthesizer(audioRouteManager: audioRouteManager)
        geofenceManager = GeofenceManager()
        metaGlasses = MetaGlassesManager()
        memoMind = MemoMindBridge()
        homeEnvironment = HomeEnvironmentController()

        geofenceManager.onHomeArrival = { [weak self] in
            Task { @MainActor in
                await self?.sendEvent("home_arrival")
            }
        }
    }

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: settings.baseURL,
            fallbackBaseURL: settings.fallbackBaseURL,
            apiToken: settings.apiToken,
            sessionID: settings.conversationSessionID
        )
    }

    func discoverNearbyPublicCameras(latitude: Double, longitude: Double) async throws -> PublicCameraDiscoveryResponse {
        try await client.discoverNearbyPublicCameras(latitude: latitude, longitude: longitude)
    }

    func establishPhysicalAwareness() async -> String {
        guard !physicalAwarenessBusy else { return "A physical-world briefing is already in progress." }
        physicalAwarenessBusy = true
        physicalAwarenessStatus = "Requesting a one-time iPhone location…"
        defer { physicalAwarenessBusy = false }
        do {
            let position = try await nearbyCameraLocation.locateOnce()
            physicalAwarenessStatus = "Checking public viewpoints, air model, official alerts and mapped facilities…"
            let overview = try await client.physicalAwareness(
                latitude: position.coordinate.latitude,
                longitude: position.coordinate.longitude
            )
            latestPhysicalAwareness = overview
            nearbyPublicCameras = overview.cameras.cameras
            nearbyCameraCoverage = overview.cameras.coverage
            nearbyCameraSourceURL = overview.cameras.sourceURL
            nearbyCameraStatus = overview.cameras.sourceNote
            publicCameraAnalyses = [:]
            nearbyConditions = overview.conditions
            nearbyConditionsStatus = overview.conditions.airQuality.sourceNote
            nearbyFacilities = overview.facilities
            nearbyFacilitiesStatus = overview.facilities.sourceNote
            physicalAwarenessStatus = overview.summary
            return overview.summary + " Details and source caveats are in the Physical tab."
        } catch {
            physicalAwarenessStatus = "Physical-world briefing unavailable: " + error.localizedDescription
            return physicalAwarenessStatus
        }
    }

    private static func isPhysicalAwarenessIntent(_ rawText: String) -> Bool {
        var normalized = rawText.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: ".?!"))
        if normalized.hasPrefix("jarvis, ") {
            normalized = String(normalized.dropFirst(8))
        } else if normalized.hasPrefix("jarvis ") {
            normalized = String(normalized.dropFirst(7))
        }
        return [
            "establish situational awareness", "give me a physical world briefing",
            "physical world briefing", "brief me on my surroundings",
            "check my surroundings", "what do the public sensors say around me",
        ].contains(normalized)
    }

    func analyzePublishedCameraStill(_ cameraID: String) async -> String {
        guard analyzingPublicCameraID == nil else {
            return "I am already analyzing a published camera still."
        }
        guard let camera = nearbyPublicCameras.first(where: { $0.id == cameraID }),
              !camera.imageURL.isEmpty else {
            return "Select an available official still from the Physical tab first."
        }
        analyzingPublicCameraID = cameraID
        defer { analyzingPublicCameraID = nil }
        publicCameraAnalyses[cameraID] = "Retrieving one official still for local analysis…"
        do {
            let analysis = try await client.analyzeOfficialPublicCamera(cameraID)
            let response = analysis.description + " " + analysis.sourceNote
            publicCameraAnalyses[cameraID] = response
            return "\(analysis.cameraName): " + response
        } catch {
            let error = "Image analysis unavailable: " + error.localizedDescription
            publicCameraAnalyses[cameraID] = error
            return error
        }
    }

    private static func isAnalyzePublicStillIntent(_ rawText: String) -> Bool {
        var normalized = rawText.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: ".?!"))
        if normalized.hasPrefix("jarvis, ") {
            normalized = String(normalized.dropFirst(8))
        } else if normalized.hasPrefix("jarvis ") {
            normalized = String(normalized.dropFirst(7))
        }
        return [
            "analyze the nearest public camera",
            "analyze nearest public camera",
            "describe the nearest public camera",
            "analyze the nearest traffic camera",
        ].contains(normalized)
    }

    func searchNearbyPublicCameras() async -> String {
        guard !nearbyCameraBusy else { return "A public camera search is already running." }
        nearbyCameraBusy = true
        nearbyPublicCameras = []
        publicCameraAnalyses = [:]
        nearbyCameraCoverage = ""
        nearbyCameraSourceURL = ""
        nearbyCameraStatus = "Requesting a one-time iPhone location…"
        defer { nearbyCameraBusy = false }
        do {
            let position = try await nearbyCameraLocation.locateOnce()
            nearbyCameraStatus = "Checking officially published camera catalogs…"
            let response = try await discoverNearbyPublicCameras(
                latitude: position.coordinate.latitude,
                longitude: position.coordinate.longitude
            )
            nearbyPublicCameras = response.cameras
            nearbyCameraCoverage = response.coverage
            nearbyCameraSourceURL = response.sourceURL
            if response.cameras.isEmpty {
                nearbyCameraStatus = response.sourceNote
                return response.status == "unsupported_region"
                    ? "I don't have an integrated public-camera provider for this area. The Physical tab shows the available official source."
                    : "No published highway cameras were returned nearby. \(response.sourceNote)"
            }
            let first = response.cameras[0]
            nearbyCameraStatus = "\(response.cameras.count) published camera feeds nearby. Footage freshness is not verified."
            return "I found \(response.cameras.count) published traffic-camera feeds within ten kilometers. Nearest: \(first.title), about \(String(format: "%.1f", first.distanceKM)) kilometers away. Open Physical on your iPhone for images. I have not analyzed the footage."
        } catch {
            nearbyCameraStatus = "Camera lookup unavailable: " + error.localizedDescription
            return nearbyCameraStatus
        }
    }

    private static func isPublicCameraIntent(_ rawText: String) -> Bool {
        var normalized = rawText.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: ".?!"))
        if normalized.hasPrefix("jarvis, ") {
            normalized = String(normalized.dropFirst(8))
        } else if normalized.hasPrefix("jarvis ") {
            normalized = String(normalized.dropFirst(7))
        }
        return [
            "find nearby public cameras", "find public cameras near me",
            "what public cameras are nearby", "show nearby public cameras",
            "find nearby traffic cameras", "find traffic cameras near me",
            "show nearby traffic cameras", "what traffic cameras are nearby",
        ].contains(normalized)
    }

    func searchNearbyPublicFacilities() async -> String {
        guard !nearbyFacilitiesBusy else { return "A public resources search is already running." }
        nearbyFacilitiesBusy = true
        nearbyFacilities = nil
        nearbyFacilitiesStatus = "Requesting a one-time iPhone location…"
        defer { nearbyFacilitiesBusy = false }
        do {
            let position = try await nearbyCameraLocation.locateOnce()
            nearbyFacilitiesStatus = "Checking OpenStreetMap public facilities…"
            let response = try await client.discoverNearbyFacilities(
                latitude: position.coordinate.latitude,
                longitude: position.coordinate.longitude
            )
            nearbyFacilities = response
            if response.status != "ok" {
                nearbyFacilitiesStatus = response.sourceNote
                return nearbyFacilitiesStatus
            }
            if response.facilities.isEmpty {
                nearbyFacilitiesStatus = "No mapped toilets, water or defibrillators returned within 1.5 km. This does not mean none exist."
                return nearbyFacilitiesStatus
            }
            let nearest = response.facilities[0]
            nearbyFacilitiesStatus = "\(response.facilities.count) mapped public facilities within 1.5 km. Nearest: \(nearest.title), approximately \(nearest.distanceM) meters away. Mapping may be incomplete."
            return nearbyFacilitiesStatus + " Open Physical on your iPhone for walking directions."
        } catch {
            nearbyFacilitiesStatus = "Public resources unavailable: " + error.localizedDescription
            return nearbyFacilitiesStatus
        }
    }

    private static func isNearbyFacilitiesIntent(_ rawText: String) -> Bool {
        var normalized = rawText.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: ".?!"))
        if normalized.hasPrefix("jarvis, ") {
            normalized = String(normalized.dropFirst(8))
        } else if normalized.hasPrefix("jarvis ") {
            normalized = String(normalized.dropFirst(7))
        }
        return [
            "find public resources near me", "find nearby public resources",
            "find nearby water fountains", "find drinking water near me",
            "where is the nearest public toilet", "find public toilets near me",
            "find a public defibrillator near me", "find defibrillators near me",
        ].contains(normalized)
    }

    func searchPhysicalConditions() async -> String {
        guard !nearbyConditionsBusy else { return "A local conditions check is already running." }
        nearbyConditionsBusy = true
        nearbyConditions = nil
        nearbyConditionsStatus = "Requesting a one-time iPhone location…"
        defer { nearbyConditionsBusy = false }
        do {
            let position = try await nearbyCameraLocation.locateOnce()
            nearbyConditionsStatus = "Checking published physical-world conditions…"
            let response = try await client.discoverPhysicalConditions(
                latitude: position.coordinate.latitude,
                longitude: position.coordinate.longitude
            )
            nearbyConditions = response
            let air = response.airQuality
            let alerts = response.weatherAlerts
            var parts: [String] = []
            if air.status == "ok" {
                if let aqi = air.usAQI {
                    parts.append("Modelled air quality is US AQI \(Int(aqi))")
                } else {
                    parts.append("Air quality data is incomplete")
                }
                if let uv = air.uvIndex {
                    parts.append("UV index \(String(format: "%.1f", uv))")
                }
            } else {
                parts.append("Air quality is \(air.status)")
            }
            if alerts.status == "ok" {
                if alerts.alerts.isEmpty {
                    parts.append("no active NWS weather alerts were returned for this point; other hazards have not been checked")
                } else {
                    let events = alerts.alerts.prefix(3).map { $0.event }
                    parts.append("\(alerts.alerts.count) NWS alerts: " + events.joined(separator: ", "))
                }
            } else if alerts.status == "unsupported_region" {
                parts.append("official weather alerts are not integrated for this region")
            } else {
                parts.append("official weather alerts could not be checked")
            }
            nearbyConditionsStatus = parts.joined(separator: "; ") + "."
            return nearbyConditionsStatus + " More detail and source times are in the Physical tab."
        } catch {
            nearbyConditionsStatus = "Physical conditions unavailable: " + error.localizedDescription
            return nearbyConditionsStatus
        }
    }

    private static func isPhysicalConditionsIntent(_ rawText: String) -> Bool {
        var normalized = rawText.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: ".?!"))
        if normalized.hasPrefix("jarvis, ") {
            normalized = String(normalized.dropFirst(8))
        } else if normalized.hasPrefix("jarvis ") {
            normalized = String(normalized.dropFirst(7))
        }
        return [
            "check conditions around me", "what are the conditions around me",
            "check nearby air quality", "what's the air quality near me",
            "what is the air quality near me", "check nearby weather alerts",
            "are there weather alerts near me", "what are the weather alerts near me",
        ].contains(normalized)
    }

    func listDiligenceMatters() async throws -> [DiligenceMatterSummary] {
        try await client.listDiligenceMatters()
    }

    func createDiligenceMatter(label: String, projectEntityID: String) async throws -> DiligenceMatterSummary {
        try await client.createDiligenceMatter(label: label, projectEntityID: projectEntityID)
    }

    func registerDiligenceIssuer(matterID: String, cik: String, name: String) async throws {
        try await client.registerDiligenceIssuer(matterID: matterID, cik: cik, name: name)
    }

    func registerNumericDiligenceClaim(
        matterID: String, cik: String, taxonomy: String, tag: String,
        value: Double, unit: String, start: String, end: String, sourceRef: String
    ) async throws {
        try await client.registerNumericDiligenceClaim(
            matterID: matterID, cik: cik, taxonomy: taxonomy, tag: tag,
            value: value, unit: unit, start: start, end: end, sourceRef: sourceRef
        )
    }

    func checkDiligenceMatter(matterID: String, includeSanctions: Bool) async throws -> [String: Any] {
        try await client.checkDiligenceMatter(
            matterID: matterID, includeSanctions: includeSanctions
        )
    }

    func findPublicCamerasAt(latitude: Double, longitude: Double) async throws -> PublicCameraDiscoveryResponse {
        try await client.discoverNearbyPublicCameras(latitude: latitude, longitude: longitude)
    }

    func createExternalWatch(
        kind: String, label: String, config: [String: Any], seconds: Int
    ) async throws -> ExternalWatchSummary {
        try await client.createExternalWatch(
            kind: kind, label: label, config: config, seconds: seconds
        )
    }

    func getExternalWatches() async throws -> [ExternalWatchSummary] {
        try await client.getExternalWatches()
    }

    func checkExternalWatch(_ id: String) async throws -> ExternalWatchCheckResponse {
        try await client.checkExternalWatch(id)
    }

    func stopExternalWatch(_ id: String) async throws -> ExternalWatchSummary {
        try await client.stopExternalWatch(id)
    }

    func refreshMemoMindCommandView() async throws {
        let snapshot = try await client.agencyCommandView()
        memoMind.presentCommandView(snapshot)
    }

    func checkConnection() async {
        do {
            let healthy = try await client.health()
            connectionStatus = healthy ? "Connected" : "Server unavailable"
        } catch {
            connectionStatus = "Connection failed"
            errorMessage = error.localizedDescription
        }
    }

    func sendCurrentCommand() async {
        let text = commandText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        commandText = ""
        await sendCommand(text)
    }

    func sendCommand(_ text: String) async {
        await performCommand(text, fromHandsFree: false)
    }

    func speakFrontendResponseIfEnabled(_ text: String) async {
        guard settings.speakResponses, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        await speakOneResponse(text)
    }

    func clearFrontendConversationHistory() {
        conversationLog.removeAll()
        FrontendConversationStore.clear()
    }

    private func recordTurn(role: String, text: String, model: String? = nil) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        conversationLog.append(FrontendConversationTurn(role: role, text: cleaned, model: model))
        if conversationLog.count > 120 { conversationLog.removeFirst(conversationLog.count - 120) }
        FrontendConversationStore.save(conversationLog)
        if role == "assistant" {
            memoMind.presentAssistantReply(
                cleaned,
                requiresConfirmation: Self.responseRequestsConfirmation(cleaned)
            )
        }
    }

    private func finishLocalResponse(
        _ localResponse: String,
        command text: String,
        fromHandsFree: Bool,
        routeReason: String
    ) async {
        lastResponse = localResponse
        recordTurn(role: "user", text: text)
        recordTurn(role: "assistant", text: localResponse, model: "iPhone")
        lastLatency = JarvisLatencySnapshot(
            model: "iPhone",
            routeReason: routeReason,
            firstResponseMS: 0,
            firstAudioReadyMS: nil,
            totalTurnMS: 0
        )
        if settings.speakResponses && !localResponse.isEmpty {
            if fromHandsFree { voiceStatus = "Speaking…" }
            if routeReason == "iPhone MapKit turn-by-turn navigation" {
                // Navigation speech must never wait on the PC/Tailscale TTS path.
                // AVSpeechSynthesizer keeps route acknowledgements available even
                // when the Windows backend is unreachable.
                await speechSynthesizer.speak(
                    localResponse,
                    preferBluetooth: settings.preferBluetoothAudio,
                    whisper: false
                )
            } else {
                await speakOneResponse(localResponse)
            }
        }
        if fromHandsFree {
            confirmationFollowUpDeadline = nil
            conversationalFollowUpDeadline = Date().addingTimeInterval(5)
            voiceStatus = "Listening for follow-up…"
        }
    }

    private func performCommand(_ rawText: String, fromHandsFree: Bool) async {
        let text = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        // The Personal Notecard is an explicit local fact source. Handle direct
        // additions, lookups, and answers to a fact Jarvis just requested before
        // any planner or external service sees the utterance.
        if let notecardResponse = PersonalNotecardStore.shared.handleCommand(text) {
            await finishLocalResponse(
                notecardResponse,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "iPhone Personal Notecard"
            )
            return
        }

        // Navigation is a first-class iPhone capability. Route it before the generic
        // frontend stack and before the PC so a spoken "Jarvis, take me to ..." can
        // resolve a place and begin guidance even when the Windows agent is offline.
        if JarvisNavigationController.isNavigationIntent(text),
           let navigationResponse = await navigationController.handle(text) {
            await finishLocalResponse(
                navigationResponse,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "iPhone MapKit turn-by-turn navigation"
            )
            return
        }

        // The Gen 1 Ray-Bans provide microphone/speaker I/O over the existing
        // Bluetooth audio route. They do not need MemoMind or a glasses HUD.
        if Self.isPhysicalAwarenessIntent(text) {
            let briefing = await establishPhysicalAwareness()
            await finishLocalResponse(
                briefing,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "One-shot sourced physical situational briefing"
            )
            return
        }

        if Self.isAnalyzePublicStillIntent(text) {
            let nearest = nearbyPublicCameras.first(where: { !$0.imageURL.isEmpty })
            let description = nearest == nil
                ? "Discover published public cameras in the Physical tab first."
                : await analyzePublishedCameraStill(nearest!.id)
            await finishLocalResponse(
                description,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "Explicit selected public still + local vision model"
            )
            return
        }

        if Self.isNearbyFacilitiesIntent(text) {
            let facilityReply = await searchNearbyPublicFacilities()
            await finishLocalResponse(
                facilityReply,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "iPhone location + public mapped resources"
            )
            return
        }

        if Self.isPhysicalConditionsIntent(text) {
            let conditionsReply = await searchPhysicalConditions()
            await finishLocalResponse(
                conditionsReply,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "iPhone location + official weather warnings / global air model"
            )
            return
        }

        if Self.isPublicCameraIntent(text) {
            let cameraReply = await searchNearbyPublicCameras()
            await finishLocalResponse(
                cameraReply,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "iPhone location + official public camera discovery"
            )
            return
        }

        // An explicitly discovered Apple Home is a direct phone-local control
        // surface. Only narrow, exact-name light commands are handled here;
        // every action gets a fresh HomeKit state readback.
        if let homeReply = await homeEnvironment.handleCommand(text) {
            await finishLocalResponse(
                homeReply,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "iPhone HomeKit verified light control"
            )
            return
        }

        if let frontendCommandHandler,
           let localResponse = await frontendCommandHandler(text) {
            await finishLocalResponse(
                localResponse,
                command: text,
                fromHandsFree: fromHandsFree,
                routeReason: "frontend-only command"
            )
            return
        }

        // Only facts selected as relevant to this particular command cross into the
        // reasoning path. The full notecard is never attached wholesale.
        let requestText = PersonalNotecardStore.shared.contextualizedCommand(text)

        guard !isSending else { return }
        isSending = true
        lastResponse = ""
        recordTurn(role: "user", text: text)
        if fromHandsFree {
            voiceStatus = "Thinking…"
        }

        let startedAt = Date()
        currentCommandStartedAt = startedAt
        currentFirstAudioAt = nil
        var firstResponseAt: Date?
        var modelLabel = "—"
        var routeReason = ""
        var assistantRecorded = false
        defer {
            isSending = false
            let end = Date()
            lastLatency = JarvisLatencySnapshot(
                model: modelLabel,
                routeReason: routeReason,
                firstResponseMS: firstResponseAt.map { max(0, Int($0.timeIntervalSince(startedAt) * 1000)) },
                firstAudioReadyMS: currentFirstAudioAt.map { max(0, Int($0.timeIntervalSince(startedAt) * 1000)) },
                totalTurnMS: max(0, Int(end.timeIntervalSince(startedAt) * 1000))
            )
            currentCommandStartedAt = nil
            currentFirstAudioAt = nil
        }

        var fullResponse = ""
        var speechBuffer = ""
        var appleFallbackBuffer = ""
        var qwenTTSAvailable = true
        var confirmationSpoken = false
        var interrupted = false

        do {
            for try await event in client.streamCommandEvents(requestText) {
                switch event {
                case .start(let model, let reason):
                    modelLabel = model ?? "backend"
                    routeReason = reason ?? ""
                    continue
                case .done:
                    continue
                case .delta(let delta):
                    if firstResponseAt == nil { firstResponseAt = Date() }
                    fullResponse += delta
                    lastResponse = fullResponse

                    guard settings.speakResponses && !interrupted else { continue }

                    if Self.responseRequestsConfirmation(fullResponse) {
                        if !confirmationSpoken {
                            speechBuffer = ""
                            appleFallbackBuffer = ""
                            confirmationSpoken = true
                            if fromHandsFree { voiceStatus = "Speaking…" }
                            let prompt = Self.spokenResponse(for: fullResponse)
                            if !(await speakQwenChunk(prompt)) {
                                if currentFirstAudioAt == nil { currentFirstAudioAt = Date() }
                                await speechSynthesizer.speak(
                                    prompt,
                                    preferBluetooth: settings.preferBluetoothAudio
                                )
                            }
                            interrupted = speechSynthesizer.lastOutputInterrupted
                        }
                        continue
                    }

                    if qwenTTSAvailable {
                        speechBuffer += delta
                        while let segment = Self.takeSpeechSegment(from: &speechBuffer, flush: false) {
                            if fromHandsFree { voiceStatus = "Speaking…" }
                            let success = await speakQwenChunk(segment)
                            if speechSynthesizer.lastOutputInterrupted {
                                interrupted = true
                                break
                            }
                            if !success {
                                qwenTTSAvailable = false
                                appleFallbackBuffer = Self.joinCommandParts(segment, speechBuffer)
                                speechBuffer = ""
                                break
                            }
                        }
                    } else {
                        appleFallbackBuffer += delta
                    }

                    if interrupted { break }
                }
            }

            if settings.speakResponses && !interrupted && !confirmationSpoken {
                if qwenTTSAvailable {
                    if let tail = Self.takeSpeechSegment(from: &speechBuffer, flush: true), !tail.isEmpty {
                        if fromHandsFree { voiceStatus = "Speaking…" }
                        let success = await speakQwenChunk(tail)
                        interrupted = speechSynthesizer.lastOutputInterrupted
                        if !success && !interrupted {
                            if currentFirstAudioAt == nil { currentFirstAudioAt = Date() }
                            await speechSynthesizer.speak(
                                tail,
                                preferBluetooth: settings.preferBluetoothAudio
                            )
                        }
                    }
                } else {
                    let fallback = Self.joinCommandParts(appleFallbackBuffer, speechBuffer)
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if !fallback.isEmpty {
                        if fromHandsFree { voiceStatus = "Speaking…" }
                        if currentFirstAudioAt == nil { currentFirstAudioAt = Date() }
                        await speechSynthesizer.speak(
                            fallback,
                            preferBluetooth: settings.preferBluetoothAudio
                        )
                        interrupted = speechSynthesizer.lastOutputInterrupted
                    }
                }
            }

            if !fullResponse.isEmpty {
                recordTurn(role: "assistant", text: fullResponse, model: modelLabel == "—" ? nil : modelLabel)
                assistantRecorded = true
            }

            if fromHandsFree && Self.responseRequestsConfirmation(fullResponse) {
                confirmationFollowUpDeadline = Date().addingTimeInterval(15)
                conversationalFollowUpDeadline = nil
                voiceStatus = "Say confirm or cancel"
            } else if fromHandsFree && !fullResponse.isEmpty {
                confirmationFollowUpDeadline = nil
                conversationalFollowUpDeadline = Date().addingTimeInterval(5)
                voiceStatus = "Listening for follow-up…"
            } else {
                confirmationFollowUpDeadline = nil
                conversationalFollowUpDeadline = nil
            }
        } catch {
            do {
                let response = try await client.command(requestText)
                if firstResponseAt == nil { firstResponseAt = Date() }
                if modelLabel == "—" { modelLabel = "backend" }
                fullResponse = response.message
                lastResponse = response.message
                if settings.speakResponses && !response.message.isEmpty {
                    if fromHandsFree { voiceStatus = "Speaking…" }
                    await speakOneResponse(Self.spokenResponse(for: response.message))
                }
                if !assistantRecorded && !response.message.isEmpty {
                    recordTurn(role: "assistant", text: response.message, model: modelLabel)
                    assistantRecorded = true
                }
                if fromHandsFree && Self.responseRequestsConfirmation(response.message) {
                    confirmationFollowUpDeadline = Date().addingTimeInterval(15)
                    conversationalFollowUpDeadline = nil
                    voiceStatus = "Say confirm or cancel"
                } else if fromHandsFree && !response.message.isEmpty {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = Date().addingTimeInterval(5)
                    voiceStatus = "Listening for follow-up…"
                }
            } catch {
                confirmationFollowUpDeadline = nil
                conversationalFollowUpDeadline = nil
                if Self.isConnectivityError(error),
                   let offlineResponseHandler,
                   let localResponse = await offlineResponseHandler(requestText),
                   !localResponse.isEmpty {
                    if firstResponseAt == nil { firstResponseAt = Date() }
                    modelLabel = "Apple on-device"
                    routeReason = "PC unreachable; answered by iPhone Foundation Models"
                    fullResponse = localResponse
                    lastResponse = localResponse
                    recordTurn(role: "assistant", text: localResponse, model: modelLabel)
                    assistantRecorded = true
                    if settings.speakResponses {
                        if fromHandsFree { voiceStatus = "Speaking offline…" }
                        await speechSynthesizer.speak(localResponse, preferBluetooth: settings.preferBluetoothAudio)
                    }
                    if fromHandsFree {
                        conversationalFollowUpDeadline = Date().addingTimeInterval(5)
                        voiceStatus = "Listening for follow-up…"
                    }
                } else if settings.offlineQueueEnabled && Self.isConnectivityError(error) {
                    offlineQueueHandler?(text)
                    let message = "The Jarvis server is unreachable, so I staged that command on this iPhone instead of losing it. Nothing will execute until you explicitly send the queued command."
                    lastResponse = message
                    recordTurn(role: "assistant", text: message, model: "iPhone")
                    modelLabel = "iPhone queue"
                    if fromHandsFree {
                        voiceStatus = "Queued offline"
                        if settings.speakResponses { await speechSynthesizer.speak(message, preferBluetooth: settings.preferBluetoothAudio) }
                    }
                } else {
                    errorMessage = error.localizedDescription
                    if fromHandsFree { voiceStatus = "Command failed" }
                }
            }
        }
    }

    private static func isConnectivityError(_ error: Error) -> Bool {
        if error is URLError { return true }
        let ns = error as NSError
        return ns.domain == NSURLErrorDomain
    }

    private func speakQwenChunk(_ text: String) async -> Bool {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return true }
        do {
            let audio = try await client.synthesizeSpeech(cleaned)
            if currentFirstAudioAt == nil { currentFirstAudioAt = Date() }
            try await speechSynthesizer.speakRemoteAudio(
                audio,
                text: cleaned,
                preferBluetooth: settings.preferBluetoothAudio
            )
            return true
        } catch {
            return false
        }
    }

    private func speakOneResponse(_ text: String) async {
        if !(await speakQwenChunk(text)) {
            if currentFirstAudioAt == nil { currentFirstAudioAt = Date() }
            await speechSynthesizer.speak(
                text,
                preferBluetooth: settings.preferBluetoothAudio
            )
        }
    }

    func sendEvent(_ name: String) async {
        do {
            let response = try await client.event(name)
            lastResponse = response.message
            if settings.speakResponses && !response.message.isEmpty {
                await speakOneResponse(response.message)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func togglePushToTalk() async {
        guard !handsFreeEnabled else { return }

        if isListening {
            stopListeningAndSend()
            return
        }

        do {
            try await speechRecognizer.requestPermissions()
            try speechRecognizer.startListening(preferBluetooth: settings.preferBluetoothAudio)
            isListening = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func stopListeningAndSend() {
        let text = speechRecognizer.stopListening().trimmingCharacters(in: .whitespacesAndNewlines)
        isListening = false
        guard !text.isEmpty else { return }
        Task { await sendCommand(text) }
    }

    func configureHomeGeofence() {
        geofenceManager.configureHome(
            latitude: settings.homeLatitude,
            longitude: settings.homeLongitude,
            radius: settings.homeRadius
        )
    }

    func setHandsFreeEnabled(_ enabled: Bool) async {
        if enabled {
            await startWakeWordMode()
        } else {
            stopWakeWordMode()
        }
    }

    func startWakeWordMode() async {
        stopWakeWordMode()
        do {
            try await speechRecognizer.requestPermissions()
        } catch {
            errorMessage = error.localizedDescription
            voiceStatus = "Microphone unavailable"
            return
        }

        handsFreeEnabled = true
        confirmationFollowUpDeadline = nil
        conversationalFollowUpDeadline = nil
        voiceStatus = "Listening for “Jarvis”…"
        wakeWordTask = Task { [weak self] in
            guard let self else { return }
            await self.runHandsFreeLoop()
        }
    }

    func stopWakeWordMode() {
        wakeWordTask?.cancel()
        wakeWordTask = nil
        confirmationFollowUpDeadline = nil
        conversationalFollowUpDeadline = nil
        handsFreeEnabled = false
        speechSynthesizer.stopSpeaking()
        if isListening || speechRecognizer.isActive {
            _ = speechRecognizer.stopListening()
        }
        isListening = false
        voiceStatus = "Hands-free Jarvis is off"
    }

    private func runHandsFreeLoop() async {
        var phase: VoicePhase = .waitingForWake
        var lastTranscript = ""
        var lastTranscriptChange = Date()
        var commandBuffer = ""
        var followUpBuffer = ""

        guard await restartVoiceRecognition() else { return }

        while !Task.isCancelled && handsFreeEnabled {
            try? await Task.sleep(for: .milliseconds(120))
            guard !Task.isCancelled && handsFreeEnabled else { return }

            let now = Date()
            let transcript = speechRecognizer.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            if transcript != lastTranscript {
                lastTranscript = transcript
                lastTranscriptChange = now
            }
            let silence = now.timeIntervalSince(lastTranscriptChange)
            let recognitionEnded = !speechRecognizer.isActive

            if let deadline = confirmationFollowUpDeadline, now >= deadline {
                confirmationFollowUpDeadline = nil
                if case .waitingForWake = phase, conversationalFollowUpDeadline == nil {
                    voiceStatus = "Listening for “Jarvis”…"
                }
            }

            if let deadline = conversationalFollowUpDeadline, now >= deadline {
                conversationalFollowUpDeadline = nil
                if case .waitingForWake = phase, confirmationFollowUpDeadline == nil {
                    voiceStatus = "Listening for “Jarvis”…"
                }
            }

            switch phase {
            case .waitingForWake:
                commandBuffer = ""
                followUpBuffer = ""

                if let deadline = confirmationFollowUpDeadline,
                   now < deadline,
                   let confirmation = Self.confirmationCommand(from: transcript),
                   silence >= 0.55 || recognitionEnded {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await submitHandsFreeCommand(confirmation)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if let deadline = conversationalFollowUpDeadline, now < deadline {
                    phase = .awaitingFollowUp(deadline: deadline)
                    voiceStatus = "Listening for follow-up…"
                    continue
                }

                if let command = Self.commandAfterWakeWord(in: transcript) {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    phase = .collectingAfterWake
                    voiceStatus = "Listening for command…"
                    let requiredSilence = Self.commandSilenceWindow(for: command)

                    if !command.isEmpty && silence >= requiredSilence {
                        await submitHandsFreeCommand(command)
                        phase = .waitingForWake
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }

                    if recognitionEnded {
                        if Self.needsExtendedDictation(command) {
                            commandBuffer = command
                            _ = await restartVoiceRecognition()
                            lastTranscript = ""
                            lastTranscriptChange = Date()
                            continue
                        }

                        if !command.isEmpty {
                            await submitHandsFreeCommand(command)
                            phase = .waitingForWake
                            lastTranscript = ""
                            lastTranscriptChange = Date()
                            continue
                        }
                    }
                } else if Self.containsWakeWord(transcript) && (silence >= 0.65 || recognitionEnded) {
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await promptForFollowUp()
                    phase = .awaitingFollowUp(deadline: Date().addingTimeInterval(20))
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                } else if !transcript.isEmpty && silence >= 1.2 {
                    _ = speechRecognizer.stopListening()
                    isListening = false
                    _ = await restartVoiceRecognition()
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

            case .collectingAfterWake:
                let segment: String
                if commandBuffer.isEmpty {
                    segment = Self.commandAfterWakeWord(in: transcript) ?? ""
                } else {
                    segment = transcript
                }

                let command = Self.joinCommandParts(commandBuffer, segment)
                let requiredSilence = Self.commandSilenceWindow(for: command)

                if !command.isEmpty && silence >= requiredSilence {
                    commandBuffer = ""
                    await submitHandsFreeCommand(command)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if recognitionEnded {
                    if Self.needsExtendedDictation(command) {
                        commandBuffer = command
                        _ = await restartVoiceRecognition()
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }

                    if !command.isEmpty {
                        commandBuffer = ""
                        await submitHandsFreeCommand(command)
                        phase = .waitingForWake
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }
                }

            case .awaitingFollowUp(let deadline):
                let command = Self.joinCommandParts(followUpBuffer, transcript)
                let requiredSilence = Self.commandSilenceWindow(for: command)

                if !command.isEmpty && silence >= requiredSilence {
                    followUpBuffer = ""
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await submitHandsFreeCommand(command)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if recognitionEnded && !command.isEmpty {
                    if Self.needsExtendedDictation(command) {
                        followUpBuffer = command
                        _ = await restartVoiceRecognition()
                        lastTranscript = ""
                        lastTranscriptChange = Date()
                        continue
                    }

                    followUpBuffer = ""
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    await submitHandsFreeCommand(command)
                    phase = .waitingForWake
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }

                if now >= deadline && command.isEmpty {
                    followUpBuffer = ""
                    confirmationFollowUpDeadline = nil
                    conversationalFollowUpDeadline = nil
                    phase = .waitingForWake
                    voiceStatus = "Listening for “Jarvis”…"
                    _ = speechRecognizer.stopListening()
                    isListening = false
                    _ = await restartVoiceRecognition()
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                    continue
                }
            }

            if recognitionEnded {
                let restarted = await restartVoiceRecognition()
                if restarted {
                    lastTranscript = ""
                    lastTranscriptChange = Date()
                } else {
                    try? await Task.sleep(for: .seconds(1))
                }
            }
        }
    }

    private func promptForFollowUp() async {
        _ = speechRecognizer.stopListening()
        isListening = false
        conversationalFollowUpDeadline = nil
        voiceStatus = "Listening for command…"
        await speakOneResponse("Yes, sir?")
        try? await Task.sleep(for: .milliseconds(180))
        _ = await restartVoiceRecognition()
    }

    private func submitHandsFreeCommand(_ rawCommand: String) async {
        let command = rawCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !command.isEmpty else { return }

        _ = speechRecognizer.stopListening()
        isListening = false
        lastHeardCommand = command
        await performCommand(command, fromHandsFree: true)

        guard handsFreeEnabled && !Task.isCancelled else { return }
        try? await Task.sleep(for: .milliseconds(180))
        if confirmationFollowUpDeadline != nil {
            voiceStatus = "Say confirm or cancel"
        } else if conversationalFollowUpDeadline != nil {
            voiceStatus = "Listening for follow-up…"
        } else {
            voiceStatus = "Listening for “Jarvis”…"
        }
        _ = await restartVoiceRecognition()
    }

    @discardableResult
    private func restartVoiceRecognition() async -> Bool {
        guard handsFreeEnabled && !Task.isCancelled else { return false }
        if speechRecognizer.isActive {
            isListening = true
            return true
        }

        do {
            try speechRecognizer.startListening(preferBluetooth: settings.preferBluetoothAudio)
            isListening = true
            audioRouteManager.refresh()
            return true
        } catch {
            isListening = false
            voiceStatus = "Waiting for microphone…"
            return false
        }
    }

    static func containsWakeWord(_ transcript: String) -> Bool {
        transcript.range(of: "jarvis", options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }

    static func commandAfterWakeWord(in transcript: String) -> String? {
        guard let range = transcript.range(of: "jarvis", options: [.caseInsensitive, .diacriticInsensitive]) else {
            return nil
        }
        let suffix = transcript[range.upperBound...]
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
        return suffix.isEmpty ? nil : suffix
    }

    private static func joinCommandParts(_ first: String, _ second: String) -> String {
        let a = first.trimmingCharacters(in: .whitespacesAndNewlines)
        let b = second.trimmingCharacters(in: .whitespacesAndNewlines)
        if a.isEmpty { return b }
        if b.isEmpty { return a }
        return "\(a) \(b)"
    }

    private static func takeSpeechSegment(from buffer: inout String, flush: Bool) -> String? {
        let trimmedLeading = buffer.drop(while: { $0.isWhitespace })
        if trimmedLeading.count != buffer.count {
            buffer = String(trimmedLeading)
        }
        guard !buffer.isEmpty else { return nil }

        let chars = Array(buffer)
        for index in chars.indices {
            let character = chars[index]
            let isSentenceEnd = character == "." || character == "!" || character == "?" || character == "\n"
            guard isSentenceEnd else { continue }
            let nextIsBoundary = index == chars.index(before: chars.endIndex)
                || chars[chars.index(after: index)].isWhitespace
            if nextIsBoundary && index >= 18 {
                let end = chars.index(after: index)
                let segment = String(chars[..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
                buffer = String(chars[end...]).trimmingCharacters(in: .whitespacesAndNewlines)
                return segment
            }
        }

        if chars.count >= 220 {
            let upper = min(chars.count - 1, 190)
            let lower = min(110, upper)
            if lower <= upper {
                for index in stride(from: upper, through: lower, by: -1) {
                    if chars[index].isWhitespace || chars[index] == "," || chars[index] == ";" || chars[index] == ":" {
                        let end = chars.index(after: index)
                        let segment = String(chars[..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
                        buffer = String(chars[end...]).trimmingCharacters(in: .whitespacesAndNewlines)
                        return segment
                    }
                }
            }
        }

        if flush {
            let segment = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
            buffer = ""
            return segment.isEmpty ? nil : segment
        }
        return nil
    }

    static func commandSilenceWindow(for command: String) -> TimeInterval {
        if needsExtendedDictation(command) {
            return 3.0
        }
        if command.count > 100 {
            return 1.65
        }
        return 1.15
    }

    static func needsExtendedDictation(_ command: String) -> Bool {
        let lower = command.lowercased()
        let cues = [
            "email", "e-mail", "email address", "address is", "my address",
            "gmail", "icloud", "outlook", "dot com", "dot net", "dot org",
            " at ", " underscore ", "spell", "spelling", "url", "website"
        ]
        return cues.contains(where: { lower.contains($0) })
    }

    static func confirmationCommand(from transcript: String) -> String? {
        let normalized = transcript
            .lowercased()
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
        guard !normalized.isEmpty else { return nil }

        if normalized == "confirm" || normalized == "yes confirm" || normalized == "confirm it" || normalized == "yes" {
            return "confirm"
        }
        if normalized == "cancel" || normalized == "no cancel" || normalized == "cancel it" || normalized == "no" {
            return "cancel"
        }
        return nil
    }

    static func responseRequestsConfirmation(_ response: String) -> Bool {
        let lower = response.lowercased()
        return lower.contains("say 'confirm'")
            || lower.contains("say “confirm”")
            || lower.contains("say confirm")
            || (lower.contains("confirm") && lower.contains("cancel"))
    }

    static func spokenResponse(for response: String) -> String {
        if responseRequestsConfirmation(response) {
            return "Ready, sir. Say confirm or cancel."
        }
        return response
    }
}

// MARK: - Local turn-by-turn navigation

@MainActor
final class JarvisNavigationController: NSObject, ObservableObject, CLLocationManagerDelegate {
    enum TravelMode: String {
        case driving
        case walking

        var transportType: MKDirectionsTransportType {
            switch self {
            case .driving: return .automobile
            case .walking: return .walking
            }
        }

        var mapsLaunchMode: String {
            switch self {
            case .driving: return MKLaunchOptionsDirectionsModeDriving
            case .walking: return MKLaunchOptionsDirectionsModeWalking
            }
        }

        var activityType: CLActivityType {
            switch self {
            case .driving: return .automotiveNavigation
            case .walking: return .fitness
            }
        }
    }

    @Published private(set) var isNavigating = false
    @Published private(set) var status = "Navigation idle"
    @Published private(set) var destinationName = ""
    @Published private(set) var destinationAddress = ""
    @Published private(set) var nextInstruction = ""
    @Published private(set) var distanceRemainingMeters: CLLocationDistance = 0
    @Published private(set) var expectedArrival: Date?
    @Published private(set) var travelMode: TravelMode = .driving
    @Published private(set) var lastRerouteAt: Date?

    private struct PendingGuidance {
        let text: String
        let createdAt: Date
        let routeRevision: Int
        let stepIndex: Int?
    }

    private unowned let appModel: JarvisAppModel
    private let locationManager = CLLocationManager()
    private var activeDestination: MKMapItem?
    private var activeRoute: MKRoute?
    private var steps: [MKRoute.Step] = []
    private var currentStepIndex = 0
    private var minDistanceToCurrentStep = CLLocationDistance.greatestFiniteMagnitude
    private var preparedStepIndex: Int?
    private var immediateStepIndex: Int?
    private var offRouteSamples = 0
    private var routeRevision = 0
    private var rerouteTask: Task<Void, Never>?
    private var guidanceTask: Task<Void, Never>?
    private var pendingGuidance: PendingGuidance?
    private var lastLocation: CLLocation?
    private var locationWaiter: CheckedContinuation<CLLocation?, Never>?
    private var locationRequestID: UUID?

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        locationManager.distanceFilter = 5
        locationManager.pausesLocationUpdatesAutomatically = false
    }

    func handle(_ rawCommand: String) async -> String? {
        let command = Self.normalize(rawCommand)

        if Self.isStopCommand(command) {
            guard isNavigating else { return "Navigation is not currently active." }
            stopNavigation(speakArrival: false)
            return "Navigation stopped."
        }
        if Self.isStatusCommand(command) { return navigationStatusText() }
        if Self.isNextTurnCommand(command) {
            guard isNavigating else { return "Navigation is not currently active." }
            if let distance = currentStepDistance(from: lastLocation) {
                return "Next: \(nextInstruction). \(Self.distancePhrase(distance)) away."
            }
            return nextInstruction.isEmpty ? "I am recalculating the next maneuver." : "Next: \(nextInstruction)."
        }
        if Self.isMapsHandoffCommand(command) {
            guard let activeDestination else { return "There is no active route to open in Apple Maps." }
            activeDestination.openInMaps(launchOptions: [
                MKLaunchOptionsDirectionsModeKey: travelMode.mapsLaunchMode,
                MKLaunchOptionsShowsTrafficKey: travelMode == .driving,
            ])
            return "I opened the active route to \(destinationName) in Apple Maps."
        }
        if Self.isRerouteCommand(command) {
            guard isNavigating, let activeDestination else { return "There is no active route to recalculate." }
            guard let origin = await currentLocation() else { return locationUnavailableMessage() }
            do {
                let route = try await calculateRoute(from: origin, to: activeDestination, mode: travelMode)
                activate(route: route, destination: activeDestination, mode: travelMode, announceFirstStepInResponse: false)
                lastRerouteAt = Date()
                return "Route recalculated. Next: \(nextInstruction)."
            } catch {
                status = "Reroute failed: \(error.localizedDescription)"
                return "I could not recalculate the route right now. The current route is still active."
            }
        }

        guard let request = Self.navigationRequest(from: command) else { return nil }
        var destinationQuery = request.destination.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !destinationQuery.isEmpty else { return "Tell me the destination after ‘take me to’." }

        // "Home" is a stable personal alias, not a MapKit search term. Resolve it
        // only from the explicit Personal Notecard and ask rather than guessing.
        if Self.isHomeDestination(destinationQuery) {
            guard let home = PersonalNotecardStore.shared.homeAddress else {
                return PersonalNotecardStore.shared.requestHomeAddress()
            }
            destinationQuery = home
        }

        status = "Resolving \(destinationQuery)…"
        guard let origin = await currentLocation() else { return locationUnavailableMessage() }

        do {
            let destination = try await resolveDestination(destinationQuery, near: origin)
            status = "Calculating route to \(destination.name ?? destinationQuery)…"
            do {
                let route = try await calculateRoute(from: origin, to: destination, mode: request.mode)
                activate(route: route, destination: destination, mode: request.mode, announceFirstStepInResponse: true)
                let eta = Date().addingTimeInterval(route.expectedTravelTime)
                expectedArrival = eta
                let resolved = destinationAddress.isEmpty ? destinationName : "\(destinationName), \(destinationAddress)"
                let first = nextInstruction.isEmpty ? "" : " First direction: \(nextInstruction)."
                return "Starting \(request.mode.rawValue) navigation to \(resolved). \(Self.distancePhrase(route.distance)), about \(Self.durationPhrase(route.expectedTravelTime)). ETA \(Self.timePhrase(eta)).\(first)"
            } catch {
                // A concrete destination has been resolved, so Apple Maps is a
                // safe continuity fallback if Jarvis's own route calculation fails.
                destination.openInMaps(launchOptions: [
                    MKLaunchOptionsDirectionsModeKey: request.mode.mapsLaunchMode,
                    MKLaunchOptionsShowsTrafficKey: request.mode == .driving,
                ])
                status = "Opened \(destination.name ?? destinationQuery) in Apple Maps"
                return "I found \(destination.name ?? destinationQuery), but could not calculate the route inside Jarvis, so I opened turn-by-turn directions in Apple Maps instead."
            }
        } catch let error as NavigationError {
            status = error.localizedDescription
            return error.localizedDescription
        } catch {
            status = "Navigation unavailable: \(error.localizedDescription)"
            return "I could not find a usable destination for \(destinationQuery) right now."
        }
    }

    private func activate(route: MKRoute, destination: MKMapItem, mode: TravelMode, announceFirstStepInResponse: Bool) {
        if guidanceTask != nil {
            guidanceTask?.cancel()
            guidanceTask = nil
            appModel.speechSynthesizer.stopSpeaking()
        }
        pendingGuidance = nil
        routeRevision += 1
        activeRoute = route
        activeDestination = destination
        travelMode = mode
        destinationName = destination.name?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty
            ?? destination.placemark.title?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty
            ?? "destination"
        destinationAddress = Self.address(for: destination)
        steps = route.steps.filter { !$0.instructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        currentStepIndex = 0
        minDistanceToCurrentStep = .greatestFiniteMagnitude
        preparedStepIndex = announceFirstStepInResponse && !steps.isEmpty ? 0 : nil
        immediateStepIndex = announceFirstStepInResponse && !steps.isEmpty ? 0 : nil
        offRouteSamples = 0
        distanceRemainingMeters = route.distance
        expectedArrival = Date().addingTimeInterval(route.expectedTravelTime)
        nextInstruction = steps.first?.instructions.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Continue on the route"
        isNavigating = true
        status = "Navigating to \(destinationName)"
        locationManager.activityType = mode.activityType
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        locationManager.distanceFilter = mode == .driving ? 8 : 4
        locationManager.pausesLocationUpdatesAutomatically = false
        locationManager.allowsBackgroundLocationUpdates = true
        locationManager.showsBackgroundLocationIndicator = true
        locationManager.startUpdatingLocation()
    }

    private func stopNavigation(speakArrival: Bool) {
        routeRevision += 1
        rerouteTask?.cancel()
        rerouteTask = nil
        if guidanceTask != nil { appModel.speechSynthesizer.stopSpeaking() }
        guidanceTask?.cancel()
        guidanceTask = nil
        pendingGuidance = nil
        locationManager.stopUpdatingLocation()
        locationManager.allowsBackgroundLocationUpdates = false
        locationManager.showsBackgroundLocationIndicator = false
        activeRoute = nil
        activeDestination = nil
        steps = []
        currentStepIndex = 0
        nextInstruction = ""
        distanceRemainingMeters = 0
        expectedArrival = nil
        offRouteSamples = 0
        isNavigating = false
        status = speakArrival ? "Arrived at \(destinationName)" : "Navigation idle"
    }

    private func currentLocation() async -> CLLocation? {
        if let lastLocation,
           Date().timeIntervalSince(lastLocation.timestamp) < 20,
           lastLocation.horizontalAccuracy >= 0,
           lastLocation.horizontalAccuracy <= 150 { return lastLocation }

        if locationManager.authorizationStatus == .notDetermined {
            locationManager.requestWhenInUseAuthorization()
            for _ in 0..<40 where locationManager.authorizationStatus == .notDetermined {
                try? await Task.sleep(for: .milliseconds(250))
            }
        }
        guard locationManager.authorizationStatus == .authorizedAlways || locationManager.authorizationStatus == .authorizedWhenInUse else { return nil }

        let requestID = UUID()
        locationRequestID = requestID
        return await withCheckedContinuation { continuation in
            locationWaiter = continuation
            locationManager.requestLocation()
            Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(8))
                guard let self, self.locationRequestID == requestID else { return }
                self.locationRequestID = nil
                let waiter = self.locationWaiter
                self.locationWaiter = nil
                waiter?.resume(returning: self.lastLocation)
            }
        }
    }

    private func resolveDestination(_ query: String, near origin: CLLocation) async throws -> MKMapItem {
        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = query
        request.region = MKCoordinateRegion(center: origin.coordinate, latitudinalMeters: 160_000, longitudinalMeters: 160_000)
        let response = try await MKLocalSearch(request: request).start()
        guard !response.mapItems.isEmpty else { throw NavigationError.destinationNotFound(query) }
        let normalizedQuery = Self.normalizeName(query)
        return response.mapItems.map { item -> (MKMapItem, Double) in
            let name = Self.normalizeName(item.name ?? "")
            let title = Self.normalizeName(item.placemark.title ?? "")
            var score = 0.0
            if name == normalizedQuery { score += 300 }
            if !name.isEmpty && (normalizedQuery.contains(name) || name.contains(normalizedQuery)) { score += 130 }
            if !title.isEmpty && title.contains(normalizedQuery) { score += 90 }
            let place = CLLocation(latitude: item.placemark.coordinate.latitude, longitude: item.placemark.coordinate.longitude)
            score -= min(origin.distance(from: place) / 1000, 500) * 0.35
            return (item, score)
        }.sorted { $0.1 > $1.1 }[0].0
    }

    private func calculateRoute(from origin: CLLocation, to destination: MKMapItem, mode: TravelMode) async throws -> MKRoute {
        let request = MKDirections.Request()
        request.source = MKMapItem(placemark: MKPlacemark(coordinate: origin.coordinate))
        request.destination = destination
        request.transportType = mode.transportType
        request.requestsAlternateRoutes = true
        let response = try await MKDirections(request: request).calculate()
        guard let route = response.routes.min(by: { $0.expectedTravelTime < $1.expectedTravelTime }) else {
            throw NavigationError.noRoute(destination.name ?? "destination")
        }
        return route
    }

    private func processLocation(_ location: CLLocation) {
        guard isNavigating, location.horizontalAccuracy >= 0, location.horizontalAccuracy <= 120,
              let route = activeRoute, let destination = activeDestination else { return }
        lastLocation = location
        let destinationLocation = CLLocation(latitude: destination.placemark.coordinate.latitude, longitude: destination.placemark.coordinate.longitude)
        let destinationDistance = location.distance(from: destinationLocation)
        if destinationDistance <= max(28, location.horizontalAccuracy * 1.2) {
            let arrivalName = destinationName
            stopNavigation(speakArrival: true)
            queueGuidance("You have arrived at \(arrivalName).")
            return
        }

        distanceRemainingMeters = max(0, approximateRemainingDistance(from: location, route: route))
        if route.distance > 1 {
            let remainingFraction = min(1, max(0, distanceRemainingMeters / route.distance))
            expectedArrival = Date().addingTimeInterval(max(30, route.expectedTravelTime * remainingFraction))
        }
        let offRouteDistance = Self.distance(from: location.coordinate, to: route.polyline)
        let allowedDeviation: CLLocationDistance = travelMode == .walking
            ? max(35, location.horizontalAccuracy * 2.0)
            : max(90, location.horizontalAccuracy * 2.2)
        offRouteSamples = offRouteDistance > allowedDeviation ? offRouteSamples + 1 : 0
        if offRouteSamples >= 3 {
            scheduleReroute(from: location)
            offRouteSamples = 0
        }

        guard !steps.isEmpty, currentStepIndex < steps.count else { return }
        let step = steps[currentStepIndex]
        let distance = Self.distanceToEnd(of: step, from: location)
        minDistanceToCurrentStep = min(minDistanceToCurrentStep, distance)
        nextInstruction = step.instructions.trimmingCharacters(in: .whitespacesAndNewlines)
        let prepareThreshold = preparationThreshold(speed: max(0, location.speed), mode: travelMode)
        let immediateThreshold = immediateThreshold(speed: max(0, location.speed), mode: travelMode)
        if preparedStepIndex != currentStepIndex, distance <= prepareThreshold, distance > immediateThreshold * 1.15 {
            preparedStepIndex = currentStepIndex
            queueGuidance(
                "In \(Self.distancePhrase(distance)), \(Self.lowercasedInstruction(nextInstruction)).",
                stepIndex: currentStepIndex
            )
        }
        if immediateStepIndex != currentStepIndex, distance <= immediateThreshold {
            immediateStepIndex = currentStepIndex
            queueGuidance(nextInstruction, stepIndex: currentStepIndex)
        }
        let passedManeuver = minDistanceToCurrentStep <= max(35, location.horizontalAccuracy * 1.2)
            && distance >= minDistanceToCurrentStep + max(35, location.horizontalAccuracy)
        if distance <= max(18, location.horizontalAccuracy * 0.8) || passedManeuver { advanceStep() }
    }

    private func advanceStep() {
        guard currentStepIndex + 1 < steps.count else { return }
        currentStepIndex += 1
        minDistanceToCurrentStep = .greatestFiniteMagnitude
        nextInstruction = steps[currentStepIndex].instructions.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func scheduleReroute(from location: CLLocation) {
        guard rerouteTask == nil, let destination = activeDestination,
              lastRerouteAt.map({ Date().timeIntervalSince($0) >= 20 }) ?? true else { return }
        status = "Off route • recalculating"
        queueGuidance("Rerouting.")
        rerouteTask = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.rerouteTask = nil }
            do {
                let route = try await self.calculateRoute(from: location, to: destination, mode: self.travelMode)
                self.activate(route: route, destination: destination, mode: self.travelMode, announceFirstStepInResponse: false)
                self.lastRerouteAt = Date()
                self.status = "Rerouted to \(self.destinationName)"
                if !self.nextInstruction.isEmpty { self.queueGuidance("New route. \(self.nextInstruction)") }
            } catch {
                self.status = "Reroute failed • continuing current route"
            }
        }
    }

    private func queueGuidance(_ raw: String, stepIndex: Int? = nil) {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, appModel.settings.speakResponses else { return }
        pendingGuidance = PendingGuidance(
            text: text,
            createdAt: Date(),
            routeRevision: routeRevision,
            stepIndex: stepIndex
        )
        guard guidanceTask == nil else { return }
        guidanceTask = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.guidanceTask = nil }
            while !Task.isCancelled {
                guard let pending = self.pendingGuidance else { return }
                if pending.routeRevision != self.routeRevision
                    || pending.stepIndex.map({ $0 != self.currentStepIndex }) == true
                    || Date().timeIntervalSince(pending.createdAt) > 18 {
                    self.pendingGuidance = nil
                    continue
                }
                let pushToTalkBusy = self.appModel.isListening && !self.appModel.handsFreeEnabled
                if self.appModel.isSending || pushToTalkBusy || self.appModel.speechSynthesizer.isSpeaking {
                    try? await Task.sleep(for: .milliseconds(250))
                    continue
                }
                self.pendingGuidance = nil
                await self.speakGuidance(pending.text)
            }
        }
    }

    private func speakGuidance(_ text: String) async {
        let wasHandsFree = appModel.handsFreeEnabled
        if wasHandsFree { appModel.stopWakeWordMode() }
        else if appModel.isListening || appModel.speechRecognizer.isActive {
            _ = appModel.speechRecognizer.stopListening()
            appModel.isListening = false
        }
        // Maneuver prompts always use on-device speech. Network TTS latency is not
        // acceptable for time-sensitive navigation instructions.
        await appModel.speechSynthesizer.speak(
            text,
            preferBluetooth: appModel.settings.preferBluetoothAudio,
            whisper: false
        )
        if wasHandsFree {
            try? await Task.sleep(for: .milliseconds(180))
            await appModel.startWakeWordMode()
        }
    }

    private func navigationStatusText() -> String {
        guard isNavigating else { return "Navigation is not currently active." }
        var parts = ["Navigating to \(destinationName)."]
        if distanceRemainingMeters > 0 { parts.append("About \(Self.distancePhrase(distanceRemainingMeters)) remaining.") }
        if let expectedArrival { parts.append("ETA \(Self.timePhrase(expectedArrival)).") }
        if !nextInstruction.isEmpty { parts.append("Next: \(nextInstruction).") }
        return parts.joined(separator: " ")
    }

    private func currentStepDistance(from location: CLLocation?) -> CLLocationDistance? {
        guard let location, currentStepIndex < steps.count else { return nil }
        return Self.distanceToEnd(of: steps[currentStepIndex], from: location)
    }

    private func approximateRemainingDistance(from location: CLLocation, route: MKRoute) -> CLLocationDistance {
        guard !steps.isEmpty, currentStepIndex < steps.count else {
            let destination = route.steps.last.flatMap { Self.finalCoordinate(of: $0.polyline) } ?? route.polyline.coordinate
            return CLLocation(latitude: destination.latitude, longitude: destination.longitude).distance(from: location)
        }
        return Self.distanceToEnd(of: steps[currentStepIndex], from: location)
            + steps.dropFirst(currentStepIndex + 1).reduce(0.0) { $0 + $1.distance }
    }

    private func preparationThreshold(speed: CLLocationSpeed, mode: TravelMode) -> CLLocationDistance {
        switch mode {
        case .walking: return 85
        case .driving:
            if speed >= 24 { return 900 }
            if speed >= 15 { return 550 }
            return 300
        }
    }

    private func immediateThreshold(speed: CLLocationSpeed, mode: TravelMode) -> CLLocationDistance {
        switch mode {
        case .walking: return 22
        case .driving:
            if speed >= 24 { return 180 }
            if speed >= 15 { return 110 }
            return 65
        }
    }

    private func locationUnavailableMessage() -> String {
        switch locationManager.authorizationStatus {
        case .denied, .restricted:
            status = "Location permission required"
            return "I need iPhone location permission to start turn-by-turn navigation. Enable Location for Jarvis in Settings, then ask again."
        default:
            status = "Current location unavailable"
            return "I could not get a reliable current location yet. Try again when the iPhone has a GPS fix."
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            if manager.authorizationStatus == .authorizedAlways || manager.authorizationStatus == .authorizedWhenInUse {
                status = isNavigating ? "Navigating to \(destinationName)" : "Location ready for navigation"
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        Task { @MainActor in
            lastLocation = location
            if let waiter = locationWaiter {
                locationWaiter = nil
                locationRequestID = nil
                waiter.resume(returning: location)
            }
            processLocation(location)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            if let waiter = locationWaiter {
                locationWaiter = nil
                locationRequestID = nil
                waiter.resume(returning: lastLocation)
            }
            if isNavigating { status = "Navigation location warning: \(error.localizedDescription)" }
        }
    }

    private static func navigationRequest(from normalizedCommand: String) -> (destination: String, mode: TravelMode)? {
        let directHome: [(String, TravelMode)] = [
            ("take me home", .driving),
            ("drive me home", .driving),
            ("get me home", .driving),
            ("navigate home", .driving),
            ("directions home", .driving),
            ("walk me home", .walking),
            ("walk home", .walking),
        ]
        if let match = directHome.first(where: { normalizedCommand == $0.0 }) {
            return ("home", match.1)
        }

        let patterns: [(String, TravelMode)] = [
            ("take me to ", .driving), ("navigate me to ", .driving), ("navigate to ", .driving),
            ("drive me to ", .driving), ("drive to ", .driving), ("get me to ", .driving),
            ("directions to ", .driving), ("walk me to ", .walking), ("walk to ", .walking),
            ("walking directions to ", .walking),
        ]
        for (prefix, mode) in patterns where normalizedCommand.hasPrefix(prefix) {
            return (String(normalizedCommand.dropFirst(prefix.count)), mode)
        }
        return nil
    }

    static func isNavigationIntent(_ raw: String) -> Bool {
        let n = normalize(raw)
        return navigationRequest(from: n) != nil || isStopCommand(n) || isStatusCommand(n)
            || isNextTurnCommand(n) || isMapsHandoffCommand(n) || isRerouteCommand(n)
    }

    private static func isHomeDestination(_ raw: String) -> Bool {
        ["home", "my home", "home address", "my home address"].contains(normalizeName(raw))
    }

    private static func isStopCommand(_ n: String) -> Bool {
        ["stop navigation", "cancel navigation", "end navigation", "stop directions", "cancel directions"].contains(n)
    }
    private static func isStatusCommand(_ n: String) -> Bool {
        ["navigation status", "where are we going", "how much farther", "how much further", "what is our eta", "what's our eta", "eta"].contains(n)
    }
    private static func isNextTurnCommand(_ n: String) -> Bool {
        ["next turn", "what is the next turn", "what's the next turn", "next direction", "what do i do next on this route"].contains(n)
    }
    private static func isMapsHandoffCommand(_ n: String) -> Bool {
        ["open route in maps", "open this route in maps", "open in apple maps", "show route in apple maps"].contains(n)
    }
    private static func isRerouteCommand(_ n: String) -> Bool {
        ["reroute", "recalculate route", "recalculate navigation", "find another route"].contains(n)
    }
    private static func normalize(_ raw: String) -> String {
        raw.lowercased().replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
    }
    private static func normalizeName(_ raw: String) -> String {
        raw.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }.joined(separator: " ")
    }
    private static func address(for item: MKMapItem) -> String {
        let placemark = item.placemark
        let street = [placemark.subThoroughfare, placemark.thoroughfare]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty }.joined(separator: " ")
        let cityLine = [placemark.locality, placemark.administrativeArea, placemark.postalCode]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty }.joined(separator: ", ")
        return [street, cityLine].filter { !$0.isEmpty }.joined(separator: ", ")
    }
    private static func distanceToEnd(of step: MKRoute.Step, from location: CLLocation) -> CLLocationDistance {
        guard let coordinate = finalCoordinate(of: step.polyline) else { return step.distance }
        return location.distance(from: CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude))
    }
    private static func finalCoordinate(of polyline: MKPolyline) -> CLLocationCoordinate2D? {
        guard polyline.pointCount > 0 else { return nil }
        return polyline.points()[polyline.pointCount - 1].coordinate
    }
    private static func distance(from coordinate: CLLocationCoordinate2D, to polyline: MKPolyline) -> CLLocationDistance {
        guard polyline.pointCount > 0 else { return .greatestFiniteMagnitude }
        let target = MKMapPoint(coordinate)
        let points = polyline.points()
        if polyline.pointCount == 1 { return target.distance(to: points[0]) }
        var minimum = CLLocationDistance.greatestFiniteMagnitude
        for index in 0..<(polyline.pointCount - 1) {
            minimum = min(minimum, pointToSegmentDistance(target, points[index], points[index + 1]))
        }
        return minimum
    }
    private static func pointToSegmentDistance(_ point: MKMapPoint, _ a: MKMapPoint, _ b: MKMapPoint) -> CLLocationDistance {
        let dx = b.x - a.x, dy = b.y - a.y
        let lengthSquared = dx * dx + dy * dy
        if lengthSquared <= 0 { return point.distance(to: a) }
        let t = max(0, min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSquared))
        return point.distance(to: MKMapPoint(x: a.x + t * dx, y: a.y + t * dy))
    }
    private static func distancePhrase(_ meters: CLLocationDistance) -> String {
        let miles = meters / 1609.344
        if miles >= 10 { return "\(Int(miles.rounded())) miles" }
        if miles >= 0.2 { return String(format: "%.1f miles", miles) }
        return "\(max(10, Int((meters * 3.28084 / 10).rounded() * 10))) feet"
    }
    private static func durationPhrase(_ seconds: TimeInterval) -> String {
        let minutes = max(1, Int((seconds / 60).rounded()))
        if minutes < 60 { return "\(minutes) minutes" }
        let hours = minutes / 60, remainder = minutes % 60
        if remainder == 0 { return hours == 1 ? "1 hour" : "\(hours) hours" }
        return "\(hours) hour\(hours == 1 ? "" : "s") \(remainder) minutes"
    }
    private static func timePhrase(_ date: Date) -> String { date.formatted(date: .omitted, time: .shortened) }
    private static func lowercasedInstruction(_ instruction: String) -> String {
        guard let first = instruction.first else { return instruction }
        return first.lowercased() + instruction.dropFirst()
    }

    enum NavigationError: LocalizedError {
        case destinationNotFound(String)
        case noRoute(String)
        var errorDescription: String? {
            switch self {
            case .destinationNotFound(let query):
                return "I could not find a destination matching \(query). Try a business name plus city, or a street address."
            case .noRoute(let destination):
                return "I found \(destination), but MapKit could not calculate a route from your current location."
            }
        }
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}
