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
        stopStream()
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

    func startStream() async {
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
                try? await Task.sleep(nanoseconds: 100_000_000)
            }
        }
        guard hasEligibleDevice else {
            streamState = "Stopped"
            errorMessage = "The glasses are connected, but Meta has not exposed an eligible DAT device yet. Keep the glasses awake and connected, then try again."
            return
        }

        do {
            let permission = try await wearables.checkPermissionStatus(.camera)
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
            let session = try wearables.createSession(deviceSelector: deviceSelector)
            try session.start()
            for await state in session.stateStream() {
                streamState = String(describing: state)
                if state == .started { break }
                if state == .stopped {
                    throw NSError(domain: "JarvisMeta", code: 1, userInfo: [NSLocalizedDescriptionKey: "The glasses session stopped before the camera became available."])
                }
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
                Task { @MainActor in self?.streamState = String(describing: state) }
            }.store(in: streamTokenBag)
            stream.videoFramePublisher.listen { [weak self] frame in
                guard let image = frame.makeUIImage() else { return }
                Task { @MainActor in self?.currentFrame = image }
            }.store(in: streamTokenBag)
            stream.errorPublisher.listen { [weak self] error in
                Task { @MainActor in self?.errorMessage = error.localizedDescription }
            }.store(in: streamTokenBag)
            stream.photoDataPublisher.listen { [weak self] photoData in
                Task { @MainActor in self?.capturedPhoto = photoData.data }
            }.store(in: streamTokenBag)
            stream.start()
        } catch {
            streamState = "Stopped"
            errorMessage = error.localizedDescription
            stopStream(preserveError: true)
        }
    }

    func stopStream() {
        stopStream(preserveError: false)
    }

    private func stopStream(preserveError: Bool) {
        camera?.stop()
        deviceSession?.stop()
        streamTokenBag.clear()
        stream = nil
        camera = nil
        deviceSession = nil
        streamState = "Stopped"
        currentFrame = nil
        if !preserveError {
            errorMessage = nil
        }
    }

    func capturePhoto() {
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
