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
