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

    private static func feature(
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
            id: id,
            category: category,
            title: title,
            summary: summary,
            details: details,
            examplePrompt: prompt,
            verification: verification,
            status: status,
            symbol: symbol,
            runnable: runnable
        )
    }

    private static func build() -> [JarvisFeature] {
        var items: [JarvisFeature] = []

        // MARK: Voice & conversation
        items.append(feature(
            "wake-word", "Voice & Conversation", "Hands-free ‘Jarvis’ wake word",
            "Talk through the Ray-Bans without touching the phone.",
            "The iPhone keeps Apple Speech active and recognizes either a complete command beginning with ‘Jarvis’ or a standalone ‘Jarvis’ followed by ‘Yes, sir?’ and a second utterance. When available it prefers the Ray-Ban Bluetooth HFP microphone and speaker route.",
            "Jarvis, what time is my next calendar event?",
            "With Hands-free Jarvis enabled, say the prompt without touching the phone. The app should transition from listening to thinking and then speaking.",
            .ready, "waveform.circle.fill"
        ))
        items.append(feature(
            "follow-up", "Voice & Conversation", "Five-second conversational follow-up",
            "Continue talking without repeating the wake word after Jarvis answers.",
            "After a spoken response, Jarvis leaves a short conversational window open. If you start speaking during that window, your next utterance is treated as a continuation even if it runs past the five-second deadline.",
            "Tell me more.",
            "Ask any question through the wake word, wait for the answer, then say this prompt within about five seconds without saying ‘Jarvis’ again.",
            .ready, "arrow.turn.down.right"
        ))
        items.append(feature(
            "barge-in", "Voice & Conversation", "Barge-in / interruption",
            "Interrupt Jarvis while it is speaking.",
            "A second on-device speech recognizer listens while speech is playing. Echo filtering suppresses likely playback, while phrases such as ‘wait’, ‘stop’, ‘actually’, or a new multi-word request can stop playback and become the next command.",
            "Wait — what about tomorrow instead?",
            "Ask for a moderately long answer, then say this while Jarvis is still talking. Playback should stop and the interruption should become the next request.",
            .ready, "hand.raised.fill"
        ))
        items.append(feature(
            "long-dictation", "Voice & Conversation", "Long dictation handling",
            "Allows longer pauses for email addresses, URLs, spelling and dictated messages.",
            "The speech loop uses a larger silence window for utterances that look like dictation rather than prematurely sending them after a normal conversational pause.",
            "Jarvis, draft an email saying I’ll send the revised document tomorrow afternoon.",
            "Pause briefly in the middle of the sentence. The recognizer should keep collecting rather than immediately sending a truncated command.",
            .ready, "text.bubble.fill"
        ))
        items.append(feature(
            "asr-vocabulary", "Voice & Conversation", "Personal speech vocabulary",
            "Biases speech recognition toward names Jarvis frequently needs.",
            "Apple Speech receives contextual vocabulary including Jarvis and Dubeck. A deterministic correction also normalizes common ‘Dubek’ / ‘Du Beck’ recognition errors to Dubeck.",
            "Jarvis, spell Dubeck.",
            "Check the live/last-heard transcript. It should use the expected spelling rather than a common phonetic misrecognition.",
            .ready, "character.cursor.ibeam"
        ))
        items.append(feature(
            "local-aliases", "Voice & Conversation", "Instant local command aliases",
            "Handles selected phone-side commands without an LLM round trip.",
            "The iPhone intercepts a small set of deterministic commands for OCR, QR scanning, vision toggles, speech/alert muting, temporary whisper mode, connection diagnostics and explicitly sending a queued command.",
            "Jarvis, connection diagnostics.",
            "The response should be marked as an iPhone/frontend-only turn and return immediately without waiting for Qwen.",
            .frontendOnly, "bolt.fill"
        ))

        // MARK: Models & reasoning
        items.append(feature(
            "qwen8", "Models & Reasoning", "Qwen3 8B fast planner",
            "Low-latency local planner for routine conversation and tool selection.",
            "Most ordinary requests use qwen3:8b through Ollama with thinking disabled. The backend keeps it warm when possible and supplies a shorter conversation context for latency.",
            "Jarvis, give me a one-sentence status check.",
            "Open Session History after the response. The model badge should normally show the 8B planner when automatic routing is active.",
            .ready, "hare.fill"
        ))
        items.append(feature(
            "qwen27", "Models & Reasoning", "Qwen3.8 27B deep reasoning",
            "Larger local model for architecture, difficult code, math and multi-step planning.",
            "Automatic routing sends sufficiently complex requests to qwen3.8:27b. Jarvis may speak a brief acknowledgement while the larger model starts, then rewarm 8B afterward.",
            "Jarvis, analyze the concurrency bottlenecks in a voice agent that streams speech, vision and background jobs simultaneously.",
            "Check Session History after completion. A hard reasoning request should show the 27B model when automatic routing is enabled.",
            .ready, "brain.head.profile"
        ))
        items.append(feature(
            "model-routing", "Models & Reasoning", "Dynamic model routing",
            "Automatically chooses 8B for speed or 27B for harder work.",
            "A deterministic complexity classifier routes requests without spending another LLM call just to choose a model. Manual pinning remains available in Settings.",
            "Jarvis, explain why a race condition can occur when two asynchronous workers mutate the same state, and propose a fix.",
            "Compare this with a trivial question. Session History should show different model choices when the classifier considers the harder request worthy of 27B.",
            .ready, "arrow.triangle.branch"
        ))
        items.append(feature(
            "reality-check", "Models & Reasoning", "Personality reality check",
            "Challenges impossible or internally contradictory requests instead of pretending they worked.",
            "The system prompt requires Jarvis to point out missing physical capabilities, contradictory premises, or dependencies before execution, while still suggesting the nearest feasible path.",
            "Jarvis, physically move the coffee cup on my desk two feet to the left.",
            "Jarvis should explain that it cannot manipulate the physical cup rather than claiming success.",
            .ready, "checkmark.shield.fill"
        ))
        items.append(feature(
            "persona", "Models & Reasoning", "J.A.R.V.I.S.-style interaction persona",
            "Restrained, capable conversational partner rather than a generic chatbot tone.",
            "The persona is composed, concise, dry, respectful and willing to challenge a bad assumption. It addresses you as ‘sir’ naturally without forcing the word into every sentence, and must not claim tools succeeded when they did not.",
            "Jarvis, I’m about to make a decision based on an assumption that may be wrong. Tell me what you would challenge first.",
            "The answer should sound conversational and critical where warranted, not like a cheerleading assistant.",
            .ready, "person.wave.2.fill"
        ))

        // MARK: Speech output & HUD
        items.append(feature(
            "kokoro", "Speech & Audio HUD", "Kokoro local neural voice",
            "Low-latency neural speech generated on your PC.",
            "Jarvis requests WAV speech from the local Kokoro-82M service. Apple speech synthesis remains a fallback if the neural TTS service is unavailable.",
            "Jarvis, say ‘neural voice test complete.’",
            "Settings → Voice should report Kokoro ready when the PC service is available. Spoken output should use the neural voice rather than the Apple fallback.",
            .ready, "speaker.wave.3.fill"
        ))
        items.append(feature(
            "streamed-speech", "Speech & Audio HUD", "Incremental response speech",
            "Starts speaking completed clauses before a long answer has fully generated.",
            "The streaming endpoint sends text deltas to the iPhone. The app accumulates complete sentence/clause chunks, synthesizes them and plays them while later text is still arriving.",
            "Jarvis, give me five concise reasons local inference is useful for a personal assistant.",
            "Watch Last Response while listening. Text should continue filling in while early completed chunks are already being spoken.",
            .ready, "waveform.path.ecg"
        ))
        items.append(feature(
            "whisper", "Speech & Audio HUD", "Adaptive and forced whisper mode",
            "Quietly lowers speech output in a quiet environment or on command.",
            "The iPhone estimates an ambient noise floor from microphone buffers. Adaptive whisper lowers playback volume and alters apparent rate/pitch; you can also force whisper for a bounded period locally.",
            "Jarvis, whisper for 10 minutes.",
            "The response should be immediate and the app should indicate whisper mode. Say ‘Jarvis, normal voice’ to end it early.",
            .frontendOnly, "speaker.wave.1.fill"
        ))
        items.append(feature(
            "hud-cues", "Speech & Audio HUD", "Contextual audio HUD cues",
            "Distinct earcons communicate thinking, scans, tasks, warnings and errors.",
            "Synthesized local tones mark thinking, visual scans, search, workflow/task start, completion, warnings, urgent events and errors. Cue volume can scale with ambient noise and has a manual level control.",
            "Jarvis, search the web for today’s top technology headline.",
            "With Ambient audio HUD cues enabled, you should hear a subtle state cue while the request is being processed.",
            .ready, "waveform.badge.plus"
        ))
        items.append(feature(
            "quiet-speech", "Speech & Audio HUD", "Quiet-speech mode",
            "Lets you speak more softly in public while using the normal acoustic microphone.",
            "This is still ordinary acoustic speech recognition, not EMG or true subvocal decoding. The mode is intended to make the interaction usable at a lower speaking volume.",
            "Jarvis, what is my next event?",
            "Enable Quiet-speech mode and deliver the prompt softly through the Ray-Bans. Verify the transcript is still captured correctly.",
            .optional, "waveform.badge.mic"
        ))

        // MARK: Vision & perception
        items.append(feature(
            "dat-camera", "Vision & Perception", "Ray-Ban DAT camera stream",
            "Streams the Meta Ray-Ban camera feed into the companion app.",
            "Meta’s Device Access Toolkit provides the camera stream used by passive vision and all iPhone-side visual features. The app shows registration, camera permission and stream state.",
            "Jarvis, read this.",
            "Open the Meta Ray-Ban card. Confirm registration, DAT eligibility, camera permission and a live frame before testing any downstream vision feature.",
            .ready, "eyeglasses"
        ))
        items.append(feature(
            "passive-vision", "Vision & Perception", "Passive vision sampling",
            "Samples low-resolution glasses frames and sends them to the PC vision worker.",
            "When enabled, the iPhone periodically JPEG-compresses Ray-Ban frames and sends them over the authenticated companion WebSocket. The PC vision worker analyzes frames without letting them build an unbounded queue.",
            "Jarvis, is passive vision on?",
            "The Persistent Presence card should show passive vision activity and the companion connection should remain connected. General live-scene answers are tracked separately below because that backend path still awaits deployment/testing.",
            .ready, "eye.fill"
        ))
        items.append(feature(
            "live-scene", "Vision & Perception", "General ‘what am I seeing?’ scene answers",
            "Conversational arbitrary scene understanding through Moondream.",
            "A repository fix exists for the recent-frame/Moondream request path, but your currently running remote PC backend has not been updated and verified. Do not treat this feature as deployed yet.",
            "Jarvis, what can you see right now?",
            "Do not use this as a verification test until the PC backend is updated. Once deployed, a current-frame question should return a semantic scene description without a multi-image HTTP 400.",
            .pendingBackend, "eye.trianglebadge.exclamationmark", runnable: false
        ))
        items.append(feature(
            "visual-ring", "Vision & Perception", "30-second iPhone visual history",
            "Keeps recent downsampled Ray-Ban frames in RAM on the phone.",
            "The iPhone maintains an auto-expiring ring buffer for about thirty seconds. Frames are RAM-only and are not automatically inserted into permanent memory. A thumbnail timeline and cache telemetry are visible in the app.",
            "Jarvis, connection diagnostics.",
            "With the camera streaming, the On-device Intelligence card should show the visual cache filling with recent frames and then expiring older ones.",
            .frontendOnly, "clock.arrow.circlepath"
        ))
        items.append(feature(
            "ocr", "Vision & Perception", "On-device OCR",
            "Reads visible text from the latest Ray-Ban frame without using the PC vision model.",
            "Apple Vision performs text recognition directly on the iPhone. This is intentionally narrower and faster than general scene understanding and works even while the backend live-scene path is pending.",
            "Jarvis, read this.",
            "Look at a clear sign, screen or printed label through the glasses and use the prompt. The response should be marked as an iPhone-only turn.",
            .frontendOnly, "text.viewfinder"
        ))
        items.append(feature(
            "ocr-copy", "Vision & Perception", "Visible text to iPhone clipboard",
            "Copies recognized glasses text directly to the phone clipboard.",
            "The same on-device OCR pipeline can place recognized text in UIPasteboard without a backend request.",
            "Jarvis, copy this text.",
            "Look at readable text, issue the prompt, then paste into Notes or another text field to confirm it arrived on the iPhone clipboard.",
            .frontendOnly, "doc.on.clipboard.fill"
        ))
        items.append(feature(
            "qr", "Vision & Perception", "QR and barcode scanning",
            "Decodes visible QR/barcode payloads entirely on the iPhone.",
            "Apple Vision scans the current Ray-Ban frame for supported machine-readable codes. The first payload is shown and copied to the iPhone clipboard.",
            "Jarvis, scan the QR code.",
            "Point at a known QR code and compare the returned/copied payload with the expected value.",
            .frontendOnly, "qrcode.viewfinder"
        ))
        items.append(feature(
            "fast-perception", "Vision & Perception", "Continuous on-device fast perception",
            "Runs lightweight structural Vision requests on recent glasses frames.",
            "When enabled, the iPhone periodically performs OCR, QR/barcode detection, face rectangle counting without identity, human rectangle detection, generic rectangle detection and attention saliency. It is off by default to reduce battery use.",
            "Jarvis, connection diagnostics.",
            "Enable Continuous on-device fast perception, then inspect the On-device Intelligence card for detection summaries and scan status.",
            .optional, "viewfinder.circle.fill"
        ))
        items.append(feature(
            "known-people", "Vision & Perception", "Known People closed-set recognition",
            "Matches visible faces only against people you deliberately enroll.",
            "Enrollment uses multiple images to create private Apple Vision feature prints. Raw enrollment photos are discarded; feature profiles are kept in this device’s Keychain. Continuous matching requires stability and rejects ambiguous results rather than identifying arbitrary strangers.",
            "Jarvis, who is this?",
            "First enroll the person in Settings → Manage Known People using 3–6 clear samples, enable recognition, then look at them through the glasses and issue the prompt.",
            .frontendOnly, "person.crop.circle.badge.checkmark"
        ))
        items.append(feature(
            "known-person-context", "Vision & Perception", "Known-person local context recall",
            "Associates a recognized enrolled person with your own local notes and recent Jarvis turns that mention them.",
            "The iPhone can retrieve the private note attached to an enrolled profile plus nearby turns from the bounded conversation history on this device. Full Gmail/Calendar/vector-memory retrieval by stable contact_id is not yet implemented backend-side.",
            "Jarvis, what do I know about this person?",
            "Enroll someone, add a private note, make sure the person is recognized, then ask the prompt. Jarvis should return the note and any matching local conversation context.",
            .frontendOnly, "person.text.rectangle"
        ))
        items.append(feature(
            "spatial-memory", "Vision & Perception", "Spatial last-seen object memory",
            "Remembers the last visual scene in which selected portable objects were observed.",
            "The backend stores conservative object sightings from vision analysis with time and scene/location context. This is last-seen memory, not a full 3D SLAM/world map.",
            "Jarvis, where did I last see my keys?",
            "After passive vision has observed an object and the backend has stored a sighting, ask the prompt. Jarvis should cite the most recent scene rather than inventing a current location.",
            .ready, "mappin.and.ellipse"
        ))
        items.append(feature(
            "visual-hazards", "Vision & Perception", "Proactive visible hazard/error warnings",
            "Can proactively flag a small set of directly visible high-confidence conditions.",
            "The PC vision prompt is conservative about open flame/hot tools, running or spilling liquid, obvious trip hazards, visibly open/ajar access points when relevant, and legible application/terminal errors. It is explicitly not a certified safety system and must not infer hidden states.",
            "Jarvis, what was the last proactive visual observation?",
            "With passive vision active, use a harmless visible test condition such as a legible terminal error. Verify Jarvis reports only directly visible evidence.",
            .ready, "exclamationmark.triangle.fill"
        ))

        // MARK: Memory & context
        items.append(feature(
            "short-history", "Memory & Context", "Conversation context discipline",
            "Uses recent context without letting stale topics hijack unclear speech.",
            "Normal 8B turns receive only the immediately preceding exchange. Older history is expanded when you explicitly refer backward with phrases such as ‘earlier’, ‘remember’, or ‘five prompts ago’. A garbled utterance should not resurrect an unrelated old topic.",
            "What did you say about that one prompt ago?",
            "Discuss one topic, switch topics several times, then make an intentionally vague utterance. Jarvis should ask for clarification rather than returning to the oldest topic.",
            .ready, "text.line.first.and.arrowtriangle.forward"
        ))
        items.append(feature(
            "episodic-memory", "Memory & Context", "Long-term episodic semantic memory",
            "Embeds useful past interactions for semantic recall across sessions.",
            "The PC stores conversation episodes and uses nomic-embed-text to retrieve semantically related memories. Retrieval is on-demand so normal 8B requests do not pay an embedding latency penalty every time.",
            "Jarvis, what did we previously discuss about Tailscale?",
            "Ask about a distinctive topic from an older session. A successful answer should surface relevant historical information rather than only the immediately preceding turn.",
            .ready, "memorychip.fill"
        ))
        items.append(feature(
            "decaying-memory", "Memory & Context", "Decaying temporary focus state",
            "Stores temporary context that automatically expires.",
            "A temporary focus can carry a TTL so a short-lived project/debugging state influences relevant requests without becoming a permanent preference.",
            "Jarvis, remember that I’m debugging the networking issue for the next two hours.",
            "After setting the focus, ask ‘What am I focused on right now?’ It should reflect the temporary state during its lifetime.",
            .ready, "timer"
        ))
        items.append(feature(
            "environment-state", "Memory & Context", "Persistent environmental state graph",
            "Carries current project, location/profile, device and perception state into prompts.",
            "The PC maintains structured environmental state including project focus, home/mobile state, Ray-Ban status, phone transport, selected preferences, recent visual context and optional Health context.",
            "Jarvis, what context do you currently have about my environment?",
            "Jarvis should summarize available state without requiring you to restate the current project/profile first.",
            .ready, "point.3.connected.trianglepath.dotted"
        ))
        items.append(feature(
            "unified-search", "Memory & Context", "Unified cross-app vector search",
            "Searches indexed Gmail, Calendar, local notes and past conversations together.",
            "The backend maintains a shared semantic index using nomic-embed-text so you can search by concept rather than knowing which application contains the information.",
            "Jarvis, search across my information for anything about the networking bug.",
            "Use a distinctive phrase that appears in one of your indexed sources and verify Jarvis returns relevant cross-source context.",
            .ready, "rectangle.stack.badge.magnifyingglass"
        ))
        items.append(feature(
            "local-history-ui", "Memory & Context", "Searchable iPhone session history",
            "Stores a bounded local transcript for inspection and debugging.",
            "Recent user/Jarvis turns are retained on the iPhone with timestamps and model labels. This is separate from the PC’s long-term semantic memory and can be searched in Session History.",
            "Jarvis, say the phrase ‘feature guide history test’.",
            "Open Session History and search for ‘feature guide history test’. The turn should appear locally.",
            .frontendOnly, "doc.text.magnifyingglass"
        ))

        // MARK: Web & knowledge
        items.append(feature(
            "serper", "Web & Knowledge", "Serper real-time web search",
            "Searches the current web through the Serper API.",
            "The Serper key stays on the Windows PC. Jarvis can route current-information queries to search and then synthesize a compact answer rather than speaking an entire result page or URLs aloud.",
            "Jarvis, search the web for the latest OpenAI news.",
            "If Serper is configured, the answer should reflect current search results and should be a short synthesis, not a raw list of URLs/snippets.",
            .setup, "globe.badge.chevron.backward"
        ))
        items.append(feature(
            "query-refine", "Web & Knowledge", "Dynamic search query refinement",
            "Condenses long conversational requests into cleaner search-engine queries.",
            "The fast planner can transform a rambling voice request into a concise query while preserving important names, dates and constraints. Simple queries skip the extra pass.",
            "Jarvis, search the web and figure out whether there have been any meaningful announcements from OpenAI today about new models or product releases.",
            "The resulting spoken answer should be focused on the requested current facts rather than mirroring the conversational wording verbatim.",
            .ready, "text.magnifyingglass"
        ))

        // MARK: Google & communications
        items.append(feature(
            "gmail-read", "Google & Communications", "Gmail reading and search",
            "Reads and searches your Gmail with cleaned speech-friendly output.",
            "The backend can query Gmail, retrieve sender/subject/date/unread state and cleaned body text. Tracking links and newsletter boilerplate are reduced so TTS does not read enormous URLs.",
            "Jarvis, what is my latest unread email?",
            "Jarvis should return the useful sender/subject/content without narrating tracking URLs.",
            .setup, "envelope.open.fill"
        ))
        items.append(feature(
            "gmail-send", "Google & Communications", "Protected Gmail sending",
            "Can send email only after the configured safety checks succeed.",
            "Outbound Gmail is an external-write action. It normally requires confirmation and the final resolved recipient must also be on the exact PC-side allowed-recipient list. An empty list blocks all sending.",
            "Jarvis, send a test email to [an address on my allowlist] saying ‘Jarvis email test.’",
            "Replace the bracketed address with an allowed recipient. Jarvis should ask for confirmation before sending; do not confirm unless you actually want the message sent.",
            .setup, "paperplane.fill", runnable: false
        ))
        items.append(feature(
            "contacts", "Google & Communications", "Google Contacts resolution",
            "Resolves saved names to contact details for other tools such as Gmail.",
            "Jarvis can look up a saved contact by name and use the resolved address in a later email action. The email allowlist is checked after resolution.",
            "Jarvis, look up the email address for [saved contact name].",
            "Replace the placeholder with a contact in Google Contacts. Jarvis should resolve the saved address without sending anything.",
            .setup, "person.crop.circle.fill", runnable: false
        ))
        items.append(feature(
            "calendar-read", "Google & Communications", "Google Calendar read/search",
            "Lists, searches and summarizes past or upcoming calendar events.",
            "The Calendar integration can list future events, search by query, inspect past events and identify the most recent event. Times are converted into speech-friendly formatting.",
            "Jarvis, what is on my calendar tomorrow?",
            "The answer should reflect actual Calendar events for tomorrow and use human-readable times.",
            .setup, "calendar"
        ))
        items.append(feature(
            "calendar-write", "Google & Communications", "Protected calendar creation",
            "Creates calendar events behind the external-write confirmation boundary.",
            "Creating an event is not auto-executed under the default permission policy. Jarvis prepares the action and asks you to confirm before the Calendar API write.",
            "Jarvis, create a test calendar event tomorrow at 4 PM called ‘Jarvis test’.",
            "Jarvis should ask for confirmation before creation. Cancel unless you actually want the test event.",
            .setup, "calendar.badge.plus"
        ))
        items.append(feature(
            "calendar-conflict", "Google & Communications", "Calendar conflict analysis",
            "Detects overlapping timed events and proposes alternatives.",
            "Jarvis can inspect the schedule for overlaps and suggest open alternative slots. It does not silently move or decline meetings.",
            "Jarvis, check my calendar for conflicts.",
            "If conflicts exist, Jarvis should describe them and propose open alternatives without changing anything automatically.",
            .ready, "calendar.badge.exclamationmark"
        ))

        // MARK: PC & browser
        items.append(feature(
            "pc-apps", "PC & Browser", "Windows application control",
            "Checks, launches and closes explicitly supported Windows applications.",
            "The backend exposes explicit app/process tools instead of an unrestricted shell. It can list/check processes, launch apps, close apps, open URLs/paths and use Minecraft-specific helpers.",
            "Jarvis, is Minecraft running?",
            "Jarvis should inspect the PC process state and answer from the tool result rather than guessing.",
            .ready, "desktopcomputer"
        ))
        items.append(feature(
            "minecraft", "PC & Browser", "Minecraft helpers",
            "Checks or ensures Minecraft is running on the PC.",
            "Dedicated tools can check Minecraft state, launch it, or ensure it is running. Process-based detection may still depend on the Java process environment.",
            "Jarvis, make sure Minecraft is running.",
            "If Minecraft is already running Jarvis should leave it alone; otherwise it should use the configured launch helper.",
            .ready, "cube.fill"
        ))
        items.append(feature(
            "browser", "PC & Browser", "Opera/Chromium tab control",
            "Uses Chrome DevTools Protocol to inspect and control browser tabs.",
            "When Opera is launched with the configured remote-debugging port, Jarvis can list tabs, find/focus/close matching tabs and open known sites such as Spotify, YouTube, Gmail and ChatGPT.",
            "Jarvis, what browser tabs are open?",
            "The answer should list concise tab titles without reading giant URLs aloud.",
            .setup, "safari.fill"
        ))
        items.append(feature(
            "smart-app", "PC & Browser", "Smart browser-vs-app routing",
            "Checks browser tabs before blindly launching a native application.",
            "For known services, smart open/status/close logic can treat an existing browser tab as the active app representation. This avoids opening duplicate native apps when the service is already available in Opera.",
            "Jarvis, open Spotify.",
            "If Spotify is already open as a controllable browser tab, Jarvis should focus/reuse it rather than necessarily launching a separate app.",
            .ready, "rectangle.on.rectangle.angled"
        ))
        items.append(feature(
            "pc-context", "PC & Browser", "Cross-device PC context handoff",
            "Lets the glasses ask what was active on the Windows PC after you walk away.",
            "A lightweight PC monitor records the foreground process/window and available browser-tab context. It does not imply Jarvis has read the full contents of an arbitrary document or IDE buffer.",
            "Jarvis, what was I doing on my PC?",
            "Switch to a distinctive app/window on the PC, walk away, then ask the prompt. Jarvis should report the recorded foreground context.",
            .ready, "rectangle.connected.to.line.below"
        ))

        // MARK: Automation & agents
        items.append(feature(
            "jobs", "Automation & Agents", "Persistent scheduled and event jobs",
            "Runs one-time, recurring or event-triggered tasks that survive backend restarts.",
            "The backend stores jobs in SQLite. Jobs can be time-based, recurring, or tied to events such as home arrival. They can be listed and cancelled.",
            "Jarvis, list my scheduled jobs.",
            "Jarvis should return the persistent job list, including any previously configured arrival/recurring jobs.",
            .ready, "clock.badge.checkmark"
        ))
        items.append(feature(
            "briefing", "Automation & Agents", "Automated daily audio briefing",
            "Produces scheduled summaries from your calendar, mail, current information and background work.",
            "Recurring briefing jobs combine relevant Calendar data, unread mail, weather/news through Serper when available, and active background-job status, then deliver the result through the companion channel.",
            "Jarvis, give me my morning briefing.",
            "A configured system should synthesize a concise cross-source briefing. Scheduling a recurring briefing can be tested separately with a future time.",
            .ready, "sunrise.fill"
        ))
        items.append(feature(
            "workers", "Automation & Agents", "Background multi-agent worker queue",
            "Runs longer work without blocking the primary voice conversation.",
            "Persistent background workers can accept long tasks, track status, survive ordinary service restarts and send completion/failure events. Heavy jobs still contend for the same physical GPU when they use large models.",
            "Jarvis, list my background jobs.",
            "The response should show the current persistent queue while normal conversation remains usable.",
            .ready, "square.stack.3d.up.fill"
        ))
        items.append(feature(
            "dag", "Automation & Agents", "Autonomous DAG workflows",
            "Compiles a larger goal into dependent tool steps and parallelizes safe reads.",
            "The 27B planner can produce a validated directed acyclic graph with bounded nodes. Independent read-only steps may execute concurrently; later nodes can use earlier results. Existing permission checks still apply to every consequential action.",
            "Jarvis, prepare me for tomorrow morning by checking my calendar, important unread email and the weather, then summarize what matters.",
            "The answer should combine multiple tool results into one coherent result rather than requiring you to issue each step separately.",
            .ready, "point.3.filled.connected.trianglepath.dotted"
        ))
        items.append(feature(
            "proactive", "Automation & Agents", "Proactive interruption thresholds",
            "Only interrupts you when a background event meets your configured urgency threshold.",
            "Companion events carry info, warning or urgent severity. Settings lets you choose Info+, Warning+ or Urgent only, reducing unnecessary spoken interruptions.",
            "Jarvis, what is my proactive interruption threshold?",
            "Compare the answer with Settings → Interrupt me at. Background events below that threshold should remain silent.",
            .ready, "bell.badge.fill"
        ))
        items.append(feature(
            "prefetch", "Automation & Agents", "Predictive model/context prewarming",
            "Warms likely-needed local resources shortly before calendar events.",
            "Before an upcoming event, the backend can warm the 8B model and retrieve related local context so the first interaction near the meeting has less startup overhead.",
            "Jarvis, what is my next meeting?",
            "This prompt confirms the calendar dependency. Actual prewarming is background behavior; verify lower cold-start latency near a scheduled meeting using Session History timing.",
            .ready, "bolt.horizontal.circle.fill"
        ))

        // MARK: Meetings
        items.append(feature(
            "meeting-notes", "Meetings", "Explicit Meeting Notes mode",
            "Records and transcribes a meeting only when you deliberately start it.",
            "Meeting mode visibly owns the microphone, rotates Apple Speech tasks for long sessions and sends transcript chunks to the PC. It is explicit opt-in and should only be used where recording/transcription is permitted and appropriately disclosed.",
            "Jarvis, stop meeting notes.",
            "Use the Start Meeting Notes button, speak a short sample, then stop. The app should show the live transcript and extract concrete action items when the backend is reachable.",
            .ready, "record.circle.fill"
        ))
        items.append(feature(
            "meeting-offline", "Meetings", "Offline meeting capture",
            "Keeps transcribing locally if the PC becomes unreachable.",
            "The iPhone accumulates transcript chunks locally, supports pause/resume and bookmarks, saves a local snapshot and offers Sync & Extract later when the backend returns.",
            "Start Meeting Notes while the server is unreachable.",
            "This verification is done from the UI rather than by sending the prompt: begin a meeting with offline capture enabled and confirm the status says local/sync pending.",
            .frontendOnly, "iphone.and.arrow.forward", runnable: false
        ))
        items.append(feature(
            "meeting-bookmarks", "Meetings", "Meeting timer, pause/resume and bookmarks",
            "Adds local controls and timestamped bookmarks to long meeting capture.",
            "The iPhone shows elapsed time, can pause/resume speech capture, and records bookmarks with relative timestamps and a short nearby transcript snippet. Local transcript text can be shared through the iOS Share Sheet.",
            "Use the Meeting Notes controls.",
            "Start Meeting Notes, press Bookmark after a sentence, pause/resume once, then verify the bookmark timestamp and exported transcript.",
            .frontendOnly, "bookmark.fill", runnable: false
        ))
        items.append(feature(
            "fact-check", "Meetings", "Local metric contradiction checks",
            "Can flag direct numeric/metric contradictions against your indexed local records during an active meeting session.",
            "The backend treats its own records as potentially stale and only raises a possible contradiction when stored evidence directly conflicts with a concrete claim. It is not a universal truth detector.",
            "Jarvis, search across my information for the metric we discussed earlier.",
            "For a controlled test, use a known numeric value already present in your local index and compare it with a contradictory statement during Meeting Notes.",
            .ready, "checkmark.message.fill"
        ))

        // MARK: Location, network & sensors
        items.append(feature(
            "tailscale", "Network & Sensors", "Automatic LAN → Tailscale failover",
            "Keeps the iPhone connected to Jarvis away from home Wi‑Fi.",
            "The client prefers the configured home/LAN URL and falls back to a private Tailscale Serve HTTPS endpoint. The API token remains in use; Funnel and public port forwarding are intentionally avoided.",
            "Jarvis, connection diagnostics.",
            "Away from the home LAN, the diagnostic response/card should show Tailscale reachable and the active companion path should be remote/private.",
            .setup, "network"
        ))
        items.append(feature(
            "bandwidth", "Network & Sensors", "Adaptive remote vision bandwidth",
            "Reduces passive camera traffic on the Tailscale path.",
            "Passive vision uses a higher sampling rate/resolution on LAN and automatically reduces frame frequency and dimensions when the companion is remote, preserving cellular bandwidth.",
            "Jarvis, connection diagnostics.",
            "Compare local visual/transport telemetry at home and away. Remote operation should use the reduced passive vision cadence when adaptive bandwidth is enabled.",
            .ready, "arrow.down.right.and.arrow.up.left"
        ))
        items.append(feature(
            "geofence", "Network & Sensors", "Home/mobile geofenced profiles",
            "Switches context when the iPhone enters or leaves the configured home region.",
            "Core Location monitors a private home geofence. Entry/exit updates the home/mobile profile and can emit a home_arrival event for scheduled automation.",
            "Jarvis, what profile am I in right now?",
            "Enable/configure Home Geofence, then compare Jarvis’s context inside and outside the configured region.",
            .setup, "location.circle.fill"
        ))
        items.append(feature(
            "motion", "Network & Sensors", "iPhone motion/travel context",
            "Shows coarse local activity such as stationary, walking, running, cycling or driving.",
            "Optional Core Motion/Core Location updates provide local activity, speed, course and altitude diagnostics. This context is off by default and requires normal iOS permissions.",
            "Jarvis, connection diagnostics.",
            "Enable Motion / travel context and inspect the diagnostics while stationary and while walking. The coarse activity label should update.",
            .optional, "figure.walk.motion"
        ))
        items.append(feature(
            "health", "Network & Sensors", "Apple Health / Watch context",
            "Optionally supplies recent heart rate, HRV and sleep context.",
            "HealthKit access is explicit and read-only. Jarvis does not convert these measurements into diagnoses, psychological stress labels or unsupported medical conclusions.",
            "Jarvis, what recent Health context do you have?",
            "Enable Apple Watch / Health context and grant the requested Health permissions. Jarvis should report only available recent measurements and their limits.",
            .optional, "heart.text.square.fill"
        ))

        // MARK: Personal data & local records
        items.append(feature(
            "expenses", "Personal Records", "Receipt and invoice expense capture",
            "Extracts supported receipt fields into local expense records.",
            "Using recent visual imagery, the backend can parse legible merchant/date/tax/tip/total/line-item information and save it to SQLite plus a CSV under Jarvis AppData. The prompt is instructed not to guess unreadable values.",
            "Jarvis, log this receipt.",
            "Point the glasses at a clear receipt and use the prompt. Then ask Jarvis to list recent expenses and compare the stored totals with the receipt.",
            .ready, "receipt.fill"
        ))
        items.append(feature(
            "journal", "Personal Records", "Automated daily local journal",
            "Creates a concise Markdown summary of the day from local Jarvis activity.",
            "The journal can aggregate relevant conversations, completed background work, communications and spatial/object records. It is instructed not to invent your feelings or motives.",
            "Jarvis, write today’s journal.",
            "Jarvis should produce/save today’s local Markdown entry and summarize concrete recorded activity without fabricated emotional interpretation.",
            .ready, "book.pages.fill"
        ))

        // MARK: System observability
        items.append(feature(
            "resources", "System & Diagnostics", "PC resource guardrail monitoring",
            "Monitors CPU, RAM, NVIDIA GPU, VRAM, GPU temperature and queue pressure.",
            "The PC periodically samples system resources and can generate proactive warnings near configured saturation conditions. This is useful when 8B/27B/vision/TTS compete for the same machine.",
            "Jarvis, GPU status.",
            "The response should report current local GPU/VRAM telemetry rather than generic hardware information.",
            .ready, "gauge.with.dots.needle.67percent"
        ))
        items.append(feature(
            "audio-damping", "System & Diagnostics", "Smart PC audio damping",
            "Temporarily lowers Windows output volume during active Jarvis conversation.",
            "When enabled, the backend stores the previous Windows master volume, lowers it while you are interacting with Jarvis and restores it afterward. It currently controls the Windows endpoint, not arbitrary smart-speaker ecosystems.",
            "Jarvis, give me a short spoken test response.",
            "Play audio on the PC first, then speak to Jarvis with Smart PC audio damping enabled. PC volume should dip during the interaction and restore afterward.",
            .optional, "speaker.minus.fill"
        ))
        items.append(feature(
            "frontend-diagnostics", "System & Diagnostics", "iPhone diagnostic report",
            "Collects route, ASR, Ray-Ban, local vision, queue and latency telemetry in one place.",
            "The frontend independently probes LAN/Tailscale latency and reports voice state, audio route, ASR confidence, camera state, local cache size/FPS, perception status, offline queue depth, motion state, Health state and last model/timing.",
            "Jarvis, connection diagnostics.",
            "Compare the response with On-device Intelligence. You can also press Copy Diagnostics and paste the report into a note or support message.",
            .frontendOnly, "stethoscope"
        ))
        items.append(feature(
            "latency", "System & Diagnostics", "Per-turn model and latency telemetry",
            "Measures model choice, first response, first audio and total turn time.",
            "The iPhone records the model label reported by the streaming backend plus time to first text delta, first playable speech and completion. Session History exposes the latest timing.",
            "Jarvis, say ‘latency test complete.’",
            "After the reply, open Session History and inspect the timing line/model badge for that turn.",
            .frontendOnly, "stopwatch.fill"
        ))
        items.append(feature(
            "offline-queue", "System & Diagnostics", "Offline command staging",
            "Preserves commands when both configured server paths are unreachable.",
            "The iPhone can queue a failed command locally instead of discarding it. Queued commands never execute automatically when connectivity returns; you must explicitly send the next queued command.",
            "Jarvis, send queued command.",
            "To test safely, disconnect both server paths, issue a harmless request, verify it appears in the queue, restore connectivity, then explicitly send it.",
            .frontendOnly, "tray.full.fill"
        ))
        items.append(feature(
            "shortcuts", "System & Diagnostics", "App Intents / Shortcuts / Action Button",
            "Exposes common Jarvis actions to iOS Shortcuts.",
            "The app registers intents for Talk to Jarvis, local Visual Scan, Read Visible Text, Toggle Passive Vision, Toggle Speech and Meeting Notes. They can be assigned through Shortcuts and, where iOS allows, to the Action Button.",
            "Run the ‘Talk to Jarvis’ shortcut.",
            "Open Shortcuts, find Jarvis actions, run Talk to Jarvis and verify the app opens and begins the local push-to-talk flow.",
            .frontendOnly, "button.programmable"
        ))

        // MARK: Security & advanced tools
        items.append(feature(
            "permissions", "Security & Advanced Tools", "Permission policy engine",
            "Separates read, local-write, external-write, destructive and security actions.",
            "Default policy auto-allows reads/local writes while external writes, destructive actions and security-sensitive actions require confirmation. Every agentic tool action is expected to pass through this policy rather than bypass it.",
            "Jarvis, what are my current permission policies?",
            "Jarvis should describe the configured policy classes and should not execute a protected write merely because it was requested conversationally.",
            .ready, "lock.shield.fill"
        ))
        items.append(feature(
            "sandbox", "Security & Advanced Tools", "Local Docker code/terminal sandbox",
            "Runs generated Python or terminal commands in a constrained disposable container.",
            "When Docker support is installed, generated code can run with no network, read-only filesystem, dropped capabilities, no-new-privileges, memory/CPU/PID limits and a hard timeout. This is intentionally not host PowerShell access.",
            "Jarvis, run a sandboxed Python command that prints 2 + 2.",
            "Jarvis should propose/use the isolated sandbox rather than claiming unrestricted host-shell access. Docker must be configured on the PC.",
            .optional, "shippingbox.fill"
        ))
        items.append(feature(
            "exact-command", "Security & Advanced Tools", "Exact spoken terminal confirmation",
            "Requires a specific voice phrase after reading the full proposed command.",
            "Security-class terminal execution reads the exact command aloud and requires ‘execute exact command’ rather than a generic yes/confirm. This reduces accidental authorization of unseen generated commands.",
            "Jarvis, run a sandboxed terminal command that prints ‘hello’.",
            "Jarvis should read the exact command and wait for the exact execution phrase before running it.",
            .optional, "terminal.fill"
        ))
        items.append(feature(
            "tool-synthesis", "Security & Advanced Tools", "Self-generated API tools",
            "Lets 27B create narrow API adapters, validate them and register them disabled.",
            "Generated adapters are tested in the isolated sandbox, restricted to declared HTTPS hosts, cannot embed authorization/cookie/API-key headers, and are stored disabled until an explicit security action enables them.",
            "Jarvis, list my custom API tools.",
            "The list should show registered dynamic tools and their enabled/disabled state. Creating a new one should not silently grant it execution privileges.",
            .optional, "hammer.fill"
        ))
        items.append(feature(
            "self-heal", "Security & Advanced Tools", "Custom-tool self-healing proposals",
            "Can draft and validate a repair when a generated API adapter fails structurally.",
            "The 27B model may propose a patch, test it in the sandbox and revalidate host/risk restrictions, but the repair is queued for approval rather than silently modifying itself.",
            "Jarvis, list custom tool repairs.",
            "If any repair proposal exists, Jarvis should show it without applying it. Applying a repair remains a protected security action.",
            .optional, "cross.case.fill"
        ))

        // MARK: Explicit boundaries
        items.append(feature(
            "no-notification-intercept", "Known Limits", "System-wide iPhone notification interception",
            "A normal companion app cannot arbitrarily read every other app’s notifications.",
            "Jarvis can prioritize its own companion/proactive events, but iOS does not grant it a general API to intercept and inspect all third-party notification contents.",
            "Not available as a general iOS capability.",
            "This is documented as a platform boundary rather than a feature to test.",
            .limited, "bell.slash.fill", runnable: false
        ))
        items.append(feature(
            "no-speaker-biometric", "Known Limits", "No biometric speaker identification",
            "Jarvis does not maintain voiceprints to identify people from their voices.",
            "Meeting capture can transcribe what is explicitly said, but it does not assign identity from a speaker’s biometric voice signature or infer psychological state from vocal acoustics.",
            "Not implemented by design.",
            "This is a privacy boundary rather than a testable feature.",
            .limited, "person.wave.2.fill", runnable: false
        ))
        items.append(feature(
            "no-stress", "Known Limits", "No vocal stress/emotion inference",
            "Jarvis does not label nearby people as stressed, deceptive, angry or afraid from their voice.",
            "Acoustic signals such as pitch/jitter are not used to make sensitive psychological inferences about other people. Content-level disfluencies can be described without assigning mental state.",
            "Not implemented by design.",
            "This is a privacy/safety boundary rather than a feature to test.",
            .limited, "waveform.slash"
        ))
        items.append(feature(
            "no-3d", "Known Limits", "No full 3D world model / indoor homing",
            "Current object memory is scene-based last-seen context, not safety-grade navigation.",
            "The ordinary Ray-Ban camera path does not provide a complete persistent 6DoF map suitable for dependable indoor homing. Jarvis therefore does not present monocular guesses as precise navigation.",
            "Not available in the current hardware/software stack.",
            "Use spatial last-seen memory for contextual recall, not physical navigation guarantees.",
            .limited, "cube.transparent"
        ))
        items.append(feature(
            "no-ide-buffer", "Known Limits", "No full live IDE-buffer awareness",
            "Jarvis knows foreground app/window context but does not continuously read arbitrary editor buffers.",
            "A proper VS Code/editor extension or explicit desktop bridge is still required for reliable continuous source-buffer access. A window title is not treated as document contents.",
            "Jarvis, what was I doing on my PC?",
            "Jarvis may report the active editor/window, but should not fabricate the contents of a file it has not actually read.",
            .limited, "chevron.left.forwardslash.chevron.right"
        ))

        return items
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
            let categoryMatches = selectedCategory == "All" || feature.category == selectedCategory
            let queryMatches = query.isEmpty || feature.searchableText.contains(query)
            return categoryMatches && queryMatches
        }
    }

    private var grouped: [(String, [JarvisFeature])] {
        let dictionary = Dictionary(grouping: filtered, by: \.category)
        return dictionary.keys.sorted().map { ($0, dictionary[$0] ?? []) }
    }

    var body: some View {
        List {
            Section {
                Picker("Category", selection: $selectedCategory) {
                    ForEach(categories, id: \.self) { category in
                        Text(category).tag(category)
                    }
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
                                        .frame(width: 26)
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
                    Image(systemName: feature.symbol)
                        .font(.largeTitle)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(feature.title).font(.title3.bold())
                        Label(feature.status.rawValue, systemImage: feature.status.icon)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Text(feature.summary)
                    .font(.headline)
            }

            Section("What it does") {
                Text(feature.details)
                    .textSelection(.enabled)
            }

            Section("How to verify it") {
                Text(feature.verification)
                    .textSelection(.enabled)
            }

            Section("Example prompt") {
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
                    Text("This example is intentionally not runnable from the guide because it contains a placeholder, can create an external side effect, or documents a capability boundary.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if feature.status == .pendingBackend {
                Section("Deployment note") {
                    Label("Do not count this capability as deployed yet. The necessary backend change exists in the repository but is still waiting for a Windows-server update and real-device verification.", systemImage: "clock.badge.exclamationmark")
                        .font(.callout)
                }
            }
        }
        .navigationTitle(feature.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}
