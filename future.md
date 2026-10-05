# Future Ideas

An deliberately broad, unordered scratchpad of feature ideas for Jarvis. Nothing here is scoped,
scheduled, prioritized, or committed to — this is a place to dump ideas before they're
lost, not a roadmap. Move an idea out of this file and into a real design
doc (or just implement it) once someone decides to act on it.

## HORUS naming architecture

**HORUS** is the product/system name. "A real-world Jarvis" remains useful shorthand for explaining
the goal, but new user-facing subsystem names should use the following story-driven vocabulary where
the mapping is semantically useful rather than forcing a theme:

- **Kant** — deep reasoning / deliberate high-effort thinking.
- **Carcosa** — reconstructed and historical world state; Reality Rewind and accumulated past evidence.
- **Ariadne** — investigation; following evidence threads through complex research and identity/world questions.
- **Cassandra** — predictive warnings; forward-looking risk detection and proactive alerts.
- **Mnemosyne** — memory; durable personal/world memory and retrieval.
- **Cerberus** — security; permission, policy, trust and defensive boundaries.
- **Mercury** — communications; messaging, routing and cross-device information delivery.
- **Sisyphus** — retries/background repair; persistent recovery, maintenance and self-healing work.

These are **semantic names, not a mythology theme requirement**. The naming rule is that a name should
carry a story that explains the subsystem once the reference is known. Existing internal module names,
environment variables and compatibility surfaces do not need a mechanical mass rename merely for
branding; migrate user-facing terminology deliberately and preserve compatibility.

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


## Open-source capability mining — GitHub survey 2026-09-28

These repositories are **idea/component candidates, not dependencies or implementation claims**.
The point is to mine proven primitives and architectures that could expand Jarvis. Before adopting
anything, verify license, maintenance state, security posture, hardware requirements, privacy model,
and fit with Jarvis's authority/verification architecture.

### Computer use / digital agency

- **opensymph/open-computer-use — accessibility-first desktop MCP.** Cross-platform local MCP
  exposing app state plus click/type/scroll/drag/set-value operations through OS accessibility
  layers, with an explicit goal of not hijacking the user's real mouse/keyboard. Candidate for a
  deterministic semantic-control lane underneath Conductor: accessibility/API control first,
  screenshot/VLM fallback second. https://github.com/opensymph/open-computer-use
- **heaventree/cua-desktop-ai (Cua) — computer-use infrastructure + evaluation.** Common SDK
  across macOS/Linux/Windows VMs, pluggable local/cloud computer-use models, and benchmarks.
  Mine its abstraction boundary and eval harness so Jarvis computer control can be model-agnostic
  and acceptance-tested instead of tied to one visual agent. https://github.com/heaventree/cua-desktop-ai
- **microsoft/UFO — Windows multi-app AgentOS.** Separates host-level app selection from
  app-specific execution and combines Windows UI Automation/native APIs with visual reasoning.
  Candidate architecture for turning the Windows backend from individual hard-coded functions into
  reliable cross-application workflows while retaining native controls where possible.
  https://github.com/microsoft/UFO
- **bytedance/UI-TARS-desktop — local/remote GUI + browser operator.** Mature open multimodal
  computer-use stack for Windows/macOS/browser with visual grounding and mouse/keyboard control.
  Evaluate as a visual fallback lane for interfaces with no API/accessibility path, and mine its
  grounding/evaluation patterns rather than assuming it should replace deterministic tools.
  https://github.com/bytedance/UI-TARS-desktop
- **browser-use/browser-use — browser agency.** Mature Playwright-based browser-agent layer that
  can navigate, fill forms, manage tabs and extract content. Candidate browser execution backend
  for Jarvis tasks where no stable first-party API exists; actions still need Jarvis confirmation,
  domain allowlisting, receipts and post-action verification. https://github.com/browser-use/browser-use
- **arthurkatcher/desktop-use — observable computer-use mission control.** Particularly relevant
  idea: live VNC, snapshot replay, append-only event/screenshots, and mid-flight human intervention.
  Mine this for Conductor's observability contract: every autonomous GUI task should be watchable,
  interruptible and replayable after the fact. https://github.com/arthurkatcher/desktop-use
- **shlawgathon/Computer-Use — demonstrate/record/replay desktop workflows.** Vision-first macOS
  agent with named tools, confidence rejection, active-window context and AppleScript state probes.
  Strong reference for the existing Demonstrate -> Compile -> Verify / Physical Macros ideas:
  learn a workflow visually, then crystallize stable pieces into deterministic controls.
  https://github.com/shlawgathon/Computer-Use

### Memory / Reality Graph

- **getzep/graphiti — temporal knowledge graphs.** Tracks entities and relationships with validity
  windows, source episodes/provenance, incremental updates and historical queries. This maps almost
  directly onto Reality Rewind, Reality Diff and the requirement that Jarvis distinguish
  "was true" from "is true." Evaluate its temporal model as a Reality Graph substrate or borrow
  its episode/fact/validity semantics. https://github.com/getzep/graphiti
- **neo4j-labs/agent-memory — graph-native agent memory.** Combines short-term conversation,
  long-term entity knowledge, reasoning/tool traces, entity resolution, geospatial queries,
  consolidation and evals. Interesting for making Jarvis remember not merely facts but prior
  decisions, tool use and which entities a reasoning step touched. https://github.com/neo4j-labs/agent-memory
- **letta-ai/letta-code / letta-agent-sdk — persistent agent identity/state.** Long-lived agents
  retain memory/identity across sessions, machines and model backends and can run proactively.
  Mine the separation between agent state and transient model execution so "Jarvis" remains one
  continuous system even when cognition moves among local 8B, Groq/cloud, PC, Mac and phone.
  https://github.com/letta-ai/letta-code

### Cameras / visual-world ingestion

- **AlexxIT/go2rtc — universal camera stream normalization.** Accepts RTSP, RTMP, MJPEG, WebRTC,
  ONVIF and other camera inputs and can expose normalized RTSP/WebRTC/HTTP outputs. Potentially a
  major simplification for both Worldwide Cams and Jarvis: provider adapters discover lawful/public
  streams; a dedicated media gateway handles protocol/codec normalization; perception sees one
  stable interface. https://github.com/AlexxIT/go2rtc
- **koush/scrypted — high-performance video integration platform.** Low-latency camera integration,
  NVR/smart-detection architecture and bridges into HomeKit/Google Home/Alexa. Mine its camera
  plugin model and event/detection pipeline for user-owned cameras and authorized physical-space
  perception. https://github.com/koush/scrypted
