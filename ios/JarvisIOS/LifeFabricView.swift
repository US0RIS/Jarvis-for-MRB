import Foundation
import SwiftUI

/// One explicitly enrolled life-state workspace. It does not watch the user,
/// infer their accounts, submit forms, spend, send messages or actuate devices.
struct LifeFabricView: View {
    @EnvironmentObject private var appModel: JarvisAppModel

    @State private var records: [LifeFabricRecord] = []
    @State private var readiness: LifeFabricReadiness?
    @State private var candidates: [LifeFabricFrictionCandidates.Candidate] = []
    @State private var busy = false
    @State private var status = "No Life Fabric data loaded."
    @State private var recordTitle = ""
    @State private var recordDescription = ""
    @State private var recordNextStep = ""
    @State private var recordLocation = ""
    @State private var recordDomain = "other"
    @State private var recordKind = "task"
    @State private var hasDeadline = false
    @State private var deadline = Date().addingTimeInterval(86400)
    @State private var createRequestID = UUID().uuidString

    @State private var transitionKind = "moving"
    @State private var transitionTitle = ""
    @State private var transitionRequestID = UUID().uuidString
    @State private var frictionLabel = ""
    @State private var frictionStatus = ""
    @State private var handoffTitle = ""
    @State private var handoffSummary = ""
    @State private var handoffNext = ""
    @State private var linkedIDs: Set<String> = []
    @State private var handoffRequestID = UUID().uuidString
    @State private var resumeStatus = ""
    @State private var resumeText = ""
    @State private var whatIfMinutes = "120"
    @State private var whatIfDays = "3"
    @State private var whatIfPerDay = "60"
    @State private var whatIfStatus = ""
    @State private var pendingConfirm: LifeFabricRecord?
    @State private var pendingRetire: LifeFabricRecord?
    @State private var pendingForget: LifeFabricRecord?
    @State private var confirmFrictionClear = false

