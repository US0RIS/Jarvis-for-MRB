# Future Ideas

An unordered scratchpad of feature ideas for Jarvis. Nothing here is scoped,
scheduled, or committed to — this is a place to dump ideas before they're
lost, not a roadmap. Move an idea out of this file and into a real design
doc (or just implement it) once someone decides to act on it.

## Proactive / situational awareness

- **Push, don't pull, the pre-meeting brief.** Situation Evidence already
  fuses Guardian watches and Life Fabric deadlines into a meeting prebrief,
  but it only answers when asked ("anything I need to know before I go
  in?"). Have it push a spoken/notification brief automatically N minutes
  before each calendar event instead of waiting to be queried. This is the
  core "persistent system, not a chatbot" thesis — a should-have, not a
  nice-to-have.

- **Bind calendar events to exact Reality Lens coordinates.** The README
  already flags that calendar events aren't bound to exact coordinates.
  Closing this gap unlocks real geofenced behavior ("you're 12 minutes from
  the office, meeting starts in 10") that currently can't happen because
  location and event are disconnected.

- **Real-time Guardian alerting, not just read-only evidence.** Situation
  Evidence explicitly does not run a Guardian alert or infer all-clear
  today. Turning Guardian from a queryable evidence source into a proactive
  alert path is probably the single highest-leverage unimplemented
  capability given how much infrastructure already points at it.

- **Health-aware scheduling flags.** Health data is already opt-in.
  Correlating sleep/activity with the day's calendar to flag something
  like "you slept 4 hours and have a 9am with the board" would put
  existing data to genuinely differentiated use.

- **Indoor / place-of-context awareness.** Independent of the Iron Man demo
  below, the underlying gap it surfaced is real: Jarvis often can't answer
  "what is this place / what room am I in." Worth treating as its own
  gap to close, tied to the calendar-coordinate binding item above.

## Email / admin automation

- **Email triage + drafted replies awaiting approval.** `email_policy.py`
  and the action-verification infrastructure already exist. Have Jarvis
  draft replies to routine emails and flag anything needing a real
  decision, never sending without explicit confirmation — fits the
  existing authority-boundary design rather than introducing a new one.

- **Post-meeting action-item extraction → Life Fabric task creation.**
  `meeting_notes.py` and the Life Fabric ledger both exist independently;
  wiring them together means a meeting ending automatically seeds
  follow-up tasks/deadlines instead of manual re-entry.

- **Subscription/renewal and bill tracking from email receipts.**
  `expense_tracker.py` exists but sounds manually fed today. Auto-scanning
  Gmail for receipts and renewal notices directly serves the "reduce five
  years of ordinary friction" Life Fabric goal and is likely one of the 17
  life-friction catalog domains still unimplemented.

## Interaction model / UX (inspired by the Roblox "Iron Man Legacy" Edith
glasses demo — combat mechanics dropped, the underlying UX patterns kept)

- **"What can you do?" self-describing capability statement.** Support a
  literal voice command — "Jarvis, what can you help me with right now?"
  — that introspects the currently enabled tools/permissions and states
  them aloud, rather than requiring the user to already know what's wired
  up. Cheap, and useful given how many optional subsystems exist
  (Guardian, Life Fabric, calendar, email).

- **Nearest-obligation glanceable HUD.** A "what's nearest/next" panel —
  nearest calendar event, nearest geofenced place of interest, nearest
  Life Fabric deadline — surfaced passively on the MemoMind display or
  phone home screen instead of requiring a query.

- **Passive system status indicators.** Persistent glanceable status for
  "PC host reachable," "phone sensors syncing," "last world-model sync,"
  pulled from existing `runtime_health.py` / `resource_monitor.py` data
  that's already collected but not surfaced passively today.

- **Action tray / quick-action palette.** A small customizable set of
  one-tap actions — "log expense," "draft reply," "start meeting notes,"
  "mute proactive alerts" — instead of routing everything through
  conversation.

- **Explicit, guaranteed "stop talking" barge-in command.** A real,
  instant, always-available interrupt for proactive narration, distinct
  from simply not responding.

- **Named preset/loadout invocation.** "Jarvis, set up my [focus mode /
  commute / meeting] loadout" triggers a bundle of existing actions (DND,
  relevant docs pulled up, calendar context loaded) instead of asking for
  each one separately.

