import AVFoundation
import Foundation
import SoundAnalysis

struct LocalSpeechSnippet: Identifiable, Equatable {
    let id = UUID()
    let timestamp: Date
    let text: String
    let confidence: Double
}

@MainActor
final class LocalSpeechHistoryStore: ObservableObject {
    static let shared = LocalSpeechHistoryStore()

    @Published private(set) var snippets: [LocalSpeechSnippet] = []

    private init() {}

    func record(_ rawText: String, confidence: Double) {
        guard UserDefaults.standard.object(forKey: "jarvis.rollingAudioMemoryEnabled") as? Bool ?? false else { return }
        let text = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count >= 2 else { return }

        if let last = snippets.last,
           Date().timeIntervalSince(last.timestamp) < 2,
           (text == last.text || text.hasPrefix(last.text)) {
            snippets.removeLast()
        }
        snippets.append(LocalSpeechSnippet(timestamp: Date(), text: text, confidence: confidence))
        prune()
    }

    func recent(seconds: TimeInterval = 30) -> [LocalSpeechSnippet] {
        let cutoff = Date().addingTimeInterval(-seconds)
        return snippets.filter { $0.timestamp >= cutoff }
    }

    func latestUsefulText(seconds: TimeInterval = 30) -> String {
        recent(seconds: seconds)
            .suffix(8)
            .map(\.text)
            .joined(separator: " ")
    }

    func clear() {
        snippets.removeAll()
    }

    private func prune() {
        let cutoff = Date().addingTimeInterval(-90)
        snippets.removeAll { $0.timestamp < cutoff }
        if snippets.count > 80 { snippets.removeFirst(snippets.count - 80) }
    }
}

enum PersonalVocabularyStore {
    private static let key = "jarvis.personalVocabulary"

    static func values() -> [String] {
        let raw = UserDefaults.standard.array(forKey: key) as? [String] ?? []
        return raw
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    static func save(_ values: [String]) {
        let normalized = Array(Set(values
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }))
            .sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
        UserDefaults.standard.set(normalized, forKey: key)
    }
}

final class LocalAudioRingBuffer {
    static let shared = LocalAudioRingBuffer()

    private let queue = DispatchQueue(label: "com.us0ris.jarvis.audio-ring", qos: .utility)
    private var samples: [Int16] = []
    private var sampleRate: Double = 16_000
    private let maximumSeconds: Double = 30

    private init() {}

    func append(_ buffer: AVAudioPCMBuffer) {
        guard UserDefaults.standard.object(forKey: "jarvis.rollingAudioMemoryEnabled") as? Bool ?? false,
              let channels = buffer.floatChannelData,
              buffer.frameLength > 0 else { return }

        let rate = buffer.format.sampleRate
        let count = Int(buffer.frameLength)
        let source = channels[0]
        var copied = [Int16]()
        copied.reserveCapacity(count)
        for index in 0..<count {
            let value = max(-1.0, min(1.0, Double(source[index])))
            copied.append(Int16(value * Double(Int16.max)))
        }

        queue.async { [weak self] in
            guard let self else { return }
            if abs(self.sampleRate - rate) > 1 {
                self.samples.removeAll(keepingCapacity: false)
                self.sampleRate = rate
            }
            self.samples.append(contentsOf: copied)
            let maxCount = max(1, Int(self.sampleRate * self.maximumSeconds))
            if self.samples.count > maxCount {
                self.samples.removeFirst(self.samples.count - maxCount)
            }
        }
    }

    func clear() {
        queue.async { [weak self] in self?.samples.removeAll() }
    }

