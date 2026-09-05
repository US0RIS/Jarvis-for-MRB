import Foundation
import ImageIO
import PhotosUI
import SwiftUI
import UIKit
import Vision

struct EnrolledPerson: Identifiable, Codable, Equatable {
    let id: UUID
    var name: String
    var notes: String
    var featurePrints: [Data]
    var calibrationDistance: Float
    let enrolledAt: Date

    init(
        id: UUID = UUID(),
        name: String,
        notes: String,
        featurePrints: [Data],
        calibrationDistance: Float,
        enrolledAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.notes = notes
        self.featurePrints = featurePrints
        self.calibrationDistance = calibrationDistance
        self.enrolledAt = enrolledAt
    }
}

struct RecognizedPersonMatch: Equatable {
    let personID: UUID
    let name: String
    let distance: Float
    let threshold: Float
    let matchedAt: Date

    var scoreDescription: String {
        String(format: "distance %.3f / %.3f", distance, threshold)
    }
}

private struct FaceFeatureResult {
    let observation: VNFeaturePrintObservation
    let faceCount: Int
}

@MainActor
final class KnownPeopleController: ObservableObject {
    @Published private(set) var people: [EnrolledPerson] = []
    @Published private(set) var currentMatch: RecognizedPersonMatch?
    @Published private(set) var status = "No recognition yet"
    @Published private(set) var lastFaceCount = 0

    private static let storageAccount = "jarvis.knownPeople.v1"
    private var candidateID: UUID?
    private var candidateHits = 0
    private var lastRecognitionAttempt = Date.distantPast

    init() {
        load()
    }

    var hasEnrolledPeople: Bool { !people.isEmpty }

