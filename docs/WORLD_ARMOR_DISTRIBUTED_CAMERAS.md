# World Armor v5 — Distributed Camera Workers

**Branch:** `jarvis/world-armor-distributed-camera-workers`, stacked on
World Armor v4 / PR #17.

This increment uses the exact paired MacBook Air and Mac mini as
**rights-scoped public-camera acquisition + local vision workers**. Windows
remains the authority for source enrollment, source terms, polling cadence,
leases, revocation, retention, notices and final evidence writes.

## What is distributed

When a camera source is already enrolled in the World Armor v2 source ledger,
the explicit distributed runner may assign a due check to a Mac that was
started with:

```bash
python3 scripts/jarvis-mac-node.py \
  --device-id macbook \
  --label "MacBook Air" \
  --bind <this Mac's Tailscale IPv4> \
  --allow-world-observer
```

The Mac advertises:

```json
{
  "world_observer_capabilities": [
    "opensky_region_read_only",
    "camera_source_analysis_read_only"
  ]
}
```

Supported remote camera source kinds in this increment:

- `caltrans`
- `public_https`
- `public_http`

`windy` stays on Windows because its provider API may require a credential;
World Armor does not delegate that credential to a worker.

## Dispatch

Movement dispatch remains unchanged. Camera dispatch is an additional,
explicit option:

```powershell
jarvis-world-distributed --once --include-cameras --camera-limit 4
```

or continuously:

```powershell
jarvis-world-distributed --include-cameras --camera-limit 4 --interval-seconds 10
```

The runner selects only source grants that are active, explicitly authorized
for automated access, due under their source-specific cadence, within any
operator-set check budget, and not expired or already leased.

A Mac failure is **not** silently retried through another Mac or Windows in
the same source interval. That avoids converting a worker outage into an
extra publisher request.

## Camera task boundary

The controller sends one typed task containing the exact already-enrolled
source kind/locator, the environmental scene goal and the prior frame digest.

The worker may not receive a shell command, file path, private-network target,
credential bundle or action request. Direct public-media sources still pass
through the existing World Armor media guard:

- public DNS hostname required;
- no literal IP targets;
- private, loopback, link-local and other non-public resolved addresses
  rejected on each fetch;
- standard HTTP/HTTPS ports only;
- no stored credential/signed URL for generic media;
- no open redirects;
- supported still/MJPEG/HLS media only;
- one normalized frame per check.

The worker performs local vision using the same environmental/infrastructure
prompt and identity/tracking exclusions as the Windows path.

## Data movement and lineage

Raw camera image bytes remain on the worker only for the duration of the
single analysis call and are not returned to Windows. The worker returns only:

- SHA-256 frame digest;
- retrieval timestamp;
- normalized media kind;
- sanitized source display;
- whether the published frame digest was unchanged;
- the structured local-model observation when the frame is distinct.

Windows revalidates the receipt before persistence. Camera evidence and check
receipts now record `worker_id` just like movement evidence.

The controller acquires its SQLite lease **before** dispatch. After the worker
returns, Windows checks the same source grant, lease, expiry/check budget and
feature gate again. Pause/stop/revocation during remote acquisition or model
work therefore vetoes late persistence.

## What this does not add

This increment does not add private-camera access, network scanning,
credential harvesting, arbitrary web fetching, person identification,
cross-camera person/vehicle tracking, face or plate recognition, remote
actuation, general-purpose compute RPC, controller failover, APNs push, or
automatic source-rights adjudication.

Provider/publisher rights and rate limits remain source-specific facts that
the operator records in the World Armor grant ledger; code cannot establish
legal entitlement by itself.

## Scale implication

This removes a major single-host bottleneck. The Windows RTX host can remain
the source-of-truth controller while the MacBook Air and Mac mini independently
consume due public-camera frames and run local vision. The same typed worker
protocol can later grow to additional explicitly paired machines, load-aware
scheduling and credential-free providers without granting general command
authority.
