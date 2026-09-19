import Foundation
import SwiftUI

/// The compact, authenticated Agency status returned by the Jarvis backend.
/// This is a read-only projection of persisted facts, not an LLM-generated claim.
struct MemoMindCommandSnapshot: Decodable {
    struct Objective: Decodable {
        struct NextStep: Decodable {
            let tool: String
            let status: String
            let stepKey: String

            enum CodingKeys: String, CodingKey {
                case tool, status
                case stepKey = "step_key"
            }
        }
        let title: String
        let state: String
        let evaluatedAt: String
        let planStatus: String
        let stepCount: Int
        let verifiedSteps: Int
        let nextStep: NextStep?

        enum CodingKeys: String, CodingKey {
            case title, state
            case evaluatedAt = "evaluated_at"
            case planStatus = "plan_status"
            case stepCount = "step_count"
            case verifiedSteps = "verified_steps"
            case nextStep = "next_step"
        }
    }

    struct PendingApproval: Decodable {
        let goal: String
        let tool: String
        let summary: String
    }

    struct Alert: Decodable {
        let message: String
        let severity: String
        let seenAt: String

        enum CodingKeys: String, CodingKey {
            case message, severity
            case seenAt = "seen_at"
        }
    }

    let generatedAt: String
    let source: String
    let mode: String
    let totalGoals: Int
    let activeGoals: Int
    let blockedGoals: Int
    let pendingApprovalCount: Int
    let goals: [Objective]
    let pendingApprovals: [PendingApproval]
    let recentAlerts: [Alert]
    let readOnly: Bool

    enum CodingKeys: String, CodingKey {
        case source, mode, goals
        case generatedAt = "generated_at"
        case totalGoals = "total_goals"
        case activeGoals = "active_goals"
        case blockedGoals = "blocked_goals"
        case pendingApprovalCount = "pending_approval_count"
        case pendingApprovals = "pending_approvals"
        case recentAlerts = "recent_alerts"
        case readOnly = "read_only"
    }
}

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
        case status, reply, approval, alert, overview, objective, exception, pendingAction
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
            requiresPhoneApproval: card.kind == .approval || card.kind == .pendingAction,
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

    /// Replace only the Agency command-view slice of the HUD, retaining
    /// conversational replies and other standalone status cards.
    func presentCommandView(_ snapshot: MemoMindCommandSnapshot) {
        guard snapshot.readOnly, snapshot.source == "persisted_agency" else { return }
        let commandKinds: Set<MemoMindHUDCard.Kind> = [
            .overview, .objective, .exception, .pendingAction
        ]
        cards.removeAll { commandKinds.contains($0.kind) }
        cards.append(
            MemoMindHUDCard(
                kind: .overview,
                title: "COMMAND VIEW • " + snapshot.mode.uppercased(),
                body: "\(snapshot.activeGoals) active / \(snapshot.totalGoals) goals. \(snapshot.blockedGoals) blocked. \(snapshot.pendingApprovalCount) need approval. Snapshot: \(snapshot.generatedAt).",
                containsPrivateData: true
            )
        )
        for objective in snapshot.goals {
            let next = objective.nextStep.map { "Next: \($0.tool) [\($0.status)]" }
                ?? "No next step recorded."
            let evaluated = objective.evaluatedAt.isEmpty
                ? "Not yet evaluated."
                : "Last evaluation: \(objective.evaluatedAt)."
            cards.append(
                MemoMindHUDCard(
                    kind: .objective,
                    title: "GOAL • " + objective.state.uppercased(),
                    body: "\(objective.title). \(objective.verifiedSteps)/\(objective.stepCount) plan steps verified. \(next). \(evaluated)",
                    containsPrivateData: true
                )
            )
        }
        for approval in snapshot.pendingApprovals {
            cards.append(
                MemoMindHUDCard(
                    kind: .pendingAction,
                    title: "APPROVAL ON IPHONE",
                    body: "\(approval.goal): \(approval.tool). \(approval.summary)",
                    containsPrivateData: true
                )
            )
        }
        for alert in snapshot.recentAlerts {
            cards.append(
                MemoMindHUDCard(
                    kind: .exception,
                    title: "ALERT • " + alert.severity.uppercased(),
                    body: "\(alert.message). Last seen: \(alert.seenAt).",
                    containsPrivateData: true
                )
            )
        }
        if cards.count > 40 { cards.removeFirst(cards.count - 40) }
        if let overviewIndex = cards.firstIndex(where: { $0.kind == .overview }) {
            selectedIndex = overviewIndex
        } else {
            selectedIndex = min(selectedIndex, cards.count - 1)
        }
        publish()
    }

    func presentProactiveAlert(_ text: String, severity: String) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        cards.append(
            MemoMindHUDCard(
                kind: .alert,
                title: "JARVIS ALERT • " + severity.uppercased(),
                body: cleaned,
                containsPrivateData: true
            )
        )
        if cards.count > 40 { cards.removeFirst(cards.count - 40) }
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
            intent = (cards[selectedIndex].kind == .approval || cards[selectedIndex].kind == .pendingAction)
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
    @EnvironmentObject var appModel: JarvisAppModel
    @State private var isRefreshing = false
    @State private var fetchStatus = "Read-only Agency command view"

    var body: some View {
        let frame = bridge.currentFrame
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("MemoMind One")
                    .font(.title2.weight(.semibold))
                Text(bridge.connectionState.rawValue)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                HStack {
                    Text(fetchStatus)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Spacer()
                    if isRefreshing { ProgressView() }
                    Button("Refresh") {
                        Task { await refreshCommandView() }
                    }
                    .disabled(isRefreshing)
                }

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

                JarvisPhysicalControlView()

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
        .task {
            while !Task.isCancelled {
                await refreshCommandView()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    @MainActor
    private func refreshCommandView() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            try await appModel.refreshMemoMindCommandView()
            fetchStatus = "Agency snapshot received"
        } catch {
            // No invented goal counts or false connected state when the backend
            // has not yet been updated or the phone is offline.
            fetchStatus = "Agency unavailable: " + error.localizedDescription
        }
    }
}