    func enroll(name rawName: String, notes rawNotes: String, imageData: [Data]) async -> String {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        let notes = rawNotes.trimmingCharacters(in: .whitespacesAndNewlines)
        guard name.count >= 2 else { return "Enter a contact name first." }
        guard !people.contains(where: { $0.name.compare(name, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame }) else {
            return "That name is already enrolled. Delete the existing profile first if you want to replace it."
        }
        guard imageData.count >= 2 else {
            return "Use at least two clear samples of the same person; three to six is better."
        }

        status = "Creating private face profile…"
        do {
            let bounded = Array(imageData.prefix(6))
            let packed: [Data] = try await Task.detached(priority: .userInitiated) {
                var results: [Data] = []
                for data in bounded {
                    if let packed = try? Self.faceFeatureArchive(from: data) {
                        results.append(packed)
                    }
                }
                return results
            }.value

            guard packed.count >= 2 else {
                status = "Enrollment failed"
                return "I could not find a clear single face in at least two of those samples. Try closer, well-lit images with the same person."
            }

            let calibration = try Self.calibrationDistance(for: packed)
            let person = EnrolledPerson(
                name: name,
                notes: String(notes.prefix(2000)),
                featurePrints: packed,
                calibrationDistance: calibration
            )
            people.append(person)
            people.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
            persist()
            status = "Enrolled \(name) with \(packed.count) private samples"
            return "Enrolled \(name) using \(packed.count) samples. Raw enrollment photos were not retained."
        } catch {
            status = "Enrollment failed"
            return "Enrollment failed: \(error.localizedDescription)"
        }
    }

    func delete(_ person: EnrolledPerson) {
        people.removeAll { $0.id == person.id }
        if currentMatch?.personID == person.id { currentMatch = nil }
        persist()
        status = people.isEmpty ? "No enrolled people" : "Forgot \(person.name)"
    }

    func forgetAll() {
        people.removeAll()
        currentMatch = nil
        candidateID = nil
        candidateHits = 0
        KeychainStore.delete(Self.storageAccount)
        status = "No enrolled people"
    }

    func updateNotes(personID: UUID, notes: String) {
        guard let index = people.firstIndex(where: { $0.id == personID }) else { return }
        people[index].notes = String(notes.trimmingCharacters(in: .whitespacesAndNewlines).prefix(2000))
        persist()
    }

    func recognize(jpeg: Data, toleranceMultiplier: Double = 1.65, force: Bool = false) async {
        guard !people.isEmpty else {
            currentMatch = nil
            status = "No enrolled people"
            return
        }
        if !force && Date().timeIntervalSince(lastRecognitionAttempt) < 1.1 { return }
        lastRecognitionAttempt = Date()

        do {
            let query = try await Task.detached(priority: .userInitiated) {
                try Self.faceFeature(from: jpeg)
            }.value
            lastFaceCount = query.faceCount

            let ranked = try Self.rank(query: query.observation, people: people, toleranceMultiplier: toleranceMultiplier)
            guard let best = ranked.first, best.accepted else {
                candidateID = nil
                candidateHits = 0
                if let match = currentMatch, Date().timeIntervalSince(match.matchedAt) > 4 {
                    currentMatch = nil
                }
                status = query.faceCount == 0 ? "No face detected" : "Face detected • no confident enrolled match"
                return
            }

            if ranked.count > 1 {
                let second = ranked[1]
                let separation = second.distance - best.distance
                let required = max(0.04, best.threshold * 0.10)
                guard separation >= required else {
                    candidateID = nil
                    candidateHits = 0
                    status = "Face detected • match ambiguous"
                    return
                }
            }

            if candidateID == best.person.id {
                candidateHits += 1
            } else {
                candidateID = best.person.id
                candidateHits = 1
            }

            guard force || candidateHits >= 2 else {
                status = "Checking possible match: \(best.person.name)…"
                return
            }

            currentMatch = RecognizedPersonMatch(
                personID: best.person.id,
                name: best.person.name,
                distance: best.distance,
                threshold: best.threshold,
                matchedAt: Date()
            )
            status = "Matched enrolled contact: \(best.person.name) • \(currentMatch!.scoreDescription)"
        } catch {
            candidateID = nil
            candidateHits = 0
            status = "Recognition unavailable: \(error.localizedDescription)"
        }
    }

    func currentPerson() -> EnrolledPerson? {
        guard let id = currentMatch?.personID else { return nil }
        return people.first { $0.id == id }
    }

    func localContext(for person: EnrolledPerson, conversationLog: [FrontendConversationTurn]) -> String {
        var sections: [String] = []
        if !person.notes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            sections.append("Your private note about \(person.name): \(person.notes)")
        }

        let terms = searchTerms(for: person.name)
        var matchingIndices: [Int] = []
        for index in conversationLog.indices {
            let text = conversationLog[index].text
            if terms.contains(where: { text.localizedCaseInsensitiveContains($0) }) {
                matchingIndices.append(index)
            }
        }

        var selected = Set<Int>()
        for index in matchingIndices.suffix(4) {
            selected.insert(index)
            if index > conversationLog.startIndex { selected.insert(index - 1) }
            if index + 1 < conversationLog.endIndex { selected.insert(index + 1) }
        }
        let ordered = selected.sorted().suffix(8)
        if !ordered.isEmpty {
            let lines = ordered.map { index -> String in
                let turn = conversationLog[index]
                let label = turn.role == "user" ? "You" : "Jarvis"
                let compact = turn.text.replacingOccurrences(of: "\n", with: " ")
                return "\(label): \(String(compact.prefix(350)))"
            }
            sections.append("Recent iPhone-stored conversation context mentioning \(person.name):\n" + lines.joined(separator: "\n"))
        }

        return sections.joined(separator: "\n\n")
    }

    func answerAboutCurrentPerson(conversationLog: [FrontendConversationTurn]) -> String {
        guard let match = currentMatch,
              Date().timeIntervalSince(match.matchedAt) <= 8,
              let person = people.first(where: { $0.id == match.personID }) else {
            return "I don't have a confident match to one of your explicitly enrolled people right now, sir."
        }

        let context = localContext(for: person, conversationLog: conversationLog)
        if context.isEmpty {
            return "This appears to match your enrolled contact \(person.name), sir. I don't have any locally stored conversation context or notes about them yet."
        }
        return "This appears to match your enrolled contact \(person.name), sir. \(context)"
    }

