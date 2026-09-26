# Jarvis for MRB

Jarvis is a private, local-first personal operating system built around a persistent model of the user’s world. Its primary presence path is the iPhone/compatible Bluetooth microphone plus phone motion, opt-in GPS/geofences, separately opt-in Health data and public environmental sources. The optional camera-free MemoMind display is an I/O surface, not a sensor prerequisite. A Windows reasoning/tool host, local language/speech models, private Gmail/Calendar data, automation, audited web research and explicit action verification form the remaining system. Meta first-person vision and public-camera lookup remain optional capabilities.

The project is not intended to be “a chatbot with lots of plugins.” The design goal is a single persistent system that can understand what the user is doing, remember durable facts and objectives, connect evidence across sources, decide what matters, act within explicit authority boundaries, and then independently verify whether consequential actions actually changed the outside world.

This README is the canonical high-level guide to the repository. It is intentionally broad: architecture, setup, every major feature family, privacy/security boundaries, world-model semantics, runtime operations, testing, evaluation, and troubleshooting are all covered here. Deeper design/history documents remain in the repository for specialized details.

## World Armor — proposed planetary-scale extension

**[Full design specification](docs/WORLD_ARMOR_SPEC.md)** for the Planetary Event
Fabric and Distributed Agency: source-qualified infrastructure OSINT, spatial
and temporal correlation, uncertainty-aware event investigations, explicit
regional watches, and tightly scoped computation across authorized paired
devices. **Design only / Roadmap:** no World Armor collector, event store, new
API endpoint, RF sensor, global AIS service, trading service, or cloud worker
was implemented or deployed by this document. The Reality Browser, Presence,
Causal Debugger, Synthetic Senses and Parallel Existence ideas are preserved
and remain on hold.

## Meeting prebrief convergence — read-only source-qualified evidence

On the stacked `jarvis/situation-evidence-unification` branch,
[Situation Evidence](SITUATION_EVIDENCE.md) augments the existing
`world_situation` meeting compiler with previously evaluated **linked**
Guardian watches and **matching** user-enrolled Life Fabric deadlines,
dependencies and completion states. Every item carries provenance and
coverage limits. It does not run a Guardian alert, infer all-clear or
actuate devices. iPhone Mission Control is still phone-local and calendar
events are not yet bound to exact Reality Lens coordinates; those inputs
are available only through explicit, exact-event optional snapshots and
are **not** claimed as automatically wired. This feature is branch source,
not merged to `main` or observed deployed.

## Life Fabric — reduce five years of ordinary friction

**[Life Fabric](LIFE_FABRIC.md)** adds a private, user-enrolled everyday-life
ledger with an actual iPhone **Life Fabric** workspace, timezone-aware
readiness and dependency checks, classified completion receipts, manually
recorded assets, six eight-step life-transition checklists, explicit
cross-device continuation packets, a Friction Observatory for three distinct
reported days, and bounded time-budget what-ifs. A separate
**[five-year inconvenience catalog](LIFE_FRICTION_CATALOG.md)** maps all 17
ordinary-life domains to implemented primitives and the external connectors
or hardware still required. It is a source- and authorization-aware foundation,
**not** a claim that Jarvis can already automate every scenario in the
catalog, passively observe your habits, charge a card, or verify medical,
financial or physical outcomes without the necessary provider access.
Nothing is deployed on your devices merely because CI passes.

## Human Extension v1 — executable first superpower slice

**[Reality Lens](HUMAN_EXTENSION.md)** is the first deliberately non-chatbot
human-extension workflow originating on `jarvis/human-extension-v1` and included in this candidate: use the existing
iPhone Mesh named-place resolver, sense actual supported public environmental
sources, explicitly remember a bounded source-backed observation on the
private Jarvis PC, revisit later for a deterministic change comparison, and
feel a short user-triggered haptic signal if a supported fresh provider value
changed. Unknown/stale sources remain unknown; the lens does not continuously
track the user, save raw media or authorize remote actions. This is a concrete
**remote perception + external episodic memory + tactile feedback** loop,
not a claim that the full human-extension roadmap is already deployed.
The matching iPhone/backend builds still require physical-device acceptance.

## Camera-free ambient autonomy — in the convergence candidate

The camera-centred opportunity matcher is retired. Originating on `jarvis/memomind-prep` and included in this candidate, opt-in iPhone acoustic sound classification (foreground or active voice capture), separately timestamped phone motion and location/geofence and modelled, source-labelled outdoor temperature can match *explicit existing standing reminders* through Agency Attention. The source metadata is transient and cannot authorize tools or physical actions. Health is separately opt-in read-only context, not a diagnosis or actuating signal.

Actual reversible action path: after discovering Apple Home, the user may individually preauthorize an exact light for an observed arrival, or for **two high-confidence doorbell classifications while the phone confirms home during 18:00–07:00 local time**. The foreground iPhone initiates only those enrolled HomeKit writes, then reads back the characteristic. An encrypted, locally clearable receipt separates verified success from failed/unverified actions. This is not a general autonomous device controller and is not supported in iOS background without actual device acceptance.

Configuration: Physical → Ambient presence → Settings. Independently enable Proactive microphone + sensor opportunities, Motion / travel context, Sound Recognition for acoustic triggers, and optional weather/Health sources. Discover Apple Home on the Physical tab; enroll each permitted light. Geofenced home coordinates/radius must be configured. Do not interpret a sound label as proof of a visitor. The ability to use a future MemoMind HUD/audio stream still requires the actual official SDK and physical hardware.

**[Jarvis Conductor v1](CONDUCTOR.md) now implements a real, bounded exact-device workstation mission.** The iPad/iPhone Mesh tab lets you choose one paired Windows/Mac host, up to three literal allowed app names and optionally a two-minute private view. A server-persisted plan returns a short-lived one-use grant in iPhone RAM; an explicit confirmation consumes it before side effects, with each step reserved ahead of OS/remote IO and followed by a different fresh running-process observation. Replays, changed targets, expired/revoked grants, missing source evidence and unknown external outcomes fail closed and never trigger blind retries. Separately opted-in **exact low-risk speech** can say "Jarvis, open Safari on my MacBook Air": this stages and consumes a fresh one-app/no-screen grant, checks running-process state and reports the outcome. This is not general remote shell, authenticated speaker identification, focus verification or unfettered physical control; setup and limits are in `CONDUCTOR.md`.

**[Reality Graph](REALITY_GRAPH.md) now performs deterministic cross-provider observation correlation and model-free mission readback.** It compiles real integrated place sources and typed mission evidence into timestamped entities, source-linked route edges, freshness and derived facts. A separate default-off local mission ledger retains only bounded normalized caller-supplied observations, with authenticated create/append/snapshot/stop/delete routes and narrow voice status questions answered before Qwen. Courier/traffic provider credentials, real courier tracking, worldwide CCTV and independent provider attestation are **not yet integrated**; a client-supplied source label is not proof of authenticity. Reality Graph has no purchasing, messaging or device-control authority. See `REALITY_GRAPH.md` for setup and precise limits.

**Selected next *unimplemented* milestone: [EDITH Field Ops](EDITH_FIELD_OPS.md).** Extend verified speech → real-world effect from benign workstation actions to individually authorized nonhazardous personal devices (first supported HomeKit lights), using actual OS APIs, source-specific readback, repeat limits and risk-appropriate grants; do not add fictional globally controlled infrastructure or autonomous hazardous actuation. The earlier Conductor planning spec is retained in `NEXT_BIG_UPGRADE.md` as architectural history.

**[Reality Mesh](REALITY_MESH.md) now provides an initial working cross-device fabric and remote-world viewport.** The iPhone/iPad **Mesh** tab checks the actual Windows host and explicitly paired MacBook Air/Mac mini nodes over private Tailscale links. An additional default-off Windows process flag enables **actual view-only desktop snapshots** from the interactive Windows session using Pillow ImageGrab, under the same independently tapped 120-second phone consent and authenticated bearer gate; headless Session 0 cannot claim a screen. A real macOS Python node can serve fresh device status and, only after Mac startup opt-in plus a separate two-minute phone tap, view-only private screen snapshots routed through the authenticated Windows backend. Sessions expire and can be revoked; missing Mac Screen Recording permission or unavailable hardware stays unavailable. A separately disabled-by-default Mac startup flag also allows **five exact, user-tapped app launches** (Safari, Notes, Calendar, Preview, Finder) on an authenticated matching Mac, returning OS launch acknowledgement plus a distinct process observation—never arbitrary terminal execution, OS remote input or a falsely asserted foreground window. The same tab resolves a precisely named place using Apple MapKit and calls already integrated real public environmental, Caltrans, USGS, NWS and OSM source adapters, preserving regional coverage gaps (including **no implied Melbourne public-camera stream**). No uncontrolled LAN scanning, remote desktop input, OS-native file dragging, general purpose device agent, or global camera/video access is asserted. Setup, threat boundaries and Mac activation are in `REALITY_MESH.md`.

**[Mission Control](MISSION_CONTROL.md) now adds a concrete persistent, outcome-oriented iPhone execution pack.** In the dedicated Missions tab (also Physical), enroll one exact timed calendar appointment as a mission; Jarvis rechecks its original Calendar event, fresh accurate GPS and a real Apple MapKit driving route, reasons about a five-minute departure buffer, and records distinct sourced receipts. Separately authorized, one-use, event/time/destination-bound Apple Maps handoff is attempted at risk; an ETA draft is strictly local. Two distinct accurate GPS observations near the uniquely resolved destination distinguish observed on-time/late arrival from merely opening directions; background suspension or missing evidence never proves attendance or a miss. A default-off mission toggle, RAM-only grant lifecycle and Privacy-mode revocation bound autonomy. The Mission Board also shows a read-only, permission-aware PC tool affordance inventory; a registered tool is not assumed online, approved for the mission or successfully executed. Other mission packs remain future work.

**[Counterfactual Guardian](COUNTERFACTUAL_GUARDIAN.md) first slice now exists in source.** When independently enabled, the foreground iPhone checks up to three upcoming timed primary-Google-Calendar destinations against fresh accurate iPhone GPS and actual Apple MapKit driving routes. It alerts if travel time plus a stated five-minute buffer threatens the start time; failure to resolve a source produces an unknown status, not an invented all-clear. The user can open Apple Maps manually, enroll a one-use event/time/location-bound automatic Maps handoff, or stage a strictly local unsent ETA draft. Receipts are retained in the iPhone Keychain and distinguish handoff accepted from arrival verified. A second, separately enrolled Guardian path now watches **explicit user goals with precise deadlines** on the Windows World Executive, cross-checks active status, next actions and pending linked commitments, and offers read-only evidence review or an unsent local follow-up draft. It interrupts at most once per monitor cycle, only with a fresh foreground phone opt-in and when you are not driving/in a meeting/conversing. Watches can be individually snoozed or revoked and expire; changing a source deadline requires reenrollment. This is *not* generalized prediction, an always-on phone-background process, or authority to send messages or arbitrarily control devices.

---

## Table of contents

