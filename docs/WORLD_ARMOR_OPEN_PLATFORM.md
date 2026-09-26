# World Armor — Open Observation Platform v2

**Implementation branch:** `jarvis/world-armor-open-observation-platform`, stacked
on the worldwide public-camera expansion PR #14 (itself stacked on
World Armor #13/#12/#9/#8/#7). Draft source code and synthetic CI are NOT
a deployment on the operator's Windows PC, iPhone, paired Macs or cloud.

## What this increment actually changes

The legacy World Armor *v1* 12-region/20-sample/72-hour fixed-source
investigation and its early bounded watch engine remain unchanged for
compatibility. The new **v2 source platform is not constrained by those
numbers**: it maintains any number of individually enrolled exact public
camera sources through paginated reads, with grants that remain active until
stopped, expired **if an expiry was expressly selected**, a source-specific
check budget **if expressly selected**, or host resource limits.
No auto-search of private networks, covert recording, or silent host runner.

The new subsystem has five concrete separable components:

1. `world_armor_platform.py`: persistent, revocable, source-scoped
   access registry and typed policy/cadence/retention; host budgets,
   index-backed paginated observations, check receipts and notices.
2. Existing PR #14 adapters + `world_armor_perception.py`: exact Caltrans,
   optionally keyed Windy, or operator-chosen public HTTPS still/MJPEG/
   compatible HLS media. One normalized frame per check, task-oriented
   local Ollama scene interpretation with a **freeform visual environmental
   or infrastructure condition**, no longer just smoke/congestion.
   Image hash skips repeat model calls when a publisher re-serves the
   identical frame. No media URL from inside an image is followed.
3. `world_armor_observe.py`: explicit local host collector, user-tapped
   manual observation or cadence-based source polling, SQLite write
   leases, mid-flight stop/expiry/consent check, independent degraded
   source status and two **distinct** matching-image findings before
   a model-qualified watch notice. No remote action or notification push.
4. `world_armor_graph.py`: combined, read-only regional evidence display
   for legacy World Armor NWS/USGS/modelled AQI receipts and nearby v2
   camera receipts, using source-published camera position only as a
   *point of interest*. **Camera capture times remain unknown**, so
   these are co-displayed evidence, not spurious simultaneous-event
   source confirmations or causal links. An unlocated source is
   explicitly separated rather than assigned the investigation center.
5. `service.py` and native `WorldArmorView.swift`: private authenticated
   REST endpoints and a persistent globally accessible source console
   to enroll source-specific rights and inspection goals, preflight,
   page through sources, manually inspect, read evidence and notices,
   pause, stop and forget. A discovered Caltrans/Windy camera or an
   explicitly pasted media URL can pre-fill an exact proposed source;
   the operator still enters governing permission before enrolling.

**Not implemented:** cross-machine worker execution, rights adjudication,
generic JavaScript/WebRTC/RTSP/DRM adapters, archive/recording raw video,
verified camera view cones, verified capture times, automated camera
identity/person tracking, all-camera global scans, closed-app push, or
remote actuation. The legacy v1 region and environmental sample ceilings
are not secretly represented as lifted. A v2 source can observe
indefinitely *within its actual access and infrastructure constraints*;
v1 regions are still bounded. Better provider source-time metadata and
true cross-source physical event correlation are separate acceptance work.

## Source rights: record a declaration, never claim legal verification

Each exact source has:

- `kind`: `caltrans`, `windy`, `public_https` or separately
  selected `public_http`. HTTP uses unencrypted port 80 only with an
  explicit source grant; DNS/IP destination controls still apply, but
  TLS authenticity/confidentiality does not exist for that feed;
- `locator`: one exact catalog ID or directly vetted public HTTPS media
  URL; URLs with credentials/token-like parameters are not accepted in
  this version; no private IP, localhost or redirects;
- `grant_class`: `public_publisher`, `api_contract`,
  `owned_or_authorized`, plus a nonempty `terms_reference` string;
- `authorized_automated_access`: independently selectable true/false;
- `automated_min_interval_seconds`: **operator-declared source rule**;
- `cadence_seconds`: 0 = manual only; positive interval must meet
  the declared source minimum. A declaration cannot override actual
  provider terms, statutes, licensor rights, rate limits, copyright,
  privacy requirements or geographic restrictions;
