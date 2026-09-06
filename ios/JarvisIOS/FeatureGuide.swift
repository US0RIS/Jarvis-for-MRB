import SwiftUI
import UIKit

struct JarvisFeature: Identifiable, Hashable {
    enum Status: String, CaseIterable, Hashable {
        case ready = "Ready"
        case frontendOnly = "iPhone-only"
        case setup = "Setup required"
        case optional = "Optional"
        case pendingBackend = "Backend update pending"
        case limited = "Platform-limited"

        var icon: String {
            switch self {
            case .ready: return "checkmark.circle.fill"
            case .frontendOnly: return "iphone.circle.fill"
            case .setup: return "wrench.and.screwdriver.fill"
            case .optional: return "slider.horizontal.3"
            case .pendingBackend: return "clock.badge.exclamationmark"
            case .limited: return "exclamationmark.triangle.fill"
            }
        }
    }

    let id: String
    let category: String
    let title: String
    let summary: String
    let details: String
    let examplePrompt: String
    let verification: String
    let status: Status
    let symbol: String
    let runnable: Bool

    var searchableText: String {
        [category, title, summary, details, examplePrompt, verification, status.rawValue]
            .joined(separator: " ")
            .lowercased()
    }
}

enum JarvisFeatureCatalog {
    static let all: [JarvisFeature] = build()

    private static func f(
        _ id: String,
        _ category: String,
        _ title: String,
        _ summary: String,
        _ details: String,
        _ prompt: String,
        _ verification: String,
        _ status: JarvisFeature.Status = .ready,
        _ symbol: String,
        runnable: Bool = true
    ) -> JarvisFeature {
        JarvisFeature(
            id: id, category: category, title: title, summary: summary,
            details: details, examplePrompt: prompt, verification: verification,
            status: status, symbol: symbol, runnable: runnable
        )
    }

