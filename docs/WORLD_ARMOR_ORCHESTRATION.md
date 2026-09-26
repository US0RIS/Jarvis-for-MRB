# World Armor v6 — Worker Orchestration and Pooled Transport

**Branch:** `jarvis/world-armor-worker-orchestration`, stacked on World Armor
v5 / PR #18.

This increment turns the private observer fabric from two hard-coded Macs into
an explicitly registered, capability- and load-aware worker fleet. It also
collapses due AIS region polling onto a pooled Windows-side AISStream
connection so provider credentials remain centralized.

## Explicit worker fleet

The existing `macbook` and `macmini` IDs remain the interactive workstation
pair. Additional World Armor-only observers may be named explicitly in the
Windows service environment:

```powershell
$env:JARVIS_MESH_WORLD_WORKER_IDS = "observer-3,observer-4"
$env:JARVIS_MESH_OBSERVER_3_URL = "http://100.x.y.z:8766"
$env:JARVIS_MESH_OBSERVER_3_TOKEN = "<separate random node secret>"
$env:JARVIS_MESH_OBSERVER_3_LABEL = "Observer 3"
```

There is no multicast, subnet scan, MagicDNS enumeration, mDNS, ARP discovery
or wildcard trust. A worker is eligible only if its exact ID is in the registry,
its exact private endpoint/token are configured, and its authenticated health
response reports the matching device ID and a supported typed capability.

Additional observer IDs are observation-only. The pre-existing MacBook/Mac mini
interactive screen/app controls remain separately constrained; adding an
observer does not grant desktop-control authority.

## Worker capacity and load

Start an observer with an explicit concurrency budget:

```bash
python3 scripts/jarvis-mac-node.py \
  --device-id observer-3 \
  --label "Observer 3" \
  --bind <this node's Tailscale IPv4> \
  --allow-world-observer \
  --world-capacity 2
```

Authenticated health now reports bounded scheduling telemetry:

- active World Armor requests;
- configured observation capacity;
- CPU count;
- one-minute system load;
- normalized load = one-minute load / CPU count.

The controller uses only these coarse operational metrics. It does not collect
process lists, files, browsing history or arbitrary host telemetry for
scheduling.

## Scheduling

For regional OpenSky and credential-free camera work, the controller selects
an eligible remote worker by:

1. exact typed capability;
2. online/identity-verified state;
3. controller-owned failure cooldown;
4. advertised free capacity;
5. normalized system load;
6. virtual assignments already made in the current dispatch pass.

If no remote worker qualifies, Windows executes the same enrolled source
locally. Remote jobs assigned in one pass actually execute concurrently up to
each worker's advertised capacity; the controller uses a 32-thread execution
pool as a host throughput guard, not a source-count limit. Windows-local work
remains serialized. A failure does not trigger an immediate second request for
the same source. The next undispatched source may use another worker, while the
failed worker enters an exponentially increasing controller-side cooldown
(15 seconds up to five minutes).

The controller persists only orchestration health: success/failure counts,
consecutive failures, last success/failure and cooldown expiry. Successful work
clears the consecutive-failure cooldown.

## Pooled AIS transport

AISStream credentials stay on Windows. When multiple AIS regions are due in the
same movement batch, World Armor now:

1. acquires each exact source lease first;
2. constructs the exact set of enrolled bounding boxes;
3. opens one AISStream WebSocket;
4. subscribes to those boxes together;
5. normalizes each vessel position once;
6. partitions it back into every matching enrolled source;
7. runs the existing per-source authorization/revocation fence;
8. persists each source's evidence/check receipt independently.

The pooled adapter handles up to 64 source regions per transport batch. This is
not a global source limit; later due regions remain queued for subsequent
passes. A provider outage or malformed pooled result cannot be converted into
an all-clear.

## API / phone

`GET /world-armor/v6/workers` exposes the same private no-store worker
topology as v4 plus scheduling metrics and controller dispatch health. The v4
route remains as a compatibility alias.

The iPhone/iPad World Armor console displays worker capability, normalized load,
active/capacity and cooldown state. Merely opening the app still does not start
a dispatcher or provider connection.

## Authority boundaries retained

This increment still does not add:

- arbitrary command/RPC execution;
- private-camera or private-network source discovery;
- face, plate or person identification;
- cross-camera person/vehicle tracking;
- credential delegation to observation workers;
- autonomous physical action;
- public-Internet bearer-token transport;
- automatic legal-rights adjudication.

Provider rights, terms, rate limits and source-specific retention remain
operator-recorded grants enforced by the Windows controller.
