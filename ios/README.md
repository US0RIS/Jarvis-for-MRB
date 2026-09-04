# Jarvis iOS client

`JarvisIOS.xcodeproj` is a native SwiftUI iPhone app. It connects to the Jarvis backend, supports text and hands-free voice conversation, plays the local PC-generated Jarvis voice through the Ray-Bans, fires a `home_arrival` event from a Core Location geofence, and integrates Meta's Wearables Device Access Toolkit for registration, camera permission, and live Ray-Ban camera preview.

## Requirements

- macOS with Xcode
- iPhone running a current iOS release (deployment target is iOS 17+)
- Meta AI app on the iPhone
- compatible Meta AI glasses paired to Meta AI
- Developer Mode enabled for the glasses
- Apple developer signing team selected in Xcode
- Jarvis Windows backend reachable from the phone

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

On Windows:

```powershell
py -3.14 -m jarvis_mrb.remote_setup
```

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

## Hands-free voice

The app has:

- **Push to Talk** for explicit one-shot commands
- **Hands-free Jarvis** for a continuous conversation loop

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

Dictation-like commands use longer silence thresholds. Partial text can survive Apple Speech task restarts so email addresses, URLs, spelling, and long bodies are less likely to be truncated. The recognizer biases toward `Jarvis`, `Dubeck`, and `Emmett Dubeck`, and corrects common `Dubek` / `Du Beck` transcriptions to `Dubeck`.

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