    func backendContext(conversationLog: [FrontendConversationTurn]) -> String? {
        guard let match = currentMatch,
              Date().timeIntervalSince(match.matchedAt) <= 8,
              let person = people.first(where: { $0.id == match.personID }) else { return nil }

        let context = localContext(for: person, conversationLog: conversationLog)
        var lines = [
            "[Private on-device known-person context]",
            "The iPhone's closed-set matcher currently estimates that the visible face matches the user's explicitly enrolled contact: \(person.name).",
            "Treat this match as advisory, not certain identity. Never take a consequential action based only on this recognition; ask for identity confirmation when the action depends on who the person is.",
        ]
        if !context.isEmpty { lines.append(context) }
        lines.append("[End private on-device known-person context]")
        return lines.joined(separator: "\n")
    }

    private func load() {
        guard let data = KeychainStore.readData(Self.storageAccount),
              let decoded = try? JSONDecoder().decode([EnrolledPerson].self, from: data) else {
            people = []
            return
        }
        people = decoded
    }

    private func persist() {
        guard let data = try? JSONEncoder().encode(people) else { return }
        KeychainStore.saveData(data, account: Self.storageAccount)
    }

    private struct RankedMatch {
        let person: EnrolledPerson
        let distance: Float
        let threshold: Float
        let accepted: Bool
    }

    private static func rank(
        query: VNFeaturePrintObservation,
        people: [EnrolledPerson],
        toleranceMultiplier: Double
    ) throws -> [RankedMatch] {
        var results: [RankedMatch] = []
        let multiplier = Float(max(1.15, min(toleranceMultiplier, 2.5)))

        for person in people {
            var distances: [Float] = []
            for packed in person.featurePrints {
                guard let enrolled = unpack(packed) else { continue }
                var distance: Float = 0
                try query.computeDistance(&distance, to: enrolled)
                distances.append(distance)
            }
            guard !distances.isEmpty else { continue }
            distances.sort()
            let selected = distances.prefix(min(2, distances.count))
            let score = selected.reduce(0, +) / Float(selected.count)
            let calibration = max(0.01, person.calibrationDistance)
            let threshold = max(calibration * multiplier, calibration + 0.06)
            results.append(RankedMatch(person: person, distance: score, threshold: threshold, accepted: score <= threshold))
        }
        return results.sorted { $0.distance < $1.distance }
    }

    private static func calibrationDistance(for packed: [Data]) throws -> Float {
        let observations = packed.compactMap(unpack)
        guard observations.count >= 2 else {
            throw NSError(domain: "JarvisKnownPeople", code: 2, userInfo: [NSLocalizedDescriptionKey: "At least two usable face samples are required."])
        }
        var distances: [Float] = []
        for i in 0..<(observations.count - 1) {
            for j in (i + 1)..<observations.count {
                var distance: Float = 0
                try observations[i].computeDistance(&distance, to: observations[j])
                distances.append(distance)
            }
        }
        distances.sort()
        guard !distances.isEmpty else { return 0.1 }
        return distances[distances.count / 2]
    }

    private static func faceFeatureArchive(from data: Data) throws -> Data {
        let result = try faceFeature(from: data)
        return try NSKeyedArchiver.archivedData(withRootObject: result.observation, requiringSecureCoding: true)
    }

    private static func faceFeature(from data: Data) throws -> FaceFeatureResult {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw NSError(domain: "JarvisKnownPeople", code: 3, userInfo: [NSLocalizedDescriptionKey: "Could not decode image."])
        }

        let faceRequest = VNDetectFaceRectanglesRequest()
        let faceHandler = VNImageRequestHandler(cgImage: image, options: [:])
        try faceHandler.perform([faceRequest])
        let faces = faceRequest.results ?? []
        guard let face = faces.max(by: { $0.boundingBox.width * $0.boundingBox.height < $1.boundingBox.width * $1.boundingBox.height }) else {
            throw NSError(domain: "JarvisKnownPeople", code: 4, userInfo: [NSLocalizedDescriptionKey: "No clear face detected."])
        }

