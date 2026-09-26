# World Armor v4 — Distributed Public-World Observers

**Branch:** `jarvis/world-armor-distributed-observers`, stacked on the
movement graph PR #16, observation platform #15 and camera expansion #14.

This increment turns the existing private Reality Mesh into a small
distributed **read-only observation fabric**. It does not create a general
remote computer, shell, arbitrary URL fetcher, network scanner or action
executor.

## Authority model

The Windows Jarvis controller remains authoritative for:

- exact source enrollment and recorded provider terms;
- whether automation is permitted at all;
- per-source provider minimum request interval and actual cadence;
- SQLite leases before external I/O;
- normalization and schema validation;
- deduplication, derived-data retention and deletion;
- final evidence persistence.

A paired Mac may be used only as a **fetch worker** after that Mac was
explicitly started with `--allow-world-observer`. The current worker
capability is deliberately narrow:

```text
opensky_region_read_only
```

The Mac accepts a typed task containing only:

```json
{
  "kind": "opensky_region",
  "latitude": 34.05,
  "longitude": -118.25,
  "radius_km": 80
}
```

The node itself constructs the request to the fixed OpenSky
`/api/states/all` endpoint. A caller cannot supply a hostname, URL,
header, credential, shell command, file path, arbitrary provider or
general RPC.

This is a **capability boundary**, not a statement that laws require one
provider or one task. Additional lawful providers can be added as explicit
typed capabilities once implemented and tested.

## Mac startup

Existing Mac node setup remains the same, with one additional independent
flag:

```bash
export JARVIS_MESH_NODE_TOKEN='<separate long random Mac node secret>'

python3 scripts/jarvis-mac-node.py \
  --device-id macbook \
  --label "MacBook Air" \
  --bind <this Mac's Tailscale IPv4> \
  --allow-world-observer
```

The option is independent of `--allow-screen` and
`--allow-app-launch`. A Mac may expose any subset of those capabilities.

The health manifest reports:

```json
{
  "world_observer": "opensky_region_read_only"
}
```

only when the startup opt-in is active.

## Controller dispatch

Enable the same source/movement gates used by World Armor v2/v3:

```powershell
$env:JARVIS_WORLD_ARMOR_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_PLATFORM_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED = "1"
```

Then explicitly run:

```powershell
jarvis-world-distributed --once --limit 8
```

or an ongoing foreground dispatcher:

```powershell
jarvis-world-distributed --limit 8 --interval-seconds 10
```

The dispatcher does **not** create new source authority. It looks only at
movement sources already enrolled for scheduled automated access and
already due under their source-specific cadence.

Assignment rules in this increment:

- regional OpenSky: round-robin over live, identity-verified, opted-in
  `macbook` / `macmini` workers when available, otherwise Windows;
- provider-global OpenSky: Windows controller only;
- AISStream: Windows controller only.

A failed remote worker is not silently retried through another worker in
the same cadence window. This avoids turning a worker outage into a hidden
extra provider request. The next authorized source interval may try again.

## Evidence lineage and revocation

Movement observations and movement check receipts now record
`worker_id` (`windows`, `macbook` or `macmini`).

The controller obtains its SQLite lease **before** asking a Mac to contact
OpenSky. After the network response returns, it verifies that the same
source grant and lease are still active before persisting anything.

Therefore:

- pause/stop during remote network I/O vetoes late evidence;
- feature-gate revocation vetoes late evidence;
- a worker/provider exception releases the exact lease and leaves an
  explicit failed check receipt rather than wedging the source;
- the Mac cannot persist directly into the World Armor database.

Raw OpenSky provider JSON is returned over the existing authenticated,
private Reality Mesh connection and normalized by the Windows controller.
The Mac does not receive the World Armor database or source ledger.

## Private API and native UI

One new read-only private route:

```
GET /world-armor/v4/workers
```

It lists only:

- the Windows controller; and
- exact paired Macs that are currently online, identity-verified and
  advertising `opensky_region_read_only`.

There is intentionally **no**
`/world-armor/v4/run-due` remote dispatch endpoint. The iPhone/iPad
World Armor movement console can display and refresh the trusted worker
topology, but opening the app cannot start distributed collection.

## Current limits that are implementation gaps, not arbitrary policy ceilings

The distributed fabric does not yet:

- run camera fetching or local vision inference on paired Macs;
- maintain pooled long-lived AIS workers;
- distribute provider-global OpenSky responses;
- use the RTX Windows host plus Macs as a general inference cluster;
- support additional worker machines beyond the explicitly configured
  MacBook Air and Mac mini;
- dynamically advertise plugin/provider capabilities;
- balance work using CPU/GPU/network load;
- survive controller failover;
- stream live entity deltas to the phone;
- send APNs notifications when the app is closed.

Those are the next engineering layers. The fixed worker protocol exists so
they can be added as explicit capabilities without turning a trusted node
into an arbitrary command or network proxy.

## Privacy and legal scope

A distributed worker does not change the rights attached to the source.
The source/provider contract stored on Windows remains authoritative.
Worker execution cannot widen geography, polling rate, retention, provider,
or purpose.

Movement IDs remain public transport identifiers; this layer does not infer
owners, passengers, crew or other people from ICAO24/MMSI/callsign/name.

Passing CI demonstrates code behavior under test. It does not establish
provider entitlement, a live Tailscale path, actual Mac availability,
real OpenSky quota, production deployment or legal permission for a
particular use.
