# Jarvis for MRB

A private, local-first personal agent that uses Ray-Ban Meta glasses as an always-available voice/vision interface while reasoning models, memory, tools, automation, and private data access run on the user's PC.

## Milestone 13 — Contextual Perception

The current stack includes:

- Ray-Ban Meta DAT live camera streaming and passive vision
- hands-free `Jarvis` wake/conversation loop, five-second follow-up window, and barge-in
- Qwen3 8B / Qwen3.8 27B speculative routing with thinking disabled
- Kokoro-82M low-latency local TTS
- adaptive whisper playback and local audio HUD cues
- automatic LAN → private Tailscale Serve failover
- adaptive remote vision bandwidth throttling
- 30-second **RAM-only** rolling visual frame history
- on-demand visual-history questions such as `what did that passing sign say?`
- OCR-style visible-text extraction directly to the Windows clipboard
- conservative proactive physical/terminal hazard alerts from visible evidence
- spatial last-seen object memory
- proactive calendar/email interruption monitor with severity thresholds
- predictive 8B + local-context prewarming shortly before calendar events
- active-PC application/window/browser context handoff
- CPU/RAM/GPU/VRAM/thermal/background-queue guardrail monitoring
- optional smart Windows output-volume damping during active Jarvis conversations
- explicit opt-in meeting transcription with local action-item extraction
- local metric-contradiction checks during an explicitly active meeting-note session
- structured receipt/invoice extraction to local SQLite + CSV expense records
- automatic or on-demand local Markdown daily journal generation
- calendar conflict detection with proposed alternative times
- long-term semantic episodic memory and decaying temporary state
- unified vector search across indexed Gmail, Calendar, local notes, and past conversations
- asynchronous background worker queue
- autonomous DAG workflow execution with parallel read-only steps
- recurring jobs and scheduled briefings
- Serper web search with dynamic query refinement and short spoken synthesis
- Gmail, Contacts, Calendar, Windows app, Opera/Chromium and browser-tab tools
- optional Apple Health context for recent heart rate, HRV, and sleep
- home/mobile geofenced system profiles
- isolated Docker Python/terminal sandbox
- sandbox-generated, host-allowlisted custom API tool adapters
- automatic sandbox-validated **repair proposals** for structurally broken custom API adapters

The language model still receives **no unrestricted Windows host shell**. External writes, destructive actions, Docker execution, dynamic-tool operations, and repair application retain explicit permission barriers.

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

`GET /health` should report `0.13.0`.

No additional Ollama models are required beyond the existing setup. `pip install -e .` now also installs `pycaw`/`comtypes` for optional Windows audio damping.

## Planner, voice, vision, and memory models

```text
qwen3:8b           fast routine voice/tool routing
qwen3.8:27b        higher-capability reasoning/workflow/repair planning
nomic-embed-text   episodic/unified-memory embeddings
moondream          passive vision + recent-frame analysis
Kokoro-82M         low-latency local neural TTS
```

Both planner models run with `think: false`.

