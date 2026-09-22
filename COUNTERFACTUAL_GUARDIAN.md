# Next capability: Counterfactual Guardian — notice what has *not* happened yet

**Status:** design for the next milestone, not a deployed prediction engine. The camera-free Ambient Opportunity Loop in this branch is the implementation substrate; the system described below is future scope.

## The conceptual leap

Today Jarvis responds to an event ("we got home", "the doorbell may have rung", "the modelled temperature dropped") and matches it to a user-enrolled standing objective. The next step is *negative-space agency*: Jarvis should know an event was expected, notice when current evidence contradicts the expected trajectory, compare possible interventions, and act within the user's existing authority envelope **before** the failure occurs.

This is not surveillance omniscience. Without a fresh observation, Jarvis must distinguish "not observed" from "did not happen." Counterfactuals are grounded in time, GPS, calendar, motion, microphone sound labels, public providers, user declarations and verified device state. Camera input is optional and never required.

The cinematic move is not "run a thousand automations". It is "preserve the user's goal using an unexpected but authorized affordance as circumstances change."

## Concrete first slice: don't miss the appointment

A calendar event begins at 3:00. It has a place. At 2:32, the phone has a fresh location fix and the user is still at a different location. A real MapKit route estimate now says 37 minutes. Jarvis compares the observed *remaining time* to the provider's ETA, not straight-line distance or an LLM's imagined travel time. It can say, conversationally: "The meeting starts in 28 minutes and the drive is currently estimated at 37. I'd leave now; I can start directions. Sending an ETA to anyone would need your authorization."

With a separately enrolled, time-limited scope, starting the route might become an allowed low-risk autonomous action. Drafting the late message can happen locally; sending it requires exact-recipient approval. If the phone has no fresh GPS, calendar access fails, a remote URL is unreachable, or iOS suspended Jarvis, no confident "you're late" assertion is generated.

An important variant: the expectation is not merely "arrive by 3." It's "leave in time to arrive by 3." Recognize impending trajectory failures even before the expected deadline.

## Shared runtime contracts

1. **Observation ledger:** `source, signal_type, observed_at, received_at, confidence, TTL, consent_scope`. Sound labels are not speech commands. The absence of a doorbell label is not evidence no one arrived. Health metrics are optional, read-only context, never inferred diagnoses.
2. **Expectation ledger:** human-entered or explicitly approved goal, latest acceptable time, measurable condition, evidence quality and owner. A model may *suggest* an expectation but cannot silently enroll one.
3. **Mismatch detector:** bounded deterministic checks for observed trajectory against the expected state. No probabilistic bluffing when a route, public feed or observation is missing.
4. **Affordance registry:** per-actual-device/app/tool action schema, reversible flag, risk class, exact target/recipient, proof of authorization, TTL, maximum frequency, fresh verification method. Model output cannot add actuators or broaden permissions.
5. **Intervention broker:** propose multiple grounded paths: say something, stage a draft, launch navigation, preapproved lighting, defer nonurgent chatter, or seek approval. Compare intrusiveness and reversibility, not cinematic theatrics. Protected/irreversible actions stay confirmation-bound.
6. **Outcome receipts:** action attempted vs tool accepted vs independently verified state, timestamp, rollback eligibility and observed next state. A failed readback never becomes "done."
7. **Calibration:** after an observed success/failure or user dismissal, adjust future interruption timing and false-positive controls. Never learn blanket permission from repeated unapproved suggestions.

## Why it is materially different from IFTTT

IFTTT implements "if X then Y" when X happens. The Guardian asks what X *should have looked like by now*, whether an objective will still be reachable if nothing changes, and whether an **already-allowed different action** could rescue it. Crucially, this does not require eyes or even a pair of glasses: iPhone sensors, Apple Watch (where independently authorized), calendar, public conditions and controllable apps/devices form a fragmented but useful physical operating system.

A second example: an explicitly enrolled daily check says the garage should be shut by bedtime. If, and only if, a real authorized HomeKit accessory reports it still open, Jarvis could flag the discrepancy. It must not presume a garage-door sensor/control exists; and closing a garage door would require a separately reviewed safety policy and verification, unlike the current light-only proof of concept.

## Suggested implementation order

1. Ship and physically test current iPhone acoustic + geofence + HomeKit light loop, including launch/relaunch, denied permissions, app suspension, mixed Bluetooth routes, rebound geofences, false doorbells and failed readback.
2. Build a metadata-only read-only `expectation_evaluator` using already-authorized calendar queries + fresh opt-in phone location + actual MapKit route ETA, with a detailed reason/evidence card and no writes.
3. Add typed, revocable `affordance_grants`: first navigation, local draft and enrolled lights; no generic HomeKit, arbitrary HTTP or iOS Shortcuts invocation.
4. Stage alternatives and verify outcomes. Measure prevented misses, false alarms per week, intervention utility, latency, and false claims of execution.
5. Only then consider model-generated intervention hypotheses. A language model can expand *possibilities*, never evidence, authorization or physical capabilities.

**Acceptance criterion:** for a reproducible missed-appointment trajectory with valid sources, Jarvis issues one useful, timely, concise warning with provenance; a dry-run shows the permitted intervention set; navigation opens only with a grant/approval; third-party communication cannot be sent by inference; no-camera and no-glasses operation passes end-to-end.
