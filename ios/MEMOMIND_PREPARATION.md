# MemoMind One × Jarvis: preparation and activation contract

Prepared September 18, 2026, from MemoMind's September 1 developer-access announcement and September 10 two-part-app SDK demonstration.

## What is already implemented

- iOS `MemoMindBridge.swift`: a vendor-agnostic, bounded monochrome HUD frame/card model, a local iPhone preview, an input-intent mapper, and a transport callback.
- **EDITH-inspired Command View:** the optional Glasses simulator (under Physical) now requests authenticated `GET /agency/command-view` on entry and every 15 seconds *while the tab is visible*. It renders real persisted Agency mode, active/blocked goal counts, current plans, next recorded steps, approval backlog and emitted exception events. The backend model is read-only and does not call an LLM, plan, execute or imply that unobserved conditions are current.
- Existing authenticated companion `proactive_alert`/job-completion messages flow to opt-in HUD cards using the iPhone's existing threshold filter. Backend alert text and goal details are private by default on the glasses; they never activate voice recording.
- Completed Jarvis replies are delivered to the *iPhone-side* bridge from the existing `JarvisAppModel.recordTurn` path; there is no additional model, memory store, network endpoint, or AI assistant.
- The optional **Glasses simulator** renders the same current frame as the proposed physical-device adapter and simulates taps and navigation.
- The bridge accepts future touch, head-gesture, and KiWear ring events as **semantic** inputs, not guessed BLE bytes or guessed vendor enums.
- Glasses pairing is never fabricated: connection status starts at `Simulator only`; a physical driver must report connected after an actual handshake.
- Private Jarvis replies are hidden by default on the HUD. A dedicated toggle enables display; this setting does **not** enable capture/recording.
- Approval cards direct the wearer to iPhone. A tap/nod/ring select **does not execute** a protected action, approve an Agency plan, email anyone, or dismiss the backend's pending approval.

For operational details of the broader remote-eye watches, regional airspace/USGS detections and matter-scoped SEC/OFAC/EPA diligence, see `EXTERNAL_EVIDENCE_OPERATIONS.md` in the repository root.

## Primary camera-free MemoMind / ambient runtime

MemoMind does not have to supply a camera. Jarvis's primary presence inputs are authorized microphone capture, iPhone GPS/geofence and motion, separately opted-in Apple Health data, and source-labelled public environmental models. The prior camera-to-opportunity bridge has been removed. Meta first-person vision and official public-camera searches remain optional, separate features, not architectural prerequisites.

### Implemented, opt-in signals

- **Microphone:** existing iPhone/Bluetooth HFP audio route; on-device SoundAnalysis class, confidence and timestamp when the Sound Recognition setting is enabled. While voice capture is active it reuses the existing speech-recognition microphone tap; when idle and foregrounded, an independent on-device sound-label-only microphone tap can run after separate opt-in and iOS permission. It yields audio ownership before speech, meeting capture and TTS, and never claims iOS background persistence or access to unshipped MemoMind audio.
- **GPS / geofence:** existing Core Location home/away callbacks, rounded transient coordinates, fresh separate GPS and motion timestamps. Requires active iPhone app, permissions and opt-in Motion / travel context. A first fix at home is not treated as an arrival.
- **Motion:** Core Motion activity; driving or an active conversation suppresses nonessential sensor interruptions. Motion cannot establish destination or user intent.
- **Health:** separately opt-in Apple Health / Watch heart rate, HRV and sleep data over the existing authenticated companion link. Read-only; no diagnoses, clinical interventions or inferred emotional state.
- **Outdoor temperature:** separately opt-in Open-Meteo current modelled 2-m temperature, up to one provider request per 15 minutes when a fresh coarse GPS fix exists. An iPhone/MemoMind ambient thermometer is not assumed. The alert includes the model timestamp and provenance.

The camera-free ambient engine matches exact standing reminder goals of the form “Remind me to X when I get/leave home”, “... when the doorbell rings”, and “... when it's cold/hot”. It produces only source-labelled, deduplicated Agency Attention messages. It does not treat ambient speech or a sound classifier output as an instruction to send messages, unlock devices or make purchases.

