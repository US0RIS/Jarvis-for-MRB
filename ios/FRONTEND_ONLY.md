# Jarvis iPhone — Frontend-only capability layer

This document covers features that can be installed by rebuilding the iPhone app without changing the running Windows Jarvis backend.

## Important status boundary

The conversational backend path for questions such as **“Jarvis, what can you see right now?”** is **not counted as implemented/tested** on the user's currently running backend. A backend-side Moondream/recent-frame compatibility change exists in the repository but must not be considered deployed until the Windows service can be updated and tested.

The iPhone-only perception features below are independent of that path. They use Apple's on-device Vision framework and are intentionally narrower than general scene understanding.

## On-device perception

The iPhone can keep a 30-second RAM-only ring buffer of downsampled Ray-Ban DAT frames. It can run Apple Vision locally for:

- OCR / visible text recognition
- QR and barcode decoding
- human rectangle detection
- face rectangle counting without identity
- rectangle detection
- attention-based saliency

Local commands include forms such as:

- `Jarvis, read this.`
- `Jarvis, copy this text.`
- `Jarvis, scan the QR code.`

Recognized text/code payloads are copied to the **iPhone** clipboard. These local features do not imply that the iPhone can semantically describe arbitrary scenes like Moondream.

The app exposes a recent-frame thumbnail timeline, cache size, estimated local capture FPS, last compressed frame size and local-perception status.

## Offline command staging

When both configured Jarvis endpoints are unreachable, commands may be staged locally instead of discarded. Staged commands **never execute automatically** when connectivity returns. The user must explicitly press **Send Next** or issue the local `send queued command` command.

## Connection diagnostics

The frontend independently probes the configured LAN and Tailscale health endpoints and displays approximate round-trip latency. The diagnostic report also includes:

- voice state
- active audio route
- speech-recognition confidence
- Ray-Ban registration / DAT state
- camera-stream state
- local visual cache/FPS/frame size
- local perception state
- offline queue depth
- optional motion state
- Health context state
- last planner model and response timing

## Local conversation history and latency telemetry

The iPhone keeps a bounded local transcript of recent user/Jarvis turns for UI inspection. It records the planner model reported by the existing streaming backend and measures:

- time to first response text
- time to first playable audio
- total frontend turn duration

This local transcript is separate from the PC's long-term semantic memory.

## Local voice aliases

Selected commands can execute on the iPhone without an LLM round trip, including:

- read/copy visible text
- scan QR/barcode
- passive vision on/off
- mute/unmute proactive speech
- mute/unmute response speech
- force whisper for N minutes / return to normal voice
- connection diagnostics
- explicitly send the next queued command

## Audio improvements

HUD cue volume has a user control and can scale based on the measured ambient noise floor. A local command can force the existing whisper playback mode for a bounded time period without changing the backend.

Speech recognition now exposes average Apple Speech segment confidence and partial/final state for diagnostics.

## Meeting capture improvements

The iPhone meeting recorder now supports:

- visible elapsed timer
- pause/resume
- bookmarks with relative timestamps
- continuous local transcript accumulation
- local transcript snapshot in Application Support
- Share Sheet export of the local transcript
- continued local capture when the PC cannot be reached
- explicit later **Sync & Extract** using the backend endpoints that already exist

Meeting recording remains explicit and visible. It does not identify speakers by voiceprint or infer emotion/stress.

## Optional motion/travel context

When enabled, the iPhone can use Core Motion / Core Location to show coarse activity such as stationary, walking, running, cycling or driving, plus locally available speed/course/altitude diagnostics. Motion access is off by default and requires the normal iOS permission.

## App Intents / Shortcuts / Action Button

The app registers App Intents for:

- Talk to Jarvis
- local Visual Scan
- Read Visible Text
- Toggle Passive Vision
- Toggle Meeting Notes
- Toggle Jarvis spoken responses (intent is registered in-app even if not shown in the primary shortcut list)

These can be invoked from Shortcuts and can be assigned to the iPhone Action Button where iOS offers app shortcuts.

## Not included in this frontend-only pass

### General live scene understanding

Still backend/Moondream-dependent and explicitly not considered working on the currently deployed backend.

### Dynamic Island / Live Activity and true Lock Screen widget controls

Those require adding a separate Widget/Live Activity extension target, associated extension provisioning/signing, and additional lifecycle testing. They were deliberately not folded into the existing single-target app during this frontend-only pass because doing so would materially increase build/signing risk while the user is away from the PC. App Intents cover Action Button / Shortcuts access in the meantime.

### Arbitrary cross-app iOS notification interception

Not available to a normal companion app.

### Full IDE/document contents, PC tool additions, model changes, memory/index changes, Moondream changes

Those remain backend or external-app integration work.
