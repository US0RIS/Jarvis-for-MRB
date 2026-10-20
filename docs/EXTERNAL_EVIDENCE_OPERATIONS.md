# External evidence, remote perception and scoped diligence

> Status: source implementation on `jarvis/memomind-prep`, PR #2. No claim of deployment or physical iPhone/Gen 1 Meta acceptance. All observations are **source-specific**; absence of an observation is not a safety, compliance, or sanctions clearance.

## Deployment

Install the latest `jarvis/memomind-prep` branch on the Windows backend and build/reinstall the iPhone app from the **same branch**. The original `jarvis/agency-1.0` backend does **not** serve these endpoints. The standard iPhone **Physical** tab requires no MemoMind. The existing Gen 1 Ray-Ban Meta microphone/speaker route can trigger explicitly supported voice commands; the lenses cannot render a HUD. The MemoMind simulator and future driver remain optional.

For SEC lookups, set an identifying contact user-agent on the backend **before starting Jarvis**:

```powershell
$env:JARVIS_SEC_USER_AGENT = "JarvisPersonal your-real-contact@example.com"
py -3.14 -m jarvis_mrb.service
```

Use a real identifying contact (not the placeholder); configure a persistent environment variable in Windows if Jarvis normally starts through its on-logon task. Do **not** put client identities, deal code names, confidential document contents or matter identifiers into that user-agent.

Recommended activation sequence: start backend, verify `GET /health` includes `external_watches: running`, rebuild iPhone, check the normal Physical tab, select a harmless public camera and create an expiring personal watch, explicitly check the source and cancel it. Then, with authority for any professional matter, create a **local isolated matter**, enter a verified exact SEC CIK, and run a one-time independent evidence check.

## Supported sources and scope

| Surface | Actual integration | Not implemented / not implied |
|---|---|---|
| Public remote eyes | Caltrans CWWP2 statewide district catalogs, public still URLs, explicit still-image Moondream evaluation, named-place-to-coordinate MapKit resolution on iPhone | Worldwide camera catalogs, EarthCam automation, ALERTCalifornia machine access, proprietary/city safety CCTV, arbitrary webcam URL scraping or generic IP scanning |
| Standing camera watch | Opt-in, <=7-day expiry, selected official Caltrans ID, >=15-minute interval, optional smoke/congestion classifier; only reports *possible* visible condition after two distinct JPEG/PNG image hashes with conservative positive classifications | Verified image capture time or camera field-of-view; continuous video streaming/archival; detecting an actual fire, road clearance, person, license plate or emergency |
| Incidents | USGS recent earthquake GeoJSON near explicit coordinates; NWS point alerts for supported US locations | PulsePoint/911, dispatch, police/fire/evacuation, global government weather alert feeds, tsunami guarantees, NASA FIRMS (not yet wired), all-hazards safety assessments |
| Airspace | OpenSky bounding-box anonymous regional aircraft **count**, time checked and provider timestamp, bounded quota usage | Global full coverage, AIS shipping, person/counterparty travel correlation, flight passenger identification, aircraft/jet owner inference, unlimited free polling |
| Environmental/context | Global modelled air/UV via Open-Meteo/CAMS, worldwide OSM public facility finder, iPhone MapKit routing | Street-level sensor measurements everywhere; emergency-grade AED availability/hours or guaranteed map coverage |
| Deal diligence | Exact-CIK SEC submissions, exact XBRL taxonomy/concept/period/unit numeric candidate comparisons; exact user-linked EPA ECHO FRS facility snapshots; opt-in local primary-name OFAC SDN candidate review; explicit optional project/world term ledger reference | PACER/court docket, UCC filings, county deeds, corporate registries, OSHA databases, SDN aliases/non-SDN/ownership sanctions clearance, comprehensive target-company perimeter search, legal conclusions |

Official source documentation:
- Caltrans: https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm
- USGS: https://earthquake.usgs.gov/fdsnws/event/1/
- NWS: https://www.weather.gov/documentation/services-web-alerts
- OpenSky: https://openskynetwork.github.io/opensky-api/rest.html
- Open-Meteo: https://open-meteo.com/en/docs/air-quality-api
- SEC: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- OFAC: https://ofac.treasury.gov/sanctions-list-service
- EPA ECHO: https://echo.epa.gov/tools/web-services

OpenSky anonymous access has quotas. Open-Meteo's no-cost offering is not a general commercial licence; independently confirm any provider's applicable terms before production/commercial use. Camera catalog metadata does not prove the still image is timely or working.

