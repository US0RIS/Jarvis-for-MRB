# Jarvis iPhone — Frontend-only capability layer

This document covers capabilities that can be installed by rebuilding the iPhone app without changing the currently running Windows Jarvis backend.

## Important status boundary

The conversational backend path for questions such as **“Jarvis, what can you see right now?”** is still not counted as deployed/tested on the user's currently running backend. A backend-side Moondream/recent-frame compatibility change exists in the repository but must not be considered live until the Windows service is updated and tested.

The frontend features below are independent of that deployment boundary. The latest frontend source also contains preparation and observability for the upcoming backend migration so the phone can show whether the new world-model stack is actually connected and receiving bounded state.

## Backend Readiness / Compatibility dashboard

The iPhone now has a dedicated **Operations** screen accessible from the main Jarvis toolbar. It independently probes the configured LAN and fallback/Tailscale `/health` endpoints using the existing bearer token and reports the backend capabilities the server actually advertises.

Where supplied by the backend health payload, it displays:

- backend version;
- planner model;
- auto-routing state;
- TTS state;
- sandbox state;
- web-search state;
- visual-history state;
- resource-guardrail state;
- world-model state;
- closed-loop verification state;
- action-audit state;
- endpoint and round-trip timing.

The parser is intentionally tolerant of older health payloads. Missing newer fields display as `Unknown` rather than making an old but otherwise reachable backend look disconnected.

Local command examples include:

- `Jarvis, backend readiness.`
- `Jarvis, system readiness.`
- `Jarvis, backend compatibility.`

## World-sync telemetry and privacy contract

The authenticated companion socket now reports its own operational state instead of making world synchronization a black box.

Frontend telemetry tracks:

- connection attempts;
- current active endpoint;
- successful connection time;
- reconnect count;
- disconnect time/error;
- world-snapshot send attempts;
- successful snapshot time;
- canonical snapshot SHA-256 hash;
- serialized byte count;
- schema version;
- per-collection counts;
- semantic no-op count;
- send-failure count;
- last error.

The same semantic-deduplication behavior is preserved: `captured_at` does not create artificial changes, and an unchanged world snapshot is not retransmitted.

Before a metadata world snapshot crosses the companion connection, the iPhone recursively checks it for fields that violate the world-snapshot privacy contract. A snapshot is blocked rather than transmitted if it contains keys representing:

- biometric/feature-print data;
- enrollment images;
- raw camera frames;
- raw/rolling microphone audio buffers;
- clipboard content;
- privacy-zone coordinates;
- incident media.

The Operations screen exposes whether this privacy contract is currently OK or blocked.

Local command example:

- `Jarvis, world sync status.`

## On-device perception

The iPhone can keep a 30-second RAM-only ring buffer of downsampled Ray-Ban DAT frames. It can run Apple Vision locally for:

- OCR / visible text recognition;
- QR and barcode decoding;
- human rectangle detection;
- face rectangle counting;
- rectangle detection;
- attention-based saliency.

Local commands include forms such as:

- `Jarvis, read this.`
- `Jarvis, copy this text.`
- `Jarvis, scan the QR code.`

Recognized text/code payloads are copied to the **iPhone** clipboard. These local features do not imply that the iPhone can semantically describe arbitrary scenes like Moondream.

The app exposes a recent-frame thumbnail timeline, cache size, estimated local capture FPS, last compressed frame size and local-perception status.

## Known People — closed-set private recognition

Known People is an explicit opt-in, frontend-only recognition layer. It does **not** attempt to identify arbitrary strangers. The user deliberately creates a profile with a contact label and at least two (preferably 3–6) clear samples of that same person.

Enrollment and matching work locally on the iPhone:

1. Apple Vision detects the largest face in each enrollment sample.
2. The app crops the face region and creates a `VNFeaturePrintObservation`.
3. Raw enrollment photos are discarded by this feature after the feature print is created.
4. The contact label, private user note, calibration distance and archived feature prints are stored in the app's this-device-only Keychain item.
5. While recognition is enabled, current Ray-Ban frames are compared only against those explicitly enrolled profiles.
6. Continuous recognition requires two consecutive compatible matches before accepting a contact. An explicit `who is this?` request can force an immediate comparison.
7. If two enrolled people score too closely, the result stays ambiguous instead of forcing an identity.

Local commands include:

- `Jarvis, who is this?`
- `Jarvis, who am I talking to?`
- `Jarvis, what do I know about this person?`
- `Jarvis, what did I talk about with them?`

The frontend can retrieve the user's private note for that profile and recent conversation turns stored by the iPhone app that mention the person's name. It phrases recognition as an estimate rather than certain identity.

**Current deployment limitation:** full filtered retrieval across the PC's long-term Gmail, Calendar, notes and world model requires the upcoming backend deployment. The currently running Windows service must not be assumed to know a newly recognized contact automatically.

## Audio routing policy

Jarvis now treats the Ray-Bans and iPhone as different classes of microphone rather than as one interchangeable input.

### Wearer-command profile

