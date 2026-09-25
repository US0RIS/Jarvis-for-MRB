# World Armor Phase 1 — executable kernel

**Status:** source implementation on `jarvis/world-armor-phase1-kernel`, stacked on
the [full design spec](WORLD_ARMOR_SPEC.md). Not observed deployed. No live
provider entitlement or physical Windows/iPhone acceptance is inferred from CI.

## Exactly what works in this PR

A bounded, authenticated, **default-off** one-shot investigation:
create a region with a clear expiry; click/tell an authorized client to
collect **once** from existing `physical_conditions` and
`regional_earthquakes` fixed-provider adapters; inspect independent status
for (1) modelled Open-Meteo/CAMS US AQI, (2) NWS point weather alerts and
(3) USGS regional M>=2.5 events; replay the *data Jarvis had received as of
a specified time*; inspect source-native record revisions; forget an entire
investigation. This is **not** a general Planetary Event Graph, spatial
join, continuous watch, computer worker, command platform or trading system.

The default-off gate is `JARVIS_WORLD_ARMOR_ENABLED=1` on the Windows
Jarvis backend. All API endpoints require the same **configured bearer token**
as Reality Mesh. A tokenless backend returns 503, not access to your region.

### Private API (existing FastAPI backend)

- `GET /world-armor/v1/capabilities` — status and precise limits; never contacts providers.
- `POST /world-armor/v1/investigations` — JSON `{"label":"Test corridor","latitude":34.12,"longitude":-118.16,"radius_km":30,"lifetime_hours":24}`.
- `GET /world-armor/v1/investigations` — explicitly saved regions.
- `POST /world-armor/v1/observe` — JSON `{"investigation_id":"<returned 32-char ID>"}`; requests providers **one time**, no scheduling.
- `POST /world-armor/v1/replay` — JSON `{"investigation_id":"<ID>","as_known_at":"2026-09-24T20:00:00Z"}`, or omit `as_known_at` for the latest saved receipts.
- `POST /world-armor/v1/changes` — JSON `{"investigation_id":"<ID>"}`; deterministically compare the last two saved receipt times, separate modelled AQI changes, source record revisions, **first received** (not necessarily newly occurred) events and source outage/recovery. If fewer than two receipts or evidence coverage is inadequate, show that explicitly. No provider request or background watch.
- `POST /world-armor/v1/forget` — JSON `{"investigation_id":"<ID>"}`; allowed even after World Armor is turned off so deletion isn't held hostage by a feature switch.

Each returns `Cache-Control: private, no-store`; callers must supply
`Authorization: Bearer <YOUR_PRIVATE_JARVIS_TOKEN>`. The feature flag
does **not** generate a token for you. No client or provider credentials
should ever be committed to this repo.

### Storage and interpretation

- New separate `JarvisForMRB/world_armor.sqlite3`; no raw response, video,
  face, license plate, aircraft identifier, private user-world DB copy or
  unbounded stream. Records: investigation, sample receipt, normalized
  source observations, independent provider coverage. Names and selected
  coordinates are retained only by **explicitly creating** the region.
- Up to 12 active regions, 20 source checks per region, up to 1200 distinct
  observations, radius 1–100 km, expiry 1–72 h. No background scheduler.
- US AQI is **modelled**, not measured on the user's street. Data comes with
  model observation time, separate Jarvis receipt time and source lineage.
- Existing NWS adapter provides alert IDs but not publication/issue times or
  alert footprint: `observed_at` and `published_at` deliberately null;
  the selected point is the **query point**, not an alert footprint.
- Existing USGS adapter gives event time/magnitude/source ID but no
  geographic coordinates per earthquake: the selected region is a query
  radius, **not the event's epicenter**.
- Changes compare compatible results for the same explicitly selected region: modelled AQI before/after; source-native earthquake/alert first-seen records and exact ID revisions. Provider failures appear as **source-status changes**, never as real-world changes or implied resolution. A missing record is not a proven disappearance because the current normalization does not retain per-sample complete provider-ID membership.
- Duplicate provider record content is deduplicated; changed contents with
  the same provider key create a new revision and explicit supersession.
  `replay(as_known_at)` selects what Jarvis had received then. Prior source
  corrections remain inspectable.
- Provider outage, unsupported NWS geography, malformed or missing time and
  empty observed events are distinct. Absence is **not** an all-hazards,
  all-aircraft or all-infrastructure clearance. `fixture_only` test data
  is explicitly labelled so no synthetic observation is presented as live.
- Expired investigations are excluded immediately and physically pruned on
  later store access, not via a hidden background process. `forget` removes
  live investigation/child rows with `secure_delete`, not third-party
  source records or independent filesystem backups.

### How the first physical acceptance would work

On a real configured Windows backend, authorize one selected region;
compare the three provider receipts to the actual official/modelled responses
and known coverage at the exact time; rerun later; demonstrate a changed
provider ID's revision or a time-separated model observation; replay before
and after; disconnect one source and confirm explicit `unavailable`; then
forget and confirm the SQLite records are gone.

Run `python3 -m unittest discover -s tests -v`,
`python3 -m jarvis_mrb.world_acceptance_check`, prepare an **isolated**
test world and run `python3 -m jarvis_mrb.world_check`. Run the Windows
runner (actual deployment OS) in addition to Linux. Simulator builds
cannot assert the app exposes a new World Armor view: **this PR only adds
backend endpoints**, not a map or Swift UI.

### What is next

Phase 1 follow-up: source-specific footprint and exact sample/provider
coverage audit, query/replay UI, explicit source license record; then a
reproducible *cross-source* spatial/temporal correlation demonstration.
Later phases add actual approved watches and leased typed workers.
See W0–W16 in [the full spec](WORLD_ARMOR_SPEC.md).

The “suit of armor around the world” / Ultron reference is a caution:
perception and lawful computation can grow without an expansion in authority
over people, devices, accounts or the world itself.