    private let domains = [
        "morning", "travel", "work", "food", "home", "shopping",
        "moving", "money", "relationships", "health", "digital",
        "vehicle", "recovery", "maintenance", "uncertainty",
        "opportunity", "other",
    ]
    private let transitions = [
        ("moving", "Moving"), ("travel", "Travel"),
        ("new_job", "New job"), ("purchase", "Purchase"),
        ("vehicle", "Vehicle service"), ("health_followup", "Health follow-up"),
    ]

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                introduction
                readinessPanel
                capturePanel
                taskPanel
                transitionsPanel
                frictionPanel
                handoffPanel
                whatIfPanel
                Text("This view maintains only records you explicitly enter. "
                     + "It cannot yet discover subscriptions, receipts, medications, "
                     + "household stock, visits or physical completion automatically.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding()
        }
        .navigationTitle("Life")
        .navigationBarTitleDisplayMode(.inline)
        .task { await refresh() }
        .confirmationDialog(
            "Confirm this task is complete?",
            isPresented: Binding(
                get: { pendingConfirm != nil },
                set: { if !$0 { pendingConfirm = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("I personally confirm completion") {
                if let item = pendingConfirm {
                    Task { await confirm(item) }
                }
                pendingConfirm = nil
            }
            Button("Cancel", role: .cancel) { pendingConfirm = nil }
        } message: {
            Text("This saves your confirmation. It does not assert a provider "
                 + "receipt, sensor observation or independently verified outcome.")
        }
.confirmationDialog(
            "Permanently forget this one Life Fabric record?",
            isPresented: Binding(
                get: { pendingForget != nil },
                set: { if !$0 { pendingForget = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("Delete this record and its receipts", role: .destructive) {
                if let item = pendingForget { Task { await forget(item) } }
                pendingForget = nil
            }
            Button("Cancel", role: .cancel) { pendingForget = nil }
        } message: {
            Text("This removes the selected record from Jarvis's Life Fabric "
                 + "ledger. Other tasks that depend on it become blocked. "
                 + "This does not erase separate Jarvis records or backups.")
        }
        .confirmationDialog(
            "Retire this record without claiming completion?",
            isPresented: Binding(
                get: { pendingRetire != nil },
                set: { if !$0 { pendingRetire = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("Retire record", role: .destructive) {
                if let item = pendingRetire {
                    Task { await retire(item) }
                }
                pendingRetire = nil
            }
            Button("Cancel", role: .cancel) { pendingRetire = nil }
        }
        .confirmationDialog(
            "Delete the entire Friction Observatory log?",
            isPresented: $confirmFrictionClear,
            titleVisibility: .visible
        ) {
            Button("Delete all manually logged inconveniences", role: .destructive) {
                Task { await clearFriction() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This does not delete tasks or other separate Jarvis memories.")
        }
    }

    private var introduction: some View {
        GroupBox("Five-year friction • Life Fabric") {
            VStack(alignment: .leading, spacing: 7) {
                Text("Remember commitments, maintain an explicit asset inventory, "
                     + "track real completion evidence, hand off unfinished work, "
                     + "and identify inconvenience you repeatedly log.")
                    .font(.callout)
                Text("Private Jarvis PC ledger • manual enrollment • zero model calls "
                     + "for deadline, recurrence and time-budget calculations.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                HStack {
                    Button(busy ? "Working…" : "Refresh Life") {
                        Task { await refresh() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(busy)
                    Spacer()
                    Text("\(records.count) visible records")
                        .font(.caption)
                }
                Text(status)
                    .font(.caption)
                    .accessibilityIdentifier("life-fabric-status")
            }
        }
    }

    private var readinessPanel: some View {
        GroupBox("Readiness • temporal intelligence") {
            VStack(alignment: .leading, spacing: 8) {
                if let readiness {
                    if readiness.setupRequired {
                        Text("No enrolled records: Jarvis cannot assess your day yet.")
                            .font(.callout)
                    } else {
                        Text("\(readiness.tasksTotal) enrolled tasks • "
                             + "\(readiness.due.count) due soon/overdue • "
                             + "\(readiness.blocked.count) blocked")
                            .font(.callout)
                        if readiness.allClear {
                            Text("No enrolled upcoming deadlines or blocked dependencies. "
                                 + "Unrecorded obligations are unknown.")
                                .font(.caption)
                        }
                    }
                    ForEach(readiness.due) { item in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title).font(.subheadline.weight(.medium))
                            Text(item.dueState.replacingOccurrences(of: "_", with: " ")
                                 + " • " + item.deadlineAt)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    ForEach(readiness.blocked) { item in
                        Text("Blocked: " + item.title
                             + " (\(item.blockingTaskIDs.count) prerequisite(s))")
                            .font(.caption)
                    }
                    if !readiness.unknown.isEmpty {
                        Text("\(readiness.unknown.count) tasks have unknown outcomes.")
                            .font(.caption)
                    }
                    Text(readiness.allClearQualifier)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Readiness unavailable until Jarvis is reachable.")
                        .font(.caption)
                }
            }
        }
    }

    private var capturePanel: some View {
        GroupBox("Capture a real-world obligation or possession") {
            VStack(alignment: .leading, spacing: 10) {
                Picker("Record type", selection: $recordKind) {
                    Text("Obligation").tag("task")
                    Text("Asset").tag("asset")
                }
                .pickerStyle(.segmented)
                TextField("What needs doing / what do you own?", text: $recordTitle)
                    .textFieldStyle(.roundedBorder)
                Picker("Domain", selection: $recordDomain) {
                    ForEach(domains, id: \.self) { domain in
                        Text(domain.capitalized).tag(domain)
                    }
                }
                TextField("Context (optional)", text: $recordDescription, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...4)
                if recordKind == "task" {
                    TextField("Next concrete step (optional)", text: $recordNextStep)
                        .textFieldStyle(.roundedBorder)
                    Toggle("Exact deadline", isOn: $hasDeadline)
                    if hasDeadline {
                        DatePicker("Deadline", selection: $deadline)
                    }
                } else {
                    TextField("Where you keep it (optional)", text: $recordLocation)
                        .textFieldStyle(.roundedBorder)
                    Text("One manually reported item. This is not a live sensor.")
                        .font(.caption2)
                }
                Button("Save explicit \(recordKind == "task" ? "obligation" : "asset")") {
                    Task { await capture() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || recordTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }

    private var taskPanel: some View {
        GroupBox("Your enrolled state • certainty") {
            VStack(alignment: .leading, spacing: 10) {
                if records.isEmpty {
                    Text("Add a task or asset above, or create a transition checklist.")
                        .font(.caption)
                }
                ForEach(records.filter { $0.kind != "handoff" && $0.kind != "transition" }) { record in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(record.title)
                            .font(.subheadline.weight(.medium))
                        Text(record.domain + " • " + record.completionState
                             .replacingOccurrences(of: "_", with: " "))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if let value = record.data.description, !value.isEmpty {
                            Text(value).font(.caption)
                        }
                        if let next = record.data.nextStep, !next.isEmpty {
                            Text("Next: " + next).font(.caption)
                        }
                        if let due = record.deadlineAt {
                            Text("Due: " + due).font(.caption2)
                        }
                        if let whereStored = record.data.location, !whereStored.isEmpty {
                            Text("Stored: " + whereStored).font(.caption2)
                        }
                        HStack {
                            if record.kind == "task",
                               !["user_confirmed", "sensor_observed",
                                 "document_supported", "provider_reported"]
                                .contains(record.completionState) {
                                Button("I completed this") {
                                    pendingConfirm = record
                                }
                                .buttonStyle(.bordered)
                                .disabled(busy)
                            }
                            Button("Retire", role: .destructive) {
                                pendingRetire = record
                            }
                            .buttonStyle(.bordered)
                            .disabled(busy)
                            Button("Forget", role: .destructive) {
                                pendingForget = record
                            }
                            .buttonStyle(.bordered)
                            .disabled(busy)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 9))
                }
            }
        }
    }

    private var transitionsPanel: some View {
        GroupBox("Life transitions • coordinated checklists") {
            VStack(alignment: .leading, spacing: 8) {
                Text("Create eight concrete, initially unverified obligations "
                     + "for a real life event. No purchases or outreach occur.")
                    .font(.caption)
                Picker("Transition", selection: $transitionKind) {
                    ForEach(transitions.indices, id: \.self) { index in
                        Text(transitions[index].1).tag(transitions[index].0)
                    }
                }
                TextField("Name this event", text: $transitionTitle)
                    .textFieldStyle(.roundedBorder)
                Button("Create 8-step checklist") {
                    Task { await createTransition() }
                }
                .buttonStyle(.bordered)
                .disabled(busy || transitionTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }

    private var frictionPanel: some View {
        GroupBox("Friction Observatory • explicit incidents") {
            VStack(alignment: .leading, spacing: 8) {
                TextField("What minor inconvenience just happened?", text: $frictionLabel)
                    .textFieldStyle(.roundedBorder)
                Button("Log this inconvenience once") {
                    Task { await logFriction() }
                }
                .buttonStyle(.bordered)
                .disabled(busy || frictionLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Text("A recurring candidate needs three distinct days in 30 days; "
                     + "Jarvis does not watch your behavior or deploy an automation.")
                    .font(.caption2)
                if !frictionStatus.isEmpty {
                    Text(frictionStatus).font(.caption)
                }
                Button("Clear my friction log", role: .destructive) {
                    confirmFrictionClear = true
                }
                .buttonStyle(.bordered)
                .disabled(busy)
                ForEach(candidates) { candidate in
                    Text("\(candidate.label) • \(candidate.occurrences) occurrences "
                         + "on \(candidate.days) days. Consider a permanent fix.")
                        .font(.caption)
                }
            }
        }
    }

    private var handoffPanel: some View {
        GroupBox("Universal handoff • preserve intent") {
            VStack(alignment: .leading, spacing: 9) {
                TextField("Activity name", text: $handoffTitle)
                    .textFieldStyle(.roundedBorder)
                TextField("What have you decided so far?", text: $handoffSummary, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...4)
                TextField("Exact next step", text: $handoffNext)
                    .textFieldStyle(.roundedBorder)
                ForEach(records.filter { $0.kind == "task" }.prefix(8)) { record in
                    Toggle(record.title, isOn: Binding(
                        get: { linkedIDs.contains(record.id) },
                        set: { selected in
                            if selected { linkedIDs.insert(record.id) }
                            else { linkedIDs.remove(record.id) }
                        }
                    ))
                    .font(.caption)
                }
                Button("Save continuation packet") {
                    Task { await createHandoff() }
                }
                .buttonStyle(.bordered)
                .disabled(busy || handoffTitle.isEmpty
                          || handoffSummary.isEmpty || handoffNext.isEmpty)
                ForEach(records.filter { $0.kind == "handoff" }) { record in
                    Button("Resume • " + record.title) {
                        Task { await resume(record.id) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                if !resumeStatus.isEmpty {
                    Text(resumeStatus)
                        .font(.caption)
                }
                if !resumeText.isEmpty {
                    Text(resumeText)
                        .font(.callout)
                        .textSelection(.enabled)
                }
                Text("This restores an intention packet; it does not reopen external "
                     + "applications or authorize remote device actions.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var whatIfPanel: some View {
        GroupBox("Personal simulation • bounded time what-if") {
            VStack(alignment: .leading, spacing: 8) {
                TextField("New activity total minutes", text: $whatIfMinutes)
                    .keyboardType(.numberPad)
                    .textFieldStyle(.roundedBorder)
                TextField("Days available (1–31)", text: $whatIfDays)
                    .keyboardType(.numberPad)
                    .textFieldStyle(.roundedBorder)
                TextField("Assumed free minutes per day", text: $whatIfPerDay)
                    .keyboardType(.numberPad)
                    .textFieldStyle(.roundedBorder)
                Button("Calculate assumed time budget") {
                    Task { await simulate() }
                }
                .buttonStyle(.bordered)
                .disabled(busy)
                if !whatIfStatus.isEmpty {
                    Text(whatIfStatus).font(.caption)
                }
                Text("Your assumed free time only. No connected calendar, "
                     + "travel conflicts or future outcome prediction.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func refresh() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            async let overview = client.lifeReadiness()
            async let current = client.lifeRecords()
            async let repeated = client.lifeFrictionCandidates()
            let a = try await overview
            let b = try await current
            let c = try await repeated
            readiness = a
            records = b.records
            candidates = c.candidates
            status = "Confirmed current private Life Fabric records. "
                + "No external actions taken."
        } catch {
            status = "Life Fabric could not be loaded. Check the matching "
                + "backend version and private token. Existing data not cleared."
        }
    }

    private func capture() async {
        guard !busy else { return }
        busy = true
        do {
            _ = try await client.lifeCreate(
                kind: recordKind, title: recordTitle, domain: recordDomain,
                description: recordDescription,
                deadlineAt: recordKind == "task" && hasDeadline
                    ? ISO8601DateFormatter().string(from: deadline) : nil,
                nextStep: recordKind == "task" ? recordNextStep : "",
                location: recordKind == "asset" ? recordLocation : "",
                quantity: recordKind == "asset" ? 1 : nil,
                requestID: createRequestID
            )
            createRequestID = UUID().uuidString
            recordTitle = ""
            recordDescription = ""
            recordNextStep = ""
            recordLocation = ""
            status = "Saved exactly one new user-enrolled record."
        } catch {
            status = "Save unconfirmed; refresh before deciding whether to retry. "
                + "No automatic second write attempted."
        }
        busy = false
        await refresh()
    }

    private func confirm(_ item: LifeFabricRecord) async {
        guard !busy else { return }
        busy = true
        do {
            let updated = try await client.lifeConfirmDone(id: item.id, version: item.version)
            status = "Recorded user confirmation: " + updated.title
                + ". This is not independent proof."
        } catch {
            status = "Completion write unconfirmed or stale; refresh before retrying."
        }
        busy = false
        await refresh()
    }

    private func retire(_ item: LifeFabricRecord) async {
        guard !busy else { return }
        busy = true
        do {
            _ = try await client.lifeRetire(id: item.id, version: item.version)
            status = "Record retired. Completion was not fabricated."
        } catch {
            status = "Retirement unconfirmed or stale; inspect records before retrying."
        }
        busy = false
        await refresh()
    }

    private func forget(_ item: LifeFabricRecord) async {
        guard !busy else { return }
        busy = true
        do {
            let result = try await client.lifeForget(id: item.id, version: item.version)
            status = "Deleted \(result.deletedRecords) record and "
                + "\(result.deletedReceipts) receipt(s). Other records unchanged."
        } catch {
            status = "Deletion unconfirmed or stale. Refresh before retrying."
        }
        busy = false
        await refresh()
    }

    private func clearFriction() async {
        guard !busy else { return }
        busy = true
        do {
            let result = try await client.lifeClearFriction()
            frictionStatus = "Deleted \(result.deletedFrictionEvents) friction event(s)."
        } catch {
            frictionStatus = "Cannot confirm friction history deletion; refresh."
        }
        busy = false
        await refresh()
    }

    private func createTransition() async {
        guard !busy else { return }
        busy = true
        do {
            let result = try await client.lifeTransition(
                template: transitionKind,
                title: transitionTitle,
                requestID: transitionRequestID
            )
            transitionRequestID = UUID().uuidString
            transitionTitle = ""
            status = "Created \(result.tasks.count) explicit, unverified transition tasks."
        } catch {
            status = "Checklist creation unconfirmed; refresh before retrying. "
                + "The same request id remains in use."
        }
        busy = false
        await refresh()
    }

    private func logFriction() async {
        guard !busy else { return }
        busy = true
        do {
            let logged = try await client.lifeLogFriction(frictionLabel)
            frictionStatus = "Recorded on \(logged.distinctUTCDays) distinct days "
                + "in the last 30. "
                + (logged.candidateRepeatedFriction
                   ? "Recurring inconvenience candidate." : "No recurrence conclusion yet.")
            frictionLabel = ""
        } catch {
            frictionStatus = "Log unconfirmed; refresh before logging another occurrence."
        }
        busy = false
        await refresh()
    }

    private func createHandoff() async {
        guard !busy else { return }
        busy = true
        do {
            _ = try await client.lifeHandoff(
                title: handoffTitle, summary: handoffSummary,
                nextStep: handoffNext,
                linkedIDs: Array(linkedIDs).sorted(),
                requestID: handoffRequestID
            )
            handoffRequestID = UUID().uuidString
            handoffTitle = ""
            handoffSummary = ""
            handoffNext = ""
            linkedIDs = []
            resumeStatus = "Continuation packet saved on Jarvis PC."
        } catch {
            resumeStatus = "Handoff save unconfirmed; refresh before retrying."
        }
        busy = false
        await refresh()
    }

    private func resume(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let packet = try await client.lifeResume(id)
            resumeStatus = "Restored explicit continuation, not external app state."
            resumeText = packet.handoff.title + "\n"
                + (packet.handoff.data.description ?? "")
                + "\nNEXT: " + (packet.handoff.data.nextStep ?? "")
                + "\nLinked active records: "
                + packet.linkedRecords.map(\.title).joined(separator: ", ")
        } catch {
            resumeStatus = "Could not retrieve the exact continuation packet."
        }
    }

    private func simulate() async {
        guard !busy else { return }
        guard let activity = Int(whatIfMinutes), let days = Int(whatIfDays),
              let perDay = Int(whatIfPerDay) else {
            whatIfStatus = "Enter integers within the listed ranges."
            return
        }
        busy = true
        defer { busy = false }
        do {
            let report = try await client.lifeWhatIf(
                activity: activity, days: days, freePerDay: perDay
            )
            whatIfStatus = "Assumed \(report.availableMinutes) available minutes; "
                + "\(report.remainingMinutes) remain after this activity. "
                + (report.fitsAssumedTimeBudget ? "Fits assumed budget." : "Exceeds assumed budget.")
        } catch {
            whatIfStatus = "Could not evaluate bounded time assumptions."
        }
    }
}
