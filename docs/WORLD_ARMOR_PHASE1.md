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
- `GET /world-armor/v1/investigations` — explicitly saved regions, **including while collection is disabled** so they remain available for user-directed forgetting. This does not contact providers.
- `POST /world-armor/v1/observe` — JSON `{"investigation_id":"<returned 32-char ID>"}`; requests providers **one time**, no scheduling.
- `POST /world-armor/v1/replay` — JSON `{"investigation_id":"<ID>","as_known_at":"2026-09-24T20:00:00Z"}`, or omit `as_known_at` for the latest saved receipts.
- `POST /world-armor/v1/changes` — JSON `{"investigation_id":"<ID>"}`; deterministically compare the last two saved receipt times, separate modelled AQI changes, source record revisions, **first received** (not necessarily newly occurred) events and source outage/recovery. If fewer than two receipts or evidence coverage is inadequate, show that explicitly. No provider request or background watch.
- `POST /world-armor/v1/correlate` — JSON `{"investigation_id":"<ID>","start_at":"2026-09-24T18:00:00Z","end_at":"2026-09-24T20:00:00Z","as_known_at":"2026-09-24T20:10:00Z","source_ids":["openmeteo_model","usgs_earthquakes"],"query_radius_km":10}`. `as_known_at` and `source_ids` are optional. Query **retained records only** with an exact 0–72h source-observed-time window in the saved region. Optional `query_radius_km` narrows, never expands, the operator's enrolled radius. A cross-source time match is a **candidate**, not a verified shared location or cause. NWS entries without a provider event timestamp appear in a separate *receipt-time-only* list. The API does not call providers, create a watch or act.
- `POST /world-armor/v1/hypotheses/query` — same bounded window/radius request shape as `correlate`. Reads retained evidence only and emits an evidence graph with typed `temporal_overlap` / source-revision edges plus **candidate_unverified** cross-source co-occurrence hypotheses. Every candidate exposes supporting observation IDs, independent-lineage count, spatial precision, assumptions, missing evidence, and alternate explanations. It emits zero causal/wrongdoing/identity claims and grants no action.
- `POST /world-armor/v1/forget` — JSON `{"investigation_id":"<ID>"}`; allowed even after World Armor is turned off so deletion isn't held hostage by a feature switch.
  The iPhone/iPad workbench continues to list existing regions and offer Forget when disabled; Observe and Replay remain blocked.

Each returns `Cache-Control: private, no-store`; callers must supply
`Authorization: Bearer <YOUR_PRIVATE_JARVIS_TOKEN>`. The feature flag
does **not** generate a token for you. No client or provider credentials
should ever be committed to this repo.

### iPad/iPhone correlation workbench

The existing native World Armor view now has a chosen-region MapKit center and
radial search circle, publisher-reported USGS epicenter markers where actually
available, a 6/24/72-hour observation-window selector, a within-enrollment
spatial radius slider, a date/time window-end picker, read-only cross-source
correlation cards, evidence/hypothesis cards with alternatives and missing
evidence, explicit provider coverage, and a
receipt-time rewind menu backed by the actual bounded `sample_timeline`.
MapKit's pin is the **user's inquiry location**; it is not a verified
earthquake epicenter, NWS alert polygon or sensor view footprint. Users must
explicitly tap `Observe once` to contact providers; `Correlate saved sources`
and `Replay retained evidence` read only saved receipts. Evidence clears
from the phone's view when the app leaves the foreground or Reality Mesh
privacy is disabled. Native iOS build success is not actual device acceptance.

### Reproducible query plan and sample-level coverage

Every read-only correlation now returns a canonical `query_id` plus its exact
typed `query_plan`: investigation, source-observed-time window, as-known
receipt cutoff, selected source IDs, bounded radius and pair window. When the
operator chooses “latest saved evidence” rather than an explicit cutoff, the
cutoff canonicalizes to the newest retained sample receipt (or the requested
window end if no sample exists), **not the wall clock**. Re-running an unchanged
retained evidence set therefore produces the same query ID; collecting another
sample advances it.

Each observation also carries the coverage status of the exact sample that
produced it. A stale model result remains inspectable evidence, but cannot
support an independent-source correlation or hypothesis unless its producing
sample was `status=ok`. Later provider outage does not rewrite an earlier
healthy receipt; coverage is evidence-time-specific as well as summarized at
the latest receipt. The replay's actual `sample_timeline` now includes per-sample
per-provider `source_coverage` with status, check time, retained-source
reported count, and scope; the iPhone/iPad rewind menu displays the historical
status of AQI, NWS and USGS next to each receipt. These are discrete samples,
not inferred continuous monitoring.

