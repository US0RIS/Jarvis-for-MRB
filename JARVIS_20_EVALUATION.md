# JARVIS-20 Evaluation Suite

JARVIS-20 is the fixed, repeatable behavioral scorecard for Jarvis development. It is not a replacement for the 12-part Definition of Done and does not add a new completion criterion. Its purpose is to answer a narrower engineering question:

> Is Jarvis becoming more capable, more integrated, and more trustworthy from build to build?

The suite contains 20 conceptual tests. Their meanings stay fixed. The concrete instance used for a scored run should change so Jarvis cannot improve by memorizing benchmark answers.

## Scoring

Each test is scored from 0 to 3:

- **0 — Fail:** cannot complete the task or gives a materially wrong result.
- **1 — Partial:** meaningful progress, but needs hand-holding, misses important context, or makes an unjustified claim.
- **2 — Pass:** completes the intended behavior correctly and autonomously.
- **3 — Excellent:** behavior is good enough that the evaluator could reasonably trust Jarvis in a real situation without corrective intervention.

Maximum score: **60**.

North-star tests are **7, 8, 12 and 17**. Their separate maximum is **12**.

Suggested interpretation:

- 0–20: prototype
- 21–30: capable demo
- 31–40: useful assistant
- 41–50: strong integrated agent
- 51–56: highly reliable personal agent
- 57–60: exceptional / near north-star

The labels are engineering shorthand, not claims of general intelligence.

## Fixed tests

1. No-tool judgment
2. Ambiguous follow-up
3. Personal Notecard persistence
4. Notecard to action
5. Identity continuity
6. Persistent objective
7. Situational awareness **(north star)**
8. Cross-source contradiction **(north star)**
9. Document change detection
10. Executive judgment
11. Efficient current lookup
12. Rigorous recommendation **(north star)**
13. Long-tail discovery
14. Research adversary
15. Research calibration
16. Action permission
17. Closed-loop verification **(north star)**
18. Failure detection
19. Room audio
20. Presence greeting

The canonical prompt/pass-condition/variant rules live in `jarvis_mrb/jarvis20.py` and are exposed by `jarvis-20 plan`.

## Anti-overfitting rule

Do not permanently associate a conceptual test with one answer.

Examples:

- Test 1 is not permanently `17 × 24`; choose a different simple problem.
- Test 8 is not permanently `Apollo indemnity cap 10% vs 15%`; change project, term, values and source order.
- Test 13 is not permanently one obscure watch/car/hotel; privately choose a different long-tail candidate each scored run.
- Test 17 should alternate among independently observable actions when practical.

The score sheet contains an `instance` field. Record the concrete variant used so later regressions can be diagnosed without turning that instance into the permanent test definition.

## Preflight is not a score

`jarvis-20 preflight` runs deterministic source/integration prerequisites that can be exercised without the live web, real accounts, or hardware. It currently reuses the isolated world acceptance harness and a sealed injected Research Receipt provider.

A preflight PASS means the necessary machinery appears present in source. It does **not** award JARVIS-20 points.

This distinction is deliberate. For example:

- proving the permission table says Gmail send requires confirmation is not the same as observing the full live confirmation experience;
- proving the verifier state machine works in an isolated database is not the same as verifying a real Gmail send;
- proving the routing guard forces recommendation requests into audited search is not the same as finding the genuinely best option on the live web;
- no Python test can substitute for real iPhone microphone, Bluetooth, GPS or background-execution behavior.

## Commands

After installing the current source:

```powershell
jarvis-20 plan --compact
```

Run source/integration prerequisites:

```powershell
jarvis-20 preflight --strict
```

Create a new score sheet:

```powershell
jarvis-20 template --seed 2026-09-baseline --output jarvis20-baseline.json
```

Fill each `score`, `evidence`, `notes`, and `instance` field after performing the real test.

Score it:

```powershell
jarvis-20 score jarvis20-baseline.json
```

Score and preserve it in Jarvis evaluation history:

```powershell
jarvis-20 score jarvis20-baseline.json --save
```

Show prior runs:

```powershell
jarvis-20 history
```

Saved runs live under `%APPDATA%\JarvisForMRB\evaluations\jarvis20`.

## What should eventually become automatic

The long-term target is to automate most of the behavioral suite without changing its semantics.

Good candidates for synthetic/digital-twin automation:

- identity continuity;
- persistent objectives;
- situational awareness;
- cross-source contradictions;
- document changes;
- Executive prioritization;
- permission decisions;
- closed-loop verification and failure states;
- research routing, candidate recall, contradiction discovery, calibration and audit fidelity.

Hardware-in-the-loop remains appropriate for:

- real microphone routing and far-field speech capture;
- Ray-Ban reconnect/presence behavior;
- GPS/navigation timing;
- background iOS operation;
- DAT camera behavior.

A future self-improvement loop may optimize against JARVIS-20 variants, but the evaluator, hidden variants, safety/privacy invariants and scoring rules must remain outside the candidate system's write authority.

## Relationship to the fixed endpoint

JARVIS-20 is a progress instrument. It does not create Criterion 13 and does not move the fixed finish line. A high JARVIS-20 score is useful evidence of quality; the existing Definition of Done and deployment/runtime acceptance remain the completion contract.
