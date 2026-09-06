import Foundation
import UIKit
import MWDATCore
import MWDATCamera

@MainActor
final class MetaGlassesManager: ObservableObject {
    @Published private(set) var registrationStatus = "Unknown"
    @Published private(set) var isRegistered = false
    @Published private(set) var cameraPermissionStatus = "Unknown"
    @Published private(set) var availableDeviceCount = 0
    @Published private(set) var hasEligibleDevice = false
    @Published private(set) var streamState = "Stopped"
    @Published private(set) var currentFrame: UIImage?
    @Published private(set) var capturedPhoto: Data?
    @Published private(set) var errorMessage: String?
    @Published private(set) var cameraMasterEnabled: Bool

    /// Fired only when a new *presence session* begins. Meta DAT exposes device
    /// eligibility, not a reliable on-head switch, so Jarvis deliberately does not
    /// treat every Bluetooth/DAT flap as "the user put the glasses back on." A new
    /// session requires a sustained absence and is rate-limited across app launches.
    /// If the return occurs during app startup before the single greeting owner is
    /// installed, one pending signal is delivered when the handler arrives.
    var onGlassesBecameAvailable: (() -> Void)? {
        didSet {
            guard onGlassesBecameAvailable != nil,
                  pendingPresenceSignal,
                  hasEligibleDevice else { return }
            pendingPresenceSignal = false
            onGlassesBecameAvailable?()
        }
    }

    private static let cameraMasterEnabledKey = "jarvis.cameraMasterEnabled"
    private static let lastPresenceSignalKey = "jarvis.meta.lastPresenceSignalEpoch"
    private static let meaningfulAbsenceSeconds: TimeInterval = 30
    private static let minimumPresenceSessionInterval: TimeInterval = 10 * 60

    private let wearables = Wearables.shared
    private let deviceSelector: AutoDeviceSelector
    private var registrationTask: Task<Void, Never>?
    private var deviceTask: Task<Void, Never>?
    private var eligibleDeviceTask: Task<Void, Never>?
    private var deviceSession: DeviceSession?
    private var camera: Camera?
    private var stream: MWDATCamera.Stream?
    private let streamTokenBag = ListenerTokenBag()

    private var availabilityInitialized = false
    private var previousEligible = false
    private var unavailableSince: Date?
    private var lastPresenceSignal: Date
    private var pendingPresenceSignal = false

    init() {
        // Stop Camera is a master privacy switch, not merely a request to stop
        // the current DAT stream. Persist it so background/passive protocols
        // cannot silently reopen the camera after the user explicitly stopped it,
        // including across an app relaunch. Only an explicit Start Camera action
        // is allowed to clear this latch.
        cameraMasterEnabled = UserDefaults.standard.object(forKey: Self.cameraMasterEnabledKey) as? Bool ?? true

        let lastSignalEpoch = UserDefaults.standard.double(forKey: Self.lastPresenceSignalKey)
        lastPresenceSignal = lastSignalEpoch > 0
            ? Date(timeIntervalSince1970: lastSignalEpoch)
            : Date.distantPast

        // AutoDeviceSelector learns its active device asynchronously from the
        // SDK's device stream. Keep one alive for the lifetime of the manager so
        // it is already populated by the time the user taps Start Camera.
        self.deviceSelector = AutoDeviceSelector(wearables: Wearables.shared)
        observeRegistration()
        observeDevices()
        observeEligibleDevice()
    }

