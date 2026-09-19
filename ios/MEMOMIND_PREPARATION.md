# MemoMind One × Jarvis: preparation and activation contract

Prepared September 18, 2026, from MemoMind's September 1 developer-access announcement and September 10 two-part-app SDK demonstration.

## What is already implemented

- iOS `MemoMindBridge.swift`: a vendor-agnostic, bounded monochrome HUD frame/card model, a local iPhone preview, an input-intent mapper, and a transport callback.
- **EDITH-inspired Command View:** the existing Glasses tab now requests authenticated `GET /agency/command-view` on entry and every 15 seconds *while the tab is visible*. It renders real persisted Agency mode, active/blocked goal counts, current plans, next recorded steps, approval backlog and emitted exception events. The backend model is read-only and does not call an LLM, plan, execute or imply that unobserved conditions are current.
- Existing authenticated companion `proactive_alert`/job-completion messages flow to opt-in HUD cards using the iPhone's existing threshold filter. Backend alert text and goal details are private by default on the glasses; they never activate voice recording.
- Completed Jarvis replies are delivered to the *iPhone-side* bridge from the existing `JarvisAppModel.recordTurn` path; there is no additional model, memory store, network endpoint, or AI assistant.
- New **Glasses** tab renders the same current frame as the proposed physical-device adapter and simulates taps and navigation.
- The bridge accepts future touch, head-gesture, and KiWear ring events as **semantic** inputs, not guessed BLE bytes or guessed vendor enums.
- Glasses pairing is never fabricated: connection status starts at `Simulator only`; a physical driver must report connected after an actual handshake.
- Private Jarvis replies are hidden by default on the HUD. A dedicated toggle enables display; this setting does **not** enable capture/recording.
- Approval cards direct the wearer to iPhone. A tap/nod/ring select **does not execute** a protected action, approve an Agency plan, email anyone, or dismiss the backend's pending approval.

## Portable physical-world sensor: official public camera catalog

A standalone physical-world discovery panel lives in **Physical → Public viewpoints** on the normal iPhone tab bar; it has no MemoMind runtime prerequisite. A button asks the iPhone for its position once, then calls the authenticated Jarvis backend via `POST /physical/public-cameras` with coordinates in the JSON body (not URL access logs). The backend does not persist the location. It looks up published government highway-camera locations, sorts by distance, and returns publicly posted images and optional streams. The iPhone renders publisher still images and offers the official stream directly; the backend does not scrape camera firmware, scan nearby IP ranges, or proxy footage.

First integrated provider: **Caltrans CWWP2**, 12 official district JSON feeds. Source: https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm. In-service status comes from the provider's catalog and does **not** establish that the returned image is currently working or live. The camera catalog is cached for 15 minutes and partial provider outages are surfaced, not silently converted into "no cameras". Media URL hosts are constrained to documented Caltrans HTTPS hosts.

The global interface is intentionally honest about coverage. For Melbourne, the endpoint currently returns `unsupported_region` plus VicTraffic's official traffic information site; it does **not** suggest that Melbourne public-safety CCTV is open to the public or that an undocumented local-stream API exists. New geography requires a verified published provider and usage rights. Worldwide device access depends on the iPhone's network, not joining a stranger's Wi-Fi/LAN.

This is a camera **discovery and viewing** prototype, not yet a vision-LLM analysis pipeline; capturing and interpreting third-party camera imagery should be an explicit, provenance-labelled operation with temporal freshness checking and no stranger identification or indefinite recording. The backend-camera feature requires deploying this preparation branch, and the iPhone UI requires installing this branch's app.

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