- **Context-gated capability sets.** Certain actions auto-disable in
  certain contexts (driving, in a meeting) rather than relying on the user
  to remember not to ask — a legitimate extension of the existing
  authority-boundary design.

- **Command-center / world-model dashboard as a real destination view.**
  Not just query-driven — a standing view showing aggregate state at a
  glance, similar in spirit to a base-of-operations screen.

- **Gamified progress on mundane admin tasks.** Visible progress +
  completion reward could make the Life Fabric checklist grind (the
  five-year friction catalog) noticeably less tedious than a plain task
  list.

## Cross-device / continuity

- **Cross-device continuation for general productivity, not just Life
  Fabric.** Life Fabric already claims cross-device continuation packets
  for its own workflows; extend the same mechanism to general tasks so
  work started on phone can resume on PC (or vice versa) without manual
  handoff.

## Severe weather / physical safety (from an El Niño discussion with Gemini)

- **Ingest NWS Impact-Based Warnings (IBW) feeds.** NWS Flash Flood
  Warnings carry explicit damage tags (`CONSIDERABLE` or `CATASTROPHIC`).
  Parse these tags in the adapter payload to instantly escalate alerting
  priority instead of treating every flash flood warning the same
  regardless of severity.

- **Ingest California Geological Survey (CGS) and USGS slope data.** Map
  the immediate neighborhood's slope steepness and landslide-susceptibility
  zones. If an observation node sits in a high-susceptibility zone, halve
  the rainfall-rate alert threshold there rather than applying one
  blanket threshold everywhere.

- **Local failover alerting.** Push local notifications via a physical
  buzzer, a local-network webhook, or loud sound output on a home machine
  when `CRITICAL` conditions are reached, so the alert still lands even
  if cellular networks or the power grid go down during a severe storm —
  the phone-push path alone isn't enough for the exact scenario it's
  meant to cover.

## Physical/sensor world providers (more integrations in the Caltrans-adapter shape)

Same pattern as the existing Caltrans CWWP2 camera provider throughout:
official/public source, allowlisted host, cached catalog, bounded fetch,
explicit "possible condition" framing rather than a certainty claim.

- **More state DOT camera feeds** (WSDOT, TxDOT, NYSDOT, etc.) — the
  README already names this as the obvious next step.
- **ALERTWildfire public camera network** — wildfire-observation cameras,
  same "possible visible condition, not a confirmed incident" framing
  already used for smoke classification.
- **Harbor/coastal webcams** from NOAA/port authorities, for "is that
  beach crowded / is the pass open" queries the README already names.
- **NOAA/NDBC marine buoy data** — wave height, wind, water temp near a
  coordinate. Same shape as the existing USGS/OpenSky adapters: public,
  read-only, timestamped, no fabricated coverage claims.
- **PurpleAir / AirNow air-quality sensors** — a real local AQI reading
  instead of the existing modelled/global air-data estimate.
- **GTFS-realtime public transit feeds** — bounded and official, and
  directly useful for Situation Evidence's meeting-prebrief logic
  ("your train is delayed 12 minutes").
- **FAA NOTAMs** — same risk profile as the existing OpenSky
  aircraft-count adapter, one step further (why airspace near you is
  active, not just a count).
- **Smart plugs/switches via HomeKit** — lowest-risk actuation, same
  authorization/grant/readback model already specified for the planned
  HomeKit lights in EDITH Field Ops.
- **A second CrunchLabs-style bench sensor node** — not a camera, a
  small authenticated physical sensor (temperature, door-open, humidity)
  reporting into the world model as another observation source,
  extending the pattern the pitch-servo bench already proved out.

Explicitly not in this list, on purpose: thermostats/locks/garage doors
(real safety/security stakes), any private or third-party CCTV, anything
framed as "global" coverage, or actuation without a fresh per-action
grant. See the CCTV boundary-decision note in the README for why.

## Security hardening (defensive, not offensive)

- **Speaker verification for Conductor actions.** Conductor already gates
  real-world effects (opening apps on a paired Mac/Windows host) behind a
  one-use grant, explicit confirmation, and process readback — solid
  mechanics for "was this action authorized and did it actually happen."
  But nothing verifies *whose voice* triggered it; the README already
  names "authenticated speaker identification" as a current gap. Since
  Conductor is the one subsystem with real physical/device-level effect,
  and the one place a voice alone (a recording, a video playing in the
  room, someone else in the house) can currently cause a real side
  effect, closing this gap is higher-leverage than most net-new
  features — it hardens something that already ships.
