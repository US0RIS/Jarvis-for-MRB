# HORUS — AirPods-first camera-dependency audit

**Status:** Binding current implementation interpretation for future.md and the implementation packets. The original 1,869-line [source archive](archive/FUTURE_IDEAS_2026_10.md) and its [480-item trace](implementation_batches/TRACE.md) remain unchanged for auditability. The full archive was inspected for both explicit first-person camera requirements and implicit visual/HUD/scene assumptions; affected and adjacent entries are mapped below, not all unrelated bookkeeping ideas.

## Product north star

**Horus primarily lives in an earbud, not behind a camera.** Default user hardware is ordinary AirPods or compatible Bluetooth headphones and an iPhone (with optional PC/cloud computation). It should feel like a responsive, discreet conversational agent that knows what trusted digital sources and explicitly provided observations tell it. **No smart glasses, body-worn cameras, first-person video, optical overlay, or extra physical sensor purchase can be a prerequisite for core Horus.**

Headphones are an audio interface, not a computer vision system, autonomous location sensor or unrestricted background microphone. User initiation, consent, iOS audio routes, interruption, background suspension, private TTS, a stop control and a text fallback must work within **actual** OS capabilities; never promise continuous listening or a hardware wake word without real acceptance testing.

### Sensory hierarchy

1. **User-confirmed voice reports.** Example: 'Remember the jumper cables are in the trunk.' Keep the explicit assertion, origin, timestamp and correction history; it is user-reported, not visually verified.
2. **Authorized phone and digital state.** Calendar, maps and location only with permission, known apps/documents, files, messages, system/tool receipts, named object records, device capabilities. A GPS point is not a room/orientation or proof of a person's presence.
3. **Authorized remote sources.** Official weather/fire/road/transit data, aircraft/vessel feeds, RF/sensors owned or enrolled by the user, user-owned smart devices, and optionally fixed public/owned camera feeds. **Public/owned remote cameras can remain useful without being attached to the user.**
4. **Explicit opt-in visual mode.** If the user deliberately supplies a phone photo, screenshot, fixed-camera frame or supported glasses feed, vision can enrich a result. The absence of that source must yield a narrower source-qualified answer or 'unknown', never an invented scene.

**Output hierarchy:** concise private earbud speech and subtle consented earcons; optional discreet phone notification or phone/desktop detail. HUD, AR, constant world dashboard and visual labels are optional output surfaces, not the way the product fundamentally works.

**Evidence labeling:** use 'user-reported', 'provider-reported', 'directly verified source', 'inferred', 'historical last observation', 'stale/unknown' and 'explicit opt-in visual observation' accurately. No camera does **not** mean all physical facts can be inferred from radio, noise or nearby phones. No source means unknown, not absence. Device proximity is not personal identity.

## Camera-free examples

- 'Horus, remember I put the screwdriver in the garage drawer.' → durable user-report, timestamp, possibly explicitly named room; later search returns last reported position, not 'I can see it.'
- 'What's around me?' → permitted phone location and mapped points of interest; no location permission means ask the user for the place; no claim of what is in front of their eyes.
- 'Remember this.' → if 'this' has no referenced document/device/place, ask what should be remembered; create a voice/context bookmark, not a fabricated snapshot.
- 'What changed here?' → compare sensor/API/user-reported events; cannot know that furniture moved without suitable data.
- 'Watch for delayed trains on my commute.' → consented, expiring real-time transit monitor with sourced updates and private notification, never a camera requirement.
- 'Get me to Alex.' → Callless as permission-based remote conversational proximity with honest live-audio state and cues; no first-person video needed.

## Classification

**CORE** = reframe camera-free from spoken facts, permitted phone/digital context and typed sensors. **OUTPUT** = use private speech/earcons; visual UI only optional. **EXTERNAL** = camera is optional fixed/public/owned evidence, not user-mounted. **GATED** = a genuinely visual claim requires independently authorized imagery or geometric hardware; camera-free mode must degrade honestly. **RESEARCH** = third-party vision or GUI research does not become a default dependency.

## Source-by-source crosswalk

