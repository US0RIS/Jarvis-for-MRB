# Capability inventory — C01 truth audit

> **C01 state: READY FOR REAL TEST (not passed).** User decision on 2026-09-27: every capability previously presented as
> implemented or current stays in scope (P). `criteria.md` §7A adds grouped REAL scenarios C01-S01 … C01-S16 for them.
> C01 passes only when every one of those scenarios, plus the A-table gates, has REAL PASS on the frozen candidate.
> Only pure internal mechanisms are labelled "not a user capability".

Sources enumerated:

- `README.md`;
- the iPhone Feature Guide (`ios/JarvisIOS/FeatureGuide.swift`, 116 entries);
- the iPhone tabs (Mesh, World Armor, Physical, Life Fabric, Mission Control, Settings);
- the conversational tool registry (`jarvis_mrb/permissions.py`);
- production HTTP routes (`jarvis_mrb/service.py`).

## A. Mapped to a REAL gate

| Capability (source) | Gate(s) |
|---|---|
| Candidate identity, `/health` `code_sha`, `/release/identity`, iOS `JarvisBuildSHA` | C00 |
| Ordinary UI/voice path; deterministic dispatch; "What can you do right now?" (`capabilities.now`); backend tool-necessity gate | C02, C12 |
| World model: entities, beliefs, linker, Chronos history; user facts/corrections (`world.remember_fact` / `world.correct_fact` / `world.describe_entity`); episodic memory; unified search; context discipline | C03, C10 |
| Local goal manager → world-model goal; "My goal is …" intake; Agency persistence across restart | C04 |
| Agency executive loop; DAG workflows (`workflow.run`) | C05 |
| Permission engine; protected Gmail send; email allowlist; Agency approve/deny; preference ≠ authority | C06, C20 |
| Independent verification (Calendar/Gmail/app/HomeKit readback); "did that work?" | C07 |
| Replanning; dormant `wait_until` goals and wake watches | C08 |
| Proactive monitor; Agency attention; World Armor attention inbox / standing watches; Guardian deadline warnings; closed-app push of proactive interventions | C09, C18 |
| Meeting prebrief (Situation Evidence); calendar conflict analysis | C10 |
| Parallel deliberation; counterfactual branches; capability gaps; self-generated API adapters; custom-tool repair; Docker sandbox | C11, C20 |
| Automatic 8B↔27B routing; local Qwen; Groq cloud cognition (iPhone Keychain key); fallback | C12 |
| Conductor workstation missions; exact spoken app actions; Windows exact app control | C13 |
| Reality Mesh nodes, private view-only screen, app buttons; LAN→Tailscale failover | C14, C21 |
| Reality Graph missions/place graph (model-free answers) | C15 |
| Public cameras: Caltrans, Windy directory, operator-enrolled HTTPS/JPEG/PNG/WebP/MJPEG/HLS, page-media discovery, distributed camera workers, Reality Browser evidence view | C16 |
| Providers: NWS alerts, Open-Meteo air/UV, USGS earthquakes, OpenSky, AISStream (only if configured), OSM facilities, SEC/EPA/OFAC matter diligence, external watches, World Armor Phase 1 investigations, movement graph | C17 (inventory-driven, see note) |
| APNs outbox; watchdog; live supervisor; runtime guard | C18 |
| Presence: exact HomeKit light grant/dispatch/readback; `presence.set_light` | C19 |
| Secrets, revocation, fail-closed boundaries (all of the above) | C20 |
| Long-run persistence of everything above | C21 |
| Composition of all families into one task | C22 |

C17 note: the gate covers every provider that the frozen candidate advertises as user-available. The C17 evaluator currently derives
real-request checks automatically for NWS, Open-Meteo, USGS and OpenSky. For the other providers (AISStream, OSM, SEC, EPA, OFAC,
Caltrans, Windy), the C17 record must carry the real request and provider timestamp as artifacts, or else the provider must be
labelled unavailable/unconfigured in the product by user choice.

