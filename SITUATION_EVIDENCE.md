# Situation Evidence Unification (stacked after convergence PR #5)

The existing `world_situation.compile_situation()` and
`context_for_query()` select a real calendar event and gather linked
participants, projects, pending commitments, intentions and recent events.
This addition calls `situation_evidence.compile_evidence()` for **read-only,
source-tagged, exact-event-related observations**. It is not a universal
background daemon and does not create permissions.

## Implemented, now

| Input | What is included | Fail-closed rule |
|---|---|---|
| Enrolled Guardian | Last stored `at_risk`, `monitoring` or `past_deadline_unverified` signal with its watch id and last-check time | Only for an intention already linked by the existing graph to **this selected meeting**, exact matching deadline, evaluated <=15 min ago. Does **not** call `evaluate_once`, emit an attention event, send anything, infer current travel conditions or re-enroll watches. |
| Life Fabric | Explicitly enrolled, incomplete near-term/overdue/blocked task with due state, completion evidence kind, domain and match reason | Requires exact `calendar:<event id>` / event id source reference, >=2 distinctive matching title terms, or a connected project name. No unrelated medical, money, or personal task included merely because it is urgent. A provider receipt or document alone does not mark an obligation as completed. Reads existing ledger only; no new Life database created when absent. |
| Mission Control | If furnished explicitly, a time-fresh, exact-event iPhone mission phase and timestamp | iPhone Mission Control actually resides in local Keychain; the Windows backend has **no current automatic access**. The optional typed `phone_mission` argument requires event ID, start and literal destination equality plus a <=2 min observation. Nothing is uploaded automatically and no GPS or navigation grant is passed. Without the optional snapshot, source status explicitly says `phone_local_not_shared`. |
| Reality Lens | If furnished a confirmed exact calendar-place match, a historical difference between two user-saved snapshots, with provider and both capture times | Calendar currently stores **text location**, not MapKit-resolved coordinates, so no automatic location join is possible. The optional `resolved_place` argument must exactly match the event's literal location and coordinates; database is keyed by the same coordinates. The newest saved snapshot must be <=2 h old and prior <=30 d. This is **not** a fresh provider read or the last unsaved `Sense and compare` result. If no exact match is available, status is `exact_place_not_linked`. |

The structured result includes `cross_source_evidence.sections`,
`source_status`, provenance, actual evaluation/capture times,
`external_actions: 0`, `model_calls: 0`. The text context includes only
bounded evidence, and explicitly mentions that absent local iPhone mission
and exact location linkage cannot be treated as a reassuring all-clear.

**Important correction to the original proposal:** the idea is the correct
integration point but its four-way unification is *not* zero infrastructure.
Guardian's latest deadline signals and Life Fabric's manually enrolled tasks
are already queryable from the backend. Mission Control's mission board is
phone-local by design, and Reality Lens does **not** persist the last
unsaved diff or associate saved MapKit coordinates with a calendar's text
location. Pretending those data are already accessible would violate the
repository's evidence/permission contract.

## Acceptance / next transport boundary

1. On a matching backend, select a real next meeting; check that the normal
   participant/project/commitment prebrief still appears.
2. Enroll an explicit Guardian goal that the meeting graph genuinely links.
   Evaluate through the Guardian's **separate authorized workflow**. Within
   fifteen minutes its prior signal may appear, but prebrief must not run
   Guardian evaluation, wake an attention watch or dispatch a tool.
3. Explicitly add a matching Life task and deadline; confirm unrelated
   sensitive tasks never bleed into this prebrief. Match its exact calendar
   ID to avoid lexical ambiguity where possible.
4. To make the iPhone portion end-to-end, design a **separate per-prebrief,
   user-consented request** carrying only the exact event's phase and
   checked timestamp; do not turn local Mission Control into a background
   location uplink. Verify the exact event identity and location.
5. To make the location portion end-to-end, add a **user-confirmed event to
   MapKit-place binding** and an explicit choice whether to include
   *historical saved snapshots*. Fresh place changes require an independent
   foreground Sense request; do not change existing opt-in retention or
   trigger a camera merely because a meeting prebrief was requested.

Synthetic unit tests must verify event mismatch, stale evidence,
unavailable sources, completion distinctions, location mismatch and no
side-effect calls. Real provider/physical iPhone acceptance remains separate.
The main convergence PR #5 is independent and must be reviewed/merged first.
