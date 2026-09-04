# Jarvis for MRB

A private, local-first personal agent that uses Ray-Ban Meta glasses as an always-available voice/vision interface while the reasoning models, memory, tools, and automation run on the user's PC.

## Milestone 11 — Persistent Presence

Jarvis now goes beyond a request/response voice tool. The current stack includes:

- Ray-Ban Meta DAT camera access and live stream
- hands-free `Jarvis` wake/conversation loop with five-second follow-up listening
- barge-in while Jarvis is speaking
- streamed LLM responses
- Kokoro-82M local neural TTS
- Qwen3 8B and Qwen3.8 27B planner modes, with thinking disabled
- automatic speculative 8B → 27B routing
- persistent short-term conversation history plus long-term semantic episodic memory
- passive glasses-camera sampling and local vision analysis
- persistent environmental state
- background worker queue with completion notifications
- local ambient audio cues
- Gmail read/send, Google Contacts, Calendar, browser and Windows tools
- backend-enforced email recipient allowlist and confirmation barriers
- home geofence and persistent jobs
- automatic LAN → Tailscale failover for away-from-home access

The language model never receives unrestricted shell access. It can only use explicit tools with the configured permission policy.

## Update the Windows backend

```powershell
cd C:\Users\emmet\Jarvis-for-MRB
git pull
py -3.14 -m pip install -e .
```

Stop an old service if one is running, then start milestone 11:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess |
  ForEach-Object { Stop-Process -Id $_ -Force }

py -3.14 -m jarvis_mrb.service
```

`GET /health` should report version `0.11.0`.

## Local models

### Planner

Jarvis supports:

```text
qwen3:8b       low-latency planner
qwen3.8:27b    higher-capability planner
```

Both run through Ollama with thinking explicitly disabled.

With **Automatic model routing** enabled, Jarvis uses 8B for routine conversation/status/tool-routing turns and sends requests with strong complex-reasoning signals to 27B. A 27B route can emit a brief spoken status such as `Analyzing that now, sir.` before the heavier model finishes loading/generating.

Manual 8B/27B selection remains available in the iPhone Settings screen when automatic routing is disabled.

### Voice

The normal voice is **Kokoro-82M**, running locally in WSL on port `8880`. It replaced Qwen3-TTS because conversational latency matters more than maximum standalone TTS quality for this project.

One-time setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-kokoro-tts-wsl.ps1
```

Apple speech remains a fallback if the local TTS service is unavailable.

### Episodic memory + passive vision

Install the small supporting Ollama models once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-persistent-ai.ps1
```

This installs/pulls:

```text
nomic-embed-text    semantic episodic-memory embeddings
moondream           lightweight passive-vision model
```

Passive vision defaults to **zero GPU layers** so it does not displace Qwen/Kokoro from the RTX 5080. The iPhone can send one sampled low-resolution JPEG per second, but the server deliberately drops frames while the vision worker is busy instead of building a latency backlog.

## Long-term episodic memory

Conversation turns are still stored in the short-term session database:

```text
%APPDATA%\JarvisForMRB\conversation.sqlite3
```

In addition, completed conversational exchanges and useful visual observations are embedded with `nomic-embed-text` and stored locally in:

```text
%APPDATA%\JarvisForMRB\episodic_memory.sqlite3
```

Before a request is planned, Jarvis retrieves the top three semantically relevant past episodes and injects them as context. This makes references to older discussions possible without placing the entire conversation archive into every prompt.

Useful diagnostic:

```text
GET /memory/status
```

## Passive vision

Enable **Settings → Persistent Presence → Passive vision** in the iPhone app.

The flow is:

```text
Ray-Ban DAT camera
    ↓
current live frame
    ↓ 1 low-res JPEG / second
private companion WebSocket
    ↓
Jarvis PC
    ↓
Moondream visual worker
    ↓
scene state + optional high-confidence proactive alert
```

The server only produces unsolicited alerts when the local vision model reports something immediately useful with high confidence. Frames are not written to the episodic database; only compact scene summaries may be remembered. Visual text is treated as untrusted content, not agent instructions.

Diagnostic:

```text
GET /vision/status
```

## Persistent environmental state

Jarvis stores durable ambient context at:

```text
%APPDATA%\JarvisForMRB\environment_state.json
```

Current state can include:

- home/away location state
- current project focus
- Ray-Ban/phone transport state
- passive-vision state
- user interaction preferences
- last useful visual scene summary

This compact state is appended to the system context on every model request so routine conversations need less setup.

## Background worker queue

Jarvis can move longer work off the live voice turn. Background tasks are persisted in:

```text
%APPDATA%\JarvisForMRB\background_tasks.sqlite3
```

The live assistant can start a task, remain available for conversation, and receive a completion/failure event over the companion WebSocket. The iPhone can play a local cue and optionally speak the result through the glasses.

Examples:

```text
Work on that analysis in the background and tell me when it's done.
What are you working on?
Cancel background task 3.
```

The worker queue uses explicit Jarvis tools and the 27B planner for heavy work; it is not unrestricted shell execution.

## Ambient audio cues

The iPhone generates small local cues for states such as:

- task started
- task completed
- attention/proactive observation
- warning
- error

No cloud audio or asset download is required. Cues can be disabled independently in Settings.

## Away-from-home access with Tailscale

Do **not** expose Jarvis directly to the public Internet and do not forward router port `8765`.

Instead, run once on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-tailscale.ps1
```

