# Reality Graph — deterministic world/mission correlation

Reality Graph is **source-implemented**, not a promise of worldwide delivery APIs or physical hardware. It gives Jarvis a bounded model-free representation of an observed place or an individually enrolled mission. It **never executes actions**; Conductor and the existing permissions/confirmation system remain the execution boundary.

## What works in this branch

- `/mesh/graph`, `/mesh/graph/context`, `/mesh/graph/answer`: compile a *fresh* place snapshot from the project's current public/environmental provider adapters. The graph distinguishes a cataloged public camera from an actually retrieved image, preserves provider errors, timestamps and incomplete coverage.
- `/mesh/graph/mission`: compile a caller-supplied structured mission plus observations without persisting them. Derives typed entities, evidence and explicit relations. ETA/deadline math, fresh provider-reported delivery, courier stationarity, route delays and weather/camera-style observation facts use code rather than Qwen. A traffic-delay explanation requires fresh stationary courier and traffic reports from **distinct declared sources referencing the same exact route ID**. Public-camera congestion can add only *public-road condition evidence* when its declared route ID matches; it never identifies a courier or proves why they stopped.
- `/mesh/graph/missions/*`: separate **default-off local SQLite ledger** for 1–72-hour missions. An authenticated enrolled client can create a mission, submit bounded normalized evidence, get model-free current status/answers, stop ingestion, or delete its rows. Each source record is labeled **client-supplied, not provider-authenticated**. A source name in JSON is not a delivery-provider credential or cryptographic attestation.
- Unknown questions receive a small facts/evidence packet, not an instruction to send entire camera data or raw partner JSON to an 8B model. A model may interpret that packet, but it cannot authorize actions through the graph.

## Setup

Configure the private Jarvis API bearer token as required by Reality Mesh. On the Windows backend explicitly opt in:

```powershell
$env:JARVIS_REALITY_GRAPH_MISSIONS_ENABLED='1'
```

No opt-in: persistent mission routes return 503 and do not create a private ledger. Place and non-persistent mission reduction still function behind the configured Mesh bearer. Keep the API bound to the project's documented private network setup; protect the bearer as a sensitive credential.

### Enrolled mission lifecycle

All these routes are authenticated `POST`, with `Cache-Control: private, no-store`. The shapes below are illustrative. Values are UTC ISO 8601 with timezone; the examples are **not live observations**.

```json
POST /mesh/graph/missions/create
{"goal":"Dinner delivered","deadline":"2026-09-24T02:30:00+00:00","lifetime_hours":2}

POST /mesh/graph/missions/append
{
  "mission_id":"rg_<returned-id>",
  "observations":[
    {"id":"order-evt-1","kind":"order","source":"authorized-delivery-adapter",
     "observed_at":"<current-UTC-timestamp>","status":"picked_up"},
    {"id":"courier-evt-1","kind":"courier","source":"authorized-delivery-adapter",
     "observed_at":"<current-UTC-timestamp>","route_id":"route-123",
     "eta_at":"<provider-ETA-timestamp>","moving":false,"stationary_seconds":300},
    {"id":"route-evt-1","kind":"traffic","source":"authorized-road-adapter",
     "observed_at":"<current-UTC-timestamp>","route_id":"route-123",
     "delay_seconds":600,"disruption":"reported incident"}
  ]
}

POST /mesh/graph/missions/snapshot
{"mission_id":"rg_<returned-id>","question":"why is it delayed?"}

POST /mesh/graph/missions/stop
{"mission_id":"rg_<returned-id>"}

POST /mesh/graph/missions/delete
{"mission_id":"rg_<returned-id>"}
```

The backend returns a mission ID, *not* an execution grant. Append is replay-idempotent for **identical observation IDs and contents**; conflicting reuse is rejected. Only fixed typed fields are stored. No raw camera pixels, arbitrary provider JSON, message contents or recipient identity fields. Each mission has up to 400 retained events; each reduction uses the 100 most recent; each append at most 20 records; at most 24 active missions. Stopped missions remain inspectable until deleted or lazily pruned. The ledger prunes expired missions after an additional 72-hour grace period on a subsequent create; there is no claim of a continuously running erase daemon or secure SSD overwrite. Use delete if immediate logical removal is needed. The SQLite file may also be present in local backups/WAL until ordinary database maintenance.

## Current vs proposed / required actual adapter work

The graph can compute a food-delivery traffic explanation **only if** an authorized delivery integration supplies order state/courier movement and an actual route provider supplies comparable route observations. It does not yet have production Uber, DoorDash, courier GPS, identity verification or global public CCTV integration. Nor does a camera-catalog entry prove live footage exists. The existing integrated public place observations are narrower, and Caltrans highway coverage is California-specific.

A provider adapter must supply **real capability/access checks**, verified account/mission mapping, timestamps, durable observation IDs, route join IDs and explicit error/unavailable states. Never derive a courier identity from public camera pixels. "Provider delivered" remains different from "recipient received." A purchase, paid courier dispatch, message or lock control needs its own permitted typed executor and user authority, **not an edge in the graph**.

## How this reduces the 8B workload

```text
Authorized source/adapter -> bounded typed observation -> freshness/provenance
                                            |
                                            v
Mission + place entities -> explicit route/device/order edges -> deterministic reducer
                                            |
                      +---------------------+----------------------+
                      |                                            |
               known question                                novel question
                      |                                            |
              direct factual answer                     bounded semantic packet
             (zero Qwen calls)                           -> optional model reasoning
                      |
              no action authority
```

Known answer templates are intentionally conservative: no source freshness is inferred from ingestion time, no confirmation is inferred from a missing event, no camera is presumed to observe an identified courier, and no stop/delay cause is presented as certain. The next adapter and Field Ops milestones can reuse the same graph while keeping action authority separate.