        let faceArea = face.boundingBox.width * face.boundingBox.height
        guard faceArea >= 0.015 else {
            throw NSError(domain: "JarvisKnownPeople", code: 5, userInfo: [NSLocalizedDescriptionKey: "Face is too small for reliable enrollment or matching."])
        }

        guard let crop = cropFace(image, boundingBox: face.boundingBox) else {
            throw NSError(domain: "JarvisKnownPeople", code: 6, userInfo: [NSLocalizedDescriptionKey: "Could not crop face region."])
        }

        let featureRequest = VNGenerateImageFeaturePrintRequest()
        let featureHandler = VNImageRequestHandler(cgImage: crop, options: [:])
        try featureHandler.perform([featureRequest])
        guard let observation = featureRequest.results?.first as? VNFeaturePrintObservation else {
            throw NSError(domain: "JarvisKnownPeople", code: 7, userInfo: [NSLocalizedDescriptionKey: "Could not generate local face feature print."])
        }
        return FaceFeatureResult(observation: observation, faceCount: faces.count)
    }

    private static func cropFace(_ image: CGImage, boundingBox: CGRect) -> CGImage? {
        let width = CGFloat(image.width)
        let height = CGFloat(image.height)
        var rect = CGRect(
            x: boundingBox.minX * width,
            y: (1 - boundingBox.maxY) * height,
            width: boundingBox.width * width,
            height: boundingBox.height * height
        )
        let padX = rect.width * 0.22
        let padY = rect.height * 0.28
        rect = rect.insetBy(dx: -padX, dy: -padY)
        rect = rect.intersection(CGRect(x: 0, y: 0, width: width, height: height)).integral
        guard rect.width >= 40, rect.height >= 40 else { return nil }
        return image.cropping(to: rect)
    }

    private static func unpack(_ data: Data) -> VNFeaturePrintObservation? {
        try? NSKeyedUnarchiver.unarchivedObject(ofClass: VNFeaturePrintObservation.self, from: data)
    }

    private func searchTerms(for name: String) -> [String] {
        var terms = [name]
        let words = name.split(separator: " ").map(String.init).filter { $0.count >= 3 }
        if let first = words.first, !terms.contains(first) { terms.append(first) }
        if words.count > 1, let last = words.last, !terms.contains(last) { terms.append(last) }
        return terms
    }
}

