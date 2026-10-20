# Jarvis for MRB — Complete Capabilities, Architecture, Build History, and Current Verification State

> **Repository state document.** This file describes the current `US0RIS/Jarvis-for-MRB` source tree after the fixed world-model integration endpoint was implemented.
>
> **Critical status distinction:** the repository is now **source-complete against the fixed twelve-criterion endpoint**, but the newest source has **not yet been pulled, installed, migrated, regression-tested, restarted, and exercised on the home Windows PC**, and the matching iPhone source has **not yet been rebuilt and runtime-tested on the physical iPhone**. Therefore this document uses “implemented in source” deliberately. It does **not** claim that every newly added behavior is already deployed or that the test suite has passed.
>
> The fixed completion contract is in `FIXED_ENDPOINT_ACCEPTANCE.md`. Deployment, diagnostics, and rollback procedures are in `WORLD_MODEL_OPERATIONS.md`.

---

## 1. What Jarvis is

Jarvis is a private, local-first personal agent intended to behave as a coherent personal operating system rather than a collection of unrelated chatbot features.

Its fundamental architecture is:

```text
                                PRIVATE USER WORLD
                                      |
                    +-----------------+-----------------+
                    |                                   |
              perception/events                    private sources
                    |                                   |
         Ray-Ban Meta glasses                 Gmail / Calendar / notes
         iPhone sensors/frameworks            meetings / jobs / journals
         PC foreground context                prior conversations / state
                    |                                   |
                    +-----------------+-----------------+
                                      |
                                      v
                         PERSISTENT WORLD MODEL
                    entities / identities / aliases
                    events / beliefs / commitments
                    relations / documents / terms
                    intentions / attention / decisions
                    action attempts / verification
                                      |
                                      v
                         SITUATIONAL REASONING
                    relevance / situation compiler
                    document changes / term conflicts
                    Executive Loop / proactive brief
                                      |
                                      v
                            PERMISSION GATE
                  read -> local write -> external write
                       destructive -> security
                                      |
                                      v
                                TOOL/ACTION
                                      |
                                      v
                           INDEPENDENT OBSERVER
                                      |
                                      v
                       VERIFIED UPDATED WORLD STATE
```

The desired causal loop is now explicit in source:

```text
world state
   -> persistent intention
   -> attention
   -> decision
   -> permitted action attempt
   -> expected outcome
   -> independent observation
   -> verified / failed / timed out / unverified
   -> updated world state and Executive priority
```

The glasses, iPhone, PC, voice interface, background services, private information sources, and tools are intended to be different **sensors, interfaces, and actuators around one world state**, not independent assistants with separate memories.

---

## 2. Current status vocabulary

This repository contains capabilities from several generations of work. The following labels should be interpreted literally.

### Source implemented

The code exists in the repository and is wired into the intended architecture.

### Previously deployed / historically working

A capability existed on the user’s previously running Milestone-13-era backend/iPhone stack before the latest world-model integration work. It still needs regression testing after the new source is deployed.

### Requires backend deployment verification

The source is present, but the Windows service has not yet been updated/restarted/tested with the new code.

### Requires iPhone build verification

The Swift source is present, but Xcode has not yet built and run the newest revision on the physical iPhone.

### Platform-limited / deliberate boundary

The capability is intentionally not represented as available because the platform cannot safely/reliably support it or because the project deliberately excludes it.

---

# PART I — USER INTERFACES, VOICE, AUDIO, AND WEARABLES

## 3. Ray-Ban Meta glasses integration

### 3.1 Meta Wearables Device Access Toolkit

The iPhone app integrates Meta’s Wearables Device Access Toolkit (DAT) for compatible Ray-Ban Meta glasses.

The source supports:

- DAT device registration through the Meta AI app;
- camera permission and eligibility state;
- persistent device selection state;
- live Ray-Ban camera preview on the iPhone;
- sampled camera-frame transport to the PC for backend vision;
- local iPhone processing of recent DAT frames;
- Bluetooth HFP microphone selection when the glasses expose a hands-free input;
- speech playback back through the corresponding Bluetooth hands-free route.

The app keeps the relevant DAT selector/listener objects alive rather than creating them transiently for each camera request, which avoids losing device eligibility/camera-session state.

### 3.2 Glasses as the primary conversational interface

The intended interaction is hands-free:

```text
wearer speaks -> Ray-Ban HFP mic -> iPhone Apple Speech
             -> local iPhone capability OR authenticated PC backend
             -> generated response -> iPhone audio -> Ray-Ban speakers
```

The phone remains the transport/privacy/control boundary between the wearable and the PC.

---

## 4. Hands-free conversation system

The iPhone source includes a continuous Jarvis conversation controller rather than only push-to-talk.

### 4.1 Wake behavior

Supported interaction patterns include:

```text
Jarvis, <command>
```

and:

```text
Jarvis.
```

followed by Jarvis acknowledging and waiting for the request.

### 4.2 Five-second conversational follow-up window

After an ordinary response, Jarvis keeps a short follow-up window open. Speech that **begins** inside the window becomes the next turn without requiring the wake word again. The utterance is not truncated merely because the nominal five-second window expires after speech has already begun.

### 4.3 Barge-in

The iPhone listens for real user interruption during Jarvis speech playback. It can:

- stop current playback;
- preserve the new recognized request;
- hand the interruption into the normal conversation path;
- filter likely playback echo so Jarvis is less likely to interrupt itself.

This supports interactions such as:

```text
Jarvis: There are several things to consider—
User: Actually, just give me the most important one.
```

### 4.4 Dictation-aware silence handling

Longer commands—especially email bodies, URLs, spelling, or other dictation-like requests—receive more tolerant silence timing so ordinary pauses are less likely to submit an incomplete fragment.

### 4.5 Speech vocabulary and corrections

The frontend can bias Apple Speech using custom contextual strings. Existing source specifically includes custom handling for names/terms used heavily in Jarvis and supports user-added personal vocabulary.

### 4.6 Recognition diagnostics

The iPhone records frontend speech information including:

- recognized text;
- partial/final recognition state;
- segment-confidence information;
- active audio route;
- voice state;
- timing information for the turn.

### 4.7 Quiet-speech mode

A frontend option tunes interaction assumptions for deliberately quiet microphone speech. This is ordinary acoustic speech recognition. It is **not** subvocal EMG, lip reading, thought decoding, or any representation of those capabilities.

---

## 5. Streaming response and speech pipeline

### 5.1 Streaming language-model output

The iPhone uses the backend streaming command path rather than waiting for an entire response before updating the interface.

The response can be delivered as incremental text while generation continues.

### 5.2 Chunked local neural TTS

Current backend source `tts_client.py` makes **Kokoro** the default runtime TTS:

- default model string: `kokoro`;
- default voice: `bm_george`;
- HTTP speech service on the local PC/WSL path;
- local health checking;
- WSL autostart support;
- WAV synthesis returned to the iPhone;
- explicit rejection of an older Qwen3-TTS health response when Kokoro is expected.

This resolves an older documentation inconsistency: some earlier iOS documentation still describes Qwen3-TTS as the runtime. Current backend code explicitly treats Qwen3-TTS as the older server and expects Kokoro by default. The post-deployment test must verify the actual configured voice service on the home PC.

### 5.3 Apple speech fallback

The iPhone retains Apple speech synthesis as a fallback when the backend neural-voice service cannot be used.

### 5.4 Adaptive / forced whisper

The frontend can reduce delivery intensity based on environmental assumptions and can force a bounded whisper-style mode for a chosen interval before returning to normal voice.

### 5.5 Audio HUD cues

Compact local earcons can signal states such as:

- thinking;
- scan/activity;
- warning/attention;
- task completion;
- other frontend interaction transitions.

HUD cue volume is user-controlled and can adapt to the measured ambient acoustic floor.

### 5.6 Smart Windows audio damping

The backend includes optional PC output-volume damping. During an active Jarvis conversation it can temporarily lower the Windows master-output level and restore the previous value after the interaction.

This affects the Windows audio endpoint; it is not represented as arbitrary smart-speaker control.

---

# PART II — MODELS AND REASONING

## 6. Planner/model architecture

The existing backend architecture uses local Ollama-hosted planning models with fast-vs-quality routing.

Current project documentation identifies:

- `qwen3:8b` for routine, low-latency conversation/tool routing;
- `qwen3.8:27b` for harder reasoning, planning, workflow, code, and repair tasks;
- `think: false` for both planner models to prioritize interactive latency.

The iPhone records which planner/model route was reported for a turn.

### 6.1 Automatic routing

Requests can be routed to the smaller/faster or larger/higher-capability model based on task difficulty. The model selection is not supposed to change permission authority; a larger model does not receive a stronger action class.

### 6.2 Embeddings

`nomic-embed-text` is used for semantic episodic/unified-memory retrieval.

### 6.3 Vision model

Moondream is used by the PC vision stack for passive/recent-frame visual analysis.

### 6.4 Apple on-device Foundation Models

On supported Apple Intelligence hardware/OS versions, the iPhone has a local model route for stable explanatory questions and bounded local-memory synthesis.

The frontend router refuses or falls through from this local model when the request materially requires:

- current/fresh web information;
- Gmail/inbox data not locally available;
- private PC/browser/file state;
- external actions;
- device/app control owned by the PC;
- current general semantic scene understanding that requires the backend vision path.

The local model is not granted external-write authority merely because it can generate text.

---

# PART III — VISION, PERCEPTION, AND RECENT PHYSICAL CONTEXT

## 7. Thirty-second visual memory

Jarvis has two related recent-vision concepts.

### 7.1 Backend visual-history buffer

The PC-side architecture retains a roughly 30-second **RAM-only** rolling recent-frame history for questions such as:

```text
What did that passing sign say?
What was I just looking at?
Copy that error code.
```

Raw rolling frames are deliberately not added to long-term episodic memory.

### 7.2 iPhone local visual cache

The frontend separately keeps a bounded, downsampled RAM-only DAT frame ring for local Apple Vision operations and diagnostics.

It can expose local information such as:

- cache count;
- newest-frame age;
- local capture FPS estimate;
- compressed-frame size;
- thumbnail timeline;
- local perception status.

### 7.3 Important current deployment boundary

The source repository contains backend work for conversational recent-scene questions such as:

```text
Jarvis, what can you see right now?
```

but that compatibility fix has **not yet been deployed and tested on the user’s currently running Windows backend**. It must remain marked “backend update pending” until the final deployment/test phase.

The local Apple Vision tools below are independent of that general semantic-scene path.

---

## 8. iPhone Apple Vision perception

The frontend can process the latest glasses frame locally for narrower deterministic/structural tasks.

