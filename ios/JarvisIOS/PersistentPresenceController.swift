import CoreLocation
import Foundation
import HealthKit
import UIKit
import UserNotifications

@MainActor
final class HealthContextManager: ObservableObject {
    @Published private(set) var status = "Off"
    @Published private(set) var heartRateBPM: Double?
    @Published private(set) var hrvMS: Double?
    @Published private(set) var sleepHours: Double?
    @Published private(set) var lastUpdated: Date?

    private let store = HKHealthStore()
    private var authorizationAttempted = false
    private var lastRefresh = Date.distantPast

    func refreshIfEnabled(_ enabled: Bool) async {
        guard enabled else {
            status = "Off"
            return
        }
        guard HKHealthStore.isHealthDataAvailable() else {
            status = "Health data unavailable"
            return
        }
        if !authorizationAttempted {
            authorizationAttempted = true
            do {
                let heart = HKObjectType.quantityType(forIdentifier: .heartRate)!
                let hrv = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN)!
                let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!
                try await store.requestAuthorization(toShare: [], read: [heart, hrv, sleep])
            } catch {
                status = "Health permission unavailable"
                return
            }
        }
        guard Date().timeIntervalSince(lastRefresh) >= 60 else { return }
        lastRefresh = Date()
        status = "Refreshing…"

        if let heartType = HKObjectType.quantityType(forIdentifier: .heartRate),
           let sample = await latestQuantitySample(heartType) {
            heartRateBPM = sample.quantity.doubleValue(for: HKUnit.count().unitDivided(by: .minute()))
        }
        if let hrvType = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN),
           let sample = await latestQuantitySample(hrvType) {
            hrvMS = sample.quantity.doubleValue(for: HKUnit.secondUnit(with: .milli))
        }
        if let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) {
            sleepHours = await recentSleepHours(sleepType)
        }
        lastUpdated = Date()
        status = "Connected"
    }

    private func latestQuantitySample(_ type: HKQuantityType) async -> HKQuantitySample? {
        await withCheckedContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: type,
                predicate: nil,
                limit: 1,
                sortDescriptors: [NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)]
            ) { _, samples, _ in
                continuation.resume(returning: samples?.first as? HKQuantitySample)
            }
            store.execute(query)
        }
    }

    private func recentSleepHours(_ type: HKCategoryType) async -> Double? {
        let start = Date().addingTimeInterval(-36 * 3600)
        let predicate = HKQuery.predicateForSamples(withStart: start, end: Date(), options: .strictEndDate)
        let samples: [HKCategorySample] = await withCheckedContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: type,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: nil
            ) { _, values, _ in
                continuation.resume(returning: (values as? [HKCategorySample]) ?? [])
            }
            store.execute(query)
        }
        let asleepValues: Set<Int> = [
            HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue,
            HKCategoryValueSleepAnalysis.asleepCore.rawValue,
            HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
            HKCategoryValueSleepAnalysis.asleepREM.rawValue,
        ]
        let seconds = samples
            .filter { asleepValues.contains($0.value) }
            .reduce(0.0) { $0 + $1.endDate.timeIntervalSince($1.startDate) }
        guard seconds > 0 else { return nil }
        return min(16.0, seconds / 3600.0)
    }

    var environmentPayload: [String: Any] {
        var payload: [String: Any] = ["enabled": status != "Off"]
        if let heartRateBPM { payload["heart_rate_bpm"] = Int(round(heartRateBPM)) }
        if let hrvMS { payload["hrv_ms"] = Int(round(hrvMS)) }
        if let sleepHours { payload["sleep_hours"] = (sleepHours * 10).rounded() / 10 }
        if let lastUpdated { payload["updated_at"] = ISO8601DateFormatter().string(from: lastUpdated) }
        return payload
    }
}

@MainActor
final class PersistentPresenceController: ObservableObject {
    @Published private(set) var companionStatus = "Stopped"
    @Published private(set) var activeServerURL = ""
    @Published private(set) var visionStatus = "Off"
    @Published private(set) var lastVisionScene = ""
    @Published private(set) var lastProactiveMessage = ""