- **blakeblackshear/frigate — local camera perception/NVR.** Evaluate Frigate's event-oriented
  object-detection model for user-owned/authorized camera feeds: continuous video should become
  sparse, queryable observations/events rather than forcing Jarvis to reason over raw streams.
  https://github.com/blakeblackshear/frigate
- **streamlink/streamlink + yt-dlp/yt-dlp — public livestream resolution.** Useful components for
  Worldwide Cams' YouTube/public-webcam ingestion: resolve supported public streaming pages into
  actual media streams and metadata. Pair with the existing webcam-only classifier/filter so
  arbitrary livestreams (music, gaming, news loops, etc.) do not become "cameras."
  https://github.com/streamlink/streamlink and https://github.com/yt-dlp/yt-dlp

### Persistent monitoring / proactive Jarvis

- **dgtlmoon/changedetection.io — generalized web Reality Diff.** Already solves persistent page
  watching, JavaScript-rendered pages, history and change alerts. Instead of inventing one-off
  polling for every site, evaluate using/borrowing its watcher engine as a Web Observation adapter
  that emits timestamped diffs into the Reality Graph. https://github.com/dgtlmoon/changedetection.io
- **huginn/huginn — persistent event agents.** Long-running agents watch sources, transform events
  and trigger downstream actions. Mine its event-graph model for the Reality Compiler: natural
  language intent -> persistent collector -> transform/filter -> condition -> notification/action,
  with the compiled graph visible and editable. https://github.com/huginn/huginn
- **binwiederhier/ntfy — self-hosted push bus.** Extremely simple HTTP pub/sub notifications to
  phones/desktops. Candidate redundant alert path for Guardian and local infrastructure, especially
  when Jarvis needs a vendor-light way for any node to push an authenticated event to the user.
  https://github.com/binwiederhier/ntfy

### Voice / ambient presence

- **livekit/agents — realtime multimodal agent transport.** Framework for low-latency voice/video
  agents with streaming STT/LLM/TTS, turn detection and realtime media. Mine its transport/session
  architecture for making Jarvis conversation continuous across room node, iPhone/iPad and future
  glasses rather than rebuilding realtime media plumbing per surface. https://github.com/livekit/agents
- **rhasspy/wyoming — small interoperable voice-service protocol.** Simple streaming event protocol
  designed to connect wake-word, STT and TTS components without forcing one monolithic assistant.
  Strong fit for Raspberry Pi room satellites: microphones/speakers can be replaceable edge nodes
  while Jarvis cognition remains elsewhere. https://github.com/rhasspy/wyoming
- **The-OASIS-Project/dawn — multi-room local JARVIS-style assistant.** Always-listening voice,
  wake word, local/cloud models, memory, smart-home control and embedded Linux satellites.
  Worth mining specifically for multi-room presence topology, deployment and failure handling,
  not for its branding or as a wholesale replacement for Jarvis. https://github.com/The-OASIS-Project/dawn

### Physical world / infrastructure

- **home-assistant/core — use Home Assistant as a capability bus, not merely a smart-home UI.**
  Its enormous local-first device/integration ecosystem could let Jarvis inherit normalized state
  and authorized control for many physical devices instead of writing bespoke integrations for
  every manufacturer. Jarvis should remain the intent/authority/verification layer above it.
  https://github.com/home-assistant/core
- **meshtastic/firmware — off-grid Jarvis mesh.** LoRa mesh provides low-power messaging, location
  and telemetry without cellular/Internet infrastructure. Candidate for Raspberry Pi/portable
  Presence nodes, family emergency beacons and degraded-connectivity Guardian messages. Treat
  radio hardware as an optional future transport, not a current capability.
  https://github.com/meshtastic/firmware
- **juanfont/headscale — self-hosted private device mesh control plane.** A self-hosted Tailscale
  control server can provide a stable private overlay among Jarvis PCs, Macs, Raspberry Pis and
  remote nodes without exposing services directly to the public Internet. Evaluate against plain
  Tailscale before adding operational complexity. https://github.com/juanfont/headscale

### New feature ideas synthesized from the repositories

- **Semantic-First Computer Control Router.** For each digital action choose the strongest
  available control surface in order: native API -> OS accessibility/UI Automation -> DOM ->
  visual grounding. The VLM is a fallback, not the default, and every lane emits the same action
  receipt schema.
- **Observable Autonomy / Mission Recorder.** Any multi-step autonomous task exposes a live view,
  current goal/subgoal, action stream, screenshots/state snapshots, pause/take-over/abort controls,
  and deterministic replay/audit after completion. "Jarvis did it" should never be opaque.
- **Temporal Truth Model.** Every mutable Reality Graph fact can carry observed-at, valid-from,
  valid-to/superseded-at, source episode, confidence and derivation. Queries such as "where was it
  yesterday?" and "what changed?" become first-class rather than reconstructed ad hoc.
- **Universal Media Gateway.** Separate camera *discovery* from camera *transport*. Provider
  adapters establish provenance, legality/public availability and coordinates; a go2rtc-like
  gateway resolves codecs/protocols; perception consumes normalized frames; the UI can show the
  exact source Jarvis used.
- **Eventification Layer.** Convert high-bandwidth continuous sources (video, audio, telemetry,
  web pages) into sparse typed events plus links to retained evidence. The Reality Graph should
  reason primarily over events while allowing drill-down to the underlying observation.
- **Web Observation Fabric.** Make arbitrary user-approved web state monitorable as a durable
  sensor: page/selector/API value -> normalized observation -> diff -> Reality Graph event ->
  optional alert/action. This generalizes price/restock/status/deadline/change monitoring without
  bespoke code per website.
- **Transport-Independent Presence.** Voice/text/event sessions should survive switching among
  LAN, Internet, push, WebRTC and eventually LoRa/off-grid paths. "Jarvis is present" should not
  be synonymous with one server or one network link.
- **Capability Bus Adapters.** Treat mature integration ecosystems such as Home Assistant as
  subordinate capability buses. Jarvis discovers their entities/actions, wraps them in its own
  authority and verification model, and gains breadth without duplicating hundreds of device
  integrations.
- **Agent State Portability.** Define a serializable Jarvis cognitive-state packet—active mission,
  salient memories, pending commitments, current hypotheses, capability grants and provenance—
  that can move between model/runtime backends without resetting the assistant's continuity.
- **Repository Radar.** Periodically search GitHub/release feeds for projects relevant to known
  Jarvis capability gaps, score them for novelty/fit/activity/license, and append candidates for
  human review. The system should search for missing primitives, not blindly chase popular
  "AI agent" repositories.


### Voice stack replacement candidates — deeper GitHub sweep 2026-09-28

