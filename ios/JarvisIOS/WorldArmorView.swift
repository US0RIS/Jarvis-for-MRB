import Foundation
import MapKit
import SwiftUI

// Phase 1 is a user-enrolled, one-shot evidence instrument. There is no
// background camera, AIS, aircraft tracker, worker or actuation path here.
struct ArmorCapabilities: Decodable {
    struct Provider: Decodable, Identifiable {
        let id: String
        let kind: String
        let coverage: String
    }
    let enabled: Bool
    let mode: String
    let sourceState: String
    let providers: [Provider]
    enum CodingKeys: String, CodingKey {
        case enabled, mode, providers
        case sourceState = "source_state"
    }
}

struct ArmorInvestigation: Decodable, Identifiable {
    let id: String
    let label: String
    let latitude: Double
    let longitude: Double
    let radiusKM: Double
    let expiresAt: String
    let sampleCount: Int
    enum CodingKeys: String, CodingKey {
        case id, label, latitude, longitude
        case radiusKM = "radius_km"
        case expiresAt = "expires_at"
        case sampleCount = "sample_count"
    }
}

struct ArmorInvestigationList: Decodable {
    let investigations: [ArmorInvestigation]
    let setupRequired: Bool
    enum CodingKeys: String, CodingKey {
        case investigations
        case setupRequired = "setup_required"
    }
}

struct ArmorCreated: Decodable {
    let id: String
    let label: String
}

struct ArmorCoverage: Decodable {
    let status: String
    let checkedAt: String
    let reportedCount: Int
    let scope: String
    let adapterMode: String
    enum CodingKeys: String, CodingKey {
        case status, scope
        case checkedAt = "checked_at"
        case reportedCount = "reported_count"
        case adapterMode = "adapter_mode"
    }
}

struct ArmorValues: Decodable {
    let usAQI: Double?
    let event: String?
    let headline: String?
    let severity: String?
    let magnitude: Double?
    let place: String?
    let reviewed: Bool?
    let sourceURL: String?
    enum CodingKeys: String, CodingKey {
        case event, headline, severity, magnitude, place, reviewed
        case usAQI = "us_aqi"
        case sourceURL = "source_url"
    }
    var brief: String {
        if let usAQI {
            return "Modelled US AQI: " + String(format: "%.1f", usAQI)
        }
        if let magnitude {
            return "USGS reported M" + String(format: "%.1f", magnitude)
                + " • " + (place ?? "Unspecified location")
        }
        if let event {
            return event + " • " + (headline ?? "No headline")
                + " • " + (severity ?? "Unknown severity")
        }
        return "Source reported a structured observation."
    }
}

struct ArmorObservation: Decodable, Identifiable {
    let id: String
    let source: String
    let kind: String
    let observedAt: String?
    let publishedAt: String?
    let receivedAt: String
    let revision: Int
    let lineage: String
    let geometryBasis: String
    let adapterMode: String?
    let values: ArmorValues
    enum CodingKeys: String, CodingKey {
        case id, source, kind, revision, lineage, values
        case observedAt = "observed_at"
        case publishedAt = "published_at"
        case receivedAt = "received_at"
        case geometryBasis = "geometry_basis"
        case adapterMode = "adapter_mode"
    }
}

struct ArmorSampleMoment: Decodable, Identifiable {
    let id: String
    let receivedAt: String
    let adapterMode: String
    enum CodingKeys: String, CodingKey {
        case id
        case receivedAt = "received_at"
        case adapterMode = "adapter_mode"
    }
}

struct ArmorReplay: Decodable {
    struct Region: Decodable {
        let id: String
        let label: String
        let latitude: Double
        let longitude: Double
    }
    let investigation: Region
    let asKnownAt: String
    let observationCount: Int
    let sampleTimeline: [ArmorSampleMoment]?
    let observations: [ArmorObservation]
    let coverage: [String: ArmorCoverage]
    let mode: String
    let unknownIsNotAllClear: Bool
    enum CodingKeys: String, CodingKey {
        case investigation, observations, coverage, mode
        case asKnownAt = "as_known_at"
        case observationCount = "observation_count"
        case sampleTimeline = "sample_timeline"
        case unknownIsNotAllClear = "unknown_is_not_all_clear"
    }
}

