# Callless: product and systems design

**Status:** Proposed design, **not** an implemented-feature claim  
**Date:** 2026-10-19  
**Subsystem:** Mercury (communications); Cerberus (authorization); Mnemosyne (user-owned context)  
**Current baseline:** Horus 0.14, commit `58ba780`  
**Companion documents:** [Shipping / current prototype](SHIPPING.md) · [Scope and housekeeping](HORUS_HOUSEKEEPING.md)

> **North star: remote conversational proximity, not a telephone replacement.** Callless should feel like a permission-based, personal walkie-talkie: two people apart can speak as naturally as if they shared a room. "Horus, get me to Alex" means *start a live, nearly frictionless conversation* when Alex has knowingly authorized this kind of access. No dial/ring/answer ceremony when the recipient is Open and the device genuinely supports that interaction. An unmistakable connection cue, easy termination and instant revocation are mandatory. A request never grants permission to bypass OS restrictions, secretly activate a microphone, record, expose context, spend credits or open a door.

## Product invariant: what Callless actually is

The origin is the **James Bond / Q earpiece** interaction: touch or speak to an earpiece, say "Q, are you seeing this?", hear a subtle connection cue, and talk. The user should not need to navigate a call screen. **Callless is ambient, permission-based conversational access**; calling, messaging, voicemail and screening are supporting mechanisms, not the product.

- **Success metric:** time from deciding to speak to *confirmed live two-way audio* for an already-authorized recipient; target an experience approaching face-to-face conversation, measuring p50/p95 latency and failed attempts on real devices. Never count delivered signaling, a queued request or a played tone as connected audio.
- **First-class experience:** a trusted pair, both wearing headsets, can establish short conversations repeatedly without entering a persistent voice channel, opening a browser, redialing, waiting for a ring or staring at UI. "Open" is **advance, scoped permission to receive immediate speech**, not the same as being online or having an active microphone. "Ask" negotiates the interruption first. "Closed" blocks unsolicited speech.
- **Social safety:** the recipient knows who can reach them and on which devices, with clearly visible status, a distinct audio cue before remote audio, tactile/simple mute and end controls, block/revoke that takes effect, and no indefinitely live idle microphone. Explicitly authorized foreground/OS-compliant media sessions only; do not simulate invisible background answer on platforms that forbid it.
- **What is distinctive:** conversational spontaneity without obligatory shared voice channels or the ring/answer ritual; availability policies, calendar Free/Busy and AI screening exist to make that spontaneity socially acceptable. Never optimize those at the expense of fast, reliable, honest audio.
- **Architecture:** Callless is a transport-independent *permission and audio-presence coordination layer* within Horus, not necessarily its own social network. A Discord **user-installable app/adapter** is a plausible distribution and policy-validation experiment, using user/context commands and approved messaging surfaces. Discord app permissions **do not** confer native DM-call control, unattended microphone access or automatic joining; use supported handoff and/or a separately authorized client. Preserve an independently operating native path and non-user fallback.
- **Product validation:** test real pairs for time-to-audio, repeat daily use, friction versus native voice, unwanted interruption, accidental microphone activation, and reversible permissions before expanding recording, billing, agent calls or phone/SMS. Passing API tests alone does not validate this experience.

### Implementation priority, distinct from the feature inventory

**P0:** authorized near-immediate two-way audio, truthful connected/disconnected state and unmistakable connection/end cues, explicit easy Open/Ask/Closed/revocation, multi-device validation. **P1:** headset/AirPods and OS-compliant foreground/background experience, group/timed permissions, notification policies and meaningful offline fallback. **P2:** calendar-derived heads-up, hold, screening, guests and urgency. **Later:** recording, payments, agent-to-agent and conventional telephony. The detailed phases below are dependency/design inventory; they must not obscure the experience-first priority.

Current repository reality remains a foreground WebRTC browser prototype with explicit Join/microphone tap, no native incoming audio, no two-device acceptance and no measured near-instant handoff. **This product vision is not yet implemented or shipped.**

