# World Armor — Phase 3A: explicit bounded local watches

**Status:** stacked implementation on `jarvis/world-armor-standing-watches`,
on top of the retained regional event kernel and evidence workbench. Source
code and CI do not mean the feature has been installed or run on the user's
Windows host or iPad/iPhone. No provider contract/license or live data
acceptance is inferred.

## Actual operational boundary

This adds an **explicitly opt-in local host runner** for already-enrolled
World Armor regions. It is NOT an automatically started FastAPI background
scheduler, a remote worker fleet or notification service. The only recurring
collection operation is the existing `observe_once` and its two fixed,
bounded public/modelled adapter calls: Open-Meteo AQI + NWS point alerts
through `physical_conditions`, and a USGS regional earthquake request.
A watch does not expand the saved region, request arbitrary URLs, check a
camera, identify a person, request aircraft/ship telemetry, spend money,
send messages or initiate physical actions.

Enable BOTH environment switches **on the actual Jarvis host / watch runner**:

```powershell
$env:JARVIS_WORLD_ARMOR_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_WATCHES_ENABLED = "1"
```

The private FastAPI backend also needs its already configured bearer token.
Enrolling a watch NEVER starts a process or triggers collection. For actual
periodic sampling, intentionally start a separate terminal on the same
authorized Windows host, with the same environment and DB configuration:

```powershell
python -m jarvis_mrb.world_armor_watches --loop
```

`--once` runs at most one due grant and exits. `--loop` checks for one
due grant at a time and sleeps when no grant is due. Stop the process with
Ctrl+C. This is NOT installed as a Windows service or Startup task; machine
sleep, process exit or an unlaunched runner means no samples. Enabling
World Armor on the FastAPI process alone cannot launch it. No background
task is created by opening the iOS view.

## Private management endpoints

Every route requires `Authorization: Bearer <JARVIS API TOKEN>` and sends
`Cache-Control: private, no-store`.

- `POST /world-armor/v1/watches` with
  `{"investigation_id":"<saved-region-id>","interval_minutes":60,"max_checks":6,"lifetime_hours":6}`
  enrolls exactly one grant. It does not collect or launch the runner.
- `GET /world-armor/v1/watches` returns persisted grants, their
  state/check budget/next due/last outcome and the explicit statement
  `runner_auto_started=false`. Optional `investigation_id` filters.
- `POST /world-armor/v1/watches/pause`, `.../resume`, `.../stop`,
  with `{"watch_id":"<watch-id>"}`, transition that exact grant.
  List and stop work even with both switches disabled; resuming does not.
  Revoked/exhausted/expired grants never silently resume.

The iPhone/iPad workbench includes an additional "Explicit standing
watches" panel: choose a bounded interval, check limit and expiry; enroll,
inspect status, pause, resume or stop. It expressly states that the host
runner must be started separately and that there are **no push alerts**.
The watch workbench accesses only the saved region already selected by
the operator. Leaving the app foreground still hides the investigation
evidence, as in Phase 1.

## Budgets, durability, ownership and source semantics

- Per-grant interval: 30–360 whole minutes.
- Per-grant maximum collection attempts: 1–12; default API 6.
- Per-grant lifetime: 1–72 hours, clipped to the saved investigation's
  absolute expiry. There is no renew-after-expiry or automatic resume.
- Up to 12 active/paused grants across the store. The investigation's
  existing 20-total-sample cap remains authoritative, including foreground
  observations and other watches. A collection that hits the cap fails
  explicitly; it does not silently exceed it.
- Each watch is tied by SQLite foreign key to the previously saved region.
  Forgetting the region cascades its grants and local watch receipt rows.
  A revoked watch intentionally retains previous investigation samples
  until the user forgets the region or it expires. Provider systems and
  filesystem backups are separate.
- A SQLite `BEGIN IMMEDIATE` claim stores a per-watch lease before any
  provider call. At most one runner can claim a currently leased/due
  grant. Lease lifetime is 120 seconds, and every claim advances the
  next-due time by the chosen interval. If a runner dies, the next
  due time and lease expiry prevent immediate unchecked retry storms;
  network-side requests may have occurred without a committed receipt.
- Both a pre-fetch grant check and an **in-transaction post-fetch fence**
  reject receipt storage if the grant was paused/stopped/expired or the
  lease superseded during HTTP. Stopping cannot undo a sample already
  committed before revocation; it prevents future collection and
  late-commit collection. It does not promise to recall HTTP requests
  already underway.
- A receipt is labelled `sample_coverage_ok` only when all three
  integrated sources report `ok`; otherwise it is
  `sample_degraded_or_partial`. It is never a physical "all-clear."
  Collection failures are labelled, and no successful observation is
  fabricated. No push message is sent.
- An expired region deletes watch rows with its child rows the next time
  the existing store pruning path runs. Merely passing a watch's own TTL
  changes its watch state to expired; it need not immediately delete
  the investigation and its legitimate historical evidence.

## CI and actual acceptance

Run on exact PR head on Linux **and Windows**:

```text
python -m unittest discover -s tests -p "test_world_armor_watches.py" -v
python -m unittest discover -s tests -v
python -m jarvis_mrb.world_acceptance_check
```

Also run the existing iPhone **simulator** build. These tests are synthetic
and cannot prove the runner actually collected official/modelled live data
or ran on a user's real hardware.

For private physical acceptance, the operator must configure the backend,
enroll one real bounded region, deliberately launch the runner, verify at
least two distinct provider sample receipts at the correct interval against
the contemporaneous official/modelled feeds, inspect degraded-source
handling, pause/restart, revoke during an in-flight permitted HTTP fetch,
verify no further sample is committed, and forget the investigation.
External source entitlement, storage/attribution and provider terms must
be reviewed before production enrollment. Do not rely on this as an
emergency alert, evacuation recommendation or dispatch system.

## Deferred components

OS-native autostart, notification delivery, predicate configuration,
source-specific rate/cost ledger, ETag/Retry-After policy, watchdog health,
licensed camera watches, distributed workers, multi-source physical
colocation, external action grants and any economic extension are **not
implemented** by this PR. This increment establishes a bounded recurring
evidence pipeline and local operator controls, not the rest of Phase 3.
