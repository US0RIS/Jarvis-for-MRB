import Foundation
import SwiftUI

/// Jarvis-side contract for MemoMind One. No vendor BLE UUIDs or SDK types belong
/// here: the future phone/glasses transport translates real hardware events to
/// MemoMindInput, and renders MemoMindHUDFrame onto the actual HUD.
enum MemoMindInput: String, CaseIterable {
    case tap
    case doubleTap
    case swipeForward
    case swipeBackward
    case longPress
    case headNod
    case headShake
    case ringNext
    case ringPrevious
    case ringSelect
    case ringBack
}

enum MemoMindIntent: Equatable {
    case nextCard
    case previousCard
    case revealCurrentCard
    case requestVoiceCapture
    case dismissCurrentCard
    case showApprovalOnPhone
    case none
}

struct MemoMindHUDCard: Equatable, Identifiable {
    enum Kind: String {
        case status, reply, approval, alert
    }

    let id: UUID
    let kind: Kind
    let title: String
    let body: String
    let containsPrivateData: Bool
    let createdAt: Date

    init(kind: Kind, title: String, body: String, containsPrivateData: Bool = false) {
        self.id = UUID()
        self.kind = kind
        self.title = title
        self.body = body
        self.containsPrivateData = containsPrivateData
        self.createdAt = Date()
    }
}

struct MemoMindHUDFrame: Equatable {
    let title: String
    let lines: [String]
    let index: Int
    let count: Int
    let requiresPhoneApproval: Bool
    let isRedacted: Bool

    static func render(
        _ card: MemoMindHUDCard,
        index: Int,
        count: Int,
        privateContentAllowed: Bool
    ) -> MemoMindHUDFrame {
        let redacted = card.containsPrivateData && !privateContentAllowed
        let text = redacted
            ? "Private content hidden. Open Jarvis on iPhone to view."
            : card.body
        let clean = text
            .replacingOccurrences(of: "\r", with: " ")
            .replacingOccurrences(of: "\t", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        // Conservative monochrome text layout, independent of vendor pixel API.
        // The official beta/demo report different widths; calibration is deferred.
        let wrapped = Self.wrap(clean, width: 34, maximumLines: 6)
        return MemoMindHUDFrame(
            title: String(card.title.prefix(42)),
            lines: wrapped,
            index: index,
            count: count,
            requiresPhoneApproval: card.kind == .approval,
            isRedacted: redacted
        )
    }

    private static func wrap(_ text: String, width: Int, maximumLines: Int) -> [String] {
        var lines: [String] = []
        var current = ""
        let words = text.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        for word in words {
            var remaining = word
            while remaining.count > width {
                if !current.isEmpty {
                    lines.append(current)
                    current = ""
                }
                lines.append(String(remaining.prefix(width)))
                remaining = String(remaining.dropFirst(width))
            }
            if remaining.isEmpty { continue }
            if current.isEmpty {
                current = remaining
            } else if current.count + 1 + remaining.count <= width {
                current += " " + remaining
            } else {
                lines.append(current)
                current = remaining
            }
        }
        if !current.isEmpty { lines.append(current) }
        if lines.count > maximumLines {
            lines = Array(lines.prefix(maximumLines))
            if let last = lines.last {
                lines[maximumLines - 1] = String(last.prefix(width - 1)) + "…"
            }
        }
        return lines.isEmpty ? [""] : lines
    }
}

@MainActor
final class MemoMindBridge: ObservableObject {
    enum ConnectionState: String {
        case simulator = "Simulator only"
        case disconnected = "Not connected"
        case connected = "Connected"
    }

    @Published private(set) var connectionState: ConnectionState = .simulator
    @Published private(set) var cards: [MemoMindHUDCard] = [
        MemoMindHUDCard(
            kind: .status,
            title: "JARVIS",
            body: "MemoMind preview ready. No glasses connected."
        )
    ]
    @Published private(set) var selectedIndex = 0
    @Published private(set) var lastIntent: MemoMindIntent = .none

    /// Defaults off. This is only a *display* preference; it does not enable
    /// microphone capture, meeting recording, or remote actions.
    @Published var showPrivateContent: Bool {
        didSet {
            UserDefaults.standard.set(showPrivateContent, forKey: "jarvis.memomind.showPrivateContent")
            publish()
        }
    }

    /// The real MemoMind SDK adapter installs this when available. No fake
    /// pairing, simulated BLE handshake, or invented wire protocol is performed.
    var onHUDFrame: ((MemoMindHUDFrame) -> Void)?
    var onIntent: ((MemoMindIntent) -> Void)?