### 8.1 OCR

Apple Vision text recognition supports local commands such as:

```text
Read this.
Copy this text.
```

The local copy command writes recognized text to the **iPhone clipboard**.

### 8.2 QR / barcode scanning

The iPhone can decode supported visible QR/barcode payloads from the current Ray-Ban frame without requiring Moondream.

### 8.3 Human/face rectangle detection

The local perception layer can detect/count structural human or face rectangles. Detection is not automatically identity.

### 8.4 Rectangle detection

Apple Vision rectangle requests provide low-cost geometric perception for local tools.

### 8.5 Saliency

The frontend can request Apple Vision attention-based saliency information as a structural visual signal.

### 8.6 Scene-change detection

The iPhone can compare image feature-print distances between recent frames and record a local “major visual change” event when the whole-frame difference crosses a threshold.

It intentionally does not infer *which* semantic object changed merely from the feature-print distance.

---

## 9. Passive PC vision

When passive vision is enabled, the iPhone samples Ray-Ban frames to the authenticated backend.

Remote/Tailscale operation can reduce resolution/frequency to conserve bandwidth. Project documentation describes approximately:

```text
LAN path       ~1 sampled frame/sec, up to 512 px
Tailscale path ~1 sampled frame/3 sec, up to 384 px
```

Single explicit visual scans can use a higher-quality frame than passive sampling.

---

## 10. Conservative visible hazard/error alerts

Backend vision can generate proactive physical/terminal alerts only when the image itself provides high-confidence visible evidence.

Examples of intended visible cues include:

- obvious open flame/hot-tool situations;
- clearly running/spilling liquid;
- clear trip/impact hazards;
- visibly open/ajar access points when immediately relevant;
- clearly legible local terminal/application error messages.

Explicit non-claims include:

- inferring a closed door is unlocked;
- claiming a present appliance is dangerous without visible evidence;
- inventing hidden hazards;
- representing the system as a safety-certified hazard detector.

---

## 11. Spatial / last-seen object memory

The backend can preserve conservative last-seen object sightings with:

- object identity/name;
- observed scene text;
- location context;
- time;
- confidence;
- provenance event.

This supports questions such as:

```text
Where did I last see my keys?
```

It is evidence-based memory, not a centimeter-accurate 3D indoor map and not safety-critical visual homing.

---

# PART IV — PEOPLE, PERSONAL OBJECTS, AND LOCAL CONTEXT

## 12. Known People: private closed-set face recognition

Known People is explicitly **closed-set**. Jarvis does not attempt public stranger identification.

### 12.1 Enrollment

The user explicitly creates a person profile and provides multiple clear samples.

The local pipeline:

1. detects the relevant face;
2. crops the face region;
3. creates an Apple Vision `VNFeaturePrintObservation`;
4. discards the enrollment image for this feature after the feature print is created;
5. stores the contact label, private note, calibration information, and archived feature prints in a this-device-only Keychain-backed store.

### 12.2 Matching

Recognition compares current frame feature prints only against explicitly enrolled people.

Continuous recognition uses conservative confirmation rather than accepting every single nearest match. If candidates are too close, the result remains ambiguous/unknown instead of forcing an identity.

### 12.3 Supported local person questions

Examples include:

```text
Who is this?
Who am I talking to?
What do I know about this person?
What did I talk about with them?
```

### 12.4 Local person brief

A confidently matched enrolled person can be connected to:

- the private Known People note;
- local bounded conversation context;
- locally captured encounter summaries.

Spoken briefing is separately opt-in because reading private context aloud near the recognized person can itself be a privacy problem.

### 12.5 Post-encounter context

When explicitly enabled, the frontend can save a bounded recent recognized-speech excerpt after a known-person encounter. Where Apple’s on-device model is available it can make a short factual summary.

It does **not** use a speaker voiceprint and does **not** infer another person’s emotions, stress, honesty, tension, or mental state.

### 12.6 PC world-model identity bridge — new source architecture

The unified world model now lets an enrolled person’s explicit local identifier resolve to the same canonical person as independent evidence such as:

- Gmail email address;
- Calendar attendee/organizer identity;
- meeting/document participation;
- commitments;
- future supported sources using the same stable identity scheme.

Identity resolution is hardened against conflicting strong IDs. A unique exact name may bridge two compatible namespaces, but two different email IDs are not silently collapsed merely because they have the same display name.

### 12.7 Unenrollment semantics — new source architecture

Removing a person from an authoritative full Known People snapshot means **face enrollment revoked**, not “erase every historical mention of this human.”

The backend source now:

- removes the `iphone_known_person` external ID;
- removes aliases sourced specifically from Known People;
- strips copied private enrollment `note` and `contact_id` metadata;
- writes a current `known_person_enrollment = revoked` belief;
- records a provenance event documenting the revocation;
- preserves independent Gmail/Calendar identity and historical evidence if present;
- tombstones the live identity if no independent identity source remains, preventing the old enrolled name from relinking future text;
- removes current derived graph relationships from a tombstoned no-independent-identity entity while retaining historical source events.

A hypothetical “forget this person everywhere” feature would be a distinct destructive privacy operation. The system does not infer that request from face unenrollment.

---

## 13. Private personal inventory

The iPhone source includes explicit enrollment/matching of important objects.

### 13.1 Enrollment

The user supplies several object images. Apple Vision image feature prints are stored locally; raw enrollment photos are not retained by the feature.

### 13.2 Matching

Matching is deliberately conservative and works best when the enrolled object occupies a substantial part of the frame.

### 13.3 Last-seen metadata

A confident match can update:

- last-seen time;
- approximate local location/coordinates when local location context is enabled.

This metadata can participate in local inventory questions and can be exported to the backend world snapshot in bounded form.

---

## 14. Rolling local audio/speech context

When enabled, the iPhone can keep approximately 30 seconds of local rolling microphone context, including a bounded recent recognized-speech transcript and RAM audio buffer.

The raw rolling audio is not silently persisted as long-term memory. Explicit incident preservation is a separate user action.

---

## 15. Environmental sound classification

The frontend can use Apple Sound Analysis to classify supported environmental sounds from the existing microphone feed.

High-confidence local classifications can be displayed and selected alarm-like categories can support conservative local alerts.

This is advisory and is not represented as a safety-certified detector.

---

## 16. On-device translation

The iPhone source includes a local translator using Apple’s Translation framework/system language models.

It can work with typed/recently recognized speech and can speak the translated result. Required OS language-model downloads/availability remain an Apple-platform dependency.

---

# PART V — IPHONE LOCAL INTELLIGENCE AND PRODUCTIVITY

## 17. Local-first capability routing

A major frontend architectural change was replacing a growing stack of ad-hoc local command wrappers with an explicit capability router.

Each capability pack can declare:

- stable ID;
- human-readable name;
- category;
- priority;
- effect class;
- requirements;
- lazy-activation policy;
- intent predicate;
- availability predicate;
- execution handler.

Current named capability packs include:

- Camera Master Privacy Gate;
- Read-only Pack Composer;
- Deterministic Utilities;
- Native Calendar;
- Native Reminders;
- Jarvis Local Timers;
- Context Capsule Writer;
- Unified Local Memory;
- Native Contacts;
- Vision / Known People / Inventory;
- Local Executive;
- Frontend Controls;
- Apple Stable-Question Brain;
- Legacy Frontend Compatibility Adapter.

The compatibility adapter is intentionally last priority so old frontend features continue to work while higher-value capabilities receive explicit typed routing.

---

## 18. Camera master privacy gate

The Stop Camera/master privacy latch has the highest frontend routing priority for visual requests.

If the camera is stopped, lower visual capability packs do not get to “decide” to reactivate it. This is both a routing invariant and a deeper camera-manager privacy latch.

---

## 19. Deterministic local utilities

The iPhone can answer stable utility requests without a model/PC round trip, including:

- local time;
- common city/time-zone time;
- date/day;
- simple arithmetic;
- percentages;
- common length conversion;
- mass conversion;
- volume conversion;
- speed conversion;
- temperature conversion.

This specifically prevents tool-selection errors such as interpreting “What time is it in DC?” as a request to inspect whether the Windows Clock app is running.

---

## 20. Native iPhone Calendar

With EventKit permission, the iPhone can locally answer Calendar queries such as:

```text
What meetings do I have tomorrow?
What's on my calendar today?
What's my next meeting?
```

This is separate from the PC Google Calendar connector and can work from calendars already exposed to iOS.

---

## 21. Native Apple Reminders

With explicit Reminders permission, the iPhone can locally create Apple Reminders, including relative reminders such as:

```text
Remind me in 20 minutes to ...
```

This is distinct from PC-side scheduled Jarvis jobs.

---

## 22. Local Jarvis timers

The frontend can create notification-backed timers without using or inspecting Clock.app.

It can support:

```text
Set a timer for 10 minutes.
How much time is left on my timer?
Cancel my timer.
```

Notification delivery allows the timer to survive ordinary app suspension.

---

## 23. Native Contacts bridge

With Contacts permission, the iPhone can locally answer contact-detail queries such as stored phone/email details.

Known People profiles can be linked to Contacts when a unique match exists. Ambiguous name matches are deliberately not auto-linked.

A face match is advisory context and is not sufficient authority for a consequential external action.

---

## 24. Encrypted Context Capsules

The iPhone can explicitly save a “remember this context” snapshot.

Available capsule material can include bounded values such as:

- active Jarvis mode;
- currently matched enrolled person, if any;
- recent OCR text;
- last recognized command;
- last Jarvis response;
- bounded clipboard excerpt;
- coarse location context when enabled.

Capsules are encrypted with AES-GCM using a device Keychain-protected key and complete file protection.

They do not silently persist raw camera frames or the rolling raw microphone buffer.

---

## 25. Unified local iPhone memory search

The Local Memory interface can search across iPhone-side Jarvis state such as:

- context capsules;
- device-session conversation history;
- Known People profiles/notes;
- local perception/power events;
- captured known-person encounters;
- enrolled inventory;
- goals;
- Waiting-On items;
- local action receipts.

Where Apple’s on-device model is available it may synthesize an answer **only from the retrieved local records**; otherwise matching records are presented directly.

---

## 26. Local goals, Waiting-On, reminders, encounters, and event state

The frontend maintains explicit local productivity/context objects used both by local intelligence and the backend world-snapshot bridge.

The bounded world snapshot currently includes metadata for:

- Known People;
- goals;
- Waiting-On items;
- personal inventory and last-seen metadata;
- reminders;
- encounter summaries/transcript excerpts;
- selected local power events;
- local action receipts;
- active mode.