Normal hands-free commands prefer the Ray-Ban Bluetooth HFP microphone when enabled and available. If Bluetooth microphone preference is disabled, the app explicitly selects the iPhone built-in microphone instead of merely hoping iOS leaves HFP.

### Room/meeting profile

Meeting Notes and explicit Room Listening use a separate `AVAudioSession` room-capture profile. It:

- uses `.playAndRecord`;
- uses `.measurement` mode;
- does not expose Bluetooth HFP as a capture option;
- explicitly selects the iPhone built-in microphone;
- allows A2DP output where iOS permits it independently;
- fails visibly if the built-in microphone is unavailable.

This is deliberate because the Ray-Ban microphones are optimized for the wearer, whereas meeting capture needs speech from other people in the room.

## Meeting microphone route watchdog

Selecting the iPhone microphone once is not treated as sufficient. While Meeting Notes is active, the frontend repeatedly verifies that the current input is still `.builtInMic`.

If iOS/Bluetooth changes the route, Jarvis attempts to reassert the room-capture profile immediately. A route failure appears in Operations and can create an Attention Inbox warning rather than silently degrading the transcript.

Meeting Notes also reasserts the room microphone whenever Apple Speech is restarted during its bounded recognition-task rotation.

## Explicit Room Listening mode

Jarvis can now use the same room-facing microphone profile outside a formal Meeting Notes session.

Examples:

- `Jarvis, start room listening.`
- `Jarvis, listen to the room for five minutes.`
- `Jarvis, listen for the next ten minutes.`
- `Jarvis, what did they just say?`
- `Jarvis, stop room listening.`

Properties:

- explicit start only;
- visible `Room Listening` state;
- iPhone built-in microphone only;
- default five-minute window;
- bounded between approximately 15 seconds and 30 minutes;
- 20-second Apple Speech task rotation;
- local transcript bounded in memory;
- route watchdog continuously reasserts the iPhone microphone;
- hands-free Ray-Ban listening is suspended during the room session and restored afterward;
- a HUD card and Live Activity make the active capture state visible.

The recent transcript can be retrieved locally. A user-requested translation of the captured text can use the existing Apple on-device model when available. Room Listening does not identify speakers by voiceprint and does not infer emotion, stress or deception.

Use audio capture only where permitted and with appropriate participant notice/consent.

## Microphone placement/calibration test

The Operations screen can run a short sequential microphone comparison.

The test:

1. temporarily suspends hands-free Jarvis;
2. captures the same room speaker with the iPhone room microphone;
3. if Ray-Ban HFP is available, repeats the sample using HFP;
4. compares Apple Speech confidence and measured input level;
5. recommends the iPhone room route or advises repositioning the phone closer to the center of the table;
6. restores hands-free mode afterward.

Local command:

- `Jarvis, calibrate the microphone.`

This is a practical placement check, not laboratory microphone calibration.

## Deterministic “Welcome back, sir” coordinator

The previous introduction depended directly on a device-return callback and could be inconsistent around Bluetooth/DAT transitions. The latest frontend gives the introduction one explicit owner.

The coordinator now:

- replaces the prior glasses-return callback after frontend Operations starts;
- treats Meta DAT's sustained unavailable→available transition as a **proxy** for glasses return, not as a false claim of perfect on-head sensing;
- waits for the device route to settle;
- confirms the glasses remain eligible;
- applies a ten-minute duplicate-greeting cooldown;
- suppresses repeated Bluetooth flaps;
- defers while Jarvis is busy speaking/processing rather than talking over a turn;
- skips after a bounded busy timeout instead of firing at an arbitrary later moment;
- explicitly reasserts the wearer audio profile immediately before the greeting;
- temporarily suspends hands-free recognition during playback;
- restores hands-free recognition afterward;
- exposes status, last greeting, and suppressed duplicate count in Operations;
- includes a deterministic `Test Greeting Once` control.

This still cannot turn Meta DAT into a true on-head sensor. It makes the best supported return signal deterministic and observable.

## Display-neutral Jarvis HUD

The frontend now has a structured display model independent of any particular hardware display.

Five primitive card types are defined:

1. attention;
2. context;
3. action;
4. verification;
5. ephemeral answer.

Each `JarvisHUDCard` contains bounded structured state such as title, detail, badge, priority, creation/expiry time and source. The HUD store deterministically chooses a primary card by current validity, priority and recency.

Today those cards can be inspected on the iPhone and projected into a Live Activity. If Meta Display glasses are adopted later, a display adapter can render the same card model rather than redesigning Jarvis's state/presentation contract.

## Persistent Attention Inbox

Transient proactive messages are now also captured into a persistent frontend Attention Inbox.

The inbox:

- stores up to 100 bounded items;
- records title, detail, severity, source and acknowledgement state;
- supports stable-ID updates for recurring conditions;
- supports acknowledge / acknowledge-all / delete;
- is AES-GCM encrypted at rest;
- uses a Keychain-held, this-device local key;
- uses complete file protection.

Backend proactive observations can be mirrored into the inbox and into a short-lived HUD card. This is especially useful after the new backend is deployed because Executive blockers and failed verification no longer have to exist only as transient speech.

