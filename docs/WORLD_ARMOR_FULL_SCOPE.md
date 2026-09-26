# World Armor v8 — full-scope suit

**Branch:** `jarvis/world-armor-full-scope`  
**Status:** implementation candidate. Source/simulator/CI success is not a claim that a
particular iPhone, Apple Push Notification credential, HomeKit accessory, public
provider, Windows host, Mac worker, or physical actuator has passed live acceptance.

World Armor v8 completes the software architecture that was retained in the original
full-scope design. It does not reduce that design to a camera dashboard. The five
Phase-5 surfaces are now explicit runtime interfaces over the evidence/live-fabric
foundation:

1. **Reality Browser** — a time-navigable view of retained live events and, when an
   investigation is selected, its source-qualified evidence graph. Missing time remains
   unknown and the browser does not synthesize unobserved frames.
2. **Synthetic Senses** — explicit derived signals such as collector health, new
   movement positions, camera-evidence changes, attention notices and represented
   source diversity. Every signal is labelled derived and is not promoted to a direct
   world fact.
3. **Causal Debugger** — turns candidate correlations into falsifiable mechanism tests.
   It exposes missing evidence and alternatives; it does not turn temporal overlap into
   a causal claim.
4. **Parallel Existence** — executes bounded, typed read-only World Armor analyses in
   parallel and records a run receipt. It cannot manufacture source access, action
   authority or a physical-completion claim.
5. **Presence** — a physical embodiment bridge with an exact, short-lived actuator
   grant. The first implemented actuator is an already-discovered Apple Home light on
   the iPhone. Dispatch, HomeKit command acceptance and fresh accessory readback are
   separate states.

## Full data path

```text
authorized public/owned source
       |
       v
source-specific adapter + grant ledger
       |
       v
bounded collectors ---- paired read-only workers
       |                       |
       +----------+------------+
                  v
          evidence/live journals
                  |
       +----------+-----------+------------------+
       |          |           |                  |
       v          v           v                  v
 Reality     Synthetic     Causal            Parallel
 Browser      Senses       Debugger          Existence
       \          |           /                  /
        +---------+----------+------------------+
                            |
                    typed attention event
                       /             \
                      v               v
             companion WebSocket   durable APNs outbox
                    |                 |
                 iPhone <-------------+
                    |
              exact Presence grant
                    |
            local HomeKit controller
                    |
           fresh accessory readback
                    |
              Presence receipt
```

The durable World Armor journal is the source of truth. WebSocket and APNs are
delivery transports. A notification disappearing or APNs being unavailable does not
erase an event, and an APNs 200 response is not physical-world evidence.

## General public-camera path

The open observation platform is not limited to a fixed camera count or a small set of
named cities. In addition to provider adapters such as Caltrans and Windy, an operator
can enroll an exact public HTTP/HTTPS media source under a recorded grant/terms
reference. The media layer supports a bounded single-frame interpretation from
published JPEG/PNG/WebP, MJPEG and unencrypted MPEG-TS HLS. It performs public-DNS
validation on every fetch, pins the actual connection to the vetted public address,
rejects private/link-local/reserved targets, rejects redirects, bounds bytes/time and
does not retain the raw frame.

For a public web page rather than a direct media URL, the page-media inspector can
make one bounded read and enumerate literal image/video/source links. It does not
execute JavaScript, probe hosts, guess credentials or scan private cameras. Dynamic
players and provider-specific protected formats still need a lawful provider adapter;
that is an external compatibility/authorization constraint, not a fixed World Armor
camera-count ceiling.

## Closed-app notification transport

Set:

```text
JARVIS_WORLD_ARMOR_ENABLED=1
JARVIS_WORLD_ARMOR_PUSH_ENABLED=1
JARVIS_APNS_TEAM_ID=<Apple developer team id>
JARVIS_APNS_KEY_ID=<APNs .p8 key id>
JARVIS_APNS_BUNDLE_ID=com.us0ris.JarvisMRB
JARVIS_APNS_KEY_FILE=<local path to the .p8 private key>
JARVIS_APNS_ENVIRONMENT=development   # or production
```

