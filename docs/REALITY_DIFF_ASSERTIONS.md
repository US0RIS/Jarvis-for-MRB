# Reality Diff (P06-007) and World Assertions (P06-008)

**Status:** bounded, opt-in **source implementation**; not continuous physical observation, independently verified telemetry, autonomous actuator control or a shipped device feature. Read original requirements in [the archived backlog](archive/FUTURE_IDEAS_2026_10.md#reality--intelligence--agency-idea-dump), packets [P06-007/008](implementation_batches/06_PHYSICAL_WORLD.md) and the [capability ledger](CAPABILITIES.md).

## Common authority and evidence boundaries

These slices reuse an enrolled *mission ID* from the private Reality Graph mission ledger. Only typed normalized observations submitted by authenticated enrolled clients are stored. Their source labels **are not proof of provider authenticity**; no object identification, live camera footage, ground-truth observation, provider integration or default monitoring service is implied. Both expose private `/mesh/graph/missions/...` endpoints under the existing configured bearer token; lack of that token returns 503, invalid token 401. Responses carry `Cache-Control: private, no-store`. `JARVIS_REALITY_GRAPH_MISSIONS_ENABLED=1` is required, off by default.

## P06-007 — Reality Diff (read-only)

`POST /mesh/graph/missions/diff`

```json
{"mission_id":"rg_EXACT_ID","before":"2026-10-19T19:30:00+00:00","after":"2026-10-19T19:35:00+00:00"}
```

Reconstructs two retained event-time views, with **before strictly earlier than after**, both inside the exact mission lifetime and no more than 72 hours apart. Compares a finite allowlist of evidenced semantic facts (order reported status/delivery; ETA relative to mission deadline; courier stationary; route delay/disruption; public camera's reported congestion). Each candidate requires fresh, linked source observation IDs. Results are `reported_change`, `newly_supported`, or `no_recent_evidence`, not claims of objects appearing or disappearing. Stable values yield no change; missing/stale evidence is explicitly unknown. Includes before/after coverage, truncated-history flags and source attestation. Uses no model, notifications, network, writes or actions. There is no continuous diff worker or push event feed. Late ingestion can change historical event-time results because prior storage does not retain ingestion time.

## P06-008 — World Assertions (durable but non-actuating)

Requires **both** `JARVIS_REALITY_GRAPH_MISSIONS_ENABLED=1` and the separately enabled `JARVIS_WORLD_ASSERTIONS_ENABLED=1` (off by default). Authenticated owner explicitly enrolls a maximum of **12** predicates per mission.

`POST /mesh/graph/missions/assertions/enroll`

```json
{"mission_id":"rg_EXACT_ID","definition":{"kind":"order_status_equals","expected":"delivered"}}
```

Other accepted exact definitions:

```json
{"kind":"route_delay_at_most","route_id":"specific-route","max_seconds":300}
{"kind":"reported_eta_before_deadline"}
```

The first checks the freshest typed **reported** order status, the second a particular exact route's delay, and the third a courier's reported ETA against the enrolled mission deadline. An assertion can be `met`, `violated`, or `unknown`. Stale, missing, incomplete or unauthenticated-provider evidence **never implies met**; these are assessments of reported evidence, not independent physical truth. A violation provides a text-only *suggested review*, never an automatic action.

- `POST /mesh/graph/missions/assertions/check`: `{"mission_id":"rg_EXACT_ID"}` — re-evaluate all assertions at the current time; returns evidence and limitations.
- `POST /mesh/graph/missions/assertions/history`: `{"mission_id":"rg_EXACT_ID","assertion_id":"wa_EXACT_ID"}` — up to 32 recent state-transition receipts with evidence.
- `POST /mesh/graph/missions/assertions/revoke`: same body — delete the exact enrolled predicate and its local transition receipts.
- Observations appended through the existing authenticated mission append endpoint trigger assertion evaluation **inside the same SQLite transaction**. If an observation insert fails, no monitor update commits. Reads/checks also re-evaluate for staleness.

Mission stop/expiry prevents continuing evaluation. Mission deletion removes all assertions and transition receipts with it. Neither this feature nor the API can send messages, authorize tools, bypass user/device permissions, modify physical-world state, run a background scheduler, or auto-repair violations. This is an intentionally narrow **observed-state + suggested-review** controller foundation, not the archive's fully autonomous general desired-state system.

## Release and testing boundary

Automated tests cover state changes, evidence linkage, event-time leakage, stale/absent evidence, cross-mission isolation, opt-in, API auth, no-store, validation, revocation, stored transition receipts and deletion. **Real provider, platform/hardware, deployment and end-to-end continuous monitoring remain unverified**. Extend only through typed domains, explicit permissions and independently verified action receipts.
