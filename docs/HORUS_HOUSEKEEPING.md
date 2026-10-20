# Horus scope control and housekeeping plan

**Status:** Follow-on work plan; not a claim that cleanup has occurred  
**Date:** 2026-10-19  
**Related:** [Callless design](CALLLESS_DESIGN.md) · [Current shipping guide](SHIPPING.md)

## Why this document exists

Horus expanded from Meta-Ray-Bans-centric personal assistance into Windows distribution, iPhone/AirPods, BYOK inference, Callless communications, ambient/context systems and numerous research/World Armor features. Adding everything to the same startup, main API file, frontend Settings view and giant README will make future development and shipping less reliable. The solution is **not** to delete capabilities or perform a sweeping rename; it is to freeze contracts, identify ownership, and move optional features behind tested boundaries.

As inspected on 2026-10-19, the repository has roughly 377 tracked paths and a README exceeding 3,400 lines. The 0.14 Windows installer and iOS simulator builds are separate from end-to-end device acceptance. The whole CI suite has pre-existing failing World Armor push tests. Treat this as an honest baseline; do not turn a red test suite green by simply removing coverage.

## First principle: three independently deployable products

| Surface | Primary responsibility | What it must **not** own |
|---|---|---|
| **Horus Core** | Conversation, user-owned memory, tool/execution policy, local or BYOK inference, Windows desktop/mobile agent API | Public social identity, global friend presence or unrestricted telecom |
| **Horus Clients** | Windows chat; iOS/Android/web/wearable microphone/screens; UI-specific permissions, CallKit/shortcut/device routing | Source-of-truth authorization, model API keys or hidden ambient microphone |
| **Mercury / Callless Network** | Verified identity and device sessions, directed grants, presence, rendezvous, scoped notifications and session records | The host PC's admin token, unrestricted user memory, third-party keys, silent mic pickup, door control |

Deployment requirement: Callless cannot require the recipient's PC to run or expose the full personal Horus API to the public internet. Inference and communications are separate services with a narrow delegated interface.

## Suggested repository boundaries (incremental)

These are **target modules**, not existing paths or a mandatory big-bang reorganization:

- `core/`: session logic, policy-enforced tool execution, provider-neutral model interface and memory contracts.
- `integrations/`: opt-in provider adapters, platform capabilities and bounded tool permissions.
- `clients/windows/`, `clients/ios/`, `clients/android/`, `clients/web/`: interface-specific code and packaged entry points.
- `services/callless/`: separate principal auth, presence, directed permissions, queue, signaling and event ledger.
- `packages/contracts/`: typed common request/event schema and versions.
- `tests/contracts/`, `tests/security/`, `tests/e2e/`: boundary, abuse and two-device testing.
- `docs/architecture/` and `docs/adr/`: current architectural overview and narrowly approved decisions.

Keep `jarvis_mrb`, existing env variables, file paths, SQLite state and Swift type names as backward-compatible surfaces **until** explicit migration tests and adapters exist. User-visible branding can say Horus without a risky repo-wide find/replace.

## Work packages, in sequence

### H0 — Establish and protect baseline

- Enumerate all applications, background loops, starts-at-login components, ports, required credentials, persisted stores and platform permissions.
- Capture a clean-machine Windows installer acceptance script, iPhone smoke test, and two-host Callless audio test.
- Repair the existing World Armor push failures or isolate with a documented, time-bounded owner and an actual fix ticket. Do not suppress failure in CI as "out of scope."
- Record which tests require secrets/hardware and which CI can run deterministically; each capability has a status: **proposed, source merged, targeted CI passed, simulator passed, real device validated, released**.
- Capture model/provider failure behavior and budget/latency measurements without storing private prompt content.

### H1 — Bound every subsystem

- Define capability manifest: ID, owning subsystem, available interfaces, required permissions, optional dependencies, startup cost, health check, enabled-by-default and removal path.
- **Opt-in** ambient sensing, hardware automation, privileged workflows and cloud processing; "installed" must not silently enable these.
- Separate feature discovery from feature execution, and "ask for permission" from "has permission."
- Introduce an explicit policy boundary for actions with side effects, external communication or costs.
- Split giant service/router objects in small vertical migrations, using compatibility wrappers and preserved API versions.
- Add an inventory of model prompts, tool ACLs and every path by which untrusted external text reaches a privileged planner.