Local commands include:

- `Jarvis, attention inbox.`
- `Jarvis, what needs my attention?`

## Live Activity / Lock Screen / Dynamic Island

The iOS project now includes a dedicated `JarvisLiveActivity` WidgetKit extension and the main app declares Live Activity support.

The app-side coordinator can create/update/end a compact activity using the same display-neutral state. The widget provides:

- Lock Screen presentation;
- Dynamic Island expanded presentation;
- compact leading/trailing presentation;
- minimal presentation;
- countdown display where an end time exists;
- progress display where relevant;
- mode-specific symbols.

Room Listening uses this so an active ambient capture is not invisible. The same surface can display the current primary attention/action/verification HUD card.

This addition requires the updated Xcode project to be built and signed; it has not yet been runtime-tested on the physical iPhone.

## Offline command staging

When both configured Jarvis endpoints are unreachable, commands may be staged locally instead of discarded. Staged commands **never execute automatically** when connectivity returns. The user must explicitly press **Send Next** or issue the local `send queued command` command.

## Connection diagnostics

The frontend independently probes the configured LAN and Tailscale health endpoints and displays approximate round-trip latency. The diagnostic report also includes:

- voice state;
- active audio route;
- speech-recognition confidence;
- Ray-Ban registration / DAT state;
- camera-stream state;
- local visual cache/FPS/frame size;
- local perception state;
- offline queue depth;
- optional motion state;
- Health context state;
- last planner model and response timing.

The Operations screen complements this with backend service readiness and world-sync telemetry.

## Local conversation history and latency telemetry

The iPhone keeps a bounded local transcript of recent user/Jarvis turns for UI inspection. It records the planner model reported by the existing streaming backend and measures:

- time to first response text;
- time to first playable audio;
- total frontend turn duration.

This local transcript is separate from the PC's long-term semantic memory.

## Local voice aliases

Selected commands can execute on the iPhone without an LLM round trip, including:

- read/copy visible text;
- scan QR/barcode;
- closed-set known-person questions when recognition is enabled;
- passive vision on/off;
- mute/unmute proactive speech;
- mute/unmute response speech;
- force whisper for N minutes / return to normal voice;
- connection diagnostics;
- backend readiness;
- world-sync status;
- room listening;
- recent room transcript;
- requested room-transcript translation;
- microphone calibration;
- Attention Inbox;
- deterministic welcome-greeting test;
- explicitly send the next queued command.

## Audio improvements

HUD cue volume has a user control and can scale based on the measured ambient noise floor. A local command can force the existing whisper playback mode for a bounded time period without changing the backend.

Speech recognition exposes average Apple Speech segment confidence and partial/final state for diagnostics.

## Meeting capture improvements

The iPhone meeting recorder supports:

- visible elapsed timer;
- pause/resume;
- bookmarks with relative timestamps;
- continuous local transcript accumulation;
- local transcript snapshot in Application Support;
- Share Sheet export of the local transcript;
- continued local capture when the PC cannot be reached;
- explicit later **Sync & Extract** using the backend endpoints that already exist;
- forced iPhone room-microphone routing;
- continuous route watchdog/recovery.

Meeting recording remains explicit and visible. It does not identify speakers by voiceprint or infer emotion/stress.

## Optional motion/travel context

When enabled, the iPhone can use Core Motion / Core Location to show coarse activity such as stationary, walking, running, cycling or driving, plus locally available speed/course/altitude diagnostics. Motion access is off by default and requires the normal iOS permission.

## App Intents / Shortcuts / Action Button

The app registers App Intents for:

- Talk to Jarvis;
- local Visual Scan;
- Read Visible Text;
- Toggle Passive Vision;
- Toggle Meeting Notes;
- Toggle Jarvis spoken responses.

These can be invoked from Shortcuts and can be assigned to the iPhone Action Button where iOS offers app shortcuts.

## Still backend-dependent

### General live scene understanding

General conversational scene understanding and Moondream/recent-frame questions remain backend-dependent and explicitly are not considered working on the currently deployed backend until that service is updated and tested.

### Full cross-app person-specific memory retrieval

Known People can use private profile notes and bounded iPhone conversation history locally. Unified Gmail/Calendar/document/world-model retrieval by stable identity requires the new backend deployment.

### Executive/world reasoning

The frontend can display readiness, sync state, HUD cards and proactive messages, but the persistent world graph, Project term ledger, document lineage, Executive Loop and closed-loop verification remain PC-side systems.

## Deliberate platform boundaries

A normal companion app still cannot provide arbitrary cross-app iOS notification interception. Foreground-window context on the PC still does not imply arbitrary IDE/document contents. The frontend does not gain unrestricted authority merely because it has new local presentation surfaces.

## Verification status

Everything in this document is **source-level frontend implementation** unless already tested on the currently installed build. The latest changes—including room-audio routing/watchdog, Operations dashboard, world-sync telemetry, HUD, Attention Inbox, deterministic welcome coordinator and Live Activity extension—still require an Xcode build and physical-iPhone runtime verification.
