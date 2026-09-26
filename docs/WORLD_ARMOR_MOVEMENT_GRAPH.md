# World Armor v3 — Planetary Movement Graph

**Branch:** `jarvis/world-armor-movement-graph`, stacked on the open
observation platform PR #15 and worldwide camera PR #14.

This increment turns the previously aspirational movement graph into an
implemented, source-qualified transport telemetry layer. It is not a
commercial flight-status product, passenger-tracking system, vessel-owner
database, or guarantee of global coverage.

## Implemented providers

### OpenSky Network

Jarvis can collect current OpenSky state vectors for:

- a user-selected WGS84 point + radius; or
- an explicit **provider-global** scope.

The adapter preserves public transport identifiers (ICAO24), callsign when
broadcast, position, altitude, velocity, heading, vertical rate, on-ground
state, category, source timestamp and position-source code. It does **not**
join the transponder identifier to a person, passenger, crew member, owner,
home address, employer or private itinerary.

Anonymous recent state access remains possible when the provider permits it.
Optional authenticated access uses the current OAuth2 client-credentials
variables `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`; the access token
is kept in process memory and not returned through the iPhone API.

Official provider documentation:
https://openskynetwork.github.io/opensky-api/rest.html

### AISStream

When `AISSTREAM_API_KEY` is configured server-side, Jarvis can open a
short WSS subscription for a selected geographic box and retain normalized
`PositionReport` messages. Retained fields include MMSI, published ship name
when supplied, point, speed over ground, course and true heading.

The API key never goes to iOS. Direct browser subscriptions are not used.
The provider connection is event-driven and can miss traffic during
interruptions; no empty burst is treated as proof that a sea area is clear.

Provider documentation:
https://aisstream.io/documentation

## Persistent movement graph

The same `world_armor_platform.sqlite3` file now contains:

- `movement_sources`: exact provider grant, region/global scope, declared
  governing terms, automated-access authority, provider minimum interval,
  polling cadence, retention and revocation state;
- `movement_entities`: transport entity identity as broadcast by the
  provider (ICAO24 or MMSI), latest source name/callsign and first/last local
  receipt timestamps;
- `movement_observations`: typed point history with source/provider times,
  altitude/speed/heading and a deterministic source-state digest;
- `movement_checks`: provider status, collection time and how many new
  observations were retained.

There is **no fixed global source-count ceiling**. Registry reads are paged
for transport and UI efficiency. Derived track retention is set per source.
Provider terms, provider quotas, disk/CPU/network capacity and operator-set
cadence are the actual constraints.

A repeated state with the same source/entity/time/position/motion digest is
not stored twice.

## Collection authority

Movement collection is off unless all are set:

```powershell
$env:JARVIS_WORLD_ARMOR_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_PLATFORM_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED = "1"
```

Optional credentials:

```powershell
$env:OPENSKY_CLIENT_ID = "<OpenSky OAuth client>"
$env:OPENSKY_CLIENT_SECRET = "<OpenSky OAuth secret>"
$env:AISSTREAM_API_KEY = "<AISStream server-side key>"
```

One local batch:

```powershell
jarvis-world-movement --once --limit 4
```

Long-running explicit host collector:

```powershell
jarvis-world-movement --limit 4 --interval-seconds 10
```

The process wake interval is not the provider cadence. Each enrolled source
has its own cadence and provider-minimum interval. The service and iPhone app
do not auto-start this runner.

A stop or pause clears the lease. Before saving any provider response, the
collector rechecks source state and the feature flags. A source stopped while
network I/O is in flight therefore cannot persist the returned movement
observations.

## Queries

Authenticated private routes:

- `POST /world-armor/v3/movement-sources`
- `GET /world-armor/v3/movement-sources?offset=0&page_size=100`
- `POST /world-armor/v3/movement-sources/transition`
- `POST /world-armor/v3/movement-sources/forget`
- `POST /world-armor/v3/movement/collect`
- `GET /world-armor/v3/movement/nearby`
- `GET /world-armor/v3/movement/track`

There is deliberately no remote `run-due` endpoint. Scheduled movement
collection remains an explicit local-host authority boundary.

The native World Armor screen can enroll regional or provider-global
OpenSky sources, regional AISStream sources, collect a source, pause/stop/
forget it, and query the latest retained aircraft/vessel states near an
entered point.

## Reality Graph integration

`world_armor_graph.combined_evidence()` now includes nearby retained
movement entities beside:

- NWS / USGS / modelled AQI evidence from the bounded legacy investigation;
- selected public-camera receipts from the v2 camera source platform.

This is a **typed co-display**, not automatic causal inference. An aircraft
or vessel near a place does not prove relevance to a fire, accident, person,
transaction or trip. Missing telemetry does not prove absence. Provider
timestamps and receipt times are preserved separately.

## What remains for the full planetary system

Not yet implemented in this increment:

- persistent long-lived AIS WebSocket pooling (current AIS collection uses
  explicit bounded source bursts);
- cross-machine movement workers;
- provider adapters for rail, transit, road fleets, satellites or additional
  ADS-B/AIS networks;
- commercial airline schedule/delay/booking status;
- route intersection, geofence entry/exit and higher-level movement alerts;
- map animation and historical track rendering in iOS;
- camera field-of-view geometry joined against moving entities;
- verified entity-to-event causal relationships;
- arbitrary owner/passenger/person enrichment;
- remote physical actions based only on movement telemetry.

The movement graph is deliberately designed so additional lawful providers
can add typed transport observations without changing the graph's entity /
position / source-time contract.
