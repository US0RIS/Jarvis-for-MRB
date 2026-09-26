# World Armor — Global Public Camera Expansion (stacked draft)

**Status:** implemented on `jarvis/world-armor-global-public-cameras`
on top of PR #13. Draft/CI is not a deployed host, verified provider
license, or promise that every webcam website can be programmatically read.

## New actual capabilities

1. **Caltrans official highway cameras**, already integrated. In
   California, the unified discovery also searches Caltrans's catalog
   (Caltrans radius at most 50 km and 20 results per query).
2. **Windy Webcams API v3 worldwide directory** (optional key). Set
   `JARVIS_WINDY_WEBCAMS_API_KEY` in the actual Jarvis host environment
   after obtaining a valid key and agreeing to the provider's terms. If
   absent, Windy is `not_configured`, not a false claim of no cameras.
   A global query can return up to 100 nearby webcams and requests at
   most two 50-record pages. Available JPEG previews are fetched afresh
   by exact camera ID for every analysis; no token-bearing URL is saved
   in World Armor or camera watches. Metadata-only webcams without
   an accessible image cannot be analysed; player/embed URLs are **not**
   silently treated as publicly downloadable video streams.
3. **User-supplied public HTTPS media URL** for any publisher providing
   an unauthenticated, direct JPEG, PNG, WebP, MJPEG stream, or supported
   unencrypted MPEG-TS HLS playlist. Arbitrary camera URL/host is a
   *single user-enrolled exact target*, not an IP scanner or a
   global automatic catalog. A landing page/JavaScript player, signed
   cookie, login, private RTSP feed, DRM HLS, WebRTC, SRT and fMP4
   are NOT automatically supported. A bounded **single-page HTML
   discovery** step can list literal public image/HLS links (including
   provider thumbnails) from the exact page the operator supplies,
   without running scripts, following iframes or fetching media. The
   operator explicitly selects a candidate before analysis; a player
   page or thumbnail is not proof of live-feed access.
4. **One-frame local vision:** the already configured Ollama vision
   model describes a single bounded frame or returns an optional typed
   `smoke_visible`/`road_congestion` classification. It does
   not identify people, licence plates, particular vehicles or
   claim a confirmed fire, collision or present road safety.
5. **World Armor public-camera evidence sidecar**: within a
   user-enrolled region and a separate explicit
   `JARVIS_WORLD_ARMOR_CAMERAS_ENABLED=1` gate, inspect one cataloged
   camera whose *reported camera coordinate* is inside the region,
   or associate an exact user-supplied public URL with the region
   with **unknown camera geography**. Up to 40 local text/hash
   receipts per region, cascade on region Forget/expiry, individually
   forgettable. Exact sample image hash, image/source type, retrieval
   time, optional condition and model result are stored. No raw
   JPEG/video or signed media URL is stored in World Armor.
6. **Existing External Watches extended:** camera watches can now
   enroll exactly one official Caltrans ID, one Windy ID or one vetted
   explicit public URL, plus an optional smoke/congestion predicate.
   The host's already existing external-watch scheduler is separate
   from the World Armor AQI/USGS/NWS watch runner. Existing 15-minute
   minimum cadence, fixed expiry and two distinct positive frame
   requirement are retained. The iPhone/iPad workbench exposes an
   explicit "Watch exact camera · 3h" button. This external watch's
   history is NOT yet automatically synchronized with the World Armor
   evidence sidecar.
7. **Native World Armor iPhone/iPad interface:** search actual catalog
   sources; read coverage status; select a specific camera; optionally
   preview its published still; paste a direct public media URL; inspect
   and store an evidence receipt; explicitly enroll/stop a separate
   time-limited camera watch; read/forget camera receipts.

## Media safety and compatibility

- Every direct-media HTTP request validates the exact URL and resolves
  its DNS; ALL returned addresses must be global IPs. Requests are
  made to a vetted **pinned socket address** while TLS SNI and
  certificate validation still use the original hostname.