struct KnownPeopleView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @EnvironmentObject private var frontend: FrontendIntelligenceController

    @State private var name = ""
    @State private var notes = ""
    @State private var selectedItems: [PhotosPickerItem] = []
    @State private var liveSamples: [Data] = []
    @State private var enrollmentStatus = ""
    @State private var isEnrolling = false
    @State private var showForgetAll = false

    private var knownPeople: KnownPeopleController { frontend.knownPeople }

    var body: some View {
        Form {
            Section("Current view") {
                LabeledContent("Recognition", value: knownPeople.status)
                if let match = knownPeople.currentMatch {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(match.name).font(.headline)
                        Text(match.scoreDescription)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }
                Button("Recognize Current Ray-Ban View") {
                    Task { await frontend.recognizeCurrentPerson(force: true) }
                }
                .disabled(!knownPeople.hasEnrolledPeople || !appModel.metaGlasses.hasEligibleDevice)
            }

            Section("Enroll a private contact") {
                TextField("Contact name", text: $name)
                TextField("Your private context / reminder (optional)", text: $notes, axis: .vertical)
                    .lineLimit(2...5)

                PhotosPicker(
                    selection: $selectedItems,
                    maxSelectionCount: 6,
                    matching: .images
                ) {
                    Label("Choose Enrollment Photos", systemImage: "photo.on.rectangle")
                }
                if !selectedItems.isEmpty {
                    Text("\(selectedItems.count) selected photo sample\(selectedItems.count == 1 ? "" : "s")")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Button("Capture Current Ray-Ban Sample") {
                    guard let frame = appModel.metaGlasses.currentFrame,
                          let data = frame.jpegData(compressionQuality: 0.72) else {
                        enrollmentStatus = "No current Ray-Ban frame is available."
                        return
                    }
                    liveSamples.append(data)
                    if liveSamples.count > 6 { liveSamples.removeFirst(liveSamples.count - 6) }
                    enrollmentStatus = "Captured \(liveSamples.count) live sample\(liveSamples.count == 1 ? "" : "s"). Move slightly and capture a few angles."
                }
                .disabled(appModel.metaGlasses.currentFrame == nil)

                if !liveSamples.isEmpty {
                    Text("\(liveSamples.count) live Ray-Ban sample\(liveSamples.count == 1 ? "" : "s") ready")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Button(isEnrolling ? "Enrolling…" : "Enroll Contact") {
                    Task { await enroll() }
                }
                .disabled(isEnrolling || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || selectedItems.count + liveSamples.count < 2)

                if !enrollmentStatus.isEmpty {
                    Text(enrollmentStatus).font(.caption).foregroundStyle(.secondary)
                }

                Text("Use 3–6 clear samples of the same person from slightly different angles when possible. Jarvis detects and crops the largest face, creates an Apple Vision feature print locally, and discards the raw enrollment image after enrollment. Profiles are closed-set: Jarvis only compares against people you explicitly put here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Enrolled people") {
                if knownPeople.people.isEmpty {
                    Text("No people enrolled.").foregroundStyle(.secondary)
                } else {
                    ForEach(knownPeople.people) { person in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(person.name).font(.headline)
                            Text("\(person.featurePrints.count) private samples • enrolled \(person.enrolledAt.formatted(date: .abbreviated, time: .omitted))")
                                .font(.caption).foregroundStyle(.secondary)
                            if !person.notes.isEmpty {
                                Text(person.notes).font(.caption).foregroundStyle(.secondary)
                            }
                            HStack {
                                Button("Use Current Context") {
                                    let context = knownPeople.localContext(for: person, conversationLog: appModel.conversationLog)
                                    appModel.lastResponse = context.isEmpty ? "No local context stored for \(person.name)." : context
                                }
                                .buttonStyle(.borderless)
                                Spacer()
                                Button("Forget", role: .destructive) { knownPeople.delete(person) }
                                    .buttonStyle(.borderless)
                            }
                        }
                        .padding(.vertical, 3)
                    }
                    Button("Forget All Face Profiles", role: .destructive) { showForgetAll = true }
                }
            }

            Section("Privacy & limitations") {
                Text("Feature prints and your labels/notes are stored in this device's Keychain using a this-device-only accessibility class. Raw enrollment photos are not retained by this feature. Recognition remains probabilistic: an uncertain match stays unknown, and the backend is told not to use a face match alone for consequential actions.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("This frontend-only version can retrieve your private note and recent conversation turns stored by the iPhone app that mention the recognized person's name. Full filtered retrieval across the PC's long-term Gmail/calendar/vector memory still requires a later backend update.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Known People")
        .confirmationDialog("Forget every enrolled face profile?", isPresented: $showForgetAll, titleVisibility: .visible) {
            Button("Forget All", role: .destructive) { knownPeople.forgetAll() }
            Button("Cancel", role: .cancel) { }
        }
    }

    private func enroll() async {
        isEnrolling = true
        defer { isEnrolling = false }
        var samples = liveSamples
        for item in selectedItems {
            if let data = try? await item.loadTransferable(type: Data.self), !data.isEmpty {
                samples.append(data)
            }
        }
        enrollmentStatus = await knownPeople.enroll(name: name, notes: notes, imageData: samples)
        if enrollmentStatus.hasPrefix("Enrolled") {
            name = ""
            notes = ""
            selectedItems = []
            liveSamples = []
        }
    }
}
