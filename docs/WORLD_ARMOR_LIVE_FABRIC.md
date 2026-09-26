# World Armor v7 — Live Fabric

World Armor v7 turns the already-authorized observation stack into a persistent
controller fabric. It does **not** narrow the original World Armor target:
Reality Browser, Presence, Causal Debugger, Synthetic Senses and Parallel
Existence remain later full-scope layers.

## Supervisor

The new `jarvis-world-live` process is one controller-side supervisor for the
existing World Armor collectors. Enable it explicitly:

```powershell
$env:JARVIS_WORLD_ARMOR_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_LIVE_ENABLED = "1"
jarvis-world-live --loop
```

For service-start persistence, also set:

```powershell
$env:JARVIS_WORLD_ARMOR_LIVE_AUTOSTART = "1"
```

The supervisor runs only collectors whose own feature flags and source grants
already authorize collection. It cannot create a camera, movement source or
standing watch, discover a private source, expand a provider scope, or grant
any action authority.

A cycle can service:

- due distributed OpenSky / movement sources;
- due enrolled public-camera sources;
- due standing watches;
- the pooled AIS transport introduced in v6.

The supervisor keeps a heartbeat, cycle count, cycle duration and last error.
Provider/worker failures remain degraded/unknown rather than becoming an
all-clear.

## Durable live journal

Live collection receipts are written to a separate bounded SQLite journal.
Each event has a monotonically increasing sequence number, subsystem, source
ID, status, priority, timestamp and bounded metadata payload.

Retention is bounded to 14 days and 10,000 events. The journal explicitly
reports a `replay_gap` when a client's saved cursor predates retained history.
That prevents a reconnect from pretending it has a complete timeline.

Raw camera frames, provider payloads, camera locators and model image inputs are
not written into this live journal.

## Delivery

Every durable event is also best-effort fanned out on Jarvis's existing
authenticated companion WebSocket as `world_armor_event`. The durable journal
is authoritative; socket delivery is not.

The iPhone persistent-presence layer remembers the last consumed sequence and
requests missed events after reconnect. Warning/urgent events can be shown in
MemoMind and, when the user enables the separate setting, as iOS local
notifications.

This is not yet a claim of closed-app APNs delivery. Local notification
delivery depends on iOS permission and the Jarvis companion connection being
alive long enough to receive the event. True server-to-device APNs remains a
later transport layer.

## Private API

- `GET /world-armor/v7/live/status`
- `GET /world-armor/v7/live/events?after_seq=...&limit=...`
- `POST /world-armor/v7/live/start`
- `POST /world-armor/v7/live/stop`

All use the existing private Jarvis bearer-auth boundary and no-store response
headers.

## Full-scope direction

v7 is infrastructure for the original suit-of-armor goal. Later layers still
include broader lawful world-source coverage, closed-app push delivery,
resilient deployment/failover, Reality Browser, Presence, Causal Debugger,
Synthetic Senses and Parallel Existence. None of those are removed by this
increment.
