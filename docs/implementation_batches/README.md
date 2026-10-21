# One-prompt implementation queue

This plan covers **all 480** original bullet/numbered entries in [the full archived backlog](../archive/FUTURE_IDEAS_2026_10.md). The [trace](TRACE.md) maps every one to exactly one phase packet. **Source items are not necessarily 480 independent features:** some are research projects, library candidates, named architectural principles, or test cases.

**Binding form-factor rule:** [AirPods-first camera-dependency audit](../AIRPODS_FIRST_VISION.md) governs all packets: assume ordinary headphones and phone, no user-mounted camera. Reframe legacy HUD/AR/scene/visual-memory requirements for nonvisual sources first; condition visual-only functions on explicitly available authorized imagery. The immutable 480-entry archive and trace remain history, not an excuse to impose glasses or new sensors.

## The prompt to use

> Implement **[packet ID]** from `docs/implementation_batches/[phase file].md` directly on `main`. Read the linked original passages **and the AirPods-first audit**, not only the titles. Work **only on this packet** (up to three small targets, or one complex first vertical slice). Inspect existing implementations first and reuse working infrastructure. Add realistic automated tests, failure/permission paths, migration protection, and necessary documentation. Run relevant CI checks and report any hardware, paid-provider, or deployment checks you cannot perform. Update the capabilities ledger with verified status; never claim source code is device-tested or shipped without evidence. Never delete/disable failing tests just to make CI green.

One prompt specifies **one bounded engineering task**. It may need multiple tool calls or a follow-up for external hardware; three huge systems are not magically one-turn production work. For open-source candidates, **evaluate and benchmark** rather than installing all of them. For acceptance criteria, write tests, not fake empty implementations.

## Recommended queue: active 47-line roadmap

These **9** packets cover every active roadmap checkbox. They take priority over speculative backlog work, and deliberately overlap corresponding historical ideas.

### R01 — P0 — Make what exists reliable

- [ ] Keep all Python, simulator, installer and security-contract CI checks green. ([roadmap L7](../../future.md#L7))
- [ ] Test Windows installer on a clean PC; verify BYOK, permissions, upgrade/uninstall. ([roadmap L8](../../future.md#L8))
- [ ] Test real two-device Callless audio, disconnect and reconnection. ([roadmap L9](../../future.md#L9))

### R02 — P0 — Make what exists reliable

- [ ] Isolate public Callless infrastructure from personal-host admin APIs. ([roadmap L10](../../future.md#L10))
- [ ] Establish honest release-status terminology and feature owners. ([roadmap L11](../../future.md#L11))
- [ ] Reduce background startup work and nonessential hardware prerequisites. ([roadmap L12](../../future.md#L12))

### R03 — P1 — A useful, shippable Horus

- [ ] First-run Windows text chat with BYOK or local inference, no smart glasses. ([roadmap L16](../../future.md#L16))
- [ ] Validate iPhone Action Button, AirPods routing and microphone idle behavior. ([roadmap L17](../../future.md#L17))
- [ ] Secure updates, device auth, credential rotation and spend ceilings. ([roadmap L18](../../future.md#L18))

### R04 — P1 — A useful, shippable Horus

- [ ] Explicit opt-in privacy and authority dashboard. ([roadmap L19](../../future.md#L19))
- [ ] Simplify memory, integrations and independent action verification. ([roadmap L20](../../future.md#L20))

### R05 — P2 — Callless v1

- [ ] Directional contact grants and timed, group-scoped availability. ([roadmap L24](../../future.md#L24))
- [ ] Calendar Free/Busy overlay without meeting-detail exposure. ([roadmap L25](../../future.md#L25))
- [ ] Decline, wait, leave-message and non-user guest access. ([roadmap L26](../../future.md#L26))

### R06 — P2 — Callless v1

- [ ] Receiver-controlled BYOK/local screener with privacy disclosure and quotas. ([roadmap L27](../../future.md#L27))
- [ ] Native OS-compliant incoming calls, honest delivery states and connection tone. ([roadmap L28](../../future.md#L28))
- [ ] Urgent pushes and independently authorized, audited bypass privileges. ([roadmap L29](../../future.md#L29))

### R07 — P2 — Callless v1

- [ ] TLS hub, TURN, security review and real multi-network acceptance. ([roadmap L30](../../future.md#L30))

### R08 — P3 — Future, not v1

- [ ] All-party-consent recording and summaries. ([roadmap L36](../../future.md#L36))
- [ ] Agent-to-agent calling, party lines, mid-call handoff and whisper-in. ([roadmap L37](../../future.md#L37))
- [ ] Metered caller-pays inference and optional phone/SMS. ([roadmap L38](../../future.md#L38))

### R09 — P3 — Future, not v1

- [ ] Physical access/door actions only under separate safety authorization. ([roadmap L39](../../future.md#L39))
- [ ] User Belief Model, evidence freshness, proactive assistance. ([roadmap L40](../../future.md#L40))
- [ ] Optional spatial, radio, vision and wearable interfaces. ([roadmap L41](../../future.md#L41))

## Full historic-idea backlog by dependency area

1. [Architecture, reliability and core state](01_FOUNDATIONS.md)
2. [User experience, accessibility and device continuity](02_INTERFACES.md)
3. [Personal data, admin and memory](03_MEMORY.md)
4. [Evidence, verification and research](04_EVIDENCE.md)
5. [Proactivity, automation and execution](05_AUTOMATION.md)
6. [Physical world and spatial awareness](06_PHYSICAL_WORLD.md)
7. [Security and emergency-policy design](07_SECURITY.md)
8. [Speech, audio and ambient interaction](08_VOICE.md)
9. [External frameworks and model experiments](09_EVALUATIONS.md)

## Non-bullet specifications that must remain in scope

The bullet-level batches reference their **entire original sections**, including prose. In particular: [User Belief Model](../archive/FUTURE_IDEAS_2026_10.md#L1461), [Epistemic Freshness Gate](../archive/FUTURE_IDEAS_2026_10.md#L1526), [Identity Resolver](../archive/FUTURE_IDEAS_2026_10.md#L1688), [Ambient Commentary](../archive/FUTURE_IDEAS_2026_10.md#L1831), and [emergency ethics](../archive/FUTURE_IDEAS_2026_10.md#L833). The backlog is a specification, not an authorization to bypass a device, another person, privacy law, or a user-granted permission.

**Progress:** mark each packet not started, merged, CI-passed, physically verified, or released in the capability ledger. Keep the archived original intact for audit.
