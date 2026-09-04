# Jarvis for MRB

A personal agent designed to use Ray-Ban Meta glasses as an always-available voice/vision interface while the actual agent and tools run on trusted devices and services.

## Milestone 9

Jarvis now has the complete local glasses/voice loop plus persistent conversation, Gmail/Calendar tooling, recipient safety controls, streamed responses, and a local neural TTS voice.

Backend capabilities:

- local Ollama planner (`qwen3.8:27b` by default), with thinking explicitly disabled
- streamed non-tool conversational responses from Ollama instead of waiting for the complete answer
- deterministic fast paths for routine commands
- persistent per-session conversational history in SQLite
- the most recent 20 user/assistant messages are supplied to the planner on each non-trivial request
- contextual follow-ups such as `what about Friday?`, `close it`, or `email him that I'll be late`
- Windows app/process control
- Opera/Chromium tab discovery, focus, open, status, and close via CDP
- Gmail read/search and send
- exact backend-enforced email-recipient allowlist plus confirmation for outbound mail
- Google Contacts lookup
- general Google Calendar queries and event creation
- persistent scheduled/event-triggered jobs
- authenticated private-network API
- local Qwen3-TTS service with Apple TTS only as a fallback

Native iPhone client:

- standard `ios/JarvisIOS.xcodeproj`
- stable per-install conversation session ID
- streamed Last Response text
- sentence-level streaming speech: Jarvis starts speaking complete early clauses/sentences while later model output is still being produced
- Qwen3-TTS WAV playback through the Ray-Ban Bluetooth route
- full conversational barge-in: speech can interrupt both Qwen audio and Apple fallback TTS
- hands-free `Jarvis` interaction loop
- five-second post-response conversational listening window
- extended dictation handling for email addresses, URLs, spelling, and long message bodies
- personal speech vocabulary/correction for `Dubeck`
- explicit Bluetooth HFP input selection
- Core Location home geofence
- Meta Wearables DAT registration, camera access, live Ray-Ban camera streaming, and photo capture

The model never receives unrestricted shell access. It chooses among explicit tools.

## Update the Windows backend

```powershell
cd C:\Users\emmet\Jarvis-for-MRB
git pull
py -3.14 -m pip install -e .
```

After code updates, stop an old service if one is running:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

Then:

```powershell
py -3.14 -m jarvis_mrb.service
```

## Local neural TTS: Qwen3-TTS

The default runtime voice is:

```text
Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
speaker: Ryan
```

The 0.6B checkpoint is deliberate. The target PC has an RTX 5080 but also keeps a much larger Ollama planner warm. The smaller TTS checkpoint leaves substantially more VRAM headroom for simultaneous planner + TTS use while remaining a large quality improvement over iOS `AVSpeechSynthesizer`.

TTS is isolated in WSL/Python 3.10-3.12 rather than being installed into Jarvis's Windows Python 3.14 environment. Install it once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-qwen3-tts-wsl.ps1
```

The setup script:

- verifies the NVIDIA GPU is visible inside WSL
- creates a dedicated virtual environment
- installs a CUDA 12.8 PyTorch build suitable for RTX 50-series GPUs
- installs the local OpenAI-compatible Qwen3-TTS server
- downloads the 0.6B CustomVoice checkpoint ahead of time
- starts and warms the local service on `127.0.0.1:8880`

The normal Jarvis backend attempts to auto-start that WSL TTS service in the future. To run it manually in the foreground:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-qwen3-tts-wsl.ps1
```

Useful environment overrides:

```text
JARVIS_TTS_URL=http://127.0.0.1:8880
JARVIS_TTS_VOICE=Ryan
JARVIS_TTS_SPEED=1.0
JARVIS_TTS_INSTRUCT=<natural-language delivery instruction>
JARVIS_TTS_AUTOSTART=1
```

If the local TTS model is temporarily unavailable, the iPhone automatically falls back to Apple's installed voice so Jarvis does not become mute.

## Response streaming

The authenticated API now exposes:

```text
POST /command/stream
```

as newline-delimited JSON. For a conversational request, Qwen first emits a compact one-line tool decision. When no tool is needed, the answer immediately continues in the same Ollama stream and is forwarded to the iPhone incrementally.

The iPhone displays those deltas as they arrive. For speech, it accumulates only enough text to reach a natural sentence/clause boundary, asks local Qwen3-TTS for that segment, and starts playback while later language-model output continues arriving over the open HTTP response.

Tool calls intentionally remain atomic: Jarvis must know and execute the action before claiming the result. Fast deterministic actions also remain effectively immediate.

The CLI uses the same streamed endpoint, so longer conversational answers begin printing before generation completes.

## Example commands