    let healthContext = HealthContextManager()
    private weak var frontend: FrontendIntelligenceController?
    private var lastHomeStateObservedAt = Date.distantPast
    private var lastKnownHomeState: Bool?
    private var lastObservedAmbientSoundAt = Date.distantPast
    private var pendingDoorbellAt: Date?
    private var pendingDoorbellConfidence = 0.0

    private unowned let appModel: JarvisAppModel
    private let companion: CompanionConnection
    private let cuePlayer: AmbientCuePlayer
    private var reconnectTask: Task<Void, Never>?
    private var visionTask: Task<Void, Never>?
    private var interactionCueTask: Task<Void, Never>?
    private var started = false
    private var locationLabel = "unknown"
    private var profileLabel = "default"
    private var announcing = false
    private var pendingAnnouncements: [(String, String)] = []
    private var lastObservedResponse = ""
    private var responseCompletionPending = false
    private let worldArmorLiveSeqKey = "jarvis.worldArmorLive.lastSeq"
    private var processedWorldArmorPresence: Set<String> = []
    private var lastWorldArmorPushSync = Date.distantPast
    private var registeredWorldArmorPushToken: String?

    init(appModel: JarvisAppModel) {
        self.appModel = appModel
        companion = CompanionConnection()
        cuePlayer = AmbientCuePlayer(audioRouteManager: appModel.audioRouteManager)

        companion.onEvent = { [weak self] event in
            Task { @MainActor in
                await self?.handleCompanionEvent(event)
            }
        }

        // Glasses-return greetings intentionally are not owned here. The frontend
        // operations layer has the one authoritative WelcomeBackCoordinator. Keeping
        // the callback out of Persistent Presence removes the startup race where two
        // different controllers could greet from the same DAT availability change.

        appModel.geofenceManager.onHomeStateChanged = { [weak self] isHome in
            Task { @MainActor in
                guard let self else { return }
                let genuineArrival = self.lastKnownHomeState == false && isHome
                self.lastKnownHomeState = isHome
                self.locationLabel = isHome ? "home" : "away"
                self.lastHomeStateObservedAt = Date()
                if self.appModel.settings.geofencedProfilesEnabled {
                    self.profileLabel = isHome ? "home" : "mobile"
                }
                if !isHome {
                    _ = try? await self.client.event("home_departure")
                }
                await self.sendEnvironmentState()
                if genuineArrival,
                   UIApplication.shared.applicationState == .active,
                   self.appModel.settings.sensorOpportunitiesEnabled,
                   self.appModel.settings.localSensorContextEnabled,
                   self.appModel.settings.geofencedProfilesEnabled,
                   self.hasFreshHomeFix() {
                    // Strictly enrolled light IDs and HomeKit readback live in
                    // HomeEnvironmentController. The model cannot expand scope.
                    let outcomes = await self.appModel.homeEnvironment.runPreapprovedArrivalActions()
                    self.reportLocalIntervention(outcomes)
                }
            }
        }
    }

    func attach(frontend: FrontendIntelligenceController) {
        self.frontend = frontend
    }

    private func hasFreshHomeFix() -> Bool {
        guard let sensors = frontend?.sensors,
              let observed = sensors.lastLocationAt,
              Date().timeIntervalSince(observed) <= 120,
              let coordinate = sensors.coordinate,
              appModel.settings.homeLatitude != 0 || appModel.settings.homeLongitude != 0 else {
            return false
        }
        let home = CLLocation(latitude: appModel.settings.homeLatitude,
                              longitude: appModel.settings.homeLongitude)
        let phone = CLLocation(latitude: coordinate.latitude,
                               longitude: coordinate.longitude)
        return phone.distance(from: home) <= max(50, appModel.settings.homeRadius)
    }

    /// The acoustic intervention path is independent of the companion socket,
    /// the camera, the LLM and the glasses HUD. Two distinct on-device
    /// classifications, a current home-position fix, and a per-device grant
    /// must all agree before the reversible light action is even attempted.
    func clearAmbientOpportunityEvidence() {
        pendingDoorbellAt = nil
    }

