# Release status — C00–C22 (governed by `criteria.md`)

> **RELEASE STATUS: NOT COMPLETE.** No gate has REAL PASS evidence. Nothing here upgrades SOURCE PRESENT or
> SYNTHETIC PASS to REAL PASS.

- **Release branch:** `claude/jarvis-release-completion-77kour` (`main` + `jarvis/cloud-cognition-groq`, the branch that carries `criteria.md`).
- **Frozen candidate SHA:** none yet.
- **Evidence:** `jarvis-release-gate` (`docs/RELEASE_EVIDENCE.md`).
- **Procedure:** `docs/RELEASE_RUNBOOK.md`.

Allowed states: `UNPROVEN` · `IMPLEMENTING` · `IMPLEMENTATION BLOCKED` · `SYNTHETIC PASS` · `READY FOR REAL TEST` ·
`REAL TEST FAILED` · `REAL PASS` · `BLOCKED ON USER/HARDWARE/EXTERNAL SERVICE`.

"READY FOR REAL TEST" means the source path exists, synthetic tests pass, and the machine evaluator for the gate is in place.
The gate still needs the frozen deployment and the user's real run.

| Gate | State | Principal blocker | Next action |
|---|---|---|---|
| C00 Candidate integrity | READY FOR REAL TEST | Deployment of this branch to Windows and the iPhone; a paired Mac node | Deploy → `validate` → `freeze` → install the iOS build from the same SHA |
| C01 Feature inventory | BLOCKED ON USER | Part B of `CAPABILITY_INVENTORY.md`: the user must choose P (add a REAL test) or L (label "not release-accepted") for each group | User decision, then I amend `criteria.md` (C01 appendix) or the labels |
| C02 Ordinary interaction | READY FOR REAL TEST | — | Real session on the iPhone |
| C03 World model / identity | READY FOR REAL TEST | — | Real session (entity in ≥3 sources, correction, restart) |
| C04 Intentions across restart | READY FOR REAL TEST | — | "My goal is …" → confirm → restart; A1 inside C04 |
| C05 Executive loop | READY FOR REAL TEST | Local Qwen plan quality for a real two-write goal (unmeasured) | A2 inside C05 |
| C06 Authority / approval | READY FOR REAL TEST | — | A3 + A11 inside C06 |
| C07 Verification / recovery | READY FOR REAL TEST | — | A4 inside C07 |
| C08 Replan / dormant wake | READY FOR REAL TEST | — | A5 + A6 inside C08 (dormant `wait_until` now exists in production) |
| C09 Proactivity | BLOCKED ON USER (APNs) | Closed-app delivery needs a paid Apple Developer team and a `.p8` key | A8 inside C09 once APNs is configured |
| C10 Situational awareness | READY FOR REAL TEST | — | Real imminent meeting |
| C11 Deliberation / gaps | READY FOR REAL TEST | — | A7 + A9 inside C11 |
| C12 Cognitive routing | READY FOR REAL TEST | Groq key on the iPhone | Real session; evaluator checks tiers, Groq, fallback, redaction and protected proposal |
| C13 Conductor | BLOCKED ON HARDWARE | Mac node running `jarvis-mac-node.py --allow-app-launch` over Tailscale | Configure the Mac, then a real session |
| C14 Reality Mesh | BLOCKED ON HARDWARE | Same Mac node with `--allow-screen` and Screen Recording permission | Configure the Mac, then a real session |
| C15 Reality Graph | READY FOR REAL TEST | — | Real mission |
| C16 Public cameras | READY FOR REAL TEST | User must choose 3 lawful sources (2 publishers, 2 regions) | Real campaign; evaluator checks counts, regions, failure and pause |
| C17 Providers | BLOCKED ON USER (inventory) | Which providers are claimed depends on the C01 decision; NWS, air, USGS and OpenSky are evaluated automatically | Real campaign |
| C18 Closed-app / resilience | BLOCKED ON USER (APNs) | Paid team + APNs key; watchdog configuration | Real session after APNs |
| C19 Presence (HomeKit) | READY FOR REAL TEST | — | Real session + human attestation |
| C20 Privacy / fail-closed | READY FOR REAL TEST | — | Live probes on the deployed build (validated here against a local service) + revoke/stop |
| C21 24-h soak | READY FOR REAL TEST | Needs every earlier code change finished | Soak after the final freeze |
| C22 Capstone | READY FOR REAL TEST | Composition now possible (world, device, calendar, mail, cameras, Mesh, dormant watch, proactivity); unproven on real models | After the freeze; you choose the objective |

## Engineering done in this release branch

| Change | Gates | Notes |
|---|---|---|
| Merged `criteria.md` and cloud cognition | — | Fixed two test regressions and one iOS compile break caused by the merge (APNs delegate) |
| Evidence ledger (`jarvis-release-gate`) | C00–C22 | Append-only and hash-chained; build identity for the backend and iOS; evaluators for C00, C08, C12, C16–C21 |
| Agency capability bridge | C05, C08, C15–C17, C19, C22 | World/place observations as beliefs; camera sources; Presence with readback verifier; Mesh status; `wait_until` dormant goals; grounded world/device success criteria; planner argument contracts |
| Goal intake | C04, C22 | "My goal is …" becomes a confirmed offer to pursue it |
| Live capability inventory | C02 | "What can you do right now?" |
| User facts and corrections with provenance | C03 | — |
| Proactive interventions to APNs, with dedup | C09, C18 | Adds context-aware deferral (driving, meeting, user-set busy window) |
| Durable cloud routing telemetry | C12 | iPhone reports fallbacks; the deterministic tier is now recorded correctly |
| Presence denials recorded; provider gaps recorded | C17, C19 | — |
| 24-h soak sampler | C21 | — |
| README / Feature Guide truthfulness; `CAPABILITY_INVENTORY.md` draft | C01 | — |