struct ArmorChangeReport: Decodable {
    struct CoverageChange: Decodable {
        let source: String
        let before: String
        let after: String
    }
    struct AQIChange: Decodable {
        let before: Double
        let after: Double
        let delta: Double
        let beforeModelAt: String
        let afterModelAt: String
        enum CodingKeys: String, CodingKey {
            case before, after, delta
            case beforeModelAt = "before_model_at"
            case afterModelAt = "after_model_at"
        }
    }
    struct RecordChange: Decodable, Identifiable {
        let source: String
        let kind: String
        let recordKey: String
        let receivedAt: String
        let observedAt: String?
        let after: ArmorValues
        let note: String
        var id: String { source + ":" + kind + ":" + recordKey }
        enum CodingKeys: String, CodingKey {
            case source, kind, after, note
            case recordKey = "record_key"
            case receivedAt = "received_at"
            case observedAt = "observed_at"
        }
    }
    let comparison: String
    let sourceChanges: [CoverageChange]
    let modelledAirQualityChange: AQIChange?
    let sourceRecordChanges: [RecordChange]
    let sourcesWithoutComparableCoverage: [String]?
    let qualifier: String
    enum CodingKeys: String, CodingKey {
        case comparison, qualifier
        case sourceChanges = "source_changes"
        case modelledAirQualityChange = "modelled_air_quality_change"
        case sourceRecordChanges = "source_record_changes"
        case sourcesWithoutComparableCoverage = "sources_without_comparable_coverage"
    }
}

struct ArmorCorrelationReport: Decodable {
    struct Window: Decodable {
        let start: String
        let end: String
    }
    struct Region: Decodable {
        let latitude: Double
        let longitude: Double
        let radiusKM: Double
        let geometryBasis: String
        enum CodingKeys: String, CodingKey {
            case latitude, longitude
            case radiusKM = "radius_km"
            case geometryBasis = "geometry_basis"
        }
    }
    struct Coverage: Decodable {
        let status: String
        let scope: String
    }
    struct Link: Decodable, Identifiable {
        let firstObservationID: String
        let secondObservationID: String
        let firstSource: String
        let secondSource: String
        let firstSourceTime: String
        let secondSourceTime: String
        let separationSeconds: Int
        let spatialBasis: String
        let note: String
        var id: String { firstObservationID + ":" + secondObservationID }
        enum CodingKeys: String, CodingKey {
            case note
            case firstObservationID = "first_observation_id"
            case secondObservationID = "second_observation_id"
            case firstSource = "first_source"
            case secondSource = "second_source"
            case firstSourceTime = "first_source_time"
            case secondSourceTime = "second_source_time"
            case separationSeconds = "separation_seconds"
            case spatialBasis = "spatial_basis"
        }
    }
    let observationWindow: Window
    let queryRegion: Region
    let spatiallyIndeterminateObservations: [ArmorObservation]
    let timedObservations: [ArmorObservation]
    let receiptTimeOnlyObservations: [ArmorObservation]
    let candidateLinks: [Link]
    let sourceCoverage: [String: Coverage]
    let mode: String
    let qualifier: String
    enum CodingKeys: String, CodingKey {
        case mode, qualifier
        case observationWindow = "observation_window"
        case queryRegion = "query_region"
        case spatiallyIndeterminateObservations = "spatially_indeterminate_observations"
        case timedObservations = "timed_observations"
        case receiptTimeOnlyObservations = "receipt_time_only_observations"
        case candidateLinks = "candidate_links"
        case sourceCoverage = "source_coverage"
    }
}

struct ArmorSampleReceipt: Decodable {
    let newObservations: Int
    let receivedAt: String
    let mode: String
    enum CodingKeys: String, CodingKey {
        case mode
        case newObservations = "new_observations"
        case receivedAt = "received_at"
    }
}

struct ArmorForgetReceipt: Decodable {
    let deleted: Int
    let qualifier: String?
}

