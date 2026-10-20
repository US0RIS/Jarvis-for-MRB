# Life Fabric — Five Years of Avoidable Friction

This feature is a real, testable **manual life-state workbench** inspired by
the ages-25-to-30 thought experiment, not a declaration that Jarvis has already
automated all of adult life. The full 17-domain inventory is in
[LIFE_FRICTION_CATALOG.md](LIFE_FRICTION_CATALOG.md). The physical remote-
embodiment project **Presence** remains a separate hardware milestone.

## What was implemented

The main Jarvis iPhone toolbar's **Life Fabric** control opens the Life screen.
With an explicitly configured private API token and a matching backend build,
users may:

- Record tasks with domains, descriptions, next steps and timezone-aware
  deadlines, and manually record owned assets and their asserted location.
- Read a 7-day readiness view: overdue, due within 24 hours, due within 7
  days, missing prerequisite tasks, unknown outcomes. No records means
  **setup required**, never "all clear".
- Record exact user-confirmed completion. Backend integrations may separately
  attach provider receipts, document evidence and sensor readbacks. These
  are distinct labels. A provider-reported outcome does not unlock a dependent
  task without user confirmation or a suitable sensor readback.
- Retire a task without claiming completion, or **permanently delete** its
  Life Fabric record and attached Life Fabric receipts with an explicit
  confirmation. Dependent tasks remain unresolved if their prerequisite
  disappears; deletion never manufactures a successful outcome.
- Add one of six opt-in eight-step transitions: moving, travel, new job,
  purchase, vehicle service and clinician-directed health follow-up. These
  are checklist suggestions, not completed actions or professional advice.
- Save an explicit continuation packet: what the user decided, the exact next
  step and selected linked tasks. Another iPhone/iPad running the matching
  client against the same private backend can resume the packet. This does
  **not** restore a remote desktop's live applications.
- Explicitly log one inconvenience. Only three distinct UTC days within
  30 days create a **review candidate**. A candidate cannot create its own
  automation, access sensors or modify external services. Clear all friction
  incidents through a destructive confirmation.
- Run a bounded **what-if** with user-supplied minutes, days and assumed free
  minutes/day. The output is arithmetic, not a claim that Calendar was
  consulted or that a future event will happen.

All writes are initiated by explicit API requests or user taps. No background
behavior recording, passive person recognition, inferred purchases,
cross-account crawling, external payment, third-party messaging, device
control or medical treatment changes were added.

## Practical setup and test

1. Install the Windows backend and iOS app from the same branch:
   `jarvis/life-friction-fabric`. Keep the existing matching Reality Lens
   and private bearer-token configuration. Do not assume the GitHub branch is
   already installed on your devices.
2. Open Jarvis's **Life Fabric** toolbar control, refresh the page and create
   a task with a deadline tomorrow. A refresh must show it as `next_24h`.
3. Record an item as an asset. Its quantity/location must be described as
   **user-reported**, not live inventory.
4. Use the Moving template. You should get eight *unverified* checklist tasks
   with one parent transition. An ambiguous network error must not trigger
   a blind second creation; the phone retains the request id on failure.
5. Confirm a task complete. Its state must read `user_confirmed`, never
   `sensor_observed` or `provider_reported`. Open the remaining ledger and
   check due/readiness changes.
6. Save a handoff, navigate away and return. Resume must reconstruct the saved
   summary, next step and active linked tasks without operating a computer.
7. Log the same inconvenience on three actual distinct days: only then
   should the Observatory show a repeated-friction candidate. Use
   **Clear my friction log** and independently verify that it is gone.
8. Delete one record and verify that only that record and its associated
   Life Fabric receipts were deleted. Other linked tasks should become
   blocked, not automatically complete.

These gates require real deployed device/provider acceptance when a hardware
or provider outcome is asserted. Backend tests and simulator builds verify
source logic and compilation but cannot establish physical-world outcomes.

## Model-free local protocol

Authenticated `private, no-store` routes:

| Method / path | Contract |
|---|---|
| GET `/life/capabilities` | Implemented versus explicitly not implemented |
| POST `/life/records/create` | Explicit task/asset, optional deduplication request id |
| GET `/life/records` | Bounded active entries and classified latest receipts |
| POST `/life/records/receipt` | Expected-version guarded user/provider/sensor/document event |
| POST `/life/records/retire` | Exact record retirement, not completion |
| POST `/life/records/forget` | Destructive exact record + receipt deletion |
| GET `/life/readiness` | On-demand, timezone-aware due windows and dependencies |
| POST `/life/transition` | One idempotent user-enrolled eight-step checklist |
| POST `/life/handoff` | Explicitly saved continuity packet |
| POST `/life/handoff/resume` | Read-only reconstruction of the selected packet |
| POST `/life/friction/log` | One explicitly reported incident |
| GET `/life/friction/candidates` | Explicit recurrence on 3 UTC days in 30 |
| POST `/life/friction/clear` | Destructive deletion of Observatory events |
| POST `/life/what-if/minutes` | User-assumption arithmetic, no prediction |

All use the existing private Mesh bearer-token check. A tokenless public
server cannot use the Life endpoints. Backend code does not initiate any
actions outside the SQLite ledger. Mutations that can be confused by a
network timeout use short request-id replay guards for record creation,
handoff and transition creation, or a record-version guard for receipts,
retirements and deletions. Friction logging is intentionally not retried
automatically: a second tap logs another explicit incident.

## Data boundaries

Life Fabric uses a separate `life_fabric.sqlite3` beside Jarvis's existing
world model database on the Windows Jarvis host. It has a maximum of 500
active records and 3,000 recent friction incidents; user-supplied text fields
are bounded, and the friction candidate window is 30 days. Expired friction
events are purged on Observatory access; the backend cannot purge a disk
while offline. SQLite secure-delete is enabled for record removal. This is
**not database encryption**; use appropriate OS-level disk encryption and
backup access controls. Erasing Life Fabric does not erase copies in backups,
other Jarvis stores, external apps or a collaborator's separately held data.
Do not put passwords or full medical records in free-text task fields.

The store is one trusted-user private installation, not an access-isolated
multi-user service. For a shared server, implement actual user tenancy,
per-record scope and at-rest encryption before storing another person's
private content.

## What remains to be built before "all" can mean fully automated

The inventory describes a complete outcome taxonomy, but direct bank/merchant/
medical/vehicle/utility/provider adapters, asset sensors, remote embodiment,
universal context restoration, automatic discovery and genuine prognostic
models need real supported accounts and hardware. Each must introduce
source-specific grants, independent evidence and per-action authorization.
Until those are implemented and exercised, Jarvis may **track** an obligation
but cannot assert that it paid a bill, refilled medication, repaired a car,
completed a return or controlled a robot.