    func wavData() -> Data? {
        queue.sync {
            guard !samples.isEmpty else { return nil }
            var data = Data()
            let channels: UInt16 = 1
            let bitsPerSample: UInt16 = 16
            let rate = UInt32(max(1, Int(sampleRate.rounded())))
            let byteRate = rate * UInt32(channels) * UInt32(bitsPerSample / 8)
            let blockAlign = channels * (bitsPerSample / 8)
            let payloadBytes = UInt32(samples.count * MemoryLayout<Int16>.size)

            data.append(contentsOf: Array("RIFF".utf8))
            data.appendLE(UInt32(36) + payloadBytes)
            data.append(contentsOf: Array("WAVE".utf8))
            data.append(contentsOf: Array("fmt ".utf8))
            data.appendLE(UInt32(16))
            data.appendLE(UInt16(1))
            data.appendLE(channels)
            data.appendLE(rate)
            data.appendLE(byteRate)
            data.appendLE(blockAlign)
            data.appendLE(bitsPerSample)
            data.append(contentsOf: Array("data".utf8))
            data.appendLE(payloadBytes)
            for sample in samples { data.appendLE(sample) }
            return data
        }
    }
}

private extension Data {
    mutating func appendLE<T: FixedWidthInteger>(_ value: T) {
        var little = value.littleEndian
        Swift.withUnsafeBytes(of: &little) { append(contentsOf: $0) }
    }
}

struct LocalSoundEvent: Equatable {
    let identifier: String
    let confidence: Double
    let timestamp: Date
}

final class LocalSoundClassifier: NSObject, SNResultsObserving {
    static let shared = LocalSoundClassifier()

    private let queue = DispatchQueue(label: "com.us0ris.jarvis.sound-analysis", qos: .utility)
    private let lock = NSLock()
    private var analyzer: SNAudioStreamAnalyzer?
    private var request: SNClassifySoundRequest?
    private var configuredSampleRate: Double = 0
    private var configuredChannels: AVAudioChannelCount = 0
    private var latest: LocalSoundEvent?

    private override init() { super.init() }

    func analyze(_ buffer: AVAudioPCMBuffer, at framePosition: AVAudioFramePosition) {
        guard UserDefaults.standard.object(forKey: "jarvis.soundRecognitionEnabled") as? Bool ?? false,
              let copied = Self.copy(buffer) else { return }

        queue.async { [weak self] in
            guard let self else { return }
            do {
                try self.ensureAnalyzer(for: copied.format)
                self.analyzer?.analyze(copied, atAudioFramePosition: framePosition)
            } catch {
                // Sound recognition is advisory; audio capture must not fail because it did.
            }
        }
    }

    func latestEvent(maxAge: TimeInterval = 8) -> LocalSoundEvent? {
        lock.lock(); defer { lock.unlock() }
        guard let latest, Date().timeIntervalSince(latest.timestamp) <= maxAge else { return nil }
        return latest
    }

    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let classification = result as? SNClassificationResult,
              let best = classification.classifications.first,
              best.confidence >= 0.72 else { return }
        lock.lock()
        latest = LocalSoundEvent(identifier: best.identifier, confidence: best.confidence, timestamp: Date())
        lock.unlock()
    }

    func request(_ request: SNRequest, didFailWithError error: Error) {}
    func requestDidComplete(_ request: SNRequest) {}

    private func ensureAnalyzer(for format: AVAudioFormat) throws {
        let rate = format.sampleRate
        let channels = format.channelCount
        if analyzer != nil,
           abs(configuredSampleRate - rate) < 1,
           configuredChannels == channels { return }

        analyzer?.removeAllRequests()
        let analyzer = SNAudioStreamAnalyzer(format: format)
        let request = try SNClassifySoundRequest(classifierIdentifier: .version1)
        request.overlapFactor = 0.5
        try analyzer.add(request, withObserver: self)
        self.analyzer = analyzer
        self.request = request
        configuredSampleRate = rate
        configuredChannels = channels
    }

    private static func copy(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let copy = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: buffer.frameLength) else { return nil }
        copy.frameLength = buffer.frameLength

        if let src = buffer.floatChannelData, let dst = copy.floatChannelData {
            let bytes = Int(buffer.frameLength) * MemoryLayout<Float>.size
            for channel in 0..<Int(buffer.format.channelCount) {
                memcpy(dst[channel], src[channel], bytes)
            }
            return copy
        }
        return nil
    }
}