The setup uses **Tailscale Serve**, not Funnel. It publishes the local Jarvis service only inside your tailnet over a stable `https://...ts.net` URL. Tailscale Serve automatically terminates HTTPS and proxies to local port 8765.

Install Tailscale on the iPhone and sign into the same tailnet. Then put the HTTPS URL printed by the setup script into:

```text
Jarvis → Settings → Tailscale URL
```

Keep the existing home URL, for example:

```text
http://192.168.1.19:8765
```

The iPhone now resolves endpoints automatically:

```text
home LAN reachable?  → use LAN
otherwise            → use private Tailscale HTTPS
```

The working endpoint is cached briefly, so leaving/returning home does not require manually changing Settings.

## Response streaming

`POST /command/stream` returns newline-delimited JSON. The chosen planner emits a compact tool decision first; conversational text then streams incrementally.

The iPhone displays text as it arrives and sends complete early clauses/sentences to Kokoro while later model output continues generating. This keeps TTS prosody natural without waiting for the complete LLM answer.

Tool results remain atomic because Jarvis must execute an action before claiming it succeeded.

## Companion WebSocket

The authenticated endpoint:

```text
/ws/companion
```

carries persistent low-bandwidth state in both directions:

- iPhone → PC: sampled vision frames and environmental state
- PC → iPhone: proactive alerts, worker-completion notifications, ambient-cue events

The same bearer token used by the normal Jarvis API is required.

## Google setup

Credentials/tokens remain outside the repository under:

```text
%APPDATA%\JarvisForMRB
```

Authenticate with:

```powershell
py -3.14 -m jarvis_mrb.google_auth
```

Gmail reading is read-only. Outbound Gmail/Calendar writes require confirmation by default. Gmail sending additionally checks the final resolved email address against the backend allowlist immediately before sending.

## Opera browser control

Fully quit Opera, then run:

```powershell
py -3.14 -m jarvis_mrb.browser_setup
```

This starts Opera with local Chromium DevTools access so Jarvis can work with individual browser tabs.

## iPhone build

Open:

```text
ios/JarvisIOS.xcodeproj
```

Let Xcode resolve Meta Wearables DAT, select the Apple development team, connect the iPhone, clean, and run the `JarvisIOS` target.

The Settings screen now includes:

- Home / LAN URL
- Tailscale URL
- Automatic model routing
- manual 8B/27B mode
- passive vision
- ambient cues
- proactive announcements
- project focus
- Kokoro status
- email recipient allowlist
- home geofence

## Hands-free conversation

Enable **Hands-free Jarvis** and say:

```text
Jarvis, what's on my calendar Friday?
```

or simply:

```text
Jarvis.
```

Jarvis answers `Yes, sir?` and listens for the next utterance. After a normal response, there is a five-second conversational follow-up window in which the wake word is not required.

Barge-in stays active while Kokoro or Apple fallback speech is playing. Interruptions such as `wait`, `actually...`, or a new sentence stop the current output and become the next conversational turn.

## Personality

The system prompt is now designed around a restrained J.A.R.V.I.S.-inspired operating style rather than a generic LLM persona: calm, technically competent, conversational, respectful, dry when appropriate, willing to challenge a weak assumption, and proactive only when confidence and utility justify an interruption.

It does not reproduce copyrighted movie dialogue or scripts; it implements the behavioral characteristics needed for the interaction style.

## Permission policy

Defaults remain:

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

Background-task creation and state updates are local writes. Background cancellation is destructive. Gmail/Calendar writes keep their existing confirmation controls.

## Architecture

```text
Ray-Ban Meta
  camera via Meta DAT
  microphone/speakers via Bluetooth HFP
        |
        v
Native Jarvis iPhone app
  wake + conversation STT
  LAN/Tailscale endpoint failover
  companion WebSocket
  1 fps passive vision sampler
  streamed response text
  Kokoro audio playback + barge-in
  ambient cues / proactive announcements
        |
        v
Authenticated Jarvis API :8765
        |
        +-- speculative router
        |     +-- Qwen3 8B for routine turns
        |     +-- Qwen3.8 27B for hard turns
        |
        +-- Kokoro-82M TTS -> WSL :8880
        +-- recent conversation SQLite
        +-- episodic semantic memory + nomic-embed-text
        +-- Moondream passive-vision worker
        +-- environmental state graph
        +-- background worker queue
        +-- Windows / Opera tools
        +-- Gmail / Contacts / Calendar
        +-- scheduled/event jobs
```

## Remaining hardening work

- validate all-day/background operation under screen lock and iOS power management
- benchmark passive-vision CPU cadence and optionally dedicate GPU headroom if worthwhile
- add richer multi-step research/code worker toolchains to the background queue
- session-scope pending confirmation state for simultaneous clients
- add PC wake/recovery strategy so remote Jarvis remains available when Windows sleeps
