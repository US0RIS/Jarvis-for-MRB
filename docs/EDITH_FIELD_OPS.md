# Beyond Conductor: EDITH Field Ops — proposed next major build

EDITH's most memorable property is **speech → verified change in the real world**.
Jarvis should get as much of that as technically and safely available, not
pretend that observing a camera confers authority over arbitrary machines,
vehicles, people, weapons or infrastructure. Conductor's workstation mission
and opted-in one-utterance benign app launch are now the first concrete
implementation of this interaction pattern.

## What Jarvis can do now, in source

1. Read authorized personal Calendar/Gmail, local Windows status, and
   supported public/environmental sources; speak source-qualified answers.
2. Opt-in remote private Mac/Windows screen *snapshots*, not universal
   low-latency mouse/keyboard control.
3. Say **"Jarvis, open Safari on my MacBook Air"** (independently enrolled
   low-risk voice class), resulting in an exact one-use workstation action,
   fresh process check and spoken receipt. Screen capture never inherits
   this voice authority.
4. iPhone's separately enrolled reversible Apple Home light automation on
   a real observed arrival or multiple specific doorbell sound labels; local
   HomeKit readback distinguishes intended write from observed characteristic.
   This is on-device/iPhone foreground work with HomeKit permission and exact
   light grants, NOT a general scene/door/garage controller.
5. Real Maps navigation handoff for an exact appointment under Mission
   Control's specific one-use grant and distinct observed arrival proximity;
   not autonomous car control.
6. External, time-bounded watch jobs for specific supported public cameras
   and regional aircraft/earthquake/weather/air models; no global raw CCTV.

## The next *unimplemented* upgrade: Field Ops

A field operator is a bounded adapter for an **actually integrated device
with verifiable effect**. Its registration specifies:
`{device_identity, physical_capabilities, sensor_provenance,
 action_schema, user/grant_scope, safe_limits, state_readback,
 watchdog, emergency_stop, risk_class}`.

First pack: **Safe Home + personal devices.** Enable more of the
authorized user's own HomeKit lights and nonhazardous scenes, supported
personal audio routing, visible travel/navigation handoffs, and workstation
readiness, all through one conversational routing layer. In each case use
Apple/OS-sanctioned APIs and individually inspected scopes. An exact
preauthorized light scene can run on a direct spoken request and be
verified by readback. Context-derived/bystander speech is *not* an
actuation request.

Second pack: **Remote observability as actions.** "Watch that public
junction for congestion", "tell me whether traffic at the pass changed",
"show the official camera nearest this published point"—only where a
documented official provider and true refresh mechanism exist. A model
can interpret an observation; it cannot invent camera access, global
real-time coverage or permission to move a camera.

Third pack: **Bounded personal robotics.** Reuse the user's demonstrated
Mac → USB controller → simple servo prototype as a carefully scoped,
nonprojectile positioning/test rig **only after** a separate physical
hardware test, rate/angular limits, accessible physical kill switch,
no autonomous target following, and a watchdog that returns to a safe
state on disconnection. A prototype servo moving does not establish
safe remote manipulation or authorize launching anything.

## Risk ladder and human authority

- **Observation:** many sources can be voice-invoked, with privacy scopes
  and provenance. No proof of coverage from provider names.
- **Low-risk reversible:** precise registered app opens, user-authorized
  light scene, user-opened website/directions. Opt-in bounded voice grants,
  independent readback and repeat limits.
- **Consequential:** external messages, payments, purchases, file sharing,
  deleting data, locks, garage doors, vehicle control, persistent recordings,
  motion of heavy devices. Require inspectable exact targets, distinct
  on-device user confirmation, policy enforcement and independent
  verification; some require additional physical presence/OS support.
- **Hazardous or coercive:** weapons, targeting/firing projectiles, unsafe
  machinery, harassing/tracking private people. No ambient-spoken command,
  model plan, untrusted camera label or vague remembered intent can authorize
  force. Software limitations alone cannot make such a system safe.

`hear → parse → resolve exact target → inspect live capabilities →
 authorize for risk → reserve effect → execute via supported adapter →
 verify independent new state → report what happened` is the operational
 loop. EDITH's feeling comes from eliminating device-specific UI **where
 consent can be safely predelegated**, not skipping the checks that separate
 "my light came on" from "Jarvis said it came on."

## Release definition

The next milestone is a **single iPhone voice request to a preauthorized
nonhazardous personal physical device**, routed through one typed Field Ops
registry; include real HomeKit readback, stop controls, source timestamps,
rate limits, ambient/bystander rejection and failure receipts. Do not
claim it deployed until it works on the user's actual HomeKit accessories
and on-device voice path. The current Mac/Windows workstation pack is a
separate concrete precursor, not completion of Field Ops.
