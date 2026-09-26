# Future Ideas

An deliberately broad, unordered scratchpad of feature ideas for Jarvis. Nothing here is scoped,
scheduled, prioritized, or committed to — this is a place to dump ideas before they're
lost, not a roadmap. Move an idea out of this file and into a real design
doc (or just implement it) once someone decides to act on it.

## Governing principle: go broad to go narrow

Capture **every potentially useful Jarvis feature idea, big or small, before evaluating it**.
Do not omit an idea merely because it seems impractical, duplicative, expensive, futuristic,
low-priority, or outside the current architecture. The purpose of this file is divergent
exploration: maximize the candidate set first; converge later.

Ideas may be tagged with feasibility, dependencies, legal/authorization boundaries, risk, or
implementation notes, but those are metadata rather than reasons to erase the idea. An idea
leaves this dump only when it is promoted into a design/implementation artifact, superseded
with its lineage preserved, or explicitly rejected with a recorded reason. Implementation
must still respect applicable law, consent, authorization, security, and safety constraints.

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

Additional ideas should still be captured here even when they involve higher-stakes devices,
third-party infrastructure, global-scale coverage, or stronger forms of actuation. Their
presence in this idea dump is **not** implementation approval. Record the applicable legal,
consent, authorization, safety, and security constraints alongside them and resolve those
constraints during design review.

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


## Reality / intelligence / agency idea dump

- **Counterfactual Engine / Shadow Reality.** Fork relevant Reality Graph state and simulate
  plausible consequences before acting: travel departure times, infrastructure failures,
  weather trajectories, device changes, scheduling decisions, and other bounded scenarios.
  Preserve uncertainty rather than presenting simulation as prediction.

- **Reality Rewind / physical-world DVR.** Make historical world state queryable as
  `state(t)`: reconstruct what Jarvis observed at a place or around an entity at a past time
  from timestamped sensors, public feeds, device observations, and stored graph history.

- **Reality Diff.** Continuously compute meaningful state changes rather than forcing the user
  to inspect raw observations: object appeared/disappeared, vehicle arrived/left, route
  degraded, flight diverted, webpage changed, device joined/left, crowd level changed, etc.

- **World Assertions / desired-state controller.** Let the user declare durable predicates
  such as "important files exist in two places" or "I don't miss material flight changes."
  Jarvis monitors whether each assertion remains true, proposes or performs authorized
  interventions when it does not, and verifies the resulting state.

- **Reality Compiler.** Compile natural-language intentions into bounded persistent monitors,
  graph nodes, triggers, collectors, UI surfaces, notification policies, verification rules,
  and cleanup behavior. Goal: English -> inspectable world-monitoring program.

- **Universal Object Interface.** Objects perceived through glasses/phone cameras can become
  durable Reality Graph entities associated with visual embeddings, manuals, discovered
  devices/APIs, prior observations, capabilities, and authorized controls. "This is the
  projector" becomes a reusable object binding.

- **Spatial Bookmarks.** "Remember this" stores a place/orientation/visual context/object
  snapshot so physical locations and objects can later be recalled or searched.

- **Physical Ctrl-F.** Search personal spatial memory for objects: "where did I last see the
  screwdriver?" Return last-observed evidence, timestamp, confidence, and location rather
  than pretending current location is known.

- **World Search.** Query live physical-world observations as a search corpus: public cameras,
  environmental sensors, aircraft, ships, transit, weather, user-owned sensors, and other
  lawful/authorized sources. Examples include "show public cameras with visible snow" or
  "aircraft within 20 miles currently descending."

- **Sensor-Fusion Superresolution.** Derive observations that no single feed can provide by
  combining camera/audio/location/maps/weather/ADS-B/AIS/device telemetry and other evidence,
  with provenance and confidence attached to each derived fact.

- **Autonomous Investigation.** "Figure out what's happening" launches a bounded evidence
  investigation across relevant sources, maintains competing hypotheses, seeks
  disconfirming evidence, and returns the best-supported explanation plus uncertainty.

- **Physical Macros.** "Learn what I'm doing" observes a user-performed physical procedure,
  models objects/actions/dependencies/verification states, and later guides repetition or
  performs only those substeps available through authorized actuators.

- **Mission Mode.** Promote a goal/event/trip/project into a temporary attention domain.
  Jarvis automatically binds relevant people, places, messages, documents, reservations,
  sensors, deadlines, world events, and automations; reallocates attention while active;
  then archives the mission cleanly.

- **Closed-loop Outcome Mode.** Generalize the Jarvis control loop to
  Desired World -> Current World -> Difference -> Intervention -> Verification. Keep desired
  outcomes, evidence, authority boundaries, action receipts, and rollback/recovery explicit.

## Small ideas worth preserving too

- **"Why did you tell me this?"** Every proactive interruption can expose the exact evidence,
  rule/assertion/mission, and confidence that caused it.
- **Attention budget.** Give proactive subsystems a shared interruption budget so hundreds of
  monitors do not turn Jarvis into notification spam.
- **Observation TTLs.** Every world fact carries an expiry/staleness policy appropriate to
  its source.