These are structured state, not generic model memories.

---

## 27. Optional motion/travel context

When enabled and permitted, Core Motion/Core Location can expose coarse frontend context such as:

- stationary;
- walking;
- running;
- cycling;
- driving;
- speed;
- course;
- altitude diagnostics.

This is optional and permission-gated.

---

## 28. App Intents, Shortcuts, and Action Button

The iPhone app registers App Intents for operations including:

- Talk to Jarvis;
- local Visual Scan;
- Read Visible Text;
- Toggle Passive Vision;
- Toggle Meeting Notes;
- Toggle Jarvis spoken responses.

Where iOS exposes those intents as App Shortcuts, the user can assign them through Shortcuts or the Action Button.

A dedicated WidgetKit/Dynamic Island/Control Center extension has **not** been represented as implemented; it would require additional extension targets/provisioning/lifecycle work.

---

## 29. Offline command staging

If both configured backend paths are unreachable, the iPhone can stage commands locally rather than discarding them.

Crucially:

- staged commands do **not** automatically replay when connectivity returns;
- the user explicitly sends the next queued item.

This avoids unexpected delayed consequential actions.

---

## 30. Local response quality shield

Every explicit capability-pack response can pass through deterministic structural verification.

Examples of checks include rejecting:

- empty answers;
- pathological repeated salutations;
- time questions answered with Clock application state;
- arithmetic/conversion requests answered with app-status output;
- read-only capability packs claiming they performed an external write.

If a read-only local answer is rejected, the request can fall through to the backend rather than being spoken as authoritative.

A questionable **write** is not automatically retried because retry could duplicate side effects.

An optional Apple-model semantic audit can inspect selected read-only answers in the background, but it is advisory and does not authorize actions.

---

## 31. Encrypted frontend execution receipts

The capability router records bounded local receipts with information such as:

- chosen capability pack;
- effect class;
- packs considered;
- requirements;
- routing latency;
- accepted/rejected/backend-fallback result;
- deterministic quality verdict;
- bounded command/response excerpts;
- optional semantic-audit result.

Receipts are AES-GCM encrypted with a Keychain-held key and complete file protection. The frontend retains a bounded recent set rather than an unbounded log.

---

## 32. Frontend feature guide and regression prompts

The iPhone includes a searchable Feature Guide in source. Each feature entry can carry:

- category;
- title;
- summary;
- detailed behavior;
- example prompt;
- verification procedure;
- status (`Ready`, `iPhone-only`, `Setup required`, `Optional`, `Backend update pending`, `Platform-limited`);
- whether the example is safe to run automatically.

The capability architecture also includes dry-run canonical routing cases, allowing frontend routing predictions to be checked without executing writes.

---

# PART VI — CONNECTIVITY AND CROSS-DEVICE TRANSPORT

## 33. Authenticated backend transport

The iPhone communicates with the Windows backend through authenticated requests using a bearer API token.

The source supports:

- ordinary command requests;
- streaming command responses;
- TTS requests;
- meeting endpoints;
- health/status calls;
- companion events;
- persistent companion/WebSocket-style state exchange used by the world-snapshot path.

The backend should not be exposed directly to the public Internet.

---

## 34. LAN to private Tailscale failover

The companion can prefer the local-network backend and fall back to a private Tailscale Serve endpoint when away from home.

The intended security posture is:

- no public port-8765 exposure;
- no Tailscale Funnel;
- private Tailscale Serve URL for remote access.

The frontend can separately probe LAN and Tailscale health and report approximate latency.

---

## 35. Connection diagnostics

Frontend diagnostics can report information including:

- LAN/Tailscale reachability and approximate RTT;
- voice state;
- audio route;
- Apple Speech confidence/recognition state;
- Ray-Ban registration/DAT/camera state;
- local visual-cache status/FPS/frame size;
- local perception status;
- queued offline commands;
- optional motion context;
- optional health context;
- last planner model;
- time to first response text;
- time to first playable audio;
- total frontend turn duration.

---

# PART VII — CONVERSATION, MEMORY, AND THE UNIFIED WORLD MODEL

## 36. Durable conversation history

The backend stores conversation turns in SQLite. The iPhone sends a stable session identifier so related turns can be associated across the interaction.

The architecture deliberately distinguishes:

- immediate conversational continuity;
- older semantic recall;
- structured world state.

Recent history is kept narrow by default so an old topic does not become the fallback interpretation of a poor speech recognition result. Older conversation is expanded when the user explicitly refers backward (`earlier`, `remember`, `five prompts ago`, etc.) or when structured world evidence is relevant.

---

## 37. Semantic episodic memory

Longer-term semantic memory uses embeddings for retrieval of relevant prior text. This remains useful for fuzzy episodic recall but is no longer the sole persistence mechanism for important state.

Structured entities, obligations, project terms, intentions, and action outcomes now have dedicated world-model representation instead of depending entirely on vector similarity.

---

## 38. Temporary/ephemeral state

The backend has explicit temporary state with decay/TTL semantics. Temporary state is distinct from durable world facts and from conversation history.

Closed-loop verification includes read-back support for persistent and temporary state writes where applicable.

---

## 39. Unified private knowledge index

The knowledge layer can combine structured world results and semantic retrieval over indexed private sources such as:

- Gmail;
- Calendar;
- local notes;
- prior conversations;
- newer source additions such as indexed safe Gmail attachments.

Structured world matches are preferred where they answer the question directly; semantic fallback remains available for fuzzy/episodic retrieval.

---

# PART VIII — CORE WORLD MODEL

## 40. Persistent world database

The unified world model lives in:

```text
%APPDATA%\JarvisForMRB\world_model.sqlite3
```

The core schema contains durable representations for:

### Entities

Stable things Jarvis reasons about, including examples such as:

- people;
- projects;
- goals;
- places;
- objects;
- meetings;
- documents;
- calendar events;
- reminders;
- system/world identity.

### External identities

Namespace-scoped IDs connect entities to source systems, such as:

- email addresses;
- iPhone Known People IDs;
- Calendar IDs;
- Gmail document/attachment IDs;
- other explicit source identifiers.

### Aliases

Alternate names can be associated with an entity along with source/confidence.

### Events

Events are provenance-bearing observations or actions containing:

- event type;
- occurrence time;
- record time;
- human summary;
- bounded structured payload;
- confidence;
- source kind;
- source reference;
- evidence text.

### Event/entity participation

An event can connect to entities through semantic roles such as:

- sender;
- attendee;
- organizer;
- owner;
- source document;
- observed object;
- location;
- goal;
- project;
- requester;
- other evidence roles.

### Beliefs

Beliefs support:

- predicate/value or predicate/object assertions;
- observed time;
- validity interval;
- confidence;
- `current`, `superseded`, or `disputed` state;
- source event;
- evidence;
- revision lineage.

A lower-confidence conflicting observation can be retained as disputed rather than automatically replacing stronger current evidence.

### Commitments

Commitments include:

- owner;
- action;
- deadline/date text;
- status;
- confidence;
- source event;
- resolution event;
- metadata/provenance.

---

## 41. Identity resolution hardening

The world model was specifically hardened to prevent the classic “same display name = same human” failure.

Current policy includes:

- strong external namespace+ID match wins;
- a unique exact-name entity may bridge compatible namespaces if no same-namespace strong-ID conflict exists;
- conflicting IDs in the same namespace do not collapse merely because names match.

Example:

- an explicitly enrolled `Daniel Reed` with no email identity may later acquire `daniel@example.com`;
- `daniel2@example.com` must not silently merge into an entity already bound to a different email ID solely because both display names are `Daniel Reed`.

---

## 42. Occurrence semantics

Live events such as repeated identical conversation turns or visual sightings remain distinct occurrences when they occur at different times. They are not deduplicated merely because their text happens to be identical.

Immutable source records, by contrast, can use source-specific deduplication keys to prevent duplicate ingestion.

---

## 43. Evidence-backed relation graph

`world_linker.py` adds derived current relationships with separate evidence rows.

Examples include:

- document/calendar/meeting `about_project`;
- goal `advances_project`;
- document/calendar/meeting `involves_person`;
- object `observed_at` place;
- person `present_at` place in appropriate event classes;
- person-person `interacted_with` in supported encounter/meeting evidence;
- person `associated_with_project` **only when supported by structured participant evidence**.

### 43.1 Relation confidence

Repeated independent evidence can strengthen a relation gradually, but heuristic evidence is not promoted to certainty merely through repetition.

### 43.2 Relation evidence invariant

A current derived relationship is required to have evidence. Diagnostics verifies both the existence of evidence and agreement between the stored `evidence_count` and actual evidence rows.

### 43.3 Person/project false-association fix

Earlier broad co-occurrence semantics were identified as dangerous because a sentence such as:

```text
Daniel is not on Project Apollo.
```

could otherwise create `Daniel -> associated_with_project -> Apollo`.

Current source requires structured roles such as sender, recipient, attendee, organizer, owner, assignee, participant, speaker, requester, or beneficiary before materializing person→project association. Legacy weak current edges can be retired without deleting the historical events that created them.

---

## 44. Backfill from pre-world-model stores

The repository contains one-time/idempotent migration of historical Jarvis stores into the world model.

Core backfill covers:

- conversation database;
- non-conversation episodic memory;
- spatial sightings;
- meeting sessions/actions;
- environment state.

Extended backfill covers:

- scheduled jobs;
- background tasks;
- expense records;
- generated journals.

Completion sentinels prevent normal startup from replaying the same historical stores repeatedly. A forced backfill exists only for deliberate reconstruction/recovery.

---

# PART IX — IPHONE → WORLD MODEL SYNCHRONIZATION

## 45. Bounded world snapshot

The iPhone periodically publishes a metadata-only world snapshot over the authenticated persistent companion connection.

The snapshot is semantically deduplicated so an unchanged state is not repeatedly recorded simply because the timestamp changed.

### 45.1 Included classes

As described above, bounded structured local state can include Known People metadata, goals, Waiting-On, inventory, reminders, encounter summaries, local events, receipts, and mode.

### 45.2 Explicit exclusions

The world snapshot contract deliberately excludes:

- Known People biometric feature prints;
- face-enrollment photographs;
- raw Ray-Ban camera frames;
- raw rolling microphone/audio buffers;
- incident media;
- full clipboard contents;
- privacy-zone coordinates.

The backend must not reconstruct/request those excluded channels as part of ordinary snapshot ingestion.

### 45.3 Authoritative deletion semantics

Only specific collections are treated as authoritative current-state lists, and only when the field is actually present **and a list**.

For `goals`, `waiting`, and `people`:

- explicit `[]` means “authoritatively none remain”;
- missing key means partial/unknown — do not retire anything;
- malformed non-list means partial/unknown — do not retire anything.

This hardening prevents an older/partial frontend payload from accidentally retiring every current goal, Waiting-On item, or Known People enrollment.

---

# PART X — PERSISTENT INTENTIONS AND QUERY RELEVANCE

## 46. Explicit goals become persistent intentions

`world_executive.py` materializes active explicit goals into an `intentions` layer.

Each intention can carry:

- title/objective;
- status;
- next action;
- due time;
- confidence;
- source kind/reference;
- linked entities/projects;
- linked current commitments.

Project/dependency links are rebuilt from current evidence on refresh so a stale inferred relationship does not remain attached forever after its source relation is retired.

---

## 47. Conversational goal capture

The user does not need to open a goal-management screen for every objective. Explicit language can create durable intention state.

Accepted source forms include patterns such as:

```text
Our goal is ...
My goal is ...
The goal is ...
We're trying to ...
We are trying to ...
I'm trying to ...
I am trying to ...
```

The capture layer deliberately ignores:

- questions;
- hypotheticals;
- ordinary “I want...” statements;
- short/trivial transient phrases;
- explicitly negated trying-to wording.

Explicit `by` / `before` deadline phrases are parsed conservatively with future-aware date handling.

Repeated identical declarations use a deterministic goal key so they do not create a new objective on every mention.

Canonical example:

```text
We're trying to get Project Apollo signed by Friday.
```

becomes a durable active goal/intention linked to the explicitly named Project Apollo.

---

## 48. Query-aware intention relevance

A major prompt-quality fix prevents every active goal from being injected into every conversation.

`world_relevance.py` ranks active intentions using:

- explicit executive cues;
- lexical overlap with goal/next action;
- direct entity matches;
- graph-expanded related entities;
- commitment owner/action match;
- urgency/deadline.

Ordinary non-executive turns require concrete relation/name/lexical evidence.

Thus:

```text
What should I do next?
```

may receive active intention context, while:

```text
What should I order for dinner?
```

must not be contaminated by the Apollo signing objective merely because Apollo is active.

---

# PART XI — CALENDAR, MEETING CONTEXT, AND SITUATIONAL AWARENESS

## 49. Enriched private Calendar sync

The original compact Calendar tool returned only enough metadata for normal command answers. That was insufficient for a world model because attendees/organizer/description were discarded.

`world_calendar_sync.py` adds a separate read-only private enrichment path that can ingest:

- Calendar event ID;
- title;
- start/end;
- status;
- location;
- description;
- organizer;
- attendees.

Attendee email identities use the shared email namespace, allowing a Gmail sender and Calendar attendee to resolve to the same person.

No meeting invitation/write is performed by the enrichment process.

---

## 50. Situation compiler

`world_situation.py` answers “what matters about the situation I’m entering?” rather than dumping general memory.

Situation cues include requests such as:

```text
Anything I need to know before I go in?
Prepare me for the meeting.
Who am I meeting?
What's my next meeting?
```

The compiler can:

1. optionally refresh near-term Calendar data with a throttle;
2. choose the actual current/upcoming meeting using temporal proximity plus explicit query/attendee matches;
3. ignore cancelled events;
4. avoid generic all-day events unless explicitly matched;
5. retrieve participants;
6. traverse evidence-backed relationships to projects;
7. retrieve relevant pending commitments;
8. retrieve linked active intentions;
9. retrieve recent connected evidence;
10. return one bounded `CURRENT/UPCOMING SITUATION` context.

Temporal ranking distinguishes happening-now, within two hours, eight hours, 24 hours, three days, and recent-meeting cases.

Recent evidence supports ISO and RFC email dates.

---

## 51. Proactive meeting prebrief

Before a meeting, the proactive monitor can ask the deterministic prebrief layer for actionable connected context.

It does **not** invoke a model to decide that every calendar event deserves interruption.

A contextual prebrief exists only if evidence produces something worth surfacing, such as:

- project-term discrepancy;
- pending/overdue commitment;
- active objective next action;
- meaningful connected recent evidence;
- document-version change.

It emits at most a small number of facts and prioritizes a substantive term discrepancy over a generic task reminder.

Canonical intended result:

```text
Before Project Apollo signing call:
Term discrepancy: the newer draft says 15%, versus 10% in the prior discussion.
Daniel Reed still owes the revised disclosure schedules.
```

If there is no actionable connected context, the older generic calendar reminder remains available rather than fabricating a “brief.”

---

# PART XII — GMAIL, ATTACHMENTS, DOCUMENTS, AND CROSS-SOURCE TERMS

## 52. Gmail and Contacts/Calendar tools

The backend tool surface supports Google private-data operations including:

- Gmail querying/reading;
- Gmail sending under permission + recipient allowlist controls;
- Contacts resolution;
- Calendar reads;
- Calendar queries/recent events/conflict detection;
- Calendar creation under external-write confirmation.

The same private data can be mirrored into world-model evidence without giving the model unrestricted access to unrelated host state.

---

## 53. Gmail attachment ingestion

`world_gmail_attachments.py` closes an important information gap: Jarvis can inspect text from selected recent attachments rather than merely know an email contains an attachment.

### 53.1 Safety model

Attachments are **never executed or opened through an OS application** by this indexer.

Current passive allowlist:

- `.pdf`;
- `.docx`;
- `.pptx`;
- `.txt`;
- `.md`;
- `.csv`;
- `.json`;
- `.rtf`.

It excludes executable, macro-enabled, archive, image, unknown, and otherwise unsupported types.

### 53.2 Bounds

Current source bounds include roughly:

- maximum attachment size: 8 MiB;
- maximum extracted text: 80,000 characters;
- bounded recent-message scanning.

### 53.3 Extraction

- PDF: `pypdf` text extraction;
- DOCX: passive ZIP/XML parsing;
- PPTX: passive ZIP/XML slide-text parsing;
- text/CSV/JSON: bounded text decoding;
- RTF: basic passive stripping.

No OCR is silently run over scanned PDF pages.

### 53.4 Provenance

The resulting document entity/event retains bounded metadata such as:

- Gmail message ID;
- thread ID;
- attachment reference;
- filename;
- MIME type;
- email subject;
- sender;
- byte/text size.

The sender and parent-email/document identities participate in the event graph.

---

## 54. Document version lineage and change detection

`world_document_versions.py` determines whether two attachments are plausibly versions of the same document.

It does **not** trust similar filenames alone.

Evidence can include:

- same Gmail thread;
- shared Project identity;
- content-token overlap;
- normalized matching email subject;
- filename-family normalization.

Weak candidates are rejected rather than forced into lineage.

### 54.1 Change extraction

The comparator segments text and looks for aligned changed passages. Numeric/date changes receive priority, including values such as:

- money;
- percentages;
- basis points;
- durations;
- dates;
- other explicit numbers.

A changed version creates a `document.version_changed` event. A likely equivalent revision creates `document.version_equivalent` instead of a false change alert.

### 54.2 Supersession relation

A high-confidence, evidence-backed:

```text
new_document -> supersedes -> old_document
```

relationship is created when lineage and comparison support it.

### 54.3 Chronology hardening

Version direction is based on actual source `occurred_at`, with a stable ID only as tie-breaker. Historical documents ingested later cannot become the “new version” merely because they received a larger SQLite row ID.

Migration repair can retire/rebuild legacy reversed pairs/supersession state while keeping historical comparison evidence.

---

## 55. Cross-source Project term ledger

`world_terms.py` provides deterministic extraction for a deliberately narrow set of high-value project/deal terms.

Current supported terms include:

- indemnity cap;
- indemnity basket;
- escrow / holdback;
- survival period;
- termination / break-up fee;
- purchase price;
- working-capital target / peg;
- earnout;
- interest rate;
- ownership percentage;
- signing/closing deadline.

### 55.1 Guardrails

A term observation requires:

- an explicit named supported term;
- an explicit value;
- an evidence event connected to a Project entity.

A generic number with no named term does not become a project fact. A named term with no project does not become a global fact.

### 55.2 Source confidence

Source kinds have bounded confidence conventions; attachment and explicit meeting/conversation sources can carry different confidence while all retain provenance.

### 55.3 Conflict semantics

When adjacent chronological sources give different explicit values for the same Project+term, Jarvis creates:

```text
term.changed_or_conflicted
```

This means **possible change/conflict across sources**, not “the newer source is legally controlling truth.”

Both values, source events, source kinds, occurrence times, and bounded context are retained.

### 55.4 Chronological truth

The current observation for a term is selected using actual source occurrence time, including support for RFC-formatted email dates.

Backfilled older evidence inserted later cannot displace a genuinely newer explicit observation.

Migration can repair reversed legacy conflict pairs while preserving their old provenance events.

---

## 56. Direct structured Project-term questions

`world_term_context.py` routes explicit questions such as:

```text
What's the indemnity cap on Project Apollo?
What are the current deal terms on Project Apollo?
```

to the structured term ledger rather than relying on fuzzy event search.

The result includes:

- current explicit value;
- source kind;
- source event ID;
- occurrence time;
- confidence;
- recent source discrepancy when one exists.

It requires a Project entity match and an explicit term/all-terms cue rather than guessing a project from a generic question.

---

# PART XIII — EXECUTIVE LOOP

## 57. Why the Executive Loop exists

Before this work Jarvis could retrieve many facts but did not maintain one durable operational judgment about an objective.

Criterion 6 introduced a persistent Executive layer with the conceptual transformation:

```text
“What do I know?”
        ->
“What is preventing the objective, what changed, and what should happen next?”
```

---

## 58. Persistent attention

`executive_attention` stores current attention items tied to an explicit active intention.

Examples include:

- source-term discrepancy;
- overdue commitment;
- due-soon dependency;
- objective deadline;
- meaningful document change;
- explicit next action;
- pending/failed/unverified action outcome.

When the underlying condition disappears, the attention item becomes stale rather than pretending it never existed.

---

## 59. Persistent decisions

`executive_decisions` stores a current operational decision for each active intention, with supersession history when the priority changes.

Diagnostics enforces that one intention cannot have multiple simultaneous “current” decisions.

A decision contains data such as:

- decision type;
- summary;
- rationale/evidence;
- proposed tool;
- proposed arguments;
- risk class;
- confirmation requirement;
- confidence;
- status/time.

---

## 60. Objective state compilation

An active objective can compile into states such as:

- `active`;
- `due_soon`;
- `overdue`;
- `at_risk`;
- `awaiting_verification`.

The compiled view can contain:

```text
OBJECTIVE
DEADLINE
PROJECTS
OUTCOME VERIFICATION
BLOCKERS
DEPENDENCIES / WAITING ON
RECENT CHANGES
NEXT ACTIONS
RECOMMENDED NOW
EXECUTABLE PROPOSAL
```

---

## 61. Deterministic priority

High-value conditions have explicit ordering rather than allowing an LLM to silently invent its own operational policy.

Examples:

- failed outcome verification outranks the original plan;
- timed-out/unverifiable action outcome becomes a blocker;
- substantive cross-source term discrepancy is high-priority;
- overdue commitment outranks ordinary background change;
- document changes can become review actions;
- explicit next action remains available when no stronger blocker exists.

---

## 62. Permission-aware executable proposal

The Executive Loop can map the highest-priority item to an existing tool/action proposal.

Examples:

- term discrepancy -> `knowledge.search` for underlying private evidence;
- dependency on someone with known email -> `gmail.query` to determine whether they already satisfied it before following up;
- document change -> structured/private knowledge search.

The proposed tool is checked against `permissions.py` before it is exposed as executable.

The Executive Loop does **not** create a new privileged action channel.

---

## 63. Exact proposal correlation

For a model/planner to consume an Executive action proposal, the proposed tool and arguments must match the deterministic persisted proposal exactly.

An altered argument set does not inherit Executive provenance/authority.

For confirmation-delayed actions, a bounded one-shot correlation survives the confirmation boundary and is consumed only by the actual confirmed execution.

---

## 64. Streaming voice integration fix

A subtle integration defect was found during Criterion 6: current world/Executive context on streaming voice turns could be removed by the same anti-topic-gravity logic that intentionally drops stale conversation history.

The source now keeps freshly retrieved operational context separate from old chat-history suppression. This prevents the voice path from discarding the very current state the world model was created to provide.

---

# PART XIV — CLOSED-LOOP ACTION VERIFICATION

## 65. Tool return success is not outcome success

Criterion 7 changed the semantics of action completion.

Jarvis now distinguishes:

```text
“The API/tool accepted the action.”
```

from:

```text
“I have independent evidence that the intended state now exists.”
```

---

## 66. Verification ledger

`action_verifications` stores explicit action-outcome state.

Supported states:

- `pending`;
- `verified`;
- `failed`;
- `timed_out`;
- `unverified`;
- `superseded`.

The ledger stores the attempted action, verifier strategy, expected state, timing/deadline, evidence/error information, action event, and Executive decision correlation where present.

Verification observations are separately persisted.

---

## 67. Read vs write semantics

### Read operations

A read whose returned observation is itself the requested result can close immediately.

### Write/action operations

An external/local write does not become verified from a `200 OK`/success message alone when an independent read-back verifier exists.

### No observer

If Jarvis lacks an independent way to observe the effect, it records `unverified` instead of making up success.

---

## 68. Independent verifier coverage in source

Closed-loop verification includes strategies for observable effects such as:

- Gmail send -> causal Sent Mail read-back;
- Calendar creation -> event read-back;
- application launch/close -> process/app state;
- browser tab open/focus/close -> browser state;
- Minecraft process state;
- persistent state writes;
- temporary state writes;
- scheduled job create/cancel;
- background-task terminal state.

Unobservable custom/security effects remain explicitly unverified unless a separate observer exists.

---

## 69. Gmail causal boundary

Sent-Mail verification does not merely search for any old matching recipient/subject.

The expected state includes an action-time causal boundary so an earlier message cannot satisfy a new send.

---

## 70. Timeout behavior

When a pending verification reaches its deadline, Jarvis performs one final independent observation before declaring timeout.

This avoids the race:

```text
outcome appears at deadline
-> scheduler checks timeout first
-> false timeout
```

If the final observation finds the expected state, the action can still become verified.

---

## 71. Explicit status question behavior

Questions such as:

```text
Did that work?
```

force a fresh verification pass rather than simply reading a stale `pending` record.

---

## 72. Verification feeds back into Executive state

A pending action can move an objective to:

```text
awaiting_verification
```

A failed, timed-out, or intrinsically unverified outcome becomes higher-priority Executive attention.

Jarvis is therefore prevented from marching to the next step merely because a tool function returned normally.

---

## 73. Verification proactivity

The proactive loop periodically checks due verifications.

Routine successful verification is quiet. Failed or timed-out outcomes can produce a warning so an important objective does not disappear behind an unnoticed action failure.

---

## 74. Action audit wrapper

Tool execution receipts are mirrored into the world model with sensitive arguments redacted where appropriate.

During Criterion 7 a real integration blocker was found: the audit wrapper existed but was not guaranteed to be installed early enough to observe ordinary backend executions.

The source now installs it before runtime background/scheduler threads begin, with a retry path, so the verifier pipeline actually receives real tool attempts.

A missing audit/verification wrapper is treated as a core runtime-contract failure rather than silently ignored.

---

# PART XV — TOOLS, PC CONTROL, AUTOMATION, AND WORKFLOWS

## 75. Windows application/context tools

The backend contains bounded Windows control and status capabilities such as:

- list/check running applications;
- launch application;
- close application;
- open URL/path;
- current foreground process/window context;
- Minecraft status/launch/ensure-running;
- system resource status.

Foreground-window context is not represented as full access to an open document’s contents. A dedicated editor/content bridge would be required for that claim.

---

## 76. Browser/Opera/Chromium tools

The tool surface supports operations such as:

- browser status;
- list tabs;
- tab status;
- focus tab;
- open site;
- close tab.

Closed-loop verification can independently observe several browser-state changes.

---

## 77. Google tools

Supported classes include:

- Google connection status;
- Contacts resolution;
- Gmail query;
- Gmail send;
- Calendar list/query/recent/conflicts;
- Calendar create.

Read and write permission classes remain distinct.

---

## 78. Email recipient safety

Outbound Gmail has an additional exact-recipient allowlist enforced by the backend after contact-name resolution and immediately before send.

An empty allowlist blocks all outbound email.

This exists **in addition to** the general external-write confirmation class.

---

## 79. Web search

The backend supports Serper web search with:

- locally configured API key;
- dynamic query refinement;
- evidence collection;
- short voice-friendly synthesis rather than reading raw SERP URLs/snippets aloud.

Web search remains separate from private-world evidence.

---

## 80. Jobs and scheduling

Jarvis supports persistent scheduled work including:

- one-time time jobs;
- recurring jobs;
- event-triggered jobs;
- cancellation;
- scheduled briefings.

Job state is mirrored into the world model/backfill so automation history participates in the same persistent evidence system.

---

## 81. Background worker queue

Long-running work can be submitted to a persistent local background worker queue with status/result/failure state.

Background completion/failure is mirrored into the world model and can participate in closed-loop verification.

---

## 82. DAG workflow execution

The backend contains autonomous workflow execution using a DAG-like structure, including parallel read-only steps where safe.

Workflow execution remains subject to the same permission boundary for consequential actions.

---

## 83. Briefings

A briefing layer can synthesize relevant local/task/calendar/world information into a concise response. The newer situation/Executive architecture supplies much stronger grounding for queries where a specific imminent context exists.

---

# PART XVI — MEETINGS, FACT CHECKS, JOURNALS, AND EXPENSES

## 84. Explicit Meeting Notes

Meeting capture is explicit and visibly active.

The iPhone meeting workflow supports source features such as:

- start/stop;
- elapsed timer;
- pause/resume;
- bookmarks;
- local transcript accumulation;
- periodic Apple Speech task rotation;
- local transcript snapshot in Application Support;
- Share Sheet transcript export;
- continued local capture when PC unavailable;
- later Sync & Extract;
- backend transcript ingestion;
- action-item extraction on finish.

The normal Jarvis wake loop is suspended during the explicit recording flow to avoid competing microphone consumers.

### 84.1 Meeting privacy boundaries

The system does not:

- identify speakers using voiceprints;
- infer deception;
- infer stress/tension/emotion/mental state from voice.

Recording must be used with appropriate legal/participant notice and consent.

---

## 85. Local metric contradiction checks

During an explicitly active meeting-note session, concrete numeric/metric claims can be checked against local indexed evidence.

Jarvis reports only a **possible contradiction** when evidence directly conflicts; it does not promote the local index to infallible truth.

The newer Project term ledger generalizes the same conservative principle across conversation, documents, and other project evidence.

---

## 86. Expense/receipt capture

Jarvis can extract structured receipt/invoice information into local records.

The existing storage includes:

```text
%APPDATA%\JarvisForMRB\expenses.sqlite3
%APPDATA%\JarvisForMRB\expenses.csv
```

The vision/extraction layer is instructed not to guess unreadable merchant, date, total, tax, tip, or line-item fields.

Expense events can be mirrored into the world model.

---

## 87. Daily local journal

Jarvis can generate local Markdown daily journals on demand or through the optional automatic mechanism.

Storage is under:

```text
%APPDATA%\JarvisForMRB\journal\YYYY-MM-DD.md
```

The journal can summarize available local activity such as conversations, completed background work, communications, and spatial sightings without inventing emotions or motives.

Generated journals are backfilled/indexed into the unified world/knowledge layer.

---

# PART XVII — CALENDAR ASSISTANCE AND PROACTIVITY

## 88. Calendar conflict detection

Jarvis can detect overlapping timed Calendar events and propose alternatives.

It does not automatically move, decline, or rewrite a meeting unless the normal external-write path is explicitly authorized.

---

## 89. Proactive monitor

The backend proactive subsystem can perform bounded checks including:

- near-term Calendar reminders;
- contextual meeting prebriefs;
- unread urgent/action-required/deadline mail checks;
- action-verification due checks;
- supporting subsystem startup/health monitoring.

### 89.1 Deduplication

Alerts use keyed time windows so the same condition is not repeatedly spoken every monitor cycle.

### 89.2 Prefetch/prewarm

Shortly before relevant events, Jarvis can prewarm the fast model and local private knowledge context.

It deliberately does not require sending private calendar titles to arbitrary external services for automatic prefetch.

---

## 90. Resource monitoring

The backend monitors local PC guardrails such as:

- CPU utilization;
- system RAM;
- NVIDIA GPU utilization;
- VRAM usage;
- NVIDIA GPU temperature;
- background worker backlog.

High-confidence threshold breaches can generate proactive warnings.

---

# PART XVIII — SANDBOX, CUSTOM TOOLS, AND SECURITY

## 91. No unrestricted Windows host shell

The LLM does not receive a general host terminal.

This is a core architectural invariant.

---

## 92. Isolated Docker Python/command sandbox

Generated Python/terminal work can run in a disposable container configured with restrictions documented by the project such as:

- network disabled;
- read-only filesystem;
- Linux capabilities dropped;
- `no-new-privileges`;
- approximately 256 MiB memory bound;
- one CPU;
- process limit;
- hard timeout.

Sandbox Python/command execution is classified as a `security` action.

For an exact terminal command, the security confirmation flow deliberately speaks the **entire command** before approval so the user can hear what will execute.

---

## 93. Sandboxed custom API adapters

Jarvis can synthesize custom API tool adapters under a constrained model:

- sandbox generation/validation;
- HTTPS host allowlist;
- explicit risk classification;
- no arbitrary host-shell bridge.

### 93.1 Repair proposals

Structurally broken custom adapters can generate repair proposals after sandbox validation.

A proposal is accepted for review only after checks such as:

- sandbox execution succeeds;
- request plan is structurally valid;
- original HTTPS host remains allowed;
- original risk class is preserved;
- no embedded authorization/cookie/API-key header appears.

Jarvis never silently applies the repair. Applying it is a `security` action requiring confirmation.

---

# PART XIX — PERMISSION AND AUTHORITY MODEL

## 94. Default permission classes

Current source defines:

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

Individual tools map to one of those classes.

Examples:

- `knowledge.search` -> read;
- `gmail.query` -> read;
- app launch/tab focus -> local write;
- `gmail.send` / `calendar.create` -> external write;
- job/background cancellation -> destructive;
- sandbox/custom dynamic operations -> security.

A model-generated plan cannot elevate its own risk class or bypass confirmation.

---

## 95. Audit/provenance of actions

Backend tool executions are mirrored into world events with:

- tool identity;
- bounded/redacted arguments;
- success/failure receipt;
- action timing/provenance.

Sensitive fields such as raw security-class command content can be redacted from the world-model action log while non-sensitive control information remains auditable.

---

# PART XX — OPERATIONAL RELIABILITY (CRITERION 11)

## 96. Why reliability became a separate criterion

Once Jarvis started deriving durable identity, obligations, terms, and action outcomes, a “best effort” database was no longer sufficient. A bad partial snapshot, reversed chronology, or silently missing verifier could change what Jarvis believes the user should do.

Criterion 11 therefore converted reliability from incidental defensive code into an explicit architecture.

---

## 97. Versioned world schema

`world_migrations.py` is the single migration authority.

Current target:

```text
world schema version 4
```

Migration stages cover the progression from:

1. core world entities/events/beliefs/commitments;
2. evidence relations and intentions;
3. chronology-safe term/document lineage;
4. Executive Loop, closed-loop verification, runtime health.

The version advances only after a migration step returns successfully.

A database with a future unsupported version is refused.

---

## 98. Pre-upgrade backups

Before upgrading an existing user world, migration uses SQLite’s backup mechanism to create a bounded pre-upgrade copy under:

```text
%APPDATA%\JarvisForMRB\backups
```

Current retention is the three most recent pre-upgrade world backups.

---

## 99. WAL and contention handling

The migration path enables SQLite WAL mode for the shared world database and applies busy-timeout behavior to reduce unnecessary reader/writer contention among background subsystems.

---

## 100. Fail-fast schema validation

A database cannot bypass migration merely by containing `schema_version=4`.

Startup/diagnostics validate structural reality including:

- required tables;
- contiguous migration history;
- SQLite integrity;
- foreign keys.

A materially corrupted/incomplete declared schema is treated as a startup problem rather than silently reconstructed piecemeal while Jarvis continues operating on uncertain state.

---

## 101. Runtime subsystem health and failure isolation

Noncritical providers track persistent health information separately.

Examples include Calendar monitoring, urgent-mail monitoring, action verification, prefetch, PC context, resource monitor, audio damping, and journal startup.

One failing optional/provider subsystem should not suppress the others.

Core contracts are different: failure of world migration or the action-audit/verification installation is intentionally not treated as ignorable because operating without them would invalidate the state/action guarantees.

---

## 102. Comprehensive diagnostics

`jarvis-world-check` runs hard structural checks and exits non-zero when core invariants fail.

Current diagnostic coverage includes:

- supported schema version;
- required tables;
- migration history;
- SQLite integrity;
- foreign-key violations;
- WAL expectation;
- linker lag;
- goal/intention status mismatch;
- stale intention/commitment links;
- current derived relations with no evidence;
- `evidence_count` mismatch;
- weak person→project associations lacking structured evidence;
- prohibited raw iPhone payload indicators;
- revoked Known People identities still bound to enrollment IDs;
- revoked Known People alias leaks;
- current relations to tombstoned Known People entities;
- multiple current Executive decisions for one intention;
- same-value “term conflicts” that should not be conflicts;
- term conflicts without provenance events;
- chronologically reversed term conflicts;
- document version pairs without valid comparison event;
- chronologically reversed document pairs;
- invalid verification states;
- verified outcomes lacking `verification.verified` evidence;
- pending verifications past deadline;
- explicitly unverified outcomes;
- degraded runtime subsystems;
- world-database growth warning.

Disputed beliefs are allowed but deliberately visible as warnings rather than silently erased.

---

## 103. Source-time chronology hardening

Several derivations originally used database insertion ID as a proxy for real-world time. Criterion 11 removed that assumption.

### Project terms

Latest term observation is determined from parsed source `occurred_at`, with source event/row ID only as deterministic tie-breakers.

### RFC email dates

Term, situation, document, and Executive chronology can parse RFC-style email Date headers in addition to ISO timestamps.

### Executive recent change ordering

Recent material changes are ranked by actual occurrence time, not merely newest database row.

### Document versions

Version predecessor/successor direction is based on source time.

### Repairs

Migration routines can repair legacy reversed conflict/version derived state while retaining historical evidence events.

### Windows-safe floor

The final known Criterion-11 defect was eliminated by removing a `datetime.min.astimezone()` sorting fallback and replacing it with an explicit timezone-aware 1970 epoch floor. This avoids platform-dependent pre-epoch conversion behavior on Windows and keeps malformed timestamps “unknown” instead of pretending they have a real time.

---

## 104. Deterministic deployment preparation

`jarvis-world-prepare` provides one ordered deployment-preparation path:

1. schema migration;
2. pre-upgrade backup;
3. core historical backfill;
4. extended historical backfill;
5. drain relation linker;
6. drain term reconciliation;
7. drain document-version analysis;
8. link generated conflict/diff events;
9. refresh intentions;
10. refresh Executive state;
11. run diagnostics.

An important hardening change made the preparation loop **drain** incremental processors rather than running each only once and potentially leaving a large historical replay half-indexed.

---

## 105. Rollback contract

The operations document defines rollback without hand-editing SQLite rows:

- stop service;
- preserve failed DB for diagnosis;
- restore latest appropriate pre-upgrade backup;
- restore prior source revision if necessary;
- reinstall that source version;
- run diagnostics before restart.

---

# PART XXI — FIXED END-TO-END ACCEPTANCE (CRITERION 12)

## 106. Non-moving finish line

`FIXED_ENDPOINT_ACCEPTANCE.md` records the exact twelve project criteria. This was added specifically because the user did not want completion to recede every time another possible feature was imagined.

The finish line is now contractual:

1. persistent world model;
2. identity continuity;
3. persistent intentions;
4. situational awareness;
5. cross-source reasoning;
6. Executive Loop;
7. closed-loop verification;
8. appropriate proactivity;
9. privacy/authority boundaries;
10. unified interaction;
11. operational reliability;
12. end-to-end demonstrations.

After runtime verification satisfies that list, additional features are enhancements, not a thirteenth completion criterion.

---

## 107. Isolated acceptance harness

`world_acceptance.py` implements a synthetic integration scenario in a temporary world database.

Properties:

- does not use the user’s deployed world database;
- does not contact external services;
- does not mutate real Gmail/Calendar state;
- redirects world-model module DB paths to a temporary directory;
- suppresses live Calendar refresh in the synthetic situation test;
- restores patched module state after completion;
- maps every assertion to one of the twelve fixed criteria.

The command is:

```text
jarvis-world-acceptance
```

It emits JSON and exits non-zero when a required fixed-endpoint check fails.

`tests/test_world_acceptance.py` runs the same command in a fresh Python interpreter with an isolated `APPDATA` directory so module-level path/config state from other tests cannot contaminate the acceptance run.

---

## 108. Canonical Project Apollo acceptance story

The synthetic scenario deliberately exercises the whole architecture instead of manually writing the “final answer” into a table.

### Step 1 — iPhone current state

The synthetic iPhone world contains:

- enrolled Known Person: Daniel Reed;
- Waiting-On item: Daniel owes revised Project Apollo disclosure schedules;
- the dependency is overdue;
- mode is Work.

### Step 2 — identity continuity

`daniel@example.com` is introduced as an independent email identity and must bridge to the same Daniel person rather than creating a parallel duplicate.

### Step 3 — persistent intention

The user says:

```text
We're trying to get Project Apollo signed by Friday.
```

The conversational intention capture creates a durable goal/intention and links it to Project Apollo.

### Step 4 — conversational deal evidence

A provenance event records:

```text
Project Apollo indemnity cap is 10%.
```

### Step 5 — old document

A Project Apollo Purchase Agreement draft contains an indemnity cap of 10%.

### Step 6 — revised document

A later revision in the same source lineage contains 15%.

### Step 7 — document lineage

The comparator must recognize the documents as likely versions and emit a numeric/date change event with 10% -> 15%.

### Step 8 — Project term ledger

The term ledger must retain both explicit values with provenance and treat 15% as chronologically latest while retaining the discrepancy.

### Step 9 — imminent meeting

Calendar contains a Project Apollo signing call in approximately 30 minutes with Daniel as attendee.

### Step 10 — situation compilation

“Anything I need to know before I go in?” must connect:

- the actual meeting;
- Daniel;
- Project Apollo;
- active signing objective;
- overdue schedules;
- recent connected evidence.

### Step 11 — Executive state

The objective must become `at_risk`, with both:

- term conflict;
- overdue commitment.

The term discrepancy should outrank the ordinary dependency and produce a safe read-only evidence-gathering proposal through the normal permission gate.

### Step 12 — proactive prebrief

The prebrief must surface actionable connected facts rather than a generic countdown, including the term discrepancy and Daniel’s outstanding schedules.

### Step 13 — action attempt

A synthetic external follow-up email is registered. The provider return is only an action receipt.

### Step 14 — pending verification

The verification ledger must remain `pending`; the system may not call the email “done” from the send return alone.

### Step 15 — independent observation

The acceptance harness substitutes a deterministic independent Sent-Mail observation and requires the action to transition to `verified` only then.

### Step 16 — Known People privacy semantics