struct WorldArmorView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @Environment(\.scenePhase) private var scenePhase

    @State private var capabilities: ArmorCapabilities?
    @State private var investigations: [ArmorInvestigation] = []
    @State private var selectedID: String?
    @State private var label = "Selected corridor"
    @State private var latitude = "34.12000"
    @State private var longitude = "-118.16000"
    @State private var radius = "30"
    @State private var asKnownAt = ""
    @State private var replayResult: ArmorReplay?
    @State private var changes: ArmorChangeReport?
    @State private var correlations: ArmorCorrelationReport?
    @State private var sampleTimes: [ArmorSampleMoment] = []
    @State private var correlationWindowHours = 6
    @State private var correlationQueryRadiusKM = 30.0
    @State private var correlationEnd = Date()
    @State private var busy = false
    @State private var confirmForget = false
    @State private var status = "World Armor is off until enabled on your Jarvis backend."

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    private var selected: ArmorInvestigation? {
        investigations.first { $0.id == selectedID }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 15) {
                heading
                enrollment
                saved
                if let selected {
                    selectedRegion(selected)
                    actions
                    if let changes { changePanel(changes) }
                    temporalQueryPanel
                    if let correlations { correlationPanel(correlations) }
                    if let replayResult { replayPanel(replayResult) }
                }
            }
            .padding()
        }
        .navigationTitle("World Armor")
        .navigationBarTitleDisplayMode(.inline)
        .task { await refresh() }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                replayResult = nil
                changes = nil
                correlations = nil
                sampleTimes = []
                status = "Sensitive investigation evidence hidden while app is inactive."
            }
        }
        .confirmationDialog(
            "Forget this investigation and all of its local evidence?",
            isPresented: $confirmForget,
            titleVisibility: .visible
        ) {
            Button("Forget saved investigation", role: .destructive) {
                Task { await forgetSelected() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the stored region and its samples. It cannot "
                 + "erase source-provider records or independent backups.")
        }
    }

    private var heading: some View {
        GroupBox("World Armor • event instrument") {
            VStack(alignment: .leading, spacing: 8) {
                Text("Explicitly save one region, sample three existing public "
                     + "provider families on demand, replay source receipts, "
                     + "and inspect source-qualified changes.")
                Text("No continuous tracking, camera recording, worker, "
                     + "autonomous action or global coverage.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let capabilities {
                    Text(capabilities.enabled
                         ? "Backend feature enabled • one-shot collection only"
                         : "Backend feature OFF • set JARVIS_WORLD_ARMOR_ENABLED=1")
                        .font(.subheadline.weight(.medium))
                    ForEach(capabilities.providers) { provider in
                        Text(provider.id + " • " + provider.coverage)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Text(status)
                    .font(.caption)
                    .accessibilityIdentifier("world-armor-status")
                Button(busy ? "Working…" : "Refresh status") {
                    Task { await refresh() }
                }
                .buttonStyle(.bordered)
                .disabled(busy)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var enrollment: some View {
        GroupBox("1 · Enroll a bounded region") {
            VStack(alignment: .leading, spacing: 9) {
                TextField("Label", text: $label)
                    .textFieldStyle(.roundedBorder)
                HStack {
                    TextField("Latitude", text: $latitude)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numbersAndPunctuation)
                    TextField("Longitude", text: $longitude)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numbersAndPunctuation)
                    TextField("Radius km", text: $radius)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.decimalPad)
                        .frame(maxWidth: 110)
                }
                Text("Coordinate entry is deliberate: no GPS, contacts, "
                     + "Calendar or MapKit place match is read automatically. "
                     + "Region expires after 24 hours.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Button("Create investigation") {
                    Task { await create() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || capabilities?.enabled != true)
            }
        }
    }

    private var saved: some View {
        GroupBox("2 · Saved investigations") {
            VStack(alignment: .leading, spacing: 9) {
                if investigations.isEmpty {
                    Text("None enrolled. No automatic world collection.")
                        .font(.caption)
                }
                ForEach(investigations) { entry in
                    Button {
                        selectedID = entry.id
                        correlationQueryRadiusKM = entry.radiusKM
                        asKnownAt = ""
                        replayResult = nil
                        changes = nil
                        correlations = nil
                        sampleTimes = []
                        status = "Selected " + entry.label
                        Task { await replay() }
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(entry.label).font(.subheadline.weight(.medium))
                                Text("\(entry.sampleCount) samples • "
                                     + String(format: "%.2f, %.2f", entry.latitude, entry.longitude)
                                     + " • \(entry.radiusKM) km")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: selectedID == entry.id
                                  ? "checkmark.circle.fill" : "circle")
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func selectedRegion(_ entry: ArmorInvestigation) -> some View {
        GroupBox("Selected region • \(entry.label)") {
            VStack(alignment: .leading, spacing: 8) {
                Map(initialPosition: .region(MKCoordinateRegion(
                    center: CLLocationCoordinate2D(
                        latitude: entry.latitude, longitude: entry.longitude
                    ),
                    span: MKCoordinateSpan(
                        latitudeDelta: max(0.02, entry.radiusKM / 55.0),
                        longitudeDelta: max(0.02, entry.radiusKM / 55.0)
                    )
                ))) {
                    Marker(entry.label, coordinate: CLLocationCoordinate2D(
                        latitude: entry.latitude, longitude: entry.longitude
                    ))
                }
                .frame(height: 230)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .accessibilityLabel("Map of explicitly saved investigation region")
                Text("MapKit displays the center, not verified sensor coverage "
                     + "or a surveyed boundary. Map tiles may be requested from Apple.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("Expires: " + entry.expiresAt)
                    .font(.caption2)
            }
        }
    }

    private var actions: some View {
        GroupBox("3 · Observe, rewind and compare") {
            VStack(alignment: .leading, spacing: 9) {
                HStack {
                    Button("Observe once") { Task { await observe() } }
                        .buttonStyle(.borderedProminent)
                    Button("Compare last two") { Task { await compare() } }
                        .buttonStyle(.bordered)
                }
                .disabled(busy || capabilities?.enabled != true)
                if !sampleTimes.isEmpty {
                    Menu("Rewind to a retained receipt") {
                        Button("Latest saved evidence") { asKnownAt = "" }
                        ForEach(sampleTimes) { item in
                            Button(item.receivedAt + " • " + item.adapterMode) {
                                asKnownAt = item.receivedAt
                                Task { await replay() }
                            }
                        }
                    }
                    .disabled(busy || capabilities?.enabled != true)
                }
                TextField("Optional as-known-at ISO time (UTC or offset)", text: $asKnownAt)
                    .textFieldStyle(.roundedBorder)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                HStack {
                    Button("Replay retained evidence") { Task { await replay() } }
                        .buttonStyle(.bordered)
                        .disabled(busy || capabilities?.enabled != true)
                    Button("Forget", role: .destructive) {
                        confirmForget = true
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                Text("Two samples cannot establish continuous monitoring. "
                     + "An unavailable provider cannot imply nothing happened.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // The MapKit center is a user-enrolled query scope, NOT an event location.
    // These queries never fetch providers, enroll watches or operate machines.
    private var temporalQueryPanel: some View {
        GroupBox("4 · Investigate retained evidence across time") {
            VStack(alignment: .leading, spacing: 9) {
                Text("Compare source-observed times in this selected region. "
                     + "The current providers do not report exact shared "
                     + "event footprints, so matches are temporal candidates only.")
                    .font(.caption)
                Text("Narrowed search radius: "
                     + "\(correlationQueryRadiusKM.formatted()) km")
                    .font(.subheadline.weight(.medium))
                Slider(
                    value: $correlationQueryRadiusKM,
                    in: 1...(selected?.radiusKM ?? 30),
                    step: 1
                )
                .accessibilityLabel("Historical evidence query radius in kilometers")
                Text("The radius cannot exceed the region you enrolled. "
                     + "Exact earthquake epicenters are used only when "
                     + "present in the official source.")
                    .font(.caption2)
                Picker("Observation window", selection: $correlationWindowHours) {
                    ForEach([6, 24, 72], id: \.self) { hours in
                        Text("Previous \(hours) hours").tag(hours)
                    }
                }
                .pickerStyle(.segmented)
                DatePicker(
                    "Window ends",
                    selection: $correlationEnd,
                    in: ...Date(),
                    displayedComponents: [.date, .hourAndMinute]
                )
                Button(busy ? "Querying…" : "Correlate saved sources") {
                    Task { await correlateSavedEvidence() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || capabilities?.enabled != true)
                Text("Read-only query; observation and receipt timestamps "
                     + "remain distinct. No new sensor checks occur.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func correlationPanel(_ report: ArmorCorrelationReport) -> some View {
        GroupBox("Temporal relationship candidates • not causal findings") {
            VStack(alignment: .leading, spacing: 9) {
                Text("Region \(report.queryRegion.latitude.formatted()), "
                     + "\(report.queryRegion.longitude.formatted()) "
                     + "• \(report.queryRegion.radiusKM.formatted()) km query radius")
                    .font(.subheadline.weight(.medium))
                Text("Observed-time window: "
                     + report.observationWindow.start + " → "
                     + report.observationWindow.end)
                    .font(.caption)
                Text(report.mode + " • \(report.timedObservations.count) timestamped "
                     + "source records; \(report.receiptTimeOnlyObservations.count) "
                     + "receipt-only records")
                    .font(.caption)
                ForEach(report.sourceCoverage.keys.sorted(), id: \.self) { source in
                    if let coverage = report.sourceCoverage[source] {
                        Text(source + " • " + coverage.status + " • " + coverage.scope)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Divider()
                Text("Event-time coincidence candidates: "
                     + "\(report.candidateLinks.count)")
                    .font(.headline)
                if report.candidateLinks.isEmpty {
                    Text("No eligible independent-source event-time pairs "
                         + "in these retained samples. Not an all-clear.")
                        .font(.caption)
                }
                ForEach(report.candidateLinks) { link in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(link.firstSource + " ↔ " + link.secondSource)
                            .font(.subheadline.weight(.medium))
                        Text("\(link.separationSeconds) seconds apart in reported "
                             + "source time")
                        Text(link.firstSourceTime + " → " + link.secondSourceTime)
                            .font(.caption2)
                        Text(link.note)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 9))
                }
                if !report.receiptTimeOnlyObservations.isEmpty {
                    Divider()
                    Text("Received-only • source event times unavailable")
                        .font(.headline)
                    ForEach(report.receiptTimeOnlyObservations.prefix(25)) { row in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(row.source + " • " + row.values.brief)
                            Text("Jarvis received: " + row.receivedAt
                                 + " • source event time UNKNOWN")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                if !report.spatiallyIndeterminateObservations.isEmpty {
                    Text("Location unknown in narrowed query: "
                         + "\(report.spatiallyIndeterminateObservations.count) "
                         + "retained earthquake reports excluded from exact "
                         + "radius matching.")
                        .font(.caption)
                }
                Text(report.qualifier)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func changePanel(_ report: ArmorChangeReport) -> some View {
        GroupBox("Observed differences, not assumed causes") {
            VStack(alignment: .leading, spacing: 8) {
                Text(report.comparison.replacingOccurrences(of: "_", with: " "))
                    .font(.headline)
                if let air = report.modelledAirQualityChange {
                    Text("Modelled AQI: \(air.before.formatted()) → "
                         + "\(air.after.formatted()); Δ \(air.delta.formatted())")
                    Text("Model times: " + air.beforeModelAt + " → " + air.afterModelAt)
                        .font(.caption2)
                }
                ForEach(report.sourceChanges.indices, id: \.self) { index in
                    let row = report.sourceChanges[index]
                    Text(row.source + " coverage: " + row.before + " → " + row.after)
                        .font(.caption)
                }
                ForEach(report.sourceRecordChanges) { row in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.source + " · " + row.kind.replacingOccurrences(
                            of: "_", with: " "))
                            .font(.subheadline.weight(.medium))
                        Text(row.after.brief)
                        Text(row.note + " • received " + row.receivedAt)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                if report.sourceRecordChanges.isEmpty
                    && report.modelledAirQualityChange == nil
                    && report.sourceChanges.isEmpty {
                    Text("No detectable difference in these retained samples. "
                         + "This is not an all-clear.")
                        .font(.caption)
                }
                Text(report.qualifier)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func replayPanel(_ report: ArmorReplay) -> some View {
        GroupBox("Retained source evidence • as known then") {
            VStack(alignment: .leading, spacing: 9) {
                Text("As known at " + report.asKnownAt)
                    .font(.subheadline.weight(.medium))
                Text(report.mode + " • \(report.observationCount) latest "
                     + "source-key records • not a complete world history")
                    .font(.caption)
                ForEach(report.coverage.keys.sorted(), id: \.self) { source in
                    if let coverage = report.coverage[source] {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(source + " • " + coverage.status)
                                .font(.subheadline.weight(.medium))
                            Text("Reported count \(coverage.reportedCount) • "
                                 + "checked " + coverage.checkedAt)
                                .font(.caption2)
                            Text(coverage.scope)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                Divider()
                ForEach(report.observations.prefix(60)) { row in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.source + " • revision \(row.revision)"
                             + " • " + (row.adapterMode ?? "unknown source mode"))
                            .font(.subheadline.weight(.medium))
                        Text(row.values.brief)
                        Text("Source observation: "
                             + (row.observedAt ?? "unknown")
                             + " • Jarvis received " + row.receivedAt)
                            .font(.caption2)
                        Text(row.geometryBasis)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Divider()
                }
                Text("No source observation or no matching events "
                     + "never proves an area is safe or fully observed.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func refresh() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            capabilities = try await client.worldArmorCapabilities()
            // Listing and forgetting retained regions remains available after
            // collection is disabled; no new provider request is issued here.
            investigations = try await client.worldArmorInvestigations().investigations
            if !investigations.contains(where: { $0.id == selectedID }) {
                selectedID = nil
                replayResult = nil
                changes = nil
                correlations = nil
                sampleTimes = []
            }
            if capabilities?.enabled == true {
                status = "Source registry integrated, not proof that live "
                    + "feeds or your installed devices have been checked."
            } else {
                replayResult = nil
                changes = nil
                correlations = nil
                sampleTimes = []
                status = "Backend OFF: collection and replay disabled. "
                    + "Previously saved locations remain visible for deletion."
            }
        } catch {
            capabilities = nil
            replayResult = nil
            changes = nil
            correlations = nil
            sampleTimes = []
            status = "World Armor unavailable: " + error.localizedDescription
        }
    }

    private func create() async {
        guard !busy else { return }
        guard let lat = Double(latitude), let lon = Double(longitude),
              let radiusKM = Double(radius) else {
            status = "Enter valid numeric coordinates and radius."
            return
        }
        busy = true
        defer { busy = false }
        do {
            let made = try await client.worldArmorCreate(
                label: label, latitude: lat, longitude: lon, radiusKM: radiusKM
            )
            investigations = try await client.worldArmorInvestigations().investigations
            selectedID = made.id
            correlationQueryRadiusKM = radiusKM
            replayResult = nil
            changes = nil
            correlations = nil
            sampleTimes = []
            asKnownAt = ""
            status = "Created an expiring region. No provider checked yet."
        } catch {
            status = "Create blocked: " + error.localizedDescription
        }
    }

    private func observe() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let receipt = try await client.worldArmorObserve(selectedID)
            investigations = try await client.worldArmorInvestigations().investigations
            replayResult = try await client.worldArmorReplay(
                selectedID, asKnownAt: nil
            )
            sampleTimes = replayResult?.sampleTimeline ?? []
            asKnownAt = ""
            changes = nil
            correlations = nil
            status = "Received \(receipt.newObservations) new source records "
                + "at " + receipt.receivedAt + ". Read coverage before "
                + "drawing conclusions."
        } catch {
            status = "Observation failed: " + error.localizedDescription
        }
    }

    private func replay() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let cutoff = asKnownAt.trimmingCharacters(in: .whitespacesAndNewlines)
            replayResult = try await client.worldArmorReplay(
                selectedID, asKnownAt: cutoff.isEmpty ? nil : cutoff
            )
            if cutoff.isEmpty {
                sampleTimes = replayResult?.sampleTimeline ?? []
            }
            status = "Viewing retained evidence, not issuing provider requests."
        } catch {
            status = "Replay blocked: " + error.localizedDescription
        }
    }

    private func compare() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            changes = try await client.worldArmorChanges(selectedID)
            status = "Compared the two latest saved receipts. "
                + "No inference of causation or absence."
        } catch {
            status = "Comparison blocked: " + error.localizedDescription
        }
    }

    private func correlateSavedEvidence() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let end = correlationEnd
            let start = end.addingTimeInterval(
                -Double(correlationWindowHours) * 3_600
            )
            let formatter = ISO8601DateFormatter()
            let cutoff = asKnownAt.trimmingCharacters(in: .whitespacesAndNewlines)
            correlations = try await client.worldArmorCorrelate(
                selectedID,
                startAt: formatter.string(from: start),
                endAt: formatter.string(from: end),
                asKnownAt: cutoff.isEmpty ? nil : cutoff,
                radiusKM: correlationQueryRadiusKM
            )
            status = "Read-only historical correlation complete. "
                + "Inspect source time, scope and unknown coverage."
        } catch {
            correlations = nil
            status = "Correlation unavailable: " + error.localizedDescription
        }
    }

    private func forgetSelected() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let receipt = try await client.worldArmorForget(selectedID)
            replayResult = nil
            changes = nil
            correlations = nil
            sampleTimes = []
            investigations = try await client.worldArmorInvestigations().investigations
            self.selectedID = nil
            status = "Removed \(receipt.deleted) investigation. "
                + "External source records and backups were not erased."
        } catch {
            status = "Forget blocked: " + error.localizedDescription
        }
    }
}
