import Foundation
import UIKit
import MWDATCore
import MWDATCamera

@MainActor
final class MetaGlassesManager: ObservableObject {
    @Published private(set) var registrationStatus = "Unknown"
    @Published private(set) var cameraPermissionStatus = "Unknown"
    @Published private(set) var availableDeviceCount = 0
    @Published private(set) var streamState = "Stopped"
    @Published private(set) var currentFrame: UIImage?
    @Published private(set) var capturedPhoto: Data?
    @Published private(set) var errorMessage: String?

    private let wearables = Wearables.shared
    private var registrationTask: Task<Void, Never>?
    private var deviceTask: Task<Void, Never>?
    private var deviceSession: DeviceSession?
    private var camera: Camera?
    private var stream: MWDATCamera.Stream?

    init() {
        observeRegistration()
        observeDevices()
    }

    func startRegistration() async {
        do {
            try await wearables.startRegistration()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func unregister() async {
        stopStream()
        do {
            try await wearables.startUnregistration()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func handleURL(_ url: URL) async {
        do {
            _ = try await wearables.handleUrl(url)
            await refreshCameraPermission()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshCameraPermission() async {
        do {
            let status = try await wearables.checkPermissionStatus(.camera)
            cameraPermissionStatus = String(describing: status)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func requestCameraPermission() async {
        do {
            let status = try await wearables.requestPermission(.camera)
            cameraPermissionStatus = String(describing: status)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func startStream() async {
        guard stream == nil else { return }
        errorMessage = nil
        streamState = "Connecting"

        let config = StreamConfiguration(
            videoCodec: .raw,
            resolution: .medium,
            frameRate: 24
        )
        let selector = AutoDeviceSelector(wearables: wearables)

        do {
            let session = try wearables.createSession(deviceSelector: selector)
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

            _ = stream.statePublisher.listen { [weak self] state in
                Task { @MainActor in self?.streamState = String(describing: state) }
            }
            _ = stream.videoFramePublisher.listen { [weak self] frame in
                guard let image = frame.makeUIImage() else { return }
                Task { @MainActor in self?.currentFrame = image }
            }
            _ = stream.photoDataPublisher.listen { [weak self] photoData in
                Task { @MainActor in self?.capturedPhoto = photoData.data }
            }
            stream.start()
        } catch {
            streamState = "Stopped"
            errorMessage = error.localizedDescription
            stopStream()
        }
    }

    func stopStream() {
        camera?.stop()
        deviceSession?.stop()
        stream = nil
        camera = nil
        deviceSession = nil
        streamState = "Stopped"
        currentFrame = nil
    }

    func capturePhoto() {
        stream?.capturePhoto(format: .jpeg)
    }

    private func observeRegistration() {
        registrationTask?.cancel()
        registrationTask = Task { [weak self] in
            for await state in wearables.registrationStateStream() {
                guard !Task.isCancelled else { return }
                self?.registrationStatus = String(describing: state)
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
}
