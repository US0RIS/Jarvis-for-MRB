# Agency 1.0 vs. Conductor and Mission Control — convergence review

**Reviewed for draft convergence PR; source assessment, not REAL deployment acceptance.**
Read `AGENCY_ACCEPTANCE.md` (A1–A12), `jarvis_mrb/desired_state.py`,
`jarvis_mrb/agency_plan.py`, `jarvis_mrb/agency_runtime.py`,
`CONDUCTOR.md`, `jarvis_mrb/conductor.py`, `MISSION_CONTROL.md` and
`ios/JarvisIOS/MissionControl.swift`.

## The ancestry matters

`jarvis/agency-1.0` at `98478866f82c4b309aaf037d4ff980af5b46aa3a`
is a **direct ancestor** of `jarvis/memomind-prep`, not an independent
unmerged implementation. Comparison returned zero commits unique to the
Agency branch versus the MemoMind line. The reconciled convergence merge
retains that Agency history in its Git ancestry. **Keep the original Agency
branch and PR for human archival/review decisions; no deletion or force push.**

## Are these the same architecture built twice?

**No; different levels of control with some overlapping safeguards.**

| Component | What it actually owns | Durability and authority | What it does not prove |
|---|---|---|---|
| Agency 1.0 | General desired-state and observable-success contracts, multi-step plans and dependencies, approval/denial resumption, action-verification reconciliation, changed-fact replanning, dormant watches, deliberation, gap handling and self-model | World-model/Agency tables persist across service restarts; ordinary named-tool permission engine; long-lived open-ended but bounded goals | All REAL A1–A12 gates passed or that a particular device/provider is presently connected |
| Conductor v1 | Narrow workstation mission: one selected known Mac/Windows host, 1–3 allowed benign app names, optional two-minute view, process-observation readback | Separate `conductor.sqlite3`, 120-second one-use RAM-phone grant, reserved step before side effect, no automatic retry after ambiguous external outcome | General autonomous planning, replan across goals, actual foreground focus or external real-world completion beyond observed running process |
| Mission Control | Exact user-enrolled Calendar appointment, fresh iPhone GPS/MapKit route, bounded arrival window and optional one-use Apple Maps handoff | Phone-local/Keychain mission and exact per-event navigation permission; presence/route observations | Attendance, generic workstation control, arbitrary execution of Agency steps |
| Goal Guardian / Counterfactual Guardian | Observe enrolled goal deadlines, linked dependencies or appointment risk and surface bounded warnings/drafts | Independent opt-ins and user-driven permissions; mostly observations/drafts | Authority to send or act on a user-authored goal without a separate grant |
| Reality Graph / Life Fabric | Source-qualified state and manually enrolled tasks/assets/receipts | Their own explicit, bounded evidence stores | An Agency plan, a general physical actuator or trusted third-party provider attestation |

There **is** conceptual duplication around "mission", "plan", "receipt" and
"one-use grant." Conductor and Mission Control have intentionally separate
data stores, UI state and permission lifetimes; that is not evidence that a
second general-purpose Agency executive should be built. A task-scoped
process-observation readback is not a substitute for persistent whole-goal
convergence; Agency's durable desired state is not a replacement for a
phone-local GPS safety/privacy contract or the host-side Conductor grant.

## Recommendation for A1–A12

Keep **one canonical general executive: the existing Agency 1.0**
`desired_state` + `agency_plan` + `agency_runtime` stack. Target acceptance
work there and *reuse* the narrower specialized Mission Control/Conductor
modules as carefully authorized, typed execution/observation adapters only
where their exact authority can be preserved. Avoid transplanting an entire
second persistent goal planner from Conductor or iOS into Agency. Any future
bridge must prevent Agency from manufacturing a physical-presence attestation
or receiving blanket authority from an already-enrolled mission.

| Agency gate | Appropriate convergence route |
|---|---|
| A1 persistent desired state | Agency's world/plan/runtime tables, boot and restart receipts; Conductor's short-lived draft is not A1 |
| A2 two action/observation cycles | Agency step engine with two independently evidenced external steps; a single Conductor app batch alone does not prove repeated gap evaluation |
| A3 protected-action approval/denial | Agency permission/approval resume on the *same* step; Conductor grants remain separately scoped to exact workstation actions |
| A4 actual outcomes including failure | Existing Agency action-verification reconciliation plus compatible source-specific Conductor/Mission receipts; never interpret an app launch exit code or Maps handoff as the ultimate outcome |
| A5 relevant external change and replan | Agency relevance hash/event watermark and replacement-plan lineage; use domain observers as inputs, not as parallel planners |
| A6 dormant-goal wake | Agency persisted wake watches; Guardian's independently enrolled notifications are not an automatic substitute for Agency causal reactivation |
| A7 parallel disagreement | Agency multiworker deliberation and real worker evidence; no equivalence to running several Conductor apps |
| A8 exception-based attention | Agency Attention and opted-in Guardian reporting with deduplication and suppression; real interruption delivery still needs same-SHA device proof |
| A9 capability gaps | Agency explicit unavailable/disabled adapter lifecycle; Conductor's named-app inventory must not be fabricated as broader access |
| A10 counterfactual branches | Agency's durable alternatives, assumptions and selection provenance; Mission Control ETA is domain-specific input only |
| A11 self-model vs policy | Agency preference-inference provenance; never promote a repeatedly granted Conductor action into standing authority |
| A12 one-decision end-to-end | One Agency desired-state trace combining permitted private/public reads, deliberation, protected action, source-specific verification and causal replan; specialized packs may provide steps but cannot mint the REAL receipt themselves |

**Status:** this is a code-and-contract comparison, not a successful A1–A12
REAL campaign. The contract requires the actual Windows backend, physical
iPhone, genuine providers and immutable same-SHA/environment receipts. Full
Linux CI, isolated `world_acceptance_check` and `world_check`, and a
successful iOS simulator build are necessary but cannot upgrade the status to
**Observed deployed** or `release_ready:true`.

## Branch handling

`jarvis/agency-1.0` has no unique commits missing from the MemoMind lineage
at the verified comparison point. Leave its branch and PR intact for a
human archival decision. Do not retire Agency functionality merely because
Conductor or Mission Control use the word "mission". Do not merge ForgeCAD
or widen physical action authority as part of this convergence.