```text
Open Spotify
Close Spotify
Is YouTube open?
List tabs

Read my latest email
What unread emails do I have?
Email alex@example.com saying I can talk later and do not use emojis
confirm

What was the most recent event on my calendar?
What's on my calendar tomorrow?
Create a calendar event called Dentist tomorrow at 3 PM
confirm

At 8 PM open Spotify
When I get home, make sure Minecraft is running
List jobs
```

Conversation context supports sequences such as:

```text
What's on my calendar Friday?
What about Saturday?
Which one is earlier?
```

or:

```text
Open Spotify.
[Jarvis responds]
Close it.
```

## Conversation memory

Every `/command` request may include a `session_id`. Jarvis stores conversation turns under that session in:

```text
%APPDATA%\JarvisForMRB\conversation.sqlite3
```

The iPhone creates one stable random session ID and reuses it. The backend retains up to 200 messages per session and sends the most recent 20 messages to Qwen when contextual reasoning is required.

Background scheduled jobs do not share the live conversation session.

## Google setup

Jarvis uses Gmail API, People API, and Google Calendar API. Credentials/tokens live outside the repository under:

```text
%APPDATA%\JarvisForMRB
```

Authenticate with:

```powershell
py -3.14 -m jarvis_mrb.google_auth
```

Gmail reading is read-only. Outbound Gmail/Calendar writes are protected actions and require confirmation by default. Gmail send additionally checks the exact recipient against the backend allowlist immediately before the Gmail API call.

## Opera browser control

Fully quit Opera, then run:

```powershell
py -3.14 -m jarvis_mrb.browser_setup
```

This starts Opera with Chromium DevTools enabled so Jarvis can work with individual browser tabs rather than killing the whole browser.

## Connect the iPhone

Configure a private-network API token on the Windows PC:

```powershell
py -3.14 -m jarvis_mrb.remote_setup
```

This writes `%APPDATA%\JarvisForMRB\server.json`, generates a bearer token, and prints possible private LAN URLs for the iPhone.

Do **not** forward port `8765` from the router to the public Internet. For away-from-home access, use a private tunnel such as Tailscale.

Then open on a Mac:

```text
ios/JarvisIOS.xcodeproj
```

Let Xcode resolve the Meta Wearables package, select the Apple development team, connect the iPhone, and run the `JarvisIOS` target. Enter the server URL and token in Settings.

## Meta Ray-Ban integration

The iOS project links Meta's Wearables Device Access Toolkit components:

```text
MWDATCore
MWDATCamera
```

The development configuration uses URL scheme `jarvismrb://` and Meta App ID `0` for Developer Mode.

In the app:

1. **Register** through Meta AI.
2. **Camera Access** and approve permission.
3. Wait for an eligible DAT device.
4. **Start Camera** for the live glasses feed.

## Hands-free voice

Enable **Hands-free Jarvis**. The app prefers an available Bluetooth HFP microphone and routes output back to the matching hands-free device.

Start with:

```text
Jarvis, what's on my calendar Friday?
```

or:

```text
Jarvis.
```

Jarvis replies `Yes, sir?` and listens for the command.

After every normal response it listens for five seconds without requiring the wake word. If speech begins inside that window, the entire utterance becomes the next turn even if it extends past five seconds.

While Jarvis is talking, a second recognizer provides barge-in. Saying `wait`, `stop`, `actually ...`, or simply starting a new sentence causes the active audio playback to stop and hands the interruption into the normal conversation loop. Echo filtering reduces the chance that Jarvis's own speaker output triggers this path.

## Permission policy

Defaults:

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

## Architecture

```text
Ray-Ban Meta
  camera via Meta DAT
  microphone/speakers via Bluetooth HFP
        |
        v
Native Jarvis iPhone app
  wake/conversation/STT
  streamed response text
  Qwen audio playback + barge-in
  camera / geofence
        |
        v
Authenticated Jarvis API :8765
        |
        +-- streamed Qwen planner via Ollama
        +-- Qwen3-TTS proxy -> WSL :8880 -> RTX 5080
        +-- persistent conversation history
        +-- Windows PC / Opera tools
        +-- Gmail / Contacts / Calendar
        +-- persistent jobs
```

## Remaining major work

1. Tune Qwen3-TTS voice/instruction parameters on the physical Ray-Bans; optionally move from Ryan to a designed/cloned custom Jarvis voice.
2. Move sentence-level TTS to true PCM audio streaming if first-audio latency still needs to fall further.
3. Validate screen-locked/background voice behavior for long sessions.
4. Replace continuous Apple Speech wake detection with a dedicated low-power local keyword spotter if all-day use requires it.
5. Add vision requests that send camera frames/photos to a multimodal model.
6. Add Tailscale/private remote connectivity for away-from-home use.
7. Add longer-term semantic memory beyond the current durable short-term window.