The earlier GitHub survey under-searched speech synthesis. This deserves its own capability lane because
voice quality/latency materially affects whether Jarvis feels ambient or like a chatbot. Also keep the
current-state distinction explicit: backend code/docs currently identify **Kokoro-82M / bm_george** as
the default low-latency TTS path, while `ios/README.md` still contains stale Qwen3-TTS runtime text.
Any replacement evaluation must benchmark against the *actually running* Kokoro service, not the stale
documentation.

- **debpalash/VoiceStudio — top candidate for replacing the current TTS service layer, not merely a
  desktop voice app.** Fully local speech platform with voice cloning/design, local HTTP/WebSocket/API
  surfaces, MCP, CUDA support, model management, and a pluggable TTS engine catalogue. It currently
  supports OmniVoice, CosyVoice 3, IndexTTS 2.5, MLX-Audio/Kokoro/CSM/Dia, VoxCPM2, MOSS-TTS-Nano,
  PocketTTS, Sherpa-ONNX, GPT-SoVITS and others. On the RTX 5080, this could let Jarvis keep one stable
  `/tts`-style integration while experimentally switching among much better voices/models underneath.
  **This should have been in the first survey.** License is AGPL-3.0 and individual model licenses vary;
  treat VoiceStudio as a separately running local service unless/until licensing implications of tighter
  code integration are reviewed. https://github.com/debpalash/VoiceStudio
- **VoiceStudio OmniVoice — cloned/designed Jarvis voice candidate.** Default VoiceStudio engine,
  600+ languages, zero-shot cloning, voice design, CUDA support and ~6 GB recommended VRAM floor.
  Particularly interesting because Jarvis could design a restrained original aide voice instead of
  depending on a generic preset speaker. Benchmark quality and first-audio latency on the actual 5080.
- **VoiceStudio / CosyVoice 3 — instructed zero-shot clone candidate.** 0.5B-class multilingual model
  with reference-voice cloning and instruction-driven speech. VoiceStudio's managed Windows recipe
  explicitly handles RTX 50-series PyTorch/CUDA compatibility. Candidate if it sounds materially more
  natural than Kokoro without unacceptable sentence-start latency.
- **VoiceStudio / IndexTTS 2.5 — expressive/emotional voice candidate.** Reference cloning plus emotion
  reference/vector/text control. Probably overkill for routine acknowledgements, but useful if a
  high-quality Jarvis voice needs controlled emphasis and prosody rather than generic TTS cadence.
  Treat model licensing separately from VoiceStudio itself.
- **OpenMOSS/MOSS-TTS-Nano — low-resource cloned-voice fallback.** ~100M parameter, 20-language,
  realtime CPU-capable model with reference voice cloning. Interesting as an offline/failover voice on
  Raspberry Pi/CPU-class nodes where Kokoro/large CUDA models are unavailable.
  https://github.com/OpenMOSS/MOSS-TTS-Nano
- **Kyutai PocketTTS through VoiceStudio — ultra-low-latency CPU clone lane.** VoiceStudio documents it
  as roughly 8–9x realtime on an Apple M3 Pro, with zero-shot voice cloning. Evaluate for room satellites
  and degraded-mode operation where conversational latency matters more than maximum expressiveness.
- **resemble-ai/chatterbox — standalone high-quality open TTS candidate.** MIT-licensed, widely adopted
  open-source TTS/voice-cloning project. It should be in the bake-off even if VoiceStudio is chosen as
  the service layer, because the best Jarvis voice may come from a model VoiceStudio does not currently
  expose. https://github.com/resemble-ai/chatterbox
- **SWivid/F5-TTS — standalone zero-shot cloning candidate.** Mature MIT-licensed flow-matching TTS with
  a large ecosystem. Include in quality/latency testing, especially if a distinctive Jarvis voice can
  be cloned/designed from a short reference more naturally than Kokoro presets.
  https://github.com/SWivid/F5-TTS
- **fishaudio/fish-speech — expressive standalone candidate.** High-quality open-source TTS with voice
  cloning/conditioning; evaluate licensing, local serving and latency before considering integration.
  https://github.com/fishaudio/fish-speech
- **ServeurpersoCom/qwentts.cpp — native/quantized Qwen TTS path.** Interesting specifically because
  Jarvis previously used Qwen3-TTS but moved away for latency. A native C++/quantized implementation
  could change that tradeoff; benchmark rather than assuming the old Python service's latency still
  characterizes Qwen-based speech. https://github.com/ServeurpersoCom/qwentts.cpp

#### Voice replacement acceptance test

Do not replace the voice because a model demo sounds impressive. Build a repeatable local bake-off on
the actual Jarvis PC and score/record **measured** behavior for the same corpus:

- cold-start time and warm **time-to-first-audio** for 5-word, 15-word and 40-word responses;
- real-time factor / total synthesis latency;
- VRAM/RAM footprint and contention with Jarvis's other GPU workloads;
- naturalness, intelligibility, pronunciation of names/addresses/acronyms, and long-response stability;
- ability to produce one consistent original Jarvis identity (preset, designed or permissioned clone);
- streaming/chunking behavior with the existing sentence-level iPhone playback path;
- barge-in behavior, cancellation latency and whether an interrupted generation actually releases work;
- reliability across 100+ sequential short generations and backend restart/recovery;
- local-only operation, network dependencies, model/license constraints and failure fallback;
- exact API contract needed to drop behind Jarvis's existing TTS client.

**Decision rule:** keep Kokoro as the baseline until another stack is demonstrably better on the dimensions
that matter in conversation. VoiceStudio is especially attractive because it can turn this from a one-time
model choice into a provider-independent local speech layer: Jarvis owns the TTS contract and VoiceStudio
owns model lifecycle/engine switching underneath it.


## Systematic GitHub capability mining — mechanical sweep 2026-09-28

This pass deliberately corrects the earlier search method. Discovery was run mechanically across
GitHub topic/star queries, recent high-growth repositories (2026-created + substantial stars),
"awesome" indexes, and second-hop projects referenced by those indexes. It covered TTS/voice,
realtime audio, computer use, browser automation, mobile control, memory/knowledge graphs,
computer vision/video analytics, home automation/IoT, robotics/SLAM, AR, geospatial/OSINT,
ADS-B/AIS/satellite/SDR, mesh/networking, media transport, change detection, observability,
evaluation and agent sandboxing.

**These are research candidates, not implementation claims.** Repository popularity is not proof of
quality, and README claims are not acceptance evidence. Any promoted item still needs license/security
review plus an end-to-end test against Jarvis's actual hardware and criteria.

