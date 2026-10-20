# Jarvis Fixed Endpoint Acceptance Contract

This file is the non-moving definition of done for the Jarvis integration project.

It exists specifically to prevent the finish line from expanding merely because another useful feature can be imagined. Once the twelve criteria below are satisfied in source and then verified on the deployed PC/iPhone system, the defined project is complete. Future models, applications, wearables, tools, UI improvements, and specialist features are enhancements after completion; they are not additional completion criteria.

## Two phases of completion

There are deliberately two separate gates:

1. **Source-complete** — architecture, implementation, migrations, diagnostics, regression tests, and the isolated end-to-end acceptance harness are present in the repository.
2. **Runtime-verified** — the source has been pulled onto the home PC, dependencies installed, migrations/preparation completed, the regression and acceptance suites executed, backend runtime exercised, and the iPhone companion built/run on a real device.

A source commit is never represented as runtime verification.

## The twelve fixed criteria

### 1. Persistent world model

Jarvis maintains durable entities, external identities, aliases, events, beliefs, commitments, goals/intentions, relationships, documents, places, objects, meetings, operational state, action receipts, and evidence provenance across sessions.

Acceptance requires that this information is durable structured state rather than ephemeral prompt text.

### 2. Identity continuity

The same real-world person, project, document, place, object, meeting, or other entity resolves to a stable underlying identity across supported sources.

The canonical benchmark is Daniel Reed appearing through an explicitly enrolled iPhone Known People record, a Gmail address, a Calendar attendee, document provenance, commitments, and conversation. Those observations must converge without collapsing conflicting strong identities.

### 3. Persistent intentions

Explicit goals remain active across sessions until they are completed, retired, or superseded.

Goals may enter through explicit goal state or explicit conversational declarations such as "We're trying to get Project Apollo signed by Friday." Ambient observations, hypotheticals, questions, and ordinary transient wants must not silently become durable objectives.

### 4. Situational awareness

Jarvis can compile the context that matters to a current or imminent situation rather than merely retrieve disconnected records.

The benchmark question is:

> Anything I need to know before I go in?

For an imminent Apollo meeting, Jarvis should identify the meeting, participants, connected project, active objective, pending obligations, and relevant recent evidence.

### 5. Cross-source reasoning

Jarvis connects facts across conversation, meetings, Calendar, Gmail, attachments, local notes, iPhone context, and other supported private sources while preserving source provenance and uncertainty.

It must be able to detect a discrepancy such as:

- yesterday's discussion: indemnity cap = 10%;
- newer draft: indemnity cap = 15%.

The result is a provenance-bearing possible change/conflict. Jarvis does not silently declare which source is legally or factually authoritative.

### 6. Executive Loop

An active intention has an evolving operational state containing, where available:

- objective;
- deadline;
- blockers;
- dependencies;
- Waiting-On items;
- recent material changes;
- ordered next actions;
- current decision;
- an executable proposal when an allowed tool can implement the decision.

Priority is deterministic around high-risk structured conditions. A substantive project-term conflict outranks an ordinary document change; failed outcome verification outranks the original plan.

No Executive decision bypasses the normal permission system.

### 7. Closed-loop action verification

Tool success is evidence of an attempt, not proof of the intended outcome.

The required causal loop is:

`intention -> decision -> action attempt -> expected outcome -> independent observation -> verified/failed/timed_out/unverified -> updated Executive state`

Writes remain unresolved until independently observed when a verifier exists. Actions without an independent observer remain explicitly unverified. Failed or timed-out outcomes re-enter Executive attention.

### 8. Appropriate proactivity

Jarvis may surface information without being asked when a deterministic, evidence-backed condition materially affects an active intention or imminent situation.

The canonical Apollo prebrief should prioritize facts such as:

- the 10%/15% term discrepancy;
- Daniel still owing the revised disclosure schedules.

The system must suppress irrelevant active goals and avoid generic alert spam when there is no actionable connected context.

### 9. Privacy and authority boundaries

The world model and action system preserve explicit trust boundaries:

- read actions may run automatically under the default policy;
- local writes may run automatically under the default policy;
- external writes require confirmation;
- destructive actions require confirmation;
- security-class actions require confirmation;
- no LLM decision can promote itself into a higher authority class.

Known People synchronization is metadata-only. Raw biometric feature prints, raw camera frames, rolling microphone buffers, clipboard contents, incident media, and privacy-zone coordinates are excluded from the world snapshot contract.

Removing a Known Person revokes the face-enrollment identity and enrollment-specific private metadata. It does not silently erase independent Gmail/Calendar/history evidence about the same person. A global forget operation would be a distinct destructive privacy action.