- `retention_days`: per-source duration for derived text/hash and notices
  (not raw media). Source forget deletes all linked evidence and notices;
- `sample_budget` and `consent_expires_at`: optional, null means the
  operator did not impose that particular fixed limit;
- `scene_goal`: bounded freeform environmental/infrastructure condition;
  the model must only report visible evidence, without faces, name,
  plate extraction, personal re-identification, inferred crimes or
  asserted confirmed disasters.

No third-party license or permission is verified by this form; treat
`permission_verified_by_jarvis=false` as authoritative. A producer
change, revoked license or new law requires operator review and source
pause/stop. The platform defaults **OFF** and does not silently restore
stopped grants. Windy requires a provider/API account on the host and
the actual permissions that allow the selected level of access.

## Configure a host

```powershell
$env:JARVIS_WORLD_ARMOR_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_CAMERAS_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_PLATFORM_ENABLED = "1"

# Optional directory source, subject to Windy permissions:
$env:JARVIS_WINDY_WEBCAMS_API_KEY = "<your own API key>"

# Host engineering budget, not a legal or global source-count restriction.
# 0 disables this *file-size* preflight; available disk still constrains use.
$env:JARVIS_WORLD_ARMOR_PLATFORM_MAX_DB_MB = "1024"

# Explicit local collector; not auto-started by service or iPhone UI:
python -m jarvis_mrb.world_armor_observe --once --limit 4
python -m jarvis_mrb.world_armor_observe --limit 4 --interval-seconds 10
```

The last command is a foreground ongoing host process; provide your
own explicitly authorized service manager if persistent execution is
desired. `--limit` is **batch throughput**, not a cap on enrolled
sources. The runner wake interval is not a source poll frequency. Each
camera has its own permitted cadence. When a publisher re-serves an
identical image, a check is recorded but the model does not reprocess
the image and no new physical event is claimed.

The source metadata, derived observations and notices live in
`world_armor_platform.sqlite3` in Jarvis's own data folder.
Source URLs for exact automated checks are local application data, not
returned in the native UI's public image preview. Use the normal
host access controls, encrypted disk/backup and private network
transport appropriate to your actual setup; a screenshot of a public
image can still contain personal data.

## v2 authenticated API

Every route uses the same private Mesh bearer credential and
`Cache-Control: private, no-store`. GET read and stop/forget remain
available after the feature flag is turned off.

| Route | Action |
|---|---|
| `POST /world-armor/v2/source-grants` | Exact source enrollment with access terms, cadence, retention, goal, optional geography and optional consent expiry/budget |
| `GET /world-armor/v2/source-grants?offset=0&page_size=100` | Cursor/offset paged registry; not global count-capped |
| `POST /world-armor/v2/source-grants/transition` | `pause`, `resume`, `stop` |
| `POST /world-armor/v2/source-grants/forget` | Delete source, derived evidence, local notices and checks |
| `POST /world-armor/v2/sources/observe` | One authorized, exact user-tapped source sample |
| `GET /world-armor/v2/observations` | Paged evidence, optionally by source |
| `GET /world-armor/v2/notices` | Paged qualified private notices |
| `POST /world-armor/v2/plan` | Pure deterministic source-policy/resource preflight |
| `GET /world-armor/v2/combined-evidence` | Co-display enrolled nearby camera receipts with existing bounded v1 regional environmental evidence |

There is intentionally **no remotely invocable general due-runner API**.
The local host runner is the explicit authority boundary; APIs cannot
send media to arbitrary destinations, grant new provider permission, or
execute LLM-generated network commands.

## Acceptance distinctions

CI with mocks verifies grant validation, lack of source-count ceiling,
pagination, stop during network I/O, duplicate frame offload,
provider failure reporting, separate source cadences, notice rearming,
forget while off, model-free preflight, privacy labeling and source-time
honesty. CI simulator build verifies compilation, not iOS network
pairing, correct foreground/background behavior on hardware or notification
delivery. **Real acceptance still requires** exact branch/host SHA,
authorized provider account and written source rights as applicable,
live published frames, duration/rate/retention checks, genuine provider
failure and stop-during-HTTP, user consent, host disk monitoring and
two genuinely different images under a selected condition.
