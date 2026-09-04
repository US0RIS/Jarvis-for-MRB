import Foundation
import MWDATCore

@MainActor
final class MetaGlassesManager: ObservableObject {
    @Published private(set) var registrationStatus = "Unknown"
    @Published private(set) var cameraPermissionStatus = "Unknown"
    @Published private(set) var availableDeviceCount = 0
    @Published private(set) var errorMessage: String?

    private var registrationTask: Task<Void, Never>?
    private var deviceTask: Task<Void, Never>?

    init() {
        observeRegistration()
        observeDevices()
    }

    func startRegistration() async {
        do {
            try await Wearables.shared.startRegistration()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func unregister() async {
        do {
            try await Wearables.shared.startUnregistration()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func handleURL(_ url: URL) async {
        do {
            _ = try await Wearables.shared.handleUrl(url)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshCameraPermission() async {
        do {
            let status = try await Wearables.shared.checkPermissionStatus(.camera)
            cameraPermissionStatus = String(describing: status)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func requestCameraPermission() async {
        do {
            let status = try await Wearables.shared.requestPermission(.camera)
            cameraPermissionStatus = String(describing: status)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func observeRegistration() {
        registrationTask?.cancel()
        registrationTask = Task { [weak self] in
            for await state in Wearables.shared.registrationStateStream() {
                guard !Task.isCancelled else { return }
                self?.registrationStatus = String(describing: state)
            }
        }
    }

    private func observeDevices() {
        deviceTask?.cancel()
        deviceTask = Task { [weak self] in
            for await devices in Wearables.shared.devicesStream() {
                guard !Task.isCancelled else { return }
                self?.availableDeviceCount = devices.count
            }
        }
    }
}