- **Confidence decay.** Inferred physical state becomes less certain as time passes without
  corroborating observations.
- **Contradiction detector.** Flag when two trusted sources disagree rather than silently
  choosing one.
- **Source reputation ledger.** Track empirical reliability/freshness of feeds and sensors
  and use it in fusion confidence.
- **Coverage map.** Visualize where Jarvis can currently see/sense and, equally important,
  where it has no evidence.
- **Capability graph.** Model what Jarvis can observe, infer, or affect for every entity and
  what permission/source enables each capability.
- **Cost-aware sensing.** Prefer cheap/local/cacheable observations and escalate to expensive
  model/API calls only when the expected information gain warrants it.
- **Model router by cognitive difficulty.** Hardcoded functions first, small local models for
  bounded classification/extraction, larger models only for tasks requiring them.
- **Evidence snapshots.** Freeze the exact evidence set behind consequential conclusions so
  later queries can reconstruct why Jarvis believed something.
- **Uncertainty UI.** Make unknown / stale / inferred / directly observed visually distinct
  everywhere, not just in prose.
- **One-command temporary watch.** "Watch this for the next two hours" creates an expiring
  monitor from whatever entity/place/feed is currently in context.
- **Follow-the-entity.** A watch can migrate among lawful data sources as an entity moves,
  rather than being tied to one camera/feed.
- **Automatic watch retirement.** Remove temporary collectors when their mission, assertion,
  or TTL ends.
- **Replayable automations.** Dry-run an automation against historical Reality Graph data
  before enabling it.
- **Failure rehearsal.** Periodically simulate loss of an important provider/device and
  report which Jarvis capabilities silently depend on it.
- **Offline degradation plans.** Each major capability declares what still works without
  Internet, cloud models, phone, home power, or a particular host.
- **World-model garbage collection.** Merge duplicates, retire stale entities, preserve
  provenance, and prevent the graph from accumulating contradictory zombie state.
- **Personal vocabulary/alias graph.** Learn that informal names like "the Porsche," "home,"
  or "Matt's laptop" resolve to specific graph entities, with explicit disambiguation when
  aliases collide.
- **Teach-by-correction.** "No, that's the garage remote" updates an entity binding and
  propagates the correction to dependent memories/inferences with audit history.
- **Temporal questions as a first-class query language.** Native support for before/after,
  since/until, first/last, duration, recurrence, and change-point questions across the graph.
- **World-model bookmarks in conversation.** Any answer can pin its underlying entities,
  time window, and evidence set so a later "what changed since this?" has an exact baseline.
- **Reality Graph debugger.** Inspect why an entity/edge exists, which observation created
  it, which inference transformed it, and what would invalidate it.


## Internet idea-mining — 2026-09-26

Ideas synthesized from discussions among Home Assistant, LocalLLaMA, Obsidian,
self-hosting, smart-glasses, and personal-assistant users. These are deliberately
captured before prioritization.

- **Contextual Delivery / Follow-Me Information.** Treat every reminder, alert, answer,
  and proactive observation as a routable information object with recipient, urgency,
  expiry, prerequisites, privacy level, and acceptable surfaces. Deliver it where the
  intended person actually is; defer it if the current context makes it unactionable;
  migrate it across room speakers, glasses, watch, phone, desktop, car, and displays.
- **Ambient Output Fabric.** Do not equate "Jarvis wants to tell me something" with a
  phone notification. Choose among speech, HUD text, watch complication, desktop
  overlay, e-paper/room display, light/state cue, phone notification, or silence based
  on urgency and context. Prefer the least intrusive channel that conveys enough
  information.
- **Social Context Modes.** Make social situation a first-class world state: alone,
  family, guest, babysitter, dinner party, meeting, public, confidential-work, sleep,
  driving, etc. Globally alter narration, visible information, sensing behavior,
  permissions, proactive thresholds, and automations accordingly.
- **Temporary Delegated Capability.** Generate scoped, expiring capabilities for a
  guest/family member/collaborator to control or query only specified Jarvis entities
  without receiving full Jarvis access. Include expiry, revocation, rate limits, and
  audit trail.
- **Presence-as-Invocation.** Wake words are only one trigger. A person entering a
  relevant place, looking at an object, beginning a known routine, picking up a device,
  or a state transition can open a conversational opportunity when policy permits.
- **Conversation Handoff.** Begin a conversation on glasses, walk into the car, and
  continue it there; move to the desktop and let visual output expand automatically
  without restarting context.
- **Interruptibility as a primitive.** Guaranteed low-latency barge-in everywhere:
  stop, pause, correct, shorten, change output device, or redirect an executing plan.
- **Zero-Friction Capture Bus.** Any input—spoken fragment, screenshot, photo, URL,
  currently playing media, selected text, file, location, object, or gesture—can be
  dumped into Jarvis in one action. Jarvis timestamps it, preserves raw source,
  associates current context, and organizes later rather than demanding metadata at
  capture time.