**Verified physical steps:** after the user explicitly discovers HomeKit, they may individually enroll one of the discovered *lights* as Auto on arrival. A second exact-light grant is "Doorbell 18:00–07:00": two fresh >=0.90 on-device classifications within 0.5–10 seconds, independently checked fresh GPS position inside the configured home radius, an active app, explicit sound/motion/opportunity opt-ins and HomeKit availability must agree before the enrolled light is turned on. This is a low-risk, reversible illustration of an acoustic + geographic + time-bound physical intervention; it is not proof a person rang or is at the door. Each attempted enrolled light command has fresh HomeKit readback and a device-only Keychain receipt (last 40; clearable from the Physical tab). Explicit per-light enrollment reconnects HomeKit on relaunch, not a blanket scope grant.

**Arrival path:** With proactive sensor opportunities, Motion / travel context and geofenced profile enabled, Jarvis can turn that light on upon a new observed away→home transition while the iPhone app is running. At most five preapproved lights are processed; each command uses HomeKit's fresh readback. The first home fix at startup is not an arrival; repeated geofence toggles are debounced for five minutes. Per-light revocation, disabling sensor opportunities, or Privacy mode prevents additional automatic actions. No lights are implicitly enrolled or remotely controlled by Qwen.

Physical-device validation must test actual iPhone foreground/background transitions, HomeKit permission revocation, the configured home radius, sound-classifier false positives, geofence bouncing, app relaunch and incorrect readback. Simulator compilation alone does not confirm this behavior.

Sensor snapshots travel through the existing authenticated companion link and are stripped before the persistent environment/world snapshot pathway. Only expiring in-memory rounded GPS and sound baselines are used; no raw audio, transcripts, image frames or GPS trails are persisted by this new engine. `/ambient/status` is authenticated and reports capability status rather than personal readings. Public weather providers see query coordinates and have their own logging and terms.

**Next architectural target:** explicit user objective → fresh acoustic/geographic/temporal/environmental evidence → independently generated intervention candidates → deterministic actuator affordance/authority check → execution and observed outcome → rollback or escalation. This is not complete cinematic improvisation yet; safe autonomy must be bounded by real device interfaces and individual authorizations, not broad model-inferred permission.

## Counterfactual Guardian: first working calendar/departure rescue slice

After enabling **Guard calendar departures proactively** (off by default) plus **Motion / travel context and GPS**, the foreground iPhone fetches bounded, authenticated *primary* Google Calendar event IDs/titles/start times/literal locations from the Windows backend at most once per two minutes. Only the phone resolves a unique real MapKit place, reads a fresh accurate Core Location fix and asks MapKit for an actual driving ETA. Missing/ambiguous/stale evidence is never called an all-clear. The deterministic five-minute departure buffer is explicitly stated.

The user sees a departure risk before its calendar deadline, with exact calendar/time/route provenance in **Physical → JARVIS • Counterfactual Guardian**. A spoken “Will I make my next meeting?” or “Check next departures” invokes that same evidence-backed check without the language model planner. Alerts are quiet when driving, a meeting/command is active, or the user's interruption settings prohibit speech. The optional MemoMind simulator displays private alert cards redacted by default; the vendor's real SDK remains a separate pending dependency.

**Permitted alternatives:** Start directions is an explicit iPhone tap. Allow one automatic Maps launch creates a revocable, Keychain-protected authorization for exactly one event ID/start/location and expires by its start; launch consumes it before invoking the Apple Maps API. Local ETA message is only staged for display and optional copy, with no recipient and no send path. Receipts say only if Maps accepted the handoff, not that navigation continued or the user arrived. A displayed risk can be dismissed with its grant revoked. A disabled Guardian does not poll or launch Maps autonomously.

**Acceptance remaining:** deploy the new backend endpoint and app together, verify real phone Location/Calendar permissions and Tailscale/LAN behavior, test GPS expiry, ambiguous MapKit addresses, offline backend and device transition/backgrounding. Simulator CI does not prove physical device behavior. This is an actual, narrow trajectory-rescue loop, not general predictive omnipotence; the wider expectation ledger and typed intervention broker are specified in `COUNTERFACTUAL_GUARDIAN.md`.

## Portable physical-world sensor: official public camera catalog

