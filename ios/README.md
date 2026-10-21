# Jarvis iOS client

`JarvisIOS.xcodeproj` is a native SwiftUI iPhone app. It connects to the Jarvis backend, supports text and hands-free voice conversation, plays the local PC-generated Jarvis voice through the Ray-Bans, fires a `home_arrival` event from a Core Location geofence, and integrates Meta's Wearables Device Access Toolkit for registration, camera permission, and live Ray-Ban camera preview.

## Requirements

- macOS with Xcode
- iPhone running a current iOS release (deployment target is iOS 17+)
- Apple developer signing team selected in Xcode
- Horus Windows backend reachable from the phone for backend commands
- Optional: paired AirPods / Bluetooth headset for hands-free audio output
- Optional: Meta AI, compatible Meta glasses and Developer Mode **only** for Meta camera features

The Xcode project includes Meta Wearables DAT through Swift Package Manager:

- package: `https://github.com/facebook/meta-wearables-dat-ios`
- minimum version: `0.9.0`
- products: `MWDATCore`, `MWDATCamera`

## Open the project

```text
ios/JarvisIOS.xcodeproj
```

Allow Xcode to resolve Swift packages. Select the `JarvisIOS` target, choose the Apple development team under **Signing & Capabilities**, connect the iPhone, and run the physical-device target.

## Connect to the Windows service

On Windows, run `setup_horus.cmd` at the repository root for an isolated
Python environment and guided private-network setup. For an existing Python
installation, `py -3.14 -m jarvis_mrb.remote_setup` remains available;
rerunning it now **reuses** the saved token, while `--rotate` deliberately
invalidates existing iPhone credentials.

In iPhone Settings enter:

- **Base URL:** the PC private URL printed by `remote_setup`
- **API token:** the generated bearer token

Do not expose port `8765` directly to the public Internet. Use a private tunnel such as Tailscale for away-from-home access.

## Streamed responses and local TTS

Milestone 9 no longer waits for the full language-model answer before updating/responding.

The phone calls:

```text
POST /command/stream
```

and receives newline-delimited response deltas. `Last Response` updates while Qwen is still generating. The app collects only enough generated text to form a natural sentence/clause, then calls:

```text
POST /tts
```

for a locally generated Qwen3-TTS WAV and immediately plays it through the selected Bluetooth HFP output. Later LLM output continues travelling over the still-open response stream while the early audio is being synthesized and played.

The normal PC runtime is `Qwen3-TTS-12Hz-0.6B-CustomVoice`, speaker `Ryan`, with a restrained personal-aide instruction. Apple `AVSpeechSynthesizer` remains an automatic fallback if the PC TTS service is unavailable.

Tool operations remain atomic: the client cannot truthfully speak a tool result until the backend has performed the action/read. Conversational no-tool responses receive the largest first-response latency improvement.

## Barge-in

Both Qwen WAV playback and Apple fallback speech run with a simultaneous interruption recognizer. If the wearer starts talking over Jarvis, playback stops and the heard interruption is handed to the normal conversation recognizer.

Examples:

```text
Jarvis: Sir, there are several things to consider—
You: Actually, just give me the important one.
```

or simply:

```text
Stop.
Wait.
Hold on.
```

A text-overlap filter plus iOS `voiceChat` echo cancellation reduces self-interruption from the Ray-Ban speakers.

## Conversation identity and memory

The iPhone creates a stable random conversation session ID and sends it with every command. The backend persists the dialogue in SQLite and supplies the most recent 20 user/assistant messages to Qwen when contextual reasoning is required.

That enables:

```text
You: What's on my calendar Friday?
Jarvis: ...
You: What about Saturday?
```

and:

```text
You: Open Spotify.
Jarvis: ...
You: Close it.
```

## Privacy-first voice and iPhone Action Button

**Push to Talk is the default.** The app does not require an idle wake-word
recognizer. Tap **Push to Talk**, speak, and the command is sent after about
1.2 seconds without new recognition updates for short commands (2.3 seconds
otherwise, longer for dictation-like text); **Stop & Send** remains available
for dictation, and **Cancel** discards an unfinished capture. If no speech is
detected, the microphone is closed after 15 seconds.

On an iPhone with an Action Button:

1. Install and open Horus once, and grant microphone/speech permissions when requested.
2. In **iOS Settings → Action Button → Shortcut**, select **Talk to Horus**.
3. Press the Action Button and speak. The shortcut opens Horus and requests
   a single capture session; it does **not** toggle an active capture off.

On other iPhones, add **Talk to Horus** in the Shortcuts app and invoke it using
a supported shortcut surface. A third-party app cannot provide Siri's
privileged indicator-free always-on iOS wake word. While Horus is capturing
or running separately opted-in Meeting Notes / Room Listening, the normal iOS
microphone indicator can appear.