    func observeAmbientSound() async {
        guard appModel.settings.sensorOpportunitiesEnabled,
              appModel.settings.soundRecognitionEnabled,
              appModel.settings.localSensorContextEnabled,
              appModel.settings.geofencedProfilesEnabled,
              UIApplication.shared.applicationState == .active,
              !conversationActive,
              !frontendMeetingActive,
              (!appModel.speechRecognizer.isActive
                  || (appModel.handsFreeEnabled
                      && appModel.voiceStatus == "Listening for “Jarvis”…")),
              appModel.voiceStatus != "Speaking offline…",
              let frontend,
              let observed = frontend.sensors.lastLocationAt,
              Date().timeIntervalSince(observed) <= 120,
              lastKnownHomeState == true, locationLabel == "home",
              appModel.settings.homeLatitude != 0 || appModel.settings.homeLongitude != 0,
              let coordinate = frontend.sensors.coordinate else {
            pendingDoorbellAt = nil
            return
        }
        guard frontend.sensors.activity != "Driving" else {
            pendingDoorbellAt = nil
            return
        }
        let configured = CLLocation(latitude: appModel.settings.homeLatitude,
                                    longitude: appModel.settings.homeLongitude)
        let current = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)
        guard current.distance(from: configured) <= max(50, appModel.settings.homeRadius) else {
            pendingDoorbellAt = nil
            return
        }
        guard let sound = LocalSoundClassifier.shared.latestEvent(maxAge: 5),
              sound.timestamp > lastObservedAmbientSoundAt else { return }
        lastObservedAmbientSoundAt = sound.timestamp
        let id = sound.identifier.lowercased().replacingOccurrences(of: "-", with: "_")
        guard id == "doorbell" || id == "door_bell", sound.confidence >= 0.90 else {
            if let previous = pendingDoorbellAt,
               sound.timestamp.timeIntervalSince(previous) > 10 {
                pendingDoorbellAt = nil
            }
            return
        }
        guard let previous = pendingDoorbellAt,
              sound.timestamp.timeIntervalSince(previous) >= 0.5,
              sound.timestamp.timeIntervalSince(previous) <= 10 else {
            pendingDoorbellAt = sound.timestamp
            pendingDoorbellConfidence = sound.confidence
            return
        }
        let confidence = min(sound.confidence, pendingDoorbellConfidence)
        pendingDoorbellAt = nil
        let outcomes = await appModel.homeEnvironment.runPreapprovedDoorbellActions(
            confidence: confidence
        )
        reportLocalIntervention(outcomes)
    }

    private func reportLocalIntervention(_ outcomes: [String]) {
        guard !outcomes.isEmpty else { return }
        let text = outcomes.joined(separator: " ")
        lastProactiveMessage = text
        let verified = outcomes.allSatisfy { $0.hasPrefix("Verified in Apple Home:") }
        // This is an *actual local readback*, not a fabricated cloud-agent
        // completion. Optional HUD display never approves another action.
        appModel.memoMind.presentProactiveAlert(
            text, severity: verified ? "info" : "warning"
        )
        if appModel.settings.ambientCuesEnabled {
            cuePlayer.play(
                verified ? "task_complete" : "error",
                preferBluetooth: appModel.settings.preferBluetoothAudio
            )
        }
    }

    private var frontendMeetingActive: Bool { frontend?.isMeetingActive ?? false }

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    private func syncWorldArmorRemotePushIfNeeded(force: Bool = false) async {
        let now = Date()
        guard force || now.timeIntervalSince(lastWorldArmorPushSync) >= 30 else {
            return
        }
        lastWorldArmorPushSync = now
        let defaults = UserDefaults.standard
        let token = defaults.string(
            forKey: WorldArmorPushAppDelegate.tokenKey
        )?.trimmingCharacters(in: .whitespacesAndNewlines)

        guard appModel.settings.worldArmorLiveAlertsEnabled else {
            if let token, !token.isEmpty,
               registeredWorldArmorPushToken != nil {
                _ = try? await client.worldArmorPushUnregister(token)
            }
            registeredWorldArmorPushToken = nil
            return
        }

        let center = UNUserNotificationCenter.current()
        var settings = await center.notificationSettings()
        if settings.authorizationStatus == .notDetermined {
            _ = try? await center.requestAuthorization(
                options: [.alert, .sound, .badge]
            )
            settings = await center.notificationSettings()
        }
        guard settings.authorizationStatus == .authorized
                || settings.authorizationStatus == .provisional
                || settings.authorizationStatus == .ephemeral else {
            return
        }

        UIApplication.shared.registerForRemoteNotifications()
        guard let token, !token.isEmpty else { return }
        guard force || registeredWorldArmorPushToken != token else { return }
        do {
            let registration = try await client.worldArmorPushRegister(token)
            if registration.enabled {
                registeredWorldArmorPushToken = token
            }
        } catch {
            // Reconnect loop retries. Local/live-socket notification delivery
            // remains available and the durable event journal is authoritative.
        }
    }

    private var usingRemotePath: Bool {
        guard !companion.activeServerURL.isEmpty else { return false }
        return companion.activeServerURL != appModel.settings.baseURL
    }

    private var conversationActive: Bool {
        if appModel.isSending || appModel.speechSynthesizer.isSpeaking { return true }
        let activeStatuses = [
            "Listening for command…",
            "Listening for follow-up…",
            "Say confirm or cancel",
            "Thinking…",
            "Speaking…",
        ]
        return activeStatuses.contains(appModel.voiceStatus)
    }

    func start() async {
        guard !started else { return }
        started = true
        companionStatus = "Connecting"
        lastObservedResponse = appModel.lastResponse
        responseCompletionPending = false
        await syncWorldArmorRemotePushIfNeeded(force: true)

        reconnectTask = Task { [weak self] in
            guard let self else { return }
            await self.reconnectLoop()
        }
        visionTask = Task { [weak self] in
            guard let self else { return }
            await self.visionLoop()
        }
        interactionCueTask = Task { [weak self] in
            guard let self else { return }
            await self.interactionCueLoop()
        }
    }

    func stop() {
        started = false
        reconnectTask?.cancel()
        visionTask?.cancel()
        interactionCueTask?.cancel()
        reconnectTask = nil
        visionTask = nil
        interactionCueTask = nil
        cuePlayer.stopThinking()
        companion.disconnect()
        companionStatus = "Stopped"
        visionStatus = "Off"
    }

    func requestSilentScan() async {
        guard companion.isConnected else {
            visionStatus = "Waiting for server"
            return
        }
        if appModel.metaGlasses.streamState == "Stopped" {
            visionStatus = "Starting glasses camera"
            await appModel.metaGlasses.startStream()
            try? await Task.sleep(for: .milliseconds(450))
        }
        guard let frame = appModel.metaGlasses.currentFrame,
              let jpeg = Self.sampledJPEG(from: frame, maxDimension: 640, quality: 0.45) else {
            visionStatus = appModel.metaGlasses.cameraMasterEnabled
                ? "No glasses frame available"
                : "Camera stopped by user"
            return
        }
        do {
            if appModel.settings.ambientCuesEnabled {
                cuePlayer.play("vision_scan", preferBluetooth: appModel.settings.preferBluetoothAudio)
            }
            try await companion.sendFrame(jpeg)
            visionStatus = "Silent scan sent"
        } catch {
            visionStatus = "Scan failed"
            companion.disconnect()
        }
    }

    private func interactionCueLoop() async {
        while !Task.isCancelled && started {
            let response = appModel.lastResponse.trimmingCharacters(in: .whitespacesAndNewlines)
            if response != lastObservedResponse {
                lastObservedResponse = response
                if !response.isEmpty {
                    responseCompletionPending = true
                }
            }

            let stillProducingOrSpeaking = appModel.isSending
                || appModel.speechSynthesizer.isSpeaking
                || appModel.voiceStatus == "Speaking…"
                || appModel.voiceStatus == "Speaking offline…"

            if responseCompletionPending && !stillProducingOrSpeaking {
                responseCompletionPending = false
                if appModel.settings.ambientCuesEnabled {
                    cuePlayer.play("response_complete", preferBluetooth: appModel.settings.preferBluetoothAudio)
                }
            }

            try? await Task.sleep(for: .milliseconds(100))
        }
    }

    private func reconnectLoop() async {
        while !Task.isCancelled && started {
            await healthContext.refreshIfEnabled(appModel.settings.healthContextEnabled)
            await syncWorldArmorRemotePushIfNeeded()
            if !companion.isConnected {
                do {
                    try await companion.connect(client: client)
                    activeServerURL = companion.activeServerURL
                    companionStatus = activeServerURL == appModel.settings.baseURL
                        ? "Connected over LAN"
                        : "Connected over Tailscale"
                    await sendEnvironmentState()
                    await replayWorldArmorLiveEvents()
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
            try? await Task.sleep(for: .seconds(2))
        }
    }

    private func visionLoop() async {
        while !Task.isCancelled && started {
            guard appModel.settings.passiveVisionEnabled else {
                visionStatus = "Off"
                try? await Task.sleep(for: .seconds(1))
                continue
            }
            guard appModel.metaGlasses.cameraMasterEnabled else {
                visionStatus = "Camera stopped by user"
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

            let throttled = usingRemotePath && appModel.settings.adaptiveBandwidthEnabled
            let maxDimension: CGFloat = throttled ? 384 : 512
            let quality: CGFloat = throttled ? 0.26 : 0.35
            let interval: Duration = throttled ? .seconds(3) : .seconds(1)

            if let frame = appModel.metaGlasses.currentFrame,
               let jpeg = Self.sampledJPEG(from: frame, maxDimension: maxDimension, quality: quality) {
                do {
                    try await companion.sendFrame(jpeg)
                    if throttled {
                        visionStatus = "Remote • bandwidth-saving sampling"
                    } else if visionStatus == "Starting glasses camera" || visionStatus == "Waiting for frame" {
                        visionStatus = "Frame sent to PC"
                    }
                } catch {
                    visionStatus = "Reconnect pending"
                    companion.disconnect()
                }
            } else {
                visionStatus = "Waiting for frame"
            }
            try? await Task.sleep(for: interval)
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

        let whisper = appModel.settings.adaptiveWhisperEnabled
            && JarvisAudioEnvironment.noiseFloorDBFS <= appModel.settings.whisperThresholdDBFS

        let audioState: [String: Any] = [
            "ambient_dbfs": Int(round(JarvisAudioEnvironment.noiseFloorDBFS)),
            "whisper_mode": whisper,
            "subvocal_mode": appModel.settings.subvocalModeEnabled,
            "conversation_active": conversationActive,
        ]

        let healthState: [String: Any]
        if appModel.settings.healthContextEnabled {
            healthState = healthContext.environmentPayload
        } else {
            healthState = ["enabled": false]
        }

        let preferenceState: [String: Any] = [
            "proactive_threshold": appModel.settings.proactiveThreshold,
            "smart_audio_damping": appModel.settings.smartAudioDampingEnabled,
            "daily_journal": appModel.settings.dailyJournalEnabled,
            "adaptive_bandwidth": appModel.settings.adaptiveBandwidthEnabled,
        ]

        let deviceState: [String: Any] = [
            "ray_ban_meta": rayBanState,
            "passive_vision": appModel.settings.passiveVisionEnabled,
            "camera_master_enabled": appModel.metaGlasses.cameraMasterEnabled,
            "companion_endpoint": companion.activeServerURL,
            "remote_transport": usingRemotePath,
        ]

        let activeProfile = appModel.settings.geofencedProfilesEnabled ? profileLabel : "default"
        var environment: [String: Any] = [:]
        environment["location"] = locationLabel
        environment["active_profile"] = activeProfile
        environment["project_focus"] = appModel.settings.projectFocus
        environment["audio"] = audioState
        environment["health"] = healthState
        environment["preferences"] = preferenceState
        environment["devices"] = deviceState

        // The MemoMind interface needs no camera. Independently opted-in
        // microphone classifications, motion and GPS/geofence metadata reuse
        // the already authenticated companion link, with no raw audio, image,
        // transcript or biometric measurements in this transient snapshot.
        var opportunity: [String: Any] = [
            "source_id": appModel.settings.conversationSessionID,
            "enabled": appModel.settings.sensorOpportunitiesEnabled
        ]
        if appModel.settings.sensorOpportunitiesEnabled {
            let formatter = ISO8601DateFormatter()
            let now = Date()
            opportunity["observed_at"] = formatter.string(from: now)
            opportunity["weather_opt_in"] = appModel.settings.weatherContextEnabled
                && appModel.settings.localSensorContextEnabled
            opportunity["audio"] = ["conversation_active": conversationActive]

            if appModel.settings.localSensorContextEnabled, let sensors = frontend?.sensors {
                if let observed = sensors.lastMotionAt, now.timeIntervalSince(observed) <= 90 {
                    var motion: [String: Any] = ["activity": sensors.activity.lowercased()]
                    if let speed = sensors.speedMPS, speed.isFinite, speed >= 0 {
                        motion["speed_mps"] = speed
                    }
                    motion["observed_at"] = formatter.string(from: observed)
                    opportunity["motion"] = motion
                }
                var location: [String: Any] = [:]
                if let coordinates = sensors.coordinate,
                   let observed = sensors.lastLocationAt,
                   now.timeIntervalSince(observed) <= 120,
                   coordinates.latitude.isFinite, coordinates.longitude.isFinite {
                    // ~100-m resolution suffices for contextual opportunities.
                    location["latitude"] = (coordinates.latitude * 1_000).rounded() / 1_000
                    location["longitude"] = (coordinates.longitude * 1_000).rounded() / 1_000
                    location["observed_at"] = formatter.string(from: observed)
                }
                if appModel.settings.geofencedProfilesEnabled,
                   lastHomeStateObservedAt != .distantPast,
                   let fix = sensors.lastLocationAt,
                   now.timeIntervalSince(fix) <= 120,
                   locationLabel == "home" || locationLabel == "away" {
                    // The latest valid location fix refreshes a stable geofence
                    // state without requiring another arrival callback.
                    location["home_state"] = locationLabel
                    location["home_observed_at"] = formatter.string(from: fix)
                }
                if !location.isEmpty { opportunity["location"] = location }
            }
            if appModel.settings.soundRecognitionEnabled,
               let sound = LocalSoundClassifier.shared.latestEvent(maxAge: 8) {
                opportunity["sound"] = [
                    "identifier": sound.identifier,
                    "confidence": sound.confidence,
                    "observed_at": formatter.string(from: sound.timestamp)
                ]
            }
        }
        environment["sensor_snapshot"] = opportunity
        environment["guardian_snapshot"] = [
            "source_id": appModel.settings.conversationSessionID,
            "enabled": appModel.settings.guardianEnabled
                && UIApplication.shared.applicationState == .active,
            "busy": conversationActive || frontend?.isMeetingActive == true
                || !appModel.settings.localSensorContextEnabled
                || frontend?.sensors.lastMotionAt.map {
                    Date().timeIntervalSince($0) > 90
                } != false
                || frontend?.sensors.activity == "Driving",
            "observed_at": ISO8601DateFormatter().string(from: Date())
        ]

        do {
            try await companion.sendEnvironment(environment)
        } catch {
            companion.disconnect()
        }
    }

    private func thresholdRank(_ value: String) -> Int {
        switch value.lowercased() {
        case "urgent": return 3
        case "warning": return 2
        case "info": return 1
        default: return 0
        }
    }

    private func proactiveAlertMeetsThreshold(_ severity: String) -> Bool {
        thresholdRank(severity) >= thresholdRank(appModel.settings.proactiveThreshold)
    }

    private func rememberWorldArmorSeq(_ seq: Int) {
        let defaults = UserDefaults.standard
        let prior = defaults.integer(forKey: worldArmorLiveSeqKey)
        if seq > prior {
            defaults.set(seq, forKey: worldArmorLiveSeqKey)
        }
    }

    private func replayWorldArmorLiveEvents() async {
        var cursor = UserDefaults.standard.integer(forKey: worldArmorLiveSeqKey)
        var pages = 0
        while pages < 5 {
            pages += 1
            guard let response = try? await client.worldArmorLiveEvents(
                afterSeq: cursor, limit: 100
            ) else { return }
            for row in response.events {
                if row.seq <= cursor { continue }
                await handleWorldArmorEvent(row, replayed: true)
                cursor = max(cursor, row.seq)
                rememberWorldArmorSeq(cursor)
            }
            if !response.truncated || response.events.isEmpty { return }
        }
    }

    private func deliverWorldArmorLocalNotification(
        message: String, priority: String
    ) async {
        guard appModel.settings.worldArmorLiveAlertsEnabled,
              !message.isEmpty else { return }
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        if settings.authorizationStatus == .notDetermined {
            _ = try? await center.requestAuthorization(options: [.alert, .sound])
        }
        let updated = await center.notificationSettings()
        guard updated.authorizationStatus == .authorized
                || updated.authorizationStatus == .provisional else { return }
        let content = UNMutableNotificationContent()
        content.title = priority == "urgent"
            ? "World Armor urgent"
            : "World Armor"
        content.body = message
        content.sound = .default
        let request = UNNotificationRequest(
            identifier: "world-armor-" + UUID().uuidString,
            content: content, trigger: nil
        )
        try? await center.add(request)
    }

    private func handleWorldArmorEvent(
        _ worldEvent: ArmorLiveEvent, replayed: Bool
    ) async {
        let prior = UserDefaults.standard.integer(forKey: worldArmorLiveSeqKey)
        if !replayed && worldEvent.seq <= prior { return }
        rememberWorldArmorSeq(worldEvent.seq)

        let priority = worldEvent.priority.lowercased()
        let message = Self.collapseRepeatedSir(worldEvent.summary)
        guard priority == "warning" || priority == "urgent",
              !message.isEmpty else { return }

        lastProactiveMessage = message
        appModel.memoMind.presentProactiveAlert(message, severity: priority)
        if appModel.settings.worldArmorLiveAlertsEnabled {
            await deliverWorldArmorLocalNotification(
                message: message, priority: priority
            )
        }
        if appModel.settings.proactiveAnnouncements,
           proactiveAlertMeetsThreshold(priority),
           UIApplication.shared.applicationState == .active {
            pendingAnnouncements.append((message, "attention"))
            await drainAnnouncements()
        }
    }

    private func handleCompanionEvent(_ event: [String: Any]) async {
        let type = String(describing: event["type"] ?? "")
        let cue = String(describing: event["cue"] ?? "attention")
        let message = Self.collapseRepeatedSir(String(describing: event["message"] ?? ""))

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

        if type == "world_armor_event" {
            if let raw = event["event"] as? [String: Any],
               let data = try? JSONSerialization.data(withJSONObject: raw),
               let worldEvent = try? JSONDecoder().decode(
                   ArmorLiveEvent.self, from: data
               ) {
                await handleWorldArmorEvent(worldEvent, replayed: false)
            }
            return
        }

        if type == "world_armor_presence_request" {
            let requestID = String(describing: event["request_id"] ?? "")
            guard requestID.count == 32,
                  !processedWorldArmorPresence.contains(requestID) else { return }
            processedWorldArmorPresence.insert(requestID)
            if processedWorldArmorPresence.count > 100 {
                processedWorldArmorPresence.removeAll(keepingCapacity: true)
                processedWorldArmorPresence.insert(requestID)
            }

            let actuator = String(describing: event["actuator_kind"] ?? "")
            let action = String(describing: event["action"] ?? "")
            let targetText = String(describing: event["target_id"] ?? "")
            let desired = event["desired_on"] as? Bool
            let expiryText = String(describing: event["expires_at"] ?? "")
            var receiptStatus = "blocked"
            var receiptMessage = "Presence request was not executed."

            if let expiry = ISO8601DateFormatter().date(from: expiryText),
               expiry < Date() {
                receiptMessage = "Presence request expired before iPhone execution."
            } else if actuator != "homekit_light" || action != "set_light" {
                receiptMessage = "Presence request used an unsupported actuator/action."
            } else if let target = UUID(uuidString: targetText),
                      let desired {
                let result = await appModel.homeEnvironment.setLight(
                    target, on: desired
                )
                receiptMessage = result
                if result.hasPrefix("Verified in Apple Home:") {
                    receiptStatus = "verified_reported_state"
                } else if result.localizedCaseInsensitiveContains("rejected") {
                    receiptStatus = "failed"
                } else if result.localizedCaseInsensitiveContains("unreachable")
                            || result.localizedCaseInsensitiveContains("not available") {
                    receiptStatus = "blocked"
                } else {
                    receiptStatus = "unverified"
                }
            } else {
                receiptMessage = "Presence request target or desired state was invalid."
            }

            _ = try? await client.worldArmorPresenceReceipt(
                requestID: requestID,
                status: receiptStatus,
                message: receiptMessage
            )
            return
        }

        if type == "proactive_alert" {
            let severity = String(describing: event["severity"] ?? "info")
            guard proactiveAlertMeetsThreshold(severity) else {
                if !message.isEmpty { lastProactiveMessage = "Suppressed \(severity): \(message)" }
                return
            }
        }

        if appModel.settings.ambientCuesEnabled,
           ["cue", "proactive_alert", "background_complete", "background_failed", "meeting_complete"].contains(type) {
            cuePlayer.play(cue, preferBluetooth: appModel.settings.preferBluetoothAudio)
        }

        switch type {
        case "vision_state":
            let state = String(describing: event["state"] ?? "")
            switch state {
            case "received": visionStatus = "Frame received by PC"
            case "analyzing": visionStatus = "Analyzing on PC…"
            case "ready":
                if let scene = event["scene"] as? String, !scene.isEmpty { lastVisionScene = scene }
                if let milliseconds = event["analysis_ms"] as? Int {
                    visionStatus = "Active • \(milliseconds) ms analysis"
                } else if let number = event["analysis_ms"] as? NSNumber {
                    visionStatus = "Active • \(number.intValue) ms analysis"
                } else {
                    visionStatus = "Active"
                }
            case "error": visionStatus = message.isEmpty ? "Vision model error" : "Vision error: \(message)"
            default: break
            }

        case "proactive_alert", "background_complete", "background_failed", "meeting_complete":
            guard !message.isEmpty else { return }
            appModel.memoMind.presentProactiveAlert(
                message,
                severity: String(describing: event["severity"] ?? "info")
            )
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
            appModel.lastResponse = Self.collapseRepeatedSir(message)

            if wasHandsFree {
                try? await Task.sleep(for: .milliseconds(160))
                await appModel.startWakeWordMode()
            }
        }
    }

    private func speakProactive(_ text: String) async {
        let trimmed = Self.collapseRepeatedSir(text.trimmingCharacters(in: .whitespacesAndNewlines))
        guard !trimmed.isEmpty else { return }
        do {
            let audio = try await client.synthesizeSpeech(trimmed)
            try await appModel.speechSynthesizer.speakRemoteAudio(
                audio,
                text: trimmed,
                preferBluetooth: appModel.settings.preferBluetoothAudio
            )
        } catch {
            await appModel.speechSynthesizer.speak(
                trimmed,
                preferBluetooth: appModel.settings.preferBluetoothAudio
            )
        }
    }

    private static func collapseRepeatedSir(_ raw: String) -> String {
        raw.replacingOccurrences(
            of: #"(?i)\b(sir)\b(?:[\s,;:!\.\-–—]*\bsir\b)+"#,
            with: "$1",
            options: .regularExpression
        )
    }

    private static func sampledJPEG(
        from image: UIImage,
        maxDimension: CGFloat,
        quality: CGFloat
    ) -> Data? {
        let size = image.size
        guard size.width > 0, size.height > 0 else { return nil }
        let scale = min(1, maxDimension / max(size.width, size.height))
        let target = CGSize(width: max(1, size.width * scale), height: max(1, size.height * scale))
        let renderer = UIGraphicsImageRenderer(size: target)
        let resized = renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: target)) }
        return resized.jpegData(compressionQuality: quality)
    }
}