### H2 — Make distribution credible

- Pin and lock installer dependencies, sign Windows binaries, publish SHA-256 and reproducible provenance.
- First-run onboarding: choose local or BYOK, enter credentials securely, test provider, test audio and optional phone pairing; no terminal required.
- Application update/rollback, state migration/backup and uninstall retention/credential-revocation choices.
- Simplify default path: **Windows + BYOK + text chat**, no camera, Meta account, Tailscale, Docker, Ollama or accessory required just to open the app. Clearly gate optional prerequisites.
- Capture non-GPU, offline, fresh-install and Windows permissions failures.
- Native iOS deployment needs actual developer signing and store/distribution process; an Xcode simulator pass is not a consumer release.

### H3 — Product/architecture documentation

- Replace the README encyclopaedia with a small landing page, current quick start, capability/status matrix and links; archive historical architecture decisions, not silently discard them.
- One authoritative current design per subsystem; older documents marked superseded rather than conflicting.
- Lightweight ADR template: decision, alternatives, API/data migration, security and cost, release gate, rollback.
- Feature freeze rule: after P0 Callless stabilization and V1 acceptance, new additions need a defined owning module and acceptance test before inclusion.
- Keep user-facing names and deployed reality honest. An endpoint returning 200 is not proof of successful mobile/background calling or real-time API availability.

### H4 — Security and data minimization

- Establish separate public/private trust zones; do not publish the PC control plane alongside Callless.
- Give each credential least privilege and independent rotation; network keys in system credential store, private recordings/memory encrypted, explicit privacy retention.
- Inventory local/world state, API keys, iOS preferences, push-device tokens, OAuth secrets, logs and exports.
- Audit all always-on microphones, local sensor collection, streaming endpoints, recordings, provider disclosures, and permission changes.
- Periodically exercise safe account deletion, token revocation, consent withdrawal, message expiry and backup restore.

### H5 — Performance and maintainability

- Profile warm model cost, startup latency, memory residency, background CPU/GPU and mobile power.
- Consolidate health telemetry, event envelopes, error categories and trace IDs with redacted logs.
- Stop background tasks cleanly; no duplicate schedulers after installer updates; test crash restart.
- Version client-server schemas and support a finite rolling-compatibility window.
- Test WebRTC in real networks and measure Callless connection time, dropped attempts and false positive urgent alerts.

## Minimum release gates

A milestone may be marked **released** only if all apply:

1. Feature behavior and privacy/cost boundaries are documented and tested, including unauthorized/negative paths.
2. Installer or mobile package is installable by its intended audience and rollback-safe.
3. All tests for changed code pass; known unrelated red CI is disclosed with owner/date, not portrayed as green.
4. Relevant real devices/networks are tested; simulator-only tests are labeled as such.
5. User-facing states never imply services connected, permissions granted, identities verified or recordings consented when they are not.
6. Every user-facing service can be disabled; any durable data can be found and handled under its retention policy.

## Proposed feature/status ledger

Maintain a small `docs/CAPABILITIES.md` derived from verified code/tests (not guessed from old prose), with columns:
`capability | owner | default | prerequisites | implemented | CI | real-device | shipped | next gate`.

Initial examples to verify:
- Push-to-talk iPhone: source merged + iOS simulator; device/Action Button acceptance outstanding.
- Windows GUI/BYOK: .exe installer artifact + targeted tests; clean-machine/paid-provider end-to-end acceptance outstanding.
- Callless: single-hub WebRTC signaling and browser UI; real remote two-party media, policy redesign and public TLS safety outstanding.
- World Armor: extensive code but some push regression tests red; needs its own owner and release gate.
- Native Callless reception: design only, not implemented.

## Decision queue after the Callless spec is approved

1. Confirm exact V1 scope: directed grants, calendar overlay, hold/messaging, screener; which guest fallback ships first.
2. Repair unrelated baseline CI failures; establish app-to-hub isolation and clean migration.
3. Build each Callless slice behind versioned contracts with regression/abuse tests.
4. Decide whether a production callless hub belongs in a separate repository or mono-repo service.
5. Only after first V1 evidence, remove obsolete duplicate paths and condense the README.

**Do not bundle a wholesale rename, schema rewrite, UI redesign, hosted cloud migration and Callless feature launch into one release.**