**Always-listening wake mode is optional** and keeps microphone recognition
active while enabled. Separately opted-in ambient sound features can also
use the microphone while foregrounded. They are not silently enabled by
Push to Talk.

## Instant Earpiece flow (AirPods-first)

Horus is designed to be used from ordinary AirPods or Bluetooth headphones and
an iPhone, without a camera or glasses. The earpiece flow is one explicit,
foreground, bounded interaction:

1. **One action.** The Action Button / Siri / Shortcuts **Talk to Horus** intent
   posts a single "talk" request; the app opens the microphone once, plays a
   short rising `listening_start` cue and shows **Listening**. It never toggles
   an active capture off and never records by itself.
2. **Audio session.** `playAndRecord` + `voiceChat`, with `allowBluetoothHFP`
   (headset microphone) and `allowBluetoothA2DP` (so replies still reach the
   earbuds when the iPhone microphone is chosen). "Prefer Bluetooth microphone"
   selects the HFP input; turning it off selects the iPhone microphone.
3. **States.** One status is always visible: Idle (microphone off) / Listening /
   Thinking / Speaking, with a single **Stop** button that drops the in-flight
   response, silences speech and closes the microphone.
4. **Microphone release.** After the utterance, on Cancel/Stop, or when Horus
   leaves the foreground, the recognizer stops its `AVAudioEngine`, removes the
   input tap, plays a falling `listening_end` cue and deactivates the audio
   session with `.notifyOthersOnDeactivation`. The session is also released
   shortly after Horus goes idle so the AirPods are not kept in call-quality
   (HFP) mode. If iOS refuses deactivation because other audio is running, the
   session simply stays up until that audio ends.
5. **Headphones disconnected.** On `AVAudioSession.routeChangeNotification` with
   reason `.oldDeviceUnavailable` and no remaining headphone/Bluetooth output,
   Horus stops speaking immediately, closes any capture, refuses further speech
   and cues, and shows why. Replies remain on screen. Speech resumes when a
   headphone/Bluetooth route returns, or if you tap **Speak on iPhone speaker
   instead**. Private speech does not move to the loudspeaker on its own.
6. **Interruptions.** A call, Siri or another app taking the audio session stops
   speech and capture and leaves Horus idle with a message; the microphone is
   not reopened automatically. After a media-services reset the audio engines
   are rebuilt.
7. **Permissions.** If speech recognition or microphone access is denied or
   restricted, Horus shows the reason with an **Open iOS Settings** button and
   the typed command field keeps working (typed turns use `channel: "text"`).

### Interruptible conversation

- **Stop commands.** Saying (or typing) "stop", "cancel", "never mind" or "be
  quiet" while Horus is speaking or thinking silences it, aborts the request
  and drops any late answer. A cancel said over a confirmation prompt is still
  forwarded to the backend so the pending action is really cancelled. Aborting
  a request cannot undo something the server already did; the status says so.
- **Turn generation.** Every new turn, Stop, or Action Button press bumps a
  monotonic turn id. Streaming text, synthesized audio and local results from an
  older id are discarded instead of being spoken.
- **Barge-in.** While Horus speaks, a second recognizer listens only if the
  output is on a private route (free speech and stop commands) or the session is
  in echo-cancelling `voiceChat` mode on the loudspeaker (stop commands only).
  Free-form interruptions need at least 3 words, or 2 words persisting for
  0.35 s; text matching the answer being spoken is ignored as echo. A real
  interruption becomes the next turn without restarting the experience.
- **Backend context.** Every `/command` and `/command/stream` call sends the
  same `session_id` plus `context.channel`: `voice` (push to talk), `conversation`
  (follow-up window) or `text`. `latitude`, `longitude`, `location_accuracy_m` and
  `location_captured_at` (ISO-8601 with timezone) are added only when location
  access is already authorized, **Motion / travel context and GPS** is enabled and
  a cached fix is at most 10 minutes old; no location request is ever started
  for a command.
- **Conversation mode (optional, off by default).** Settings or the Voice card
  toggle. After a spoken answer to a *spoken* request finishes, the microphone
  opens once for an 8 second follow-up window with a visible countdown, a cue
  and the normal iOS microphone indicator. It closes after 8 silent seconds, on
  Stop, if the toggle is turned off, after 12 chained windows, or as soon as the
  app is not active. It does not run in the background and not in hands-free
  wake mode. Speech that matches Horus's own last answer is dropped as echo.