A standalone physical-world discovery panel lives in **Physical → Public viewpoints** on the normal iPhone tab bar; it has no MemoMind runtime prerequisite. A button asks the iPhone for its position once, then calls the authenticated Jarvis backend via `POST /physical/public-cameras` with coordinates in the JSON body (not URL access logs). The backend does not persist the location. It looks up published government highway-camera locations, sorts by distance, and returns publicly posted images and optional streams. The iPhone renders publisher still images and offers the official stream directly; the backend does not scrape camera firmware, scan nearby IP ranges, or proxy footage.

First integrated provider: **Caltrans CWWP2**, 12 official district JSON feeds. Source: https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm. In-service status comes from the provider's catalog and does **not** establish that the returned image is currently working or live. The camera catalog is cached for 15 minutes and partial provider outages are surfaced, not silently converted into "no cameras". Media URL hosts are constrained to documented Caltrans HTTPS hosts.

The global interface is intentionally honest about coverage. For Melbourne, the endpoint currently returns `unsupported_region` plus VicTraffic's official traffic information site; it does **not** suggest that Melbourne public-safety CCTV is open to the public or that an undocumented local-stream API exists. New geography requires a verified published provider and usage rights. Worldwide device access depends on the iPhone's network, not joining a stranger's Wi-Fi/LAN.

Camera **discovery, viewing and explicit one-still interpretation** are now included. Tap **Analyze this public still with Jarvis**, or after finding cameras say **“Jarvis, analyze the nearest public camera.”** The backend verifies the selected camera ID against the live official district catalog, fetches only its official still image with bounded MIME/byte checks, and uses the existing local Ollama vision model without adding the image to first-person vision/memory. Images are not retained or continuously recorded. It reports retrieval time but does NOT claim to know when the publisher captured the frame or whether it covers a requested street corner. No person/license plate identification or arbitrary image URL is allowed. The backend-camera feature requires deploying this preparation branch, and the iPhone UI requires installing this branch's app.

## One-command physical-world briefing

**Physical → JARVIS • Situational briefing** or **“Jarvis, establish situational awareness”** on the existing iPhone/Gen 1 Meta hands-free route uses a single one-shot iPhone location request followed by four parallel, independent public-source checks: published Caltrans highway cameras when integrated, global Open-Meteo air/UV model with data timestamp, US NWS active point alerts where supported, OpenStreetMap public facilities, and USGS earthquake detections. The response is a deterministic, sourced summary that makes missing feeds and unsupported regional alert coverage explicit. It does not assert traffic safety, detect hidden conditions, constantly track the user or claim that Meta can display a HUD.

The request populates the ordinary Physical tab's individual source cards so the user can inspect still images, optionally analyze one selected public still with local vision, see warnings, and open walking directions. MemoMind remains an optional output surface of existing Jarvis state.

## Additional portable real-world capabilities

1. **Air quality / UV**: `POST /physical/conditions` queries Open-Meteo's documented global CAMS-based air-quality model with a one-shot iPhone location. Reports model timestamp, US AQI reference scale, PM₂.₅, UV and the distinction between regional *model output* and an actual local sensor. Free API is for this private non-commercial use; any commercialization requires a paid licence or another provider. https://open-meteo.com/en/docs/air-quality-api
2. **Official US weather alerts**: the same request checks NWS active warnings/advisories specific to the current coordinates for supported US locations. It omits expired alerts. In Melbourne or other unsupported areas, the answer clearly says `unsupported_region`; network errors also never become a false “all clear.” https://www.weather.gov/documentation/services-web-alerts
3. **Worldwide public facilities**: `POST /physical/facilities` runs a bounded, rate-limited Overpass/OpenStreetMap query for mapped toilets, drinking water and defibrillators within 1.5 km. iPhone shows distance, publisher record and walking directions, and preserves mapped access/hours when present. Community tags can be missing or wrong: not a life-safety or emergency locator. It uses one explicit request and does not attempt generic LAN/device discovery. © OpenStreetMap contributors https://www.openstreetmap.org/copyright and https://wiki.openstreetmap.org/wiki/Overpass_API

4. **Explicit public still analysis**: `POST /physical/public-cameras/analyze` takes an official catalog camera ID, never a user-supplied URL, and runs one published still through the existing local vision model. This does not confer real-time situational awareness, verify lane/road status or attach the public viewpoint to Meta first-person perception; the camera direction and image capture timestamp are not independently established. An absent still image is not silently substituted with streaming media.\n\nIn the standalone **Physical** tab, **Check conditions around me**, **Find public resources near me**, and **Find nearby public cameras** share the existing one-shot iPhone Core Location flow. On the existing Gen 1 Meta audio route, voice intents such as “Jarvis, check conditions around me” and “Jarvis, find public resources near me” are handled locally before the generic LLM; the answer is spoken without claiming any glasses display.