| Original source | Packet | Category | Current implementation requirement |
|---|---|---|---|
| [L51](archive/FUTURE_IDEAS_2026_10.md#L51) | P05-001 | CORE | Calendar and location from explicit destinations and permissioned Maps; not a camera lens. |
| [L68](archive/FUTURE_IDEAS_2026_10.md#L68) | P05-002 | CORE | Named room, declared arrival, NFC/QR, opted-in geofence or enrolled device; no visual room recognition. |
| [L102](archive/FUTURE_IDEAS_2026_10.md#L102) | P02-001 | OUTPUT | Private spoken whats-next summary, with optional phone widget; no HUD. |
| [L107](archive/FUTURE_IDEAS_2026_10.md#L107) | P02-001 | OUTPUT | Spoken system-status inquiry and rare private earcons instead of mandatory persistent indicator. |
| [L131](archive/FUTURE_IDEAS_2026_10.md#L131) | P02-003 | OUTPUT | Audio mission briefs, optional phone/desktop command-center drill-down. |
| [L175](archive/FUTURE_IDEAS_2026_10.md#L175) | P06-002 | EXTERNAL | DOT camera feeds only optional remote evidence; road incidents/closures and traffic reports first. |
| [L177](archive/FUTURE_IDEAS_2026_10.md#L177) | P06-002 | EXTERNAL | Optional remote wildfire cameras; official fire/weather/perimeter alerts first. |
| [L180](archive/FUTURE_IDEAS_2026_10.md#L180) | P06-002 | EXTERNAL | Optional coastal webcam; buoy, tide, port and closure data first; crowd level unknown without evidence. |
| [L280](archive/FUTURE_IDEAS_2026_10.md#L280) | P03-004 | CORE | Trip data from confirmations, flight/rail, weather and warnings, not an assumed webcam. |
| [L313](archive/FUTURE_IDEAS_2026_10.md#L313) | P06-006 | CORE | Rewind structured timestamped observations; not a user-viewpoint video DVR. |
| [L317](archive/FUTURE_IDEAS_2026_10.md#L317) | P06-007 | CORE | Diff provider/owner/typed reported state; do not assert visual object appearance without images. |
| [L330](archive/FUTURE_IDEAS_2026_10.md#L330) | P06-010 | CORE | Stable user-named objects from speech, device identities, documentation, NFC/QR; optional vision. |
| [L335](archive/FUTURE_IDEAS_2026_10.md#L335) | P06-011 | CORE | Remember user-confirmed place/object/context in audio with timestamp; no 3-D anchor/photo required. |
| [L338](archive/FUTURE_IDEAS_2026_10.md#L338) | P06-012 | CORE | Find last user-reported/observed item location, with timestamp and uncertainty; not live visual tracking. |
| [L342](archive/FUTURE_IDEAS_2026_10.md#L342) | P06-013 | CORE | World Search via authorized weather, transit, ships, ADS-B, APIs and devices; remote cameras optional. |
| [L347](archive/FUTURE_IDEAS_2026_10.md#L347) | P06-014 | CORE | Fuse authorized audio, RF, location, phone and telemetry; never infer nonexistent visual evidence. |
| [L355](archive/FUTURE_IDEAS_2026_10.md#L355) | P06-016 | CORE | User-narrated physical procedures plus device receipts; confirm steps rather than claim unobserved completion. |
| [L382](archive/FUTURE_IDEAS_2026_10.md#L382) | P01-006 | CORE | Show source coverage and blind spots, not visual omniscience. |
| [L392](archive/FUTURE_IDEAS_2026_10.md#L392) | P01-007 | OUTPUT | Voice explanations of reported, inferred, stale and unknown evidence; color-only HUD insufficient. |
| [L394](archive/FUTURE_IDEAS_2026_10.md#L394) | P01-008 | CORE | Watch exact source/entity/condition IDs, not wherever a personal camera points. |
| [L396](archive/FUTURE_IDEAS_2026_10.md#L396) | P01-008 | CORE | Follow matched entity across authorized data sources; no continuous camera requirement. |
| [L427](archive/FUTURE_IDEAS_2026_10.md#L427) | P05-003 | OUTPUT | Earbud-private speech/quiet cues first, approved other devices optional. |
| [L432](archive/FUTURE_IDEAS_2026_10.md#L432) | P05-003 | OUTPUT | Audio or silence before phone notifications; HUD or room displays optional. |
| [L445](archive/FUTURE_IDEAS_2026_10.md#L445) | P05-004 | CORE | Invocation from voice/action or enrolled phone/place events, not gaze. |
| [L448](archive/FUTURE_IDEAS_2026_10.md#L448) | P05-004 | CORE | Conversation handoff from earbuds/phone to car or PC; no glasses dependency. |
| [L453](archive/FUTURE_IDEAS_2026_10.md#L453) | P05-005 | CORE | Quick spoken memo/share-sheet capture; photos explicitly user-selected optional source. |
| [L458](archive/FUTURE_IDEAS_2026_10.md#L458) | P05-005 | CORE | Attach approved app/calendar/place context, not invented POV or unrestricted screen state. |
| [L522](archive/FUTURE_IDEAS_2026_10.md#L522) | P05-012 | OUTPUT | Earcons or spoken states; light/HUD optional. |
| [L574](archive/FUTURE_IDEAS_2026_10.md#L574) | P02-005 | OUTPUT | Audio interruption arbitration, private cues and silence; optional desktop map. |
| [L579](archive/FUTURE_IDEAS_2026_10.md#L579) | P02-005 | OUTPUT | Spoken operational briefing with optional mission visualization, not continuous display. |
| [L713](archive/FUTURE_IDEAS_2026_10.md#L713) | P06-022 | CORE | Semantic world layer of named places, device IDs, reported objects and live API evidence. |
| [L716](archive/FUTURE_IDEAS_2026_10.md#L716) | P06-023 | CORE | Cross-device semantic place IDs; precise geometric AR anchors optional only when supported. |
| [L719](archive/FUTURE_IDEAS_2026_10.md#L719) | P06-023 | GATED | Downgrade to coarse location/zone confidence; drift/re-localization requires real suitable hardware. |
| [L722](archive/FUTURE_IDEAS_2026_10.md#L722) | P06-023 | CORE | Offer relevant voice help after consented geofence/NFC/manual context, not silently detected room entry. |
| [L725](archive/FUTURE_IDEAS_2026_10.md#L725) | P06-024 | CORE | Speak labels/status for explicitly bound device or object; visual overlays optional. |
| [L728](archive/FUTURE_IDEAS_2026_10.md#L728) | P06-024 | CORE | Location-tagged spoken reminders using permitted place binding; no AR note surface required. |
| [L730](archive/FUTURE_IDEAS_2026_10.md#L730) | P06-025 | CORE | Collaborators share named objects/place evidence under permission, without shared visual anchors. |
| [L733](archive/FUTURE_IDEAS_2026_10.md#L733) | P06-026 | GATED | Spoken procedures with manual acknowledgment or sensor readback; no phantom visual verification. |
| [L736](archive/FUTURE_IDEAS_2026_10.md#L736) | P06-027 | GATED | Compare structured state over time; scene-image diff only with authorized image baselines. |
| [L738](archive/FUTURE_IDEAS_2026_10.md#L738) | P06-027 | CORE | Room registry from user labels/enrolled devices, not fabricated geometric floorplan. |
| [L741](archive/FUTURE_IDEAS_2026_10.md#L741) | P06-027 | CORE | Place-bound live information delivered in ear when location/context known, not view triggered. |
| [L750](archive/FUTURE_IDEAS_2026_10.md#L750) | P02-009 | OUTPUT | Speech first, phone text/haptic fallback, no mandatory AR display. |
| [L753](archive/FUTURE_IDEAS_2026_10.md#L753) | P02-009 | CORE | Negotiate actual mic/audio route and permission; no always-on access assumption. |
| [L756](archive/FUTURE_IDEAS_2026_10.md#L756) | P02-010 | GATED | Map/place/known-object explanation without camera; actual visual scene is unavailable without imagery. |
| [L758](archive/FUTURE_IDEAS_2026_10.md#L758) | P02-010 | CORE | Named GPS route landmarks, not automatically seen roadside landmarks. |
| [L760](archive/FUTURE_IDEAS_2026_10.md#L760) | P02-010 | CORE | OS accessibility and DOM for digital UIs; optional authorized screenshot, no worn camera. |
| [L788](archive/FUTURE_IDEAS_2026_10.md#L788) | P05-020 | OUTPUT | Voice phrases and phone shortcuts first, optional generated visual widgets. |
| [L983](archive/FUTURE_IDEAS_2026_10.md#L983) | P09-001 | RESEARCH | Desktop accessibility/native state before screenshot/VLM fallback. |
| [L992](archive/FUTURE_IDEAS_2026_10.md#L992) | P09-001 | RESEARCH | Windows native UI automation first; visual desktop reasoning optional. |
| [L997](archive/FUTURE_IDEAS_2026_10.md#L997) | P09-002 | RESEARCH | Screenshot GUI agent is optional for digital screens, not a first-person wearable camera. |
| [L1010](archive/FUTURE_IDEAS_2026_10.md#L1010) | P09-003 | RESEARCH | Learn digital workflows from semantic events/receipts; video replay optional. |
| [L1035](archive/FUTURE_IDEAS_2026_10.md#L1035) | P09-005 | RESEARCH | go2rtc for separately authorized fixed camera sources only; not standard install. |
| [L1040](archive/FUTURE_IDEAS_2026_10.md#L1040) | P09-005 | RESEARCH | Scrypted optional external/home camera evaluation, not base Horus. |
| [L1044](archive/FUTURE_IDEAS_2026_10.md#L1044) | P09-005 | RESEARCH | Frigate optional consented home camera/NVR, never baseline object memory. |
| [L1048](archive/FUTURE_IDEAS_2026_10.md#L1048) | P09-006 | EXTERNAL | Public livestream resolution only when remote imagery explicitly requested; official data otherwise. |
| [L1071](archive/FUTURE_IDEAS_2026_10.md#L1071) | P09-008 | RESEARCH | Benchmark low-latency realtime voice before optional video transport. |
| [L1103](archive/FUTURE_IDEAS_2026_10.md#L1103) | P09-010 | RESEARCH | Computer control native API/accessibility/DOM first, screenshot only on authorized host. |
| [L1107](archive/FUTURE_IDEAS_2026_10.md#L1107) | P09-010 | RESEARCH | Action receipts and semantic state first; optional screen recording for digital tasks. |
| [L1113](archive/FUTURE_IDEAS_2026_10.md#L1113) | P09-011 | EXTERNAL | Camera transport is optional remote sensor; structured events and audio are core. |
| [L1117](archive/FUTURE_IDEAS_2026_10.md#L1117) | P09-011 | CORE | Eventify typed telemetry, web and consented audio; video is one optional source. |
| [L1238](archive/FUTURE_IDEAS_2026_10.md#L1238) | P09-018 | RESEARCH | VisionClaw is an opt-in glasses study; camera-free duplex headphone transport prioritized. |
| [L1289](archive/FUTURE_IDEAS_2026_10.md#L1289) | P09-021 | RESEARCH | iPhone mirroring sees approved digital UI, not a physical-world wearable view. |
| [L1300](archive/FUTURE_IDEAS_2026_10.md#L1300) | P09-022 | RESEARCH | Screenshot-first browser agent secondary to DOM/ARIA/network APIs. |
| [L1320](archive/FUTURE_IDEAS_2026_10.md#L1320) | P09-024 | OUTPUT | Use Worldmonitor sources to brief in audio; globe/dashboard optional. |
| [L1325](archive/FUTURE_IDEAS_2026_10.md#L1325) | P09-024 | RESEARCH | 3-D globe useful as desktop research, not wearable AR requirement. |
| [L1339](archive/FUTURE_IDEAS_2026_10.md#L1339) | P09-025 | GATED | CV tracking only when explicit camera frames exist; cannot derive object tracks from audio. |
| [L1346](archive/FUTURE_IDEAS_2026_10.md#L1346) | P09-026 | RESEARCH | Local ADS-B and prediction are camera-free; PTZ/visual verification optional hardware. |
| [L1420](archive/FUTURE_IDEAS_2026_10.md#L1420) | P01-021 | CORE | Enrolled noncamera room sensors may help; no extra hardware needed for baseline. |
| [L1429](archive/FUTURE_IDEAS_2026_10.md#L1429) | P01-022 | GATED | Predict, observe via legitimate sensor, verify and calibrate; PTZ visual lock optional. |
| [L1433](archive/FUTURE_IDEAS_2026_10.md#L1433) | P01-023 | RESEARCH | Browser API/DOM workflow, screenshot fallback only when needed. |
| [L1441](archive/FUTURE_IDEAS_2026_10.md#L1441) | P01-023 | CORE | Standing queries over digital/RF/provider states; optional cameras as separately marked source. |
| [L1500](archive/FUTURE_IDEAS_2026_10.md#L1500) | P09-030 | RESEARCH | Model benchmark emphasizes headset speech, planning/tools and latency, not images. |
| [L1510](archive/FUTURE_IDEAS_2026_10.md#L1510) | P09-031 | GATED | Audio reasoning is default bake-off; vision tests only with actual authorized images. |
| [L1519](archive/FUTURE_IDEAS_2026_10.md#L1519) | P09-032 | RESEARCH | Measure earbud latency, privacy, barge-in and power; video coexistence optional. |

## Visual-only claims that cannot honestly become audio observations

- **Scene recognition / physical OCR:** The meaning of an unseen sign, unknown object appearance, color, person or object position cannot be determined from AirPods alone. Offer mapped facts or ask the user to describe it; any true scene description requires optional authorized imagery (L330, L756).
- **Precise 3-D anchors:** Visual/geometric relocalization and drift cannot be reconstructed from coarse location or named rooms. Provide honest zone/place confidence; label high-precision spatial mode optional (L719).
- **Object appeared, moved, or vanished:** A change in structured telemetry or a user report does not prove a camera-observed scene change. No claim that an uninstrumented chair moved; no identification or surveillance of unknown people through opportunistic radio traffic (L317, L736, L1339).
- **Physical procedure verification:** Spoken acknowledgment is a user attestation; independent device readback can support stronger verification; visual hand/part motion requires actual visual sensor and explicit consent (L733).
- **PTZ visual lock:** Camera-free ADS-B/RF target trajectory prediction remains useful; optical lock and calibration remain optional external-hardware work (L1346, L1429).

## Release and design gates

1. Core acceptance on an iPhone + ordinary Bluetooth headphones with camera/video/glasses APIs absent or disabled. Optional phone text path must remain available if microphone access is denied.
2. Verify actual iOS foreground/background/audio routing and opt-in capture behavior on real devices, not simulator or SDK assumptions. No covert or default ambient recording of bystanders.
3. Every physical claim carries a source, reported/observed time, freshness/uncertainty and an honest 'last known' versus 'currently verified' distinction.
4. Manual place/object enrollment, per-feature permission/retention controls, quick revoke/delete, bounded resources and no automatic physical action merely because an object was identified.
5. Optional external cameras, user-supplied photos, phone screenshots and glasses remain isolated adapters: separate setup/consent/test coverage, graceful disabled path, and never make a nonvisual capability unavailable.
6. Quantify voice latency, interruption, privacy-safe audio routing, battery/CPU impact, disconnection and device handoff. Visual model accuracy is optional research, not a core release gate.
7. Implementation packet details and this file **override any historical glasses-first assumption** in the untouched original source archive. Do not erase archived ideas or alter their 480-entry trace to pretend they were originally different.

**This audit changes the vision and requirements, not the runtime implementation or device validation status.** Some nonvisual alternatives need genuine sensors/providers, and ambiguous physical states must remain unknown. See [active roadmap](../future.md), [implementation queue](implementation_batches/README.md), and [capabilities ledger](CAPABILITIES.md).
