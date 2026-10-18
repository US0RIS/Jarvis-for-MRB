# HORUS primitive library (`jarvis_mrb/horus`)

This package implements the ideas collected in [`future.md`](../future.md) as deterministic,
stdlib-only building blocks. Callers pass in observations, clocks and executors. The modules
decide, verify and explain. They do no network I/O and actuate nothing, and they need no
third-party dependencies, so the whole suite runs anywhere with
`python -m unittest discover -s tests -p "test_horus_*.py"`.

## Status language

The same evidence rules as the rest of the repository apply:

- **Implemented** means the software core exists in this package and passes its unit tests.
- It is **not** an "observed deployed" claim. These primitives still have to be wired into
  `service.py`, the iOS app, the Windows host and the Pi or sensor nodes. Each integration
  then needs acceptance on the real hardware with real providers.
  `reliability.capability_claim` encodes this rule: a capability with no current passing
  evidence is reported as `designed`, `implemented-unverified` or `verified-stale`, never
  just "working".
- **Harness** ideas ask for something to be benchmarked on the actual machine (TTS
  replacement, Gemma 4, vision bake-off, the humor prototype). The measurement harness and
  decision rule are implemented. The measurements themselves have not been run.
- **Catalog** ideas are external GitHub repositories. Each is recorded in `radar.CATALOG` as
  a research candidate, together with the HORUS primitive that already covers its pattern.
  None of them is a dependency.

## Traceability

`jarvis_mrb/horus/registry.py` maps **every bold idea in future.md** (375 of them, plus a few
prose-level ideas) to the module and attribute that implements or evaluates it.
`tests/test_horus_registry.py` parses `future.md` and fails if:

- a new idea is added to `future.md` without a mapping;
- a mapped title no longer exists in `future.md`;
- any reference does not resolve.

```
jarvis-horus summary            # counts by kind
jarvis-horus lookup "rewind"    # which code implements an idea
jarvis-horus list --kind harness
jarvis-horus check              # every reference resolves
```

## Modules