This is the consolidation of the Callless improvement list. The ordering below is a proposed implementation plan, not a claim that the items are already in the repository. **Do not turn a design checkbox into a shipped-capability claim.**

## 1. Current state and non-goals

Existing source:
- `jarvis_mrb/callless_core.py`: single-hub accounts, local SQLite password/token/invite hashes, symmetric contact approval, blocking, and `open | ask | closed`.
- `jarvis_mrb/callless_api.py`: single-process WebSocket presence, invitation endpoints, explicit accept/end and WebRTC SDP/ICE signaling.
- `jarvis_mrb/callless_ui.{html,js,css}`: foreground browser with user-click microphone activation.
- `ios/JarvisIOS/JarvisAppModel.swift`: "get me to X" opens the browser; no native incoming Callless call handler.
- `docs/SHIPPING.md`: limited prototype deployment, separate from a hosted service.

**Not yet implemented:** non-Horus fallback, one-way permissions, calendar policy, hold/voicemail/screener, urgency and bypass, recording consent, model-disclosure gates, native VoIP delivery, group calls, device handoff, voice whisper-in, agent-to-agent calling, physical access control, metered caller billing, or global federation.

**Preserve:** no idle phone microphone on the ordinary push-to-talk path; no media recording in the hub by default; exact, revocable authorization; clear "who/what/where" for model processing; existing Windows/iOS functionality; a private local-only mode that never requires joining Callless.

**Not goals for the first release:** guaranteed silent pickup under iOS background restrictions; making a Callless account the only way to speak to someone; turning Tailscale into a permanent required consumer dependency; a hidden universal social graph; unreviewed autonomous physical actions; anonymous unlimited interruption.

## 2. Personas and core interaction

