# Phase 6 — Physical world and spatial reality

Each numbered packet is one actionable request. **Large multi-system concepts are isolated in one-source packets**, with a bounded first end-to-end vertical slice—not a claim to finish the whole research vision. Read the [execution rules](README.md).

## Severe weather / physical safety (from an El Niño discussion with Gemini) — Severe weather / physical safety (from an El Niño discussion with Gemini)

### P06-001

- [ ] **Ingest NWS Impact-Based Warnings (IBW) feeds.** — [source L150](../archive/FUTURE_IDEAS_2026_10.md#L150)
- [ ] **Ingest California Geological Survey (CGS) and USGS slope data.** — [source L156](../archive/FUTURE_IDEAS_2026_10.md#L156)
- [ ] **Local failover alerting.** — [source L162](../archive/FUTURE_IDEAS_2026_10.md#L162)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

## Physical/sensor world providers (more integrations in the Caltrans-adapter shape) — Physical/sensor world providers (more integrations in the Caltrans-adapter shape)

### P06-002

**AirPods-first acceptance (binding):** Public/owned fixed cameras are optional remote evidence, not cameras on the user. Camera-free road/wildfire/coastal official feeds come first; beach crowd density and visual wildfire conditions are unknown without an authorized source.

- [ ] **More state DOT camera feeds** — [source L175](../archive/FUTURE_IDEAS_2026_10.md#L175)
- [ ] **ALERTWildfire public camera network** — [source L177](../archive/FUTURE_IDEAS_2026_10.md#L177)
- [ ] **Harbor/coastal webcams** — [source L180](../archive/FUTURE_IDEAS_2026_10.md#L180)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-003

- [ ] **NOAA/NDBC marine buoy data** — [source L182](../archive/FUTURE_IDEAS_2026_10.md#L182)
- [ ] **PurpleAir / AirNow air-quality sensors** — [source L185](../archive/FUTURE_IDEAS_2026_10.md#L185)
- [ ] **GTFS-realtime public transit feeds** — [source L187](../archive/FUTURE_IDEAS_2026_10.md#L187)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-004

- [ ] **FAA NOTAMs** — [source L190](../archive/FUTURE_IDEAS_2026_10.md#L190)
- [ ] **Smart plugs/switches via HomeKit** — [source L193](../archive/FUTURE_IDEAS_2026_10.md#L193)
- [ ] **A second CrunchLabs-style bench sensor node** — [source L196](../archive/FUTURE_IDEAS_2026_10.md#L196)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

## Reality / intelligence / agency idea dump — Reality / intelligence / agency idea dump

### P06-005

- [x] **Counterfactual Engine / Shadow Reality.** — [source L308](../archive/FUTURE_IDEAS_2026_10.md#L308)

**Delivered P06-005 slice:** read-only, bounded mission ETA conditional branches; 8 new tests passed in 854-test Linux CI; provider/device validation and Windows regression outstanding at latest check. Full multi-domain simulation remains future work.

### P06-006

**AirPods-first acceptance (binding):** Rewind stored, timestamped typed observations; 'DVR' does not mean continuous user POV recording. Video history is a separately opted-in external-media capability.

- [x] **Reality Rewind / physical-world DVR.** — [source L313](../archive/FUTURE_IDEAS_2026_10.md#L313)

**Delivered P06-006 slice:** read-only historical event-time replay of retained mission observations, tested for leakage, coverage, auth and retention boundaries. CI and physical-world validation status is tracked in the capabilities ledger; not a continuous place/camera DVR.

### P06-007

**AirPods-first acceptance (binding):** Compare documented/telemetry/provider state with provenance; no image-free assertions that unknown people or objects visually appeared or vanished.

- [ ] **Reality Diff.** — [source L317](../archive/FUTURE_IDEAS_2026_10.md#L317)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-008

**AirPods-first acceptance (binding):** Check explicitly enrolled and source-qualified reported state; missing optical evidence is unknown, not proof that a condition was satisfied.

- [ ] **World Assertions / desired-state controller.** — [source L321](../archive/FUTURE_IDEAS_2026_10.md#L321)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-009

**AirPods-first acceptance (binding):** Reality Compiler accepts voice/natural-language intentions but must resolve ambiguous 'this' against explicit context. Compile typed sources, expiry, consent and monitoring rules; never assume a live visual stream.

- [ ] **Reality Compiler.** — [source L326](../archive/FUTURE_IDEAS_2026_10.md#L326)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-010

**AirPods-first acceptance (binding):** Start with voice-labeled objects, aliases, user-described locations, enrolled device IDs, docs and NFC/QR identifiers; optional camera recognition is a separate enhancement. Owner statements remain owner statements.

- [ ] **Universal Object Interface.** — [source L330](../archive/FUTURE_IDEAS_2026_10.md#L330)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-011

**AirPods-first acceptance (binding):** A spoken/selected-entity/place bookmark with time, provenance and user context is fully functional; a photo, gaze vector or precise geometric anchor is not required.

- [ ] **Spatial Bookmarks.** — [source L335](../archive/FUTURE_IDEAS_2026_10.md#L335)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-012

**AirPods-first acceptance (binding):** Physical Ctrl-F reports the last explicitly recorded/reported position and its age; never claims the object's current live whereabouts without independent evidence.

- [ ] **Physical Ctrl-F.** — [source L338](../archive/FUTURE_IDEAS_2026_10.md#L338)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-013

**AirPods-first acceptance (binding):** World Search starts with public APIs, events, weather, aircraft/vessel telemetry, devices and consenting phone context. Public cameras are optional remote providers, not user-worn hardware.

- [ ] **World Search.** — [source L342](../archive/FUTURE_IDEAS_2026_10.md#L342)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-014

**AirPods-first acceptance (binding):** Fuse authorized structured sources, RF, optionally consented audio, phone location and provider telemetry. Never generate visual-only facts from audio or radio; disclose coverage and unknowns.

- [ ] **Sensor-Fusion Superresolution.** — [source L347](../archive/FUTURE_IDEAS_2026_10.md#L347)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-015

**AirPods-first acceptance (binding):** Investigations collect typed evidence and compare hypotheses; do not synthesize eyewitness or real-time scene reports without sensing.

- [ ] **Autonomous Investigation.** — [source L351](../archive/FUTURE_IDEAS_2026_10.md#L351)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-016

**AirPods-first acceptance (binding):** Physical macros rely on user-spoken instruction, step declaration, software/device receipts and verification when available. An AirPod cannot observe uninstrumented hand movements or prove completion.

- [ ] **Physical Macros.** — [source L355](../archive/FUTURE_IDEAS_2026_10.md#L355)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-017

**AirPods-first acceptance (binding):** Mission Mode defaults to private spoken briefs, calendar/files/messages and authorized sources, not constant POV recording or HUD presentation.

- [ ] **Mission Mode.** — [source L359](../archive/FUTURE_IDEAS_2026_10.md#L359)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-018

**AirPods-first acceptance (binding):** Closed-loop verification uses independent receipts or user-confirmed state; no absent-camera inference of physical completion; interventions still need scoped authority.

- [ ] **Closed-loop Outcome Mode.** — [source L364](../archive/FUTURE_IDEAS_2026_10.md#L364)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

## Adjacent-field idea mining — 2026-09-26 — Industrial-control lessons

### P06-019

- [ ] **Alarm Rationalization.** — [source L690](../archive/FUTURE_IDEAS_2026_10.md#L690)
- [ ] **Alarm Flood Mode.** — [source L693](../archive/FUTURE_IDEAS_2026_10.md#L693)
- [ ] **First-Out Analysis.** — [source L695](../archive/FUTURE_IDEAS_2026_10.md#L695)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-020

- [ ] **Intervention Timeline.** — [source L697](../archive/FUTURE_IDEAS_2026_10.md#L697)
- [ ] **Condition-Based Maintenance for Jarvis Hardware.** — [source L700](../archive/FUTURE_IDEAS_2026_10.md#L700)
- [ ] **Degradation Trend Detector.** — [source L704](../archive/FUTURE_IDEAS_2026_10.md#L704)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-021

- [ ] **Operating Envelope Model.** — [source L706](../archive/FUTURE_IDEAS_2026_10.md#L706)
- [ ] **Maintenance Verification.** — [source L708](../archive/FUTURE_IDEAS_2026_10.md#L708)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

## Adjacent-field idea mining — 2026-09-26 — Spatial computing / AR

### P06-022

**AirPods-first acceptance (binding):** Persist named places/objects/procedures as semantic entities with evidence and timestamps, even without camera-registered AR anchors.

- [ ] **Persistent World Layer.** — [source L713](../archive/FUTURE_IDEAS_2026_10.md#L713)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-023

**AirPods-first acceptance (binding):** Use semantic place IDs, user declarations, geofence/NFC/enrolled-device events and coarse confidence. Real visual/geometric anchors and drift correction require compatible hardware and explicit capture.

- [ ] **Cross-Device Spatial Anchor Abstraction.** — [source L716](../archive/FUTURE_IDEAS_2026_10.md#L716)
- [ ] **Anchor Confidence + Drift.** — [source L719](../archive/FUTURE_IDEAS_2026_10.md#L719)
- [ ] **Walk-Into Interfaces.** — [source L722](../archive/FUTURE_IDEAS_2026_10.md#L722)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-024

**AirPods-first acceptance (binding):** Speak status for user-named objects and opted-in place reminders. Visual object overlays and virtual notes are optional interfaces requiring actual recognition/AR capability.

- [ ] **Live Physical Labels.** — [source L725](../archive/FUTURE_IDEAS_2026_10.md#L725)
- [ ] **Spatial Inbox.** — [source L728](../archive/FUTURE_IDEAS_2026_10.md#L728)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 

### P06-025

**AirPods-first acceptance (binding):** Share named place/object IDs, source evidence and comments between consenting users; shared first-person video or identical optical anchors are not required.

- [ ] **Shared Spatial Context.** — [source L730](../archive/FUTURE_IDEAS_2026_10.md#L730)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-026

**AirPods-first acceptance (binding):** Use hands-free spoken step guidance with explicit acknowledgement or authenticated independent sensor readback. No visual step-completion claims without optional authorized imagery.

- [ ] **Spatial Procedure Overlay.** — [source L733](../archive/FUTURE_IDEAS_2026_10.md#L733)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. This is only the first vertical slice of a large feature.

### P06-027

**AirPods-first acceptance (binding):** Use typed time-series/event comparisons and user-labeled rooms; visual change-memory only with real authorized before/after imagery. Place-bound data should work as spoken context rather than view-triggered AR.

- [ ] **Visual Change Memory.** — [source L736](../archive/FUTURE_IDEAS_2026_10.md#L736)
- [ ] **Semantic Room Map.** — [source L738](../archive/FUTURE_IDEAS_2026_10.md#L738)
- [ ] **Place-Bound Live Data.** — [source L741](../archive/FUTURE_IDEAS_2026_10.md#L741)

**Done:** a small tested, permission-bounded implementation with honest real-world verification status; retain other subsystems. 
