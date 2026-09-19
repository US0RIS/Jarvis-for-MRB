# MemoMind One × Jarvis: preparation and activation contract

Prepared September 18, 2026, from MemoMind's September 1 developer-access announcement and September 10 two-part-app SDK demonstration.

## What is already implemented

- iOS `MemoMindBridge.swift`: a vendor-agnostic, bounded monochrome HUD frame/card model, a local iPhone preview, an input-intent mapper, and a transport callback.
- Completed Jarvis replies are delivered to the *iPhone-side* bridge from the existing `JarvisAppModel.recordTurn` path; there is no additional model, memory store, network endpoint, or AI assistant.
- New **Glasses** tab renders the same current frame as the proposed physical-device adapter and simulates taps and navigation.
- The bridge accepts future touch, head-gesture, and KiWear ring events as **semantic** inputs, not guessed BLE bytes or guessed vendor enums.
- Glasses pairing is never fabricated: connection status starts at `Simulator only`; a physical driver must report connected after an actual handshake.
- Private Jarvis replies are hidden by default on the HUD. A dedicated toggle enables display; this setting does **not** enable capture/recording.
- Approval cards direct the wearer to iPhone. A tap/nod/ring select **does not execute** a protected action, approve an Agency plan, email anyone, or dismiss the backend's pending approval.

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