Daniel is removed from the authoritative Known People list.

The acceptance check requires:

- iPhone face identity removed;
- private enrollment note removed;
- independent email identity preserved.

### Step 17 — negative graph control

A separate sentence:

```text
Alex Example is not on Project Apollo.
```

must **not** create an Alex→Apollo current project association.

### Step 18 — partial snapshot control

Malformed/missing authoritative collection fields must retire/revoke nothing.

### Step 19 — relevance control

An unrelated dinner question must not receive Apollo Executive context.

### Step 20 — diagnostics

The synthetic prepared world is quiesced/refreshed and must satisfy the same structural diagnostics expected of the deployed world.

### Step 21 — full causal-chain assertion

The final Criterion-12 assertion requires the existence of the complete chain:

```text
intention
 -> project identity
 -> cross-source evidence
 -> document change
 -> term conflict
 -> situation
 -> Executive decision
 -> proactive context
 -> action attempt
 -> independent observed outcome
```

---

# PART XXII — DATA STORES AND RETENTION BOUNDARIES

## 109. Principal backend storage

Current/legacy Jarvis stores include locations such as:

```text
%APPDATA%\JarvisForMRB\world_model.sqlite3
%APPDATA%\JarvisForMRB\conversation.sqlite3
%APPDATA%\JarvisForMRB\episodic_memory.sqlite3
%APPDATA%\JarvisForMRB\spatial_memory.sqlite3
%APPDATA%\JarvisForMRB\meeting_notes.sqlite3
%APPDATA%\JarvisForMRB\knowledge_sources.sqlite3
%APPDATA%\JarvisForMRB\expenses.sqlite3
%APPDATA%\JarvisForMRB\expenses.csv
%APPDATA%\JarvisForMRB\jobs.sqlite3
%APPDATA%\JarvisForMRB\background_tasks.sqlite3
%APPDATA%\JarvisForMRB\environment_state.json
%APPDATA%\JarvisForMRB\ephemeral_state.json
%APPDATA%\JarvisForMRB\notes\
%APPDATA%\JarvisForMRB\journal\
%APPDATA%\JarvisForMRB\backups\
```

Exact legacy store existence depends on which older features have been used on the deployed machine.

### 109.1 World DB growth

Diagnostics warns if the world DB becomes unusually large. Extracted private document text is bounded, but longer-term storage/retention should be re-evaluated if real-world attachment volume makes database growth material.

---

## 110. iPhone protected local storage

Depending on the feature, iPhone state uses normal app storage, complete-file-protected files, and Keychain-protected encryption keys.

Sensitive examples include:

- Known People feature prints/profile data;
- encrypted Context Capsules;
- encrypted capability execution receipts;
- bounded local transcripts/encounter context according to their feature settings.

The world snapshot is intentionally a reduced metadata projection, not a copy of every local sensitive store.

---

# PART XXIII — DELIBERATE NON-FEATURES AND CLAIM BOUNDARIES

## 111. No public/unrestricted face recognition

Known People recognizes only explicitly enrolled private profiles. It is not a stranger-identification system.

---

## 112. No speaker voiceprint identity

Meeting/audio features do not build a biometric voiceprint database to identify speakers.

---

## 113. No emotion/deception/stress inference from other people’s voices

Jarvis does not label another person as angry, deceptive, stressed, tense, etc. based on acoustic inference.

---

## 114. No arbitrary iOS notification interception

A normal companion app cannot read every other application’s notifications. Jarvis does not pretend otherwise.

---

## 115. No invisible meeting recording

Meeting transcription is explicit and visibly active.

---

## 116. No safety-critical camera-only indoor homing

Last-seen/context memory is available, but it is not presented as dependable safety-critical indoor navigation.

---

## 117. No unrestricted host terminal

Only the constrained sandbox/custom-tool model is exposed to the planner.

---

## 118. No automatic replay of delayed consequential commands

Offline queued commands require explicit resend.

---

## 119. No automatic authoritative resolution of project-term conflicts

A newer document saying 15% and an earlier discussion saying 10% produces a visible discrepancy. Jarvis does not silently decide which legal/economic term controls.

---

## 120. No automatic global person erasure from face unenrollment

Known People deletion means local enrollment revocation. Global historical erasure would be a separate destructive operation.

---

## 121. No Dynamic Island/Lock Screen/Control Center extension claim

Those extension targets are not part of the current source-complete endpoint. Existing App Intents/Shortcuts provide supported OS-level entry points without pretending the additional extension lifecycle exists.

---

## 122. No automatic full IDE/file-content inference from foreground-window title

PC context can tell Jarvis what application/window is foreground. It cannot claim the entire document/code contents unless a dedicated content integration actually supplies them.

---

# PART XXIV — HOW THE SYSTEM GOT HERE: DETAILED BUILD HISTORY

## 123. Phase A — local-first wearable assistant foundation

The earliest architecture established the core physical topology:

- Ray-Ban Meta as wearable microphone/speaker/camera;
- native SwiftUI iPhone companion;
- authenticated Windows backend;
- local Ollama planning models;
- private local TTS;
- PC tools rather than unrestricted shell;
- persistent conversation;
- Google private-data connectors;
- private Tailscale remote access.

The important architectural choice was made early: the iPhone and glasses were not given broad cloud-agent authority. The PC remained the main reasoning/tool host while the phone handled local UX, sensors, and privacy controls.

---

## 124. Phase B — low-latency conversation

Subsequent work made the system usable as an actual wearable conversation rather than a slow command console:

- streaming backend text;
- incremental speech playback;
- follow-up window;
- barge-in;
- HFP route preference;
- dictation-aware recognition timing;
- local audio cues;
- adaptive/forced whisper;
- planner model routing;
- TTS fallback behavior.

---

## 125. Phase C — perception and contextual presence

Milestone-13-era work added:

- DAT live camera;
- passive backend vision;
- recent RAM-only visual history;
- OCR/recent-visible-text operations;
- conservative hazard/error alerts;
- spatial last-seen memory;
- PC foreground context;
- resource guardrails;
- meeting capture;
- expenses;
- journals;
- proactive Calendar/email monitoring;
- prefetch/prewarming;
- web search;
- jobs/workflows/background execution;
- sandbox/custom tools.

This greatly expanded what Jarvis could sense/do, but those features still largely existed as parallel domains.

---

## 126. Phase D — iPhone frontend-only expansion while backend deployment was unavailable

While the user was away from the home PC, work focused on capabilities that could be added in the iPhone source without pretending the backend had changed.

This phase introduced or hardened:

- local 30-second DAT cache;
- Apple Vision OCR/QR/structural perception;
- Known People closed-set private recognition;
- private inventory matching;
- local encounter context;
- rolling speech/audio context;
- Sound Analysis;
- local Translation;
- offline command staging;
- connection diagnostics;
- session/latency telemetry;
- local voice aliases;
- meeting pause/bookmarks/export/offline capture;
- optional motion context;
- App Intents/Shortcuts/Action Button;
- deterministic local utilities;
- native Calendar/Reminders/Contacts/timers;
- Apple Foundation Models stable-question route;
- encrypted Context Capsules;
- unified Local Memory;
- searchable Feature Guide with test prompts.

The source documentation explicitly preserved the boundary that the separate backend conversational “what can you see right now?” fix was **not deployed** merely because frontend work existed.

---

## 127. Phase E — frontend capability-pack architecture

As local features multiplied, the repeated wrapper-chain approach became difficult to reason about.

The frontend was reorganized around explicit capability packs with:

- intent claiming;
- priorities;
- requirements;
- effect classes;
- lazy activation;
- compatibility adapter;
- camera privacy gate;
- read-only composition;
- deterministic quality shield;
- encrypted execution receipts;
- dry-run canonical routing tests.

This was an important precursor to the backend world work because it established the same general philosophy: **small explicit subsystems with auditable authority instead of one giant model deciding everything.**

---

## 128. Phase F — persistent world model unification

The major backend architecture effort then began: turn separate memory/capabilities into one persistent model of the world Jarvis believes it is helping operate.

The first world-model work added:

- stable entities;
- external IDs;
- aliases;
- events;
- event/entity participation;
- beliefs with contradiction/revision semantics;
- commitments;
- provenance and confidence;
- environment/conversation/vision/knowledge/meeting/action ingestion.

Major source commits from this stage include work represented by commits such as:

- `604ebae3` — persistent world model/provenance graph;
- `8cfe7144` — iPhone local context ingestion;
- `24e6b110` — connect iPhone local context to backend world model;
- `f2720354` — bounded iPhone world-state publication;
- `109b0de1` — semantic world-snapshot deduplication;
- `a7f04ffd` — mirror additional backend domains;
- `eb3e7f` — unified indexed private knowledge;
- `7db295f` — safe world-model backfill;
- `a9f5e38` — move migration off the voice-critical path;
- `edc15aa` — memory-recall repair;
- `774b8563...` — identity-resolution/global-overview hardening.

The exact short SHA list above is included as a navigation aid, not as a substitute for Git history.

---

## 129. Phase G — evidence relationships and identity/privacy contracts

The next stage added an evidence-backed relation graph and addressed identity correctness.

Work included:

- project/person/document/calendar/meeting relations;
- current relation evidence counts;
- explicit Project entity creation from literal `Project Name` identifiers;
- identity conflict protection;
- Known People unenrollment semantics;
- tombstoning no-independent-identity enrollments;
- preservation of independent Gmail/Calendar identities.

A particularly important later reliability correction restricted person→project association to structured participant evidence, eliminating generic co-occurrence false positives.

---

## 130. Phase H — persistent intentions and selective relevance

The system gained:

- materialized explicit intentions;
- goal→Project links;
- Waiting-On→intention dependencies;
- conversational intention capture;
- conservative deadline parsing;
- query-aware intention selection.

This fixed “goal contamination,” where unrelated active objectives could otherwise be inserted into every turn.

---

## 131. Phase I — situational awareness

Calendar enrichment and the situation compiler converted the graph from static memory into current-context reasoning.

The system could now answer the structural question:

```text
Who am I about to see, what project connects us, what do they owe, what objective is active, and what changed recently?
```

The contextual prebrief then moved this from reactive Q&A into bounded deterministic proactivity.

---

## 132. Phase J — documents and cross-source deal terms

The knowledge layer was expanded to inspect safe attachment text.

Then:

- document-family lineage was added;
- numeric/date changes were extracted;
- supersession relationships were added;
- Project term extraction was added;
- cross-source term conflicts were represented with both values/provenance;
- direct Project-term queries were routed to structured state.

This created the first complete architecture for the canonical 10%-versus-15% Apollo benchmark.

