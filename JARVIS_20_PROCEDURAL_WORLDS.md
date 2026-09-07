# JARVIS-20 Procedural Worlds

This document describes the procedural scenario layer for JARVIS-20. It does not change the fixed 20 behavioral tests and it does not add a new Definition-of-Done criterion.

The purpose is to prevent benchmark memorization while making repeated evaluation reproducible.

## Core rule

The **capability being tested stays fixed**. The concrete people, projects, terms, values, deadlines, distractors and wording change.

A scenario is generated from:

- a caller-supplied seed;
- an anchor timestamp;
- the frozen JARVIS-20 test definitions.

The result contains a public scenario and, optionally, a separate hidden oracle.

## Public scenario versus hidden oracle

The public scenario contains the material needed to execute the test:

- generated project;
- primary and distractor people;
- non-deliverable `example.test` email identities;
- objective;
- Waiting-On item;
- imminent meeting;
- older/newer document evidence;
- benign document edits around one material change;
- explicit negative person/project statement;
- generated prompts/setup for all 20 JARVIS-20 tests;
- pre-populated score sheet.

The hidden oracle contains the expected state:

- which identity must resolve across sources;
- which identities must not merge;
- current and conflicting term values;
- material document-change tokens;
- expected situation-context facts;
- priority expectations;
- generated arithmetic answer;
- room-audio phrase;
- permission and verification invariants.

The public file contains only a SHA-256 commitment to the oracle. The system under test should not receive the oracle file.

This matters for future recursive improvement: a candidate Jarvis build can see the task but not the answer key.

## Generate a scenario

After installing the current source:

```powershell
jarvis-20 generate `
  --seed baseline-001 `
  --output .\j20-baseline-001.json `
  --oracle-output .\j20-baseline-001.oracle.json `
  --score-output .\j20-baseline-001.score.json
```

The command reports the scenario ID and the committed oracle hash.

For an exactly reproducible generated artifact, also provide an anchor:

```powershell
jarvis-20 generate `
  --seed regression-001 `
  --anchor 2031-04-05T15:30:00Z `
  --output .\j20-regression-001.json `
  --oracle-output .\j20-regression-001.oracle.json `
  --score-output .\j20-regression-001.score.json
```

Same seed + same anchor produces the same scenario, including the populated score sheet.

## Validate tamper integrity

```powershell
jarvis-20 validate-variant .\j20-regression-001.json `
  --oracle .\j20-regression-001.oracle.json
```

Validation checks:

- exactly tests 1-20 are present and ordered;
- scenario ID exists;
- public oracle commitment exists;
- oracle content hashes to the committed value;
- oracle records the hash of the public scenario.

Changing either file after generation causes validation to fail.

## Isolated procedural world preflight

Tests 5-10 can already be materialized into a temporary world-model database:

```powershell
jarvis-20 world-preflight `
  .\j20-regression-001.json `
  .\j20-regression-001.oracle.json `
  --strict
```

The world lab creates no external side effects. It does not touch the user's deployed world and does not call Gmail, Calendar, live web services or hardware.

It currently exercises these generated-world prerequisites:

- **5 — Identity continuity:** Known People, Gmail identity and Calendar attendee must resolve to one primary person; distractors must remain separate; an explicit negative person/project statement must not create a current association.
- **6 — Persistent objective:** generated explicit objective must become an active persistent intention.
- **7 — Situational awareness:** a generic pre-meeting query must recover the generated project, relevant person and overdue Waiting-On dependency.
- **8 — Cross-source contradiction:** the newer generated term must be current while the older conflicting value remains provenance-bearing.
- **9 — Document change detection:** the version lineage must expose both old and new material values despite benign surrounding edits.
- **10 — Executive judgment:** the generated objective must become at-risk with a substantive term conflict and overdue dependency ahead of low-value distractors.

This command is a **preflight**, not a behavioral score. It proves the underlying world machinery can survive randomized fixtures. It does not prove the actual conversational/device experience deserves 2/3 or 3/3.

## Temporal replay

A scenario can be replayed long after it was generated.

The public artifact keeps its original timestamps for integrity and diagnosis. When the isolated world lab materializes it, the synthetic timeline is rebased to the current time while preserving each relative offset from the scenario anchor.

Example:

- generated meeting = anchor + 25 minutes;
- generated Waiting-On due time = anchor - 5 hours;
- generated old document = anchor - 4 hours;
- generated new document = anchor - 1 hour.

If replayed six months later, those become:

- now + 25 minutes;
- now - 5 hours;
- now - 4 hours;
- now - 1 hour.

That keeps "imminent", "overdue" and chronology behavior stable without rewriting the committed scenario files.

## Privacy behavior

The generator intentionally does not create realistic private addresses or deliverable external recipients.

Generated email addresses use the reserved-like test domain pattern `example.test`. Real navigation addresses, live-web research topics and real external-write targets are supplied by the evaluator at execution time.

The public bundle marks which tests require evaluator-supplied safe values.

## What varies today

The generator currently varies:

- person names;
- email aliases;
- distractor identities;
- project names;
- meeting types;
- Waiting-On obligations;
- objective deadlines;
- meeting proximity;
- overdue age;
- document noise edits;
- material term type;
- old/new term values;
- simple arithmetic instance;
- context-switch topics;
- harmless Notecard test fact;
- room-audio phrase;
- short and genuine-absence reconnect timing.

Supported generated material-term families match Jarvis's current deterministic term ledger:

- indemnity cap;
- escrow amount;
- termination fee;
- survival period;
- working capital target.

## What remains intentionally live/manual

Some JARVIS-20 tests should not be faked by this generator:

- real Home navigation;
- current public lookup;
- live rigorous recommendation;
- live long-tail discovery;
- live research adversary;
- real uncertainty/calibration pressure;
- protected external writes;
- independent verification against a real provider;
- fault-injected provider failure;
- room microphone routing;
- Ray-Ban presence/reconnect behavior.

Those remain actual behavioral tests. Later, some can gain additional sealed or hardware-in-the-loop variants, but the real-world score should remain distinct from synthetic preflight.

## Why this matters for recursive improvement

A future improvement agent can receive:

1. public procedural scenario;
2. its own execution trace;
3. aggregate pass/fail or score feedback.

It should **not** receive:

- the hidden oracle before execution;
- hidden holdout scenarios;
- evaluator implementation write access;
- permission/privacy invariants write access.

That gives Jarvis something meaningful to optimize against without turning the benchmark into a hard-coded answer sheet.