### Ambient presence / voice / glasses

- **QwenAudio/qwen-audio-agent — realtime "agent presence" runtime.** This is much closer to the
  conversational behavior Jarvis is trying to achieve than a plain STT -> LLM -> TTS pipeline:
  full-duplex voice, natural interruption, concurrent background agent tasks, progress/cancellation,
  task results returning naturally to the ongoing conversation, replaceable realtime voice frontends,
  and local speech-to-speech support. Mine the architecture even if Jarvis does not adopt Qwen as the
  model. The important primitive is **conversation continuing while work happens elsewhere**.
  https://github.com/QwenAudio/qwen-audio-agent
- **Intent-Lab/VisionClaw — direct Ray-Ban realtime voice+vision reference implementation.** Uses the
  same Meta Wearables DAT family Jarvis already integrates, streams glasses video plus bidirectional
  audio to a live multimodal model, and routes tool calls to an external action gateway. Extremely
  relevant as a reference for the glasses transport/session layer, WebRTC POV sharing, native-audio
  conversation and phone-camera fallback. Do not copy its trust model blindly; preserve Jarvis's
  stronger authority/verification boundaries. https://github.com/Intent-Lab/VisionClaw
- **xzf-thu/VoiceMem — streaming memory specifically designed for voice agents.** Performs retrieval
  while the user is still speaking so relevant memory can already be available at turn completion.
  Mine the speculative-prefetch, bounded Top-K injection, session-buffer and interruption-timeline
  architecture. Treat speaker voiceprints/emotion/personality inference as separately consented,
  optional capabilities rather than importing that policy wholesale.
  https://github.com/xzf-thu/VoiceMem
- **FireRedTeam/FireRedTTS3 — another serious voice-design/cloning bake-off candidate.** Apache-2.0
  code; multilingual zero-shot cloning plus instruction-controlled voice design and speech editing.
  Add it to the same measured TTS acceptance harness as VoiceStudio/Kokoro/F5/Chatterbox rather than
  choosing from demos. https://github.com/FireRedTeam/FireRedTTS3
- **k2-fsa/OmniVoice — inspect upstream directly, not only through VoiceStudio.** VoiceStudio's default
  engine is itself an actively developed voice-cloning/design stack. Keep the upstream project in the
  bake-off so Jarvis can distinguish VoiceStudio service-layer issues from model-engine behavior.
  https://github.com/k2-fsa/OmniVoice

### Camera-free physical awareness

- **ruvnet/RuView — Wi-Fi CSI as a camera-free room sensor.** Potentially major for a Jarvis room node:
  low-cost ESP32 CSI sensors feeding local occupancy/motion/activity observations without putting a
  camera in the room. The repo also explores pose/vitals/etc., but its own README explicitly notes that
  some live pose paths are still first-cut/stub quality. Initial Jarvis evaluation should therefore
  target only independently verifiable primitives such as presence/movement/room transition and treat
  health/pose claims as research until measured on real hardware. https://github.com/ruvnet/RuView
- **esphome/esphome — sensor-node fabric.** Instead of custom firmware for every ESP32 sensor,
  evaluate ESPHome as the standardized edge layer for temperature, humidity, light, mmWave presence,
  BLE proxying, buttons, relays and other user-owned sensors. Jarvis consumes normalized state/events
  above it rather than becoming an embedded-firmware project. https://github.com/esphome/esphome
- **merbanan/rtl_433 — local RF sensor receiver.** An inexpensive SDR can decode many common
  unlicensed-band weather/environment sensors and emit JSON/MQTT. Useful for *user-owned* weather,
  leak, temperature and utility sensors without vendor clouds. Scope ingestion to enrolled/authorized
  devices rather than treating every nearby broadcast as Jarvis property.
  https://github.com/merbanan/rtl_433

### Computer / browser / phone agency

- **trycua/cua — canonical current Cua repo.** The earlier survey cited an older/alternate Cua path.
  The current project includes Cua Driver for macOS/Windows/Linux app control, isolated desktops,
  local Apple-Silicon VMs, specialized bounded decision models, and Cua Bench for verified computer-use
  tasks. Particularly strong fit for Jarvis because it treats APIs/code/GUI as interchangeable control
  surfaces and includes an evaluator rather than merely a click agent. https://github.com/trycua/cua
- **mediar-ai/terminator — deterministic Windows automation with AI recovery.** Uses accessibility,
  browser DOM and pixels; can work in the background without stealing the real cursor; records human
  workflows into reusable deterministic automation and invokes AI for recovery. This maps almost
  exactly onto Jarvis's Demonstrate -> Compile -> Verify direction and is directly relevant to the
  Windows backend. https://github.com/mediar-ai/terminator
- **ShawnPana/phone-harness — no-jailbreak control of a real iPhone through Apple's iPhone Mirroring.**
  Uses macOS Screen Recording/Accessibility plus Vision OCR to see/tap/type on the mirrored phone;
  Android uses ADB. This could give Jarvis an action surface for iPhone apps that expose no API or
  Shortcuts action, while keeping the phone unmodified. Constraints are real: Mac dependency,
  mirroring must be connected, Face ID/camera/DRM flows do not work, and consequential actions still
  need confirmation/readback. https://github.com/ShawnPana/phone-harness
- **jackwener/OpenCLI — "crystallize websites into tools."** Can operate a logged-in Chrome session,
  inspect network responses/DOM, and turn repeated website workflows into deterministic adapters with
  verification. Strong implementation reference for Jarvis's Feature Crystallization / generated
  adapters: use browser reasoning once to discover a stable interface, then stop spending model tokens
  re-discovering it every time. https://github.com/jackwener/opencli
- **omxyz/lumen — vision-first browser agent with self-healing replay.** Screenshot-first execution,
  action caching, structured persistent state, stuck detection, domain/action policy hooks, resumable
  sessions and an explicit completion verifier. Mine the **known-good action replay + verification**
  pattern as a fallback for sites where DOM/API automation is unreliable. https://github.com/omxyz/lumen
- **vercel-labs/agent-browser — fast accessibility-tree browser control.** Native Rust CLI, stable
  element refs, screenshots only when needed, CDP attachment and page-provided WebMCP discovery.
  Candidate low-overhead deterministic browser lane beneath the high-level agent.
  https://github.com/vercel-labs/agent-browser
- **pinchtab/pinchtab — persistent local browser control plane.** Single Go service providing
  token-efficient structured page state, reusable authenticated profiles, multiple browser instances,
  ARM64/Raspberry Pi support and explicit local-first security defaults. Interesting if Jarvis should
  have a standing browser capability service rather than spawning browser automation ad hoc.
  https://github.com/pinchtab/pinchtab
