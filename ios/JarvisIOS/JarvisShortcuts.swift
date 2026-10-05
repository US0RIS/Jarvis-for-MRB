import AppIntents
import Foundation

struct TalkToHorusIntent: AppIntent {
    static var title: LocalizedStringResource = "Talk to Horus"
    static var description = IntentDescription("Open Horus and begin a local push-to-talk interaction.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("talk")
        return .result()
    }
}

struct LocalVisualScanIntent: AppIntent {
    static var title: LocalizedStringResource = "Horus Visual Scan"
    static var description = IntentDescription("Open Horus and run the on-device fast visual scan on the latest Ray-Ban frame.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("scan")
        return .result()
    }
}

struct ReadVisibleTextIntent: AppIntent {
    static var title: LocalizedStringResource = "Horus Read Visible Text"
    static var description = IntentDescription("Use on-device OCR on the latest Ray-Ban frame.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("read_text")
        return .result()
    }
}

struct TogglePassiveVisionIntent: AppIntent {
    static var title: LocalizedStringResource = "Toggle Horus Passive Vision"
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("toggle_vision")
        return .result()
    }
}

struct ToggleHorusSpeechIntent: AppIntent {
    static var title: LocalizedStringResource = "Toggle Horus Spoken Responses"
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("toggle_speech")
        return .result()
    }
}

struct ToggleMeetingNotesIntent: AppIntent {
    static var title: LocalizedStringResource = "Toggle Horus Meeting Notes"
    static var description = IntentDescription("Start or stop the explicit Horus meeting-note recorder.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("meeting")
        return .result()
    }
}

struct StageTextInHorusIntent: AppIntent {
    static var title: LocalizedStringResource = "Send Text to Horus"
    static var description = IntentDescription("Hand text from Shortcuts or a Share Sheet shortcut to the Horus command field without automatically executing it.")
    static var openAppWhenRun = true

    @Parameter(title: "Text")
    var text: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else {
            return .result(dialog: "There is no text to hand to Horus.")
        }
        FrontendImportMailbox.post(cleaned)
        return .result(dialog: "Text staged in Horus. It has not been sent or executed.")
    }
}

struct HorusAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: TalkToHorusIntent(),
            phrases: ["Talk to \(.applicationName)", "Ask \(.applicationName)"],
            shortTitle: "Talk to Horus",
            systemImageName: "waveform"
        )
        AppShortcut(
            intent: LocalVisualScanIntent(),
            phrases: ["Scan with \(.applicationName)", "Visual scan with \(.applicationName)"],
            shortTitle: "Visual Scan",
            systemImageName: "eye"
        )
        AppShortcut(
            intent: ReadVisibleTextIntent(),
            phrases: ["Read this with \(.applicationName)"],
            shortTitle: "Read Visible Text",
            systemImageName: "text.viewfinder"
        )
        AppShortcut(
            intent: TogglePassiveVisionIntent(),
            phrases: ["Toggle vision in \(.applicationName)"],
            shortTitle: "Toggle Vision",
            systemImageName: "camera"
        )
        AppShortcut(
            intent: ToggleHorusSpeechIntent(),
            phrases: ["Toggle speech in \(.applicationName)"],
            shortTitle: "Toggle Speech",
            systemImageName: "speaker.wave.2"
        )
        AppShortcut(
            intent: ToggleMeetingNotesIntent(),
            phrases: ["Toggle meeting notes in \(.applicationName)"],
            shortTitle: "Meeting Notes",
            systemImageName: "record.circle"
        )
        AppShortcut(
            intent: StageTextInHorusIntent(),
            phrases: ["Send text to \(.applicationName)"],
            shortTitle: "Send Text to Horus",
            systemImageName: "square.and.arrow.down"
        )
    }
}