1. **Known Horus friend:** "Get me to Alex" -> directed permission + current effective status -> connect, ask, hold, or route to screener.
2. **Busy recipient:** Calendar has a blocking event; Horus automatically applies an **effective Ask** rule (without overwriting the user's saved Open choice), and optionally offers a coarse "busy until approximately [time]" message.
3. **Unavailable or declined:** Caller may wait, leave a message, or ask Alex's limited screener; recipient can see what happened later.
4. **Non-Horus contact:** Horus can offer a conventional phone call or SMS through an explicitly configured integration, or a short-lived, identity-bound guest browser link when the recipient approves. Show the destination and any cost; never silently place a paid call or expose a private contact detail.
5. **Trusted bypass holder:** If the recipient has independently granted bypass, Horus announces that bypass is being used to *both* parties, records a reviewable event, and only attempts the OS-permitted connection.
6. **Urgent caller without bypass:** May request a separate, rate-limited urgent notification, but not unconditional live pickup or OS Focus/DND circumvention.
7. **Agent contact:** Horus agents exchange a bounded purpose-specific request, with their principals' consent and scoped context; either may escalate to a human.

User-facing outcomes must distinguish **live connected**, **ringing / awaiting OS acceptance**, **waiting**, **message offered**, **screener active**, **offline**, **declined**, and **failed to deliver**. Never say "connected" merely because signaling was sent.

## 3. Directed permissions, not compulsory mutual friendship

Pairing/discovery and calling authority are different concepts. Replace the symmetric `contacts.permitted` assumption with **directed grants**. A person may allow Alex to contact them even if they are not permitted to initiate a connection to Alex.

Suggested conceptual tables (names are provisional; require additive migration/backfill):

| Entity | Core fields | Authority |
|---|---|---|
| `principal` | user ID, verified identity handles, devices | principal owns account |
| `contact_request` | sender, recipient, state, expiry, anti-spam metadata | recipient decides |
| `reachability_grant` | `grantor` (recipient), `grantee` (caller), allowed modes, scope, expiry, revoked_at | grantor only |
| `availability_rule` | owner, default, calendar-overlay setting, contact group, local-time window, expiry, priority | owner only |
| `disclosure_grant` | owner, recipient, named busy-info fields, expiry | owner only |
| `session` | IDs, participants, media/approval state, timestamps, device endpoint, reason code | session policy |
| `interrupt_grant` | grantee, bypass type, hard limits, expiry, audit requirements | owner only |
| `urgent_budget` | sender, recipient, window, used, denied/reviewed | server-atomic |
| `screener_budget` | sender, owner, window, seconds, tokens, currency, request count | receiver policy |
| `consent` | session ID, participant, feature, content version, granted/revoked timestamps | participant only |
| `audit_event` | actor, subject, policy rule, before/after, time, immutable event ID | append-only, access controlled |
| `billing_authorization` | payer, product/recipient, cap, rate disclosure, provider token | payer only |

**Minimum directed modes:** `can_request`, `can_connect_when_open`, `can_leave_message`, `can_talk_to_screener`. **Privileged modes:** `can_bypass`, `can_request_urgent`, `can_see_busy_until`, `can_receive_agent_handoff`. Privileged modes are never implicitly enabled by a contact invite, ordinary Open status, or a group tag.

Contacts may be grouped as **favorites / friends / colleagues / anyone approved**, but the final decision is computed for the caller and session, not as a public social label. Deny and block win against every grant, even when "urgent" is asserted. Revocation takes effect during active negotiation and subsequent policy checks, not only at next sign-in.

**Migration:** read the current reciprocal contact rows, propose an explicit owner-by-owner backfill into directed basic connection grants; do not accidentally grant `bypass`, calendar detail, recording, or screener access. Keep the old API behind a deprecation adapter until iOS and browser versions migrate.

### Availability is a policy, not just an enum

`user_preference`: `open | ask | closed` still exists as a simple top-level control. The visible **effective status** is computed:

```text
effective = evaluate(
  explicit block/revocation,
  owner manual Closed / override,
  OS reachability and supported delivery mode,
  per-contact grant and time-window rule,
  calendar Free/Busy overlay,
  active session / concurrency limit,
  urgency / separately granted bypass,
  screener availability and cost limits
)
```

Rules are evaluated server-side (not merely hidden UI). **More restrictive rule wins by default.** An emergency bypass can override only enumerated user-level restrictions; it cannot override blocks, missing authentication, OS-protected restrictions, unknown device capability, a recording refusal, or a withdrawn grant.

Examples:
- "Open to friends for the next 45 minutes."
- "Open to favorites every weekday between 6 and 9 PM."
- "Ask first during my meetings."
- "Always let Alex request the screener; only let Sam interrupt."
- "Show my colleagues only that I'm occupied, but my family may see an approximate end time."

**Default:** Closed at registration. No silent microphone access just because a contact is Open. Effective status and reachability are separate: `effective_open=true` does not mean `can_auto_answer_on_ios=true`.

## 4. Calendar heads-up (first availability signal)

Initial automatic signal: **calendar free/busy only**. Do not infer busyness from microphone, motion, health, attention tracking, camera, or arbitrary background sensors. Such additional signals would need independent permission and an explicit later design review.

- Separate calendar read permission with an on/off switch and listed calendars.
- Compute busy blocks with timezone and recurrence correctness, buffer settings and a bounded look-ahead. Do not reveal meeting names, location, invitees, descriptions, or exact starts by default.
- While a busy event applies, effective `open` becomes `ask` for ordinary callers; the user's base Open status is unchanged. When the event ends, restore the previously computed policy only if no newer manual override supersedes it.
- If calendar access fails or is stale, say **availability unknown**; do not claim the user is free or promise an ETA.
- The heads-up may be local/on-device if practical; the hub should store coarse policy state rather than full calendar content.
- "Busy, perhaps free around 3:30" only when computed from an eligible calendar source and authorized disclosure tier. Allow rounding and user-selectable vagueness.
- A detected calendar block does not itself authorize recording, auto-declining, high-priority push, or provider transmission.

Acceptance: a calendar event begins and ends; normal callers see only generic busy state and a request/hold option; manual Closed is never overwritten; disabled calendar permission results in no derived signal.

## 5. Decline, hold, messaging and non-user fallback

### Hold journey

When a caller is not put directly through, offer **Wait**, **Leave a message**, **Talk to [recipient]'s Horus**, or **End** as individually permitted:

```text
request -> authorized? -> device reachable? -> effective status
                               | Open -> live attempt / OS answer
                               | Ask -> pending request / heads-up
                               | Busy -> coarse notice -> wait | message | screener | end
                               | Closed -> unavailable | permitted async message
                               | Offline -> async message or external fallback
```

A hold is a durable, bounded request state, not a perpetual open microphone connection or an indefinite server job. Suggested initial max wait: **10 minutes**, configurable by owner; show queue position only if it is truthful. Sender can cancel; recipient can reply asynchronously, accept, decline, or "available again" later. Client disconnect ends an ephemeral live media request but should not erase an authorized persisted message.

Hold music: use bundled original/royalty-cleared audio, or local synthesized audio; never assume popular music is licensed. Music is heard on caller's device; don't record it or stream receiver's ambient microphone.

### Decline semantics

Recipient can choose **Decline silently**, **Decline and send generic busy reply**, **Offer message**, **Offer screener**, or **Snooze contact**. A decline is not automatically accompanied by a reason; the caller's display is the least revealing authorized response. "They declined" vs "not available" can itself be sensitive—make the distinction a user preference.

### Non-Horus fallback

Two independent fallback options, separately enabled:

1. **Conventional phone/SMS** via OS dialer/deep link or supported licensed telecom provider. Display phone destination if authorized and disclose any per-minute/SMS charge; never auto-send SMS or auto-dial on behalf of someone who has not authorized the action.
2. **Time-limited guest web invite** tied to a single recipient-accepted session, with short expiry and a one-time token. Guest receives *no* broad contact graph, screening context, calendar status, model access, or bypass.

Neither fallback should require the other person's Horus installation or permanent Callless account. Prevent open-guest-link forwarding/replay and rate-limit enumeration. A free guest path is a product priority; PSTN/SMS may be a later paid integration.

## 6. Screener: receiver-controlled AI, bounded and transparent

The screener is an agent **operating under the recipient's identity and authority**, never the caller's unrestricted LLM. It should not be mistaken for the recipient. It can:
- Say it is Horus acting on the recipient's behalf and disclose model processing **before the caller provides substantive content**.
- Collect the caller's identity, brief purpose, preferred follow-up window, and a concise bounded message.
- Answer only explicitly published/approved FAQs or availability statements that the recipient has granted for that caller or audience.
- Offer to queue a human callback or pass a concise summary to the recipient.
- End gracefully when quota, expiration or policy limit is reached.

It **cannot** read the user's private memory, email, calendar event content, files, or other sensitive data unless separately authorized for this specific disclosure. Retrieved content and caller statements are untrusted input and cannot rewrite permissions or trigger arbitrary tools. The screener's system policy and instruction hierarchy must not come from the caller.

**Inference:** recipient chooses local model or the recipient's configured BYOK provider; the hub only supplies policy-bound envelopes, not raw secret keys. To avoid accidentally calling the model on the wrong machine, the model execution service must be explicitly tied to the recipient's delegated device/host. If no eligible executor is online, offer to leave a message; do not silently route to a hub-operated provider.

**Provider disclosure:** "You're speaking to Alex's Horus. What you say may be sent to Alex's selected AI provider ([provider name]) to process this request." Require the caller to choose **Continue**, **Leave message without AI**, or **End**, and provide an indication if provider processing changes mid-session. An approved text message may still be stored/delivered to the recipient subject to the messaging policy; never describe a message as provider-free if automatic AI summarization will read it.

**Quota policy**, enforced server-side and by the model executor: suggested per caller / per recipient / rolling day defaults (subject to pilot adjustment): 2 sessions, 3 minutes active screener time total, 3,000 output+input tokens, and a hard recipient-set currency cap. Stop when **any** cap is reached. Meter transcription/TTS separately where applicable. Never let the caller increase the receiver's spend budget or initiate premium tool calls. Give a polite one-turn wrap-up and a message option; if the cap is exceeded, decline further provider calls.

**No permanent recording by default.** Any ephemeral speech-to-text used for live screening is disclosed and retained only as long as necessary, with a separate explicit consent gate for saving transcripts and summaries.

Acceptance: a caller cannot retrieve non-published secrets even by prompt injection; billing stops at quota; offline receiver gracefully degrades; provider disclosure precedes model processing.

## 7. Urgent requests vs privileged bypass

These are **different products and permissions**.

### Urgent push

- Ordinary approved caller can label a request urgent **only if the recipient allows urgent requests** for that contact or group; marking something "urgent" is not a bypass grant.
- Score based on *transparent, inspectable* signals: caller-selected reason, opt-in relationship category, documented history of recipient-reviewed false urgency, frequency, time since last request, and known "urgent" preferences. Don't analyze people's personality or infer a medical emergency.
- **Per-sender / per-recipient rolling caps**, server-atomic and enforced across devices (pilot proposal: 2 accepted urgent alerts per 24 hours; cooldown 60 minutes). Cap outcomes must not be bypassable by changing device/session.
- Recipient can view every urgency claim afterward, mark it legitimate/incorrect, revoke the permission, and see any automated rationale. History is private to that recipient and must not become a global reputation score.
- Only a platform-supported priority notification is attempted. This does **not** promise bypass of Focus/DND, OS settings, offline devices or push-delivery guarantees. A non-delivered urgent alert is reported as such.

### Bypass

- A separate, explicit, individually granted `can_bypass` capability, with expiry, permitted hours, max uses and allowed restriction types.
- Recipient sees an unmistakable **"Alex connected using your authorized bypass"** visual/audio announcement when actually connected; caller also sees that the privileged route was used.
- Record **every attempt and result** in a durable, recipient-accessible ledger: who, time, relevant grant version, restrictions bypassed, device, outcome, revocation and review status. Provide recipient export/revocation and a visible current-bypass roster.
- A bypass cannot activate a microphone on a device/OS that does not permit it, cannot override an explicit block or revocation, cannot start recording, and cannot silently enter an already active private call.
- No one acquires bypass because they sent enough urgent messages, used a particular phrase, or are in a friends group.

Suggested precedence:

```text
hard block / identity failure / no permitted delivery / no consent
   > manual Closed unless a narrowly scoped bypass expressly covers it
   > time/calendar rules (may be bypassable if grant says so)
   > Open / Ask policies
   > caller requested urgency (notification priority only)
```

## 8. Native receiver delivery: achievable platform contracts

**Current:** browser requires a foreground tab and a Join tap. That cannot be marketed as "Open means instant pickup."

**iPhone target:** a native Callless account, authenticated APNs/PushKit device registration, CallKit/AVAudioSession integration, conversation tone, reliable disconnect, and explicit policy-aware routing. On supported devices, the system's incoming-call handling must remain authoritative. Apple documents that VoIP PushKit notifications for calls use CallKit and its system UI; do not promise invisible background microphone activation or unconditional auto-answer. See:
- [Apple: Responding to VoIP Notifications from PushKit](https://developer.apple.com/documentation/pushkit/responding-to-voip-notifications-from-pushkit)
- [Apple: CallKit](https://developer.apple.com/documentation/callkit)

**Acceptance contract:** authorized Open caller -> backend creates pending call -> push to recipient -> OS presents supported call UI -> upon actual answer/activation, play distinct Callless connection tone to both sides -> media routes to chosen headset. If native automatic answer is prohibited, require the OS answer gesture and show honest UI. If already in foreground and OS permits a live session, an explicitly user-enabled intercom mode may reduce steps; validate physical device and privacy indicators before claiming it.

A generic APNs "urgent" notification is **not** a substitute for a VoIP call invitation. Avoid using PushKit for notifications that aren't real calls. Don't promise that emergency requests can defeat Focus/DND. Implement Android with its own OS-compliant call/notification entry points.

**Multi-device delivery:** user is Open; reachable devices are a separate, observed set. Choose one primary endpoint or expose a controlled answer race. Acknowledgment revokes redundant ring invitations; media may move after negotiated handoff. Never allow both unattended microphones to activate.

## 9. Recording, provider disclosure and privacy

**Baseline:** opt-in **all-participant consent** before recording or saving a call transcript, even if one jurisdiction could allow less. This is appropriate for a California-first rollout; California Penal Code § 632 has all-party consent requirements for certain confidential communications. Obtain legal review of recording, transcription, AI model monitoring and multi-jurisdiction calls before launch.  
Reference: [California Penal Code § 632](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=632.&lawCode=PEN).

Design rules:
- Unrecorded audio flows through encrypted WebRTC media, with no application recording or saved transcription by default. Browser microphone usage during a live call is not equivalent to saving a recording.
- Any recording, transcript, AI processing, and AI-generated summary are **distinct permissions**, not bundled into "joined Callless." Where appropriate, disclose real-time model processing and seek required consent before it occurs.
- Start recording only after all active human participants give session-specific, revocable permission; announce the start and show a persistent indicator. Joining parties must give consent too.
- Revocation stops future capture and processing immediately. Retain/delete pre-revocation material according to the explicitly agreed retention policy; do not promise retroactive deletion from external providers without verification.
- Recording a party line or an agent-mediated call must account for all participants, including any automated agents and new joiners.
- Saved recordings/summaries, if enabled, are encrypted at rest, access-controlled, bounded by retention, exportable/deletable subject to legal requirements, and have an auditable consent record.
- Provider switches mid-call require renewed disclosure/approval before content is forwarded to the new provider; no API key is ever disclosed to a caller.
- Signal metadata is not equivalent to voice confidentiality: standard WebRTC media encryption does not alone verify an untrusted signaling hub's identity bindings. Require hardened identity/key verification before making a general E2EE claim against a malicious hub.

Proposed initial retention (to approve before implementation): signaling payloads ephemeral only; unreplied invitations 15 minutes; ordinary pending requests 10 minutes; non-recorded audio 0 stored; messages max 30 days by default; security/consent/bypass audit 90 days with owner export and deletion controls as appropriate. Jurisdiction-specific retention obligations may override these product defaults.

## 10. Future capabilities with explicit boundaries

| Capability | Expected behavior | Hard boundary / dependency |
|---|---|---|
| Agent-to-agent | A scoped question/handoff between two principals' assistants, without disturbing the people | Per-principal authorization, per-call tool scopes, disclosure, spend caps, signed provenance, no unsupervised privilege escalation |
| Automatic open/close doors | A specifically enrolled actuator may unlock/open or secure a door after a separately authorized request | **Not** a Callless side effect; explicit device permission and safety checks, anti-replay, sensor readback, local override, emergency egress, fail secure |
| Party line | Invite multiple approved participants into a shared conversation with visible roster and moderator/leave controls | Group consent, identity, SFU/TURN scaling, join/rejoin correctness, recording all-party rule |
| Mid-call handoff | Seamlessly move audio between desktop, iPhone, AirPods host, etc. | One media owner at a time, device capability, re-key/re-negotiate, no double microphone, no loss of consent |
| Whisper-in | An explicitly permitted assistant gives private suggestions to its own user without broadcasting them | Clear participant AI disclosure; never secret third-party listening, no channel bleed, separate audio mix |
| Caller-pays | With explicit rate and capped preauthorization, caller covers selected relay/screener/inference costs | Meter by cost source, fraud protection, refunds/disputes, accounting records, no surprise charges, no sharing receiver's API key |
| Non-user fallback | OS phone/SMS or limited guest invite without Horus install | Telecom integration and costs or identity-bound guest authorization; fraud/rate limits; no contact exposure |
| Smart user-status rules | Beyond calendar to focus/device/task state | Separate opt-in per signal, locally minimized sharing, never continuous ambient recording by default |

Doors are deliberately treated as a separate safety-sensitive capability. "Get me to Alex" must **never** unlock a door by itself. Camera/health-derived "urgency", covert whispers, secret recording and silent universal override are out of scope.

## 11. Trust boundaries and target architecture

```text
Client (Windows/iOS/web)
  -> identity and device-auth service (user account, revoke sessions)
  -> Callless policy service (directed grants, effective status, quota, consent)
  -> session orchestrator (request/hold/screener/live/end, auditing)
  -> notification service (APNs/PushKit/CallKit path; Android counterpart)
  -> signaling gateway (authenticated WebSocket, short-lived SDP/ICE)
  -> WebRTC peers or managed TURN/SFU (encrypted media)
  -> recipient-owned screener executor (local model or scoped BYOK)
  -> optional guest/PSTN gateway (separate paid permission)
```

The **public Callless hub must be separated from the local Horus PC admin/control API**. A trusted reverse proxy that hides admin paths is an interim bench arrangement, not a permanent isolation mechanism. Production identity, signaling, rate limits, queues and quotas must have shared transactional state; the prototype's process-global `connections`/`sessions` maps cannot coordinate multiple workers. Use a managed durable store (e.g., Postgres), ephemeral presence/pubsub (e.g., Redis), and an intentional topology; don't add them before a concrete scaling need is demonstrated.

Security essentials:
- Identity-bound session tickets with expiry, nonce, anti-replay; message/SDP size limits, schema validation and no cross-user session ID exposure.
- Mutual confirmation where requested; caller authorization is re-evaluated on accept, signaling, reconnect, bypass and revocation.
- TLS for identity/signaling/keys; reverse proxy handling must be explicit about trusted forwarded headers.
- Source-specific rates for sign-up/login, invites, urgent requests, guest links, screener requests and paid actions; single-token hash storage, password reset and account recovery.
- Device revocation; logout-all and delete account; avoid storing raw tokens in browser localStorage in production. Prefer secure, same-site HttpOnly cookie/BFF or native OS credential store with CSRF protection as applicable.
- Explicit consent/version/audit provenance; per-subsystem data minimization; no third-party analytics receiving raw call metadata.
- Security audit before public hub exposure; test abuse/spam, replay, denial of service, device spoofing, NAT failures, and malicious signaling.
- Restrict remote assistant execution to recipient-approved capabilities, independent of contact status; budgeted LLM calls and tool audits.

**Tailscale:** suitable for early trusted-friend access to the hub over a private tailnet, but not a replacement for the WebRTC session architecture. Use ordinary WebRTC + STUN/TURN for broad distribution. Tailscale should not be an end-user requirement.

## 12. Session state machine and failure behavior

Proposed canonical states:

`created -> checking_policy -> {rejected, invited, pending_approval, waiting, screening, ringing} -> negotiating -> connected -> ending -> ended`

Terminal reasons: `cancelled | declined | denied_policy | blocked | busy | expired | unreachable | auth_failure | no_device | media_failure | quota_exceeded | disconnected`.

Rules:
- State transitions checked against actor capability and current grant; never trust a caller-declared `status=connected`.
- Each session has a cryptographically unpredictable ID and a monotonic server-side version; duplicate messages are idempotent and cannot create extra charges.
- Retries have bounded expiry and explicit reason codes; stale pushes cannot join expired sessions.
- Race: two devices answering one invitation -> one winner, losers cancelled; peer disconnect -> stop local media tracks and deactivate mic.
- Bypass/urgent review events are durable even if no connection was established.
- A queue or screener session cannot remain in Open forever when no owner device/executor is reachable.

## 13. Phased delivery and acceptance gates

Ordered primarily by cost/risk, with prerequisites explicit. **Do not parallelize all the phases into one commit.**

| Phase | Deliverables | Evidence required before marking done |
|---|---|---|
| **0. Stabilize baseline** | Fix unrelated red CI or document exact quarantines; isolate public hub from host-admin API; test real two-browser signaling, SQLite migration/backup, auth/revocation and latency | Main CI green for affected surface; independent two-device smoke tests; threat model |
| **1. Permissions + policy (no model)** | Directed grants, friend groups, time-boxed Open rules, block precedence, audit ledger, detail-sharing scopes, short-lived invites | Migration tests, authorization matrix, expiry/concurrency tests, backwards compatibility |
| **2. Busy/hold and fallback** | Calendar Free/Busy overlay, generic heads-up, hold/expiry, decline choices, message delivery, first non-user guest link | Privacy tests and consented calendar source, exact state transition tests, guest abuse controls |
| **3. Screener** | Receiver-owned local/BYOK screener, disclosure/consent, typed permitted answers, per-caller minute/token/currency caps, friendly handoff | Provider boundary tests, prompt-injection tests, cost-hard-stop tests; zero unauthorized data leakage |
| **4. Mobile delivery + urgency** | Native iOS CallKit/PushKit/APNs VoIP path, Android OS-compliant counterpart, tone, urgent-notification path, separately granted bypass + permanent reviewable ledger | Physical-device tests, OS focus/lock/answer cases, urgency caps, bypass logs, device revocation |
| **5. Production infrastructure** | Hosted TLS hub separated from PC control API, TURN, durable presence/multi-worker support, monitored reliability, security review, two-site tests | Security signoff, consent review, NAT coverage, failure recovery, load/rate limits |
| **6. Expanded conversation** | Consentful opt-in recording + summaries, agent-to-agent, party line, handoff, whisper-in, caller-pays, optional phone/SMS provider | Individual ADR + privacy/cost/safety acceptance for each; not implicitly part of basic Callless |

**First real product milestone:** two people on different machines, one with Open and the other with Ask, can authenticate, approve contact directionally, connect and talk with predictable media/permission behavior; a declined request can deliver an authorized message; no room for accidental background mic capture or leakage of busy detail. Then validate mobile push separately.

### Suggested automated test matrix

- A grants B, not vice versa; B can request A, A cannot request B; both can revoke independently.
- Block immediately cancels future and active sessions even under urgency/bypass.
- Calendar overlays never overwrite user preferences and expire correctly across DST/timezones.
- No ungranted calendar title, event participant, exact schedule or location appears in caller responses.
- An Open user with no reachable microphone produces a truthful delivery failure, not fictitious live audio.
- Sender waits, leaves a message, or talks to the screener; expiration/cancel are idempotent.
- Caller declines provider disclosure: receiver-owned LLM gets **no** caller content.
- Fake screener context or injected caller messages cannot invoke privileged tools or read memories.
- Quota breach stops model/STT/TTS usage; billing at-most-once and cap cannot be overridden.
- Urgent per-caller limit is race-safe; each event is reviewable; no granting bypass through repeated urgency.
- Explicit bypass attempt has a grant and audit record; both parties receive the announcement on actual connect.
- A participant declining/revoking recording prevents/stops capture for the entire session.
- Late participant entering party line must consent before any recording restarts.
- WebRTC failures, ICE restarts, phone sleep, CallKit answer/reject, handoff race, offline and APNs no-delivery are graceful.
- Non-Horus guest link is single-use/short-lived and reveals no social graph; phone fallback requires explicit human authorization.

## 14. Dependencies, decisions, and engineering change control

**Decision defaults proposed by this document:**
1. **Directed reachability grants** replace symmetric contacts as the policy primitive.
2. **Availability is computed** from manual status, calendar, contact/time rules and actual device reachability, not a single persisted status.
3. **Urgent is never bypass.** Bypass is revocable per-person authority and is always announced/audited.
4. **Screener uses recipient-owned inference**, with preflight provider disclosure and hard per-caller budget.
5. **Recording off by default**, with all-party, per-session consent for saving audio/transcripts and separate permission for AI summarization.
6. **A guest path is important**, but any ordinary telephone integration needs explicit telecom economics/consent.
7. **Native iOS cannot be promised silent auto-answer**; CallKit and OS permissions control actual media activation.
8. **Public network infrastructure is separate from the personal-PC control plane.**

**Open product decisions:** first supported guest path (web-only vs phone), exact priority semantics, manual Closed versus bypass scope, what vague busy information can be shown and to whom, initial screener budget defaults, message retention, mobile connection tone behavior under system policy, which region hosts the signaling service, and whether group calls need SFU by default. Resolve through short ADRs and pilot evidence, not assumptions in application logic.

**Housekeeping rule:** Every merged capability must update its owner, status (`proposed / implemented / CI-passed / device-tested / released`), security gate, user setup delta, and deletion/disable path. See [Scope and housekeeping](HORUS_HOUSEKEEPING.md).
