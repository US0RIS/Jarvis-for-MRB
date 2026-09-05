import AppIntents
import Foundation

struct TalkToJarvisIntent: AppIntent {
    static var title: LocalizedStringResource = "Talk to Jarvis"
    static var description = IntentDescription("Open Jarvis and begin a local push-to-talk interaction.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("talk")
        return .result()
    }
}

struct LocalVisualScanIntent: AppIntent {
    static var title: LocalizedStringResource = "Jarvis Visual Scan"
    static var description = IntentDescription("Open Jarvis and run the on-device fast visual scan on the latest Ray-Ban frame.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("scan")
        return .result()
    }
}

struct ReadVisibleTextIntent: AppIntent {
    static var title: LocalizedStringResource = "Jarvis Read Visible Text"
    static var description = IntentDescription("Use on-device OCR on the latest Ray-Ban frame.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("read_text")
        return .result()
    }
}

struct TogglePassiveVisionIntent: AppIntent {
    static var title: LocalizedStringResource = "Toggle Jarvis Passive Vision"
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("toggle_vision")
        return .result()
    }
}

struct ToggleJarvisSpeechIntent: AppIntent {
    static var title: LocalizedStringResource = "Toggle Jarvis Spoken Responses"
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("toggle_speech")
        return .result()
    }
}

struct ToggleMeetingNotesIntent: AppIntent {
    static var title: LocalizedStringResource = "Toggle Jarvis Meeting Notes"
    static var description = IntentDescription("Start or stop the explicit Jarvis meeting-note recorder.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        FrontendActionMailbox.post("meeting")
        return .result()
    }
}

struct StageTextInJarvisIntent: AppIntent {
    static var title: LocalizedStringResource = "Send Text to Jarvis"
    static var description = IntentDescription("Hand text from Shortcuts or a Share Sheet shortcut to the Jarvis command field without automatically executing it.")
    static var openAppWhenRun = true

    @Parameter(title: "Text")
    var text: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else {
            return .result(dialog: "There is no text to hand to Jarvis.")
        }
        FrontendImportMailbox.post(cleaned)
        return .result(dialog: "Text staged in Jarvis. It has not been sent or executed.")
    }
}

struct JarvisAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: TalkToJarvisIntent(),
            phrases: ["Talk to \(.applicationName)", "Ask \(.applicationName)"],
            shortTitle: "Talk to Jarvis",
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
            intent: ToggleJarvisSpeechIntent(),
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
            intent: StageTextInJarvisIntent(),
            phrases: ["Send text to \(.applicationName)"],
            shortTitle: "Send Text to Jarvis",
            systemImageName: "square.and.arrow.down"
        )
    }
}