- **Capture Current Context Automatically.** When saving a thought, optionally attach
  what was playing/on-screen, current app/document, location/place, active mission,
  nearby graph entities, and recent conversation so a fragment remains intelligible
  months later.
- **Automatic Connection Discovery.** Periodically find non-obvious semantic,
  temporal, spatial, causal, and people/project connections among captured material.
  Suggest links rather than silently rewriting the user's knowledge.
- **Memory Promotion Pipeline.** Separate raw episodic captures from durable facts,
  preferences, procedures, and project knowledge. Repeated/corroborated information
  can be proposed for promotion; contradictions trigger review.
- **Memory Provenance + Revision.** Every remembered fact points back to the
  observation/message/document that produced it and supports correction, supersession,
  expiry, and confidence.
- **Routine Learning Without Programming.** Detect repeated sequences across device,
  location, calendar, home, and application state and ask whether they should become a
  macro/automation. Learn conditions and exceptions from demonstrations.
- **Counterfactual Automation Testing.** Before enabling a learned automation, replay
  it over historical context and show when it would have fired, including likely false
  positives and annoying edge cases.
- **Behavioral Automation Success Metrics.** Measure whether proactive nudges are
  useful: acted on, dismissed, snoozed, overridden, or repeatedly ignored. Adapt
  thresholds and retire low-value behaviors rather than letting automation accumulate.
- **Falsifiable Proactivity.** A proactive interruption must be able to state the
  concrete evidence and opportunity that justified interrupting now; default to
  silence when the case is weak.
- **Opportunity Detector.** Look for actionable gaps, not merely deadlines: calendar
  gap + nearby errand, destination + low vehicle range, good outdoor conditions +
  pending task, upcoming meeting + unread relevant document, etc.
- **Obligation Extraction.** Continuously convert commitments hidden in email,
  messages, documents, calendar entries, receipts, and conversations into an evolving
  obligation graph with owner, deadline, dependencies, evidence, and status.
- **Auto-Resolving Tasks.** Tasks can complete themselves when reality proves the
  underlying condition happened (device begins charging, package arrives, form
  submission receipt appears, location reached), instead of requiring checkbox labor.
- **Condition-Relative Recurrence.** Support "30 days after I actually changed the
  filter" rather than only calendar recurrence.
- **Preparation Engine.** Work backward from future events to required state:
  tomorrow's destination + vehicle range -> charge tonight; weather + clothing/task;
  flight + traffic + parking + security -> departure time; meeting + document changes
  -> review prompt.
- **Reversible First Response.** For high-consequence anomalies, identify and perform
  only pre-authorized, reversible damage-limiting actions first, then escalate to the
  user. Example class: stop a process, isolate a device, pause an automation, close an
  authorized utility valve, preserve evidence.
- **Invariant Watchdog.** Critical safety/reliability conditions are checked as state
  invariants, not only edge-triggered events. Re-evaluate them at startup, reconnect,
  sensor recovery, and periodically so Jarvis cannot miss a bad state that began while
  it was offline.
- **Critical-Sensor Redundancy.** Allow multiple independent sensors/providers to back
  important assertions; detect disagreement, degraded coverage, dead batteries, stale
  readings, and common-mode dependencies.
- **Failure-State Awareness.** "No alert" is not equivalent to "all clear." Every
  monitor knows whether it currently has enough live evidence to make its assertion.
- **Automation State Machines.** Replace sprawling independent IF/THEN rules with
  explicit contextual states and permitted transitions for home, missions, trips,
  routines, devices, and other domains.
- **State Restoration.** Temporary automation changes remember the prior state and
  restore it afterward rather than assuming a hardcoded default.
- **Personalized Environment Profiles.** Environment follows the identified/authorized
  person: preferred display density, audio level, temperature, lighting, privacy,
  notification style, and accessible controls, while resolving multi-person conflicts.
- **World-Aware Media.** Playback can follow the user across rooms/devices, adjust for
  ambient noise, pause when conversation begins, preserve position, and choose a
  suitable output surface automatically.
- **Physical Status Vocabulary.** Subtle physical cues (light pattern, e-paper icon,
  watch complication, HUD glyph) can represent persistent low-urgency Jarvis state
  without speech or push notifications.
- **Multi-Modal Escalation Ladder.** Alerts escalate across surfaces only if not
  acknowledged or if the underlying condition worsens; acknowledgement on any surface
  cancels redundant noise elsewhere.
- **Personal Digital Twin for Mundane Work.** Maintain enough structured context about
  ongoing obligations, communication patterns, files, calendar, and preferences to
  prepare routine work and propose actions without re-explaining context each time.
- **Local-First / Cloud-Escalation Router.** Deterministic code handles known tasks;
  cheap/local models handle bounded extraction/classification; stronger local/cloud
  models receive only the context necessary for difficult reasoning. Latency,
  privacy, cost, and capability are routing inputs.
- **Offline Capability Manifest.** Jarvis can answer "what can you still do right now?"
  based on actual connectivity, available hosts/models/sensors, cached data, and
  permissions rather than a static feature list.
- **Self-Healing Integrations.** Detect broken automations/providers, identify likely
  API/schema/device changes, test a repair in a sandbox/dry run, and propose or apply
  authorized repairs with rollback.