The backend uses authenticated POST bodies for coordinates to avoid application access logs that capture URLs, but public external data providers necessarily see the query location and may retain their own network logs. No background sampling/ambient location surveillance is implemented. iPhone results are retained only in the current session's app-model state. The Mac CI builds the source; the final physical-device acceptance still requires installing this branch's backend and iPhone binary.

## Hardware-independent iPhone / Gen 1 Ray-Ban Meta path

- The primary **Physical** tab is an ordinary iPhone surface. It contains one-shot public camera search and opt-in Apple Home light discovery/control. It works without possessing or pairing MemoMind.
- A spoken **“Jarvis, find nearby public cameras”** (or “find nearby traffic cameras”) goes through the existing iPhone wake/STT/response path, returns a concise answer through iPhone or the selected Bluetooth HFP device, and populates the *same* Physical tab camera results. It does not send any camera imagery into the glasses or claim to analyze imagery.
- Gen 1 Ray-Ban Meta serves as existing Bluetooth microphone/speaker hardware, plus any already supported Meta DAT camera functions. No Gen 1 optical display/HUD is implied; the iPhone shows photos, links and controls. The physical camera provider and Apple Home layer do not depend on Meta glasses either.
- Apple Home light discovery is explicit, the enrolled light must be name-unambiguous, and write attempts require fresh HomeKit readback; no general unauthorized LAN discovery or arbitrary actuator control.
- The MemoMind **Glasses** simulator remains available from **Physical → Open experimental glasses simulator**. It is an optional projection of the same Jarvis state, not the entrypoint for physical-world features.
- Backend camera discovery requires running this branch; an older `jarvis/agency-1.0` backend returns HTTP 404 for `/physical/public-cameras`. The iPhone also needs the new build. Current automated builds do not substitute for real Gen 1 glasses/audio and physical iPhone acceptance.

## Command View usage now

1. Deploy the MemoMind-prep branch to the Windows backend to enable the read-only command-view endpoint; the Agency 1.0 backend branch alone does not include that endpoint.
2. Build and install the MemoMind-prep iPhone client. Open **Glasses**. It displays the backend's real saved goal/plan/approval status, or an explicit error if it cannot connect. No fabricated goal counts are displayed.
3. Turn on **Show private Jarvis replies on HUD** to inspect real cards in the iPhone simulator. Leave it off to verify redaction.
4. The status view is not an Agency-mode switch; use the normal, confirmation-protected command flow to enable Agency. A glasses/ring gesture cannot authorize a protected action.
5. The existing Bluetooth audio route may send Jarvis speech to compatible glasses today; actual MemoMind HUD transport still awaits the vendor interface.

## Physical actuation proof-of-concept: Apple Home lights

The iPhone now includes `HomeEnvironmentController.swift` (in the **Glasses** tab) so Jarvis can interact with actual Apple Home lights *without MemoMind hardware*. This is intentionally distinct from the Windows `smart.open` tool, which launches an app/site rather than operating a household device.