    private static func build() -> [JarvisFeature] {
        var x: [JarvisFeature] = []

        // MARK: Voice & conversation
        x += [
            f("wake", "Voice & Conversation", "Hands-free Jarvis wake loop", "Use the Ray-Bans as the primary conversational interface.", "Apple Speech continuously supports either ‘Jarvis, <command>’ or a standalone ‘Jarvis’ followed by ‘Yes, sir?’. Bluetooth HFP is preferred when available, and the listener automatically restarts after normal turns.", "Jarvis, tell me the current mode.", "Enable Hands-free Jarvis, say the example without touching the phone, and verify the app moves through listening → thinking → speaking.", .ready, "waveform.circle.fill"),
            f("followup", "Voice & Conversation", "Five-second follow-up window", "Continue a conversation without repeating the wake word.", "After a response Jarvis keeps a short follow-up window open. Speech that begins inside the window is treated as the next turn even if the utterance itself lasts longer than five seconds.", "Tell me more.", "Ask any question with the wake word, wait for the answer, then say the example within about five seconds without saying Jarvis again.", .ready, "arrow.turn.down.right"),
            f("barge", "Voice & Conversation", "Barge-in", "Interrupt Jarvis while it is talking.", "A separate speech path listens during playback. Likely playback echo is filtered while real interruption speech can stop the current response and become the next request.", "Wait — what about tomorrow instead?", "Ask for a long answer and speak the example while Jarvis is still talking. Playback should stop and the new request should be handled.", .ready, "hand.raised.fill"),
            f("dictation", "Voice & Conversation", "Long dictation handling", "Use longer pauses for emails, URLs and dictated text.", "The iPhone applies a longer silence window when an utterance looks like dictation so an email address or long message is less likely to be sent prematurely.", "Jarvis, draft an email saying I’ll send the revised document tomorrow afternoon.", "Pause naturally in the middle. The recognizer should continue collecting rather than submitting the first fragment.", .ready, "text.bubble.fill"),
            f("vocab", "Voice & Conversation", "Personal speech vocabulary", "Teach Apple Speech your names, companies and technical jargon.", "Power Features lets you add custom terms. Those strings are passed into SFSpeechRecognitionRequest.contextualStrings the next time recognition starts, alongside Jarvis/Dubeck corrections.", "Jarvis, spell Dubeck.", "Add a difficult proper noun under Power Features → Personal Speech Vocabulary, restart listening, and inspect the live/last-heard transcript.", .frontendOnly, "character.cursor.ibeam"),
            f("quiet-speech", "Voice & Conversation", "Quiet-speech mode", "Tune the acoustic interaction for deliberately quiet speech.", "This remains ordinary microphone-based speech recognition, not EMG or thought decoding. It changes the frontend interaction assumptions for low-volume speech.", "Jarvis, connection diagnostics.", "Enable Quiet-speech mode in Settings and issue a low-volume command. Verify the recognized transcript before judging the planner response.", .frontendOnly, "waveform.badge.mic"),
            f("local-alias", "Voice & Conversation", "Instant local command aliases", "Run selected commands without an LLM round trip.", "OCR, QR scanning, vision/speech toggles, whisper controls, connection diagnostics, known-person questions, mode changes, inventory questions and several local executive queries can be intercepted on the iPhone.", "Jarvis, self diagnostics.", "Run the example and inspect Session History: the model badge should identify the response as iPhone/local rather than Qwen.", .frontendOnly, "bolt.fill")
        ]

        // MARK: Models and speech output
        x += [
            f("routing", "Models & Speech", "Automatic 8B ↔ 27B routing", "Use 8B for speed and 27B for harder requests.", "The PC planner can route routine conversation/tool requests to qwen3:8b and harder reasoning/code/planning to qwen3.8:27b. Thinking mode stays disabled for latency, and the iPhone records the selected model per turn.", "Jarvis, compare two approaches for designing a fault-tolerant event pipeline.", "Run a simple factual request and then a harder architecture request. Open Session History and compare the model badges.", .ready, "arrow.triangle.branch"),
            f("kokoro", "Models & Speech", "Kokoro-82M neural voice", "Generate the normal Jarvis voice locally on the PC.", "The iPhone requests local Kokoro audio from the authenticated backend and streams speech in chunks. Apple speech synthesis is the fallback when neural TTS is unavailable.", "Jarvis, say ‘neural voice test complete.’", "Use Settings → Check Neural Voice, then run the example and listen for the configured Kokoro voice.", .ready, "speaker.wave.3.fill"),
            f("whisper", "Models & Speech", "Adaptive and forced whisper", "Quiet Jarvis automatically or for a fixed interval.", "Measured room noise can reduce playback intensity and alter delivery. A local command can also force whisper behavior for a bounded number of minutes without changing the backend.", "Jarvis, whisper for 10 minutes.", "Run the example, ask another question, and verify the app indicates whisper playback. Then say ‘normal voice’.", .frontendOnly, "speaker.wave.1.fill"),
            f("audio-hud", "Models & Speech", "Audio HUD cues", "Hear compact state cues for thinking, scans, warnings and task completion.", "Local earcons provide feedback when staring at the phone is undesirable. Cue volume can be manually adjusted and can adapt to the measured acoustic environment.", "Jarvis, connection diagnostics.", "Enable Ambient audio HUD cues and run an operation long enough to trigger a cue. Adjust the HUD cue slider to verify local volume control.", .frontendOnly, "waveform.path.ecg"),
            f("offline-brain", "Models & Speech", "Apple on-device offline brain", "Keep basic reasoning available when the PC cannot be reached.", "On supported Apple Intelligence hardware/OS builds, Foundation Models provides a local fallback after both backend paths fail. It receives a small iPhone context packet but no web, Gmail, Calendar or PC-control authority and is explicitly told not to claim external actions.", "Explain the difference between TCP and UDP in two sentences.", "With the PC/Tailscale deliberately unreachable and the feature enabled, issue the example. Session History should show ‘Apple on-device’ if Foundation Models is available.", .frontendOnly, "iphone.gen3.radiowaves.left.and.right")
        ]

        // MARK: Local audio and translation
        x += [
            f("audio-memory", "Local Audio & Translation", "30-second rolling audio/speech memory", "Recall very recent recognized speech and optionally preserve raw audio only when explicitly requested.", "When enabled, the microphone tap keeps approximately 30 seconds of mono PCM in RAM and a bounded rolling speech transcript. The raw audio is not written to storage unless you explicitly save an encrypted incident.", "Jarvis, what did you just hear?", "Enable rolling audio memory, speak a sentence while Jarvis is listening, then run the example within roughly 30 seconds.", .frontendOnly, "waveform.badge.plus"),
            f("sound-analysis", "Local Audio & Translation", "Environmental sound classification", "Recognize supported sounds using Apple Sound Analysis.", "The existing microphone tap can feed Apple’s built-in sound classifier. High-confidence classifications are shown locally; selected alarm-like classifications may generate a conservative alert. It is advisory, not a safety-certified detector.", "Jarvis, what sound was that?", "Enable local sound classification, create a clear ordinary sound the system classifier knows, then ask the example and inspect Power Features → Local Intelligence.", .frontendOnly, "ear.badge.waveform"),
            f("translation", "Local Audio & Translation", "On-device translation", "Translate typed or recently recognized speech without the PC.", "The Power Features translator uses Apple’s Translation framework and system language models. It can take the recent speech buffer as input, optionally follow new recognized speech while the translator screen is open, and speak the translated result.", "Open Power Features → Local Translator.", "Enter a short phrase, choose a target language, tap Translate on device, then use Speak translation. The OS may first request/download a language model.", .frontendOnly, "translate", runnable: false)
        ]

        // MARK: Frontend perception
        x += [
            f("local-visual-cache", "Vision & Perception", "30-second iPhone visual cache", "Keep recent Ray-Ban frames in RAM for local tools.", "The iPhone downsamples recent DAT frames into a bounded RAM-only ring. OCR, QR scanning, inventory matching and diagnostics can use the latest cached frame without depending on the PC’s visual-history implementation.", "Jarvis, connection diagnostics.", "Enable the local visual cache and Ray-Ban camera. In On-device Intelligence verify the frame count/FPS/newest-frame age updates.", .frontendOnly, "clock.arrow.circlepath"),
            f("ocr", "Vision & Perception", "On-device OCR", "Read visible text directly on the iPhone.", "Apple Vision recognizes text from the latest Ray-Ban frame. ‘Read this’ can stay local; ‘copy this text’ writes the result to the iPhone clipboard.", "Jarvis, read this.", "Look at clear printed text through the glasses and run the example. Compare the spoken/displayed text with the source.", .frontendOnly, "text.viewfinder"),
            f("qr", "Vision & Perception", "QR and barcode decoding", "Decode supported visible codes without Moondream.", "Apple Vision scans the current Ray-Ban frame for QR/barcode payloads and can copy the decoded value to the iPhone clipboard.", "Jarvis, scan the QR code.", "Look directly at a known QR code and run the example. Verify the returned/copied payload.", .frontendOnly, "qrcode.viewfinder"),
            f("fast-perception", "Vision & Perception", "Fast structural perception", "Perform inexpensive iPhone-side visual checks.", "Optional Apple Vision requests can count detected faces/humans without identity, find rectangles, OCR text, decode codes and detect attention saliency. These are structural signals, not semantic scene understanding.", "Open Power Features and inspect Local Event Timeline.", "Enable Continuous on-device fast perception and inspect the perception summary while changing what the glasses see.", .frontendOnly, "viewfinder.circle"),
            f("visual-change", "Vision & Perception", "Visual scene-change detector", "Notice large changes between recent glasses frames.", "The iPhone compares Apple Vision image feature prints over time and records a local visual-change event when the whole-frame distance crosses your threshold. It intentionally does not claim which semantic object changed.", "Jarvis, what changed visually?", "Enable Detect major visual scene changes, look at one scene, then turn toward a substantially different scene and ask the example.", .frontendOnly, "rectangle.2.swap"),
            f("passive-vision", "Vision & Perception", "Backend passive vision transport", "Sample Ray-Ban frames for PC-side Moondream analysis.", "When Passive vision is enabled, the iPhone sends sampled frames to the authenticated PC path. Remote/Tailscale mode reduces frame rate/resolution to conserve bandwidth.", "Open Persistent Presence and inspect Passive vision status.", "Enable Passive vision and verify the Ray-Ban stream and backend receive/analyze status change. This transport can work even though the separate conversational recent-frame recall bug is pending deployment.", .ready, "eye.fill", runnable: false),
            f("live-scene-pending", "Vision & Perception", "General ‘what can you see?’ conversational scene recall", "Backend fix exists in the repository but is not deployed on the user’s current PC.", "The recent-frame Moondream path was corrected in source to avoid multi-image requests, but because the Windows backend cannot currently be updated/tested, this feature must not be counted as implemented on the running system.", "Jarvis, what can you see right now?", "Do not use this as a pass/fail test until the PC backend is updated. After deployment, verify a fresh-frame question and a recent-history question separately.", .pendingBackend, "eye.trianglebadge.exclamationmark", runnable: false),
            f("spatial-last-seen", "Vision & Perception", "Backend spatial last-seen memory", "Remember conservative object sightings from PC vision.", "The existing backend can store last-seen scene/context records for portable objects. It is evidence-based scene memory, not a precise 3D map or navigation system.", "Jarvis, where did I last see my keys?", "Ask about an object previously observed by the backend and confirm the answer refers to a recorded sighting rather than inventing a location.", .ready, "mappin.and.ellipse")
        ]

        // MARK: Known people and personal inventory
        x += [
            f("known-people", "People & Personal Context", "Closed-set Known People recognition", "Match only against faces you explicitly enrolled.", "Enrollment uses multiple photos/Ray-Ban samples, crops the detected face, stores private Vision feature prints and discards raw enrollment photos. Recognition requires threshold/margin checks and repeated evidence for continuous matching; uncertain faces remain unknown.", "Jarvis, who is this?", "Enroll a person under Manage Known People, enable recognition, look at them through the glasses and run the example. Test an unenrolled person as well; Jarvis should prefer unknown over a weak match.", .frontendOnly, "person.crop.circle.badge.checkmark"),
            f("person-brief", "People & Personal Context", "Known-person pre-conversation briefing", "Surface your private context when an enrolled person appears.", "After a confident enrolled-person match, the iPhone can assemble the person’s private note, recent locally stored Jarvis context and captured encounter summaries. Spoken briefing is a separate opt-in because saying private context aloud around that person may be inappropriate.", "Jarvis, what do I know about this person?", "Enable local known-person briefings, recognize an enrolled person with a private note, then run the example. Spoken briefings should remain off unless explicitly enabled.", .frontendOnly, "person.text.rectangle"),
            f("encounter-capture", "People & Personal Context", "Local post-encounter capture", "Keep a concise local record of what was recently discussed with an enrolled person.", "If explicitly enabled, when a known-person match ends the iPhone can save a bounded recent recognized-speech excerpt. If Apple’s on-device model is available, it can generate a short factual local summary. No voiceprint identity or emotion inference is used.", "Jarvis, what did I talk about with them?", "Enable rolling speech memory plus Local post-encounter context, interact while a known person is matched, then move away until the match ends and inspect the next briefing/context query.", .frontendOnly, "person.2.wave.2"),
            f("inventory", "People & Personal Context", "Private personal inventory matcher", "Explicitly enroll important objects for local recognition.", "Power Features lets you enroll 2–6 photos of an item. Apple Vision whole-image feature prints are encrypted locally; raw enrollment photos are not retained. Matching is conservative and works best when the object fills much of the frame.", "Jarvis, identify this item.", "Enroll a visually distinctive object, look at it through the Ray-Bans and run the example. Also test a different object to check rejection behavior.", .frontendOnly, "shippingbox.fill"),
            f("inventory-lastseen", "People & Personal Context", "Inventory last-seen time/location", "Remember when and approximately where an enrolled object was confidently matched.", "A successful local inventory match can update an item’s last-seen timestamp and, when local location context is available, approximate coordinates. This is assistive evidence, not precise indoor positioning.", "Jarvis, where did I last see my backpack?", "Enroll an item, enable auto-recognition and location context, let it match, then ask the example using that item’s actual name.", .frontendOnly, "location.fill.viewfinder"),
            f("inventory-alert", "People & Personal Context", "Knowledge-triggered item notes", "Attach a private warning or useful note to an enrolled object.", "When optional inventory note alerts are enabled, a confident local match can surface the note you explicitly associated with that item—for example ‘bad cable’ or ‘return this adapter’. Jarvis does not infer hidden properties of the object.", "Jarvis, identify this item.", "Enroll an item with a distinctive note, enable item-note alerts and expose it to the glasses. Verify the note comes from your stored annotation.", .frontendOnly, "tag.fill")
        ]

        // MARK: Local memory, privacy and reminders
        x += [
            f("event-timeline", "Local Memory & Privacy", "Cross-modal local event timeline", "Keep a private iPhone timeline of perception, people, sounds, modes and local actions.", "The power layer records bounded encrypted event metadata so local context is not split across unrelated screens. Visual summaries can include current enrolled-person and approximate location context when available.", "Open Power Features → Local Event Timeline.", "Trigger a local OCR/perception result, mode change or known-person match and verify a corresponding event appears.", .frontendOnly, "timeline.selection"),
            f("context-reminders", "Local Memory & Privacy", "Contextual reminders", "Trigger reminders on context rather than only clock time.", "Local one-shot reminders can fire when an enrolled person is recognized, when you enter a saved location radius, when a Meeting Notes session starts, or when a Jarvis conversation mode becomes active. They never execute an external action.", "Jarvis, list contextual reminders.", "Create a harmless reminder in Power Features using one trigger, satisfy the trigger, and verify the local notification/optional speech fires once.", .frontendOnly, "bell.badge.fill"),
            f("privacy-mode", "Local Memory & Privacy", "Privacy / Guest mode", "Quickly suppress the most privacy-sensitive continuous sensing.", "Privacy mode disables passive vision, local visual history, known-person recognition and rolling audio memory and suppresses proactive spoken announcements. Previous settings are restored when normal mode is resumed.", "Jarvis, privacy mode.", "Run the example, inspect relevant toggles, then say ‘Jarvis, normal mode’ and verify the prior settings return.", .frontendOnly, "eye.slash.fill"),
            f("privacy-zone", "Local Memory & Privacy", "Location-based privacy zones", "Automatically enter Privacy mode at selected places.", "Power Features can save a local geographic radius. Entering it switches to Privacy mode; leaving restores the prior conversation mode. Location processing stays on the iPhone for this trigger.", "Open Power Features → Privacy Zones.", "Add a test zone at the current location and verify Privacy mode activates once a fresh location fix places the phone inside it. Delete the test zone afterward.", .frontendOnly, "location.slash.fill", runnable: false),
            f("incident", "Local Memory & Privacy", "Explicit encrypted incident capture", "Preserve the preceding short local context only when you ask.", "‘Save that’ creates a device-local encrypted incident containing selected recent visual-cache frames, recent recognized speech/context, and—if rolling audio was enabled—the approximately 30-second PCM buffer. AES-GCM encryption keys remain in the device Keychain.", "Jarvis, save that.", "Enable the rolling visual/audio caches, produce harmless test context, run the example, then verify an Encrypted Incidents entry appears in Power Features.", .frontendOnly, "lock.doc.fill"),
            f("modes", "Local Memory & Privacy", "Conversation modes", "Switch Jarvis behavior for work, social, travel, driving, quiet or privacy situations.", "Modes provide a frontend policy layer without changing the backend. Quiet suppresses speech; Driving raises interruption severity and enables motion context; Privacy disables privacy-sensitive capture; other modes provide state for local reminders/context.", "Jarvis, driving mode.", "Run the example, ask ‘what mode are you in?’, then restore Normal mode.", .frontendOnly, "switch.2"),
            f("smart-interrupt", "Local Memory & Privacy", "Local interruption gating", "Avoid non-urgent spoken interruptions in bad contexts.", "The iPhone suppresses non-urgent local reminder speech in Privacy, Quiet and Driving modes and while Meeting Notes is active. Urgent local reminders may still notify according to local settings.", "Jarvis, driving mode.", "Enter Driving or Quiet mode and trigger a non-urgent local contextual reminder. Verify it does not speak over you; restore Normal afterward.", .frontendOnly, "bell.slash")
        ]

        // MARK: Local executive
        x += [
            f("goals", "Local Executive", "Local goal manager", "Track goals and concrete next actions without the backend.", "Local Executive stores bounded goal records on the iPhone, including a next action and optional due date. Completing or deleting a goal creates a local action receipt.", "Jarvis, list my goals.", "Open Settings → Local Executive, add a test goal, run the example, then mark it complete and verify it disappears from active goals.", .frontendOnly, "target"),
            f("waiting", "Local Executive", "Waiting-on tracker", "Track promises, replies and things another person/source owes you.", "A waiting item can include a person/source and optional follow-up date. Due items generate local notifications and are prioritized by the local intent radar.", "Jarvis, what am I waiting on?", "Add a test Waiting On item in Local Executive and run the example. Resolve it and verify it no longer appears in the active list.", .frontendOnly, "hourglass.badge.person.crop"),
            f("routine", "Local Executive", "Routine learning proposals", "Notice repeated Jarvis commands without silently automating them.", "The iPhone counts normalized recent user commands. After the same command appears at least three times it becomes a routine suggestion. Jarvis only proposes a Shortcut/automation; it never creates one from behavior without permission.", "Jarvis, what do I do repeatedly?", "Repeat the same harmless command three times, wait a few seconds, then run the example or inspect Local Executive → Routine Learning.", .frontendOnly, "repeat.circle.fill"),
            f("intent-radar", "Local Executive", "Local intent radar", "Suggest a likely next action from explicit local state.", "The rule-based radar prioritizes waiting items associated with the currently recognized enrolled person, overdue waiting items, due goals, then active goal next actions and repeated routines. It does not infer psychological intent.", "Jarvis, what should I do next?", "Add a goal with a next action or a waiting item, then run the example. If a matching known person is visible, their waiting item should take priority.", .frontendOnly, "scope"),
            f("knowledge-graph", "Local Executive", "Local personal knowledge graph", "Show relationships among your explicit people, objects, goals and reminders.", "The Local Executive can generate a textual graph snapshot from enrolled people, personal inventory, active goals, waiting-on relationships, contextual reminder triggers and local encounter counts. It is local and smaller than the future backend-wide knowledge graph.", "Jarvis, show me your local knowledge graph.", "Create at least one person, goal or waiting item and run the example. Verify the graph only contains explicit/local data.", .frontendOnly, "point.3.connected.trianglepath.dotted"),
            f("clipboard", "Local Executive", "Clipboard intelligence", "Explicitly use iPhone clipboard text as Jarvis context.", "Clipboard access is user-triggered. You can stage text into the Jarvis command field without executing it or summarize it using the Apple on-device model. Clipboard contents are treated as data, not trusted instructions.", "Jarvis, summarize my clipboard.", "Copy harmless text, run the example, and verify the local model summarizes it. Use ‘stage my clipboard’ to confirm staging does not auto-send.", .frontendOnly, "doc.on.clipboard.fill"),
            f("local-receipts", "Local Executive", "Local action receipts", "Audit changes made by frontend-only executive tools.", "Adding/completing/deleting local goals, waiting items and clipboard operations creates a timestamped receipt. This does not yet replace backend tool receipts for PC/external actions.", "Open Settings → Local Executive → Local Action Receipts.", "Add and complete a test goal. Verify both actions appear as receipts.", .frontendOnly, "checklist.checked", runnable: false)
        ]

        // MARK: Share and shortcuts
        x += [
            f("shortcuts", "iOS Integration", "App Intents / Action Button", "Expose common Jarvis actions to Shortcuts.", "The app registers intents for Talk to Jarvis, local visual scan, read visible text, vision/speech toggles, Meeting Notes and text handoff. These can be incorporated into Shortcuts and assigned to the Action Button where iOS permits.", "Run the ‘Talk to Jarvis’ Shortcut.", "Open Shortcuts, search Jarvis actions, run Talk to Jarvis and verify the app opens into the local interaction flow.", .frontendOnly, "button.programmable", runnable: false),
            f("share-text", "iOS Integration", "Share/Shortcut text handoff", "Bring selected text from another app into Jarvis without auto-executing it.", "The ‘Send Text to Jarvis’ App Intent accepts text, opens Jarvis and stages that text in the command field. You can build a Share Sheet Shortcut around the intent. It deliberately does not execute shared text automatically.", "Use the ‘Send Text to Jarvis’ Shortcut with selected text.", "Create/run a Shortcut that passes text into the intent and verify the text appears in Jarvis’s command field but is not sent until you choose to send it.", .frontendOnly, "square.and.arrow.down.fill", runnable: false)
        ]

        // MARK: Meetings, memory and personal context on backend
        x += [
            f("meeting", "Meetings & Memory", "Explicit Meeting Notes", "Transcribe an explicitly started meeting and extract action items.", "Meeting capture visibly owns the microphone, keeps a local transcript, supports pause/resume/bookmarks and sends transcript chunks to the existing backend when available. Stop triggers action-item extraction; speaker voiceprints are not used.", "Start Meeting Notes, say ‘Alex will send the draft Tuesday’, then stop.", "Use the Meeting Notes controls and verify the live/local transcript contains the sentence and the backend extraction identifies only commitments supported by the transcript.", .ready, "record.circle.fill", runnable: false),
            f("meeting-offline", "Meetings & Memory", "Offline meeting capture", "Keep recording locally if the PC becomes unreachable.", "The iPhone can continue accumulating an explicit Meeting Notes transcript when the PC is down. Later, Sync & Extract sends the saved text through the already-existing meeting endpoints.", "Open Meeting Notes while the PC is unreachable.", "Start with offline meeting capture enabled, speak a short test, stop, restore connectivity and use Sync & Extract.", .frontendOnly, "arrow.triangle.2.circlepath.doc.on.clipboard", runnable: false),
            f("episodic", "Meetings & Memory", "Backend episodic semantic memory", "Retrieve relevant older Jarvis interactions by meaning.", "Important PC-side conversation memories are embedded locally with nomic-embed-text. Retrieval is invoked when older context is relevant instead of forcing every past turn into every prompt.", "Jarvis, what did we previously discuss about the authentication server?", "Use a topic that genuinely appeared in prior Jarvis interactions and verify the answer reflects stored context rather than a fabricated memory.", .ready, "brain.head.profile"),
            f("context-discipline", "Meetings & Memory", "Conversation context discipline", "Prevent stale unrelated topics from hijacking a garbled new command.", "Normal turns expose only the immediately preceding exchange. Older context is expanded when the user explicitly refers back, such as ‘earlier’ or ‘remember’. Ambiguous ASR should produce clarification instead of resurrecting an unrelated topic.", "Jarvis, what did you say earlier about that?", "First establish a topic, switch to an unrelated topic, then explicitly refer back. Compare with a vague malformed request, which should ask for clarification.", .ready, "text.line.first.and.arrowtriangle.forward"),
            f("unified-search", "Meetings & Memory", "Unified semantic search", "Search indexed Gmail, Calendar, notes and prior conversations by meaning.", "The PC maintains a vector index over supported private sources and can retrieve semantically related records without requiring the user to name the source first.", "Jarvis, find the contract item we discussed last month.", "Use a known phrase/topic stored in one indexed source and verify Jarvis cites/uses the correct record rather than unrelated text.", .ready, "magnifyingglass.circle.fill")
        ]

        // MARK: Web, communications and PC tools
        x += [
            f("web", "Web & Connected Tools", "Serper web search", "Search current public web information and synthesize it for speech.", "The Serper key stays on the PC. Search queries can be refined from conversational wording, then 8B synthesizes results so Jarvis does not read raw SERP titles and URLs aloud.", "Jarvis, search the web for today’s major AI news.", "Run a current-information request and verify the answer contains fresh material rather than model-only knowledge or a raw link dump.", .ready, "globe"),
            f("gmail-read", "Web & Connected Tools", "Gmail search/read", "Search and read your connected Gmail account.", "The backend can query messages/threads and clean tracking/newsletter clutter before speech. Read access is separate from external-write permission.", "Jarvis, summarize my latest unread email.", "Use an inbox with a known unread message and compare the sender/subject/content with Gmail.", .ready, "envelope.open.fill"),
            f("gmail-send", "Web & Connected Tools", "Protected Gmail sending", "Send only after both permission and exact-recipient checks.", "Outbound Gmail is an external write and normally requires confirmation. The final resolved email address must also be present in the PC-side exact allowlist; an empty allowlist blocks all sends.", "Jarvis, email [allowed test address] saying ‘Jarvis test’. ", "Use only a harmless allowed address. Verify Jarvis asks for confirmation and does not send to an address outside the allowlist.", .ready, "paperplane.fill", runnable: false),
            f("contacts", "Web & Connected Tools", "Google Contacts resolution", "Resolve saved people for communication/calendar workflows.", "Connected Google Contacts can translate a saved person name into contact details before protected actions. Recipient safety checks still occur after resolution.", "Jarvis, find the email address for [saved contact].", "Use a contact you know exists and compare the returned address with Contacts.", .ready, "person.crop.circle"),
            f("calendar", "Web & Connected Tools", "Google Calendar read/create", "Inspect, search and create calendar events.", "Calendar reads can list/search past or future events. Creating or modifying an event is an external write and goes through confirmation policy.", "Jarvis, what is my next calendar event?", "Compare the answer with the connected calendar. Test creation only with a disposable event and confirm the write explicitly.", .ready, "calendar"),
            f("calendar-conflict", "Web & Connected Tools", "Calendar conflict analysis", "Detect overlaps and suggest open alternatives.", "The backend can identify overlapping timed events and calculate plausible open slots. It returns proposals rather than silently moving/declining meetings.", "Jarvis, check my calendar for conflicts.", "Use a day with a known overlap and verify the reported conflict and suggested alternatives; no event should be changed automatically.", .ready, "calendar.badge.exclamationmark"),
            f("pc-app", "Web & Connected Tools", "Windows application control", "Check, open and close explicitly supported PC applications.", "Jarvis exposes explicit app/process/path tools instead of giving the planner unrestricted PowerShell. It can also use browser-aware handling for services such as Spotify.", "Jarvis, is Spotify open on my PC?", "Compare the answer with Windows. If you ask it to open an app, verify the actual process/tab appears.", .ready, "desktopcomputer"),
            f("browser", "Web & Connected Tools", "Opera/Chromium CDP control", "List, focus, close and open browser tabs through DevTools.", "The backend connects to the configured Chromium DevTools port and performs explicit tab operations. It does not expose the CDP port publicly.", "Jarvis, list my browser tabs.", "Compare the returned tab titles with Opera and then test focusing one known tab.", .ready, "safari.fill"),
            f("desktop-context", "Web & Connected Tools", "Active PC context handoff", "Know the foreground process/window and available browser context.", "A lightweight PC monitor supplies active process/window title plus browser-tab context. Jarvis must not treat a window title as the full document contents.", "Jarvis, what was I doing on my PC?", "Switch to a distinctive app/window and run the example. Verify it names only context actually exposed by the desktop bridge.", .ready, "macwindow.on.rectangle")
        ]

        // MARK: Automation
        x += [
            f("jobs", "Automation", "Scheduled and recurring jobs", "Create persistent one-time/recurring/event-triggered Jarvis tasks.", "The PC scheduler persists jobs across normal service restarts and supports recurring patterns and selected events such as home arrival.", "Jarvis, list my scheduled jobs.", "Create a harmless future job, list it, restart the backend when convenient, and verify the job persists.", .ready, "clock.badge.checkmark"),
            f("briefing", "Automation", "Automated briefings", "Generate scheduled summaries from calendar, email and other available context.", "Existing briefing workflows can combine upcoming calendar context, unread mail and other configured sources and deliver results through the companion connection.", "Jarvis, give me my briefing.", "Run an on-demand briefing and compare its calendar/email components with the connected accounts.", .ready, "newspaper.fill"),
            f("background", "Automation", "Background worker queue", "Run long tasks without blocking foreground voice interaction.", "Persistent workers can submit, list, cancel and report background work. GPU-heavy background inference still competes with foreground models for the same RTX 5080.", "Jarvis, list background tasks.", "Submit a harmless long task, continue a normal voice turn, then inspect task status/completion.", .ready, "square.stack.3d.up.fill"),
            f("dag", "Automation", "Autonomous DAG workflows", "Compile a goal into a validated multi-tool dependency graph.", "The 27B planner can build a bounded DAG; independent read-only nodes may run in parallel and later nodes consume prior results. Every node still passes through normal permission policy.", "Jarvis, prepare me for tomorrow using my calendar, unread email and weather.", "Run a read-only multi-source request and inspect the result/tool activity. Protected writes must still request confirmation.", .ready, "point.3.filled.connected.trianglepath.dotted"),
            f("proactive", "Automation", "Proactive calendar/email monitor", "Interrupt only when monitored private sources cross your severity threshold.", "Background checks can generate info/warning/urgent companion events. The iPhone exposes an interruption threshold and can mute proactive speech independently.", "Open Settings and review the proactive interrupt threshold.", "Set a threshold and compare it with the severity of any test proactive event; lower-priority events should not be spoken above the chosen threshold.", .ready, "bell.and.waves.left.and.right.fill", runnable: false),
            f("prewarm", "Automation", "Predictive model/context prewarm", "Reduce latency shortly before calendar events.", "The backend can prewarm 8B and retrieve related local context before scheduled meetings rather than waiting for the first request after the meeting begins.", "Jarvis, what meetings are coming up?", "When back at the PC, inspect prewarm/log behavior shortly before a known calendar event and compare first-turn latency.", .ready, "flame.fill")
        ]

        // MARK: Local records and monitoring
        x += [
            f("expenses", "Records & Monitoring", "Receipt/invoice extraction", "Extract visible receipt fields into local expense records.", "Recent glasses imagery can be parsed for merchant/date/tax/tip/total/line items and stored in local SQLite/CSV. Unreadable values are supposed to remain unknown rather than guessed.", "Jarvis, log this receipt.", "Use a clear non-sensitive test receipt and compare the saved fields with the printed values.", .ready, "receipt.fill"),
            f("journal", "Records & Monitoring", "Daily local journal", "Create a concise Markdown record of the day’s Jarvis context.", "The backend can generate an on-demand or scheduled local journal from interactions, completed work, communications and spatial records while avoiding invented emotions/motives.", "Jarvis, write today’s journal.", "Run the example and inspect the resulting local Markdown file when you are back at the PC.", .ready, "book.pages.fill"),
            f("resources", "Records & Monitoring", "PC resource monitor", "Track CPU, RAM, NVIDIA GPU, VRAM, temperature and queue pressure.", "The backend can answer resource-status questions and generate warnings when configured thresholds are crossed, useful while 8B/27B/Moondream/TTS share one machine.", "Jarvis, how is the PC doing?", "Compare CPU/RAM/GPU/VRAM values with Windows/NVIDIA monitoring tools.", .ready, "gauge.with.dots.needle.67percent"),
            f("audio-damping", "Records & Monitoring", "Smart Windows audio damping", "Temporarily reduce PC output volume while Jarvis is actively conversing.", "When enabled, the PC endpoint volume is lowered during Jarvis interaction and restored to its previous level afterward. It controls the Windows endpoint, not arbitrary network speakers.", "Open Settings and enable Smart PC audio damping.", "Play PC audio, start a Jarvis conversation, then verify the volume lowers and restores afterward.", .optional, "speaker.wave.2.bubble.left.fill", runnable: false),
            f("health", "Records & Monitoring", "Optional Apple Health context", "Read recent heart rate, HRV and sleep as explicit context.", "HealthKit reads are opt-in and sent only to the private Jarvis PC. Jarvis is instructed not to convert those measurements into diagnoses or psychological stress judgments.", "Open Settings and enable Apple Watch / Health context.", "Grant only the intended read permissions and inspect the Health status; verify no diagnostic inference is presented as fact.", .optional, "heart.text.square.fill", runnable: false)
        ]

        // MARK: Connectivity and diagnostics
        x += [
            f("tailscale", "Connectivity & Diagnostics", "Automatic LAN → Tailscale failover", "Use Jarvis away from home without public port exposure.", "The iPhone probes the LAN URL first and falls back to the configured private Tailscale Serve URL. Ollama/Kokoro remain behind the PC service and Funnel/public port forwarding is not used.", "Jarvis, connection diagnostics.", "Test once on home LAN and once away. Route diagnostics should identify LAN vs Tailscale reachability/latency.", .ready, "network"),
            f("diagnostics", "Connectivity & Diagnostics", "Frontend diagnostics and latency telemetry", "See where time/failures are occurring.", "The iPhone tracks server route latency, ASR confidence/state, Ray-Ban registration/stream state, local visual cache metrics, offline queue depth and per-turn model/first-text/first-audio/total timing.", "Jarvis, connection diagnostics.", "Run the example and open Session History/On-device Intelligence. Compare the displayed route and timing with the actual connection.", .frontendOnly, "stethoscope"),
            f("auto-recovery", "Connectivity & Diagnostics", "Frontend automatic recovery", "Recover common dead camera/listener states without restarting the app.", "When enabled, the frontend periodically notices when a required Ray-Ban camera stream is stopped or hands-free speech recognition died outside Meeting Notes and attempts a safe restart. The camera master latch always wins: auto-recovery cannot restart a camera the user explicitly stopped. It does not restart the Windows backend.", "Jarvis, self diagnostics.", "With a recoverable frontend component stopped/interrupted, wait for the recovery loop and inspect Power Features → Auto recovery / Local Event Timeline. Then press Stop Camera and verify recovery does not restart it.", .frontendOnly, "arrow.clockwise.heart.fill"),
            f("offline-queue", "Connectivity & Diagnostics", "Offline command staging", "Avoid losing a command when both server routes fail.", "If the PC is unreachable and the Apple offline brain cannot appropriately answer, the iPhone may queue the command. It never executes queued commands automatically when connectivity returns.", "Jarvis, send queued command.", "With both server paths unavailable, issue a harmless tool request and verify it is queued. Restore connectivity and explicitly send it.", .frontendOnly, "tray.full.fill")
        ]

        // MARK: Security
        x += [
            f("permissions", "Security", "Permission policy engine", "Separate reads, local writes, external writes, destructive actions and security actions.", "Default policy auto-allows read/local-write classes while external-write, destructive and security-sensitive actions require confirmation. Agentic workflows do not bypass the policy layer.", "Jarvis, what are my current permission policies?", "Run the example and verify a protected test action still requires confirmation even when requested inside a broader workflow.", .ready, "lock.shield.fill"),
            f("email-allow", "Security", "Exact email recipient allowlist", "Block outbound email to unapproved resolved addresses.", "The PC checks the final exact address after contact resolution in addition to external-write confirmation. Empty allowlist means no outbound email recipients are permitted.", "Open Settings → Email Safety.", "Inspect the list. Do not add an address unless you intentionally want Jarvis to be able to send there after confirmation.", .ready, "person.badge.shield.checkmark", runnable: false),
            f("sandbox", "Security", "Docker code/terminal sandbox", "Run generated code in a constrained disposable container instead of the Windows host.", "When configured, generated Python/terminal work runs with no network, read-only filesystem, dropped capabilities, no-new-privileges, memory/CPU/PID limits and a hard timeout.", "Jarvis, run sandboxed Python that prints 2 + 2.", "Verify the result is 4 and that Jarvis uses the Docker sandbox rather than claiming unrestricted host PowerShell access.", .optional, "shippingbox.and.arrow.backward.fill"),
            f("exact-command", "Security", "Exact terminal-command voice confirmation", "Require the full command plus a specific authorization phrase.", "Security-class sandbox terminal execution reads the exact proposed command and requires ‘execute exact command’; a generic yes/confirm should not authorize it.", "Jarvis, run a sandboxed terminal command that prints hello.", "Jarvis should read the exact command and wait. Say ‘never mind’ to verify cancellation, then repeat and use the exact execution phrase if desired.", .optional, "terminal.fill"),
            f("dynamic-tools", "Security", "Self-generated API adapters", "Let 27B propose narrow external API tools without silently granting execution authority.", "Generated adapters are sandbox-tested, restricted to declared HTTPS hosts, cannot embed authorization/cookie/API-key headers and are stored disabled until explicitly enabled through a security action.", "Jarvis, list my custom API tools.", "Inspect enabled/disabled state. Creating a new adapter must not silently enable it or broaden its host allowlist.", .optional, "hammer.fill"),
            f("tool-repair", "Security", "Custom-tool repair proposals", "Draft/test a repair but require approval before applying it.", "A structurally broken generated adapter may be repaired by 27B, sandbox validated and rechecked for host/risk restrictions. The result is queued as a proposal rather than self-modifying automatically.", "Jarvis, list custom tool repairs.", "If proposals exist, verify they can be inspected without being automatically applied.", .optional, "cross.case.fill")
        ]

        // MARK: September 5/6 frontend reliability
        x += [
            f("camera-master", "Recent Frontend Reliability", "Persistent Stop Camera master switch", "Make Stop Camera an absolute user privacy latch.", "Stop Camera tears down the active DAT camera/session/listeners, clears current frame/photo state and persists a master-disabled latch across app relaunches. Passive vision, Known People, inventory, OCR/scan helpers and auto-recovery can request the camera, but their internal start path cannot clear the latch. Only the explicit Start Camera button can re-enable camera use.", "Press Stop Camera, then wait while passive/recovery features remain enabled.", "Start the camera, press Stop Camera, leave passive vision/Known People/auto-recovery enabled for several minutes and verify the stream stays stopped. Relaunch the app and verify it is still stopped until Start Camera is explicitly pressed.", .frontendOnly, "camera.fill.badge.ellipsis", runnable: false),
            f("empty-stream-recovery", "Recent Frontend Reliability", "Empty-stream response recovery", "Prevent a successful-looking stream with no answer text from silently ending a turn.", "If the streaming endpoint completes without usable answer text, the iPhone no longer treats that as a normal completed response. Clearly read-only requests can fall back to the ordinary command endpoint. Potential writes/actions are not replayed automatically because the original request may already have caused a side effect.", "Jarvis, explain what a black hole is in one sentence.", "Issue a read-only question and verify a malformed/empty stream cannot silently return to wake mode. Consequential actions must never be duplicated as part of recovery.", .frontendOnly, "arrow.triangle.2.circlepath.circle.fill"),
            f("sir-dedupe", "Recent Frontend Reliability", "Duplicate ‘sir’ suppression", "Prevent responses from beginning ‘Sir, sir…’.", "The frontend normalizes repeated adjacent honorifics, including the streaming edge case where one chunk ends with ‘Sir,’ and the next model chunk begins with another ‘sir’. It preserves a single natural honorific.", "Jarvis, tell me the time.", "Run several short conversational turns and inspect both displayed and spoken responses; adjacent duplicate ‘sir’ should collapse to one.", .frontendOnly, "textformat.abc.dottedunderline"),
            f("response-done-tone", "Recent Frontend Reliability", "Response-finished tone", "Make it audibly clear when an answer is truly complete.", "A distinct completion earcon plays after response generation has ended and speech playback has finished, differentiating ‘the answer is over’ from a pause while another sentence is still generating.", "Ask Jarvis for a multi-sentence explanation.", "Listen through the entire answer. The completion tone should occur only after the last spoken output, not between streamed sentences.", .frontendOnly, "checkmark.circle.badge.waveform"),
            f("welcome-back", "Recent Frontend Reliability", "Glasses-return greeting", "Say ‘Welcome back, sir.’ when the Ray-Bans return after being unavailable.", "Because Meta DAT does not expose a dependable general worn-state signal, Jarvis uses device availability as the conservative trigger: after the glasses have been unavailable for several seconds and become available again, it waits briefly for Bluetooth HFP to settle, greets you, then restores hands-free listening. It never starts the camera to infer whether the glasses are being worn.", "Reconnect/open the Ray-Bans after they have been unavailable.", "Make the glasses unavailable for at least several seconds, reconnect them, and verify the greeting occurs once after the audio route settles. Simply pressing Stop Camera must not trigger or defeat this behavior.", .frontendOnly, "eyeglasses")
        ]

        // MARK: Local Intelligence & Reliability
        x += [
            f("local-first-router", "Local Intelligence", "Local-first intent router", "Give deterministic/native iPhone capabilities first refusal before the PC planner.", "The frontend first checks explicit local capabilities, then the inherited local stack, then—only for carefully classified stable questions—the Apple on-device model. Requests needing freshness, Gmail, PC state, browser/files or external actions are blocked from the stable local-answer path and continue to the backend.", "Jarvis, what time is it in DC?", "Run the example and inspect the Local tab. It should be handled on the iPhone and must not turn into a Clock.app status request.", .frontendOnly, "arrow.triangle.branch"),
            f("deterministic-utilities", "Local Intelligence", "Deterministic local utilities", "Answer common time/date/math/conversion requests without an LLM or PC.", "A local parser handles current time with common timezone aliases, date/day, basic arithmetic, percentages, linear unit conversion and temperature conversion. This provides fast, reproducible answers and removes pressure to invoke unrelated tools.", "Jarvis, what is 17 times 24?", "Run arithmetic, ‘What time is it in DC?’, and ‘Convert 5 miles to kilometers’. Session History should identify iPhone/local handling rather than Qwen.", .frontendOnly, "function"),
            f("stable-local-brain", "Local Intelligence", "Stable-question Apple-model bypass", "Use the on-device model before the backend for bounded stable explanatory questions.", "When enabled and supported by the device, simple non-current, non-private, non-action questions can be answered by Apple Foundation Models with a compact local context packet. Current/live queries and consequential actions are explicitly excluded.", "Jarvis, explain what a black hole is in one sentence.", "Enable the setting in Local Intelligence, run a stable explanation request and inspect routing. Then ask for latest news and verify it does not stay on this path.", .frontendOnly, "apple.intelligence"),
            f("native-calendar-local", "Local Intelligence", "Native iPhone Calendar reads", "Read the calendars already available to iOS without involving the PC.", "With EventKit permission, Jarvis can answer the next event, today’s schedule and tomorrow’s schedule directly from iPhone calendars. Permission is requested explicitly rather than at app launch.", "Jarvis, what meetings do I have tomorrow?", "Grant Calendar access in the Local tab, compare the answer with Calendar, and verify the turn routes locally.", .frontendOnly, "calendar.badge.clock"),
            f("native-reminders-local", "Local Intelligence", "Native Apple Reminders creation", "Create real local reminders through EventKit.", "Explicit ‘remind me…’ requests can create Apple Reminders on the iPhone, including supported relative times. This is a local write and does not require the Windows backend.", "Jarvis, remind me in 20 minutes to check the oven.", "Grant Reminders access and create a harmless test reminder. Verify it appears in Apple Reminders with the expected due time.", .frontendOnly, "checklist"),
            f("local-timers", "Local Intelligence", "Jarvis local timers", "Run timers independently of Clock.app and the PC.", "Timers are scheduled as local iPhone notifications and tracked by Jarvis. The frontend supports timer creation, remaining-time/status and cancellation without querying or launching Apple Clock.", "Jarvis, set a timer for 2 minutes.", "Create a short timer, ask how much time is left, then cancel another test timer. Clock.app should not be involved.", .frontendOnly, "timer"),
            f("native-contacts-local", "Local Intelligence", "Native iPhone Contacts lookup", "Read saved contact details locally with permission.", "The frontend can search Contacts for names and return bounded phone/email details. Explicit Known People profiles can be linked to a unique matching iOS Contact identifier; ambiguous matches are deliberately left unlinked.", "Jarvis, look up [saved contact] in my contacts.", "Grant Contacts access, use a known saved contact, and compare the returned information. Try an ambiguous name and verify Jarvis asks for specificity instead of guessing.", .frontendOnly, "person.crop.circle.badge.checkmark", runnable: false),
            f("context-capsules", "Local Intelligence", "Encrypted Context Capsules", "Explicitly snapshot useful local context for later recall.", "‘Remember this context’ stores a bounded capsule containing mode, current advisory Known People match, recent OCR, last heard command, last Jarvis response, bounded clipboard excerpt and approximate coordinates when available. It does not silently persist raw camera frames or rolling microphone audio. Capsules are AES-GCM encrypted with a Keychain-held key and complete file protection.", "Jarvis, remember this context.", "Run the example, open Local → Context capsules, verify a new entry appears, then inspect local memory search. Stop Camera/rolling-audio settings should remain unchanged.", .frontendOnly, "archivebox.fill"),
            f("unified-local-memory", "Local Intelligence", "Unified iPhone memory search", "Search local Jarvis records across feature silos.", "The Local Memory center can search context capsules, local conversation turns, Known People notes, encounter records, inventory, local events, goals, waiting items and action receipts. When available, Apple Foundation Models can synthesize an answer from retrieved records only and is instructed not to invent absent facts.", "Jarvis, search local memory for Japan flight.", "Store a known local record, run a matching search and verify the returned evidence comes from local Jarvis data rather than a fabricated memory.", .frontendOnly, "magnifyingglass.circle"),
            f("compact-context-packet", "Local Intelligence", "Compact local context packets", "Give local reasoning only the context relevant to the current turn.", "Stable local-model requests receive a bounded packet such as conversation mode, current advisory enrolled-person match, recent OCR and immediate conversation context rather than an indiscriminate dump of the user’s local history.", "Open Local and run a stable local-model test.", "Use a stable request while OCR/person context is present and verify behavior remains relevant without resurrecting unrelated old topics.", .frontendOnly, "shippingbox.circle", runnable: false),
            f("local-route-telemetry", "Local Intelligence", "Local routing telemetry and verification suite", "See what the iPhone intercepted and test the intended routes.", "The Local tab reports the latest local route and count of locally handled requests and includes reproducible tests for time, arithmetic, conversion, Calendar, timers and Context Capsules.", "Open the Local tab and run the verification prompts.", "The displayed route should match the expected local capability, especially the canonical ‘What time is it in DC?’ test.", .frontendOnly, "chart.bar.doc.horizontal", runnable: false)
        ]

        // MARK: ETDK-inspired capability architecture
        x += [
            f("capability-packs", "Capability Architecture", "Explicit capability-pack registry", "Model frontend functions as named, inspectable packs instead of an opaque handler chain.", "Major capability families register stable IDs, human-readable names, categories, priority, effect class, requirements, activation policy, claim predicate, availability predicate and execution handler. The legacy frontend stack remains available through a lowest-priority compatibility adapter while features are progressively promoted into explicit packs.", "Open the Packs tab.", "Inspect the registered packs and verify each shows its effect/priority/requirements rather than appearing as an anonymous handler.", .frontendOnly, "square.stack.3d.up.fill", runnable: false),
            f("capability-router", "Capability Architecture", "Central capability-pack router", "Select the smallest appropriate frontend capability before falling through to the backend.", "The router evaluates only packs whose intent predicates match, honors availability gates, records which candidates were considered, and preserves backend fallback when no frontend pack can produce a valid result.", "Jarvis, what time is it in DC?", "Run several canonical requests and inspect Packs → Last decision. Utility, Calendar, Contacts and backend-only requests should route differently.", .frontendOnly, "point.3.connected.trianglepath.dotted"),
            f("camera-privacy-pack", "Capability Architecture", "Highest-priority camera privacy gate", "Block visual intents at the router when Stop Camera is latched.", "In addition to the camera manager’s hard master latch, the capability router has a highest-priority privacy pack. A visual request while the camera master is off is answered locally as unavailable rather than allowing lower visual packs to attempt a restart.", "Stop Camera, then ask ‘Jarvis, who is this?’", "With the camera master off, issue a camera-dependent request and verify the Packs decision is the privacy gate and the stream remains stopped.", .frontendOnly, "camera.badge.ellipsis"),
            f("readonly-composer", "Capability Architecture", "Read-only pack composition", "Combine multiple safe local specialists within one compound request.", "A small composer can split a compound request when every clause is independently recognized as a safe local read. It runs the clauses through the preserved local stack and combines their answers. Any command containing write/action language is excluded rather than being decomposed unsafely.", "Jarvis, what time is it in DC and what meetings do I have tomorrow?", "Use a compound read-only request and inspect the resulting Packs receipt. Then try a compound request containing a write and verify it is not automatically composed/replayed.", .frontendOnly, "rectangle.3.group.bubble.left.fill"),
            f("quality-shield", "Capability Architecture", "Deterministic response Quality Shield", "Reject structurally wrong local answers before treating them as authoritative.", "Every pack result receives inexpensive checks for empty output and known contradictions. The exact observed failure ‘What time is it in DC?’ → ‘Clock appears to be running’ is explicitly rejected. Utility requests receiving app-status answers are also rejected, and read-only packs are warned if they claim external actions.", "Open Packs and run the regression suite.", "The synthetic bad Clock response should show Reject while a direct time answer shows Pass.", .frontendOnly, "checkmark.shield.fill", runnable: false),
            f("no-write-replay", "Capability Architecture", "No automatic replay of consequential writes", "Keep recovery/verifier behavior from duplicating actions.", "If a write or mixed capability produces an uncertain result, Jarvis does not automatically execute the request again merely to get a cleaner answer. This preserves the existing rule that recovery from communication/planner problems must not create duplicate emails, reminders or other side effects.", "Review Packs execution receipts after a local write.", "Verify no verifier or fallback path causes the same write command to execute twice automatically.", .frontendOnly, "arrow.uturn.backward.circle.badge.xmark", runnable: false),
            f("semantic-audit", "Capability Architecture", "Optional Apple-model semantic audit", "Run an advisory relevance check on selected read-only answers.", "When explicitly enabled, the existing on-device Apple model can audit a completed read-only request/response pair in the background. The audit does not delay speech, does not answer the user itself, does not authorize actions and stores only a bounded PASS/WARN result with the local receipt.", "Enable Semantic audit in the Packs tab, then ask a read-only question.", "After the answer, inspect the execution receipt for an audit result. Disable the toggle to confirm the auditor is optional.", .frontendOnly, "checkmark.bubble.fill", runnable: false),
            f("capability-receipts", "Capability Architecture", "Encrypted capability execution receipts", "Keep an auditable record of frontend routing decisions.", "For routed turns the iPhone stores bounded command/response excerpts, selected pack, considered pack IDs, effect class, declared requirements, routing duration, outcome, deterministic quality verdict and optional semantic-audit result. The newest 200 receipts are AES-GCM encrypted with a Keychain-held key and complete file protection.", "Open Packs → Execution receipts.", "Run a harmless local command and verify a new receipt records the selected pack and quality outcome without exposing unrestricted raw histories.", .frontendOnly, "doc.text.magnifyingglass", runnable: false),
            f("routing-regressions", "Capability Architecture", "Canonical dry-run regression harness", "Continuously test that representative prompts choose the intended capability.", "The Packs tab includes a no-side-effect route preview suite for local utility, Calendar, Reminders, timers, memory, Contacts, vision/person, Local Executive, stable Apple-model answers and backend-only requests. It also includes synthetic Quality Shield cases. Dry-run tests do not execute writes.", "Open Packs and run the regression suite.", "All canonical route tests should pass; importantly ‘Open Clock’ and ‘Is Clock running on my PC?’ should remain backend while ‘What time is it in DC?’ should be local.utility.", .frontendOnly, "checklist.checked", runnable: false),
            f("lazy-pack-activation", "Capability Architecture", "Lazy capability activation", "Avoid waking unrelated capability systems for every request.", "Capability handlers are considered only when their intent predicate matches, and availability gates skip disabled/unavailable capabilities. This is the frontend equivalent of an elastic core: keep the routing core small and activate specialists only when useful.", "Open Packs and inspect a routing receipt.", "A simple time question should not list vision/Contacts/Calendar as executed capabilities; only relevant matching candidates should be considered.", .frontendOnly, "bolt.horizontal.circle.fill", runnable: false),
            f("packs-tab", "Capability Architecture", "Packs diagnostics tab", "Inspect the capability registry, quality system and routing tests from the iPhone.", "The third main app tab shows registered packs, last routing decision, camera-gate state, semantic-audit control, canonical regression results and encrypted execution receipts.", "Open the Packs tab.", "Verify the registry and regression controls are visible and that a new local request updates Last decision/receipts.", .frontendOnly, "square.stack.3d.up.fill", runnable: false)
        ]

        // MARK: Backend source changes waiting for deployment
        x += [
            f("backend-tool-necessity-pending", "Backend Update Pending", "Backend direct-answer / tool-necessity gate", "Reduce unnecessary tool use after the Windows server can be updated.", "Backend source now tells the planner that tools are the exception: answer ordinary knowledge, reasoning, arithmetic and supplied date/time directly; use tools only when they add information or perform an action. A post-plan necessity gate can reject obviously mismatched tool calls such as inspecting Clock.app for ‘What time is it in DC?’. The user currently cannot update the Windows server, so this source change must remain marked pending deployment.", "Jarvis, what time is it in DC?", "Do not judge this backend gate until the Windows PC is updated/restarted. In the meantime the iPhone deterministic local utility should already answer this particular example without the backend.", .pendingBackend, "wrench.and.screwdriver.fill", runnable: false)
        ]

        // MARK: Explicit limits
        x += [
            f("no-notifications", "Known Limits", "No universal iPhone notification interception", "Normal iOS apps cannot read every other app’s notifications.", "Jarvis can receive its own companion/local notifications but does not claim a private API to inspect arbitrary third-party notification contents system-wide.", "Not available as a general iOS capability.", "This is a documented platform boundary, not a testable feature.", .limited, "bell.slash.fill", runnable: false),
            f("no-speaker-id", "Known Limits", "No biometric speaker identification", "Jarvis does not maintain voiceprints of people around you.", "Meeting capture may transcribe speech but does not identify speakers from biometric voice signatures. Known People recognition is face-based and closed-set/explicitly enrolled.", "Not implemented by design.", "This is a privacy boundary rather than a feature to test.", .limited, "person.wave.2.fill", runnable: false),
            f("no-stress", "Known Limits", "No voice-based stress/emotion inference", "Jarvis does not label nearby people as stressed, deceptive, angry or afraid from vocal acoustics.", "The system deliberately avoids sensitive psychological inference from pitch, jitter, tone or other neighboring-person voice characteristics.", "Not implemented by design.", "This is a privacy/safety boundary rather than a feature to test.", .limited, "waveform.slash", runnable: false),
            f("no-diarization", "Known Limits", "No reliable automatic speaker diarization yet", "The current iPhone speech stack does not reliably separate Speaker A/B/C.", "Meeting Notes captures a combined transcript. Manual bookmarks and explicit names in speech can be used, but true local diarization needs an additional suitable model/framework and has not been represented as complete.", "Not implemented yet.", "Do not expect Meeting Notes to assign unlabeled utterances to distinct speakers automatically.", .limited, "person.3.sequence.fill", runnable: false),
            f("no-3d", "Known Limits", "No full 3D world model / indoor homing", "Last-seen context is not a safety-grade spatial map.", "The ordinary Ray-Ban camera path does not provide a complete persistent 6DoF map suitable for dependable indoor navigation. Jarvis therefore does not present monocular guesses as precise homing directions.", "Not available in the current stack.", "Use last-seen memory only as contextual recall, not navigation assurance.", .limited, "cube.transparent", runnable: false),
            f("no-ide", "Known Limits", "No full live IDE-buffer awareness", "Foreground window context is not the same as reading the editor buffer.", "A proper VS Code/editor bridge is still required for continuous reliable source-buffer contents, diagnostics and edits. Jarvis must not fabricate file contents from a window title.", "Jarvis, what was I doing on my PC?", "Jarvis may name the active editor/window but should not quote source it has not actually read.", .limited, "chevron.left.forwardslash.chevron.right"),
            f("share-limit", "Known Limits", "No native Share Extension target yet", "Text handoff uses App Intents/Shortcuts rather than a dedicated Share Extension.", "You can create a Share Sheet Shortcut around ‘Send Text to Jarvis’, which stages input safely. A true app extension would add another signed target and was deliberately avoided during the frontend-only/no-backend deployment window.", "Use Send Text to Jarvis in Shortcuts.", "Verify text is staged but not auto-executed.", .limited, "square.and.arrow.up.on.square", runnable: false),
            f("watch-limit", "Known Limits", "No Apple Watch haptic companion target yet", "HealthKit reads do not create a Watch app.", "A proper Watch haptic channel requires a Watch app/extension target, provisioning and lifecycle testing. It was not added to this single iPhone target during the frontend-only batch.", "Not implemented yet.", "This is an additional-target dependency, not a backend dependency.", .limited, "applewatch", runnable: false)
        ]

        return x
    }
}

