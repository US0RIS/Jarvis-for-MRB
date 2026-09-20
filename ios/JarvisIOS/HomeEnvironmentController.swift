import Foundation
import HomeKit
import SwiftUI

/// Opt-in, phone-local physical control. Never gives the backend generic
/// HomeKit characteristic writes or exposes arbitrary devices as actuators.
@MainActor
final class HomeEnvironmentController: NSObject, ObservableObject, HMHomeManagerDelegate {
    struct Light: Identifiable, Equatable {
        let id: UUID
        let name: String
        let room: String
        let reachable: Bool
        let cachedOn: Bool?
    }

    @Published private(set) var status = "Not connected to Apple Home"
    @Published private(set) var lights: [Light] = []
    @Published private(set) var lastResult = ""
    @Published private(set) var discovered = false
    @Published private(set) var busy = false
    @Published private(set) var arrivalLightIDs: Set<UUID> = []

    private static let arrivalKey = "jarvis.home.preapprovedArrivalLights"
    private var lastArrivalRun = Date.distantPast

    override init() {
        let ids = UserDefaults.standard.stringArray(forKey: Self.arrivalKey) ?? []
        arrivalLightIDs = Set(ids.compactMap(UUID.init(uuidString:)))
        super.init()
    }

    private var manager: HMHomeManager?
    private var characteristics: [UUID: HMCharacteristic] = [:]

    func discover() {
        status = "Requesting Apple Home access…"
        if let manager {
            refresh(from: manager)
            return
        }
        // Starting HMHomeManager may show iOS Home permission for this app;
        // do not instantiate it at app launch without the user's request.
        let newManager = HMHomeManager()
        manager = newManager
        newManager.delegate = self
        refresh(from: newManager)
    }

    func homeManagerDidUpdateHomes(_ manager: HMHomeManager) {
        refresh(from: manager)
    }

    private func refresh(from manager: HMHomeManager) {
        let homes = manager.homes
        guard let home = manager.primaryHome ?? homes.first else {
            lights = []
            characteristics = [:]
            status = "No accessible Apple Home. Check iOS Home permissions and Home setup."
            return
        }
        var catalog: [Light] = []
        var mapping: [UUID: HMCharacteristic] = [:]
        for accessory in home.accessories {
            for service in accessory.services where service.serviceType == HMServiceTypeLightbulb {
                guard let power = service.characteristics.first(where: {
                    $0.characteristicType == HMCharacteristicTypePowerState
                        && $0.properties.contains(HMCharacteristicPropertyWritable)
                        && $0.properties.contains(HMCharacteristicPropertyReadable)
                }) else { continue }
                let cachedOn = (power.value as? NSNumber)?.boolValue
                catalog.append(Light(
                    id: power.uniqueIdentifier,
                    name: accessory.name,
                    room: accessory.room?.name ?? "Unassigned",
                    reachable: accessory.isReachable,
                    cachedOn: cachedOn
                ))
                mapping[power.uniqueIdentifier] = power
            }
        }
        characteristics = mapping
        lights = catalog.sorted {
            ($0.room.localizedLowercase, $0.name.localizedLowercase, $0.id.uuidString)
                < ($1.room.localizedLowercase, $1.name.localizedLowercase, $1.id.uuidString)
        }
        discovered = true
        status = "Apple Home connected • \(lights.count) controllable light\(lights.count == 1 ? "" : "s")"
    }

    /// Exact, individually enrolled and reversible physical action. This is a
    /// location-triggered HomeKit rule, not a permission granted by an LLM or
    /// sound classifier. Auto control cannot be enrolled without discovery.
    func setArrivalControl(_ id: UUID, enabled: Bool) {
        guard discovered, lights.contains(where: { $0.id == id }) else { return }
        if enabled { arrivalLightIDs.insert(id) }
        else { arrivalLightIDs.remove(id) }
        UserDefaults.standard.set(
            arrivalLightIDs.map(\.uuidString).sorted(),
            forKey: Self.arrivalKey
        )
        lastResult = enabled
            ? "Preauthorized arrival action for this light. Runs only while Jarvis is active, and only on a fresh home-arrival event."
            : "Automatic arrival action revoked."
    }

    func runPreapprovedArrivalActions() async -> [String] {
        guard discovered, !busy, !arrivalLightIDs.isEmpty else { return [] }
        let now = Date()
        // A bouncing geofence must never repeatedly toggle physical devices.
        guard now.timeIntervalSince(lastArrivalRun) >= 300 else { return [] }
        lastArrivalRun = now
        var outcomes: [String] = []
        // Bound the work per transition, preserve exact enrollment and keep
        // fresh readback for each action. No new Home permission prompt here.
        for light in lights.filter({ arrivalLightIDs.contains($0.id) }).prefix(5) {
            outcomes.append(await setLight(light.id, on: true))
        }
        return outcomes
    }