- **lightpanda-io/browser — agent-native headless browser.** A non-Chromium browser built for
  automation with much lower memory/process overhead. Not a replacement for a real logged-in Chrome
  session where compatibility matters, but worth benchmarking for high-volume read-only research jobs
  and background web sensors. https://github.com/lightpanda-io/browser

### World Armor / global reality layer

- **koala73/worldmonitor — ready-made global intelligence/data fusion surface.** Real-time global
  dashboard combining news, infrastructure/geopolitical signals, 3D/2D maps, correlation, local AI,
  plus MCP/REST/CLI/SDK access. Do not copy its conclusions or scores blindly; mine its source adapters,
  map-layer catalogue, correlation plumbing and programmatic interfaces as potential World Armor
  inputs. https://github.com/koala73/worldmonitor
- **bilawalsidhu/gods-eye-view — photorealistic open-source spatial-intelligence globe.** Live public
  geospatial data on a Cesium-style 3D world with flight/satellite/geospatial layers. Strong visual and
  architecture reference for what the World Armor globe should feel like when it is driven by real
  sources rather than bespoke demo dots. Verify the project's non-standard license before reuse.
  https://github.com/bilawalsidhu/gods-eye-view
- **tidwall/tile38 — realtime geospatial database + geofencing.** Candidate primitive for persistent
  location predicates: moving entities enter/exit regions, proximity triggers, "within N meters" and
  spatial indexing should live in a purpose-built geospatial layer rather than repeatedly scanning
  every Reality Graph entity in Python. https://github.com/tidwall/tile38
- **organicmaps/organicmaps + Project-OSRM/osrm-backend — offline map/search/routing lane.** Jarvis
  currently depends heavily on online map services for many location questions. These projects show a
  path to locally stored OSM maps, offline search and local routing, useful both for privacy and
  degraded-connectivity/emergency operation. https://github.com/organicmaps/organicmaps and
  https://github.com/Project-OSRM/osrm-backend
- **roboflow/supervision — reusable CV tracking/event primitives.** Mature tooling around detections,
  tracking, zones, lines and video processing. Useful for the Eventification Layer: convert raw camera
  detections into durable observations like "object crossed zone" or "track entered region" rather
  than feeding raw boxes directly to an LLM. https://github.com/roboflow/supervision

### Local radio reality — independent of Internet APIs

- **cpaczek/skylight — excellent Pi 5 reference project for physical-world fusion.** Receives local
  ADS-B through RTL-SDR with sub-second updates, renders aircraft/satellites against the real sky, and
  optionally points a PTZ camera at predicted aircraft using ADS-B lead prediction + visual lock +
  continuous self-calibration. Mine both the local-radio path and the elegant
  **telemetry prediction -> actuator pointing -> visual verification -> calibration** loop.
  https://github.com/cpaczek/skylight
- **wiedehopf/readsb + wiedehopf/tar1090 — local aircraft receiver/data/history stack.** A cheap
  RTL-SDR on the Raspberry Pi can give Jarvis locally received aircraft state independent of OpenSky
  or other Internet providers, while tar1090 provides history/visualization. This would make nearby
  aircraft a directly observed Reality Graph source rather than merely a web API.
  https://github.com/wiedehopf/readsb and https://github.com/wiedehopf/tar1090
- **jvde-github/AIS-catcher — local AIS vessel receiving.** The maritime equivalent of local ADS-B:
  with appropriate SDR/antenna hardware, ingest VHF AIS broadcasts directly into World Armor for
  nearby vessels instead of depending entirely on third-party AIS APIs.
  https://github.com/jvde-github/AIS-catcher
- **SatDump/SatDump — local satellite downlink processing.** Broad SDR pipeline for receiving and
  decoding supported satellite transmissions. This is not a universal "live satellite imagery"
  shortcut—reception depends on orbit, antenna, frequency and spacecraft—but it creates a genuinely
  independent physical observation path worth exploring on the Pi/SDR side.
  https://github.com/SatDump/SatDump
- **thkruz/keeptrack.space — local/offline orbital world model.** Tracks tens of thousands of
  satellites and can run offline. Mine its orbital mechanics, sensor-visibility calculations and
  time-scrubbing model for a World Armor space layer rather than relying only on static map markers.
  https://github.com/thkruz/keeptrack.space

### Data plane / media plane / reactive state

- **eclipse-zenoh/zenoh — unified pub/sub + store/query transport for Jarvis nodes.** Built for
  distributed robotics/edge systems and supports multiple languages. Potential replacement for a
  growing pile of bespoke REST polling between PC, Mac, Pi and sensor nodes: observations can be
  published, queried and retained through one locality-aware data plane. Evaluate against the
  operational simplicity of the current HTTP/Tailscale design before adopting.
  https://github.com/eclipse-zenoh/zenoh
- **bluenviron/mediamtx — realtime media router.** Complements go2rtc: protocol conversion among
  WebRTC/RTSP/HLS/RTMP/SRT/etc., recording/playback, auth, hooks, control API and metrics in a
  portable single executable. Interesting if Worldwide Cams/Jarvis needs persistent recording,
  replay or multi-consumer routing rather than only stream normalization.
  https://github.com/bluenviron/mediamtx
- **drasi-project/drasi-platform — change-data-processing engine.** Evaluate its CDC/change-query/
  reaction model as a general Reality Diff substrate: sources emit changes, standing queries decide
  what those changes mean, and reactions fire only when relevant state transitions occur. This is
  closer to how a persistent Jarvis should work than thousands of independent polling loops.
  https://github.com/drasi-project/drasi-platform

### Verification, observability and safe execution

- **promptfoo/promptfoo — model/agent regression harness.** Jarvis's problem is not only capability;
  it is repeatedly claiming capabilities that later fail. Promptfoo can provide repeatable model and
  agent eval matrices across local/cloud models and prompts. Connect future `criteria.md` claims to
  machine-run regression suites rather than prose assertions. https://github.com/promptfoo/promptfoo
- **langfuse/langfuse — agent trace/evaluation observability.** Capture complete model/tool traces,
  latency and evaluation data so a failed "Jarvis did X" claim can be reconstructed rather than
  guessed at. Mine it for an internal **capability evidence ledger** even if the full platform is too
  heavy. https://github.com/langfuse/langfuse
- **opensandbox-group/OpenSandbox / firecracker-microvm/firecracker — isolate generated or risky
  compute from the real host.** Jarvis increasingly generates code, installs dependencies and may
  execute unfamiliar tooling. A disposable sandbox/microVM lane would let it explore/build/test
  without granting every experiment the same authority as the user's real Windows/Mac environment.
  https://github.com/opensandbox-group/OpenSandbox and
  https://github.com/firecracker-microvm/firecracker
