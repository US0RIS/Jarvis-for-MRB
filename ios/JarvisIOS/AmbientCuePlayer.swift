import AVFoundation
import Foundation

@MainActor
final class AmbientCuePlayer {
    private let audioRouteManager: AudioRouteManager
    private var player: AVAudioPlayer?
    private var currentCue = ""
    private var thinkingTask: Task<Void, Never>?

    init(audioRouteManager: AudioRouteManager) {
        self.audioRouteManager = audioRouteManager
    }

    func startThinking(preferBluetooth: Bool) {
        guard thinkingTask == nil else { return }
        thinkingTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(280))
            guard let self, !Task.isCancelled else { return }
            while !Task.isCancelled {
                self.play("thinking", preferBluetooth: preferBluetooth)
                try? await Task.sleep(for: .milliseconds(760))
            }
        }
    }

    func stopThinking() {
        thinkingTask?.cancel()
        thinkingTask = nil
        if currentCue == "thinking" {
            player?.stop()
            player = nil
            currentCue = ""
        }
    }

    func play(_ cue: String, preferBluetooth: Bool) {
        do {
            try audioRouteManager.prepareForVoice(preferBluetooth: preferBluetooth)
        } catch {
            // The currently active route can still play a cue.
        }

        let notes: [(Double, Double)]
        let baseVolume: Float
        switch cue {
        case "thinking":
            notes = [(470, 0.055), (560, 0.065)]
            baseVolume = 0.18
        case "vision_scan":
            notes = [(820, 0.035), (1040, 0.045)]
            baseVolume = 0.24
        case "search":
            notes = [(610, 0.055), (720, 0.055), (610, 0.045)]
            baseVolume = 0.28
        case "workflow_started":
            notes = [(420, 0.06), (560, 0.07), (700, 0.08)]
            baseVolume = 0.32
        case "task_complete":
            notes = [(660, 0.10), (880, 0.13)]
            baseVolume = 0.45
        case "task_started":
            notes = [(520, 0.10)]
            baseVolume = 0.40
        case "urgent":
            notes = [(840, 0.08), (840, 0.08), (1040, 0.12)]
            baseVolume = 0.52
        case "warning":
            notes = [(430, 0.11), (350, 0.14)]
            baseVolume = 0.45
        case "error":
            notes = [(300, 0.12), (260, 0.16)]
            baseVolume = 0.45
        default:
            notes = [(740, 0.10)]
            baseVolume = 0.40
        }

        let defaults = UserDefaults.standard
        let userScale = max(0.05, min(1.5, defaults.object(forKey: "jarvis.cueVolume") as? Double ?? 1.0))
        let adaptive = defaults.object(forKey: "jarvis.adaptiveCueVolumeEnabled") as? Bool ?? true
        var ambientScale = 1.0
        if adaptive {
            let db = JarvisAudioEnvironment.noiseFloorDBFS
            if db <= -52 { ambientScale = 0.58 }
            else if db <= -43 { ambientScale = 0.78 }
            else if db >= -30 { ambientScale = 1.18 }
        }
        let volume = Float(max(0.02, min(1.0, Double(baseVolume) * userScale * ambientScale)))

        guard let data = Self.makeWAV(notes: notes) else { return }
        currentCue = cue
        player = try? AVAudioPlayer(data: data)
        player?.volume = volume
        player?.prepareToPlay()
        player?.play()
    }

    private static func makeWAV(notes: [(Double, Double)]) -> Data? {
        let sampleRate = 22_050
        let gapSeconds = 0.035
        var samples: [Int16] = []

        for (noteIndex, note) in notes.enumerated() {
            let count = max(1, Int(note.1 * Double(sampleRate)))
            for index in 0..<count {
                let t = Double(index) / Double(sampleRate)
                let progress = Double(index) / Double(max(1, count - 1))
                let envelope = min(1.0, progress * 10.0) * min(1.0, (1.0 - progress) * 8.0)
                let value = sin(2.0 * Double.pi * note.0 * t) * 6_000.0 * envelope
                samples.append(Int16(max(-32_000, min(32_000, value))))
            }
            if noteIndex < notes.count - 1 {
                samples.append(contentsOf: repeatElement(0, count: Int(gapSeconds * Double(sampleRate))))
            }
        }

        guard !samples.isEmpty else { return nil }
        let pcmBytes = samples.count * MemoryLayout<Int16>.size
        var data = Data()
        data.append("RIFF".data(using: .ascii)!)
        appendUInt32(UInt32(36 + pcmBytes), to: &data)
        data.append("WAVEfmt ".data(using: .ascii)!)
        appendUInt32(16, to: &data)
        appendUInt16(1, to: &data)
        appendUInt16(1, to: &data)
        appendUInt32(UInt32(sampleRate), to: &data)
        appendUInt32(UInt32(sampleRate * 2), to: &data)
        appendUInt16(2, to: &data)
        appendUInt16(16, to: &data)
        data.append("data".data(using: .ascii)!)
        appendUInt32(UInt32(pcmBytes), to: &data)
        for sample in samples { appendInt16(sample, to: &data) }
        return data
    }

    private static func appendUInt16(_ value: UInt16, to data: inout Data) {
        var little = value.littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    private static func appendUInt32(_ value: UInt32, to data: inout Data) {
        var little = value.littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    private static func appendInt16(_ value: Int16, to data: inout Data) {
        var little = value.littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }
}