1. In Xcode, select an Apple signing team with the **HomeKit** capability. The iPhone app now declares `com.apple.developer.homekit` and explains permission in `NSHomeKitUsageDescription`.
2. On the physical iPhone, open **Glasses → Discover Apple Home**, permit access, and inspect the discovered, directly reachable lightbulb services. Home access is not requested when Jarvis launches.
3. Tap **On**/**Off** for a named light or say "Jarvis, turn on [exact device name]". Jarvis deliberately requires exact single-device matches; ambiguous names are blocked.
4. After HomeKit accepts the write, Jarvis performs a *fresh* HomeKit characteristic read. "Verified in Apple Home" means the accessory reported the target value; it is not optical proof that a bulb emitted light.
5. This does **not** expose scenes, locks, garage doors, outlets, shades, security systems, general electrical relays, or HomeKit credentials to the Windows agent. Do not mistake this iPhone-local capability for autonomous Agency control. Shades and broader authorized devices can be introduced once the light-only real-world loop works.

**Hardware reality:** Apple Home integration exists only for devices already paired/bridged there. Lutron Caséta can publish compatible lamps to HomeKit via its Smart Bridge. The actual device list, authorization and readback must be checked on the phone; no house-specific devices are hardcoded.

## Why this is not a full hardware driver yet

MemoMind says its first developer phase will include documented Bluetooth commands for HUD text/visuals, touch/button events, and microphone audio, with sample code. On September 10 it described a more extensive two-part SDK: **C on the glasses** and a **JavaScript phone plugin** in Memo Lab, with `.mmpkg` / `.gmp` packaging and a vendor simulator. The beta is targeted for **mid-October 2026**, initially whitelisted. That changes whether the appropriate final transport is direct CoreBluetooth in Jarvis iOS or a Memo Lab phone-plugin adapter. Do not guess a BLE UUID, advertise pairing, ship reverse-engineered commands, or assume the JS plugin can call into an unrelated iOS app without a documented bridge.

Official public source material:
- https://www.prnewswire.com/news-releases/memomind-one-opens-developer-access-announces-kiwear-as-first-sdk-partner-302865894.html
- https://www.memo-mind.com/ja/blogs/tech-hub/how-to-build-apps-for-smart-glasses-memomind-developer-platform-demo
- https://www.memo-mind.com/pages/memomind-one

## Proposed deployment

```text
MemoMind HUD / touch / head movement / KiWear ring
                   ↕ documented MemoMind transport (not implemented)
           iPhone: MemoMindBridge
                   ↕ already-existing JarvisAppModel and voice session
           authenticated Jarvis backend over existing private connection
                   ↕
         existing tools / Agency / world model / verification
```

Glasses remain **an I/O surface**, not a second authority, identity provider, AI backend, or store of unredacted transcripts.

The glasses are camera-free. Do not treat MemoMind as a replacement for Meta's video/vision feed; visual world grounding needs the separate approved phone/Meta camera surface. Its speaker/microphone paths should reuse the existing iPhone Bluetooth audio routing and *explicit* microphone permission settings; no independent always-on room recorder is to be added for this integration.

## Activation checklist (after hardware and official SDK/protocol are in hand)

1. Obtain the exact vendor developer package/protocol, verify version, sample license, and whether the iPhone companion may access the stream concurrently with Memo Lab. Record compatible iOS, firmware, SDK, and Memo app versions.
2. Choose the **documented** integration route: direct iOS BLE if officially supported, otherwise the C/JS paired Memo Lab application and a supported authenticated handoff. Never create a listener reachable from the open Internet to work around an iOS app boundary.
3. Implement the transport interface that supplies `onHUDFrame` and maps verified physical controls to `receive(_:) `; prove reconnect, disconnection, app backgrounding, battery/latency and display blanking.
4. Connect wearer speech to the existing Jarvis wake/voice session *only when iOS actually exposes the mic audio*. Verify whether the SDK stream is wearer-isolated or can preserve other speakers; do not claim meeting/far-field capture based on the hardware's own first-party recorder alone.
5. Add **separate opt-in** for microphone listening and meeting/nearby-speaker transcription. The HUD may show live captions only for an actively captured, authorized session. Recordings are not automatically copied to the world model.
6. Bind all approvals to the exact pending action, its audible/visible details, an explicit intentional input, and the existing Jarvis permission engine. For the first physical version keep protected actions on iPhone until real gesture provenance and accidental-input behavior are verified.
7. Exercise real end-to-end commands: one read, one Agency status lookup, one multi-step goal, one protected action requiring iPhone approval, one denied action, disconnect/reconnect, and one user privacy toggle. Require observed glass HUD output rather than simulator success.

## UX targets to revisit after optical testing

The provisional renderer uses 34 characters/line, six lines/card, twenty in-memory cards and no graphics. MemoMind's own pages list 640×350 30Hz while its September game demo describes 600×350 at 20 fps. Do not encode either value as the wire-level truth; calibrate using real SDK and device metrics. Favor one-line glanceable status, compact goal progress, and explicit "needs phone approval" over long paragraphs.

## Non-goals

No automated BLE discovery, device registration, transcript sync, private API calls, speculative pairing, ring-as-universal-confirm, or duplicate Memo AI memory. The existing Meta DAT camera implementation must continue to work independently.