Supporting-model setup, if not already done:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-persistent-ai.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\setup-kokoro-tts-wsl.ps1
```

## 30-second visual history

Every valid sampled glasses frame enters a strictly in-memory rolling cache. Frames expire after 30 seconds and are not written to the episodic database.

Examples:

```text
Jarvis, what did that sign say?
Jarvis, what was I just looking at?
Jarvis, copy that error code to my clipboard.
Jarvis, copy the serial number I'm looking at to my clipboard.
```

The clipboard action extracts clearly legible text from recent frames and writes only the resulting text to the Windows clipboard.

Useful diagnostics:

```text
GET /vision/status
GET /visual-history/status
GET /spatial/status
```

## Passive hazard monitoring

Moondream is instructed to alert only on directly visible, high-confidence evidence such as:

- obvious open flame/hot-tool situations
- visibly running/spilling liquid
- clear trip/impact hazards
- visibly open/ajar access points when immediately relevant
- clearly legible local terminal/application errors

It must not infer hidden states. In particular, Jarvis does **not** claim that a closed door is unlocked, that a present appliance is dangerous, or that a hazard exists when the image does not support it. This is assistive context, not a safety-certified hazard detector.

## Cross-device PC context

A lightweight Windows monitor records the current foreground process/window title plus available browser-tab context into the private environment state every few seconds. This supports questions such as:

```text
Jarvis, what was I doing on my PC?
Jarvis, what's on my PC right now?
```

Jarvis does not claim to have read the complete contents of an open document unless a dedicated content-reading tool actually supplied those contents.

## System resource guardrails

Jarvis monitors:

- CPU utilization
- system RAM
- NVIDIA GPU utilization
- VRAM usage
- NVIDIA GPU temperature
- background worker backlog

High-confidence threshold breaches can generate proactive warning events. Ask directly with:

```text
Jarvis, GPU status.
Jarvis, how is the PC doing?
```

Diagnostic:

```text
GET /resources/status
```

## Smart PC audio damping

With **Smart PC audio damping** enabled in iPhone Settings, the companion reports whether a Jarvis conversation is actually active. The Windows backend temporarily reduces master output volume and restores the previous level after the conversation.

This does not mute arbitrary smart speakers or cloud speakers; it currently controls the Windows audio endpoint only.

Diagnostic:

```text
GET /audio-damping/status
```

## Explicit meeting notes + local fact checking

The iPhone app now has a visible **Meeting Notes** card.

Starting it:

1. suspends the normal wake-word loop so there is only one microphone consumer;
2. starts a clearly visible local transcription session;
3. sends transcript chunks to the authenticated Jarvis PC;
4. rotates the Apple Speech task periodically so long meetings do not depend on one endless recognition task;
5. extracts explicit commitments/action items when you press **Stop & Extract Actions**.

During an explicitly active meeting-note session, transcript chunks containing concrete numeric/metric claims may be checked against the user's local unified index. Jarvis only reports a **possible contradiction** when local evidence directly conflicts; it does not treat the local index as infallible truth.

Meeting capture does **not** identify people by voiceprint and does not infer stress, tension, deception, emotion, or other sensitive traits from voices.

Use meeting recording only where permitted and with appropriate participant notice/consent.

## Expenses

With passive vision/camera context available:

```text
Jarvis, log this receipt.
Jarvis, show my recent expenses.
Jarvis, export my expenses.
```

Local storage:

```text
%APPDATA%\JarvisForMRB\expenses.sqlite3
%APPDATA%\JarvisForMRB\expenses.csv
```

The vision model is instructed not to guess unreadable merchant names, dates, totals, tax, tips, or line items.

## Daily journal

Enable **Automatic local daily journal** in iPhone Settings or generate one on demand:

```text
Jarvis, write today's journal.
```

Entries are stored locally under:

```text
%APPDATA%\JarvisForMRB\journal\YYYY-MM-DD.md
```

The journal can summarize local Jarvis conversations, completed background work, communications and spatial sightings without inventing emotions or motives.

## Calendar conflicts and prefetching

Ask:

```text
Jarvis, check my calendar for conflicts.
```

Jarvis detects overlapping timed events and proposes available alternatives. It does not move, decline, or rewrite meetings without the normal external-write confirmation path.

A few minutes before a scheduled event, Jarvis can prewarm the fast 8B model and search the **local** unified index for relevant context. It deliberately does not send private calendar titles to arbitrary external APIs as an automatic prefetch step.

## Dynamic remote bandwidth

With **Adaptive remote vision bandwidth** enabled:

```text
LAN path       ~1 sampled frame/sec, up to 512 px
Tailscale path ~1 sampled frame/3 sec, up to 384 px
```

This protects cellular/remote bandwidth without disabling passive context entirely. Silent/manual visual scans still use a higher-quality single frame.

## Sandboxed terminal command safety

Docker sandbox setup, if desired:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-sandbox.ps1
```

Generated Python and terminal commands run only inside a disposable container with:

- network disabled
- read-only filesystem
- dropped Linux capabilities
- `no-new-privileges`
- 256 MB memory limit
- one CPU
- process limit
- hard timeout

There is still no LLM-facing Windows host shell.

A proposed isolated terminal command is a `security` action. Jarvis includes the **entire exact command** in the spoken prompt before authorization. After hearing it, the user says:

```text
execute exact command
```

or:

```text
never mind
```

The special wording exists so the iPhone does not replace this security prompt with its normal abbreviated `Ready, sir. Say confirm or cancel.` response.

## Self-healing custom API adapters

Custom API adapters remain sandbox-generated and HTTPS-host allowlisted. If an enabled adapter fails structurally (for example, an invalid request plan or certain API contract errors), Jarvis may ask the 27B model to draft a repair in the background.

A repair is queued only after:

- Docker sandbox execution succeeds;
- the output is a valid request plan;
- the original HTTPS host allowlist still matches;
- the original risk level is preserved;
- no embedded authorization/cookie/API-key header appears.

Jarvis never silently applies the patch. Ask:

```text
Jarvis, list custom tool repairs.
Jarvis, apply the repair for <tool name>.
```

Applying the repair is a `security` action and requires explicit confirmation.

## Web search

Configure Serper once:

```powershell
py -3.14 -m jarvis_mrb.serper_setup
```

The key stays under `%APPDATA%\JarvisForMRB`. Search evidence is synthesized into a short voice-friendly answer rather than reading SERP snippets or URLs aloud.

## Memory

```text
%APPDATA%\JarvisForMRB\conversation.sqlite3
%APPDATA%\JarvisForMRB\episodic_memory.sqlite3
%APPDATA%\JarvisForMRB\ephemeral_state.json
%APPDATA%\JarvisForMRB\knowledge_sources.sqlite3
%APPDATA%\JarvisForMRB\notes\
```

Normal turns receive only the immediately preceding exchange, preventing an old topic from becoming the fallback interpretation of imperfect speech recognition. Older conversational context is expanded only when the user explicitly refers backward (`earlier`, `remember`, `five prompts ago`, etc.).

## Tailscale

Do not expose port 8765 publicly and do not enable Funnel.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-tailscale.ps1
```

Put the resulting private `https://...ts.net` Serve URL in **Jarvis → Settings → Tailscale URL**.

## Update the iPhone

On the Mac:

```bash
cd <Jarvis-for-MRB>
git pull
```

Then in Xcode:

```text
Shift+Cmd+K
Cmd+R
```

Keep the development Team selected under **Signing & Capabilities**. HealthKit remains an optional capability from Milestone 12.

New/updated Settings controls include:

- Adaptive remote vision bandwidth
- Smart PC audio damping
- Automatic local daily journal
- proactive interruption threshold
- passive vision
- ambient HUD cues
- geofenced profiles
- Apple Health context
- adaptive whisper
- quiet-speech mode

## Deliberate non-features / boundaries

Several tempting capabilities are intentionally **not** implemented as if they were reliable:

- **Speaker voiceprint identification:** no biometric identity database or recurring-person identification from voices.
- **Vocal stress/emotion analytics:** no labeling another person's voice as stressed, tense, deceptive, angry, etc. Non-identifying acoustic quality/disfluency metrics could be added separately without making sensitive affective inferences.
- **System-wide iPhone notification interception:** a normal companion app cannot arbitrarily read every other app's notifications. Jarvis prioritizes its own companion/proactive events instead.
- **Safety-critical indoor visual homing:** last-seen spatial/landmark memory is available, but camera-only relative guidance is not presented as dependable navigation.
- **Invisible meeting recording:** meeting capture is explicit and visibly active.
- **Unrestricted terminal control:** only the locked-down Docker sandbox is exposed to the model.

A true IDE-content integration also requires an explicit editor bridge/plugin; foreground-window context alone is not treated as access to the file contents.

## Default permission policy

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

Gmail sending additionally retains the exact-recipient backend allowlist.
