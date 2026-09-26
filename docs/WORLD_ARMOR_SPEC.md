# WORLD ARMOR — Planetary Event Fabric and Distributed Agency

**Design specification v0.1 | September 2026 | Status: PROPOSED / NOT IMPLEMENTED**

**Repository:** US0RIS/Jarvis-for-MRB  
**Baseline inspected:** `main` at `f28d47a8f210a5374fc63b69b0b56fad37909093` (after convergence PRs #5 and #6).  
**Purpose:** extend Jarvis from a personal world model and bounded place observations into an operator-controlled, distributed system for observing, correlating, investigating, and eventually acting through authorized infrastructure.

> “A suit of armor around the world” is the inspiration, not an authorization model. This system protects the user's understanding and agency; it does not claim sovereignty over people, infrastructure, devices, or information sources.

**Documentation status ladder:** everything identified as *existing source* is present in the inspected repository, not necessarily deployed on actual devices. Everything in this specification tagged *P* is proposed. A document, mockup, feature flag, synthetic test, or merged PR does not make it Observed deployed. No provider access or data license is presumed by describing an adapter.

---

## 0. Executive decision and scope

### The capability to build

Given a bounded question about the observable world, Jarvis should:

1. Translate the operator's intent into a specific geographic region, time range, observation types, and evidence standard.
2. Identify which **authorized, technically reachable, appropriately licensed** sources can answer it, and represent gaps before making any observations.
3. Collect bounded evidence without inventing observation timestamps, locations, object identities, or provider permissions.
4. Normalize heterogeneous observations into a **Planetary Event Fabric** with explicit space, time, provenance, source dependence, corrections, and uncertainty.
5. Identify changes, coincidences, candidate relationships, and alternative explanations using deterministic rules first.
6. Produce a navigable spatial/temporal investigation that makes the evidence inspectable and the unknowns visible.
7. Allow explicitly enrolled, bounded follow-up watches and delegated computations on the user's own paired machines.
8. Propose next observations or authorized actions only as scoped capabilities; require the existing permissions and independent verification contracts for every consequential side effect.

**Operational distinction:** Jarvis gains a distributed *ability to inquire about reality*. It is not promoted to an omniscient narrator, a market trader, a police-style tracking system, or an agent with universal device control.

### What makes this different from a hired assistant

The end product is an operator-accessible, inspectable **spatiotemporal evidence instrument**. It can run many bounded investigations, preserve the state of each, correlate unrelated data types, distribute lawful computation, and let the operator navigate the results at machine speed. Its value is not how convincingly it summarizes news; it is whether it creates a reproducible capability to see relationships across time, location, sensors, and systems that a single human could not manually integrate at comparable scale.

### Primary implementation proposal

**World Armor** is the program name. **Planetary Event Fabric (PEF)** is its deterministic data and correlation kernel. **Reality Browser** is a *future* immersive interface to the same kernel, explicitly on hold. **Presence**, **Causal Debugger**, **Synthetic Senses**, and **Parallel Existence** remain retained concepts, not newly opened build commitments.

The minimum viable release is a **two-region, multi-source infrastructure investigation**, not “everything everywhere.” Start with currently integrated US weather/earthquake/road-camera **metadata and conservative still-image conditions**, with global earthquake and supported air-quality model coverage clearly bounded. Never make worldwide continuous collection a v1 prerequisite.

---

## 1. Existing foundation and the precise gaps

Inspected from `main`, not inferred from earlier branch descriptions:

| Existing source | What can be reused | What World Armor must add |
|---|---|---|
| `jarvis_mrb/world_model.py` | Persistent private entities/events, source references, beliefs, chronology | A separate high-cardinality geospatial observation/event store; do not flood private-world tables or make them a public firehose |
| `jarvis_mrb/reality_graph.py` | Typed `Entity`, `Relation`, `Evidence`, `DerivedFact`, freshness and deterministic place/mission facts | Long-lived events, bitemporal corrections, source lineage, spatial index, correlation and hypothesis lifecycle |
| `jarvis_mrb/reality_mesh.py` | Explicitly paired machines, public-source registry, one-time place observation, private screen constraints | Authorized workers with narrow job types, capability leases, capacity and cost accounting |
| `jarvis_mrb/physical_awareness.py` | Bounded aggregation of currently available place providers | Periodic collection only for user-enrolled regions; per-adapter sampling contracts and coverage |
| `jarvis_mrb/public_camera_catalog.py` / `public_camera_vision.py` | Caltrans public highway-camera catalog and bounded official still analysis | Stable source IDs, timestamp truth, geometric view footprint when available, no universal camera crawler |
| `jarvis_mrb/public_airspace.py` | Explicit bounded regional airspace query | Licensing gate, provider lineage and uncertainty; no assumption of global historical flight entitlement |
| `jarvis_mrb/reality_lens.py` | Manually saved, limited environmental snapshots, opt-in comparison, 30-day history | A separate per-investigation event archive. Do **not** silently expand Lens's retention or repurpose its coordinate digest as a global location identifier |
| `jarvis_mrb/reality_graph_missions.py` | Default-off bounded observation ledger and current mission answers | Typed infrastructure investigations; do not relabel caller-submitted source strings as verified provider evidence |
| `jarvis_mrb/external_watches.py` | Exact enrolled watches, bounded cadence, camera observation conditions | Shared scheduling primitives where suitable, but new typed event predicates and provider-budget accounting |
| `jarvis_mrb/world_situation.py` / `situation_evidence.py` | Source-qualified prebrief and explicit missing coverage | Optional *summary* of relevant operator-enrolled infrastructure investigations; no reverse dependency on the whole global feed |
| `jarvis_mrb/agency_runtime.py` / `permissions.py` / `AGENCY_ACCEPTANCE.md` | Persistent desired-state executive, bounded authority and real-result acceptance | Investigations as observations/goals, not a second general executive or an implicit grant to external actions |
| `ios/JarvisIOS/RealityMesh.swift` | Private iOS/iPad entry point, place selection and Lens experiences | A new spatial/time investigation UI; keep private phone data and Mission Control's Keychain local absent separately consented transfer |

### Baseline capability claims

**Source in main:** the named modules and limited implementations above exist. **Bench/CI verified:** only claims supported by recorded runs and their exact SHAs. **Observed deployed:** only the project's historical documented device tests on their exact configurations. **Roadmap:** World Armor and every new endpoint, worker, graph table, watch, UI, and source adapter below.

Do not reuse old README language describing PRs #5/#6 as unmerged; a separate documentation cleanup should correct it. Do not treat that cleanup as product development or device acceptance.

### Architectural rule

PEF owns **external infrastructure evidence**, not the user's private personal world. A carefully bounded, user-approved **summary projection** may enter `world_model` or an Agency investigation. The raw event fabric remains in its own database and has its own retention, source scopes, and deletion policy.

---

## 2. User-facing product contract

### Operator workspaces

**A. Open Region** — pick a named place or draw a bounded polygon on a map. Show provider coverage, last successful sample, expected update interval, license status, observed events, and missing evidence. An unsupported region is an honest, partially empty map.

**B. Ask the World** — “What changed around this airport during the last six hours?” Parse region, interval, entities, and requested relationship; return a query plan for inspection, not merely a language-model answer.

**C. Investigation** — a durable, evidence-backed workspace containing the question, scope, collection grants, hypotheses, counterevidence, alternate explanations, provenance trail, replayable query, and expiry.

**D. Time Scrubber** — replay **retained observations**, display their original observed and received times, differentiate subsequent source corrections, and refuse to imply a continuous video or telemetry history when only intermittent samples exist.

**E. Coverage Lens** — a map/layer showing what each source could observe at each point in time. “No detections” can only be interpreted against a known operating source, known observation interval, and understood detection limits.

**F. Distributed Work** — choose *what lawful computation* to run and where among explicitly paired, healthy workers. The operator sees exact capabilities, input classification, resource budget, state, and evidence returned. No general-purpose remote shell.

**G. Watch** — the user enrolls a time-limited event predicate in an exact region. The Watch tab shows polling cadence, credit/storage cost, suppression settings, expiry, and stop/delete controls. An investigation is not automatically an everlasting watch.

### Three demonstration stories

**Port operating conditions:** “Show major changes in public road congestion, relevant weather alerts, and publicly reported vessel traffic around this port today.” Jarvis displays available observations and their gaps. The statement “trucks entered without manifests” is **not available** unless an independently authorized manifest system exists and a specific identity/permission contract permits that comparison; public cameras alone cannot establish it.

**Airport disruption:** “What changed near this airport around the published outage window?” Jarvis overlays separately sourced airspace snapshots, official outage notices, weather and road conditions where licensed and available. It can flag temporal coincidence. It **cannot** infer that a particular aircraft caused the outage.

**Environmental anomaly:** “Did this region change unusually in the previous day?” Jarvis compares source-consistent model observations, official weather alerts, seismic reports and sampled public road conditions, explains baseline/coverage uncertainty, and recommends a next permissible observation.

### Non-goals

Not a surveillance network for named individuals, covert monitoring, persistent license-plate recognition, cross-camera person/vehicle reidentification, phone or IMSI interception, deanonymization, general darknet/closed-platform infiltration, third-party credential collection, or inference of criminal activity from public imagery. Not an autonomous high-frequency trading system, self-replicating cloud, vulnerability scanner of unknown hosts, active RF jammer, or unrestricted command-and-control of third-party infrastructure.

---

## 3. System diagram and trust boundaries

```text
               iPhone / iPad / optional glasses (operator)
                     | one-time or expiring scopes
                     v
            PRIVATE JARVIS API / SESSION GATE
               |          |            |
           Query Plan   Watch Grant   Job Approval
               |          |            |
               +----------+------------+
                          v
                  WORLD ARMOR CORE
          +------------------------------+
          | Source policy and coverage   |
          | Scheduler and budget         |
          | Adapter runner (read-only)   |
          | Normalizer and evidence hash |
          | Event Fabric + spatial index |
          | Correlator / hypotheses      |
          | Investigation ledger         |
          | Replay and explanation       |
          +------------------------------+
             |                 |
             v                 v
      Approved provider      Paired compute nodes
      adapters / data        with leased typed jobs
             |                 |
             +--- verified receipts ---+
                          |
                  Evidence-backed view
                          |
           optional projection to world_model
           optional proposed Agency next step
                          |
                EXISTING ACTION POLICY
                  + independent readback
```

**Trust boundary T1, device:** iPhone local Mission Control, precise GPS, health, contacts and Keychain state do not become World Armor inputs merely because the phone opens the map. Per-feature and per-prebrief transfer contracts remain separate.

**T2, external source:** all incoming bytes are untrusted. The adapter can assert “this came from provider endpoint X under validated token Y at receive time Z,” not “all information in the payload is true.”

**T3, model:** prompts, camera descriptions, scraped text, headlines and provider notes are data. They cannot grant permissions, create provider URLs, define worker code, or promote hypotheses to observations.

**T4, worker:** a paired Mac or optional rented server is a limited computation principal. It is not a general extension of the backend's secrets, private world-model database, files, local network access, or action authority.

**T5, physical/economic action:** no event, correlation, or attractive opportunity grants permission to spend, contact somebody, trade, launch equipment, change network routing, or operate an actuator. Agency/Conductor permissions remain authoritative.

---

## 4. Source registry, policy, and observation coverage

Define a machine-readable **Provider Contract** before any ingestion:

```json
{
  "provider_id": "official_weather_us",
  "adapter_version": "1.0.0",
  "endpoint_allowlist_id": "nws_api",
  "authorization_basis": "public_api_policy_reviewed",
  "license_record_id": "license-nws-reviewed-YYYYMMDD",
  "supported_geometry": ["point", "US_coverage"],
  "observation_kinds": ["official_weather_alert"],
  "minimum_poll_seconds": 60,
  "preferred_poll_seconds": 300,
  "max_request_bytes": 2000000,
  "max_concurrent_requests": 2,
  "raw_retention_allowed": false,
  "derived_retention_days": 30,
  "attribution_required": true,
  "redistribution_allowed": false,
  "operator_enabled": false,
  "checked_at": null,
  "health": "not_checked"
}
```

These are **illustrative configuration values**, not representations of an external provider's current authorization, documented minimum cadence, licensing, or performance.

### Provider readiness vocabulary

`registered` — descriptive adapter/catalog only.  
`policy_pending` — legal/license/source review not completed; do not schedule.  
`configured` — credentials/scope present but live access untested.  
`available` — actual successful bounded fetch with timestamp.  
`degraded` — partial or stale results, provider errors, missing fields.  
`unavailable` — actual request failed or no entitlement.  
`unsupported_region` — known coverage excludes requested location.  
`disabled` — user/operator revoked scope.  
`restricted` — contractual or safety prohibition; cannot override through a prompt.

### Initial and deferred sources

| Source family | Present repository foundation | PEF release treatment |
|---|---|---|
| Official US weather alerts / supported conditions | NWS and modelled air-quality coverage already included in existing place observations | Phase 1, source-specific TTL and alert-update semantics |
| USGS earthquakes | Existing regional provider | Phase 1, authoritative event IDs and revision/supersession handling |
| Caltrans public highway camera catalog / official still | Existing catalog and conservative one-frame analysis | Phase 1 in supported California regions only; metadata first, user-directed still analysis; no unlicensed recording |
| OpenStreetMap facility locations | Existing public map adapter | Phase 1 as **reference geometry**, not evidence a facility is open, occupied, secure or actively operating |
| Aircraft state vectors | Existing bounded regional airspace adapter | Phase 2 only after explicit provider-license and use-case review; existing code does not confer commercial/operational permission |
| Maritime AIS | No demonstrated general live provider | Phase 3. An official **historical** dataset is not a live global AIS feed. License, attribution and geography determine eligibility |
| Public transport and outages | No general worldwide real-time integration | Phase 2/3 source-by-source, prefer official operator feeds, no scraped account bypass |
| Public satellite/remote sensing | No generalized orbital imagery entitlement | Phase 3; actual product acquisition/latency, georegistration, cloud cover and spatial resolution required |
| Public social/narrative signals | No broad social ingestion entitlement | Phase 3 **public aggregate/source-provenance research only**; no closed-room infiltration or secret-identity resolution |
| Own home/local RF, SDR | No installed SDR asserted | Phase 3 opt-in passive, aggregate spectrum observations for authorized locations; no interception of communications content |
| Market data / transactions | Not part of PEF MVP | Separate later proposal; simulated research only unless exact licensed feeds and trading approval architecture exist |

**Source licensing is a build gate, not a disclaimer.** For example, OpenSky's published terms distinguish research/educational use from operational REST API use requiring prior agreement, and its REST endpoints have quota and temporal limits. Do not assume the public API can power an always-on live operational global tracker. NWS has request/caching guidance and rate limits; USGS favors its real-time GeoJSON feeds for routine automated displays. Review up-to-date official terms before enabling each provider.

Provider-declared “public” does not imply permission to archive footage, redistribute it, bypass authentication, use a stream at arbitrary cadence, or combine it into personal tracking. Never discover cameras by broad port scanning or guessing RTSP URLs.

---

## 5. Planetary Event Fabric: data model

### Main concepts

**Source** — entity responsible for publishing a feed; includes policy, endpoint identity, chain of custody and collection coverage.

**Observation** — immutable normalized representation of what one source *reported*, when the phenomenon was observed, when the source published it, and when Jarvis actually received it. Observation ≠ verified world truth.

**Event** — a bounded real-world change candidate supported by one or more observations, with a typed class, spatial footprint, valid-time interval, evidence IDs and provenance.

**Entity** — infrastructure location, sensor, region, transit node, asset owned by user, or non-person movement token only where lawfully sourced and needed; identity confidence remains separate from position confidence.

**Edge** — a relationship with a declared type: `same_provider_revision`, `spatial_overlap`, `temporal_overlap`, `same_reported_object`, `supports`, `contradicts`, `derived_from` or `hypothesized_dependency`. No generic “is caused by.”

**Hypothesis** — candidate explanation with supporting and contradicting evidence, independent-source families, assumptions, alternatives, and a status. It cannot silently become an event.

**Coverage record** — region/time/source/kind coverage and health, including cases in which nothing was detected. There is no valid “zero observations” conclusion without an observation opportunity.

**Investigation** — explicit user question, authorization scope, budgets, records included, query plan, hypotheses and retention.

### Observation envelope (proposed versioned contract)

```json
{
  "schema": "jarvis.pef.observation.v1",
  "observation_id": "obs_opaque_immutable_id",
  "provider_id": "official_weather_us",
  "provider_record_id": "provider-native-event-id",
  "provider_record_revision": "revision-or-null",
  "adapter_version": "1.0.0",
  "source_lineage_key": "root-source:agency-feed-id",
  "source_access_grant_id": "read-grant-opaque",
  "data_class": "public_nonpersonal",
  "kind": "official_weather_alert",
  "observed_start": "2026-09-24T20:00:00Z",
  "observed_end": "2026-09-24T20:05:00Z",
  "published_at": "2026-09-24T20:06:00Z",
  "received_at": "2026-09-24T20:07:00Z",
  "geometry": {
    "type": "Point",
    "coordinates": [-118.15, 34.10]
  },
  "spatial_accuracy_m": null,
  "geolocation_basis": "publisher_geometry",
  "state": "observation",
  "values": {
    "metric_name": "illustrative_metric",
    "number": 1,
    "unit": "count"
  },
  "source_response_digest": "sha256-of-canonical-allowed-response",
  "attribution": "provider-required-attribution",
  "retention_policy_id": "public_derived_30d",
  "quality_flags": [],
  "provenance_evidence_ids": []
}
```

Example values are schematic and not claims about any actual reported weather alert.

**Required**: stable provider ID; adapter/normalizer version; UTC offset-aware times; geometry or explicit `location_unknown`; unit semantics; source lineage; source receipt; scope and policy ID. Provider time missing ⇒ mark `observed_time_unknown` and use `received_at` **only as receipt time**, never as video capture or occurrence time.

### Four clocks, no time travel fabrication

1. **Phenomenon/valid time** — what interval the source says the event applies to.
2. **Publication time** — when the source made the record available, if known.
3. **Ingest time** — when Jarvis obtained it.
4. **Revision/supersession time** — when the source changed an earlier assertion.

Maintain bitemporal “what was known at time T” and “what the source currently says happened at T.” A corrected earthquake magnitude preserves the original record and creates an explicit superseding version. A late-received aircraft state cannot masquerade as a live position.

### Geometry and spatial uncertainty

Use WGS84 GeoJSON-style coordinates and a clear altitude/datum field when relevant. Store observation **footprint** rather than automatically reducing it to a point:

- Alert polygons: actual publisher geometry.
- Camera: publisher camera location **is not its field of view**; view cone is unknown unless verified metadata exists.
- Earthquake: epicenter and location/measurement uncertainty as supplied.
- Aircraft: reported position, source time and coverage limitations.
- RF measurement: own sensor location and measurement uncertainty; do not create an exact coordinate for an unknown transmitter from one receiver.

A “within 2 km” query over two broad polygons needs a declared intersection/radius method and precision notes. A single camera location cannot justify a view of an entire nearby road network.

### Source independence

Two websites reposting one agency alert count as **one underlying evidence family**. Corroboration counts independent primary collection chains, not domain names or number of hyperlinks. Store `source_lineage_key` and `derived_from` edges. A source that cites an unspecified “report” must be treated as dependence unknown, not independent confirmation.

### Event identity and deduplication

Dedup key = source ID + source-native record ID + revision when available. If absent, use a canonical digest with stable normalization and a bounded spatiotemporal bucket, **but never merge two distinct nearby objects merely because their times and coordinates resemble one another**. Keep a dedup audit, reversible clustering, and original observation references.

### Storage and indexes

New private store: `APP_DIR/world_armor.sqlite3` (name proposed, *not yet created*). SQLite WAL and foreign keys initially; no immediate Postgres/Kafka/Neo4j requirement.

Proposed tables: `sources`, `source_policy_snapshots`, `collection_grants`, `coverage_intervals`, `observations`, `observation_revisions`, `events`, `event_observations`, `event_edges`, `hypotheses`, `hypothesis_evidence`, `investigations`, `investigation_events`, `watch_specs`, `watch_checks`, `job_leases`, `audit_entries`, `retention_tombstones`.

Indexes: `(provider_id, provider_record_id, revision)`, `(observed_start, observed_end)`, `(received_at)`, `(investigation_id, event_id)`; SQLite R*Tree of bounding boxes with a separately versioned geometry blob. Time-range partitioning/rollups only when measurements justify it.

**Deliberate separation:** do not add millions of aircraft pings or public headlines to `world_model.sqlite3`. Project select concise, authorized findings into the private world model with source IDs and expiry.

---

## 6. Query planner and search language

The system supports five canonical query operators:

`OPEN(region, interval, layers)` — list available observations and coverage.

`CHANGE(region, t0, t1, metric, source_scope)` — compare source-compatible measurements, including intervening revisions and missing samples.

`RELATE(event_or_region, interval, relation_types)` — surface evidence-backed proximity/sequence/overlap, with alternate explanations.

`REPLAY(investigation, as_known_at, phenomenon_interval)` — reproduce the retained evidence available at that point in the investigation.

`WATCH(region, predicate, interval, budget, expiry)` — explicitly authorize continued bounded checking.

### Natural-language compilation

LLM or deterministic parser emits a **query proposal**, never arbitrary SQL, network URLs, Python or shell:

```json
{
  "schema": "jarvis.pef.query.v1",
  "operation": "CHANGE",
  "geometry_ref": "user-selected-region-opaque-id",
  "window": {
    "start": "2026-09-24T18:00:00Z",
    "end": "2026-09-25T00:00:00Z"
  },
  "event_kinds": [
    "official_weather_alert",
    "public_road_condition"
  ],
  "allowed_source_ids": ["official_weather_us", "caltrans_official"],
  "include_stale": true,
  "max_observations": 500,
  "max_external_requests": 8,
  "persist_investigation": false
}
```

The operator sees the interpreted scope and any expansions. The executor validates an allowlisted DSL and compiles parameterized SQL. No prompt can enlarge geographic reach, observation retention, provider privileges, compute spending, or physical-action authority.

### Result contract

Every answer yields:

- **Observations:** literal, source-timestamped facts.
- **Derived changes:** deterministic before/after with comparable baselines.
- **Hypotheses:** attributed and explicitly uncertain.
- **Counterevidence / alternate explanations.**
- **Coverage and missing sources.**
- **Observation age and last successful checks.**
- **Reproducible query plan and source lineage.**
- **Suggested next permissible checks**, distinct from actions already executed.

Do not claim “all aircraft,” “all ships,” “no anomalies,” “no trucks,” or “nothing happened” when sampling/coverage excludes that conclusion.

---

## 7. Correlation engine and hypothesis lifecycle

### Deterministic pipeline

1. Ingest and validate source envelopes.
2. Match native identities only within provider-defined semantics.
3. Calculate spatial overlap, temporal overlap, state delta and source-family independence.
4. Find candidate event pairs within configurable time and geographic windows.
5. Apply **typed** domain rules. Example: a USGS event and a regional road disruption can be “co-temporal/co-located,” not automatically “earthquake-caused closure.”
6. Construct explanations and alternate hypotheses from *evidence edges*, not free-form LLM assertions.
7. Send a bounded candidate set to a model only for query interpretation or human-readable synthesis; validate every factual statement against stored evidence IDs.
8. Produce a hypothesis report; never auto-actuate based solely on a correlation.

### A proposed hypothesis state machine

`candidate → investigating → {supported, unresolved, contradicted, withdrawn}`

“Supported” means the **specific stated proposition** has sufficient appropriate evidence. It does not mean an entire story is proven. Causal language requires a separate mechanism, source-specific expertise, and stronger evidence than temporal coincidence. A conflicting official source must be visible, not averaged away.

Each hypothesis stores: exact claim, generating rule/version, originating query, supporting observation IDs, contradicting observation IDs, independent-lineage count, assumptions, time of last evaluation, uncertainty drivers, human notes, and expiry.

### No invented probabilities

Use descriptive classes such as `observed`, `derived`, `candidate`, `conflicting`, `unknown`. Do not display “97% likely” because a model produced a plausible narrative. Only use calibrated probabilities when a proper prospective validation dataset, reference population, and ongoing calibration monitoring exist.

### Domain examples

- **Congestion + official road closure:** plausible road-impact hypothesis with route/geography/time matches and separately sourced closure; no guaranteed cause.
- **Earthquake + alert revision:** source revision, not a new earthquake.
- **Two aircraft APIs relaying one ADS-B network:** dependent observations, not independent corroboration.
- **Weather model AQI + nearby consumer AQI sensor:** different measurement kinds/scale. Compare with method and spatial-resolution qualifier; never call them identical sensors.
- **Social spike + infrastructure event:** possible co-occurrence; no presumption of coordinated manipulation, market impact, or social unrest.

---

## 8. Infrastructure OSINT and narrative provenance

The third Gemini pillar is a **domain of the same event fabric**, not a separate “counter-intelligence agent.”

### Scope

Start with publicly accessible, provider-permitted **official notices, public news releases, metadata and aggregate topic trends**. A message in a closed Discord/Telegram room is out of scope without genuine access rights and source-specific consent. Do not treat “OSINT” as permission to infiltrate, scrape behind access controls, or identify a person from multiple profiles.

### Claim graph

Store `claim_text`, `claim_subject` (infrastructure/systemic topic, not individual identity profiling), `first_observed_at`, `publisher`, `citations`, `quoted_primary_source`, `independent_republication_chain`, `retractions`, `contradictions` and `fact_check_status`.

Support:

- Earliest **observed by Jarvis**, not universally first published.
- Source-to-source citation and identical-text propagation.
- Temporal bursts where actual collection coverage is known.
- Primary record contradictions/revisions.
- “We cannot establish coordination from these aggregate observations.”

Avoid categorical “bot,” “astroturf,” or “foreign influence” determinations from timing alone. Source methods and their false-positive risks must be inspectable. No targeting of particular people for persuasion or manipulation.

---

## 9. RF observatory and optional owned sensors

An **operator-owned, receive-only** SDR or other legitimate sensor may become an evidence adapter later.

### Allowed initial observations

Aggregate spectrum energy in named bands permitted for receive-only observation, user-owned network telemetry, device self-health, radio-environment interference trends, known local sensor telemetry and source/device timestamps.

### Explicit limits

No cellular subscriber identification, communications-content interception, credential capture, Wi-Fi handshake harvesting, active probing of third-party networks, deauthentication, jamming, unauthorized drone commands or identifying unknown transmitters from a single ambiguous signal. An unfamiliar Bluetooth beacon is an *unclassified observation*, not proof of a rogue tracker or surveillance device.

“Directional vector” requires verified sensor-array geometry or multiple authorized measurements; a single SDR + laptop cannot produce physically meaningful bearings by assertion. RF analysis code processes bounded, isolated recorded samples, not unrestricted commands on the host.

---

## 10. Distributed sovereign computation

World Armor can coordinate the **compute you own or explicitly rent**, not commandeer worldwide servers.

### v1 and v2 topology

**v1:** Windows Jarvis host remains the coordinator and authority; explicitly paired MacBook/Mac mini may report capability or run named, benign data jobs through a separate signed worker service. iPhone/iPad remains operator console. The existing Mac node screen/app-launch protocol is **not** a license to run arbitrary Python remotely.

**v2:** separately opted-in bare-metal or cloud nodes through a reviewed provider adapter, user-set cost caps and explicit region/retention policies. A cloud resource being provisionable in principle is not “instant global infrastructure” or automatic resilience.

### Typed job contract

```json
{
  "schema": "jarvis.pef.worker_job.v1",
  "job_id": "job-opaque",
  "investigation_id": "inv-opaque",
  "job_type": "normalize_official_geojson",
  "input_artifact_ids": ["artifact-opaque"],
  "output_schema": "jarvis.pef.observation.v1",
  "worker_id": "mac-mini-explicit-pair",
  "resource_budget": {
    "wall_seconds": 60,
    "ram_mb": 1024,
    "cpu_seconds": 40,
    "gpu_seconds": 0,
    "egress_bytes": 0,
    "spend_usd": 0
  },
  "expires_at": "2026-09-24T21:00:00Z",
  "grant_id": "one-use-capability-opaque"
}
```

Named job types v1: `normalize_official_geojson`, `spatial_join`, `diff_source_snapshots`, `rank_hypotheses` (deterministic), `summarize_redacted_events` (model optional), `render_timeline_tiles`. New job types require code review; the model cannot invent executable job names.

### Resource and trust policy

- Coordinator signs one-use, expiry-limited job leases; worker authenticates over a private, verified route, not a publicly exposed unauthenticated port.
- Workers receive **minimum classified inputs**. No Gmail, medical records, Keychain, passwords, signing keys or world-model DB copies by default.
- No arbitrary worker-selected URL, host shell, port scan or nested worker spawning.
- Per-job CPU/RAM/GPU/wall-clock/network limits, input/output byte bounds, queues and cancellation.
- Worker may report `completed_computation` after hash-verified output receipt; that is not proof that an outside-world action occurred.
- Workers produce versioned algorithm IDs, input digests, deterministic result hashes when possible, timing/resource receipts and error descriptions.
- Cloud expense default = **$0**, requiring separate exact provider, project, monthly/daily cap and one-use provisioning approval. The user's private keys do not migrate to cloud worker nodes.
- If all workers are unavailable, degrade to bounded local analysis; no false “planetary compute” banner.

### Failover is distinct from evasion

Approved private endpoint recovery can retry and route within the user's authorized infrastructure. It may not automatically rotate global egress to bypass a provider ban, territorial restriction, subscription limit, legal control, or the user's privacy restrictions. State replication requires encrypted backups, recovery validation and explicit data-region decisions. Zero downtime is a future tested SLO, not a promise.

---

## 11. Economic agency is a separate sealed extension

Gemini's market/protocol arbitrage proposal is **not** part of the initial Planetary Event Fabric authorization surface. PEF can publish bounded, appropriately licensed **market-related observations** only if later approved.

Possible **separate** product stages: paper market-data feeds → deterministic fee/slippage model → prospective out-of-sample evaluation → source/capital policy review → user-confirmed order staging → independently verified broker/exchange outcomes.

No unattended treasury, credit/leverage, flash-loan/MEV bot, prediction-market trading, cross-chain spending or custodial key automation by merely enabling World Armor. A model should never sit on the millisecond-critical execution path, and price discrepancies are not a profit guarantee. Provider ToS, applicable regulation, market integrity and personal risk review are release gates.

---

## 12. Collection scheduler, standing watches and attention

### Three collection modes

1. **Single glance**: explicit foreground fetch; cache permitted only by source contract.
2. **Investigation batch**: bounded region + interval + allowed sources + request budget + end condition.
3. **Standing watch**: user creates exact predicate + scopes + cadence + TTL + maximum observations + notification conditions; user can pause/stop/delete.

No unrestricted “monitor the whole planet” schedule. User-enrolled watches are the only recurring source of monitoring, aside from provider/worker health checks explicitly necessary for installed, enabled sources.

### Proposed watch state machine

`draft → confirmed → active → {paused, exhausted, expired, revoked, failed}`

Creation shows provider authorization, credit budget and whether location/raw media will be retained. Revocation stops **future** collection immediately and triggers requested store deletion according to the source-specific policy.

### Attention and dedup

A finding is not automatically an interruption. Leverage the existing attention policy, but keep infrastructure watches separately addressable. Require: meaningful change vs baseline, source coverage adequate for claim, source observation fresh for its type, sufficient independent evidence for high-consequence claims, user-specified severity, cool-down and notification delivery opt-in.

No automatic trading or physical actuation upon an alert. No “all clear” when a source is down; surface `watch_degraded` separately from `predicate_false_with_sufficient_coverage`.

### Rate and resource accounting

Rate limits, Retry-After, ETag/Last-Modified, provider caching rules, auth expiry and circuit breakers are per source. Priority order under scarcity: user foreground query > already enrolled expiring high-priority watch > ordinary background watch. Never multiplex accounts to evade quotas. Resource budgets cover provider credits, CPU/GPU, network, disk, paid APIs and operator attention.

---

## 13. APIs and access controls (proposed)

Prefix `/world-armor/v1` under the existing authenticated private service; **nothing here is currently a live route**. Use the same no-store/private response posture as other sensitive views. Validate session identity and explicit world-armor opt-in, not only possession of a generic request body.

| Method | Path | Effect / scope |
|---|---|---|
| GET | `/capabilities` | Actual installed source/worker readiness and gaps; no discovery call implied |
| GET | `/sources` | Registry, policy version, coverage, update age, remaining provider budget |
| POST | `/regions/resolve` | User-supplied bounded geometry validation, optional MapKit-selected place token |
| POST | `/queries/plan` | Parse/validate request DSL and forecast expected cost without execution |
| POST | `/queries/execute` | Authorized bounded, read-only collection/query; idempotency key |
| GET | `/queries/{id}` | Results, source provenance, unavailable fields, as-known-at time |
| POST | `/investigations` | Explicitly save question and scope; default ephemeral otherwise |
| GET | `/investigations/{id}` | Read bounded, private investigation |
| POST | `/investigations/{id}/hypotheses` | Create bounded testable proposition; **does not assert truth** |
| POST | `/investigations/{id}/replay` | As-known-at vs phenomenon-time replay |
| POST | `/watches` | Explicit future-check grant with budget, expiry and notification policy |
| POST | `/watches/{id}/stop` | Revoke/checkpoint; no silent resume |
| POST | `/watches/{id}/forget` | User deletion, including relevant derived records when policy permits |
| POST | `/worker-jobs/plan` | Exact typed computation, classified artifacts, budget; no execution |
| POST | `/worker-jobs/submit` | Separate scoped user-approved worker computation grant |
| POST | `/worker-jobs/{id}/cancel` | Cancel leased job and revoke grant |
| GET | `/audit` | User-viewable grants, queries, worker receipts and revocations |
| GET | `/health` | World Armor-specific correctness/degradation, no global availability claim |

All mutation endpoints: optimistic version checks or idempotency keys as appropriate, exact owner scope, bounded JSON, parameterized queries, explicit errors for prohibited/unsupported requests, and logs that do not expose full location histories or secrets. A timed-out remote computation is **unknown**, not automatically safe to replay if the job had a side effect (v1 jobs should not have external side effects).

A future iPhone-only Mission Control snapshot remains subject to its separate data-transfer contract; do not make `/world-armor` a backdoor into phone-local state.

---

## 14. UX specification: spatial command instrument

### Desktop/iPad first, iPhone/glasses companion

The iPad is a natural primary inspection surface; iPhone favors compact alerts and selected-place investigation, while optional glasses provide small, user-invoked summaries. Windows serves and computes. No projector or mandatory glasses dependency.

**Opening view:** geographic canvas plus time scrubber, layer drawer, source-health strip, investigation tray, query field and clear **live / delayed / historical / simulated / unsupported** badges.

**Layer drawer:** weather, official incidents, earthquake reports, public-road conditions, licensed air/maritime coverage, authorized local sensors, narrative-source metadata. Each layer includes its own last observation, resolution, coverage and source attribution.

**Interaction sequence:** select region → inspect source coverage → pose question → inspect execution plan/cost → run → inspect evidence and hypotheses → optionally pin an investigation or enroll watch.

**Evidence card:** exact literal observation; source/chain-of-custody; observed/published/received/revision times; footprint/accuracy; comparable previous sample; alternative explanations; “show source record” where allowed; “report wrong” action; delete/forget scope.

**Coverage visualization:** solid = source genuinely observed region/time; striped = partial; faded = stale; blank = unavailable/unsupported. Coverage itself has provenance. Avoid green “safe” map backgrounds without valid coverage.

**Timeline:** individual point samples and time-window bars with explicit gaps; user toggles `as-known-then` vs `corrected-now`. Never interpolate movement between gaps and present it as actual recorded travel.

**Audio/haptics:** later Synthetic Senses plug-in may encode user-enrolled signal categories only. Do not translate inferred “threat level” into an apparently authoritative sensation.

**Accessible rendering:** keyboard, screen reader, explicit color-free status strings, captions, units, time-zone selector, and distinguishable data source badges.

---

## 15. Data minimization, privacy and threat model

### Classification

- `public_nonpersonal`: official regional weather/earthquake notice.
- `public_potentially_sensitive`: public camera imagery, air/ship movements, public narrative signals that can enable tracking.
- `user_private_location`: user-selected locations, exact home/address, investigation interest, optional phone data.
- `user_private_system`: paired device/node metadata, infrastructure, source credentials.
- `restricted`: raw communications, restricted provider content, medical/financial/account data absent independent authority.

Classification determines worker eligibility, retention, source display and export; “public” does not cancel downstream privacy risk. Named-person tracking, covert license-plate stitching and pervasive cross-camera reidentification are excluded from the default architecture.

### Proposed defaults (subject to source license and explicit user settings)

| Material | Proposed retention |
|---|---|
| Ephemeral unsaved query cache | Up to 24 h, shorter if license requires |
| Derived non-personal observations in a saved investigation | 30 days by default, explicit extension with budget if permitted |
| Raw camera frame | RAM for user-requested analysis; do not persist by default |
| Camera description/road-condition summary | Up to 24 h as investigation evidence, no face/plate identifiers |
| Aggregate coverage/health statistics | 30 days |
| Private precise region/query interests | Investigation lifetime; explicit deletion |
| Hypotheses and evidence links | Co-expire with underlying investigation unless explicitly redacted/exported |
| Audit of auth/worker grants | Bounded 90 days with minimization; user can inspect |
| Reality Lens existing separate store | Its **existing 30-day and 120-snapshot limits remain unchanged** |

Expiry applies to live rows, indexes, caches, replicas, backups under documented windows; an offline node cannot promise immediate destruction. Store `delete_requested_at` and `delete_verified_at` separately; false “forgotten everywhere” claims are prohibited.

### Credible failure/abuse scenarios

1. **Prompt injection** in traffic-camera captions or OSINT text asks Jarvis to run commands: reject; all external text remains data.
2. **Feed poisoning** falsifies an infrastructure event: preserve source lineage, revision and contradictions; require second source family for high-stakes action proposals.
3. **Location disclosure** by cloud worker: classify artifacts and deny distribution absent explicit exact scope.
4. **Credential leak** via worker or provider error body: secret never serialized into PEF record; redact structured logs.
5. **SSRF or camera probing:** adapters only call reviewed provider endpoint templates and validated camera IDs; no arbitrary media URLs from user/model.
6. **Quota exhaustion** by wide-area query: enforce geofence/time/rate/cost ceilings before collecting.
7. **Archive surveillance creep:** no default long-term plate/face/individual trajectories; source-specific limits independent of UI convenience.
8. **Incorrect causal conclusion:** label hypotheses, expose missing coverage, record contradicted evidence, avoid independent actuation.
9. **Remote worker compromise:** revoke lease, rotate worker credential, quarantine outputs, no escalation into coordinator private world.
10. **Unattended spending or physical action:** model and event engine have no such capabilities; existing Action/Agency gates independently authorize and verify.
11. **Malicious user source registration:** operator cannot install arbitrary URLs through a model query; privileged local signed adapter config and allowlists required.
12. **Disaster use overclaim:** never replace emergency services or authoritative warnings with a “safe/unsafe” determination from partial sensors.

### Operator kill switches

Global **World Armor Off** stops watch scheduling and worker job leases, revokes outstanding actionless query grants and hides private views. Separate **Sources Off**, **Remote Compute Off**, **Camera Analysis Off**, **RF Off**, and **Investigation Delete** controls. Existing Jarvis Privacy mode remains authoritative. A stopped UI alone does not prove a remote worker stopped; require lease expiry and confirmation.

---

## 16. Correctness, performance, and cost targets

These are **engineering targets**, not benchmark results.

**Initial scope:** two named geographic test regions; 3–5 actually authorized source families; tens to hundreds of relevant normalized observations per foreground query, not millions of perpetually retained points.

**Query planning:** target under 300 ms local, excluding model interpretation; deterministic schema validation.

**Cached spatial query:** target p95 < 2 s at 50,000 retained observations on target Windows host, after indexes and measured dataset are established.

**Foreground provider query:** show progressive provider states; timeout per adapter; no global success flag when one feed failed.

**Freshness:** driven by source type and declared update cadence (e.g., weather alert, sampled camera still, historical AIS are incomparable). No universal “live if <5 min” rule.

**Worker overhead:** demonstrate that distributed execution wins **measured end-to-end** time or resource isolation over the local baseline before introducing cloud costs.

**Cost:** default $0 recurring paid providers/cloud; show provider credits and expected requests before activation. Do not claim “free planet-scale compute.”

**Information quality:** every surfaced event links to valid source provenance; every hypothesis links to at least one real observation and clear alternative; every absence-based claim demonstrates coverage adequacy.

**Privacy:** zero unauthorized phone state transfer, zero unauthorized external commands, zero provider access outside scopes in synthetic and adversarial tests.

**Operational availability:** distinguish `coordinator_up`, `source_fresh`, `coverage_adequate`, `worker_available`, `watch_delivered`, and `physical_effect_verified`; never collapse them into one readiness score.

---

## 17. Release plan and dependent gates

### Phase 0 — specification and capability audit (THIS DOCUMENT)

Deliver audited provider/source inventory, exact existing API contracts, data-policy matrix, UX wireframes, threat model and acceptance design. **No runtime source/worker changes by merging a spec.**

Exit: each source has documented authorization, licensing, coverage and a realistic MVP role; choose the exact two initial regions.

### Phase 1 — event kernel and replay

Implement separate `world_armor.sqlite3`, versioned schema, read-only normalizers for approved already-integrated providers, bitemporal revisions, spatial index, explicit coverage records and replay of fixed fixture snapshots.

Exit: user can investigate what **actually reported data** changed in a US-supported region and see unavailable providers rather than invented silence. Zero watchers, cloud nodes, or novel actuation.

### Phase 2 — correlation, hypotheses and investigation UI

Typed event/edge engine, source-independence validation, correlation DSL, deterministic change detection, saved investigations, evidence cards, spatial/time UI on iPad/iPhone.

Exit: run two-source, time-window infrastructure queries and reproduce their evidence offline. User sees alternative explanations and timestamps.

### Phase 3 — bounded watches and local distributed computation

Explicit enrolled regional watches, cadence/credit budgets, attention dedup, typed workers on configured private machines, one-use leases, cancellation and independent compute receipts.

Exit: demonstrate a source change while a watch runs, a correct alert and an honest `degraded` when source unavailable. A paired authorized worker processes a data tile but cannot access Gmail, run arbitrary commands, or expand grants.

### Phase 4 — controlled domain expansion

Only after license/policy reviews: airspace as permitted, historical/licensed maritime, official outage/transport notices, selected public aggregate narrative feeds and optionally user-owned passive RF sensing.

Exit: at least one additional domain yields demonstrably useful **cross-domain** correlation without personally identifying tracking or overstated coverage.

### Phase 5 — full-scope World Armor interfaces

Reality Browser (navigable immersive timeline), Presence (authorized physical embodiment), Causal Debugger (stronger mechanism testing), Synthetic Senses and Parallel Existence remain part of the **full World Armor target**. They are later layers because they depend on the evidence, live-fabric and authority infrastructure from Phases 1–4; deferral is a sequencing decision, not a removal of scope.

Each interface still receives its own implementation and acceptance gates. Presence may act only through separately authorized actuators; Reality Browser must preserve source/time/coverage uncertainty; Causal Debugger must distinguish mechanisms from correlations; Synthetic Senses must identify derived/modelled signals; Parallel Existence may distribute analysis but cannot manufacture source authority or physical completion.

### Economic extension

A separately approved, independently risk-reviewed charter, not part of any automatic PEF phase.

---

## 18. Acceptance contract: W0–W16

### Evidence standard

Unit tests, deterministic fixture replay, injected provider failures, Windows runner, iOS simulator and actual paired hardware are **different acceptance types**. Each release record must identify Git SHA, environment, provider entitlement, source fixture/live mode, clock, data retention and human-visible result. Synthetic green ≠ live-world entitlement ≠ physical deployment.

| Gate | Required proof |
|---|---|
| W0 — source honesty | Registry accurately labels configured vs successful live sources; unsupported Melbourne public CCTV remains unsupported until an approved adapter exists |
| W1 — temporal integrity | Provider observation, publication, receive and correction times survive UTC normalization; late arrivals and clock skew never become fabricated “live” |
| W2 — spatial integrity | Alert polygon, camera location/view uncertainty, user polygon and invalid coordinates handled without misleading coverage |
| W3 — dedup/revisions | Duplicate response idempotent, source correction preserved and replay shows original and later understanding |
| W4 — source lineage | Two syndications of one source are not “two independent confirmations” |
| W5 — unknown propagation | 429, bad auth, stale feed, malformed payload and no-camera coverage remain explicit, not zeros/all-clear |
| W6 — query boundedness | SQL parameterized, request/area/time/byte/cost budgets enforced; arbitrary URLs and prompt-generated code impossible |
| W7 — hypothesis discipline | Correlation does not assert causality or wrongdoing; support, contradiction and alternatives inspectable |
| W8 — replay determinism | Same retained observations, as-known-at time, algorithm revision and source policy yield equivalent normalized results |
| W9 — watch authority | No watch without explicit enrollment; expires, stops, pauses, revokes and does not multiply provider identities to evade caps |
| W10 — privacy | No phone Keychain/precise location copy, arbitrary face/plate track, leaked secrets or passive camera archive |
| W11 — worker isolation | One-use lease, known job types, cancellation, host/domain egress restrictions, worker compromise without coordinator escalation |
| W12 — action separation | Query/event/alert alone cannot spend, trade, send, launch robot or create a physical completion receipt |
| W13 — Windows correctness | Full `python3 -m unittest discover -s tests -v` plus isolated `world_acceptance_check` / prepared `world_check` on exact branch SHA; no implicit Windows codepage assumptions or unclosed SQLite handles |
| W14 — iOS correctness | Exact branch simulator build, foreground/background privacy and explicit view reset tested; real iPhone tests tracked separately |
| W15 — live provider truth | Real authorized source demonstrates a bounded event and source receipt, with license record checked; no synthetic provider passed off as live |
| W16 — human capability demo | Operator answers a genuine cross-domain question with provenance, identifies at least one uncertainty, and can replay/stop/delete the investigation without a developer editing the DB |

**REAL release rule:** Phase 1 cannot be called “Observed deployed” until W0–W8 plus relevant W10/W12–W16 pass on the actual installed Windows/iPhone configuration and real permitted providers. W9/W11 are mandatory before Phase 3 “Observed deployed.” A PR merge never satisfies these gates.

### Adversarial test fixtures

Fake 200 response with wrong MIME; 429 with retry header; private IP in a camera media URL; late source correction; NWS alert cancelled; two republishers of one source; mismatched image/source timestamp; aircraft disappearance under unknown coverage; official data and mock webpage contradicting each other; phone GPS supplied without transfer consent; worker tries to request an unapproved API; cost budget zero; fail during remote job acknowledgment; deletion request during worker lease; SQLite temp directory cleanup on Windows; absent optional provider; query to track a named private individual.

### Human-demo non-success cases

- Map shows “no problem” when a source failed.
- UI interpolates aircraft/video frames and represents them as actually recorded.
- An unofficial camera or unknown RTSP feed works because Jarvis guessed a URL.
- “Truck without a manifest” is claimed from an image with no manifest authority.
- A social pattern is labelled as malicious coordination without adequate evidence.
- Guardian/world model learns a new authority merely from PEF output.
- A provider claim or successful command is presented as independently verified real-world outcome.

Any such failure blocks the relevant feature from being called complete.

---

## 19. Engineering work packages

| Work package | Proposed files/modules | Dependency |
|---|---|---|
| PEF source policy | `jarvis_mrb/world_armor/source_registry.py`, source adapter manifests | Operator/source policy review |
| Normalized envelope and validators | `world_armor/schema.py`, `normalize.py` | Source policy |
| Store and migrations | `world_armor/store.py`, `migrations.py` | Envelope |
| Coverage/time/geometry | `world_armor/coverage.py`, `temporal.py`, `spatial.py` | Store |
| Correlator and hypothesis lifecycle | `world_armor/correlate.py`, `hypotheses.py` | Coverage and lineage |
| Query plan validator | `world_armor/query.py` | Correlator |
| Explicit investigations | `world_armor/investigations.py` | Query |
| Bounded source scheduler | `world_armor/collect.py`, `watch.py` | Policy, investigations |
| Typed worker/leases | `world_armor/worker.py` and separate paired-node worker process | Source/task classification and grant model |
| Service endpoints | Existing `jarvis_mrb/service.py`, guarded versioned routes | Corresponding modules |
| iPad/iPhone workbench | New SwiftUI view and typed API client additions | Read-only Phase 1/2 APIs |
| Reproducible fixture suite | `tests/test_world_armor_*.py` | Every module |
| Acceptance and operator runbook | `docs/WORLD_ARMOR_ACCEPTANCE.md` | Actual physical/provider evidence |

**No second general Agency executive.** Delegate intentional goals to existing `agency_runtime`. **No second unbounded observation archive.** Keep Realm/Reality Lens, private world model and PEF stores independently scoped with explicit projections.

---

## 20. Decisions that must remain visible

1. **First two regions:** suggested Southern California (official road camera support plus US conditions) and Melbourne (global air-quality/USGS where available, *explicitly no assumed camera catalog*). Region choice is a test of honest uneven coverage, not a claim of worldwide feeds.
2. **Current physical devices:** Windows coordinator + explicitly paired Macs + iPad/iPhone UI; external cloud off.
3. **First query:** “What changed in the last six hours around this selected California road corridor, and what independently corroborates it?”
4. **First hypothesis:** “Did a reported official road closure coincide with a measured traffic-condition change?” — label co-occurrence, not automatic cause.
5. **First source licensing review:** existing OpenSky use must be checked against its current operating-use requirements before any sustained or operational airspace integration is activated.
6. **First user-authorized watch:** one exact source/region/condition with visible expiry and provider rate budget.
7. **First delegated task:** spatial/temporal join of small, redacted, permitted fixture data on one explicitly paired Mac, with no network egress.
8. **Defer:** arbitrary RTSP cameras, cross-camera identity stitching, global live AIS, direct trading, third-party infrastructure scanning, cloud auto-provisioning, remote actuation and all held WorldOS concepts until separately reviewed.

---

## 21. Source review record (research references, not implementation proof)

Review the actual provider terms again at adapter-enable time; published policies can change.

- OpenSky official general terms: https://opensky-network.org/about/terms-of-use
- OpenSky API specification, temporal and credit limits: https://openskynetwork.github.io/opensky-api/rest.html
- NWS API and alert request guidance: https://www.weather.gov/documentation/services-web-api and https://www.weather.gov/documentation/services-web-alerts
- USGS GeoJSON developer format: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- NOAA/BOEM/USCG MarineCadastre AIS access is a historical data product, not automatic live global AIS: https://coast.noaa.gov/digitalcoast/tools/ais.html
- Project-specific capabilities and limitations: `REALITY_GRAPH.md`, `REALITY_MESH.md`, `HUMAN_EXTENSION.md`, `SITUATION_EVIDENCE.md`, `AGENCY_ACCEPTANCE.md`, `LIFE_FRICTION_CATALOG.md` and the exact `main` source files named in section 1.

**Final design invariant:** World Armor is powerful because it exposes *more of the world that can actually be observed*, preserves reasons for believing or doubting a claim, and expands the operator's lawful computing reach. It must never expand Jarvis's claimed authority faster than its evidence, rights, safeguards and independently verified capabilities.
