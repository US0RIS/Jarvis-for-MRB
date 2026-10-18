"""HORUS primitive library: deterministic cores for the ideas captured in future.md.

Stdlib-only and side-effect free: callers supply observations, clocks and
executors; these modules decide, verify and explain.  ``registry.IDEAS`` maps
every future.md idea to the module/attribute implementing (or, for external
research candidates and hardware bake-offs, evaluating) it.  Implementations
here are source-level capability, not an observed-deployed claim; real device and
provider acceptance remains separate evidence.

Modules (user-facing subsystem names in brackets):

* ``epistemics`` [Kant] — Epistemic Freshness Gate, TTLs, linter, receipts, lineage.
* ``belief`` [Mnemosyne] — User Belief Model and decision-relevant divergence.
* ``analysis`` [Ariadne] — ACH, information gain, assumptions, investigation, simulation.
* ``identity`` [Ariadne/Cerberus] — claim-based identity resolution and minimisation.
* ``temporal`` [Carcosa] — bitemporal truth model, rewind, diff, aliases, GC, export.
* ``standing`` [Cassandra] — predicate DSL, standing queries, Reality Compiler, invariants.
* ``attention`` [Mercury] — delivery, modes, arbitration, escalation, alarms, barge-in.
* ``memory`` [Mnemosyne] — capture bus, promotion, resurfacing, friction, spatial memory.
* ``life_admin`` [Mercury] — briefs, email/receipts/contracts, obligations, opportunities.
* ``spatial`` — anchors, semantic rooms, procedures, landmarks, pointing loop.
* ``capabilities`` [Kant/Cerberus] — capability bus, routers, personal API, mission recorder.
* ``continuity`` [Mercury] — sessions, handoff, transports, background jobs, media.
* ``automation`` [Sisyphus] — routine learning, do-the-rest, demonstrate/compile/verify.
* ``reliability`` [Sisyphus] — SLOs, dependency map/chaos, rollout, reconciliation, CBM.
* ``ethics`` [Cerberus] — ethical context engine, scoped emergency authority, guards.
* ``emergency`` [Cassandra] — playbooks, competence routing, IBW, failover, family beacon.
* ``providers`` — public/RF/sensor normalisers, Home Assistant bus, media gateway.
* ``views`` — command center, dynamic COP, coverage, world search, describe, overlay.
* ``evaluation`` [Kant] — TTS and model bake-offs, eval matrix, trace ledger.
* ``humor`` — private Commentary/Suggestion modes with privacy and timing gates.
* ``radar`` — repository radar, research catalog, meta design tools.
"""