- Only HTTPS port 443, no credentials embedded in URLs, no local
  hosts or IP literals, no automatic redirects, no environment proxies,
  no arbitrary camera guessing or discovery via port scanning.
  User-supplied token/password/API-key query parameters are rejected.
  Windy signed preview URLs come only from the authenticated
  provider adapter and are refreshed rather than persisted.
- Image downloads max 3 MB, HTML/JSON/video/error pages are never
  treated as images, decoded input max 12 megapixels, MJPEG stops
  after one complete JPEG, no passive stream recording.
- HLS supports the most recent two same-host MPEG-TS segments up
  to bounded byte budgets; decoding is through an optional
  **locally installed FFmpeg** on stdin, with network protocols
  disabled. Encryption, fMP4/map, byte ranges, cross-origin
  segments and manifests nested beyond one variant fail explicitly.
  A compatible HLS URL can still be unavailable or fail to yield
  a decodable frame. No provider access bypass is attempted.
- Publisher-reported service/updated status is not verified image
  capture time. For all captured images, `capture_time=null`.
  Model judgement on successive different image hashes is **not**
  independent confirmation of a newly occurring physical event.
- A reported camera GPS point is not its viewing polygon. A direct
  URL manually associated with a region has no provider-verified
  geographic location at all.
- Camera observations remain **receipt-time-only in a dedicated
  sidecar**, not faked as source-timed independent observations
  inside World Armor's AQI/NWS/USGS correlation or attention inbox.
  Linking watches, timestamp verification and stronger
  cross-domain hypotheses are separately unfinished.

## Private API

Under the existing private bearer gate, all with
`Cache-Control: private, no-store`:

- `POST /world-armor/v1/cameras/page-media` with
  `{"public_url":"<one public HTTPS page URL>"}` returns up to
  15 literal media candidates without opening any media, scripts,
  embedded players or arbitrary URLs. Each candidate requires an
  explicit operator selection before fetching a frame.
- `POST /world-armor/v1/cameras/discover` with finite
  `latitude`, `longitude`, `radius_km` (1–250) and
  `limit` (1–100). Includes separate provider statuses.
- `POST /world-armor/v1/cameras/inspect` with
  `investigation_id`, **exactly one of** `camera_ref`
  or `public_url`, and optional `condition`.
- `GET /world-armor/v1/cameras/receipts?investigation_id=<id>`
- `POST /world-armor/v1/cameras/forget` with
  `{"receipt_id":"<id>"}`.

Existing `/external/watch/create` accepts
`kind="camera"` and exactly one `config.camera_id`
(Caltrans), `config.camera_ref` (Windy),
or `config.public_url` (validated direct media), with
`config.condition` optional. Creation never authorizes identity
tracking or raw video archiving.

## Operator setup

```powershell
$env:JARVIS_WORLD_ARMOR_ENABLED = "1"
$env:JARVIS_WORLD_ARMOR_CAMERAS_ENABLED = "1"

# Optional, for Windy global catalog, subject to API terms and account:
$env:JARVIS_WINDY_WEBCAMS_API_KEY = "<your own Windy API key>"

# Optional, only for bounded compatible HLS MPEG-TS streams:
ffmpeg -version
```

Windy v3 official docs:
https://api.windy.com/webcams/docs
and terms:
https://api.windy.com/webcams/terms.
The provider documents that free-tier signed preview URLs expire quickly,
so the adapter re-resolves them on each selected camera check. Free-tier
image size and rate limits may constrain vision quality. Global directory
coverage does not make every listed webcam operational or reuse-permitted.

**Validation:** synthetic pytest/unittest and iOS simulator show code
correctness, not live real-world provider rights/coverage, actual HLS
decode or successful installed-jarvis checks. Before production,
review individual camera/provider terms and source attribution,
launch the installed Windows backend, confirm Caltrans live still,
a valid Windy key in at least two international locations, a known
public still/MJPEG/HLS URL, off/expiry/forget/failure behaviour, and
camera watch stop-during-HTTP on the actual host.