- **Cua Bench (inside trycua/cua) — real task verification for computer use.** Treat this as more than
  a benchmark: adopt the pattern that every computer-control capability has a reproducible task,
  reference state and evaluator. "Clicked the right thing" is not completion; the resulting computer
  state must satisfy the test.

### New architectural ideas synthesized from the mechanical sweep

- **Conversation/Execution Split.** Keep a realtime low-latency conversational presence alive while
  durable backend jobs execute independently. The voice frontend can answer, interrupt, report
  progress, cancel and accept follow-ups without coupling conversational responsiveness to tool-task
  duration.
- **Direct-Observation Tier.** Prefer local physical receivers when practical—ADS-B, AIS, SDR sensors,
  ESPHome, Wi-Fi CSI—then use Internet data as broader but less direct evidence. Record which facts are
  locally observed versus provider-reported.
- **Camera-Free Room Model.** Build the room Presence node around non-camera sources first
  (mmWave/CSI/BLE/door/light/audio labels as authorized), with cameras as an optional high-information
  sensor rather than the prerequisite for ambient intelligence.
- **Physical Sensor Gateway on Pi 5.** Make the Pi the edge concentrator for SDR, ESPHome/MQTT,
  Bluetooth, Wi-Fi CSI and local environmental sensors. It publishes normalized timestamped
  observations to Jarvis; it should not need to run the main reasoning model.
- **RF Reality Layer.** Treat radio as another sensory modality: aircraft transponders, AIS, weather
  sensors and supported satellite downlinks can populate the same Reality Graph as cameras and web
  APIs, each with source/provenance and reception limits.
- **Predict -> Point -> Verify -> Calibrate loop.** Generalize Skylight's aircraft-camera design:
  external telemetry predicts where an observable target should be; an actuator/sensor is directed
  there; perception verifies the target; measured error updates calibration. Useful well beyond
  aircraft whenever Jarvis controls a PTZ camera or physical sensor.
- **Compiled Website Capability.** After Jarvis successfully operates a website through a general
  browser agent, attempt to crystallize the workflow into a deterministic DOM/network adapter with
  tests. Fall back to visual/agent control only when the deterministic adapter stops satisfying its
  verifier.
- **Capability Evidence Ledger.** Every user-visible capability claim links to: implementation commit,
  environment/hardware, last passing acceptance test, recorded trace/receipt, and freshness. A feature
  with no current passing evidence is described as designed/implemented-but-unverified, never simply
  "working."
- **Standing Query Reality Engine.** Express ongoing interests as persistent queries over changing
  state rather than scheduled prompts. Example: `aircraft where distance(home)<10mi AND altitude
  decreasing`, `camera source changed availability`, or `device entered geofence`. Emit events
  only on meaningful result-set changes.
- **Offline World Core.** Maintain enough local maps, routing, satellite ephemerides, emergency
  knowledge, enrolled-device state and direct RF sensing that degraded Internet removes breadth but
  does not reduce Jarvis to a dead chat box.
- **Model-independent Interaction Bus.** Voice, browser, desktop, phone, sensors and world feeds should
  expose stable typed capabilities while models remain swappable. The system can then change Qwen,
  Groq, Gemini Live, local speech models, etc. without rebuilding its hands and senses.

### Ongoing discovery rule

The GitHub survey should not be a one-off. A future Repository Radar should periodically run the same
mechanical categories plus **recently-created/high-growth** queries, then inspect second-hop projects
from awesome lists and dependency graphs. A candidate is interesting when it adds a missing primitive,
materially improves latency/reliability/privacy, or supplies a tested implementation of something
already in `future.md`—not merely because it is popular.


## User Belief Model — track what the user believes, not just what is true

Every layer of Jarvis models one thing: what is true (with provenance, confidence, verification). Nothing models what the user currently believes and, more importantly, the gap between the two.

That gap is the thing that actually hurts people — and it’s the real engine of the cinematic Apollo moment. The danger in that scene isn’t that the draft says 15%. It’s that you still think it says 10% and you’re about to sign.

The current Executive Loop can tell you “the term changed.” It cannot tell you:

> “The term changed, you were never exposed to the change, and you’re about to act on the old number in 12 minutes.”

That third clause is the whole game, and no existing subsystem represents it.

A **User Belief Model** should therefore track not only world-state facts, but the best evidence-backed estimate of what the user currently believes about those facts, including when and how that belief was formed. Jarvis should be able to represent:

- the current verified fact;
- the user’s likely believed value/state;
- the evidence that the user was exposed to that value/state;
- the last time the user’s belief was plausibly updated;
- uncertainty about whether the user actually noticed or understood a change;
- the delta between believed state and verified state;
- whether the user is about to take an action that depends on the stale belief;
- the deadline / irreversibility / consequence level of that action.

This creates a new class of proactive intervention:

**world changed + user probably did not update + user is about to act on stale state = intervene now.**

The system must not treat inferred beliefs as facts. Every belief estimate needs provenance and confidence, and Jarvis should prefer direct evidence of exposure (opened message, viewed document, explicit acknowledgment, spoken discussion, etc.) over assumptions. It should also be able to say **unknown** when it cannot establish what the user believes.

The important output is not merely “something changed.” It is **decision-relevant belief divergence**: the subset of changes where Jarvis has evidence that the user’s mental model is stale and that the stale model is about to affect a real decision or action.


## Gemma 4 evaluation — local multimodal brain candidate

Gemma 4 is now a real released open-model family, not a speculative future model. Google released the
family under Apache 2.0, and the 12B Unified model is explicitly designed for local consumer hardware
with native multimodal input and agentic/function-calling use. Treat it as a benchmark candidate, not
an automatic replacement for the current Qwen planners.

- **Benchmark Gemma 4 12B Unified on the RTX 5080 as a general local-intelligence candidate.**
  Official material says it is designed to run locally with 16 GB of VRAM/unified memory and supports
  text, image, audio and video input with text output. It is therefore unusually well matched to
  Jarvis's current 16 GB GPU constraint and multimodal ambitions.
- **Do not replace deterministic systems with it.** Reality Graph provenance, permissions,
  confirmations, deadline math, source freshness, action verification and typed provider adapters
  remain code-owned. Gemma should reason over bounded evidence, not become the source of truth.
- **Possible role:** deterministic fast paths -> lightweight fast planner/classifier -> Gemma 4 12B
  for ambiguous local reasoning/multimodal synthesis -> larger local/cloud escalation only when the
  task warrants it.