- **Automation Dependency Map.** Show which seemingly small device/API/provider
  failures would disable important higher-level capabilities.
- **Physical Consequence Graph.** Encode downstream consequences of failures/actions
  (e.g. leak -> water damage; low EV range -> tomorrow's trip risk) so attention is
  prioritized by expected consequence rather than novelty.
- **Useful Boredom Detector.** During genuinely idle windows, surface one high-value,
  context-appropriate task that fits the available time/place/tools instead of a
  generic to-do list.
- **Micro-Opportunity Bundling.** Combine several nearby low-cost actions into one
  suggestion: "You're already near X and have 18 free minutes; Y and Z can both be
  completed here."
- **Personal Friction Miner.** Analyze repeated manual corrections, app switching,
  dismissed prompts, recurring searches, repeated commands, and repeated sequences to
  propose new Jarvis features/automations automatically.
- **"Why isn't this automatic?" log.** A one-command capture specifically for moments
  of friction. Jarvis records the surrounding state and later clusters these moments
  into candidate features.
- **Capability Gap Detection.** When Jarvis repeatedly cannot complete a class of
  requests, aggregate failures and propose the missing sensor, API, permission,
  deterministic function, or UI primitive that would unlock them.
- **Feature-Idea Harvester.** Periodically mine opt-in public discussions, project
  issues, changelogs, and the project's own failed requests for candidate Jarvis
  capabilities and append evidence-backed ideas to a review queue before future.md.


## Adjacent-field idea mining — 2026-09-26

Concepts translated from ubiquitous computing, emergency management, intelligence
analysis, SRE/distributed systems, industrial control, accessibility, AR/spatial
computing, end-user programming, and personal knowledge management.

### Attention, command, and situational awareness

- **Attention Commander.** A Common Operating Picture can become useless when every
  subsystem competes to put its information on screen. Give Jarvis a single explicit
  arbitration layer that decides what deserves scarce visual/audio/HUD attention now,
  why, for how long, and what gets demoted. Missions and emergencies can temporarily
  change the arbitration policy.
- **Dynamic Common Operating Picture.** Instead of one giant dashboard, synthesize a
  temporary operational view around the active question/mission: only relevant map
  layers, entities, timelines, dependencies, alerts, cameras, people, and controls.
  Tear it down or archive it when the situation ends.
- **Information Triage Officer.** When a situation produces too much evidence, rank
  information by decision relevance, novelty, confidence, consequence, and time
  sensitivity—not merely timestamp.
- **Decision Window Detection.** Distinguish facts that are merely interesting from
  situations where a decision must be made before a closing window; escalate the latter
  as the window shrinks.
- **Operational Tempo.** Infer whether a situation is stable, accelerating, resolving,
  or becoming chaotic and adjust refresh rates, model allocation, notification
  thresholds, and display density accordingly.
- **Cognitive-Load Governor.** Estimate current interaction burden from driving,
  conversation, meetings, active alerts, task switching, and device use; compress or
  defer nonessential information until capacity returns.
- **Sterile-Cockpit Mode.** During high-workload/high-consequence intervals, suppress
  unrelated Jarvis chatter and low-priority actions automatically while preserving
  critical exceptions.
- **Mode Annunciation.** Jarvis always makes consequential mode/state changes visible
  enough to avoid "automation surprise": what mode it is in, what it is currently
  controlling, and what changed the mode.
- **Automation Surprise Detector.** Detect when observed system behavior diverges from
  the user's likely mental model or the declared automation state and proactively
  explain the discrepancy.
- **Return-to-Manual Handoff.** If automation loses required evidence/capability, make
  the handoff explicit: what stopped being automated, what state it left behind, and
  what the user now needs to control manually.

### Intelligence-analysis primitives

- **Analysis of Competing Hypotheses (ACH) Engine.** For ambiguous investigations,
  explicitly enumerate plausible hypotheses, map evidence for/against each, weight
  source reliability, seek disconfirming evidence, and show what observation would
  most distinguish the remaining possibilities.
- **Key-Assumption Register.** Important plans/inferences expose the assumptions they
  depend on. Jarvis watches for evidence that invalidates an assumption and can
  automatically reopen the conclusion.
- **Disconfirm-Me Mode.** Given a conclusion, deliberately search for evidence that
  would make it wrong instead of gathering only corroboration.
- **Evidence Diagnosticity Scoring.** Prefer evidence that separates hypotheses over
  evidence that is merely consistent with all of them.
- **Information-Gain Planner.** When uncertain, choose the next lawful/authorized
  observation or query expected to reduce uncertainty the most.
- **Source Independence Graph.** Detect when five apparently separate reports all trace
  back to the same original source so corroboration is not overstated.
- **Claim Lineage.** Any synthesized claim can expand into its chain:
  raw observation -> extraction -> inference -> corroboration -> conclusion.
- **Assumption Expiry.** Assumptions have freshness windows and must be revalidated
  when circumstances materially change.
- **Collection Plan Generator.** For a question Jarvis cannot yet answer, construct an
  explicit evidence collection plan identifying missing facts, available sources,
  expected value, cost, and stopping conditions.
- **Investigation Stop Rule.** Prevent endless research by defining what confidence,
  evidence, or decision threshold is sufficient for the actual decision at hand.
- **Alternative-Explanation Prompt.** Before a high-impact conclusion, generate at
  least one materially different plausible explanation and test it.
- **Analytic Confidence Calibration.** Track whether prior confidence estimates proved
  justified and recalibrate future language/thresholds by domain.

### Reliability / SRE / distributed-system ideas

- **Jarvis Reliability SLOs.** Define measurable reliability objectives for important
  capabilities: command latency, observation freshness, alert delivery, action
  verification, sync convergence, and availability.
- **Capability Error Budgets.** Track tolerated failures/staleness for each capability;
  repeated budget exhaustion automatically shifts engineering attention from adding
  features to reliability.
- **Automation Ownership Registry.** Every automation declares purpose, owner,
  dependencies, credentials/permissions, trigger, side effects, rollback, last test,
  and retirement condition so the system never accumulates mysterious jobs.
- **Automation Maintenance Cost Meter.** Estimate how much operational complexity an
  automation creates versus the human effort it saves; flag automations that have
  become net-negative.
- **Runbook Compiler.** Turn a successfully resolved incident/problem into an
  inspectable deterministic runbook, preserving decision points that still require
  judgment.
- **Human-Fix Memory.** Correlate anomaly telemetry with what the human actually did to
  resolve it. When the same pattern recurs, surface prior successful interventions and
  differences from the previous case.
- **Recurring-Failure Clustering.** Detect that superficially separate incidents are
  manifestations of the same underlying pattern across time/devices/services.
- **Known-Good State Snapshots.** Preserve enough configuration/state to compare a
  malfunctioning system against its last verified healthy state.
- **Change-Correlation Engine.** When something breaks, automatically identify nearby
  software/config/device/network/environment changes that plausibly preceded it.
- **Canary Actions.** Before applying a broad Jarvis-generated change, test the action
  on the smallest safe scope and verify outcome.
- **Progressive Rollout.** Expand a successful action gradually across devices/rules/
  environments with automatic halt on anomalous results.
- **Automatic Rollback Contract.** Actions can declare measurable success conditions
  and a reversible rollback that executes if those conditions fail.
- **Chaos Jarvis.** In a safe simulation/test environment, intentionally remove
  providers, hosts, network links, sensors, models, and permissions to discover hidden
  single points of failure before reality does.
- **Graceful-Degradation Planner.** Precompute substitute paths when a capability
  disappears: alternate model, alternate device, cached map, SMS instead of data,
  local sensor instead of cloud provider, etc.
- **Split-Brain Detector.** Detect when different Jarvis nodes hold incompatible world
  state or believe different authorities are active.
- **Eventual-Reconciliation Ledger.** Offline nodes may continue recording observations
  and safe local actions; when connectivity returns, merge histories with explicit
  conflict handling rather than treating the cloud copy as automatically correct.
- **Local Mesh Sync.** Let nearby Jarvis devices exchange relevant state directly over
  LAN/Bluetooth/ad-hoc links when Internet/cloud services are unavailable.
- **Long-Now Export.** Maintain a documented, portable representation of core memory,
  graph state, automations, and provenance so Jarvis remains recoverable even if a
  vendor/service/project disappears.

### Industrial-control lessons

- **Alarm Rationalization.** Periodically analyze alert frequency, duration,
  acknowledgment, consequence, and usefulness; identify nuisance alarms, duplicate
  alarms, permanently active alarms, and alerts that never change behavior.
- **Alarm Flood Mode.** When many alerts share one likely cause, collapse them into the
  causal incident rather than independently interrupting for every symptom.
- **First-Out Analysis.** In cascades, preserve and highlight the earliest meaningful
  state change that likely initiated the downstream alarm storm.
- **Intervention Timeline.** For any physical/digital entity, show telemetry, alerts,
  human actions, Jarvis actions, maintenance, configuration changes, and outcomes on
  one timeline.
- **Condition-Based Maintenance for Jarvis Hardware.** Use temperatures, battery
  health, SMART data, fan behavior, error counts, connectivity, and other telemetry to
  service the PC/Macs/sensor nodes before a likely failure—using deterministic
  thresholds where they outperform speculative ML.
- **Degradation Trend Detector.** Identify slow drift away from an entity's own healthy
  baseline even when no fixed alarm threshold has yet been crossed.
- **Operating Envelope Model.** Learn/define normal combinations of state rather than
  isolated scalar thresholds; flag impossible or unusual combinations.
- **Maintenance Verification.** After a repair/configuration change, verify that the
  original symptom actually disappeared and that no new abnormal state was introduced.

### Spatial computing / AR

- **Persistent World Layer.** Maintain Jarvis-owned semantic anchors that survive
  sessions: objects, controls, notes, warnings, remembered locations, procedures, and
  live data attached to physical places.
- **Cross-Device Spatial Anchor Abstraction.** Hide vendor-specific anchor systems
  behind Jarvis IDs so an anchor created from one capable device can be represented,
  approximated, or re-localized from another.
- **Anchor Confidence + Drift.** Treat spatial anchors as uncertain measurements;
  estimate localization quality, detect drift, and re-anchor using multiple visual/
  geometric references.
- **Walk-Into Interfaces.** Entering a known physical zone can instantiate the relevant
  Jarvis interface automatically: workshop tools in workshop, travel board near luggage,
  system dashboard at desk, cooking context in kitchen.
- **Live Physical Labels.** Attach current dynamic information to stable real-world
  objects/places—device status, next maintenance, instructions, ownership, destination,
  warnings, or relevant mission state.
- **Spatial Inbox.** Leave a virtual note/task/reminder at a physical location and have
  it resurface when the right person returns there.
- **Shared Spatial Context.** With explicit participant consent, multiple enrolled
  users can reference the same Jarvis spatial entity/anchor during a collaborative
  task without needing identical hardware.
- **Spatial Procedure Overlay.** Step-by-step instructions attach to the actual
  component/control involved, advancing only after visual/sensor evidence indicates
  the step was completed.
- **Visual Change Memory.** Compare a current view against prior observations of the
  same anchored space and highlight meaningful changes.
- **Semantic Room Map.** Go beyond geometry: identify what areas are *for*, what
  objects normally belong there, which controls affect what, and which missions/
  routines commonly occur there.
- **Place-Bound Live Data.** Physical spaces can expose contextually relevant live
  information when viewed/entered rather than forcing the user to locate an app.

### Accessibility-derived interaction ideas

- **Input-Modality Independence.** No important Jarvis capability should inherently
  require voice. Commands/actions can be invoked by touch, keyboard, eye/gaze where
  hardware permits, gesture, switches, text, or automation using the same semantic
  intent layer.
- **Output-Modality Independence.** Any important response should have equivalent
  visual, auditory, and haptic/notification representations where hardware supports
  them.
- **Interaction Capability Negotiation.** Jarvis knows which modalities are currently
  available/reliable (hands occupied, noisy room, display unavailable, driving, etc.)
  and chooses accordingly.
- **Describe-on-Demand.** A universal "what am I looking at / what changed / what's
  important here?" operation over the current visual scene with explicit uncertainty.
- **Navigation Landmark Memory.** Learn useful landmarks and decision points along
  familiar routes, not merely GPS coordinates, to support richer situational guidance.
- **Interface Semantic Overlay.** Where permitted, understand visible GUI structure and
  provide a consistent Jarvis interaction layer over otherwise inconsistent apps.
- **Accessibility as Core Architecture.** Keep semantic labels, predictable focus/
  navigation, keyboard control, and modality alternatives native rather than relying
  on an AI agent to repair inaccessible interfaces after the fact.

### End-user programming / malleable systems

- **Demonstrate -> Compile -> Verify.** User performs a digital workflow once; Jarvis
  records it, extracts variables/conditions, compiles the stable path into deterministic
  code, uses an agent only for genuinely variable edges, and asks the user to verify a
  replay before activation.
- **Just-in-Time Automation.** Midway through repetitive work, say "do the rest like
  that." Jarvis infers the repeated transformation from the examples already completed
  and previews the remaining actions.
- **Automation Generalization Dialog.** After demonstration, Jarvis asks only the
  questions needed to distinguish constants from variables: "always this folder or
  whichever folder is open?"
- **Automation Versioning.** User-created automations are first-class versioned
  artifacts with diffs, tests, rollback, dependencies, and provenance.
- **Editable Generated Logic.** Natural-language automation is never a black box:
  expose a human-readable rule/state-machine representation that can be directly
  edited.
- **Composable Capability Blocks.** Small Jarvis primitives can be connected into
  bespoke workflows without requiring a new app or full software project.
- **Personal Micro-App Generator.** If a workflow deserves a persistent interface,
  Jarvis can generate a tiny purpose-built local UI around the underlying capability
  graph rather than forcing interaction through chat forever.
- **Interface-by-Use.** Frequently used commands/queries can crystallize into buttons,
  panels, HUD widgets, or dedicated views automatically; rarely used ones can recede.
- **Personal API.** Expose authorized pieces of Jarvis's world model and capabilities
  through a stable local API/DSL so the user can build on top of Jarvis rather than
  only converse with it.

### Memory that returns at the useful moment

- **Why-I-Saved-It Memory.** Captures preserve the user's surrounding goal/context and,
  when inferable, the reason the item appeared relevant—not just the content itself.
- **Contextual Resurfacing.** Stored knowledge resurfaces when it becomes relevant to a
  current problem/person/place/decision, rather than through arbitrary "on this day"
  reminders.
- **Knowledge Activation Queue.** Separate "saved" from "processed/understood/applied."
  Maintain a prioritized queue that can be consumed incrementally during appropriate
  idle windows.
- **Application Test for Knowledge.** For useful saved concepts, optionally ask "where
  could this change something you currently do?" and connect knowledge to an actual
  project, decision, procedure, or automation.
- **Memory Utility Tracking.** Track which stored information actually gets retrieved,
  changes decisions, or supports actions; use this to improve capture/resurfacing
  policies without deleting provenance.
- **Forgetting-Aware Compression.** Keep raw sources intact but maintain progressively
  shorter high-value representations for rapid resurfacing, with links back to full
  evidence.
- **Spaced Resurfacing for Important Non-Tasks.** Concepts the user wants to retain can
  reappear at expanding intervals, integrated with real context rather than requiring
  a separate flashcard application.

### Meta-Jarvis ideas prompted by the research

- **Concept Importer.** Maintain a catalog of useful abstractions from other disciplines
  (SRE, aviation, intelligence analysis, emergency management, industrial control,
  robotics, HCI) and periodically ask whether new Jarvis subsystems should inherit
  those patterns.
- **Anti-Feature Detector.** Mine user behavior and public discussions not only for
  desired features but for recurring complaints about complexity, distraction,
  unreliability, privacy, and maintenance; encode these as design constraints.
- **Complexity Budget.** Every new subsystem consumes explicit complexity/maintenance/
  attention budget. Prefer a new primitive that collapses several special cases over
  five separate features.
- **Feature Crystallization.** Detect clusters of future.md ideas that are actually
  manifestations of one missing primitive and propose a unifying architecture.


## Ethical context, necessity, and emergency authority — 2026-09-26

Jarvis should not treat ethics/safety as a context-free list of forbidden verbs. The same
technical action can have radically different ethical significance depending on authorization,
necessity, imminence, affected parties, alternatives, proportionality, and purpose. At the same
time, "it's an emergency" must never become a magic phrase that disables safeguards.

- **Ethical Context Engine.** Evaluate consequential requests against structured circumstances:
  intended outcome, authorization, ownership, affected parties, threatened interests, severity,
  imminence, available alternatives, reversibility, collateral effects, evidence quality, and
  applicable hard boundaries. Produce an inspectable decision record rather than an opaque
  LLM yes/no.
- **Necessity & Proportionality Engine.** For normally restricted actions, ask whether the
  action is actually necessary to address the demonstrated problem and whether a less
  intrusive/risky intervention can adequately achieve the same protective outcome.
- **Least-Intervention Planner.** Search first for the smallest sufficient intervention.
  Prefer ordinary authorized routes, then reversible protective actions, before considering
  exceptional actions with larger externalities.
- **Scoped Emergency Authority.** Exceptional circumstances may justify narrowly expanded
  authority, but only for the specific protective objective, target, time window, and action
  class supported by evidence. Never implement a global `EMERGENCY_MODE = SAFETY_OFF`.
- **Emergency Authority TTL.** Any exceptional grant expires automatically when its time,
  condition, mission, or protective objective ends. Reauthorization requires fresh evidence.
- **Emergency Scope Firewall.** Prevent an exception justified for one entity/action from
  silently expanding to adjacent systems. Authority to open one emergency exit does not imply
  authority to disable a facility's security system.
- **Circumstance Verification.** Where practical, corroborate claimed exceptional
  circumstances using available sensors, device state, location, communications attempts,
  environmental data, system telemetry, or other independent evidence. Absence of
  corroboration is not automatically proof the claim is false, especially when sensors may
  themselves have failed.
- **Evidence-Weighted Urgency.** Balance confidence against consequence and time. Jarvis
  should not demand courtroom-level certainty while a credible physical danger is rapidly
  worsening, but should require stronger evidence before taking more consequential or
  irreversible actions.
- **Competing-Interest Model.** Explicitly represent whose safety, privacy, property,
  security, autonomy, and other interests could be affected rather than optimizing only for
  the requesting user.
- **Protect-Life Priority Without Blank Check.** Serious imminent threats to human safety
  substantially change the proportionality calculation, while still requiring Jarvis to
  minimize unnecessary harm and scope.
- **Emergency Escalation Ladder.** Encode domain-specific ordered options such as:
  ordinary controls -> documented emergency mechanisms -> contact responsible humans/
  emergency services -> reversible protective intervention -> narrowly justified exceptional
  intervention. Permit skipping steps when delay itself materially increases danger.
- **Alternative Exhaustion Record.** Track what safer options were attempted, unavailable,
  failed, or were too slow for the circumstances so later decisions do not repeatedly retry
  dead ends.
- **Reversible-First Bias.** When two interventions can plausibly protect the same interest,
  strongly prefer the one that can be undone and independently verified.
- **Minimum Necessary Damage Budget.** If some property/system disruption is genuinely
  necessary to prevent substantially greater harm, optimize explicitly for the minimum
  sufficient disruption rather than treating authorization as unlimited once crossed.
- **Exceptional-Action Verification Loop.** After each consequential step, reassess the
  situation before escalating further. Stop as soon as the protective objective has been
  achieved.
- **Automatic Authority Retraction.** When the emergency predicate clears, immediately
  retract exceptional permissions and return subsystems to ordinary authority policy.
- **Mandatory Exceptional-Action Audit.** Preserve evidence, reasoning inputs, alternatives
  considered, authority granted, actions attempted, outcomes, and termination reason for
  every use of exceptional authority.
- **Post-Emergency Restoration.** After immediate danger ends, identify temporary changes,
  disabled protections, damaged configuration, exposed credentials, or other consequences
  requiring restoration or human follow-up.
- **Uncertain-Emergency Handling.** Distinguish "verified emergency," "credible possible
  emergency," "unverified claim," and "contradicted claim" rather than forcing a binary
  emergency/not-emergency state.
- **Anti-Pretext Checks.** Look for mismatches between the claimed protective objective and
  requested scope. A request framed as rescue that asks for unrelated persistent access,
  credential harvesting, concealment, or broader compromise should not inherit the emergency
  justification.
- **No Concealment Benefit.** Exceptional protective authority does not automatically grant
  authority to erase logs, evade legitimate responders, establish persistence, hide the
  intervention, or preserve access after the protective need ends.
- **Ethical Decision Explainability.** Jarvis should be able to answer: what circumstances
  changed the decision, what safer options existed, why this action was or was not necessary,
  what constraint still applies, and what new evidence would change the decision.
- **Policy/Value Separation.** Keep hard legal/authorization/security boundaries,
  configurable user values, contextual risk assessment, and model-generated interpretation
  as separate layers so one probabilistic model output cannot silently rewrite policy.
- **Ethics Regression Tests.** Maintain scenario suites where superficially similar requests
  differ in authorization/context (owner recovery vs intrusion, rescue vs theft, emergency
  shutdown vs sabotage, medical disclosure to responder vs curiosity) and test that policy
  responds to the meaningful distinctions.
- **Ethical Red-Team Simulator.** Test emergency/necessity logic against fabricated urgency,
  social engineering, sensor spoofing, scope creep, conflicting evidence, compromised
  devices, and ambiguous ownership before enabling stronger real-world actions.

### Small-model emergency competence

Jarvis's local 8B model should not be expected to invent expert emergency procedures or
complex ethical judgments reliably under pressure. Build competence into deterministic
systems and curated knowledge so the model mainly identifies context, fills structured
fields, communicates, and chooses among verified capabilities.

- **Emergency Playbook Library.** Curate offline, source-attributed playbooks for plausible
  emergencies involving home, vehicle, travel, computing, severe weather, power/network
  failure, entrapment, and other supported domains. Prefer authoritative manufacturer/
  government/emergency guidance and store revision/freshness metadata.
- **Emergency Capability Index.** Maintain a locally available map of emergency mechanisms
  Jarvis actually knows how to invoke or explain: enrolled-device SOS functions, emergency
  contacts, building/device manuals, shutoffs, alarms, communications paths, offline maps,
  and authorized actuators.
- **Deterministic Emergency State Machine.** Encode common high-stakes flows as explicit
  state machines with evidence gates, escalation criteria, stopping conditions, and safe
  fallbacks rather than free-form agent loops.
- **Procedure Retrieval Before Generation.** In emergencies, retrieve the relevant verified
  playbook/manual first. The model may summarize/contextualize it but should not casually
  fabricate a procedure from parametric memory.
- **Offline Emergency Knowledge Pack.** Keep critical manuals, contacts, local maps,
  emergency procedures, device recovery instructions, and essential capability metadata
  locally accessible when Internet/cloud models are unavailable.
- **Emergency Model Escalation.** If connectivity exists and the situation requires
  reasoning beyond the local model's calibrated competence, route a minimal necessary
  context package to a stronger approved model/service while preserving the ability to
  continue locally if that route fails.
- **Competence-Aware Routing.** Each emergency task type declares whether it is safe for
  deterministic handling, retrieval + small model, stronger-model consultation, human
  expert escalation, or emergency-services escalation.
- **Don't-Let-the-8B-Wing-It Rule.** High-consequence novel procedures with weak retrieved
  evidence should trigger explicit uncertainty and escalation rather than confident
  improvisation.
- **Emergency Communications Composer.** Deterministically assemble a concise responder
  packet from known facts: identity/contact as configured, location if available, nature of
  emergency, hazards, relevant sensor readings, accessibility needs, actions already tried,
  and callback path.
- **Emergency Evidence Snapshot.** Freeze recent sensor/world-model history when an
  emergency begins so responders or later review can reconstruct what happened even if
  devices subsequently fail.
- **Power/Connectivity Survival Mode.** When infrastructure degrades, shed nonessential
  workloads, preserve battery/compute for sensing, communications, local reasoning, and
  critical automations, and reduce expensive continuous inference.
- **Emergency Self-Test.** Periodically verify that offline playbooks open, contacts are
  current, critical local models start, important sensor nodes report, fallback
  communications exist, and emergency automations still pass dry-run tests.
- **Emergency Drill Mode.** Safely simulate emergencies end-to-end without performing
  dangerous real-world effects; measure whether Jarvis recognized the situation, found the
  right playbook, chose appropriate escalation, communicated clearly, and terminated
  exceptional authority correctly.