| Module | Subsystem | What it covers |
|---|---|---|
| `epistemics` | Kant | Epistemic Freshness Gate: claim classes, pre-model freshness routing, contradiction trigger, configurable TTLs, verification receipts, degraded "unverified, not false" answers, evidence-before-explanation sequencing, post-generation linter. Also confidence decay, contradiction detection, source reputation, evidence snapshots, claim lineage and uncertainty labels. |
| `belief` | Mnemosyne | User Belief Model: exposure-weighted belief estimates, `unknown` when unestablished, decision-relevant divergence ("the term changed, you were never exposed, you act in 12 minutes"). |
| `analysis` | Ariadne | ACH matrix with diagnosticity, information-gain planner (lawful/authorized observations only), key-assumption register with expiry, disconfirmation queries, source independence, collection plans, stop rule, calibration, surprise-weighted verification, bounded autonomous investigation, counterfactual simulation and departure planning, sensor fusion, consequence graph. |
| `identity` | Ariadne / Cerberus | Claim-based identity resolution: lineage-aware corroboration, contamination hypotheses (household leakage, same-name merge, stale contact, temporal combination, derivative reproduction), alias hypothesis sets, salience thresholds, separate retrieval/disclosure/action/retention permissions, research receipts. Reasons only over claims the caller already gathered. |
| `temporal` | Carcosa | Bitemporal truth model, `state_at(t)` rewind, `known_at(t)`, diff, temporal query language, bookmarks, debugger, teach-by-correction with dependent invalidation, GC with provenance, Long-Now export/import, alias graph. |
| `standing` | Cassandra | Safe predicate DSL (no `eval`), standing queries that emit only on result-set change, Reality Compiler (English to an inspectable program, or a clarifying question), TTL retirement, follow-the-entity, assertions with evidence sufficiency/redundancy/common-mode detection, level-triggered invariant watchdog, replay/counterfactual testing, condition-relative recurrence, self-resolving tasks, eventification, web observation diffs, state machines, state restoration, automation versioning, closed-loop outcome mode. |
| `attention` | Mercury | Routable information objects, least-intrusive adequate channel, social modes, context-gated capabilities, sterile cockpit, cognitive load, falsifiable proactivity and "why did you tell me this", attention budget and commander, triage, decision windows, tempo, escalation ladder with acknowledge-anywhere, mode annunciation, automation surprise, return-to-manual, loadouts, barge-in, nudge metrics, alarm rationalization, flood/first-out, status indicators. |
| `memory` | Mnemosyne | Capture bus with context and why-saved, entity tagging, connection suggestions, promotion with contradiction review, provenance and revision, resurfacing, activation queue, utility tracking, compression, spaced resurfacing, unified search with freshness disclosure, friction log/miner, capability gaps, idea harvester, spatial bookmarks, Physical Ctrl-F, spatial inbox. |
| `life_admin` | Mercury | Pushed prebriefs, coordinate binding and ETA alerts, health flags, email triage with drafts that wait for approval, action items, obligation graph, receipts/renewals, spending anomalies, contract clauses, vehicle maintenance, package correlation, document freshness, trip timeline, action receipts, evening summary, preparation engine, opportunities/bundling, HUD, gamified progress. |
| `spatial` | — | Cross-device anchors with drift, world layer with consented sharing, live labels, semantic rooms, indoor locate, walk-into interfaces, procedure overlay, visual change, landmarks, object registry, physical macros, predict→point→verify→calibrate loop. |
| `capabilities` | Kant / Cerberus | Capability bus ("what can you do right now"), capability graph, modality-independent invoke, quick actions and interface-by-use, semantic-first control router, model/sensing routers, personal API, composable blocks, micro-app generator, tamper-evident mission recorder, mission mode, state-portability packet, compiled website capability, task-state evaluators. |
| `continuity` | Mercury | Sessions with device handoff and output expansion, transport-independent presence, continuation packets, background job manager (conversation/execution split), presence-as-invocation, environment profiles, world-aware media. |
| `automation` | Sisyphus | Routine learning, "do the rest like that", demonstrate→compile→verify with generalization questions, checkpointed replay with recovery. |
| `reliability` | Sisyphus | SLOs/error budgets, automation registry and cost meter, dependency map (chaos, blast radius, offline manifest, degradation plan), survival mode, failure clustering, change correlation, snapshots, human-fix memory, runbooks, canary/progressive rollout, rollback contracts, split-brain, reconciliation ledger, capability evidence ledger, schema drift and sandboxed repair proposals, condition-based maintenance, drift trends, operating envelopes, maintenance verification, intervention timeline, backup checks. |
| `ethics` | Cerberus | Ethical context engine with layered decision records, necessity/least-intervention, competing interests, uncertain-emergency classes, evidence-weighted urgency, scoped emergency grants (TTL cap, scope firewall, retraction, audit, restoration), anti-pretext/no-concealment hard boundaries, regression and red-team suites. Also speaker gate, HMAC-bound payment guard, breach diffing, stale grants, after-action entries, tracker detection, own-LAN new devices, delegated capabilities. |
| `emergency` | Cassandra | Source-attributed playbooks with review dates, retrieval before generation, competence-aware routing that refuses to improvise, minimal escalation packages, capability index, gated state machine, responder packet, evidence snapshot, self-test, drill mode, NWS IBW tags, slope-adjusted rainfall thresholds, multi-path failover alerting, family beacon. |
| `providers` | — | WSDOT-shaped DOT cameras with host allowlists, wildfire camera framing, webcam-only stream filter, media gateway plan, zone-crossing eventification, NDBC, AirNow/PurpleAir (EPA 2024 PM2.5 breakpoints), GTFS-rt delays, NOTAMs, readsb ADS-B, AIS-catcher, rtl_433 (enrolled devices only), ESPHome, Wi-Fi CSI presence (no pose/vitals), camera-free room fusion, HMAC sensor envelopes, Home Assistant capability bus with grants/readback, LoRa compact alerts. |
| `views` | — | Command center, dynamic COP, coverage map (explicit blind cells), world search, describe-on-demand, interface semantic overlay, proactive Guardian alerts through attention arbitration. |
| `evaluation` | Kant | TTS bake-off scoring with hard gates and the "Kokoro stays until beaten" rule, model promotion rule, eval matrix, trace ledger, vision scoring. |
| `humor` | — | Commentary/Suggestion/Off modes, trigger detection for the canonical bits, private-device verification, distress/important-conversation silence, stutter protection, dark lines limited to commentary, timing/cooldown/repetition gates, feedback learning, transcript evaluation harness. |
| `radar` | — | Research catalog of every surveyed repository, gap-driven scoring (stars ignored), review queue, discovery queries, concept importer, anti-feature constraints, complexity budget, feature crystallization. |

## Integration path

Each primitive is meant to sit underneath an existing surface rather than replace it.
Examples: `views.guardian_alerts` under `proactive_monitor`, `standing` under
`desired_state`/`external_watches`, `temporal` under `reality_graph`, `capabilities.route_model`
alongside `model_router`, `providers` under the World Armor adapters. Wiring is
intentionally left as separate, reviewable changes. Each one should come with device
acceptance evidence.
