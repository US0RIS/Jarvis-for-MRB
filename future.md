# Horus — AirPods-First Focused Roadmap

**Proposals, not shipped features.** The original 1,869-line idea collection is preserved in [the archive](docs/archive/FUTURE_IDEAS_2026_10.md); nothing was discarded. For implementation status, read [Capabilities](docs/CAPABILITIES.md).

**Primary form factor:** AirPods or ordinary Bluetooth headphones + an iPhone; discreet voice/private audio first, with optional phone text and backend computation. **No user-worn camera, smart glasses, POV video stream, spatial HUD or additional physical sensor is required for baseline Horus.** Visual input remains explicitly optional. [Binding full-backlog camera audit and revised requirements](docs/AIRPODS_FIRST_VISION.md).

**Truthfulness:** Camera-free physical knowledge comes from the user's explicitly confirmed descriptions, permitted phone/digital context, or legitimate external sources. Never invent a scene, item location, precise room, visual motion, identity or physical-action verification. AirPods do not grant unrestricted iOS microphone/background access; handle consent, stopped capture, and fallback honestly.

## P0 — Make what exists reliable

- [ ] Prove camera-free AirPods/headset-first interaction: explicit invocation, fast private audio, barge-in/stop, clear microphone state and reliable camera-off fallback.

- [ ] Keep all Python, simulator, installer and security-contract CI checks green.
- [ ] Test Windows installer on a clean PC; verify BYOK, permissions, upgrade/uninstall.
- [ ] Test real two-device Callless audio, disconnect and reconnection.
- [ ] Isolate public Callless infrastructure from personal-host admin APIs.
- [ ] Establish honest release-status terminology and feature owners.
- [ ] Reduce background startup work and nonessential hardware prerequisites.

## P1 — A useful, shippable Horus

- [ ] First-run Windows text chat with BYOK or local inference, no smart glasses.
- [ ] Validate real iPhone Action Button/OS-permitted voice initiation, AirPods/Bluetooth audio, background limits and microphone idle behavior; no assumed always-on recording.
- [ ] Secure updates, device auth, credential rotation and spend ceilings.
- [ ] Explicit opt-in privacy and authority dashboard.
- [ ] Simplify memory, integrations and independent action verification.

## P2 — Callless v1

- [ ] Directional contact grants and timed, group-scoped availability.
- [ ] Calendar Free/Busy overlay without meeting-detail exposure.
- [ ] Decline, wait, leave-message and non-user guest access.
- [ ] Receiver-controlled BYOK/local screener with privacy disclosure and quotas.
- [ ] Native OS-compliant incoming calls, honest delivery states and connection tone.
- [ ] Urgent pushes and independently authorized, audited bypass privileges.
- [ ] TLS hub, TURN, security review and real multi-network acceptance.

See [Callless specification](docs/CALLLESS_DESIGN.md).

## P3 — Future, not v1

- [ ] All-party-consent recording and summaries.
- [ ] Agent-to-agent calling, party lines, mid-call handoff and whisper-in.
- [ ] Metered caller-pays inference and optional phone/SMS.
- [ ] Physical access/door actions only under separate safety authorization.
- [ ] User Belief Model, evidence freshness, proactive assistance.
- [ ] Camera-free spoken place/object memory, world search and optional enrolled radio/sensors; separate opt-in camera/AR/wearable adapters only when independently verified.

## Promotion rule

**Camera-off acceptance:** a core feature must work with no camera, glasses or visual sensor attached to the user, using exact available evidence or an explicit unknown state; genuine visual-only capabilities stay optional and accurately labeled.

A feature moves from "future" only with a named owner, scoped authorization, user-visible permissions, regression tests, real-device evidence when relevant, and a clear disable/revoke path. **Code merged is not proof of product release.**

[Scope and housekeeping](docs/HORUS_HOUSEKEEPING.md) · [Full idea archive](docs/archive/FUTURE_IDEAS_2026_10.md)

[All implementation batches](docs/implementation_batches/README.md) · [480-item traceability](docs/implementation_batches/TRACE.md).
