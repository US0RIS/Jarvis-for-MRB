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
2.3 seconds with no new recognition update; **Stop & Send** remains available
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