- **Voice/device-confirmed guardrail before any Jarvis-initiated
  purchase or payment.** Not autonomous trading or spending — the
  opposite: an explicit, non-bypassable confirmation step specifically
  for any action that moves money, on top of the existing authority
  framework.
- **Breach/exposure monitoring for your own enrolled accounts.** Poll a
  service like HaveIBeenPwned's API for your own emails and alert on new
  breaches — a legitimate personal-security use of a public API, distinct
  from OSINT on other people.
- **Stale OAuth/grant audit.** Periodically list what's actually
  authorized against your Google/HomeKit/etc. accounts and flag grants
  unused for N months — turns the project's own authority-boundary
  philosophy into something that audits itself, not just other actors.
- **Post-action audit log.** After any Conductor action or Guardian
  alert, auto-generate a short after-action entry (what triggered it,
  what Jarvis did, verified outcome) into the world model, making the
  existing action-verification trail queryable instead of implicit.
- **Unknown-tracker alerts.** Passively note nearby BLE beacons that
  persist across your movement (the same pattern as Apple's own
  AirTag-stalking alerts), using only broadcast data your phone already
  legally receives — no interception of anyone else's traffic.
- **Your own home-network security posture.** Flag new devices joining
  *your own* Wi-Fi/LAN. Deliberately scoped to your own network only —
  see the discussion in this doc's history for why scanning others'
  networks or intercepting others' traffic is out of scope entirely, not
  just unimplemented.

## Life admin & memory (batch 2)

- **Spending-anomaly detection against your own history.** Not market
  arbitrage — flag a charge that's meaningfully out of pattern versus
  your own past spend. Purely defensive, uses data already ingested via
  `expense_tracker.py`.
- **Contract/lease clause extraction.** `pypdf` and `knowledge_index.py`
  already exist; parse uploaded contracts/leases for renewal deadlines
  and auto-renewal clauses, feeding directly into Life Fabric deadlines
  instead of requiring a manual re-read later.
- **Vehicle maintenance tracking** tied to mileage/date, surfaced through
  the same Life Fabric checklist mechanism as the rest of the friction
  catalog.
- **Package/delivery correlation.** Match shipping-notification emails
  against a door/geofence event to know a package actually arrived, not
  just that a courier claims it did — stays inside "your own email plus
  your own geofence," no new data source required.
- **Ambient "remember this" voice capture** that auto-tags into the
  right world-model entity (person/project) instead of an
  undifferentiated notes pile — makes `memory.py` actually useful
  hands-free, e.g. while driving.
- **Self-hosted backup/failover for your own services.** Ordinary DevOps
  redundancy for infrastructure you actually own — no "evade
  detection/takedown" framing needed, unlike the rejected version of
  this idea.

## More scope (round 3)

- **Meeting document freshness check.** Before a meeting brief goes out,
  cross-check the attached deck/doc against `world_document_versions.py`
  and flag if it changed since you last reviewed it — so the prebrief
  can say "this deck was updated 40 minutes ago" instead of silently
  handing you a stale version.
- **Trip timeline fusion.** Pull flight/hotel confirmation emails into a
  single trip timeline, correlate against weather/wildfire/camera
  coverage at the destination using the existing external-evidence
  adapters, and generate a day-of departure checklist automatically.
- **General action-receipt capture.** Extend the existing
  calendar/Conductor verification pattern to other digital actions —
  online reservations, form submissions — so "did this actually happen"
  has a consistent answer across more than just the two subsystems that
  currently check.
- **Evening wind-down summary.** Correlate end-of-day calendar, open
  Life Fabric tasks, and (opt-in) health data into a short evening
  summary and tomorrow's prep — the inverse of the pre-meeting brief,
  aimed at reducing morning friction instead of walking into a meeting
  blind.
- **Opt-in family safety beacon.** During a user-declared emergency
  window only (not always-on), let enrolled family members' own devices
  report a simple "safe / need help" status to each other — consent-based
  and bounded to a declared window, explicitly not passive location
  tracking of anyone.
- **Unified "ask everything I know" search with source/freshness
  disclosure.** A direct query mode over email, documents, meeting notes,
  and the world model that always states where an answer came from and
  how stale it is, rather than presenting fused evidence as a single
  unsourced fact.