struct FeatureGuideView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @State private var searchText = ""
    @State private var selectedCategory = "All"

    private var categories: [String] {
        ["All"] + Array(Set(JarvisFeatureCatalog.all.map(\.category))).sorted()
    }

    private var filtered: [JarvisFeature] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return JarvisFeatureCatalog.all.filter { feature in
            (selectedCategory == "All" || feature.category == selectedCategory)
                && (query.isEmpty || feature.searchableText.contains(query))
        }
    }

    private var grouped: [(String, [JarvisFeature])] {
        let groups = Dictionary(grouping: filtered, by: \.category)
        return groups.keys.sorted().map { ($0, groups[$0] ?? []) }
    }

    var body: some View {
        List {
            Section {
                Picker("Category", selection: $selectedCategory) {
                    ForEach(categories, id: \.self) { Text($0).tag($0) }
                }
            }

            if filtered.isEmpty {
                ContentUnavailableView.search(text: searchText)
            } else {
                ForEach(grouped, id: \.0) { category, features in
                    Section(category) {
                        ForEach(features) { feature in
                            NavigationLink {
                                FeatureDetailView(feature: feature)
                            } label: {
                                HStack(alignment: .top, spacing: 12) {
                                    Image(systemName: feature.symbol)
                                        .font(.title3)
                                        .frame(width: 28)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(feature.title).font(.headline)
                                        Text(feature.summary)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(2)
                                        Label(feature.status.rawValue, systemImage: feature.status.icon)
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Jarvis Features")
        .searchable(text: $searchText, prompt: "Search features, tools or prompts")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Text("\(filtered.count)/\(JarvisFeatureCatalog.all.count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct FeatureDetailView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    let feature: JarvisFeature
    @State private var copied = false

    var body: some View {
        List {
            Section {
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: feature.symbol).font(.largeTitle)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(feature.title).font(.title3.bold())
                        Label(feature.status.rawValue, systemImage: feature.status.icon)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Text(feature.summary).font(.headline)
            }

            Section("What it does") {
                Text(feature.details).textSelection(.enabled)
            }

            Section("How to verify it") {
                Text(feature.verification).textSelection(.enabled)
            }

            Section("Example prompt / test") {
                Text(feature.examplePrompt)
                    .font(.body.monospaced())
                    .textSelection(.enabled)

                Button {
                    UIPasteboard.general.string = feature.examplePrompt
                    copied = true
                } label: {
                    Label(copied ? "Copied" : "Copy Prompt", systemImage: copied ? "checkmark" : "doc.on.doc")
                }

                if feature.runnable {
                    Button {
                        Task { await appModel.sendCommand(feature.examplePrompt) }
                    } label: {
                        Label("Run Test Prompt", systemImage: "play.fill")
                    }
                    .disabled(appModel.isSending)
                } else {
                    Text("This example is intentionally not run automatically because it is a setup procedure, contains a placeholder, can create a side effect, or documents a platform/deployment boundary.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Feature")
        .navigationBarTitleDisplayMode(.inline)
    }
}