1. [Current state](#current-state)
2. [What Jarvis is trying to become](#what-jarvis-is-trying-to-become)
3. [System architecture](#system-architecture)
4. [Core design invariants](#core-design-invariants)
5. [Hardware and software requirements](#hardware-and-software-requirements)
6. [Experimental physical actuation: CrunchLabs IR Turret](#experimental-physical-actuation-crunchlabs-ir-turret)
7. [Cross-branch capability ledger and forward roadmap](#cross-branch-capability-ledger-and-forward-roadmap)
8. [Backend installation and update](#backend-installation-and-update)
9. [Models and local AI services](#models-and-local-ai-services)
10. [Google, web, browser, Tailscale, and Docker setup](#google-web-browser-tailscale-and-docker-setup)
11. [iPhone build and configuration](#iphone-build-and-configuration)
12. [Voice and conversation](#voice-and-conversation)
13. [Audio routing and speech](#audio-routing-and-speech)
14. [Ray-Ban Meta integration](#ray-ban-meta-integration)
15. [Vision and recent visual memory](#vision-and-recent-visual-memory)
16. [Known People](#known-people)
17. [Personal inventory](#personal-inventory)
18. [Personal Notecard](#personal-notecard)
19. [Turn-by-turn navigation](#turn-by-turn-navigation)
20. [Local iPhone intelligence](#local-iphone-intelligence)
21. [World synchronization](#world-synchronization)
22. [Persistent world model](#persistent-world-model)
23. [Identity, provenance, chronology, and relation safety](#identity-provenance-chronology-and-relation-safety)
24. [Persistent goals and intentions](#persistent-goals-and-intentions)
25. [Situational awareness and meeting prebriefs](#situational-awareness-and-meeting-prebriefs)
26. [Gmail attachments, document lineage, and term conflicts](#gmail-attachments-document-lineage-and-term-conflicts)
27. [Executive Loop](#executive-loop)
28. [Tools, permissions, and action authority](#tools-permissions-and-action-authority)
29. [Closed-loop action verification](#closed-loop-action-verification)
30. [Proactivity, HUD, Attention Inbox, and Live Activities](#proactivity-hud-attention-inbox-and-live-activities)
31. [Meeting Notes and Room Listening](#meeting-notes-and-room-listening)
32. [Automation, jobs, background work, and workflows](#automation-jobs-background-work-and-workflows)
33. [Web research integrity and Research Receipts](#web-research-integrity-and-research-receipts)
34. [COVER and COVER-U benchmarks](#cover-and-cover-u-benchmarks)
35. [JARVIS-20 behavioral evaluation](#jarvis-20-behavioral-evaluation)
36. [Expenses, journals, PC context, and system guardrails](#expenses-journals-pc-context-and-system-guardrails)
37. [Sandbox and custom tools](#sandbox-and-custom-tools)
38. [Privacy and security model](#privacy-and-security-model)
39. [Data stores and retention](#data-stores-and-retention)
40. [Health, diagnostics, migrations, and rollback](#health-diagnostics-migrations-and-rollback)
41. [Testing and acceptance](#testing-and-acceptance)
42. [Canonical Project Apollo acceptance story](#canonical-project-apollo-acceptance-story)
43. [Repository layout](#repository-layout)
44. [Common command reference](#common-command-reference)
45. [Known limitations and deliberate non-features](#known-limitations-and-deliberate-non-features)
46. [Troubleshooting](#troubleshooting)
47. [Development philosophy and finish line](#development-philosophy-and-finish-line)
48. [Related documentation](#related-documentation)

---

# Current state

Jarvis has moved beyond a source-only prototype: the current architecture has been deployed onto the primary Windows PC and a physical iPhone, and several of the most important end-to-end paths have been exercised against real services.

### Verification snapshot — September 7, 2026 (Pacific)

The following have been observed working in the real deployment during the current validation cycle:

- Windows backend starts and serves authenticated requests.
- `/health` reports the core backend as operational.
- local Qwen inference is working.
- Kokoro TTS is running through WSL, warming on CUDA, synthesizing valid WAV output, and reporting ready.
- Docker Desktop is installed and the Jarvis sandbox reports ready.
- Gmail authentication/read works against the real account.
- Google Calendar authentication/read works against the real account.
- a real Calendar write passed the normal external-write confirmation gate.
- the Calendar write was independently read back from Google and changed the persisted action-verification status to `verified`.
- an earlier verification timeout was later recovered by an explicit “Did that work?” query without repeating the action.
- world schema is at **version 5 / target 5**.
- world diagnostics have returned `ok=true` with no hard problems; the known standalone-diagnostic warning about the runtime audit wrapper is expected because the wrapper belongs to the live service process.
- the iPhone app builds, signs, installs, and launches on a physical iPhone.
- the iPhone Operations screen can see backend readiness, companion state, world-sync telemetry, and the snapshot privacy contract.
- the iPhone successfully published a real Goal Manager goal into the PC world model.
- completing that goal on the phone produced the correct temporal lifecycle on the PC: the prior `active` belief became `superseded`, while `completed` became the current status.
- the physical iPhone is running the Operations dashboard, HUD/Attention Inbox plumbing, Personal Notecard, World tab, and Live Activity extension.
- a 100-world randomized JARVIS-20 world-model fuzz run completed at **100 / 100 worlds passed** during the current deployment cycle.
- a recent full Python regression run completed with **108 tests passing** before the final Calendar/goal-routing fixes; later fixes added additional targeted regression tests, so a fresh full-suite run is still required before treating the present Git head as a release candidate.

Deployment validation is not finished. Remaining device/runtime checks include transport failover/deduplication, authoritative-deletion edge cases, explicit snapshot privacy inspection, local-iPhone routing, room-microphone behavior, welcome-back behavior, current Ray-Ban hardware behavior, navigation/Notecard behavior, and a final representative real-world acceptance pass.

### Convergence scope — proposed merge, not observed deployed

This README preserves the September 20 bench experiment and roadmap while
reconciling the tested source histories on a draft PR against `main`.
Published `main` stays at `5599b6f` until that PR is reviewed and merged.
The September 7 Windows/iPhone observations and September 20 independent
servo bench remain historical, configuration-specific evidence; **no new
physical-device exercise is inferred from this source merge**.

### Physical actuation bench — September 20, 2026 (Pacific)

A separate **MacBook Air + CrunchLabs Nano + IR Turret PITCH servo** prototype was physically exercised. The Nano accepted a custom Arduino sketch, obeyed angles 60/90/120 from Arduino IDE's Serial Monitor, then obeyed the same class of commands sent by Python 3.9.6/pyserial over USB. A Flask HTTP server on the MacBook subsequently moved the servo from local browser requests and returned the Nano's `DONE` acknowledgement. The exact experimental configuration, safety boundaries, and next integration steps are documented in [Experimental physical actuation](#experimental-physical-actuation-crunchlabs-ir-turret). **Jarvis's Windows backend has not yet been connected to this hardware**; Tailscale setup/remote access was pending at the last verified checkpoint.

### Version-number caveat

`pyproject.toml` and the HTTP health payload still report package version `0.13.0`. That string originated before the unified world-model and current iPhone work and is **not** a reliable description of present feature maturity. For development and deployment, use the Git commit SHA as the real build identity until semantic versioning is intentionally reset.

---

# What Jarvis is trying to become

The target user experience is ambient and operational rather than app-centric.

A finished interaction should look more like this:

```text
User puts on the glasses.
Jarvis: “Welcome back, sir.”

Jarvis notices an upcoming meeting, a revised document, and an overdue dependency.
Jarvis: “Your Apollo call is in twelve minutes. Daniel sent the schedules,
         but the new draft still says 15% while yesterday’s discussion said 10%.”

User: “Take me to Nobu Malibu.”
Jarvis: “Certainly.”
[turn-by-turn guidance begins]

User: “Email Daniel and ask him to confirm the cap.”
Jarvis: [asks for confirmation]
User: “Confirm.”

Later:
User: “Did that work?”
Jarvis: “Yes, sir. I independently verified the message in Sent Mail.”
```

The phone, glasses, PC, world model, tools, and background services are different interfaces around the same agent—not independent assistants with separate memories.

---

# System architecture

```text
                               PRIVATE USER WORLD
                                      |
                 +--------------------+--------------------+
                 |                    |                    |
             wearable             iPhone              private data
             sensors              context             + PC state
                 |                    |                    |
        Ray-Ban camera/mic   Calendar/Contacts      Gmail / Calendar
        Ray-Ban speakers     reminders/goals       notes / meetings
                             motion/location        browser / apps
                             Known People           jobs / documents
                             Notecard               conversations
                 |                    |                    |
                 +--------------------+--------------------+
                                      |
                                      v
                         AUTHENTICATED COMPANION LAYER
                         local-first routing / Tailscale
                                      |
                                      v
                             WINDOWS JARVIS HOST
                                      |
                +---------------------+---------------------+
                |                     |                     |
             models                tools                memory
      Qwen / Moondream /       Google / browser       world model
       Kokoro / embeddings      Windows / sandbox      vector memory
                |                     |                     |
                +---------------------+---------------------+
                                      |
                                      v
                            PERSISTENT WORLD MODEL
                   entities / identities / aliases / events
                  beliefs / commitments / relations / documents
                   terms / intentions / attention / decisions
                       action attempts / verification state
                                      |
                                      v
                         SITUATIONAL / EXECUTIVE LAYER
                           “what matters right now?”
                                      |
                                      v
                               PERMISSION GATE
                                      |
                                      v
                                  ACTION
                                      |
                                      v
                          INDEPENDENT OBSERVATION
                                      |
                                      v
                         VERIFIED UPDATED WORLD STATE
```

The causal loop Jarvis is built around is:

```text
world state
  -> persistent intention
  -> attention
  -> decision
  -> permission-aware proposed action
  -> action attempt
  -> expected outcome
  -> independent observation
  -> verified / failed / timed_out / unverified
  -> updated world state and Executive priority
```

---

# Core design invariants

These principles are more important than any individual feature.

### 1. Local first

Private reasoning, memory, perception, voice synthesis, and tools should run locally when practical. External services are used deliberately, not as the default place to copy the user’s life.

### 2. One world model

A goal created on the iPhone, a Gmail sender, a Calendar attendee, a Known People identity, an attachment revision, a meeting, and a tool outcome should be able to refer to the same persistent entities.

### 3. Provenance over vague memory

Important facts are represented with where they came from, when they occurred, confidence, and revision/conflict state. Jarvis should be able to explain why it believes something.

### 4. Explicit authority

A language model is not the authority boundary. The permission layer is. A better model does not receive broader permissions.

### 5. Tool success is not real-world success

When an action can be independently observed, Jarvis does not call it complete merely because an API returned success.

### 6. Privacy is enforced structurally

The iPhone world-snapshot bridge has an explicit contract that excludes biometric feature prints, enrollment photos, raw camera/audio buffers, clipboard contents, incident media, and privacy-zone coordinates.

### 7. No hidden biometric/affective claims

Known People is closed-set and opt-in. Audio does not identify people by voiceprint and does not infer emotion, deception, stress, or mental state.

### 8. No unrestricted host shell

The model does not receive a general Windows terminal. Generated code/commands run in an isolated Docker sandbox under a security-class permission gate.

### 9. Deterministic control around high-risk seams

Critical state questions, permission decisions, action verification, research auditing, snapshot reconciliation, and Executive priorities are not left entirely to unconstrained model improvisation.

### 10. The finish line does not move

The project has a frozen twelve-criterion Definition of Done in `FIXED_ENDPOINT_ACCEPTANCE.md`. New features after those criteria are enhancements, not a thirteenth criterion.

---

# Hardware and software requirements

## Windows backend

The primary host is Windows 11. The Python package declares Python `>=3.12`; the current deployment uses Python 3.14.

Recommended/used components:

- Windows 11
- Python 3.12+ (3.14 currently used in deployment)
- Ollama
- NVIDIA GPU for best local-model/TTS performance, though not every component strictly requires one
- WSL for the current Kokoro service path
- Docker Desktop for the isolated Python/terminal sandbox
- Tailscale for private remote connectivity
- Chromium/Opera integration where browser tools are desired
- Google OAuth credentials for Gmail/Contacts/Calendar
- Serper key for web search

## iPhone

The current companion is a native SwiftUI app built from `ios/JarvisIOS.xcodeproj`.

The app uses Apple frameworks including Speech, AVFoundation, Vision, MapKit/CoreLocation, Contacts, EventKit, Reminders, Core Motion, Sound Analysis, Translation, CryptoKit, ActivityKit/WidgetKit, and optional Health data paths. A modern iPhone running the supported iOS deployment target is required.

## Ray-Ban Meta glasses

Compatible Ray-Ban Meta hardware is used for:

- wearer-facing microphone input over Bluetooth HFP;
- speech output through the glasses;
- camera frames through Meta’s Wearables Device Access Toolkit (DAT).

The project treats DAT availability as an external platform dependency and does not pretend it is a perfect on-head presence sensor.

## Mac/Xcode

A Mac with current Xcode is required to build/sign/install the iPhone companion and its Live Activity extension. Separately, a MacBook Air has been used as a USB-connected experimental physical-actuation host; this does not make the Mac a replacement for the Windows reasoning/tool host.

---

# Experimental physical actuation: CrunchLabs IR Turret

> **Status: working local bench prototype; not yet a Jarvis tool or a deployed remote actuator.** Verified September 20, 2026 (Pacific). This section records an independent hardware experiment and an integration proposal, not an additional fixed-endpoint acceptance criterion.

## Purpose and verified path

The experiment establishes that software can command real physical motion using inexpensive, USB-connected hardware. It is a potential future output modality for Jarvis: pointing, pressing a lightweight button, or other bounded, permission-controlled physical interactions. The immediate result is **one functioning positional axis**, not a completed robotic arm, autonomous tracker, or remotely available Jarvis action.

```text
Browser on MacBook Air
  -> Flask local API (127.0.0.1:8765)
  -> pyserial (/dev/cu.usbserial-110, 9600 baud; example device path)
  -> Nano programming USB-C port
  -> D11 pitch control signal, with separate servo power/ground
  -> #2 PITCH servo moves
  -> Nano prints "Moving to <angle>" and "DONE"
  -> Flask reports success based on the Nano's serial acknowledgement
```

The browser requests `http://127.0.0.1:8765/pitch?angle=60` and `?angle=120` were tested and caused distinct physical motion. This local HTTP service is **not** the Windows Jarvis FastAPI service, even though both prototypes use port `8765` on different hosts.

## Hardware available and wiring learned

Two CrunchLabs Hack Packs were on hand: **IR Turret** and **Laser Synthesizer**. The combined parts include two Nano-class controller assemblies, two portable battery packs, three Turret servos labeled YAW/PITCH/ROLL, an IR remote and receiver, X/Y resistive touch surface, an IR proximity/reflectance sensor, potentiometers, laser, speaker, cables, and mechanical components. The Laser Synthesizer's Bluetooth/audio board was accidentally damaged and is **not available** for this project; Bluetooth or BLE data transport must not be assumed.

Only the **#2 PITCH** servo has been electrically and functionally validated in the new setup. The tested Arduino pin is **D11**, established by actually moving the motor using `Servo.attach(11)`. Its green lead is the servo signal; red is servo power; black is ground. The Turret's multicolored four-wire jumper carries the signal separately from the red/black supply wiring. Preserve the working physical connections; do not infer that adjacent headers, other motors, or similarly shaped connectors share the same pinout. The uploaded Turret booklet, especially build steps **28–32 on pages 16–19**, is the original assembly reference.

The carrier has **two distinct USB-C connections**: the power assembly's USB-C can power the board, but the USB-C **on the Nano itself** is the one that made the device appear in Chrome's CrunchLabs IDE and on the Mac serial port. On the Mac, it appeared as `/dev/cu.usbserial-110`; this path may change after reconnection. The Anker Prime desktop charger displayed `0.0 W` for an idle Nano, which is a meter-resolution observation, **not** evidence that the Nano received no power or proof of electrical safety.

Power off/unplug before rewiring. Avoid stalled servos, tight mechanical stops, exposed connector shorts, and relying on the USB power display to protect components. Keep the loose PITCH servo unloaded until a mount and travel limits have been checked. Do not use the laser as a roaming room pointer without a controlled eye-safe optical arrangement.

## How the working prototype was established

1. Connected the Nano's **programming** USB-C port to the MacBook Air and selected `CrunchLabs Nano (#1)` in the CrunchLabs web IDE. A one-second `LED_BUILTIN` blink test compiled, uploaded, and blinked successfully.
2. Wired the #2 PITCH servo using the Turret hardware and confirmed the motor moved from a `Servo.h` sketch using `attach(11)`.
3. Replaced the sweep sketch with serial angle control. Arduino IDE 2.3.10 selected **Arduino Nano** and the `/dev/cu.usbserial-110` port. Unlike the CrunchLabs page's observed monitor, Arduino IDE's Serial Monitor offered a text input; commands `90`, `60`, `120` physically moved the servo.
4. Python 3.9.6 on the MacBook installed `pyserial`, opened the port at 9600 baud, waited approximately two seconds for the Nano to reset, sent ASCII `90\n`, and received `Moving to 90` / `DONE`.
5. A persistent Python command-line loop at `~/servo_control.py` moved the servo repeatedly. Flask was then installed and a local-only API at `~/servo_server.py` successfully moved the motor from a browser. These files and the saved CrunchLabs `.ino` sketch were created **on the MacBook**, not added to this Git repository by this documentation update.

The tested Nano firmware used `Servo.h`, D11, 9600 baud, an initial angle of 100°, a test limit of **60–120°**, and incremental 1° movement with 15 ms between steps. It prints `DONE` on completing the commanded step sequence. If reproducing the experiment, the essential serial command protocol is:

```text
Host -> Nano:  90\n
Nano -> Host:  Moving to 90
Nano -> Host:  DONE
```

Messages must end with a newline. The Arduino serial port can normally have **one owner at a time**: close Arduino IDE's Serial Monitor and the CrunchLabs monitor before starting the Python client/server. Opening the Python serial connection can reset the Nano; wait for boot before issuing commands.

### Reproducing the working MacBook-side controls

```bash
python3 --version                    # tested on 3.9.6
python3 -m pip install --user pyserial flask

# On this MacBook, while no other serial monitor has the port open:
python3 ~/servo_control.py           # interactive: type 60, 90, 120, or quit

# OR, after exiting the interactive controller:
python3 ~/servo_server.py            # keeps the serial port open
```

With the server running, on the **same MacBook**:

```text
GET http://127.0.0.1:8765/health
GET http://127.0.0.1:8765/pitch?angle=60
GET http://127.0.0.1:8765/pitch?angle=120
```

The experimental `/pitch` handler rejects missing, non-integer, and out-of-range angles; serializes requests with a lock; sends `<angle>\n`; and waits up to approximately four seconds for `DONE`. The `/health` handler checks the Python serial object's `is_open`, which is **not** a live servo-function test. `DONE` proves the Nano processed the command; it is **not independent confirmation** that the shaft actually reached the commanded angle, since there is no separate angle sensor or observation loop.

The initial Flask server binds to **`127.0.0.1` only**. This is intentional. Its present `GET /pitch` operation causes motion and has **no authentication**; it is a local experiment, not a safe remote-control endpoint.

## Next integration: MacBook Air -> private Tailscale -> Windows Jarvis

At the last checkpoint, Tailscale was **being downloaded on the MacBook Air**. The Mac's Tailscale IPv4 address was not yet confirmed and the server was not reachable from Jarvis's Windows PC. Do not record an invented address or describe cross-machine control as working.

Recommended sequence:

1. Confirm both MacBook and Windows host are authenticated to the intended tailnet and can reach one another; inspect the MacBook's current Tailscale IP.
2. Evolve the **Mac** service before making it remotely reachable: prefer authenticated `POST` for motion (not unauthenticated state-changing `GET`), add a narrow actuator-specific credential, bounded rate and range limits, and explicit error/fail-safe behavior. Bind to the Mac's **Tailscale interface/address only**, not `0.0.0.0`; do not port-forward the service onto the public internet. Account for Mac sleep/disconnect and servo power loss.
3. Test from the **Windows PC** through Tailscale, then implement a narrowly scoped Jarvis physical-actuation tool. Route tool calls through the existing permissions/action-audit layer rather than letting model-generated text choose arbitrary URLs, pins, speeds, or angles.
4. Represent requested command, Nano acknowledgement, and any separately sensed physical result as **distinct evidence** in Jarvis's world model. A successful HTTP 200/`DONE` is not verified external-world motion.
5. Only after a safe single-axis loop works remotely, consider connecting other Turret motors, calibrating joint directions/mechanical stops, and designing an actual pointing/manipulation mechanism. YAW and ROLL behavior and wiring have **not** been validated in this session.

This adds a possible **physical action tool** without changing the project's fixed twelve-criterion finish line or claiming the experimental MacBook server is already part of the main Windows backend.

---


# Cross-branch capability ledger and forward roadmap

> **Convergence review — September 24, 2026; based on September 20 historical ledger.** This section unifies the core README, the separate `jarvis/agency-1.0` and `jarvis/memomind-prep` lines of development, the bench-tested CrunchLabs actuator, and the longer-term physical-world/Jarvis “superpowers” design. **The currently published `main` remains at `5599b6f` until the draft convergence PR is reviewed and merged. The proposed merge commit contains Agency, MemoMind-prep, Conductor, Mission Control, Reality Mesh/Graph, Reality Lens and Life Fabric. CI is not live-provider, Windows, glasses, or physical-iPhone acceptance.** Read the statuses below before treating any example as an instruction Jarvis can perform today.

## Source-of-truth and status conventions

**Git ancestry verified for this convergence candidate:** `jarvis/agency-1.0` is an ancestor of `jarvis/memomind-prep`; `jarvis/human-extension-v1` is an ancestor of `jarvis/life-friction-fabric`. The convergence merge preserves both feature histories and the two main-only September 20 README commits. No existing branch is deleted. Before human approval of this PR, `main` at `5599b6f` remains the published code baseline. After a merge-commit PR merge, these candidate features move from **Branch source** to **source in main, CI verified**; none is upgraded to **Observed deployed** by CI, the draft PR, or Git history.

Status terminology used here:

| Label | Meaning |
|---|---|
| **Observed deployed** | A specifically described physical device, real provider, or running host was exercised; the observation applies to that configuration and date only. |
| **Bench verified** | A small real hardware/software loop worked independently of the Jarvis deployment; not an integrated Jarvis tool. |
| **Branch source** | Implemented on a development branch (including this proposed merge branch until its PR is merged); source/tests or simulator coverage is not deployed-device acceptance. |
| **Source in main (CI verified)** | Applies only after the draft convergence PR is actually merged; the code is included in `main` and the stated CI ran against the exact integration merge SHA. It is not a deployment claim. |
| **Integration pending** | Components exist, but their cross-machine or cross-subsystem end-to-end connection has not been demonstrated. |
| **Roadmap** | An intentional future capability, not current software behavior, device capability, provider entitlement, or delivery commitment. |
| **Unsupported / conditional** | Depends on hardware, SDK permissions, usable third-party sources, lawful/authorized access, platform background rules, or acceptable latency/cost. |

**Authoritative working documents:** [Agency A1–A12 acceptance contract](https://github.com/US0RIS/Jarvis-for-MRB/blob/jarvis/agency-1.0/AGENCY_ACCEPTANCE.md), [MemoMind and camera-free sensor preparation](https://github.com/US0RIS/Jarvis-for-MRB/blob/jarvis/memomind-prep/ios/MEMOMIND_PREPARATION.md), [external evidence/remote-camera/provider coverage](https://github.com/US0RIS/Jarvis-for-MRB/blob/jarvis/memomind-prep/EXTERNAL_EVIDENCE_OPERATIONS.md), and [deterministic/model-free routing audit](https://github.com/US0RIS/Jarvis-for-MRB/blob/jarvis/memomind-prep/MODEL_FREE_OPERATIONS.md). The following consolidates their design and expands the future end state without silently promoting planned functions into delivered ones.

## Capability coverage at a glance

| Domain | Published `main` @ `5599b6f` (pre-review) | Source on proposed merge commit (status: **Branch source** until PR merged) | Next gate / end state |
|---|---|---|---|
| Windows + iPhone core, Gmail/Calendar, voice, world model | **Observed deployed** only for specifically documented September 7 configuration and tests | Included with existing baseline and additional automated CI | Revalidate real devices and provider authorization at exact deployed SHA |
| Agency 1.0 persistent goals, plans, approvals, verification | Not in published `main` | Agency branch is an ancestor of the feature line; source/tests carried forward; A1–A12 REAL campaign **not complete** | Actual same-SHA Windows/iPhone REAL acceptance and release check |
| Guardian, Counterfactual Guardian, Goal Guardian | Not in published `main` | Opt-in evidence-backed deadline/warning loops | Foreground/background and true provider/device acceptance |
| Mission Control | Not in published `main` | iPhone appointment journey mission, Maps handoff, GPS arrival observations | Verify physical iPhone, location permissions and provider behavior; proximity is not attendance |
| Conductor | Not in published `main` | Bounded one-use, exact selected Mac/Windows benign app-launch missions | Real paired host/phone acceptance; not general remote computer control |
| Reality Mesh | Not in published `main` | Exact paired nodes, short private view-only screen, supported public-source observations | Real node availability and screen consent; no arbitrary machine or global camera |
| Reality Graph | Not in published `main` | Deterministic source-qualified place/mission graph and model-free readback | Actual provider onboarding, identity verification and coverage calibration |
| Reality Lens | Not in published `main` | Explicit saved environmental scalar snapshot and foreground tactile source-diff cue | Actual iPhone haptic + live provider verification; no background omniscience |
| Life Fabric | Not in published `main` | Explicit deadlines, handoffs, assets, task receipts, transition templates and friction records | Real providers, user tenancy/security design and device deployment before automation claims |
| Camera-free ambient input and enrolled HomeKit lights | Not in published `main` | Limited source and exact user-approved lights/readback source paths | Physical phone/HomeKit, mic/location consent, interruption testing |
| Official public cameras, USGS/NWS/OpenSky counts, OSM, SEC/EPA/OFAC | Not in published `main` | Bounded documented regions and providers; no AIS/remote CCTV entitlement | Independent source/authorization review and real provider acceptance |
| Deterministic small-model offload, MemoMind bridge | Not in published `main` | Specific model-free cases, simulated HUD and optional glasses I/O code | Benchmarks, actual MemoMind SDK/hardware, non-simulator acceptance |
| CrunchLabs pitch-servo bench | **Bench verified** Sep 20, separately, not an integrated Jarvis tool | Main's independent bench documentation preserved in this candidate | Authenticated integration, safeguards, independent position readback |
| Presence robotic telepresence, AIS and universal physical-world actuation | **Roadmap** | **Roadmap**, no fabricated enabled interface | Actual authorized robotics/provider hardware and measurable acceptance |
| ForgeCAD | Separate repository, outside this convergence | Separate repository, untouched | Separate review and release process |

### Main principle: ambient first, camera optional

The central cinematic-Jarvis aspiration is **proactive understanding and useful intervention**, not a camera permanently looking around a room. The primary input strategy is **authorized audio and sensors**: microphones when the user has opted in and iOS provides capture; fresh GPS/geofences, movement/IMU, time/calendar/context, opt-in Health/Watch data, temperature/weather models, home accessory state, and external public events. The system must function with **no glasses at all**, with Gen 1 Ray-Ban Meta glasses as microphone/speaker hardware, and eventually with camera-free MemoMind hardware. Meta first-person vision, a phone camera and official public cameras remain **optional distinct perception paths**, not prerequisites for conversation, planning, reminders or actuation.

Examples of intended causal opportunities—not blanket existing autonomous behavior:

- After a real away→home transition, the user-enrolled light turns on; a fresh accessory readback records what the light *reported*. The branch implements this **limited** case with separate opt-ins, deduplication and revocation.
- At a relevant approaching deadline or meaningful external change, Jarvis recalls the active objective, checks what is truly different, and interrupts only if action is warranted. Routine changes stay queryable.
- A microphone sound classification, outdoor temperature model or aircraft event may trigger a **candidate** suggestion. It cannot authorize unlocking, buying, contacting someone or inferring a diagnosis/intent.
- A physical pointer might move toward a user-approved coordinate after explicit calibration; absent a spatial sensor, Jarvis cannot claim to know where a particular object is.

The future decision loop is:

```text
authorized persistent goal + explicit device affordances/policy
    + fresh audio/geographic/temporal/home/health/public-event evidence
    -> source-labelled, uncertainty-aware opportunity proposals
    -> deterministic capability + permission + interruption checks
    -> execute bounded/reversible action or request exact approval
    -> independently observe what changed
    -> update the world model, rollback/escalate if possible, or retry within policy
```

This is the desired *emergent-feeling* cinematic experience: responsive physical and digital help with minimal micromanagement, not uncontrolled autonomy or fake omniscience. No global continuous microphone capture, unconsented bystander recording, raw-audio hoarding, guessed health inference or supposed always-on iOS execution is part of the design.

## Agency 1.0: persistent executive, not a single planner call

The Agency 1.0 history (already an ancestor of this merge candidate) contains code and an explicit acceptance framework for durable desired states/plans and plan steps, authorized observations/actions, approval resumption, verification reconciliation, replanning, dormant wake watches, parallel evidence/skeptic/feasibility/risk workers, exception-based attention, capability-gap detection and sandboxed adapter drafting, counterfactual branch preservation, and an evidence-bearing self-model. The agent must distinguish user facts, preferences, hard policies, objectives, inferred tradeoffs, decisions, and corrections. Inferences can guide reversible options but never silently widen protected action authority.

**Agency 1.0 is not marked released.** Its [contract](https://github.com/US0RIS/Jarvis-for-MRB/blob/jarvis/agency-1.0/AGENCY_ACCEPTANCE.md) requires A1–A12, including REAL gates on one deployed Windows/iPhone SHA and environment: restart continuity; multiple real action/observation cycles; approvals and denials; independently verified external outcomes including failure; plan invalidation; dormant goal wake-up; genuinely parallel disagreement; deduplicated attention; enabled-only narrow tool synthesis; preserved counterfactual alternatives; preference vs authority; and the A12 “one decision” chain that needs no human intermediate orchestration. Source/tests or a synthetic acceptance pass are **insufficient**.

Release procedure, on the **actual deployment after all qualifying REAL receipts**, is `jarvis-agency-release-check --full`. Never claim `release_ready:true` without that tool's qualifying, current same-SHA evidence. Work on this branch should close an acceptance gate, make a gate falsifiable, or repair a regression, not endlessly add an unrelated feature.

## Model-free hardening and conversation

In the proposed merge (originating on `jarvis/memomind-prep`), shared streaming/non-streaming deterministic dispatch handles defined, explicit Gmail/Calendar queries and writes, PC/browser/status/world reads, basic reminders and arithmetic/time, bounded read-only workflows, evidence-only briefings/journals, query cleanup, research-query family construction, structured meeting-action lines and simple observable-goal contracts. The user request's literal proper nouns, negations, date windows and recipients must be retained. A no-match falls back to model interpretation; hardcoded behavior must **not fabricate a recipient or infer authorization**. Existing permission gates and post-action readback continue to apply.

The same branch revises Jarvis's conversational voice: contextually responsive, able to offer grounded engineering/design/taste judgments where appropriate, able to disagree, fewer templated preambles or compulsory “sir,” and no pretend personal experiences. This is a **style/dispatch improvement**, not permission for the model to manufacture actions or facts. Ambiguous follow-ups, unfamiliar evidence, independent research synthesis, genuinely new workflows, complex deliberation and perception still need capable models or real source adapters. The authenticated `GET /routing/status` counters cover specified planner bypasses, not a universal “Qwen-free Jarvis” percentage. See [MODEL_FREE_OPERATIONS.md](https://github.com/US0RIS/Jarvis-for-MRB/blob/jarvis/memomind-prep/MODEL_FREE_OPERATIONS.md).

## Physical perception and a global external evidence graph

### Public cameras: from one region to “remote eyes”

The implemented **candidate-merge source** camera provider is official **Caltrans CWWP2**, with district catalogs, a bounded still-image fetch, explicit one-frame Moondream interpretation, an iPhone Physical tab, selected remote-region coordinates, and watches. It does **not** have EarthCam automation, worldwide CCTV, arbitrary IP-camera access, verified capture-time/live status, generalized multi-camera continuous video analysis, ALERTCalifornia access or arbitrary internet-camera scraping. The media provider's published image may be stale or offline even when catalog metadata lists the camera. A visible smoke classification from two distinct images is a **possible visible condition**, not independent confirmation of a wildfire.

Future adapters should prioritize documented official/publicly viewable and permitted sources, including, where available, government DOT/traffic, wildfire observation, ski/mountain-pass, harbor/coastal, public weather and other opt-in feeds. “Show me Melbourne,” “watch this mountain pass,” or “is that beach crowded?” should first discover a **verified usable source** for that area, return “not covered” if none exists, obtain fresh source timestamps when available, then perform narrow perception. Arbitrary CCTV, private/security cameras, LAN scanning of strangers' devices, bypassing logins, blind URL guessing, person/license-plate surveillance and source-rights violations are not substitutes for coverage.

Cameras should serve an explicit question or watch. They should not become the whole architecture or an excuse to make MemoMind depend on camera hardware.

**Boundary decision (September 2026):** the provider-expansion roadmap above — additional state DOT camera feeds, ALERTWildfire, harbor/coastal webcams, and similar — stays limited to official, publicly accessible camera catalogs the operator has rights to view, following the same allowlisted-host, cached-catalog, single-still shape as the Caltrans adapter. A proposal to instead stream arbitrary or private RTSP/CCTV feeds, perform cross-camera person or vehicle tracking, or otherwise build toward general surveillance capability was considered and explicitly declined. That is not a scope difference from the paragraph above; it is the same "no arbitrary CCTV, no person/license-plate surveillance" line already stated there, restated here because it was directly proposed and rejected rather than just never attempted.

### Aircraft, ships and places: the movement graph

The desired graph correlates **publicly observable moving entities** with source, time, confidence, geography and explicit user-selected regions:

```text
source event (ADS-B/MLAT, AIS, official transport/incident)
  -> entity (aircraft, vessel, transit vehicle or relevant place)
  -> position / heading / speed / observed-at / provider-time / freshness
  -> bounded history and change detection
  -> user-selected POI / proximity / route intersection
  -> eligible alert / read-only answer / permission-gated action
```

Existing branch source currently offers **OpenSky regional aircraft counts**, not a verified individual flight-tracker UI, tail-number history, passenger insight, aircraft ownership or global real-time coverage. **AIS vessel tracking is roadmap.** Independent adapters would need documented provider terms/quotas, appropriate polling, track-identity reconciliation, stale/duplicate observations, uncertain gaps, and attribution. Alerts should answer “what is near me/this place?” or “what changed?” without claiming private itineraries or correlating people with observed aircraft/vessels absent legitimate evidence and authority. Specific commercial flight status and raw aircraft telemetry are different products and must not be conflated.

### Other evidence surfaces

`jarvis/memomind-prep` adds one-shot and watchable public-source context, including USGS quake events, supported US NWS alerts, Open-Meteo modelled air/UV (and temperature for opted-in ambient opportunities), OpenStreetMap mapped toilets/water/AEDs, and provenance-bearing, expiring personal watches. Global weather-model coverage does not make NWS alerts global; mapped AED existence does not establish accessibility or emergency suitability. Provider outage or no event is **not** a safety all-clear.

Its opt-in, locally separated matter-specific diligence surface covers exact verified SEC CIK submissions/XBRL, EPA ECHO FRS facility snapshots and local OFAC SDN *candidate* screening. It is not a full legal, accounting or sanctions opinion and does not imply connected PACER, court, UCC, county, corporate registry or OSHA sources. Future professional integrations require separate authorization, data licensing, matter isolation, real-record matching and provenance. General personal-world metadata may not silently absorb confidential matter source records. See [EXTERNAL_EVIDENCE_OPERATIONS.md](https://github.com/US0RIS/Jarvis-for-MRB/blob/jarvis/memomind-prep/EXTERNAL_EVIDENCE_OPERATIONS.md).

### Shared standing-watch and alert engine

The long-term capability is to define a place, asset, person-authorized device, route, condition, or project objective once and have Jarvis recheck only approved, actually available sources at an appropriate rate. Preserve baseline vs change, retrieval vs actual observation time, source URI and rights, independent checks, expiring retention, deduplication, quiet hours, alert thresholds and a clear stop/revoke control.

The branch-source watch implementation is **finite, user enrolled and scoped** (including <=7-day expiries and >=15-minute camera polling), not limitless passive global monitoring. The general world graph receives bounded **personal** watch metadata; isolated matter records stay in matter/watch stores. Use evidence receipts to avoid repeated alerts on identical stills or the same aircraft/event record. Expand from provider-specific adapters; don't pass arbitrary live URLs to vision/network tools.

## Multiple computers, iPad-first UI and device control

The intended primary portable interface remains the **iPad** when convenient; the iPhone, desktop, Ray-Bans and future MemoMind are other surfaces around **one** Jarvis world model. The Windows RTX desktop is the reasoning/AI host; the M5 MacBook Air and M4 Mac mini may act as authorized companion/physical nodes. They are different rooms/devices, so room-bound CCTV or a projector must not be a dependency.

Future cross-device actions include authenticated screen/control sessions, routing a desktop onto the iPad, focusing apps across hosts, moving files safely, and—**only if a concrete implementation allows it**—natural drag/transfer semantics across operating systems. Current PC/browser tool integration is not proof of universal remote desktop, virtual display, OS-native drag-and-drop, low-latency multi-host compositor or permissions to operate everything on every machine. Use supported transport/protocols, explicit pairing and grants, per-host capability inventories, clear active-session indicators, clipboard/file permissions, reconnection rules, and the existing action audit. Avoid jailbreaking or permanently modifying the devices just to simulate seamlessness.

The iPad UI should prioritize: glanceable world/alerts; conversational follow-ups; Physical/public source selection and controls; remote-desktop launch and routing when implemented; and bounded “watch this place/device” jobs. The projector is optional, not central to the product.

## MemoMind, KiWear and glasses-independent design

**Existing:** Gen 1 Ray-Ban Meta microphone/speaker route and optional DAT vision; no Ray-Ban lens HUD. **Branch-source:** `ios/MemoMindBridge.swift` and iPhone glasses simulator; bounded HUD cards, semantic tap/head/ring event mapping, read-only authenticated Agency Command View, and optional redacted notifications/replies. It begins honestly at **“Simulator only.”** Glasses/ring selection does not silently approve a protected action.

**Conditional future:** physical MemoMind One support, KiWear ring and any SDK-permitted HUD/touch/IMU/microphone/speaker integration. MemoMind is camera-free. Wait for the actual vendor SDK/protocol and supported iOS/Memo Lab bridge; do not invent BLE services, pairing success, microphone access, background audio guarantees or a HUD on Gen 1 Meta. Preserve compatibility **without glasses**. Far-field/bystander capture and recording need separate permissions and real capability testing, and continuous passive labels must not be misrepresented as perpetual authorized recording.

## Physical action: from a bench servo to a useful effector

The [CrunchLabs section](#experimental-physical-actuation-crunchlabs-ir-turret) documents **one verified local servo axis**; it is the canonical reproduction record. The Windows Jarvis ↔ MacBook ↔ Nano link and permission-gated Jarvis tool remain **integration pending**. Do not say “Jarvis moved the servo” merely because a human-operated browser did.

Next stages: confirm MacBook Tailscale; add an authenticated/POST-only narrow Mac actuator endpoint bound privately; verify Windows-to-Mac transport; register a typed pitch-angle tool with strict limits, timeouts, stop/revoke behavior, audit and explicit authority; distinguish serial `DONE` from measured physical motion. Then calibrate YAW/PITCH/ROLL individually and design an interchangeable lightweight pointer/button-pusher/gripper **only as mechanics permit**. Later sensor input might enable closed-loop targeting/press verification. No unguarded autonomous laser aiming or dart firing, particularly around people/animals. Motor load, USB supply/servo power budget, travel stops and force limits remain real constraints.

The purpose is not to turn every leftover Hack Pack component into a novelty. The target is an incremental **general-purpose physical affordance**: software can interact with selected objects that have no ordinary API, starting with lightweight, bounded operations.

## Deployment and integration order

| Stage | Deliverable and proof required |
|---|---|
| **1. Preserve current working baseline** | Keep existing Windows/iPhone Jarvis functional, the MacBook Nano sketch/serial/Flask local bench reproducible, and exact Git SHA/environment recorded. Document which branch each running device is actually on. |
| **2. Reconcile branches deliberately** | Compare `main`, Agency, MemoMind-prep, and separate ForgeCAD work before merging; resolve overlapping service/agent/iOS changes and update README descriptions to the merged commit. Do not merely combine prose or silently replace `main`. |
| **3. Revalidate the real deployment** | Run full tests, migration/world diagnostics, target-device build and provider checks; perform Agency's required same-SHA REAL gate campaign and release check before claiming Agency 1.0 complete. |
| **4. Establish camera-free proactive loop** | On a real iPhone, verify opt-in audio/GPS/motion/Health/modelled temperature and bounded preapproved HomeKit light action, including app suspend/permission revocation and accessory readback. Keep optional cameras out of the critical path. |
| **5. Accept external adapters region by region** | Exercise actual Caltrans/OpenSky/USGS/NWS/Open-Meteo/OSM and diligence providers; verify quotas, terms, timestamp freshness, source failures and retention. Add further public eyes, AIS, individual ADS-B and incidents only with documented feeds. |
| **6. Connect physical node** | Finish private Tailscale and authenticated Windows↔MacBook↔Nano control, explicit one-axis command/stop tests, failures and audit; then calibrated additional axes. |
| **7. Deliver an integrated iPad / wearable surface** | Use current iPhone/Meta routes first; add true Mac/Windows remote-desktop/session control and real MemoMind driver only after authorized SDK/protocol and hardware tests. |
| **8. Prove proactive usefulness** | Use representative end-to-end scenarios: genuine external event or sensed opportunity → relevant persistent goal → warranted suggestion/action → permission check → independently measured outcome → nonduplicated alert and updated world state. |

### Example acceptance stories for the longer-term end state

**Remote place:** “Watch this mountain pass for congestion until tomorrow.” Jarvis resolves geography, identifies a real permitted source, shows current coverage/freshness, asks about an expiring watch if needed, saves baseline, deduplicates observations, and tells the user when evidence changes. Unsupported regions report the actual gap rather than fabricate imagery.

**Movement:** “Tell me if an aircraft enters the area near this place” or “What ships are approaching this harbor?” Source-specific aircraft/AIS adapters locate moving entities and calculate bounded proximity using timestamped observations. Aircraft counts alone cannot satisfy the individual-track story; ship tracking remains impossible until an AIS source is integrated.

**Ambient home:** An enrolled light turns on after a genuine arrival; no action occurs on the first at-home location fix, stale geofences, revoked access or an unrelated sound. HomeKit state readback and its limits are recorded.

**Physical Jarvis:** “Move the pointer to its calibrated rest position.” Windows Jarvis invokes an authenticated narrow tool, MacBook confirms Nano receipt and a separate sensor or human observation confirms actual placement before marking real-world success. The present local browser test does not satisfy this scenario.

**Remote workflow:** “Bring the Windows workspace to my iPad and open the relevant document.” An explicitly authorized host session is activated with visible device and file permissions; control does not imply that raw desktop content is automatically ingested into long-term memory.

**Agency:** “Keep pursuing this bounded outcome; interrupt me only when you need a decision.” Jarvis preserves the objective across restart, observes authorized sources, does safe work, stops at exact confirmation boundaries, independently checks changes, handles an injected failure or changed premise, and stops after documented satisfaction.

### What “everything” does **not** mean

This roadmap records the agreed direction and major capability families without promising unrestricted surveillance, access to private CCTV, universal desktop control, unlicensed third-party data, private-flight passenger identity, omniscience, indefinite always-on phone sensing, or physically unsafe robotic behavior. It does not mark code-ready, deployed, source-backed, permitted and independently verified as synonyms. New ideas should be entered with status, dependencies, proof obligations, and relevant branch, then only upgraded to **observed deployed** after an actual test.

---

# Backend installation and update

## Clone

```powershell
git clone https://github.com/US0RIS/Jarvis-for-MRB.git
cd Jarvis-for-MRB
```

## Install the Python package

```powershell
py -3.14 -m pip install -e .
```

If your Python `Scripts` directory is not on `PATH`, commands such as `jarvis-world-prepare` may not resolve even though installation succeeded. The most portable form is always:

```powershell
py -3.14 -m jarvis_mrb.<module>
```

## Prepare/migrate the world model

Normal deployment should use the ordered preparation path rather than manually creating tables:

```powershell
py -3.14 -m jarvis_mrb.world_prepare
```

This performs migration, bounded pre-upgrade backup, historical backfills, relation/link processing, term reconciliation, document-version analysis, intention refresh, Executive refresh, and diagnostics.

## Run regression tests

```powershell
py -3.14 -m unittest discover -s tests -v
```

## Run isolated fixed-endpoint acceptance

```powershell
py -3.14 -m jarvis_mrb.world_acceptance_check
```

## Run world diagnostics

```powershell
py -3.14 -m jarvis_mrb.world_check
```

## Start the backend

```powershell
py -3.14 -m jarvis_mrb.service
```

The default backend port is `8765`.

For an update to an existing deployment:

```powershell
cd <Jarvis-for-MRB>
git pull
py -3.14 -m pip install -e .
py -3.14 -m jarvis_mrb.world_prepare
py -3.14 -m unittest discover -s tests -v
py -3.14 -m jarvis_mrb.world_acceptance_check
py -3.14 -m jarvis_mrb.world_check
```

Then restart the service from the same revision.

---

# Models and local AI services

Current architecture uses these model roles:

```text
qwen3:8b          low-latency routine voice/tool routing
qwen3.8:27b       higher-capability planning/reasoning/workflows/repair
nomic-embed-text  semantic episodic/unified-memory embeddings
moondream         backend vision / recent-frame semantic analysis
Kokoro-82M        local neural speech synthesis
```

Both Qwen planner paths are intended to run with thinking disabled for interactive latency unless deliberately changed.

## Model setup

The repository includes setup scripts used by the current deployment:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-persistent-ai.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\setup-kokoro-tts-wsl.ps1
```

## Kokoro

Current backend TTS defaults to Kokoro rather than the older Qwen3-TTS path.

The runtime:

- checks TTS health;
- can start the WSL service automatically;
- preflights the model files;
- can repair/download a missing Kokoro model before launch;
- monitors warm-up so a temporary startup degradation can later clear to ready;
- synthesizes WAV audio for iPhone playback.

The current deployed voice default is `bm_george`.

The Kokoro HTTP service currently uses port `8880` in the WSL setup.

## Apple on-device model

Where Apple’s on-device Foundation Models are available, the iPhone can answer bounded stable/local questions without the PC. The local model is deliberately bypassed when the task requires current web information, private PC data, external actions, or backend-only semantic vision.

---

# Google, web, browser, Tailscale, and Docker setup

## Google

Connect Gmail, Contacts, and Calendar:

```powershell
py -3.14 -m jarvis_mrb.google_auth
```

Google tool classes include:

- connection status;
- Contacts resolution;
- Gmail search/read;
- Gmail send;
- Calendar list/query/recent/conflict detection;
- Calendar creation.

Writes remain permission-gated. Gmail sends also have an exact-recipient backend allowlist; an empty allowlist blocks all outbound mail.

## Serper web search

```powershell
py -3.14 -m jarvis_mrb.serper_setup
```

The key is stored under the Jarvis app-data directory rather than the repository.

## Browser integration

```powershell
py -3.14 -m jarvis_mrb.browser_setup
```

Browser tools support bounded status/list/focus/open/close operations for the configured Chromium/Opera environment.

## Tailscale

Jarvis is designed to use private Tailscale Serve as the remote path.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-tailscale.ps1
```

**Do not expose port 8765 directly to the public Internet and do not enable Tailscale Funnel.**

Configure the resulting private `https://...ts.net` URL in the iPhone app.

## Docker sandbox

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-sandbox.ps1
```

Docker is optional for basic conversation but required for Jarvis’s isolated generated-Python/terminal execution path and some dynamic-tool repair workflows.

---

# iPhone build and configuration

On the Mac:

```bash
cd <Jarvis-for-MRB>
git pull
open ios/JarvisIOS.xcodeproj
```

In Xcode:

1. select the physical iPhone;
2. configure **Signing & Capabilities** for the main `JarvisIOS` target;
3. configure signing for the `JarvisLiveActivity` extension as well;
4. let Swift Package Manager resolve Meta Wearables dependencies;
5. build/run on the phone.

If the repository bundle identifiers are unavailable to your developer account, use a unique application identifier and a matching child identifier for the Live Activity extension.

## Backend configuration in the app

The iPhone companion expects:

- a LAN backend URL;
- optional Tailscale fallback URL;
- the bearer API token from the backend configuration;
- feature-specific iOS permissions.

The backend token is stored in `%APPDATA%\JarvisForMRB\server.json` on Windows. Treat it as a secret. Do not commit it.

## Main tabs

The current iPhone app exposes four primary tabs:

- **Jarvis** — conversation, connection, Notecard, meeting controls, response state;
- **Local** — local-first intelligence, native iPhone data, Context Capsules, timers, local verification prompts;
- **World** — Intent Radar, goals, Waiting On, world-sync status, local world graph, receipts/productivity state;
- **Packs** — capability-pack inspection/management.

The toolbar also exposes **Operations**, the Feature Guide, and Settings.

---

# Voice and conversation

## Hands-free wake

The intended conversational form is:

```text
Jarvis, <request>
```

or:

```text
Jarvis.
```

followed by the request after acknowledgement.

## Follow-up window

After a normal reply, Jarvis keeps a short conversational follow-up window open. If the user begins speaking during that window, the follow-up can continue without repeating the wake word.

The implementation is designed so speech that **starts** inside the window is not truncated just because the nominal timeout expires while the user is still talking.

## Barge-in

During Jarvis playback, user speech can interrupt the response. The iPhone:

- stops playback;
- preserves the recognized interruption;
- suppresses obvious self-echo cases;
- routes the interruption through the normal turn pipeline.

## Dictation-aware pauses

Commands that look like dictation—email bodies, URLs, spelling, longer prose—use more tolerant silence handling so normal pauses are less likely to prematurely submit an incomplete command.

## Speech vocabulary

Apple Speech contextual strings and custom user vocabulary are used to improve recognition of recurring names and terms.

## Streaming

The iPhone receives streaming backend response events and can begin presenting/speaking before the whole answer is complete.

## Deterministic state-question fast paths

Some state questions are intentionally answered from authoritative state instead of letting recent conversation bias the planner. Current examples include explicit action-outcome checks and generic current-goal queries. This prevents failures such as a Calendar conversation causing “What are my goals?” to be answered with an upcoming event.

---

# Audio routing and speech

Jarvis distinguishes **wearer audio** from **room audio**.

## Wearer-command profile

Normal hands-free commands prefer Ray-Ban Bluetooth HFP input when enabled and available. If Bluetooth microphone preference is disabled/unavailable, the app explicitly selects the iPhone built-in microphone instead of relying on a stale route.

## Room/meeting profile

Meeting Notes and Room Listening deliberately force the **iPhone built-in microphone**, because the glasses microphones are wearer-focused and often poor at hearing people across a room.

The room profile:

- uses `AVAudioSession` play-and-record;
- uses measurement mode;
- does not allow Bluetooth HFP as the capture input;
- explicitly selects the built-in iPhone mic;
- allows A2DP output where the OS supports it independently;
- fails visibly instead of silently falling back to the glasses microphone.

## Route watchdog

While room capture is active, Jarvis repeatedly checks the input route. If iOS/Bluetooth changes it, the app attempts to reassert the room profile and exposes failures in Operations/Attention state.

## TTS fallback

Kokoro is preferred when the backend service is available. Apple speech synthesis remains a fallback.

## Adaptive/forced whisper

The frontend can reduce speech delivery intensity based on local conditions or force whisper-style playback for a bounded interval.

## Ambient cues

Local earcons can signal thinking, visual activity, warnings, completion, and other states. Cue volume can adapt to measured ambient noise.

## Smart Windows audio damping

When enabled, the PC can temporarily reduce its output level during an active Jarvis conversation and restore the prior level afterward.

---

# Ray-Ban Meta integration

The iPhone integrates Meta Wearables Device Access Toolkit (DAT).

Supported architecture includes:

- device registration/eligibility through the Meta ecosystem;
- persistent DAT device selection state;
- live camera preview;
- sampled frame transfer to backend vision;
- local Apple Vision processing on recent glasses frames;
- HFP wearer microphone selection;
- response audio routed back to the wearable.

The relevant DAT selector/listener objects are kept alive instead of being recreated for each request, which reduces device-state loss around camera sessions.

## Welcome-back greeting coordinator

The “Welcome back, sir” introduction has one explicit frontend owner rather than being fired opportunistically from multiple device callbacks.

The coordinator:

- treats sustained DAT unavailable→available as a **proxy** for glasses return;
- waits for the device route to settle;
- confirms eligibility remains available;
- applies a ten-minute duplicate-greeting cooldown;
- suppresses Bluetooth/DAT flapping duplicates;
- defers while Jarvis is actively speaking/processing;
- abandons an old deferred greeting after a bounded busy timeout instead of firing randomly later;
- reasserts the wearer audio route immediately before the greeting;
- suspends hands-free recognition during playback;
- restores hands-free mode afterward;
- exposes coordinator state, last greeting, and suppressed-duplicate count in Operations;
- includes a **Test Greeting Once** control.

This improves determinism but does not claim DAT is a perfect physical on-head sensor.

---

# Vision and recent visual memory

Jarvis has both local-iPhone and backend visual paths.

## 30-second recent-frame memory

Recent Ray-Ban frames are kept in bounded **RAM-only** history for short-horizon questions and diagnostics. The raw rolling buffer is not silently written into long-term episodic memory.

Examples:

```text
Jarvis, what did that sign say?
Jarvis, what was I just looking at?
Jarvis, copy that error code.
```

## Local Apple Vision

The iPhone can operate on the latest/recent glasses frame for narrower structural tasks:

- OCR / visible text;
- QR and barcode decoding;
- human rectangle detection;
- face rectangle counting;
- general rectangle detection;
- attention-based saliency;
- scene-change measurement using image feature-print distance.

Example commands:

```text
Jarvis, read this.
Jarvis, copy this text.
Jarvis, scan the QR code.
```

Local OCR results copy to the **iPhone** clipboard.

## Backend semantic vision

Moondream is the semantic vision model for general scene/recent-frame analysis. Passive glasses frames can be sampled to the PC when enabled.

Bandwidth can be reduced on the remote/Tailscale path. The historical target profile is approximately:

```text
LAN passive path       ~1 sampled frame/sec, up to ~512 px
Tailscale passive path ~1 sampled frame/3 sec, up to ~384 px
```

Explicit manual scans can use higher-quality single frames.

## Conservative hazard/error alerts

Passive vision may warn only when the visible evidence itself supports a high-confidence condition, such as an obvious open flame, visibly running/spilling liquid, clear trip/impact hazard, visibly open access point, or clearly legible terminal/application error.

Jarvis must not infer hidden states such as an unlocked closed door or a dangerous appliance merely because it is present. This is assistive context, not a safety-certified detector.

## Spatial last-seen memory

Evidence-backed object sightings can be stored with object, scene/location context, time, confidence, and provenance. This supports questions such as “Where did I last see my keys?” without pretending the system has centimeter-accurate indoor positioning.

---

# Known People

Known People is a **private, closed-set, explicit enrollment** system. It does not identify arbitrary strangers.

## Enrollment

The user supplies multiple samples of a known person. The iPhone:

1. detects/crops the relevant face;
2. creates Apple Vision feature-print observations;
3. discards the raw enrollment image for this feature after creating the feature print;
4. stores the label, private note, calibration metadata, and feature prints in local protected storage.

## Matching

Current frames are compared only to enrolled people. Continuous recognition uses conservative confirmation; close/ambiguous candidates remain unknown rather than forcing a match.

## Supported questions

```text
Who is this?
Who am I talking to?
What do I know about this person?
What did I talk about with them?
```

The local brief can combine the explicitly saved Known People note with bounded local conversation/encounter context.

## World-model bridge

The backend can resolve an iPhone Known People ID to the same person represented by an email address, Calendar attendee, meeting participant, commitment owner, or document evidence when the identities are compatible.

## Presence privacy

A fresh local match can cross to the backend only as bounded advisory metadata such as person ID, name, match time, and an advisory flag. Distance, threshold, feature print, and image data are excluded.

## Unenrollment semantics

Removing a person from an authoritative Known People snapshot means **revoke face enrollment**, not “erase this person from history.”

Jarvis removes the iPhone enrollment identity/aliases/private enrollment metadata while preserving independently sourced Gmail/Calendar/history evidence. If no independent identity remains, the live entity is tombstoned so the old enrolled name does not keep creating new current relationships.

---

# Personal inventory

The iPhone supports explicit enrollment/matching of important objects using local Apple Vision feature prints.

The feature is conservative and works best when the enrolled item occupies a substantial portion of the camera frame.

A confident local match can update:

- last-seen time;
- optional approximate coordinates/location context;
- bounded metadata that may cross into the world snapshot.

Raw enrollment photos/feature-print internals do not become ordinary backend world facts.

---

# Personal Notecard

The Personal Notecard is an encrypted, user-controlled source of explicit facts the user wants Jarvis to be able to rely on.

It exists specifically for facts such as:

```text
I live at 123 Example Street.
My relationship to Jane Doe is spouse.
Jane Doe is my sister.
Put “preferred airport = Burbank” on my notecard.
```

## Supported fact classes

- home address;
- relationship to a named person;
- custom labeled facts.

## Important semantics

Jarvis does **not** silently infer Notecard facts from ordinary conversation. A fact is added through explicit Notecard language, the Notecard UI, or a direct answer to a question Jarvis just asked for the Notecard.

If a required fact is absent, Jarvis can ask for it. The pending question is short-lived rather than remaining indefinitely.

Examples:

```text
User: “Take me home.”
Jarvis: “I don't have your home address on the Personal Notecard yet. What address should I use for home?”
User: “100 Main Street, Pasadena.”
Jarvis: “Saved that as your home address on the Personal Notecard.”
```

## Privacy

The Notecard is encrypted on the iPhone. The full Notecard is **not** attached wholesale to every backend request. Only entries selected as relevant to the current command are included in a bounded private-context block.

## Queries

Examples include:

```text
What is my home address?
Where do I live?
What is my relationship to Jane Doe?
Show my Personal Notecard.
```

The Notecard is visible from the main Jarvis UI for review/edit/delete.

---

# Turn-by-turn navigation

Navigation is a first-class **iPhone-local** capability, deliberately routed before the generic backend planner so ordinary directions do not depend on the Windows PC being reachable.

The implementation uses MapKit/CoreLocation for destination resolution and routing.

## Commands

Examples:

```text
Jarvis, take me to <business/address/place>.
Jarvis, drive me to <destination>.
Jarvis, walk me to <destination>.
Jarvis, take me home.
Jarvis, what is the next turn?
Jarvis, navigation status.
Jarvis, recalculate the route.
Jarvis, open this route in Apple Maps.
Jarvis, stop navigation.
```

## Destination resolution

A named business/address is resolved with local MapKit search near the current location and ranked by name/title match plus geographic distance.

`home` is **not** treated as an arbitrary map-search term. It resolves only through the explicit Personal Notecard home address. If no home address is saved, Jarvis asks rather than guessing.

## Route behavior

The navigation controller supports:

- driving and walking;
- route calculation and ETA;
- spoken first direction;
- preparation and immediate-turn prompts;
- next-turn queries;
- remaining distance/status;
- arrival detection;
- repeated off-route detection;
- automatic reroute after sustained deviation;
- explicit reroute command;
- background location updates while navigation is active;
- Apple Maps handoff for the active destination.

This is normal MapKit navigation assistance, not a safety-certified navigation system. Live acceptance of the current build’s navigation path is still part of the remaining physical-device validation checklist.

---

# Local iPhone intelligence

The frontend uses an explicit capability-pack router instead of a growing stack of ad-hoc command interceptors.

Each pack can declare:

- stable ID/name/category;
- priority;
- effect class;
- requirements;
- availability;
- intent predicate;
- lazy activation;
- execution handler.

Current pack families include:

- Camera Master Privacy Gate;
- Read-only Pack Composer;
- Deterministic Utilities;
- Native Calendar;
- Native Reminders;
- Jarvis Local Timers;
- Context Capsule Writer;
- Unified Local Memory;
- Native Contacts;
- Vision / Known People / Inventory;
- Local Executive/productivity features;
- Frontend Controls;
- Apple Stable-Question Brain;
- Legacy Frontend Compatibility Adapter.

The compatibility adapter is intentionally low priority so newer typed capabilities can claim a request first.

## Camera privacy gate

If the master camera latch is off, lower visual packs cannot silently reactivate it.

## Deterministic utilities

Stable requests can be answered without model/backend routing, including time/date, arithmetic, percentages, and common unit conversions.

This prevents category errors such as answering “What time is it in DC?” with the state of the Windows Clock application.

## Native iPhone Calendar

With permission, the phone can answer local calendar questions using EventKit independently of the PC Google connector.

## Native Reminders

With permission, the phone can create Apple Reminders locally, including relative-time reminders.

## Jarvis local timers

Notification-backed timers do not inspect/control Clock.app and can survive ordinary app suspension.

## Native Contacts

The app can answer contact-detail questions from the iPhone Contacts database. Known People can be linked to Contacts only when the match is sufficiently unambiguous.

## Encrypted Context Capsules

The user can explicitly save a bounded local context snapshot. Capsules may include current mode, current matched enrolled person, recent OCR, last command/response, bounded clipboard excerpt, and optional coarse location context. They are AES-GCM encrypted with a device-protected key and do not silently persist raw camera/microphone buffers.

## Unified local memory

Local search can span Context Capsules, recent app conversation history, Known People notes, local events, encounters, inventory, goals, Waiting On, and local receipts.

## Offline command staging

If both backend routes are unavailable, a command can be staged locally. **Queued commands never auto-execute on reconnect**; the user must explicitly resend them.

## Quality shield

Local capability responses are structurally checked before being spoken. The shield rejects empty/pathological responses, utility/app-category mismatches, and read-only packs falsely claiming they executed writes. A rejected read answer can fall through to the backend; a questionable write is not automatically retried because retrying can duplicate side effects.

## Encrypted execution receipts

The frontend records bounded encrypted receipts describing which capability pack handled a request, effect class, requirements, routing latency, verdict, and bounded command/response excerpts.

---

# World synchronization

The iPhone periodically publishes a bounded metadata world snapshot over the authenticated persistent companion connection.

## Semantic deduplication

`captured_at` does not count as a semantic change. If the actual world state is unchanged, the snapshot hash remains the same and the payload is not repeatedly sent just because time passed.

On reconnect, the current authoritative state can be resent even if its semantic hash is unchanged, ensuring the backend catches up after transport loss.

## Operations telemetry

The iPhone Operations screen tracks:

- current endpoint;
- connection/reconnect state;
- snapshot send attempts/successes;
- last successful snapshot time;
- canonical SHA-256 hash;
- serialized bytes;
- schema version;
- per-collection counts;
- no-op dedupe count;
- send failures/last error;
- privacy-contract state.

## Snapshot content

Current metadata classes include:

- Known People metadata;
- goals;
- Waiting-On items;
- inventory metadata/last seen;
- reminders;
- bounded encounter summaries/transcript excerpts;
- bounded local power events;
- local action receipts;
- current mode;
- short-lived advisory current-person presence.

The current iPhone snapshot schema is version 2.

## Explicitly excluded from ordinary world sync

- biometric feature prints;
- face enrollment photographs;
- raw camera frames;
- raw/rolling microphone audio;
- incident media;
- clipboard contents;
- privacy-zone coordinates;
- recognition match distances/thresholds.

The phone recursively checks for forbidden field families before sending and blocks a violating snapshot rather than trusting the backend to ignore it.

## Authoritative collection semantics

For `goals`, `waiting`, and `people`:

```text
explicit []        authoritative “none remain”
missing key        partial/unknown; retire nothing
malformed non-list partial/unknown; retire nothing
```

This prevents an older or damaged client payload from mass-retiring the user’s current state.

---

# Persistent world model

The unified world database is:

```text
%APPDATA%\JarvisForMRB\world_model.sqlite3
```

The current migration target is **schema version 5**.

## Core representations

### Entities

Stable things such as people, projects, goals, places, objects, meetings, documents, Calendar events, reminders, and system identities.

### External IDs

Namespace-scoped source identifiers connect entities to Gmail, Calendar, Known People, attachments, and other systems.

### Aliases

Alternate names with source/confidence.

### Events

Provenance-bearing observations/actions containing event type, occurrence time, record time, summary, bounded payload, confidence, source kind/reference, and evidence text.

### Event/entity roles

Entities participate in events as sender, recipient, attendee, organizer, owner, assignee, source, observed object, location, project, goal, requester, beneficiary, etc.

### Beliefs

Beliefs support value/object assertions with observation time, validity, confidence, source event, evidence, revision lineage, and state:

```text
current
superseded
disputed
```

A lower-confidence conflict can remain disputed instead of overwriting stronger evidence.

### Commitments

Commitments model who owes what, due date/text, status, confidence, source/resolution event, and metadata.

### Derived relations

Evidence-backed current graph relationships are stored separately from source events.

### Intentions

Active user objectives receive dedicated persistent operational state.

### Executive attention/decisions

The system stores what currently needs attention and one current operational decision per active intention.

### Action verifications

Consequential action attempts have persistent expected-outcome and observation state.

---

# Identity, provenance, chronology, and relation safety

## Identity resolution

Strong external namespace+ID matches dominate. A unique exact name may bridge compatible namespaces only when no same-namespace strong-ID conflict exists.

Example:

- an enrolled `Daniel Reed` without an email can later acquire `daniel@example.com`;
- `daniel2@example.com` must not silently merge into an entity already bound to a different email just because both display names are Daniel Reed.

## Occurrence semantics

Repeated identical live events remain distinct occurrences at different times. Immutable source records can use source-specific dedupe keys.

## Evidence-backed relation graph

Current derived relationships require evidence rows. Diagnostics verifies that evidence exists and that stored evidence counts agree with actual evidence.

## Person→project protection

Textual co-occurrence does not establish association.

The sentence:

```text
Daniel is not on Project Apollo.
```

must not create `Daniel -> associated_with_project -> Apollo`.

Person/project association requires structured participant roles such as sender, recipient, attendee, organizer, assignee, owner, speaker, requester, beneficiary, or participant.

## Chronology

When chronology changes the meaning of current state, Jarvis uses **source occurrence time**, not SQLite insertion order.

This applies to:

- current project-term observations;
- document-version direction;
- recent Executive changes;
- conflict ordering.

ISO and RFC-style email dates are supported. Malformed dates remain unknown and use a timezone-safe epoch floor only for deterministic sorting.

---

# Persistent goals and intentions

Goals can enter the system through the iPhone Goal Manager or explicit conversation.

## Conversational capture

Patterns such as these can create durable intentions:

```text
Our goal is ...
My goal is ...
The goal is ...
We're trying to ...
We are trying to ...
I'm trying to ...
I am trying to ...
```

The capture layer intentionally ignores ordinary questions, hypotheticals, trivial fragments, and ambiguous “I want...” language.

Explicit deadlines are parsed conservatively.

Repeated identical declarations use stable keys to avoid creating a new goal every time the user repeats it.

## Intention state

An intention may carry:

- objective/title;
- status;
- next action;
- due time;
- confidence;
- source;
- linked project/entities;
- linked current commitments.

## Query-aware relevance

Active goals are not injected into every turn. Jarvis ranks relevance using entity links, lexical overlap, commitments, graph expansion, and urgency.

Thus:

```text
What should I do next?
```

may receive active-objective context, while:

```text
What should I order for dinner?
```

should not be contaminated by an unrelated work objective.

## Goal lifecycle

The live iPhone→PC test has demonstrated the intended temporal behavior:

```text
active     -> superseded
completed  -> current
```

The history remains available rather than deleting the old belief.

---

# Situational awareness and meeting prebriefs

The situation compiler answers “what matters about the situation I am entering?” rather than dumping general memory.

It can:

- refresh near-term Calendar state with throttling;
- choose the actual current/upcoming meeting;
- ignore cancelled events;
- avoid generic all-day events unless matched;
- resolve participants;
- traverse evidence-backed project/person relations;
- retrieve pending commitments;
- retrieve relevant active intentions;
- retrieve recent connected evidence;
- return bounded current/upcoming context.

Example:

```text
Jarvis, anything I need to know before I go in?
```

A useful prebrief is emitted only when connected evidence supports something actionable, such as a term discrepancy, overdue dependency, important document change, or active next action.

It should prefer:

```text
“Newer draft says 15%; prior discussion said 10%.”
```

over a generic:

```text
“Your meeting starts in 12 minutes.”
```

when both are available.

---

# Gmail attachments, document lineage, and term conflicts

## Passive Gmail attachment ingestion

Jarvis can index bounded text from selected recent Gmail attachments without executing or opening them through a desktop application.

Current passive allowlist:

```text
.pdf
.docx
.xlsx
.pptx
.txt
.md
.csv
.json
.rtf
```

Current bounds include approximately:

- 8 MiB maximum attachment size;
- 80,000 extracted text characters;
- bounded message/page scanning;
- resumable pagination/checkpoint state;
- 48-hour overlap on later incremental scans to avoid source-time gaps.

Extraction behavior:

- PDF: passive `pypdf` text extraction;
- DOCX/PPTX: passive ZIP/XML parsing;
- XLSX: read-only `openpyxl` with `data_only=True`; formulas are never executed;
- text/CSV/JSON: bounded decoding;
- RTF: basic passive stripping.

Image-only/textless PDFs are not silently treated as successfully indexed; OCR is a separate requirement.

Macro-enabled, executable, archive, image, unknown, and unsupported formats are excluded from passive ingestion.

## Document lineage

Jarvis determines whether attachments are plausibly versions of the same document using evidence such as Gmail thread, shared Project identity, content overlap, subject normalization, and filename-family normalization.

Similar filenames alone are not enough.

## Material change extraction

Version comparison prioritizes explicit numeric/date changes, including money, percentages, basis points, durations, dates, and other explicit values.

The comparator distinguishes likely equivalent revisions from material changed revisions.

## Supersession

When evidence supports it, the newer document receives an evidence-backed `supersedes` relation to the older document.

## Project term ledger

Supported high-value deterministic term families currently include:

- deadline/signing/closing date;
- earnout;
- escrow/holdback;
- indemnity basket;
- indemnity cap;
- interest rate;
- ownership percentage;
- purchase price;
- survival period;
- termination/break-up fee;
- working-capital target/peg.

A term observation requires a named supported term, an explicit value, and evidence connected to a Project.

## Conflict semantics

If chronological sources provide different explicit values for the same Project+term, Jarvis records a change/conflict event and retains both values/provenance.

It does **not** silently decide which legal/economic source controls.

Direct queries such as:

```text
What's the indemnity cap on Project Apollo?
What are the current deal terms on Project Apollo?
```

route to the structured term ledger when possible rather than fuzzy memory search.

---

# Executive Loop

The Executive Loop converts knowledge into persistent operational judgment.

Its core question is:

```text
Not merely: “What do I know?”
But:        “What is preventing the objective, what changed,
             and what should happen next?”
```

## Attention

Attention items may include:

- failed/timed-out/unverified action outcome;
- source-term discrepancy;
- overdue dependency;
- due-soon commitment;
- objective deadline;
- meaningful document change;
- explicit next action.

When a condition disappears, the attention item becomes stale rather than being erased as if it never existed.

## Objective state

Compiled states include:

```text
active
due_soon
overdue
at_risk
awaiting_verification
```

The compiled view can include objective, deadline, projects, blockers, Waiting On, recent changes, next actions, recommendation, and executable proposal.

## Deterministic priority

Important failure conditions have explicit priority. For example, failed outcome verification outranks continuing the original plan; an overdue dependency outranks low-value background change; a substantive term discrepancy is high priority.

## Permission-aware executable proposal

The Executive Loop can propose an existing tool/action, but that proposal still goes through `permissions.py`. It does not create a privileged executor.

## Exact correlation

If a model consumes an Executive proposal, tool identity and arguments must match the persisted proposal exactly. Modified arguments do not inherit the original Executive authority/provenance.

---

# Tools, permissions, and action authority

The backend exposes bounded tool classes rather than a general host shell.

## Default permission model

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

Examples:

```text
knowledge.search     read
gmail.query          read
app launch/tab focus local_write
gmail.send           external_write
calendar.create      external_write
job cancellation     destructive
sandbox/custom tool  security
```

A model-generated plan cannot elevate its own risk class.

## Confirmation

Consequential operations require the appropriate confirmation flow. For exact security-class terminal commands, Jarvis presents the full command before allowing execution.

## Windows tools

Bounded local operations include app/process status, app launch/close, URL/path opening, foreground process/window context, Minecraft status/launch/ensure-running, and system-resource status.

Foreground-window context is not treated as full document contents.

## Browser tools

Supported operations include browser status, tab list/status, focus, open, and close.

## Google tools

Gmail, Contacts, and Calendar reads/writes are separated by permission class. Gmail recipient allowlisting is enforced independently of the generic confirmation policy.

---

# Closed-loop action verification

Jarvis distinguishes:

```text
“The tool accepted the request.”
```

from:

```text
“I have independent evidence that the intended state now exists.”
```

## Verification states

```text
pending
verified
failed
timed_out
unverified
superseded
```

The ledger stores action, expected state, verifier, timing/deadline, observations, evidence/error, action event, and optional Executive correlation.

## Read vs write

A read can close immediately when its returned observation is the requested result.

A write does not become verified merely from a success response when an independent observer exists.

If no observer exists, Jarvis records `unverified` rather than inventing certainty.

## Independent verifiers

Current verifier strategies include observable effects such as:

- Gmail send → causal Sent Mail read-back;
- Calendar create → Calendar event read-back;
- application launch/close → process state;
- browser tab open/focus/close → browser state;
- Minecraft state;
- persistent/temporary state writes;
- scheduled job create/cancel;
- background-task terminal state.

## Causal Gmail boundary

A previous matching Sent Mail message cannot satisfy a new send simply because recipient/subject match. The expected observation is bounded by action time.

## Timeout semantics

Before changing a pending action to `timed_out`, Jarvis performs a final independent observation.

An explicit later query such as:

```text
Did that work?
```

forces a fresh observer pass and can recover a previous timeout to `verified` if the outside system now shows the effect.

The outcome query itself is routed deterministically so it cannot accidentally re-run the original action.

## Live verification example

The current deployment has demonstrated:

```text
natural-language Calendar request
-> external-write confirmation
-> Google Calendar create
-> action verification pending
-> independent Google Calendar read-back
-> persisted status verified
-> “Did that work?” answered from observed state
```

---

# Proactivity, HUD, Attention Inbox, and Live Activities

## Backend proactive monitor

Bounded proactive checks include:

- near-term Calendar reminders;
- contextual meeting prebriefs;
- unread urgent/action-required/deadline mail;
- due action-verification checks;
- model/context prewarm before relevant events;
- runtime-provider health/resource conditions.

Alerts are deduplicated so the same condition is not repeatedly spoken every cycle.

## Display-neutral HUD

The iPhone uses structured display cards independent of a particular future glasses display.

Five primitive types:

1. attention;
2. context;
3. action;
4. verification;
5. ephemeral answer.

Cards contain bounded title/detail/badge/priority/timing/source state. The frontend chooses a primary card deterministically by validity, priority, and recency.

## Attention Inbox

Transient proactive messages are mirrored into a persistent encrypted iPhone inbox with acknowledgement state. This allows important blockers/failures to survive beyond a one-time spoken interruption.

The inbox supports bounded storage, stable-ID updates, acknowledge, acknowledge-all, and delete.

## Live Activity / Dynamic Island / Lock Screen

The iOS project contains a dedicated `JarvisLiveActivity` extension. The same structured HUD state can be projected to Lock Screen/Dynamic Island presentations.

Room Listening uses the Live Activity so active ambient capture remains visible.

---

# Meeting Notes and Room Listening

## Explicit Meeting Notes

Meeting capture is intentionally visible and user-initiated.

The workflow supports:

- start/stop;
- elapsed timer;
- pause/resume;
- bookmarks;
- local transcript accumulation;
- periodic Apple Speech task rotation;
- local transcript snapshot;
- Share Sheet export;
- continued local capture when the PC is unreachable;
- later **Sync & Extract**;
- backend transcript ingestion;
- action-item extraction.

The normal hands-free wake loop is suspended during explicit meeting capture so two microphone consumers do not compete.

## Local metric contradiction checking

During an explicitly active meeting session, concrete numeric claims can be compared to local indexed evidence. Jarvis reports a **possible contradiction** when evidence conflicts; it does not claim the index is infallible.

## Room Listening

Room Listening generalizes the room-facing microphone profile outside a formal meeting.

Examples:

```text
Jarvis, start room listening.
Jarvis, listen to the room for five minutes.
Jarvis, what did they just say?
Jarvis, stop room listening.
```

Properties:

- explicit start only;
- visible active state;
- iPhone built-in microphone only;
- bounded duration (roughly 15 seconds to 30 minutes, default five minutes);
- Apple Speech task rotation;
- bounded in-memory transcript;
- route watchdog;
- hands-free wearer mode suspended and restored afterward;
- HUD/Live Activity visibility.

## Microphone placement test

Operations can compare room-mic versus available HFP input level/recognition confidence and recommend repositioning the phone. This is a practical placement check, not laboratory calibration.

## Meeting/audio privacy boundary

Jarvis does not identify speakers by biometric voiceprint and does not infer another person’s emotion, stress, deception, tension, or mental state.

Use recording/listening features only where lawful and with appropriate participant notice/consent.

---

# Automation, jobs, background work, and workflows

## Scheduled jobs

Persistent automation supports one-time jobs, recurring jobs, event-triggered jobs, cancellation, and scheduled briefings.

## Background worker queue

Long-running work can execute outside the interactive turn. Task state includes pending/running/completed/failed result information and participates in verification/world history.

## DAG workflows

Jarvis can execute workflow graphs, including parallel read-only steps when safe. Consequential steps retain the normal permission model.

## Prefetch/prewarm

Shortly before relevant events, Jarvis can prewarm the fast model and retrieve local private context. It does not need to send private Calendar titles to arbitrary external services merely to prefetch.

---

# Web research integrity and Research Receipts

A central Jarvis requirement is that a model must not be able to claim “I searched thoroughly” without an auditable execution trace.

For material recommendation/completeness tasks, Jarvis supports **audited research** rather than simply prompting the model to “search harder.”

## Research Receipt

An audited run records:

- user decision/search problem;
- search plan;
- every query family;
- exact queries;
- results and ranks;
- novel vs duplicate yield;
- domain/source diversity;
- candidate discovery;
- disconfirming/long-tail/adversarial coverage;
- provider failures;
- stopping reason;
- calibrated coverage grade;
- tamper-evident hash-chain state.

## Mandatory query families

Audited search uses eight independent directions:

```text
precision
breadth
constraints
authoritative
independent
disconfirming
long_tail
adversarial
```

The planner may tailor wording, but it may not silently omit a required family. Deterministic fallback queries exist if planning fails.

## Saturation diagnostics

Late-query novelty measures whether the final independent searches are still discovering new material. High late novelty is evidence that search has **not** stabilized.

Candidate overlap across independent query groups is also used in a Chapman capture–recapture estimate as a rough residual-candidate signal. It is calibration, not proof that the open web is complete.

## Coverage grades

Research Receipts can classify coverage approximately as:

- **A** — high-coverage audited search;
- **B** — useful/moderate coverage with residual uncertainty;
- **C** — incomplete/weakly saturated; do not claim a definitive “best.”

## Tamper-evident ledger

Research execution is written to `search_integrity.sqlite3` as a hash-linked event ledger. A changed/missing/reordered event breaks verification of the chain.

Full receipts are also stored under:

```text
%APPDATA%\JarvisForMRB\research_receipts\
```

## Automatic activation

Ordinary fresh-fact lookup can remain cheap. Audited research is intended to activate for material completeness/selection language such as best, recommend, compare, alternatives, exhaustive, rigorous, all/every option, rank, closest match, or “do not miss anything.”

The final language should remain honest: **“best found in this audited search”** rather than “best option in existence” unless the search universe is actually closed and fully enumerated.

---

# COVER and COVER-U benchmarks

## COVER

**COVER = Coverage, Option discovery, Verification, Evidence, and Research traceability.**

The benchmark measures whether an AI performed a sufficiently comprehensive, auditable search to justify its final confidence.

Primary metrics include:

- candidate recall;
- evidence recall;
- contradiction recall;
- decision quality/regret;
- constraint accuracy;
- audit fidelity;
- calibration;
- efficiency.

Core dimensions use a geometric mean so one catastrophic weakness cannot be hidden by several strong averages. Fabricating a research trace hard-zeros the composite.

## COVER-U

COVER-U generalizes the idea into a universal system-level research benchmark. It measures not only thoroughness but whether the system knows **when** to research, **how deeply**, **which evidence to trust**, **when to stop**, and **how strongly its conclusion is justified**.

The standardized benchmark defines ten archetypes:

```text
A0 No-search
A1 Lookup
A2 Verification
A3 Multi-hop investigation
A4 Synthesis
A5 Decision/recommendation
A6 Comprehensive enumeration
A7 Temporal/version resolution
A8 Adversarial/unsatisfiable
A9 Long-horizon research
```

Each archetype has a six-level difficulty ladder, including D6 frontier-tail tasks. The benchmark is deliberately designed so frontier systems should not simply score 100; the desired release calibration keeps the strongest system materially below saturation.

COVER-U maintains separate standardized-tool, native-product, and Jarvis deployment tracks. Jarvis also has a separate application profile that places additional weight on recommendation/comprehensive-search behavior while preserving the universal Standard score.

CLI entry point:

```powershell
jarvis-cover-score --help
```

or, if Scripts is not on PATH:

```powershell
py -3.14 -m jarvis_mrb.cover_universal_cli --help
```

See `SEARCH_INTEGRITY_AND_COVER_BENCHMARK.md` and `COVER_U_UNIVERSAL_BENCHMARK.md` for the formal benchmark definitions.

---

# JARVIS-20 behavioral evaluation

JARVIS-20 is the fixed, repeatable behavioral scorecard for day-to-day Jarvis development. It does **not** add another Definition-of-Done criterion.

There are 20 conceptual tests, each scored 0–3:

```text
0 fail
1 partial
2 pass
3 excellent
```

Maximum: **60**.

The fixed tests are:

1. No-tool judgment
2. Ambiguous follow-up
3. Personal Notecard persistence
4. Notecard to action
5. Identity continuity
6. Persistent objective
7. Situational awareness (north star)
8. Cross-source contradiction (north star)
9. Document change detection
10. Executive judgment
11. Efficient current lookup
12. Rigorous recommendation (north star)
13. Long-tail discovery
14. Research adversary
15. Research calibration
16. Action permission
17. Closed-loop verification (north star)
18. Failure detection
19. Room audio
20. Presence greeting

North-star tests are 7, 8, 12, and 17.

## Basic commands

```powershell
jarvis-20 plan --compact
jarvis-20 preflight --strict
jarvis-20 template --seed 2026-09-baseline --output jarvis20-baseline.json
jarvis-20 score jarvis20-baseline.json --save
jarvis-20 history
```

## Procedural worlds

Concrete names/projects/terms/deadlines/distractors should change so Jarvis cannot memorize the benchmark.

Generate a public scenario plus hidden oracle:

```powershell
jarvis-20 generate `
  --seed regression-001 `
  --anchor 2031-04-05T15:30:00Z `
  --output .\j20-regression-001.json `
  --oracle-output .\j20-regression-001.oracle.json `
  --score-output .\j20-regression-001.score.json
```

Run the isolated generated-world preflight:

```powershell
jarvis-20 world-preflight `
  .\j20-regression-001.json `
  .\j20-regression-001.oracle.json `
  --strict
```

Batch fuzz:

```powershell
jarvis-20 fuzz-world `
  --seed-prefix regression-world `
  --count 100 `
  --anchor 2031-04-05T15:30:00Z `
  --strict
```

The current deployment cycle produced a 100/100 pass across a 100-world fuzz run.

## Recursive improvement boundary

A future self-improvement agent may optimize against public procedural tasks and execution feedback, but the hidden oracle, holdout variants, evaluator implementation, privacy invariants, permission policy, and scoring rules must remain outside the candidate system’s write authority.

---

# Expenses, journals, PC context, and system guardrails

## Expense/receipt capture

Jarvis can extract structured receipt/invoice data into local storage:

```text
%APPDATA%\JarvisForMRB\expenses.sqlite3
%APPDATA%\JarvisForMRB\expenses.csv
```

The extraction layer is instructed not to guess unreadable merchant/date/total/tax/tip/line items.

## Daily journal

Jarvis can generate a local Markdown daily journal on demand or through the optional automatic path:

```text
%APPDATA%\JarvisForMRB\journal\YYYY-MM-DD.md
```

The journal can summarize available local activity without inventing emotions or motives.

## PC foreground context

A lightweight monitor can record current foreground process/window title and available browser-tab context. This supports “What was I doing on my PC?” without claiming the full contents of an open document.

## Resource guardrails

Jarvis monitors CPU, RAM, NVIDIA GPU utilization, VRAM, GPU temperature, and background-worker backlog. High-confidence thresholds can generate Attention/proactive warnings.

Example:

```text
Jarvis, how is the PC doing?
Jarvis, GPU status.
```

---

# Sandbox and custom tools

## No unrestricted host shell

This is a hard architectural boundary.

## Docker sandbox

Generated Python/terminal work runs in a disposable container with restrictions including:

- network disabled;
- read-only filesystem;
- Linux capabilities dropped;
- `no-new-privileges`;
- bounded memory/CPU/process count;
- hard timeout.

Sandbox execution is a **security** action.

## Exact-command confirmation

When Jarvis proposes an isolated terminal command, the user receives the **entire exact command** before approving execution.

## Custom API adapters

Jarvis can create constrained custom API adapters using:

- sandbox generation/validation;
- HTTPS host allowlisting;
- risk classification;
- no arbitrary host-shell bridge.

## Self-healing repair proposals

A structurally broken custom adapter may produce a repair proposal, but only after validation such as successful sandbox execution, valid request plan, unchanged host allowlist, preserved risk class, and no embedded auth/cookie/API-key header.

Repairs are never silently applied. Applying one is security-gated.

---

# Privacy and security model

Jarvis is designed around a local/private trust boundary rather than treating all sensors and services as equivalent.

## Backend transport

The iPhone uses bearer-authenticated requests and persistent companion communication. Remote access should be private Tailscale Serve, not a public port.

## World-sync privacy contract

The metadata snapshot explicitly excludes raw/biometric media channels as documented above.

## Known People

Closed-set, explicit enrollment only. No stranger identification.

## Audio

No speaker voiceprint identification. No affective inference about other people.

## Meeting capture

Explicit and visible. Not invisible background recording.

## Offline commands

No automatic delayed replay of consequential commands after reconnect.

## Permission authority

Read/local-write/external-write/destructive/security classes are enforced outside the language model.

## Action provenance

Tool executions are mirrored into world events with bounded/redacted arguments and execution result. Sensitive fields can be redacted from the durable audit event.

## Notecard

Encrypted locally; only selected relevant facts are attached to a request.

## Context Capsules / frontend receipts / Attention Inbox

Sensitive frontend persistence uses AES-GCM with device-protected keys and protected file storage where implemented.

---

# Data stores and retention

Principal Windows-side stores include:

```text
%APPDATA%\JarvisForMRB\world_model.sqlite3
%APPDATA%\JarvisForMRB\conversation.sqlite3
%APPDATA%\JarvisForMRB\episodic_memory.sqlite3
%APPDATA%\JarvisForMRB\spatial_memory.sqlite3
%APPDATA%\JarvisForMRB\meeting_notes.sqlite3
%APPDATA%\JarvisForMRB\knowledge_sources.sqlite3
%APPDATA%\JarvisForMRB\expenses.sqlite3
%APPDATA%\JarvisForMRB\expenses.csv
%APPDATA%\JarvisForMRB\jobs.sqlite3
%APPDATA%\JarvisForMRB\background_tasks.sqlite3
%APPDATA%\JarvisForMRB\search_integrity.sqlite3
%APPDATA%\JarvisForMRB\environment_state.json
%APPDATA%\JarvisForMRB\ephemeral_state.json
%APPDATA%\JarvisForMRB\research_receipts\
%APPDATA%\JarvisForMRB\evaluations\jarvis20\
%APPDATA%\JarvisForMRB\notes\
%APPDATA%\JarvisForMRB\journal\
%APPDATA%\JarvisForMRB\backups\
```

Exact legacy files depend on which features have been used.

## iPhone storage

The iPhone uses a mixture of app storage, complete-file-protected files, and Keychain-backed cryptographic material for feature-specific state such as Known People feature prints, Personal Notecard, Context Capsules, execution receipts, and Attention Inbox.

The world snapshot is deliberately a reduced projection of this local state rather than a full replication of sensitive storage.

---

# Health, diagnostics, migrations, and rollback

## `/health`

A healthy current deployment should expose fields similar to:

```text
status                 ok
tts                    ready
web_search             ready
planner_model          qwen3:8b
sandbox                ready
visual_history         ready
resource_guardrails    active
world_model            ready
world_schema_version   5
world_schema_target    5
verification           ready
tool_audit             ready
runtime_health         ready
scheduler              running
knowledge_refresh      running
proactive_monitor      running
```

`auto_route` may be enabled or disabled according to configuration; it is not itself a health failure.

## Schema version 5

`jarvis_mrb.world_migrations` is the migration authority.

Current stages:

1. core entities/events/beliefs/commitments;
2. evidence relations, intentions, strong person/project semantics;
3. chronology-safe term ledger and document lineage;
4. Executive Loop, verification, runtime subsystem health;
5. resumable Gmail attachment-ingestion state/support telemetry.

A database claiming a future unsupported schema is refused. A database claiming current version while missing required structure/history is also refused.

## Backups

Before upgrading an existing world, Jarvis creates a bounded SQLite backup under:

```text
%APPDATA%\JarvisForMRB\backups
```

The current retention is three pre-upgrade world backups.

## WAL / contention

Migration enables SQLite WAL mode and busy-timeout behavior for the shared world database.

## Runtime failure isolation

Optional/provider subsystems track health independently. A failing Calendar monitor, mail monitor, resource check, journal startup, prefetch, or other noncritical provider should not suppress unrelated subsystems.

Core world migration and action-audit/verification installation are treated differently: running without them would invalidate the state/action contract, so startup fails safe.

## Diagnostics

`world_check` validates invariants including schema/version/history, SQLite integrity, foreign keys, relation evidence, person/project evidence quality, stale intention links, Known People privacy revocation, tombstone relation leaks, multiple current Executive decisions, term/document chronology, verification states/evidence, runtime degradation, WAL expectation, and DB growth warnings.

## Rollback

If migration/diagnostics fail:

1. stop Jarvis;
2. preserve the failed DB under a diagnostic filename;
3. choose the newest appropriate pre-upgrade backup;
4. restore it to `world_model.sqlite3`;
5. restore the prior source revision if required;
6. reinstall that revision’s dependencies;
7. run its diagnostics before restart.

Do not hand-edit/merge SQLite rows as an ordinary rollback strategy.

---

# Testing and acceptance

## Full Python suite

```powershell
py -3.14 -m unittest discover -s tests -v
```

## World preparation

```powershell
py -3.14 -m jarvis_mrb.world_prepare
```

## Fixed-endpoint acceptance

```powershell
py -3.14 -m jarvis_mrb.world_acceptance_check
```

The acceptance harness runs in an isolated temporary world and does not contact real external services or mutate the deployed user world.

## Diagnostics

```powershell
py -3.14 -m jarvis_mrb.world_check
```

## JARVIS-20

```powershell
jarvis-20 preflight --strict
jarvis-20 fuzz-world --seed-prefix regression-world --count 100 --strict
```

## Hardware-in-the-loop tests

Some properties cannot be proven by unit tests and remain real-device tests:

- Ray-Ban reconnect/presence behavior;
- HFP wearer microphone routing;
- room/far-field iPhone microphone capture;
- GPS/background navigation behavior;
- iOS background execution;
- DAT camera behavior;
- LAN/Tailscale transition behavior.

---

# Canonical Project Apollo acceptance story

The synthetic Apollo story exists because a true personal operating system must connect the whole chain rather than pass isolated feature tests.

The scenario requires Jarvis to:

1. ingest iPhone state containing Daniel Reed and an overdue Waiting-On item;
2. resolve Daniel’s Gmail address to the same person;
3. capture “We’re trying to get Project Apollo signed by Friday” as a persistent objective;
4. record prior conversational evidence that an indemnity cap is 10%;
5. ingest an older agreement attachment saying 10%;
6. ingest a newer version saying 15%;
7. detect the document lineage and 10%→15% material change;
8. retain both term values/provenance while recognizing 15% as chronologically latest;
9. identify an imminent Apollo meeting with Daniel;
10. compile the meeting/person/project/intention/dependency/evidence situation;
11. mark the objective `at_risk` with term conflict + overdue dependency;
12. surface the discrepancy and schedules in the prebrief;
13. register an external follow-up action attempt;
14. keep verification pending after the send receipt alone;
15. change to verified only after independent Sent Mail observation;
16. revoke Daniel’s Known People face enrollment without erasing independent email identity;
17. reject a false person/project relation from “Alex Example is not on Project Apollo”;
18. preserve state when snapshot collections are missing/malformed;
19. keep Apollo context out of an unrelated dinner question;
20. pass structural diagnostics;
21. prove the full causal chain exists.

The point is not Apollo itself. The point is that the architecture survives a randomized equivalent problem with different people/projects/terms/source order.

---

# Repository layout

Key top-level files/directories:

```text
README.md
FIXED_ENDPOINT_ACCEPTANCE.md
WORLD_MODEL_OPERATIONS.md
JARVIS_COMPLETE_CAPABILITIES_AND_BUILD_HISTORY.md
SEARCH_INTEGRITY_AND_COVER_BENCHMARK.md
COVER_U_UNIVERSAL_BENCHMARK.md
JARVIS_20_EVALUATION.md
JARVIS_20_PROCEDURAL_WORLDS.md
pyproject.toml
jarvis_mrb/
ios/
scripts/
tests/
```

Important backend modules include:

```text
jarvis_mrb/agent.py                    natural-language routing / fast paths
jarvis_mrb/streaming_agent.py          streaming conversational path
jarvis_mrb/service.py                  FastAPI runtime
jarvis_mrb/permissions.py              authority model
jarvis_mrb/tts_client.py               Kokoro TTS client/autostart
jarvis_mrb/world_model.py              core persistent world graph
jarvis_mrb/world_migrations.py         schema versioning / backup / validation
jarvis_mrb/world_frontend_ingest.py    iPhone snapshot bridge
jarvis_mrb/world_snapshot_reconcile.py authoritative snapshot semantics
jarvis_mrb/world_linker.py             evidence-backed derived relations
jarvis_mrb/world_executive.py          persistent intentions
jarvis_mrb/world_executive_loop.py     attention/decision/objective compiler
jarvis_mrb/world_situation.py          current/upcoming situation compiler
jarvis_mrb/world_prebrief.py           deterministic meeting prebrief
jarvis_mrb/world_calendar_sync.py      enriched private Calendar ingestion
jarvis_mrb/world_gmail_attachments.py  passive attachment ingestion
jarvis_mrb/world_document_versions.py  document lineage/change detection
jarvis_mrb/world_terms.py              structured Project term ledger
jarvis_mrb/world_term_context.py       direct term-query routing
jarvis_mrb/world_verification.py       closed-loop outcome verification
jarvis_mrb/tool_audit.py               action-attempt/audit integration
jarvis_mrb/runtime_health.py           persistent subsystem health
jarvis_mrb/world_diagnostics.py        invariant checks
jarvis_mrb/world_acceptance.py         isolated fixed-endpoint scenario
jarvis_mrb/search_integrity.py         audited-research ledger/receipts
jarvis_mrb/cover_universal.py          COVER-U scoring
jarvis_mrb/jarvis20*.py                JARVIS-20 suite/generator/world lab
```

Important iPhone source areas include:

```text
ios/JarvisIOS/JarvisAppModel.swift          core turn orchestration + navigation
ios/JarvisIOS/CompanionConnection.swift     persistent companion/world sync
ios/JarvisIOS/FrontendIntelligence.swift    local intelligence/capability packs
ios/JarvisIOS/FrontendOperations.swift      Operations/HUD/Attention/welcome/audio
ios/JarvisIOS/LocalProductivityFeatures.swift goals/Waiting On/world snapshot
ios/JarvisIOS/FeatureGuide.swift            searchable feature/test guide
ios/JarvisIOS/SpeechRecognizer.swift        wearer/room microphone routing
ios/JarvisIOS/JarvisShortcuts.swift         App Intents / Shortcuts
ios/JarvisLiveActivity/                     Live Activity extension
```

Exact filenames evolve; use the current tree as source of truth.

---

# Common command reference

```powershell
# Install/update package
py -3.14 -m pip install -e .

# Prepare world model
py -3.14 -m jarvis_mrb.world_prepare

# Full tests
py -3.14 -m unittest discover -s tests -v

# Fixed acceptance
py -3.14 -m jarvis_mrb.world_acceptance_check

# Diagnostics
py -3.14 -m jarvis_mrb.world_check

# Start backend
py -3.14 -m jarvis_mrb.service

# Google auth
py -3.14 -m jarvis_mrb.google_auth

# Serper setup
py -3.14 -m jarvis_mrb.serper_setup

# Browser setup
py -3.14 -m jarvis_mrb.browser_setup

# JARVIS-20 help
py -3.14 -m jarvis_mrb.jarvis20_cli --help

# COVER-U scorer help
py -3.14 -m jarvis_mrb.cover_universal_cli --help
```

Installed console aliases from `pyproject.toml` include:

```text
jarvis
jarvis-service
jarvis-install-startup
jarvis-google-auth
jarvis-browser-setup
jarvis-remote-setup
jarvis-serper-setup
jarvis-world-check
jarvis-world-migrate
jarvis-world-prepare
jarvis-world-acceptance
jarvis-cover-score
jarvis-20
```

---

# Known limitations and deliberate non-features

Jarvis intentionally does **not** claim the following capabilities:

## No public/unrestricted face recognition

Known People is private closed-set recognition only.

## No speaker voiceprint identity

Audio/meeting systems do not build a biometric speaker-identity database.

## No emotion/deception/stress inference

Jarvis does not label other people angry, deceptive, stressed, tense, etc. from voice.

## No arbitrary iOS notification interception

A normal app cannot inspect every other app’s notifications. Jarvis does not pretend otherwise.

## No invisible meeting recording

Meeting/Room Listening is explicit and visible.

## No safety-critical camera-only indoor homing

Last-seen memory and scene context are available; dependable safety-critical indoor visual homing is not represented as solved.

## No unrestricted host shell

Only the locked-down Docker sandbox is exposed to generated code/commands.

## No delayed auto-replay of consequential offline commands

Queued commands require explicit user resend.

## No automatic authoritative resolution of deal-term conflicts

A 10% vs 15% discrepancy remains a discrepancy with provenance until real evidence resolves it.

## No automatic global historical erasure from face unenrollment

Face-enrollment deletion is not silently interpreted as “erase this person everywhere.”

## No full IDE/document-content inference from window title

Foreground PC context is not equivalent to file contents.

## No claim that a tool return proves the real-world action succeeded

Observable writes require independent verification.

## Not yet a consumer-installable/public product

The current repository is an advanced private deployment. It still assumes a technical setup involving Windows, Python, Ollama, WSL, Docker, Xcode, account integrations, and developer provisioning. A production installer/onboarding/update/support layer is future productization work.

---

# Troubleshooting

## `jarvis-world-prepare` is not recognized

The Python package may be installed but the Python `Scripts` directory may not be on `PATH`.

Use:

```powershell
py -3.14 -m jarvis_mrb.world_prepare
```

instead of relying on the console alias.

## `git pull` says “not a git repository”

Change into the repository first:

```powershell
cd <path-to>\Jarvis-for-MRB
git pull
```

## Port 8765 already in use

Find/stop the current listener before starting another service instance:

```powershell
$pid = (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue).OwningProcess
if ($pid) { Stop-Process -Id $pid -Force }
```

Then restart Jarvis.

## TTS shows `starting-or-unavailable` / runtime health degraded

Check the Kokoro service directly:

```powershell
Invoke-RestMethod http://127.0.0.1:8880/health -TimeoutSec 5
```

Expected current response is a healthy status. If the model is missing, current startup code can preflight/repair the model and launch the WSL service; inspect the Jarvis/Kokoro startup logs before manually changing paths.

## Kokoro WSL service not reachable

Confirm WSL service/process/port and then restart the backend. The repository contains targeted regression coverage for WSL argv construction, model preflight, process lifetime, warm-up monitoring, and health recovery.

## Docker sandbox unavailable

Start Docker Desktop and verify the daemon before blaming Jarvis. Then re-check `/health` for `sandbox=ready`.

## Google read/write fails

First confirm:

```powershell
py -3.14 -c "from jarvis_mrb.tools.google import google_status; print(google_status())"
```

Re-run Google auth if required.

## Calendar create returns HTTP 400

Current source normalizes planner-wrapped timestamps, applies/validates timezone-aware RFC3339 values, rejects `end <= start`, and guards against accidental seconds-for-minutes durations. If this reappears, inspect the current `calendar.create` verification/action arguments rather than assuming Google itself is down.

## “Did that work?” repeats an action

That was a previously discovered defect. Current source routes explicit outcome checks through verification state rather than the planner and can recover a timed-out verification with a new observer pass. If repetition occurs on a deployed machine, confirm the backend revision is current.

## “What are my goals?” returns a Calendar event

That was another discovered seam bug. Current source has a deterministic current-goal fast path. If the wrong answer persists, update/restart the backend and check the Git SHA.

## World diagnostics warns that the audit wrapper is not installed

If this warning appears only in the **standalone diagnostic process** while the live `/health` endpoint reports `tool_audit=ready`, it is expected. A hard diagnostic `problem` is different and should not be ignored.

## Xcode app builds but a feature is missing from navigation

Confirm the Mac checkout is at the expected Git SHA and rebuild. The current main app exposes Jarvis / Local / World / Packs; the World tab was added specifically so goals/Waiting On/world-sync state are not hidden behind an unlinked view.

---

# Development philosophy and finish line

## Fixed twelve-criterion Definition of Done

The project completion contract is frozen as:

1. persistent world model;
2. identity continuity;
3. persistent intentions;
4. situational awareness;
5. cross-source reasoning;
6. Executive Loop;
7. closed-loop verification;
8. appropriate proactivity;
9. privacy/authority boundaries;
10. unified interaction/state;
11. operational reliability;
12. end-to-end demonstrations.

There is no Criterion 13.

Failures found while validating these properties are repairs of the existing contract, not evidence that the finish line should move.

## Source completeness vs runtime completeness

A feature can exist in source yet still fail on a real phone, a specific Bluetooth route, a provider API, Windows timing, or a long-lived database. The repository therefore distinguishes automated/source preflight from actual runtime/hardware acceptance.

## JARVIS-20 is a progress instrument

A better JARVIS-20 score means Jarvis is improving. It does not redefine completion.

## Recursive improvement

Future self-improvement is plausible only if the evaluator and safety constraints remain outside the candidate agent’s write authority. The goal is to optimize against hidden, changing tests—not teach Jarvis the answer key.

---

# Deterministic routing / smaller local model

The `jarvis/memomind-prep` branch now routes dozens of exact read/action patterns **without** invoking the Ollama Qwen planner. Shared streaming and non-streaming dispatch preserves existing approval gates; common calendar/Gmail/PC/browser/system/world operations, explicit structured writes, selected read-only workflows, routine briefings, daily journals, web-query cleanup, eight-family audited research plans and simple achieved-state goal contracts have deterministic paths. Nuanced open-ended language, semantic synthesis, novel workflows and model-based perception still use the appropriate model. `MODEL_FREE_OPERATIONS.md` documents the call-site inventory, default/opt-in model settings, tests and authenticated `/routing/status` telemetry.

# External evidence branch addendum

The `jarvis/memomind-prep` feature branch adds an **iPhone-first Physical** tab (Gen 1 Ray-Ban Meta voice compatible; MemoMind optional) and independently sourced public-world infrastructure. This includes bounded Caltrans remote camera/still watches; USGS earthquakes, NWS alerts, global modelled air data, OpenStreetMap public utilities, and regional OpenSky aircraft counts; plus an explicitly enrolled, separate local SEC/OFAC/EPA matter-diligence workbench. All watches require active enrollment and expire; camera detection is an uncertain two-distinct-frame model indication, never a verified incident. Personal watch source metadata may be mirrored into the canonical world graph; matter-specific source/claim data stays in the separate local matter and watch ledgers.

**`EXTERNAL_EVIDENCE_OPERATIONS.md` is the definitive feature/deployment/provider-coverage and privacy contract for this new branch.** It distinguishes implemented official adapters from unsupported worldwide CCTV, AIS, court/UCC/corporate-registry/OSHA and licensed 911/ALERTCalifornia sources. These source additions require a *new backend and iPhone build*, are not already deployed by an old Agency 1.0 install, and have not had real provider/account/device acceptance by merely passing simulator or synthetic CI tests.

# Related documentation

For deeper/reference material:

- **`FIXED_ENDPOINT_ACCEPTANCE.md`** — non-moving twelve-criterion completion contract.
- **`WORLD_MODEL_OPERATIONS.md`** — deployment/diagnostics/rollback contract. Note that some prose in older sections may lag the current schema; the current code target is schema v5.
- **`JARVIS_COMPLETE_CAPABILITIES_AND_BUILD_HISTORY.md`** — very long architecture/capability/build-history reference.
- **`SEARCH_INTEGRITY_AND_COVER_BENCHMARK.md`** — Jarvis Research Receipts and COVER benchmark.
- **`COVER_U_UNIVERSAL_BENCHMARK.md`** — universal non-saturating research-intelligence benchmark.
- **`JARVIS_20_EVALUATION.md`** — behavioral scorecard.
- **`JARVIS_20_PROCEDURAL_WORLDS.md`** — anti-overfitting procedural variants/world fuzzing.
- **`ios/FRONTEND_ONLY.md`** — detailed frontend-only capability documentation and historical deployment boundaries.
- **`ios/JarvisIOS/FeatureGuide.swift`** — in-app searchable feature/verification guide.

---

## Final note

Jarvis’s most important property is not that it can call many tools. It is that those tools, sensors, memories, identities, objectives, and outcomes are being forced into one evidence-bearing operational model.

A useful test of the architecture is whether the user can simply say:

```text
“Jarvis, anything I need to know before I go in?”
```

and receive the right answer without manually reminding Jarvis which meeting, which person, which project, which email, which document revision, which obligation, which critical number, or whether the last action actually worked.

That is the system this repository is building.