- **Vision bake-off:** compare Gemma 4 12B against Moondream on the actual Jarvis camera corpus:
  scene understanding, OCR, object/state changes, multi-frame reasoning, latency, VRAM and failure
  calibration. A stronger model is useful only if its latency allows the intended sensor cadence.
- **Audio understanding experiment:** test non-speech/environmental audio plus speech-context tasks
  that ASR necessarily destroys. Keep the ordinary speech-recognition path for low-latency
  transcription unless direct-audio understanding proves useful and fast enough.
- **User Belief Model experiment:** allow Gemma to infer a bounded candidate belief from explicit
  exposure evidence and conversation context, while the database owns provenance/confidence and
  never treats the model's inferred belief as fact.
- **Jarvis-specific acceptance harness:** same task corpus across current fast planner, current quality
  planner and Gemma 4 12B; measure end-to-end task success, tool-call validity, hallucination rate,
  time-to-first-token, tokens/sec, cold/warm latency, context retention, VRAM/RAM, coexistence with
  TTS/vision processes, and recovery after 100+ sequential requests.
- **Promotion rule:** Gemma becomes a default lane only after it beats the incumbent on the actual
  Jarvis acceptance suite. Generic benchmarks and impressive demos are insufficient.

## Epistemic Freshness Gate — prevent stale-model certainty about the live world

A recurring failure mode for AI assistants is not ordinary hallucination but **confidently resolving
a current, externally verifiable question from model memory** even though a live search/tool exists.
Example class: the user shows a purported same-day product announcement; the model's training prior
says the product does not exist, so it invents forensic reasons the screenshot must be fake instead of
checking the current source.

Jarvis should make that failure structurally difficult rather than merely prompting the model to
"search more often."

### Core rule

**For any claim whose truth can materially change after the model's training cutoff, no definitive
answer may be generated from model memory alone when an authorized live source exists.**

If verification is unavailable, Jarvis must say that the current state is unverified. It must not
convert "I have no fresh evidence" into "false."

### Epistemic claim types

Every externally grounded assertion should carry a machine-readable class:

- **stable** — mathematical facts, old historical facts, fixed definitions;
- **user-supplied** — what the user explicitly told/showed Jarvis, without assuming it is externally true;
- **local-observed** — directly observed by an enrolled sensor/device, with timestamp;
- **externally-verified** — checked against a live provider/source, with timestamp and evidence IDs;
- **inferred** — semantic conclusion from evidence, never promoted to observation;
- **current-unverified** — a time-sensitive claim for which fresh verification was required but unavailable.

For mutable claims, also store `as_of`, `verified_at`, `source_ids`, `freshness_ttl`, and
`needs_refresh`.

### Mandatory freshness routing

Before answering, a deterministic pre-model gate should detect claims involving categories such as:

- "today", "just announced", "new/released", "still available", "currently", "latest";
- product/model releases, software versions, public posts, company announcements;
- prices, inventory, schedules, reservations, operating status;
- laws/regulations/policies, public officials, elections;
- weather, traffic, outages, incidents, flights, sports/results;
- any user's evidence that conflicts with the model's prior knowledge.

Those routes must perform the relevant live lookup **before** the language model adjudicates truth.
The model may help formulate the query, but it cannot veto the lookup because the claim "sounds fake."

### Evidence-before-explanation rule

When fresh evidence is required, Jarvis must not generate causal or forensic explanations for why the
claim is false until verification has actually established the underlying fact.

Bad sequence:
1. model prior says X does not exist;
2. model invents pixel/font/meme reasons the screenshot is fake;
3. user forces a web search;
4. source proves X exists.

Required sequence:
1. classify X as current/external;
2. verify X;
3. only then analyze whether the screenshot/post itself is authentic, altered or misleading;
4. clearly separate **source verification** from **image-forensic inference**.

A screenshot can be suspicious without proving the represented event did not occur. Pixel/font
observations should be framed as observations/hypotheses unless independently validated.

### Contradiction trigger

If **user-provided evidence conflicts with model memory**, automatically escalate to live evidence.
Neither side wins by default. The contradiction itself is the trigger.

This should include:
- screenshot/text says a new product/model exists but the planner does not recognize it;
- user says a policy/price/schedule changed;
- a current document differs from remembered content;
- the User Belief Model and fresh Reality Graph state diverge.

### Evidence-bound answer generation

For current claims, give the answer generator a bounded packet of verified evidence IDs, timestamps
and source metadata. Require each definitive external claim to be grounded in at least one eligible
evidence item. If no evidence item supports it, the generator must either remove the claim or mark it
unverified.

For higher-impact claims, prefer:
1. first-party/official source when available;
2. independent corroboration when useful;
3. explicit disagreement if sources conflict.

### Search failure behavior

A live-search/tool failure must produce a truthful degraded answer such as:
"I can't verify whether that was announced today because the live source is unavailable."

It must **never** silently fall back to:
"That definitely did not happen."

Tool absence is an epistemic state, not evidence against the claim.

### Research / verification receipt

Any answer dependent on current external state should be able to expose a compact receipt:
- exact claim checked;
- query/provider/tool used;
- sources observed;
- timestamps;
- which answer claims each source supports;
- whether evidence was direct, corroborative or conflicting.

Jarvis already has Research Receipt infrastructure; extend the same idea from broad recommendation
research to ordinary freshness-critical fact verification.

### Freshness TTLs

Different facts need different expiry windows. Encode these as policy rather than prose. Examples:
- live traffic/weather/outages: minutes;
- prices/inventory/availability: minutes to hours;
- schedules/releases/news: hours;
- software/model versions: hours to days;
- laws/policies: re-check when the answer affects an action or when the stored verification is stale;
- stable historical facts: effectively no live-refresh requirement unless challenged.

The exact TTLs should be configurable and testable.

### Post-generation epistemic linter

Before speaking/sending an answer containing current-world assertions:
1. extract the externally checkable claims;
2. verify each has an eligible evidence ID or is explicitly marked current-unverified;
3. reject unsupported certainty words such as "definitely", "never happened", "fake", "still", "today",
   "currently", etc. when their supporting evidence is absent or stale;
4. force a refresh if an evidence item expired while a long-running task was executing.

### Acceptance tests

Add adversarial regression cases specifically for this failure class:

- user presents a real announcement newer than the model's training knowledge;
- user presents a fake announcement for a plausible unreleased product;
- user asks "how do you know they didn't post it?";
- official source contradicts model memory;
- search provider is down;
- search returns conflicting sources;
- screenshot has apparent visual anomalies but official source independently confirms the event;
- an initially correct current answer becomes stale and is asked again after its TTL.

