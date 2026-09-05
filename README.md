# Jarvis for MRB

A private, local-first personal agent that uses Ray-Ban Meta glasses as an always-available voice/vision interface while reasoning models, memory, tools, automation, and private data access run on the user's PC.

## Milestone 12 — Autonomous Context

The current stack includes:

- Ray-Ban Meta DAT live camera streaming and 1 FPS passive vision
- hands-free `Jarvis` wake/conversation loop, five-second follow-up window, and barge-in
- Qwen3 8B / Qwen3.8 27B speculative routing with thinking disabled
- Kokoro-82M low-latency local TTS
- adaptive low-volume/lower-pitch whisper playback based on measured ambient noise floor
- subtle thinking pulse plus distinct local audio HUD cues
- proactive calendar/email interruption monitor with selectable severity threshold
- persistent environment/personality state and decaying temporary session state
- long-term semantic episodic memory
- unified vector search across indexed Gmail, Calendar, local notes, and past conversations
- passive-vision spatial object sightings (`where did I last see my keys?`)
- asynchronous background worker queue
- autonomous DAG workflow execution with parallel read-only steps
- recurring jobs and scheduled daily audio briefings
- Serper web search with dynamic query refinement and short spoken synthesis
- Gmail, Contacts, Calendar, Windows app, Opera/Chromium and browser-tab tools
- optional Apple Health context for recent heart rate, HRV, and sleep
- home/mobile geofenced system profiles
- isolated Docker Python sandbox
- sandbox-generated, host-allowlisted custom API tool adapters
- automatic LAN → private Tailscale Serve failover

The model still does **not** receive unrestricted host shell access. External writes, destructive actions, sandbox execution, and dynamic-tool operations retain explicit permission barriers.

## Update Windows

```powershell
cd C:\Users\emmet\Jarvis-for-MRB
git pull
py -3.14 -m pip install -e .

Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess |
  ForEach-Object { Stop-Process -Id $_ -Force }

py -3.14 -m jarvis_mrb.service
```

`GET /health` should report `0.12.0`.

## Models

Planner:

```text
qwen3:8b       fast routine voice/tool routing
qwen3.8:27b    higher-capability reasoning and workflow planning
```

Both run through Ollama with `think: false`. Automatic routing keeps 8B resident for normal interaction and temporarily loads 27B for clearly heavier turns.

Supporting models:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-persistent-ai.ps1
```

```text
nomic-embed-text    episodic/unified-memory embeddings
moondream           passive vision
```

Voice:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-kokoro-tts-wsl.ps1
```

Kokoro runs locally in WSL on port 8880. Apple speech remains a fallback.

## Web search

Configure Serper once:

```powershell
py -3.14 -m jarvis_mrb.serper_setup
```

The key is stored under `%APPDATA%\JarvisForMRB`, not committed to GitHub or sent to the iPhone. Conversational search requests are optionally condensed by Qwen3 8B before Serper is called, then the evidence is synthesized into a short spoken answer rather than reading SERP snippets aloud.

## Proactive presence

A background monitor checks near-term calendar events and high-priority unread mail. Proactive messages carry `info`, `warning`, or `urgent` severity. The iPhone Settings screen controls the minimum severity that is allowed to interrupt with audio.

The companion WebSocket also carries thinking, warning, completion, error, vision, and other HUD-state events. The iPhone synthesizes these cues locally.

## Memory

Recent conversation:

```text
%APPDATA%\JarvisForMRB\conversation.sqlite3
```

Semantic episodic memory:

```text
%APPDATA%\JarvisForMRB\episodic_memory.sqlite3
```

Decaying temporary state:

```text
%APPDATA%\JarvisForMRB\ephemeral_state.json
```

Unified-index metadata:

```text
%APPDATA%\JarvisForMRB\knowledge_sources.sqlite3
```

Drop local text/Markdown/JSON/log notes to index into:

```text
%APPDATA%\JarvisForMRB\notes
```

The backend refreshes the cross-app index in the background. `knowledge.search` searches indexed mail, calendar, notes, and conversation episodes through the same embedding space.

## Passive vision and object memory

The iPhone sends one resized JPEG per second while passive vision is enabled. The PC drops new frames while Moondream is busy rather than building a queue.

Moondream produces:

- a compact scene summary
- a conservative list of visible portable objects
- an optional high-confidence proactive alert and severity

Object sightings are stored at:

```text
%APPDATA%\JarvisForMRB\spatial_memory.sqlite3
```