## Watch and evidence model

The dedicated local `external_watches.sqlite3` database stores explicit watches and the **last 100 distinct source observations** per watch. Source URL, retrieval time, source event/capture time if available, signed digest, summary, checked/status and baseline-vs-change are kept separate. The general world graph gets personal-watch metadata-only events; **matter-scoped watch data is not mirrored** into the general world graph.

A watch starts with a *baseline*, not a change alert. A provider timeout, empty/unavailable source, stale OpenSky sample, unsupported NWS geography, or image-vision parse uncertainty must not become a false positive/false clearance. The camera detector requires two distinct source images to be positively classified. It is still ML-derived **candidate evidence**, not a verified incident. Watches are expressly enrolled, bounded by cadence, and expire after <=168 hours; they can be stopped in the iPhone app. The backend scheduler handles at most two due watches per minute and is not a continuous surveillance engine.

Endpoint families are all authenticated with the existing Jarvis bearer token:

```text
POST /physical/public-cameras
POST /physical/public-cameras/analyze
POST /physical/awareness
POST /physical/conditions
POST /physical/facilities
POST /physical/incidents
POST /physical/airspace

POST /external/watch/create
POST /external/watch/list
POST /external/watch/check
POST /external/watch/history
POST /external/watch/stop

POST /external/diligence/list
POST /external/diligence/matter
POST /external/diligence/issuer
POST /external/diligence/epa-facility
POST /external/diligence/claim
POST /external/diligence/view
POST /external/diligence/check
POST /external/epa/facility
```

An `external/watch/create` camera payload is `{"scope":"personal","kind":"camera","label":"Mountain pass","config":{"camera_id":"caltrans-d7-196","condition":"smoke_visible"},"interval_seconds":900,"expires_hours":24}`. Replace camera ID with one actually returned by the Caltrans catalog. Conditions supported: `smoke_visible`, `road_congestion` or empty/no condition. Existing watcher and iPhone screens offer more guided controls.

SEC matters are stored separately in `matter_diligence.sqlite3`. A professional user must explicitly create a matter, specify an actual verified CIK for each issuer, optionally link a verified FRS facility ID, and quote an identified source for a numeric claim. No private deal terms/names are posted to SEC, EPA, or OFAC: the SEC gets only exact public CIK/concept; EPA gets FRS ID; OFAC list is downloaded, then exact candidate-name review happens locally. Links from corporate names to subsidiaries, beneficial ownership and source assertions are **never inferred as settled identity**. Numerical XBRL differences are candidate discrepancies requiring accounting/legal/context review, not adverse factual conclusions.

Privacy boundary: the matter/watch databases are logically separated on the same Windows host, **not an independent cryptographic or per-user access control domain**. Every authenticated caller to this single-user Jarvis backend can access the endpoints unless further user/matter authorization is implemented. Do not use these prototype endpoints for restricted client data on a shared endpoint or without required institutional review and authorization.

## Commands and examples

- “Jarvis, establish situational awareness” checks the sources integrated at the **phone's** current location.
- “Jarvis, find nearby public cameras”; “Jarvis, analyze the nearest public camera” operate on a deliberately discovered Caltrans still.
- “Jarvis, watch the nearest public camera for smoke” establishes a 24-hour expiring watch with conservative two-image candidate alerts. Inspect and stop it under **Physical → Remote observation and standing watches**.
- To select somewhere else on Earth, use **Physical → Remote observation and standing watches**, resolve a place in MapKit or enter lat/lon, browse official cameras for that remote region, and enroll relevant public-source watches. A region with no integrated camera provider truthfully shows no feed rather than guessing camera access.
- **Physical → Independent public-record diligence** is the explicitly authorized, local matter-specific SEC/EPA/OFAC workbench.

## Unfinished integration gates

Live-provider smoke tests must verify actual response schemas, redirect hosts, API quotas, data currency and account/licensing terms. Physical iPhone, Gen 1 Ray-Ban audio, a real authenticated remote connection, HomeKit effects, Windows on-logon daemon behavior and real client-data isolation require separate acceptance. GitHub simulator/source CI validates compilation and synthetic contracts only; do not treat that as operational deployment.

Further integrations need individually verified permitted interfaces: ALERTCalifornia/other official webcams, NASA FIRMS, Australian official incident/transport sources, authorized AIS provider, PulsePoint where redistributable, PACER/state courts/UCC/county/corporate registry/OSHA coverage, parent-subsidiary ownership resolution and workflow-specific client data governance.