## B. Shipped capabilities without a C02–C22 gate → covered by §7A scenarios (decision: P)

| Scenario | Capabilities |
|---|---|
| C01-S01 Voice conversation | wake, followup, barge, dictation, vocab, quiet-speech, local-alias, audio-hud, response-done-tone, sir-dedupe, empty-stream-recovery, kokoro, whisper, context-discipline, episodic memory |
| C01-S02 Ray-Ban Meta glasses | Gen 1 audio route, welcome-back, passive-vision, live-scene recall, spatial last-seen, camera-master, local-visual-cache, fast-perception, visual-change |
| C01-S03 iPhone-only intelligence (offline → online) | offline-brain, local-first-router, deterministic-utilities, stable-local-brain, native Calendar/Reminders/Contacts, local-timers, context-capsules, unified-local-memory, local-route-telemetry, quality-shield, semantic-audit, capability-receipts, packs-tab, offline-queue, no-write-replay, diagnostics, auto-recovery |
| C01-S04 On-device perception/audio | audio-memory, sound-analysis, translation, ocr, qr |
| C01-S05 People & inventory | known-people, person-brief, encounter-capture, inventory, inventory-lastseen, inventory-alert |
| C01-S06 Privacy & interruption | privacy-mode, privacy-zone, incident, modes, smart-interrupt, context-reminders, event-timeline, camera-privacy-pack |
| C01-S07 Local executive | goals, waiting, routine, intent-radar, knowledge-graph, clipboard, local-receipts |
| C01-S08 iOS integration | shortcuts (App Intents / Action Button), share-text |
| C01-S09 Windows PC & automation | pc-app, browser, desktop-context, jobs, briefing, background, prewarm, resources, audio-damping, journal, expenses, meeting, meeting-offline, unified-search |
| C01-S10 Connectivity | LAN → Tailscale failover |
| C01-S11 Mission Control & navigation | appointment mission, Maps handoff, GPS arrival, turn-by-turn navigation |
| C01-S12 Life Fabric | deadlines, handoffs, assets, friction log, readiness, what-if |
| C01-S13 Reality Lens & World Armor analysis | Reality Lens; Synthetic Senses; Causal Debugger; Parallel Existence; two-region comparison |
| C01-S14 Notecard & Health | Personal Notecard; optional Apple Health context |
| C01-S15 Ambient physical actuation | arrival- and doorbell-triggered enrolled HomeKit light (second actuation path) |
| C01-S16 Guardian surfaces | Counterfactual Guardian, Goal Guardian |

**Labelled "internal mechanism, not a user capability" (decision: L):** capability-packs registry, capability-router,
readonly-composer, lazy-pack-activation, routing-regressions harness, compact-context-packets. These are implementation
mechanisms. They were never presented as things the user does, and they are exercised implicitly by C01-S03, C02 and C12.

C17 provider list, all P: NWS, Open-Meteo air/UV, USGS, OpenSky, AISStream (needs its server-side key), OSM facilities,
SEC / EPA / OFAC matter diligence, Caltrans, Windy (needs the key entered on the iPhone). Each needs a real request on
the frozen candidate.

## C. No gate needed

- **Declared limitations** (Feature Guide "Known Limits"): no-notifications, no-speaker-id, no-stress, no-diarization, no-3d,
  no-ide, share-limit, watch-limit. These deny capability; they claim none.
- **Developer and evaluation harnesses** (not user capabilities): JARVIS-20 worlds/eval (`jarvis-20`), COVER benchmark
  (`jarvis-cover-score`), search-integrity benchmark, fixed-endpoint acceptance, cognition benchmark, `/acceptance/*` preview
  routes, `jarvis-agency-*`, `jarvis-world-*` and `jarvis-release-*` CLIs.
- **Honestly labelled bench/roadmap items**: the CrunchLabs servo (bench only; documented as not integrated with Jarvis), MemoMind
  (documented as "Simulator only"), and all of `future.md`.