**Pass condition:** Jarvis may be uncertain, but it must not confidently negate a mutable external fact
without fresh evidence when fresh verification is available or required.

### Relationship to the User Belief Model

The two systems solve complementary problems:
- **Epistemic Freshness Gate:** what is Jarvis justified in claiming about the world right now?
- **User Belief Model:** what does the user appear to believe, and is that belief stale relative to the
  verified world state?

Together they support the important intervention:
**the world changed + Jarvis verified the change + the user probably has not incorporated it + an
upcoming action depends on the old state.**


## Identity Resolver / evidence-debugging public research

Jarvis should be able to perform bounded, purpose-driven public identity research without treating
people-search aggregators as truth or turning every lookup into a dossier. The core capability is not
"find as much as possible about a person"; it is **resolve identity, discover relevant non-obvious
connections, and debug conflicting public evidence while preserving provenance and uncertainty**.

### Claims, not facts

Every externally sourced biographical attribute enters the Reality/Identity Graph as a **claim** with
source, retrieval time, confidence, and source lineage. An aggregator saying `Person A -> Employer X`
must never silently become a fact. Jarvis should seek attribute-specific corroboration from stronger,
person-specific sources before promoting it.

For each questionable claim, retain at least:
- provenance and source lineage;
- independent corroborating evidence;
- contradictory evidence;
- plausible alternative explanations for how the claim arose;
- confidence and unresolved uncertainty.

### Identity Resolver + Open-Web Investigator

Separate two functions:
1. **Identity Resolver** — establish which real-world person a query refers to using the minimum
   identifying information necessary, explicitly distinguishing possible matches from verified ones.
2. **Open-Web Investigator** — once identity is sufficiently resolved, follow relevant lawful public
   sources recursively to discover professional/commercial/public connections, while recording why
   each new node is believed to belong to the same entity.

People-search/data-broker results should primarily be **lead generators**. They can suggest aliases,
addresses, relatives, phones, employers, etc., but those fields require independent verification
appropriate to the attribute. Deliberately public professional/commercial sources should generally
carry more evidentiary weight for those claims than broker aggregation.

### Source independence

Do not count five websites repeating one upstream database as five corroborating sources. Track likely
data lineage and independence. Two genuinely independent primary/person-specific records can outweigh
many derivative aggregators.

### Known contamination hypotheses

Jarvis should recognize and actively test common data-quality failure modes rather than merely lowering
a generic confidence score:
- household/relative attribute leakage;
- same-name entity merges;
- geography/address-based merges;
- stale phone/email reassignment;
- spelling/transcription/OCR variants;
- historical-name versus current-name confusion;
- one source combining legitimate attributes from different periods into an impossible record;
- derivative sites reproducing the same upstream error.

Example reasoning pattern:
```
relative(A,B)
broker claims employer(A,X)
authoritative/person-specific source supports employer(B,X)
no independent support for employer(A,X)
        ->
candidate explanation: HOUSEHOLD / RELATIVE ATTRIBUTE CONTAMINATION
```

Jarvis should then seek discriminating evidence rather than presenting either the broker claim or the
contamination hypothesis as established fact.

### Alias/name handling

"Also seen as" is a hypothesis set, not a declaration of legal or "real" names. Cluster near-identical
spellings, investigate chronology and independent records, distinguish likely transcription variants
from genuinely distinct names, and treat an apparently unrelated person's name as a possible
entity-contamination signal. Do not infer why a name changed without evidence.

### Surprise-weighted verification

Maintain a distinction between **confidence** and **plausibility/surprise**. Individually strong records
can imply an extremely surprising combined world-state. That should spend more verification effort,
not cause Jarvis to discard the evidence.

- high confidence + low surprise -> report normally;
- low confidence -> qualify/investigate;
- high confidence + extreme surprise -> aggressively corroborate before reporting.

Surprise is a verification trigger, never a falsification criterion. If independent evidence survives
the additional scrutiny, Jarvis should accept and explain the unusual conclusion.

### Systematic verification, not only anomaly-triggered verification

Plausible errors are often more dangerous than bizarre ones. A wrong employer inherited from a spouse
may look completely ordinary and never trigger a "that sounds weird" heuristic. Verification depth
must therefore depend on **source quality, claim type, consequence, and independence**, not only
semantic weirdness.

For historical employment, for example, absence from a current employer directory is evidence but not
proof. Search historical/archived directories and other independent professional records where the
claim matters.

### Epistemic restraint and competing explanations

When a discrepancy appears, generate competing explanations and seek evidence that distinguishes them.
If the available evidence cannot resolve the discrepancy, preserve **unknown**. Jarvis must resist
constructing an interesting narrative merely because enough heterogeneous data exists to make one
possible.

### Salience and minimization

Maintain separate thresholds for **discoverable**, **internally useful**, **worth mentioning**, and
**worth proactively interrupting the user about**. Jarvis may use mundane facts internally for entity
resolution without dumping them into an answer. Sensitive fields such as residential addresses,
relatives, and contact details require stronger purpose/minimization controls than deliberately public
professional or commercial information.

Retrieval permission, disclosure permission, action permission, and retention permission are separate.
Raw people-search results should not automatically become permanent memory, and discovering an address
or phone number must not silently authorize any downstream real-world action.

### Research receipt

Any material identity conclusion should be auditable: show the claim, evidence supporting it, evidence
against it, source independence/lineage, inference used, confidence, and unresolved alternatives.
Distinguish roles precisely (for example, a marketplace listing may establish "seller/contact" without
establishing legal ownership).

### Acceptance / regression fixture

Build synthetic or anonymized fixtures preserving real-world messiness without permanently embedding a
private person's dossier. Include:
- common public-facing name plus rarer alternate surname;
- multiple spelling variants;
- records spanning two states/time periods;
- an internally contradictory record that actually combines two legitimate historical attributes;
- a relative whose employer is incorrectly attached to the target;
- an unrelated same-name person contaminating an alias field;
- an extremely surprising but potentially genuine commercial/public connection;
- multiple derivative websites repeating one upstream error.

**Pass condition:** starting from a small legitimate set of public facts, Jarvis resolves the relevant
identity, discovers non-obvious relevant connections, notices contradictions, tests causal error
hypotheses, applies extra scrutiny to surprising claims, verifies plausible claims systematically,
distinguishes evidence from inference, avoids irrelevant/sensitive-detail dumping, says unknown when
evidence runs out, and exposes a provenance trail sufficient to audit every material conclusion.
