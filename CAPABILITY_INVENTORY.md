# Capability inventory — C01 truth audit (draft)

> **C01 state: IMPLEMENTING. It cannot pass yet.** Part B lists shipped or claimed capabilities that have no REAL gate
> in `criteria.md`. Under `criteria.md` §0 and C01, each one must either
> (1) get a concrete REAL test added to `criteria.md` and pass it, or
> (2) be relabelled as not a finished capability by an **explicit user choice**. Engineering may not relabel it
> merely to pass. The user makes that decision, one group at a time (see "Decision needed").

Sources enumerated:

- `README.md`;
- the iPhone Feature Guide (`ios/JarvisIOS/FeatureGuide.swift`, 116 entries);
- the iPhone tabs (Mesh, World Armor, Physical, Life Fabric, Mission Control, Settings);
- the conversational tool registry (`jarvis_mrb/permissions.py`, 95 tools);
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

## B. Shipped or claimed with no REAL gate — **decision needed**

Recommended disposition: **P** = promote, i.e. add a REAL smoke test to `criteria.md` (a C01 appendix) and run it on the candidate.
**L** = the user explicitly chooses to label it "not release-accepted" in the README and Feature Guide.

| Group | Capabilities (Feature Guide ids / docs) | Recommendation |
|---|---|---|
| Voice UX | wake, followup, barge, dictation, vocab, quiet-speech, local-alias, audio-hud, response-done-tone, sir-dedupe, empty-stream-recovery | P (one scripted voice session covers them) |
| Speech output | kokoro, whisper (adaptive/forced) | P |
| Ray-Ban Meta glasses | Gen 1 audio route, welcome-back greeting, passive-vision transport, live-scene recall, spatial last-seen, camera-master switch | P if the glasses are in use, otherwise L |
| iPhone local intelligence | offline-brain, local-first-router, deterministic-utilities, stable-local-brain, native Calendar/Reminders/Contacts, local-timers, context-capsules, unified-local-memory, compact-context-packet, local-route-telemetry | P (single local-routing session) |
| Capability-pack architecture (internal mechanisms) | capability-packs, capability-router, camera-privacy-pack, readonly-composer, quality-shield, no-write-replay, semantic-audit, capability-receipts, routing-regressions, lazy-pack-activation, packs-tab | L (internal mechanisms; they are exercised implicitly by C02/C12) |
| Local audio/vision | audio-memory, sound-analysis, translation, local-visual-cache, ocr, qr, fast-perception, visual-change | L unless used |
| People & inventory | known-people, person-brief, encounter-capture, inventory, inventory-lastseen, inventory-alert | L unless used (face recognition carries privacy weight) |
| Local memory & privacy | event-timeline, context-reminders, privacy-mode, privacy-zone, incident, modes, smart-interrupt | P for privacy-mode/privacy-zone (fail-closed, fits C20); L for the rest unless used |
| Local executive | waiting, routine, intent-radar, knowledge-graph, clipboard, local-receipts | L unless used |
| iOS integration | shortcuts (App Intents/Action Button), share-text | P (cheap) |
| Automation/records | jobs (scheduled/recurring reminders), briefing, background worker, prewarm, expenses, journal, resources, audio-damping, health, meeting / meeting-offline | P for jobs, briefing, meeting; L for the rest unless used |
| PC/browser | pc-app (local Windows), browser (Opera CDP), desktop-context | P (pc-app is also usable in C07 Test A) |
| Connectivity diagnostics | diagnostics, auto-recovery, offline-queue | P for offline-queue (no automatic replay of writes, fits C20); L for the rest |
| Mission Control | appointment journey mission, Maps handoff, GPS arrival | P (real appointment) or L |
| Life Fabric | deadlines, handoffs, assets, friction log, readiness, what-if | L unless used |
| Reality Lens | sense/compare/remember at a place | P (cheap once providers work) |
| Personal Notecard | home address, relationships | P (cheap) |
| Turn-by-turn navigation | Maps routing commands | L unless used |
| Camera-free ambient presence | arrival/doorbell-triggered preauthorized HomeKit light | **P required if kept**: this is a second physical actuation path, so C19 requires its own physical scenario |
| World Armor v8 analysis surfaces | Synthetic Senses, Causal Debugger, Parallel Existence, two-region comparison | P (read-only; one real run each) or L |
| Counterfactual Guardian / Goal Guardian iOS surfaces | evidence-backed warning loops | map to C09 if their alerts use the proactive path; otherwise P |

## C. No gate needed

- **Declared limitations** (Feature Guide "Known Limits"): no-notifications, no-speaker-id, no-stress, no-diarization, no-3d,
  no-ide, share-limit, watch-limit. These deny capability; they claim none.
- **Developer and evaluation harnesses** (not user capabilities): JARVIS-20 worlds/eval (`jarvis-20`), COVER benchmark
  (`jarvis-cover-score`), search-integrity benchmark, fixed-endpoint acceptance, cognition benchmark, `/acceptance/*` preview
  routes, `jarvis-agency-*`, `jarvis-world-*` and `jarvis-release-*` CLIs.
- **Honestly labelled bench/roadmap items**: the CrunchLabs servo (bench only; documented as not integrated with Jarvis), MemoMind
  (documented as "Simulator only"), and all of `future.md`.

## Decision needed from the user

For each Part B group, reply **P** or **L**. **P** means I add a concrete REAL test to `criteria.md` (C01 appendix) and it becomes
part of the acceptance campaign. **L** means you explicitly choose to label it "not release-accepted" in the README and the
in-app Feature Guide. Both choices keep the code in the product.