An adapter returning more than the explicit normalization cap (15 NWS alert
rows or 50 USGS earthquake rows) produces `partial` coverage even when the
upstream request itself succeeded. The fixed NWS adapter now reads enough of
the approved response to detect a 16th eligible alert; the fixed USGS adapter
requests at most 51 source items to detect whether its retained 50-item result
is incomplete. Both emit `source_limit_reached`, while World Armor retains
only the original per-source cap. A `partial` receipt's saved rows remain
reviewable but cannot corroborate a second source in an evidence candidate;
`ok` must not imply that the entire response was retained. An adapter also flags structurally discarded or unidentified source
rows as `partial`; the normalizer independently marks invalid incoming
rows as `partial` rather than silently treating the retained subset as
complete. Intentionally expired NWS alerts are excluded as an explicit
time filter, not a malformed record. These flags cannot detect omissions
upstream of the approved adapter itself. Counts refer to normalized records
before deduplication, not necessarily new SQLite observations.

A revision fingerprint covers a source assertion's event time, publish time,
kind, lineage, geometry basis and normalized values. Correcting a USGS
occurrence timestamp is therefore a new linked revision even if the magnitude,
place and other display fields are unchanged. Comparisons of consecutive
`fixture` and `real_adapter` receipts return
`comparison=incompatible_adapter_modes` without claiming an AQI or event
change; both individual samples can still be replayed.

### Evidence graph and hypothesis discipline

The workbench can now turn retained eligible source observations into a
deterministic evidence graph. A displayed hypothesis means only that two
independent source lineages meet the current typed co-occurrence rule. It is
always `candidate_unverified`; the UI shows alternatives and evidence still
needed. Synthetic fixture evidence cannot corroborate a real-adapter
observation. Every edge must reference evidence inside the bounded graph.
No free-form model prompt or user-written accusation is accepted by this
endpoint, and there is no path from a hypothesis to Agency, Conductor, trading,
messaging, device control or any other action.

### Spatial/temporal limits (deliberate)

The enrolled region bounds every subsequent spatial query: the center is
immutable and the requested radius can only shrink. Actual valid USGS
publisher epicenters are checked by geographic distance when present.
Reports with unknown epicenters cannot satisfy the narrower radius. NWS is
queried for a point without retaining full alert footprint or issuance time;
modelled AQI belongs to a coarse model grid. Thus Jarvis can join independent
reports temporally within a bounded queried region, but cannot infer exact
event-to-event co-location, road sightlines, route impact or causation. Source time must be known to join
on event time; unknown-time NWS items can be displayed only as **received at**
a specific time. `as_known_at` is the cutoff on when Jarvis received records,
not a reconstruction of all real-world activity.

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
- USGS reports now retain validated publisher-supplied GeoJSON epicenter
  coordinates when available; malformed and older source reports have an
  explicitly unknown epicenter. The selected region's center is **not** an
  earthquake epicenter.
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
runner (actual deployment OS) in addition to Linux. The new **World Armor** button on the iPhone/iPad main toolbar opens
`ios/JarvisIOS/WorldArmorView.swift`, with an explicit coordinate entry,
selected-region MapKit preview, one-tap Observe, source coverage, historical
Replay, two-sample Compare and destructive Forget. It does **not** collect
until you deliberately create a region and then press Observe. MapKit may
request tiles for an already-selected region; these map tiles are separate
from Jarvis's three one-shot provider requests.

An iOS **simulator build** checks the source and project wiring, not actual
physical iPhone deployment, backend endpoint availability, provider license,
real camera imagery or successful source observations on your equipment.

### What is next

Phase 1 follow-up: source-specific footprint and exact sample/provider
coverage audit, verified geometry from licensed primary sources and explicit
source license record; then a
reproducible *cross-source* spatial/temporal correlation demonstration.
Later phases add actual approved watches and leased typed workers.
See W0–W16 in [the full spec](WORLD_ARMOR_SPEC.md).

The “suit of armor around the world” / Ultron reference is a caution:
perception and lawful computation can grow without an expansion in authority
over people, devices, accounts or the world itself.