`Info.plist` background modes are unchanged (`audio`, `bluetooth-peripheral`,
`external-accessory`, `location`); the earpiece flow adds none and never starts
capture while the app is in the background.

### Not device-verified

All of the above is covered only by compile-time review and static source tests
(`tests/test_earpiece_ios_wiring.py`). It has **not** been run on hardware:

- Real AirPods / Bluetooth HFP routing: input/output switching, the
  A2DP-plus-iPhone-microphone combination, and the ~100-300 ms notification
  delay before speech stops after a disconnect.
- Barge-in echo behavior: whether `voiceChat` mode actually removes Horus's own
  voice on the loudspeaker or AirPods microphone, and the false-interruption
  rate of the word-count / duration / text-match guards.
- The Action Button on hardware, cold-start latency from press to microphone
  open, and Siri / Shortcuts delivery while the app is already foregrounded.
- End-to-end latency: the shortened ~1.2 s end-of-speech window for short commands (it may cut off slow talkers; dictation-like text keeps 2.3 s+), speech end to first spoken word, stop-to-silence time and
  battery/CPU cost of the barge-in recognizer.
- Interruption recovery for real calls, Siri, other apps' audio and media-services
  resets; deactivation failing while other audio runs.
- Permission-denied paths (Settings round trip) and the conversation-mode
  window under real use.

## Hands-free voice

The app has:

- **Push to Talk** for explicit one-shot commands (default)
- **Hands-free Jarvis** for an optional continuous conversation loop

Hands-free mode uses an iOS `playAndRecord` / `voiceChat` session and explicitly prefers an available Bluetooth HFP microphone. With the Ray-Bans exposed as an HFP input, Jarvis selects them and routes playback back to the matching hands-free output.

Start with:

```text
Jarvis, open Spotify.
```

or:

```text
Jarvis.
```

Jarvis replies `Yes, sir?` and treats the next utterance as the command.

After every normal response, Jarvis listens for five seconds. Speech that *starts* during that window becomes a follow-up without saying `Jarvis` again; it is not cut off merely because the five-second deadline passes after the user has begun talking.

Dictation-like commands use longer silence thresholds. Partial text can survive Apple Speech task restarts so email addresses, URLs, spelling, and long bodies are less likely to be truncated. The recognizer biases toward `Horus`, `Dubeck`, and `Emmett Dubeck`, and corrects common `Dubek` / `Du Beck` transcriptions to `Dubeck`.

Protected actions keep the confirmation barrier and get a longer confirmation window so `confirm` or `cancel` can be spoken without another wake word.

## Email safety

Settings includes an **Email Safety** section. The user manages an exact recipient allowlist there. The list is stored/enforced on the PC backend, after contact-name resolution and immediately before Gmail send. An empty list blocks all outbound email.

## Home arrival

Set home latitude, longitude, and radius under Settings, then enable Home Arrival Automation. iOS region monitoring posts:

```json
{"event":"home_arrival"}
```

to the backend.

## Meta Ray-Ban setup

The app configures Meta Wearables DAT with development `MetaAppID` `0` and URL scheme `jarvismrb://`.

1. **Register** through Meta AI.
2. **Camera Access** and approve permission.
3. Wait for **DAT eligible: Yes**.
4. **Start Camera** for the live glasses feed.

The app keeps one `AutoDeviceSelector` alive from initialization so device eligibility is populated before camera-session creation. Camera listener tokens are retained until the stream stops.

## Current architecture

```text
Ray-Ban Meta
  Meta DAT camera
  Bluetooth HFP microphone/speakers
        |
        v
Jarvis iPhone client
  STT / wake / conversation
  streamed text UI
  Qwen WAV playback + barge-in
  geofence / live camera
        |
        v
Authenticated Jarvis API
        |
        +-- streaming Ollama planner
        +-- Qwen3-TTS service on PC/WSL GPU
        +-- persistent conversation
        +-- Windows / Opera tools
        +-- Gmail / Contacts / Calendar
        +-- persistent jobs
```

## BYOK and Callless on iOS

iPhone Settings now exposes backend local/hosted inference provider selection.
A new API key must travel over HTTPS, or be entered on the Windows PC in
the Horus .exe setup window; the key stays in Windows Credential Manager.

Settings provides a shared Callless hub URL and **Open Callless** button.
Both users need accounts on the same hub and a mutual contact invitation.
WebRTC peer media uses encrypted DTLS-SRTP, with no audio stored at the hub.
Saying `get me to alex` opens the Callless web UI with that contact selected.
Browser recipients must still tap Join for microphone access; HTTPS (outside
localhost), a TURN relay in some networks and a foreground browser are
required. Native CallKit, APNs wakeup, background pickup and federation
are not yet implemented.