    func startRegistration() async {
        guard !isRegistered else {
            errorMessage = nil
            return
        }
        errorMessage = nil
        do {
            try await wearables.startRegistration()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func unregister() async {
        stopStreamInternal(preserveError: false)
        errorMessage = nil
        do {
            try await wearables.startUnregistration()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func handleURL(_ url: URL) async {
        errorMessage = nil
        do {
            _ = try await wearables.handleUrl(url)
            await refreshCameraPermission()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshCameraPermission() async {
        guard isRegistered else {
            cameraPermissionStatus = "Unavailable"
            return
        }
        do {
            let status = try await wearables.checkPermissionStatus(.camera)
            cameraPermissionStatus = String(describing: status)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func requestCameraPermission() async {
        guard isRegistered else {
            errorMessage = "Register Jarvis with Meta AI before requesting camera access."
            return
        }
        errorMessage = nil
        do {
            let status = try await wearables.requestPermission(.camera)
            cameraPermissionStatus = String(describing: status)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Automatic/internal camera start used by passive vision, Known People,
    /// on-device perception, recovery logic, etc. This method can never override
    /// an explicit user Stop Camera action.
    func startStream() async {
        guard cameraMasterEnabled else {
            streamState = "Stopped"
            return
        }
        await startStreamInternal()
    }

    /// The only operation that may clear the master Stop Camera latch.
    /// This must be called from an explicit user Start Camera action.
    func startStreamByUser() async {
        setCameraMasterEnabled(true)
        await startStreamInternal()
    }

    private func startStreamInternal() async {
        guard cameraMasterEnabled else {
            streamState = "Stopped"
            return
        }
        guard isRegistered else {
            errorMessage = "Register Jarvis with Meta AI before starting the camera."
            return
        }
        guard stream == nil else { return }

        errorMessage = nil
        streamState = "Connecting"

        if !hasEligibleDevice {
            for _ in 0..<80 where !hasEligibleDevice {
                guard cameraMasterEnabled else {
                    streamState = "Stopped"
                    return
                }
                try? await Task.sleep(nanoseconds: 100_000_000)
            }
        }
        guard cameraMasterEnabled else {
            streamState = "Stopped"
            return
        }
        guard hasEligibleDevice else {
            streamState = "Stopped"
            errorMessage = "The glasses are connected, but Meta has not exposed an eligible DAT device yet. Keep the glasses awake and connected, then try again."
            return
        }

        do {
            let permission = try await wearables.checkPermissionStatus(.camera)
            guard cameraMasterEnabled else {
                streamState = "Stopped"
                return
            }
            guard permission == .granted else {
                streamState = "Stopped"
                cameraPermissionStatus = String(describing: permission)
                errorMessage = "Camera permission has not finished granting yet. Tap Camera Access and choose Allow once or Always allow."
                return
            }
            cameraPermissionStatus = String(describing: permission)
        } catch {
            streamState = "Stopped"
            errorMessage = error.localizedDescription
            return
        }

        let config = StreamConfiguration(
            videoCodec: .raw,
            resolution: .medium,
            frameRate: 24
        )

        do {
            guard cameraMasterEnabled else {
                streamState = "Stopped"
                return
            }
            let session = try wearables.createSession(deviceSelector: deviceSelector)
            try session.start()
            for await state in session.stateStream() {
                guard cameraMasterEnabled else {
                    session.stop()
                    streamState = "Stopped"
                    return
                }
                streamState = String(describing: state)
                if state == .started { break }
                if state == .stopped {
                    throw NSError(domain: "JarvisMeta", code: 1, userInfo: [NSLocalizedDescriptionKey: "The glasses session stopped before the camera became available."])
                }
            }

            guard cameraMasterEnabled else {
                session.stop()
                streamState = "Stopped"
                return
            }
            guard let camera = try session.addCamera(config: config) else {
                throw NSError(domain: "JarvisMeta", code: 2, userInfo: [NSLocalizedDescriptionKey: "The glasses camera capability is unavailable."])
            }
            let stream = camera.stream
            self.deviceSession = session
            self.camera = camera
            self.stream = stream

            streamTokenBag.clear()
            stream.statePublisher.listen { [weak self] state in
                Task { @MainActor in
                    guard let self, self.cameraMasterEnabled else { return }
                    self.streamState = String(describing: state)
                }
            }.store(in: streamTokenBag)
            stream.videoFramePublisher.listen { [weak self] frame in
                guard let image = frame.makeUIImage() else { return }
                Task { @MainActor in
                    guard let self, self.cameraMasterEnabled else { return }
                    self.currentFrame = image
                }
            }.store(in: streamTokenBag)
            stream.errorPublisher.listen { [weak self] error in
                Task { @MainActor in
                    guard let self, self.cameraMasterEnabled else { return }
                    self.errorMessage = error.localizedDescription
                }
            }.store(in: streamTokenBag)
            stream.photoDataPublisher.listen { [weak self] photoData in
                Task { @MainActor in
                    guard let self, self.cameraMasterEnabled else { return }
                    self.capturedPhoto = photoData.data
                }
            }.store(in: streamTokenBag)

            guard cameraMasterEnabled else {
                stopStreamInternal(preserveError: false)
                return
            }
            stream.start()
        } catch {
            streamState = "Stopped"
            if cameraMasterEnabled {
                errorMessage = error.localizedDescription
            }
            stopStreamInternal(preserveError: true)
        }
    }

    func stopStream() {
        setCameraMasterEnabled(false)
        stopStreamInternal(preserveError: false)
    }

    private func setCameraMasterEnabled(_ enabled: Bool) {
        cameraMasterEnabled = enabled
        UserDefaults.standard.set(enabled, forKey: Self.cameraMasterEnabledKey)
    }

    private func stopStreamInternal(preserveError: Bool) {
        streamTokenBag.clear()
        stream?.stop()
        camera?.stop()
        deviceSession?.stop()
        stream = nil
        camera = nil
        deviceSession = nil
        streamState = "Stopped"
        currentFrame = nil
        capturedPhoto = nil
        if !preserveError {
            errorMessage = nil
        }
    }

    func capturePhoto() {
        guard cameraMasterEnabled else { return }
        stream?.capturePhoto(format: .jpeg)
    }

    private func observeRegistration() {
        registrationTask?.cancel()
        registrationTask = Task { [weak self] in
            for await state in wearables.registrationStateStream() {
                guard !Task.isCancelled, let self else { return }
                switch state {
                case .unavailable:
                    registrationStatus = "Unavailable"
                    isRegistered = false
                case .available:
                    registrationStatus = "Ready to register"
                    isRegistered = false
                case .registering:
                    registrationStatus = "Registering…"
                    isRegistered = false
                case .registered:
                    registrationStatus = "Registered"
                    isRegistered = true
                    errorMessage = nil
                    await refreshCameraPermission()
                }
            }
        }
    }

    private func observeDevices() {
        deviceTask?.cancel()
        deviceTask = Task { [weak self] in
            for await devices in wearables.devicesStream() {
                guard !Task.isCancelled else { return }
                self?.availableDeviceCount = devices.count
            }
        }
    }

    private func observeEligibleDevice() {
        eligibleDeviceTask?.cancel()
        eligibleDeviceTask = Task { [weak self] in
            guard let self else { return }
            for await deviceID in deviceSelector.activeDeviceStream() {
                guard !Task.isCancelled else { return }
                let eligible = deviceID != nil
                let now = Date()
                hasEligibleDevice = eligible

                // The first DAT sample is initialization, not a return event. This
                // prevents a greeting every time the app launches while the glasses
                // are already connected.
                if !availabilityInitialized {
                    availabilityInitialized = true
                    previousEligible = eligible
                    if !eligible { unavailableSince = now }
                    continue
                }

                if !eligible {
                    if previousEligible { unavailableSince = now }
                    previousEligible = false
                    continue
                }

                guard !previousEligible else { continue }
                let unavailableDuration = unavailableSince.map { now.timeIntervalSince($0) } ?? 0
                previousEligible = true
                unavailableSince = nil

                // Treat a sustained absence as the end of one wearing/presence
                // session. Short DAT/Bluetooth flaps do not create a new session.
                // Persist the emission time so an app restart cannot immediately
                // produce a duplicate welcome-back event.
                guard unavailableDuration >= Self.meaningfulAbsenceSeconds,
                      now.timeIntervalSince(lastPresenceSignal) >= Self.minimumPresenceSessionInterval else {
                    continue
                }

                lastPresenceSignal = now
                UserDefaults.standard.set(now.timeIntervalSince1970, forKey: Self.lastPresenceSignalKey)
                if let onGlassesBecameAvailable {
                    onGlassesBecameAvailable()
                } else {
                    pendingPresenceSignal = true
                }
            }
        }
    }
}