The signing key is read from the local file at send time and is never stored in the
World Armor database or returned to the phone. The iOS notification toggle is the
user opt-in. When enabled, iOS requests notification permission, registers for remote
notifications, and sends the APNs device token to the authenticated private Jarvis
API. Disabling the toggle disables that backend token.

Warning/urgent events are copied to a bounded durable outbox. Delivery uses APNs
HTTP/2 provider-token authentication, capped exponential retry and terminal handling
for invalid/unregistered tokens. Informational events do not enter the APNs outbox.
The outbox is capped at 2,000 pending rows and pending pushes expire after 24 hours;
the underlying live journal remains available for replay.

The checked-in entitlement uses the development APNs environment for developer-device
builds. A production signing/provisioning configuration must carry the matching
production push entitlement and `JARVIS_APNS_ENVIRONMENT=production`.

## Resilience

There are two recovery levels.

**Inside the Jarvis service:** a small runtime guard checks the live-supervisor and
push-worker threads every 15 seconds. If an opted-in thread unexpectedly dies, it is
re-created. Individual collector failures remain isolated and become degraded receipts
rather than terminating the supervisor.

**Independent process supervision:** for an always-on host, disable the in-process
collector autostart and use:

```text
JARVIS_WORLD_ARMOR_LIVE_AUTOSTART=0
jarvis-world-live-watchdog
```

The watchdog starts exactly one `jarvis_mrb.world_armor_live --loop` child, restarts
unexpected exits with capped exponential backoff, maintains a local status record and
rejects use alongside in-process live autostart. The host OS/service manager should in
turn supervise the watchdog; no process can guarantee recovery after its own host loses
power or the operating system stops it.

## Full-scope enablement

The v8 read/analysis/Presence APIs additionally require:

```text
JARVIS_WORLD_ARMOR_FULL_ENABLED=1
```

The existing source-specific flags still apply. Enabling v8 does not enroll a source,
authorize automated polling, create a watch, expose a worker, or authorize an actuator.

## Presence authority contract

A Presence command is valid only when all of the following are true:

- the full-scope layer is enabled;
- the target is an exact UUID;
- the actuator class is a registered type (`homekit_light` today);
- a short-lived grant exists and has remaining uses;
- the authenticated iPhone receives the typed request before expiry;
- that exact light is present in the iPhone's current Apple Home catalog and reachable.

The backend first records **dispatched_unverified**. The iPhone then invokes the
existing local HomeKit controller and posts a second receipt. A successful fresh
HomeKit state readback is recorded as **verified_reported_state**. That is stronger than
HTTP/command acceptance, but it is still an accessory-reported state, not an independent
optical/physical sensor. Locks, garage doors and arbitrary URLs are not exposed through
this Presence implementation.

## Private v8 API

All routes use the existing private Jarvis authentication and `Cache-Control:
private, no-store`.

```text
GET  /world-armor/v8/status
POST /world-armor/v8/reality-browser
POST /world-armor/v8/synthetic-senses
POST /world-armor/v8/causal-debugger
POST /world-armor/v8/parallel-existence

GET  /world-armor/v8/presence
POST /world-armor/v8/presence/grants
POST /world-armor/v8/presence/dispatch
POST /world-armor/v8/presence/receipt
POST /world-armor/v8/presence/revoke

GET  /world-armor/v8/push/status
POST /world-armor/v8/push/register
POST /world-armor/v8/push/unregister
```

## Completion and acceptance

“Implemented” and “observed deployed” remain separate statuses. The software-side v8
scope is complete when its regression suite and iOS simulator build pass at the exact
branch SHA. A real deployment still has source/provider and hardware gates that cannot
be proven by source code:

- signed physical iPhone registration with APNs and a delivered closed-app notification;
- real permitted provider events and replay;
- Windows long-run supervisor/watchdog restart exercise;
- paired worker disconnect/recovery;
- one exact HomeKit light grant, command, fresh readback and revoke/expiry exercise;
- operator stop/delete/replay demonstration;
- any additional provider-specific camera format under its actual terms.

Those are acceptance tests of the installed system, not missing conceptual layers or a
reason to remove scope.
