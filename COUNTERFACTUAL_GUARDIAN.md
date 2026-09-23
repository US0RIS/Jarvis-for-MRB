# Next capability: Counterfactual Guardian — notice what has *not* happened yet

**Status:** first operational slice implemented in source on `jarvis/memomind-prep`: opt-in local iPhone calendar-route anticipation, genuine Apple MapKit route estimates, evidence cards, explicit event-scoped one-use Maps grants, local unsent ETA drafts, and Keychain-protected handoff receipts. This is not yet a general future-state prediction engine and has not been validated on a physical phone or vendor glasses.

## The conceptual leap

Today Jarvis responds to an event ("we got home", "the doorbell may have rung", "the modelled temperature dropped") and matches it to a user-enrolled standing objective. The next step is *negative-space agency*: Jarvis should know an event was expected, notice when current evidence contradicts the expected trajectory, compare possible interventions, and act within the user's existing authority envelope **before** the failure occurs.

This is not surveillance omniscience. Without a fresh observation, Jarvis must distinguish "not observed" from "did not happen." Counterfactuals are grounded in time, GPS, calendar, motion, microphone sound labels, public providers, user declarations and verified device state. Camera input is optional and never required.

The cinematic move is not "run a thousand automations". It is "preserve the user's goal using an unexpected but authorized affordance as circumstances change."

## Implemented activation and evidence contract

In the iPhone app open **Physical → JARVIS • Counterfactual Guardian**. Enable **Guard upcoming calendar departures** (off by default) and opt into **Motion / travel context and GPS**. The controller only runs while the app is foregrounded, polls at most once per two minutes, and allows a separate explicit **Check next departures now** button.

The Windows backend serves `GET /guardian/calendar` through the existing bearer-token authorization and primary Google Calendar credentials. Its read-only response contains up to twelve upcoming timed calendar events with literal locations and a server timestamp; it rejects missing permissions/unavailable calendars instead of returning a fabricated empty agenda. The iPhone independently requires a fresh location fix, its reported horizontal accuracy, a timed event within the next two hours, a uniquely resolved MapKit destination, and a live route estimate. Up to the first three usable upcoming appointments are checked per pass. A five-minute departure buffer is explicit, not a claim about traffic-prediction accuracy. All-day and virtual events are excluded. Map ambiguity, stale GPS, missing backend access and route failures do not become confident predictions.

The Guardian shows a source- and time-labelled warning for supported impending departure risks, deduplicates events within the current session, and avoids speaking when driving, in meetings, or in active conversations. A HUD card is redacted by default. The GPS fix, route destination and calendar content used for matching stay on the phone; the backend does not receive a new location history from Guardian.

**Interventions:** a visible **Start directions** control opens Apple Maps only after the user taps it. The user may separately **Allow one automatic Maps launch**, bound to the calendar event ID, its exact start and location, expiring by the start time or after two hours. An auto handoff consumes the authorization *before* attempting to open Maps and is vetoed for stale observations, app suspension, driving, active meetings or another active Jarvis route. The receipt reports whether Apple Maps accepted the handoff, **not** whether the trip started or arrival was achieved. **Prepare local ETA message** stages text in the iPhone only; copying it is a distinct tap, and no message/recipient is sent or selected. Event dismissals revoke that event's grant. Grants, dismissals and bounded handoff receipts are device-only Keychain records; the user can clear receipts.

**Current scope:** driving-route calendar departure protection, not unsupervised general objective inference, calendar modifications, email transmission, arbitrary device control or clinical health intervention. Do not describe this as physically accepted until it has been installed and validated on the actual phone.

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
