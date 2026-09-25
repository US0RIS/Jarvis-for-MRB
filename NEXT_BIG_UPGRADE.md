# Historical Conductor design — v1 implemented, Field Ops next

**Source implementation status:** Conductor's exact-device workstation pack, independently opted-in fixed one-app voice path, hashed short-lived one-use grants, reservations before side effects, backend step ledger, separate observed process verification, optional iPad screen view and explicit revoke are implemented on `jarvis/memomind-prep`. See **[CONDUCTOR.md](CONDUCTOR.md)** for the authoritative executable v1 contract and real-device release limitations. This document preserves the earlier vision; its more general device-bound cryptographic approvals and multi-device workflows are **not** implemented. The next selected, **not yet implemented**, major upgrade is **[EDITH Field Ops](EDITH_FIELD_OPS.md)**.


**Decision:** The next major development cycle is **Conductor**, a single cross-device,
evidence-verified mission executor over the already built Reality Mesh and Mission
Control. This section records the initial engineering direction; the narrow first
workstation pack is now implemented in source, but a generalized executor
is **not** deployed.

## Why not another isolated integration?

At the current source checkpoint the user can create a narrowly scoped
appointment mission, recheck provider observations, open consented directions,
inspect several explicitly paired devices, view a real opt-in remote desktop
snapshot, request one of a few precisely registered app launches, and enroll
limited time-bounded public watches. Those work **alongside** each other, not
as one coherent, inspectable workflow. Another camera, model or gesture layer
would add inputs but not close that gap.

Conductor's defining change: a user supplies an outcome, and Jarvis may
**coordinate exactly authorized steps on multiple devices and verify effects
independently**, recovering from offline nodes without inventing success.
Permission is bound to **mission + exact device + exact action + exact arguments
+ duration + execution count**. Neither an inferred user intent nor an LLM
plan can silently enlarge the authority.

## First end-to-end mission: "Prepare my workstation"

This is an intentionally narrow demonstrator, not universal desktop control.
On the iPad, the user chooses the exact paired Windows PC or Mac and exact
registered applications; Jarvis checks live node identity, state, and
capabilities, requests an explicit one-use grant for each chosen app, performs
bounded launch actions, observes independent running-process evidence, and
routes an opt-in view-only desktop snapshot back to the iPad. A failed launch
or missing screenshot ends in a **blocked/unknown** state and a specific
user-facing next step, not a success summary. No unlocking a machine,
background remote-input injection, destructive close, shell, protected
data extraction, blind retry or third-party send.

Success is **not** "OS launch returned zero." It requires the selected
applications to be observed running by a newer source observation and the
user-requested remote view to be available at its checked time. Neither
running-process observation nor a screenshot proves application window focus;
do not promise that without an actual allowed focus verifier.

## Core implementation

1. **Typed mission definition:** exact desired state, target node IDs,
   approver, expiry, allowed app names, and device-only/private source scopes.
2. **Capability broker:** a live node/sensor graph distinguishes defined
   contract, configured, presently online, separately opted in, mission-granted,
   and observed successful. Server-readable bearer possession alone is **not**
   evidence of a physical phone tap; add device-bound signed approvals where
   high-trust actions require them.
3. **Causal step runner:** durable idempotency IDs, once-only action reservations
   before side effects, reason-coded rejections, explicit unknown results and
   no automatic retry after ambiguous outcomes.
4. **Source-linked verifier:** compare post-action evidence timestamp and
   target identity against pre-action observations. Keep original evidence and
   show a concise source/time/result chain on the iPad.
5. **Continuity bus:** route mission updates to phone/iPad/approved glasses
   UI even if a node goes offline. Delivery/visibility are not proof of
   physical effect. Backends must not assume background iOS execution.
6. **Adversarial acceptance:** wrong node, spoofed online status, stale
   screenshots, expired/replayed grants, revoked permission, offline during
   action, restarted Windows service, conflicting same-name processes,
   unverified focus, secrets in logs and accidental permission inheritance.

## Expansion order

After workstation missions pass real Windows/Mac/iPad acceptance, extend to
**travel disruption response** across exact calendar trip + airline/official
status + public movement/weather signals with explicit source coverage, then
**time-bounded remote situation watches** (regional cameras/aircraft/weather).
AIS ship tracking, global public camera catalogs, real-time remote desktop
input, OS-native file dragging, and MemoMind hardware must only enter after
genuine provider/protocol/SDK access and a concrete scoped-action gate.
Do not label these next packs deployed in README or the app.

## Release gate

Reality Mesh must first pass latest-head Python and iOS CI and independent
actual iPad + interactive Windows + each Mac's private Tailscale, screen
permission, app startup opt-in, expiry/revoke and no secret leakage checks.
Then Conductor ships only when the workstation mission actually performs
an authorized cross-node action and shows a subsequent independent,
source-timestamped state observation on the intended device.