This is **last-seen scene/location memory**, not full 6DoF world mapping. A `Silent Visual Scan` button is also available in the iPhone app as the software trigger point for an on-demand scan.

Useful diagnostics:

```text
GET /vision/status
GET /spatial/status
GET /memory/status
GET /knowledge/status
```

## Autonomous workflows

`workflow.run` asks the 27B model to compile a goal into a validated DAG of explicit Jarvis tools. Independent read-only nodes can execute concurrently. Writes execute serially.

Every node still passes through the normal permission policy. A low-risk workflow can run without repeated prompts, while an external write or destructive node still stops for confirmation.

Long work can instead be placed on the persistent background queue, leaving the live voice channel free.

## Recurring briefings

Jarvis supports recurring daily, weekday, and weekly jobs. For example:

```text
Jarvis, give me my morning briefing every day at 7:30 AM.
```

The briefing combines near-term Calendar events, unread email, weather/news through Serper when configured, and active background work. When the scheduled job fires, the result is delivered over the companion channel and can be spoken through the glasses.

## Environment, profiles, and Apple Health

Durable state is stored at:

```text
%APPDATA%\JarvisForMRB\environment_state.json
```

The iPhone can switch between `home` and `mobile` profiles from the home geofence. The active profile modifies response style; it does not replace the permission system.

Optional HealthKit support reads recent:

- heart rate
- HRV
- sleep duration

Health data is sent only to the private Jarvis PC when the setting is enabled. Jarvis is explicitly instructed not to infer diagnoses, stress, or emotional state from biometric values.

## Adaptive whisper and quiet speech

The iPhone continuously estimates the acoustic noise floor while the wake-word recognizer is idle. With Adaptive Whisper enabled, quiet environments reduce TTS volume and apparent pitch/rate automatically.

`Quiet-speech mode` uses the existing acoustic Ray-Ban/iPhone microphone + Apple Speech path for very soft voiced speech. It is not literal EMG or thought/subvocal decoding; the current Ray-Ban Meta hardware does not provide that signal.

## Local code sandbox and synthesized API tools

The optional code sandbox requires Docker Desktop:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-sandbox.ps1
```

Generated Python is executed in `python:3.12-alpine` with:

- network disabled
- read-only filesystem
- dropped Linux capabilities
- `no-new-privileges`
- 256 MB memory limit
- one CPU
- process limit
- hard timeout

Dynamic API tool synthesis is intentionally narrower than unrestricted self-modifying code. Qwen3.8 27B may generate a small request-planning adapter, but that adapter is sandbox-tested, can target only explicitly allowlisted HTTPS hosts, cannot embed auth secrets, starts disabled, and requires a security-class confirmation before enabling/running.

## Tailscale

Do not expose port 8765 to the public Internet and do not enable Funnel.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-tailscale.ps1
```

Put the resulting private `https://...ts.net` Serve URL in **Jarvis → Settings → Tailscale URL**. The iPhone tries the LAN URL first and then Tailscale.

## iPhone build

Open:

```text
ios/JarvisIOS.xcodeproj
```

Then clean/build/install. Milestone 12 adds HealthKit entitlement/privacy metadata. With automatic signing, Xcode may ask the selected development team to provision the HealthKit capability the first time it is used.

Key Settings controls now include:

- Automatic 8B/27B model routing
- Passive vision
- Ambient audio HUD cues
- Proactive interruption threshold
- Geofenced system profiles
- Apple Watch / Health context
- Adaptive whisper threshold
- Quiet-speech mode
- email recipient allowlist

## Hardware/API limitation: glasses gestures

The `Silent Visual Scan` software action is implemented, but ordinary Ray-Ban Meta Device Access Toolkit currently exposes camera/audio rather than arbitrary developer-defined tap/head-nod callbacks. Do not fake a gesture binding in the app. If Meta exposes a suitable gesture event in a future DAT release, that event can call `requestSilentScan()` directly without changing the vision backend.

## Voice cloning

Milestone 12 keeps Kokoro because its latency is currently the right tradeoff for conversation. It does not clone an identifiable movie actor's voice. An optional user-owned/licensed/consented reference-voice engine can be added as a separate voice profile later without replacing the fast default.

## Default permission policy

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

Sandbox execution and dynamic custom tools are classified as `security`. Gmail and Calendar writes remain external writes. Gmail sending also retains the exact-recipient backend allowlist.