### 10. Unified interaction

The glasses, iPhone, PC, voice interface, background services, private data sources, and tools operate over one Jarvis world rather than separate assistant memories.

The acceptance benchmark uses one Apollo objective fed by multiple channels:

- iPhone Waiting-On state;
- conversational intention and discussion evidence;
- Gmail-style documents;
- Calendar participant context;
- Executive state;
- action verification.

The resulting project/intention is one connected operational state.

### 11. Operational reliability

The architecture is safe to upgrade and inspect. The fixed reliability requirements include:

- versioned world-model migrations;
- pre-upgrade SQLite backup;
- bounded backup retention;
- WAL mode for the shared world database;
- fail-fast startup when the declared schema is structurally invalid;
- migration history;
- SQLite integrity and foreign-key checks;
- evidence-count consistency;
- no current derived relationship without evidence;
- conservative person/project linking;
- partial-snapshot reconciliation safety;
- chronology based on source occurrence time rather than insertion order;
- RFC email-date support;
- document-lineage chronology repair;
- term-conflict chronology repair;
- privacy-boundary diagnostics;
- verification-state diagnostics;
- Executive-decision uniqueness checks;
- runtime subsystem failure isolation/health telemetry;
- deterministic deployment preparation;
- rollback documentation;
- regression coverage.

### 12. End-to-end demonstrations

Several integrated paths must behave correctly without manual database stitching. The canonical synthetic acceptance scenario is Project Apollo.

The full Apollo chain is:

1. iPhone knows Daniel Reed and records that the user is waiting on revised disclosure schedules.
2. Gmail identity `daniel@example.com` resolves to the same Daniel entity.
3. The user says, "We're trying to get Project Apollo signed by Friday."
4. Jarvis persists the objective and links it to Project Apollo.
5. Conversation evidence records an indemnity cap of 10%.
6. An earlier Apollo agreement draft also contains 10%.
7. A newer revision contains 15%.
8. Document lineage recognizes the revision and the numeric change.
9. The term ledger records a provenance-bearing 10%/15% discrepancy while treating the 15% observation as chronologically latest.
10. Calendar contains an imminent Project Apollo signing call with Daniel as an attendee.
11. Situation compilation links the meeting, Daniel, Apollo, the objective, the overdue schedules, and the term discrepancy.
12. The proactive prebrief surfaces the material discrepancy and overdue dependency.
13. The Executive Loop marks the objective at risk and prioritizes resolving/gathering evidence for the term discrepancy.
14. A simulated external follow-up action is recorded as attempted but not complete.
15. The verification ledger keeps it pending until an independent observer reports the expected state.
16. Independent observation marks the outcome verified and records verification evidence.
17. Known People unenrollment removes Daniel's iPhone face identity/private enrollment note while preserving his independent Gmail identity and connected history.
18. A negative sentence such as "Alex Example is not on Project Apollo" does not create a durable Alex-to-Apollo association.
19. A malformed/partial iPhone snapshot cannot mass-retire authoritative state.
20. An unrelated dinner question does not receive Apollo Executive context.
21. Final diagnostics report no structural reliability problems.

## Source acceptance command

After installing the package, run:

```powershell
jarvis-world-acceptance
```

The command creates a temporary isolated world database, uses no external services, and does not modify deployed user data. It emits a JSON report with every check mapped to one of the twelve fixed criteria and exits non-zero if any required check fails.

The same scenario is locked into the regression suite through `tests/test_world_acceptance.py`, which executes the acceptance command in a fresh Python interpreter with an isolated `APPDATA` directory.

## Deployment verification sequence

Once the source passes are complete and the home PC is available, the intended sequence is:

```powershell
git pull
python -m pip install -e .
jarvis-world-prepare
python -m unittest discover -s tests -v
jarvis-world-acceptance
jarvis-world-check
```

Then restart the Jarvis backend and exercise the actual backend/tool/provider paths. Finally build and run the iPhone companion and verify phone-to-PC world synchronization, Ray-Ban transport/perception paths available to the current iOS build, privacy controls, and representative voice interactions.

## Completion rule

The project reaches the defined endpoint when:

- all twelve criteria are implemented;
- the source regression/acceptance suites pass;
- `jarvis-world-check` reports no structural problems;
- deployed backend behavior is verified on the home PC;
- the iPhone build/runtime behavior is verified on-device;
- the fixed end-to-end scenarios behave correctly without manual intervention.

At that point, discovering another useful feature does **not** reopen this definition of done. It becomes post-completion enhancement work.