    func listLightNames() -> String {
        guard discovered else { return "Open the Physical tab and tap Discover Apple Home first." }
        guard !lights.isEmpty else { return "No controllable lights were found in Apple Home." }
        let catalog = lights.prefix(20).map { "\($0.name), \($0.room)" }.joined(separator: "; ")
        return "Apple Home lights: " + catalog
    }

    /// Exact, single-device grammar. No fuzzy names, broad "all" control,
    /// inferred intent, locks, shades, scenes or arbitrary switch writes.
    func handleCommand(_ raw: String) async -> String? {
        let normalized = Self.normalize(raw)
        if ["what lights can you control", "list controllable lights", "jarvis what lights can you control"].contains(normalized) {
            return listLightNames()
        }
        let phrase = normalized.hasPrefix("jarvis ")
            ? String(normalized.dropFirst(7))
            : normalized
        let prefixes: [(String, Bool)] = [
            ("turn on ", true), ("turn off ", false),
            ("switch on ", true), ("switch off ", false),
        ]
        guard let (prefix, desired) = prefixes.first(where: { phrase.hasPrefix($0.0) }) else {
            return nil
        }
        var requested = String(phrase.dropFirst(prefix.count))
        if requested.hasPrefix("the ") { requested = String(requested.dropFirst(4)) }
        guard discovered else { return nil } // Keep prior backend routing until expressly enrolled.
        let candidates = lights.filter {
            let label = Self.normalize($0.name)
            let explicit = Self.normalize($0.name + " " + $0.room)
            return requested == label || requested == label + " light"
                || requested == label + " lights" || requested == explicit
                || requested == explicit + " light" || requested == explicit + " lights"
        }
        guard !candidates.isEmpty else { return nil }
        guard candidates.count == 1, let target = candidates.first else {
            return "More than one HomeKit light matches. Use the explicit control in the Physical tab."
        }
        return await setLight(target.id, on: desired)
    }

    func setLight(_ id: UUID, on: Bool) async -> String {
        guard discovered else { return "Discover Apple Home first." }
        guard !busy else { return "Another HomeKit action is in progress." }
        guard let light = lights.first(where: { $0.id == id }),
              let characteristic = characteristics[id] else {
            return "That light is not available in the current Apple Home catalog."
        }
        guard light.reachable else { return "\(light.name) is marked unreachable by Apple Home." }
        busy = true
        defer { busy = false }
        do {
            // A write success is not the outcome. Read a fresh characteristic
            // value afterward; report mismatch or unavailable verification.
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                characteristic.writeValue(on) { error in
                    if let error { continuation.resume(throwing: error) }
                    else { continuation.resume() }
                }
            }
        } catch {
            lastResult = "Apple Home rejected \(light.name): \(error.localizedDescription)"
            return lastResult
        }
        do {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                characteristic.readValue { error in
                    if let error { continuation.resume(throwing: error) }
                    else { continuation.resume() }
                }
            }
            let observed = (characteristic.value as? NSNumber)?.boolValue
            if observed == on {
                lastResult = "Verified in Apple Home: \(light.name) reports \(on ? "on" : "off")."
            } else {
                lastResult = "Apple Home accepted the command, but fresh readback did not confirm \(light.name) is \(on ? "on" : "off")."
            }
        } catch {
            lastResult = "Apple Home accepted the command, but readback failed: \(error.localizedDescription)"
        }
        if let manager { refresh(from: manager) }
        return lastResult
    }

    private static func normalize(_ value: String) -> String {
        value.lowercased()
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: ".!?"))
    }
}

struct AppleHomeControlView: View {
    @EnvironmentObject var home: HomeEnvironmentController

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Physical-world control", systemImage: "house")
                .font(.headline)
            Text(home.status)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button("Discover Apple Home") { home.discover() }
                .buttonStyle(.borderedProminent)
            if home.discovered {
                Text("Only HomeKit light services appear here. Individually enroll Auto on arrival for an explicit reversible light action when fresh GPS/geofence and ambient opportunity controls are enabled. It runs only while Jarvis is active; there are no locks, garage doors, outlets, or scenes.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                ForEach(home.lights) { light in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(light.name)
                            Text(light.room + (light.reachable ? "" : " • Unreachable"))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button("On") {
                            Task { _ = await home.setLight(light.id, on: true) }
                        }
                        Button("Off") {
                            Task { _ = await home.setLight(light.id, on: false) }
                        }
                        Button(home.arrivalLightIDs.contains(light.id) ? "Auto on arrival ✓" : "Auto on arrival") {
                            home.setArrivalControl(
                                light.id,
                                enabled: !home.arrivalLightIDs.contains(light.id)
                            )
                        }
                        .accessibilityIdentifier("home-auto-arrival-\(light.id.uuidString)")
                    }
                    .buttonStyle(.bordered)
                    .disabled(home.busy || !light.reachable)
                }
            }
            if !home.lastResult.isEmpty {
                Text(home.lastResult)
                    .font(.footnote)
                    .accessibilityIdentifier("jarvis-home-readback")
            }
        }
    }
}
