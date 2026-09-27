# Release status — C00–C22 (governed by `criteria.md`)

> **RELEASE STATUS: NOT COMPLETE.** No gate has REAL PASS evidence. Nothing here
> upgrades SOURCE PRESENT / SYNTHETIC PASS to REAL PASS.

Release branch: `claude/jarvis-release-completion-77kour` (= `main` + `jarvis/cloud-cognition-groq`,
which carries `criteria.md`). Frozen candidate SHA: **none yet**.

Allowed states: `UNPROVEN` · `IMPLEMENTING` · `IMPLEMENTATION BLOCKED` · `SYNTHETIC PASS` ·
`READY FOR REAL TEST` · `REAL TEST FAILED` · `REAL PASS` · `BLOCKED ON USER/HARDWARE/EXTERNAL SERVICE`.

Evidence ledger: `jarvis-release-gate` (see `docs/RELEASE_EVIDENCE.md`). A gate is PASS only
when that ledger holds a valid PASS record bound to the frozen SHA.

## Matrix

| Gate | State | Principal blocker | Next action |
|---|---|---|---|
| C00 Candidate integrity | IMPLEMENTING | `/health` had no code SHA; iOS build carried no SHA; no single C00 check | Add build identity (backend + iOS), `jarvis-release-gate c00-check`; then freeze + deploy (user) |
| C01 Feature inventory | IMPLEMENTING | README (3.4k lines) + UI claims not mapped to gates | Write `CAPABILITY_INVENTORY.md`; correct overstated README text |
| C02 Ordinary interaction | IMPLEMENTING | No "what can you do right now?" answer reflecting live enabled/reachable capabilities | Deterministic live capability inventory tool + route |
| C03 World model / identity | IMPLEMENTING | No conversational path to assert or correct a fact as the user (distinct from inference) | Add user fact/correction tools + entity readback with provenance/disputes |
| C04 Intentions across restart | SYNTHETIC PASS (A1) | Real restart on Windows + physical iPhone | Ready once C00 deployed; harness `jarvis-agency-real-gate start A1` |
| C05 Executive loop | SYNTHETIC PASS (A2) | Agency tool scope limited to PC/browser/Google/state tools | Widen Agency tool scope (see C22) then real test |
| C06 Authority / approval | SYNTHETIC PASS (A3, A11) | Real protected write + denial on device | Real test after deploy |
| C07 Verification / recovery | SYNTHETIC PASS (A4) | Real verified write + induced failure | Real test after deploy |
| C08 Replan / dormant wake | SYNTHETIC PASS (A5, A6) | Needs a real observable external change reachable by Agency observations | Real test after Agency world-evidence tools |
| C09 Proactivity | IMPLEMENTING | Agency interruptions only go to the foreground WebSocket; APNs carried only World Armor events | Route warning/urgent proactive interventions into the durable APNs outbox |
| C10 Situational awareness | SYNTHETIC (world acceptance) | Real imminent event with multi-source data | Real test after deploy |
| C11 Deliberation / gaps | SYNTHETIC PASS (A7, A9, A10) | Production model workers on real task | Real test after deploy |
| C12 Cognitive routing | SOURCE PRESENT | Real Groq key on iPhone Keychain; real outage case | Ready after iOS build installed |
| C13 Conductor | SOURCE PRESENT | Real paired workstation + phone | BLOCKED ON HARDWARE until Mac node/Windows flags configured |
| C14 Reality Mesh | SOURCE PRESENT | Real Mac node, Tailscale, screen permission | BLOCKED ON HARDWARE (configured Mac required) |
| C15 Reality Graph | SOURCE PRESENT | Real mission with ≥2 real sources | Real test after deploy |
| C16 Public cameras | SOURCE PRESENT | 3 real lawful sources, 2 publishers, 2 regions | Real campaign after deploy |
| C17 Providers | SOURCE PRESENT | Inventory of shipped providers + each real request | Derive list in C01; real campaign |
| C18 Closed-app / resilience | SOURCE PRESENT | APNs requires paid Apple Developer team + .p8 key | BLOCKED ON USER (APNs credentials) |
| C19 Presence (HomeKit) | SOURCE PRESENT | Physical light + human observation | Real test after iOS install |
| C20 Privacy / fail-closed | SYNTHETIC (partial) | Consolidated campaign over the 8 cases on real deploy | Script the campaign; run after deploy |
| C21 24-h soak | UNPROVEN | No soak sampler | Add `jarvis-release-soak` sampler; run 24 h after freeze |
| C22 Capstone | IMPLEMENTING | **Agency cannot compose World Armor / weather / hazards / cameras / Presence / Mesh / Reality Graph — they are HTTP/UI-only, absent from the tool registry and Agency scope** | Expose them as permission-gated, verifiable Agency tools |

## Audit findings (2026-09-27)

- `criteria.md` existed only on `jarvis/cloud-cognition-groq`; `main` lacked it and cloud cognition,
  while the groq branch lacked main's two-region comparison. Merged both into the release branch.
- Full Python suite on the merge: 2 regressions (time-bomb in APNs outbox tests; Caltrans placeholder
  threshold) — fixed. Agency synthetic A1–A12: ok. World acceptance + world check (prepared DB): ok.
- Agency A1–A12 real-gate harness (`jarvis-agency-real-gate`) is strong and SHA/env-bound; it covers
  C04–C08, C11 and part of C06/C09/C22 but nothing for C00–C03, C10, C12–C21.
- 84 conversational tools exist; Agency may use 55 of them. None cover World Armor, NWS/USGS/air,
  public cameras, movement, Reality Graph, Mesh, Conductor or Presence. This is the shared root cause
  blocking C05/C08 real tests with world evidence, C15/C17 through the normal user path, and C22.
- `jarvis/cloud-cognition-groq-lite` removes APNs for Personal Team signing: C18 needs a paid team.