Representative commits from this period include:

- `6e56f6ba` — Gmail attachment ingestion;
- `f6a69064` — `pypdf` dependency;
- `312eae1f` — attachment sync into knowledge refresh;
- `2067b77c` — document version module;
- `510c3164` — hardened lineage/supersession;
- `716ed6e4` — cross-source term ledger;
- `28f775c7` — conversational term observation;
- `1ce3035a` — knowledge refresh term reconciliation;
- `2fe8de0d` — term-ledger tests;
- `c8e75df7` — query-aware Project-term retrieval context.

---

## 133. Criterion 6 — Executive Loop

The first of the final four bounded work passes converted world knowledge into persistent operational judgment.

Implemented:

- persistent attention table;
- one current decision per intention;
- objective state compiler;
- blockers/dependencies/deadlines/recent changes;
- deterministic priority;
- next actions;
- permission-aware executable proposal;
- exact tool/args correlation;
- direct term retrieval integration;
- post-ingestion Executive refresh;
- streaming voice context preservation;
- dedicated regression coverage.

Criterion-6 source endpoint was recorded around commit:

- `d8164b3704a17fe8579985d5e88faf3d4cd88073` — protect Executive context on the streaming voice path.

---

## 134. Criterion 7 — closed-loop verification

The second final pass changed the definition of action completion.

Implemented:

- persistent verification ledger;
- read-vs-write outcome semantics;
- independent verifier registry;
- Gmail causal Sent-Mail verification;
- Calendar/app/browser/process/state/job/background observers;
- explicit unverified state;
- final-before-timeout observation;
- status-query refresh;
- Executive feedback;
- proactive failure warnings;
- exact confirmation correlation;
- action-audit startup installation;
- diagnostics/regression tests.

Criterion-7 source endpoint was recorded around:

- `2d9cb34580788c735deb627a8e1d914dd66e99e9` — install action verification audit before runtime threads.

---

## 135. Criterion 11 — operational reliability

The third final pass treated derived personal-world state as production data rather than a toy cache.

Implemented/fixed:

### Snapshot safety

- missing/malformed authoritative arrays no longer mean empty;
- destructive reconciliation only follows explicit lists.

### Graph safety

- person→project association requires strong roles;
- migration repair retires legacy weak current links while retaining evidence.

### Versioned migration

- target schema v4;
- migration metadata/history;
- pre-upgrade backup;
- WAL;
- future-schema refusal;
- startup structural validation.

### Failure isolation

- persistent subsystem health;
- optional providers isolated;
- core migration/audit failures fail safe.

### Diagnostics

- broad schema/graph/privacy/Executive/verification/runtime integrity checks.

### Chronology

- Project term chronology uses source occurrence time;
- RFC email dates supported;
- direct term context uses actual chronology;
- Executive recent changes use actual chronology;
- document lineage uses actual chronology;
- reversed legacy terms/doc relationships repairable.

### Deployment preparation

- `jarvis-world-migrate`;
- `jarvis-world-prepare`;
- queue draining;
- rollback runbook.

### Regression coverage

Dedicated reliability, chronology, corruption, partial-snapshot, relation, migration, and timestamp tests were added.

The final explicitly known reliability defect was fixed in:

- `40843de0b936e097b8c9618e20167915f4bf1ea8` — Executive RFC/platform-safe chronology parsing;
- `6ca0777ae9bee6a0abe0da33b91de2dea1cad215` — regression coverage for that timestamp portability case.

Criterion 11 is now **source-complete**.

---

## 136. Criterion 12 — fixed endpoint acceptance

The fourth/final source pass turned the abstract completion list into executable acceptance.

Implemented:

- `world_acceptance.py` isolated synthetic Apollo scenario;
- per-check mapping to criteria 1–12;
- no real user-data mutation;
- no external service dependency;
- cross-source identity/intention/doc/term/situation/Executive/action/verification flow;
- privacy and negative graph controls;
- `jarvis-world-acceptance` CLI;
- subprocess regression wrapper with isolated `APPDATA`;
- `FIXED_ENDPOINT_ACCEPTANCE.md` non-moving completion contract.

Representative commits:

- `a6b395dff7cb7cd685bafe5a18d3dd9a9be91d06` — fixed end-to-end acceptance harness;
- `a5bfebbb20d9561a6d30b33f34ffb660d8963d9d` — acceptance CLI;
- `3ace778e7eeafd7ceae209bf52806ba6aea126fe` — expose acceptance command;
- `348bcff733f6cda80abe3229f5f0fb23b074584a` — regression wrapper;
- `d02dc40c917e609b1a2fafe20e525c98a109df18` — fixed completion contract.

Criterion 12 is now **source-complete**.

---

# PART XXV — TESTS NOW PRESENT IN SOURCE

## 137. World-model and integration regression suites

The repository now includes tests covering areas such as:

- explicit Project creation and relation evidence;
- goal→intention creation/retirement;
- Waiting-On retirement;
- distinct repeated occurrences;
- disputed lower-confidence belief contradictions;
- action receipt sensitive-argument redaction;
- unrelated-intention filtering;
- Known People revocation with/without independent identity;
- situation compiler selection;
- conversational intention capture;
- document numeric-change detection;
- document lineage rejection/equivalence;
- term conflict/no-conflict/no-project behavior;
- direct term context;
- Executive Loop priorities and query projection;
- streaming Executive-context preservation;
- closed-loop verification transitions;
- action failure/timeout/unverifiable semantics;
- exact Executive action correlation;
- partial-snapshot safety;
- strong-vs-weak person/project relation semantics;
- migration/backups/future-schema refusal;
- subsystem failure/recovery state;
- chronology under out-of-order historical ingestion;
- structural corruption detection;
- RFC timestamp portability;
- full isolated Project Apollo acceptance.

Important: **the newest complete suite has not yet been executed in this development conversation.** Passing status must be established on the home PC after pull/install.

---

# PART XXVI — CURRENT FIXED COMPLETION SCOREBOARD

## 138. Source status

| Criterion | Fixed requirement | Source status |
|---|---|---|
| 1 | Persistent world model | Implemented |
| 2 | Identity continuity | Implemented |
| 3 | Persistent intentions | Implemented |
| 4 | Situational awareness | Implemented |
| 5 | Cross-source reasoning | Implemented |
| 6 | Executive Loop | **Source complete** |
| 7 | Closed-loop verification | **Source complete** |
| 8 | Appropriate proactivity | Implemented |
| 9 | Privacy/authority boundaries | Implemented |
| 10 | Unified interaction/state | Implemented in architecture/source |
| 11 | Operational reliability | **Source complete** |
| 12 | End-to-end acceptance | **Source complete** |

Therefore the fixed architecture is **source complete**.

This is not yet equivalent to “deployed system complete.”

---

## 139. Runtime verification still required

When the user is back at the home PC, the intended sequence is:

```powershell
git pull
py -3.14 -m pip install -e .
jarvis-world-prepare
py -3.14 -m unittest discover -s tests -v
jarvis-world-acceptance
jarvis-world-check
```

Then:

1. restart the Jarvis backend from the same source revision;
2. verify `/health`;
3. verify model/TTS runtime, including that Kokoro rather than an old Qwen3-TTS service is serving the expected voice path;
4. verify Gmail/Calendar authentication and read paths;
5. verify the action audit is installed;
6. exercise at least one read verification;
7. exercise at least one independently observable write verification;
8. verify a noncritical provider failure does not stop other proactive checks;
9. build the matching iOS revision in Xcode;
10. install/run on the target iPhone;
11. verify authenticated transport/reconnect/failover;
12. verify world-snapshot semantic dedupe;
13. verify an explicit empty authoritative list reconciles correctly;
14. verify a deliberately missing/malformed authoritative field does not retire state;
15. inspect/verify that excluded raw biometric/camera/audio/clipboard/privacy-zone material does not cross the world-snapshot boundary;
16. verify representative local capability packs and their quality shield;
17. verify Ray-Ban DAT camera and HFP voice path;
18. verify the pending general live-scene conversational backend fix rather than assuming its source commit equals a working deployment;
19. run representative real-world acceptance prompts, including the meeting/prebrief and closed-loop action paths.

Only after those checks actually pass should the project be called **runtime-verified complete**.

---

# PART XXVII — WHAT “DONE” MEANS AFTER TESTING

## 140. The finish line does not move

The purpose of `FIXED_ENDPOINT_ACCEPTANCE.md` and the isolated acceptance harness is to stop this project from becoming an endless sequence of “one more thing.”

Once:

- the twelve fixed criteria are implemented;
- regression tests pass;
- isolated acceptance passes;
- diagnostics pass;
- deployed backend behavior passes on the home PC;
- the matching iPhone build passes on-device;
- the fixed real end-to-end demonstrations behave correctly;

then **the defined Jarvis project is complete**.

Future work might still improve Jarvis—newer models, better vision, more apps, additional wearables, HomeKit, MusicKit, Maps, an IDE bridge, widgets, different hardware, more term extractors, richer UI—but those are post-completion enhancements.

They are not a new Criterion 13.

---

# PART XXVIII — CONCISE END-STATE DESCRIPTION

## 141. What Jarvis is now designed to do

At the fixed source endpoint, Jarvis is designed to maintain a private, provenance-bearing model of:

- who and what exists in the user’s operational world;
- which source identities refer to the same entity;
- what happened and when;
- what Jarvis currently believes, with confidence and contradictions;
- what people owe / what the user is waiting on;
- what explicit goals the user is pursuing;
- which projects, people, documents, meetings, and obligations connect to those goals;
- what changed across source documents;
- what explicit project terms differ across conversations/documents;
- what imminent situation matters right now;
- what currently blocks an objective;
- what next action is justified by evidence;
- what tool could implement that action under the user’s permission policy;
- whether the action was merely attempted or independently observed to work;
- when a failed/unverified outcome should re-enter attention;
- what should be surfaced proactively before the user asks.

The central benchmark is no longer:

```text
Can Jarvis retrieve an email, open an app, analyze a frame, or remember a conversation?
```

It is:

```text
Can Jarvis understand the user is trying to get Project Apollo signed,
know Daniel is involved and owes revised schedules,
know an Apollo meeting is imminent,
notice that the newer draft says 15% while prior discussion said 10%,
bring those two facts up before the meeting,
recommend the right evidence-gathering/action step,
respect the write-confirmation boundary,
and later know from independent evidence whether the action actually worked?
```

That is the system the repository is now built to implement.

The remaining work is no longer another architectural feature pass. It is the agreed **deployment and test phase** that determines whether the source behaves on the real PC/iPhone exactly as the fixed acceptance contract requires.
