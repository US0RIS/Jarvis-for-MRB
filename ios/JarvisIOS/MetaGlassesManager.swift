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

    private static let cameraMasterEnabledKey = "jarvis.cameraMasterEnabled"

    private let wearables = Wearables.shared
    private let deviceSelector: AutoDeviceSelector
    private var registrationTask: Task<Void, Never>?
    private var deviceTask: Task<Void, Never>?
    private var eligibleDeviceTask: Task<Void, Never>?
    private var deviceSession: DeviceSession?
    private var camera: Camera?
    private var stream: MWDATCamera.Stream?
    private let streamTokenBag = ListenerTokenBag()

    init() {
        // Stop Camera is a master privacy switch, not merely a request to stop
        // the current DAT stream. Persist it so background/passive protocols
        // cannot silently reopen the camera after the user explicitly stopped it,
        // including across an app relaunch. Only an explicit Start Camera action
        // is allowed to clear this latch.
        cameraMasterEnabled = UserDefaults.standard.object(forKey: Self.cameraMasterEnabledKey) as? Bool ?? true

        // AutoDeviceSelector learns its active device asynchronously from the
        // SDK's device stream. Keep one alive for the lifetime of the manager so
        // it is already populated by the time the user taps Start Camera.
        // Creating a fresh selector immediately before createSession() races that
        // discovery and can throw DeviceSessionError.noEligibleDevice even when
        // devicesStream() is already reporting the glasses.
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

        // The selector can take a moment to become active after returning from
        // Meta AI or waking the glasses. Give its monitor a short window to
        // converge instead of immediately failing with noEligibleDevice.
        if !hasEligibleDevice {
            for _ in 0..<80 where !hasEligibleDevice {
                // Re-check the master switch during the wait so a Stop Camera tap
                // wins even while an automatic start attempt is already pending.
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

    /// Explicit user-facing Stop Camera. This is a persistent master kill switch:
    /// it prevents passive vision, Known People, inventory, local perception,
    /// recovery logic, silent scans, or any future automatic protocol from
    /// restarting the camera until the user explicitly taps Start Camera.
    func stopStream() {
        setCameraMasterEnabled(false)
        stopStreamInternal(preserveError: false)
    }

    private func setCameraMasterEnabled(_ enabled: Bool) {
        cameraMasterEnabled = enabled
        UserDefaults.standard.set(enabled, forKey: Self.cameraMasterEnabledKey)
    }

    private func stopStreamInternal(preserveError: Bool) {
        // Detach listeners first so late SDK callbacks cannot make the UI look
        // active again after the user has stopped the camera.
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
                hasEligibleDevice = deviceID != nil
            }
        }
    }
}