    init() {
        showPrivateContent = UserDefaults.standard.bool(forKey: "jarvis.memomind.showPrivateContent")
    }

    var currentFrame: MemoMindHUDFrame {
        MemoMindHUDFrame.render(
            cards[selectedIndex],
            index: selectedIndex,
            count: cards.count,
            privateContentAllowed: showPrivateContent
        )
    }

    func setHardwareConnected(_ connected: Bool) {
        connectionState = connected ? .connected : .disconnected
        publish()
    }

    func presentAssistantReply(_ text: String, requiresConfirmation: Bool) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        let card = MemoMindHUDCard(
            kind: requiresConfirmation ? .approval : .reply,
            title: requiresConfirmation ? "APPROVAL ON IPHONE" : "JARVIS REPLY",
            body: cleaned,
            containsPrivateData: true
        )
        cards.append(card)
        if cards.count > 20 { cards.removeFirst(cards.count - 20) }
        selectedIndex = cards.count - 1
        publish()
    }

    func presentStatus(_ text: String) {
        cards.append(MemoMindHUDCard(kind: .status, title: "STATUS", body: text))
        if cards.count > 20 { cards.removeFirst(cards.count - 20) }
        selectedIndex = cards.count - 1
        publish()
    }

    @discardableResult
    func receive(_ event: MemoMindInput) -> MemoMindIntent {
        let intent: MemoMindIntent
        switch event {
        case .swipeForward, .ringNext:
            selectedIndex = min(cards.count - 1, selectedIndex + 1)
            intent = .nextCard
        case .swipeBackward, .ringPrevious:
            selectedIndex = max(0, selectedIndex - 1)
            intent = .previousCard
        case .tap, .headNod, .ringSelect:
            intent = cards[selectedIndex].kind == .approval
                ? .showApprovalOnPhone : .revealCurrentCard
        case .doubleTap, .longPress:
            intent = .requestVoiceCapture
        case .headShake, .ringBack:
            // Dismissing a HUD card is NOT a denial of an Agency action.
            intent = .dismissCurrentCard
            cards.remove(at: selectedIndex)
            if cards.isEmpty {
                cards = [MemoMindHUDCard(kind: .status, title: "JARVIS", body: "HUD clear.")]
            }
            selectedIndex = min(selectedIndex, cards.count - 1)
        }
        lastIntent = intent
        publish()
        onIntent?(intent)
        return intent
    }

    private func publish() {
        onHUDFrame?(currentFrame)
    }
}

/// Native iPhone HUD simulator: test the product experience before hardware or
/// MemoMind's beta SDK is available. It does not claim to render on real glasses.
struct MemoMindPreviewView: View {
    @EnvironmentObject var bridge: MemoMindBridge

    var body: some View {
        let frame = bridge.currentFrame
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("MemoMind One")
                    .font(.title2.weight(.semibold))
                Text(bridge.connectionState.rawValue)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 14) {
                    Text(frame.title)
                        .font(.system(size: 16, weight: .semibold, design: .monospaced))
                    ForEach(Array(frame.lines.enumerated()), id: \.offset) { entry in
                        Text(entry.element)
                            .font(.system(size: 17, design: .monospaced))
                    }
                    if frame.requiresPhoneApproval {
                        Text("APPROVE IN JARVIS ON IPHONE")
                            .font(.system(size: 12, weight: .bold, design: .monospaced))
                    }
                    Text("\(frame.index + 1) / \(frame.count)")
                        .font(.system(size: 12, design: .monospaced))
                }
                .foregroundStyle(.green)
                .padding(22)
                .frame(maxWidth: .infinity, minHeight: 240, alignment: .topLeading)
                .background(.black, in: RoundedRectangle(cornerRadius: 18))

                Toggle("Show private Jarvis replies on HUD", isOn: $bridge.showPrivateContent)
                Text("Off by default. A physical gesture never approves, denies, sends, or deletes anything. Activation of actual glasses still requires MemoMind's documented SDK/protocol and hardware testing.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                HStack {
                    Button("Previous") { bridge.receive(.swipeBackward) }
                    Spacer()
                    Button("Tap") { bridge.receive(.tap) }
                    Spacer()
                    Button("Next") { bridge.receive(.swipeForward) }
                }
                .buttonStyle(.bordered)
                Button("Simulate incoming status") {
                    bridge.presentStatus("Jarvis is ready. Your active goals and next steps will appear here.")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
        }
        .navigationTitle("Glasses")
    }
}
