# Horus Earpiece — camera-free AirPods-first capabilities

**Status (2026-10-21):** source merged on `claude/relaxed-gates-9jfruc`; Python suites green; **not device-validated**. See the delivery states in [Capabilities](CAPABILITIES.md). Requirements: [AirPods-first vision](AIRPODS_FIRST_VISION.md).

## One path, not nine assistants

```
iPhone (push-to-talk / Action Button, AirPods route)
  └─ POST /command or /command/stream  {text, session_id, context:{channel, latitude?, longitude?, location_accuracy_m?, location_captured_at?}}
       └─ voice_router.observe()  → optional spoken preface (belief-gap warning)
       └─ agent._fast_path → voice_router.route()  → first handler that answers
            object_memory · saved_places · callless_voice · situational_voice ·
            voice_watches · proactive_briefing (+ proactive_attention) ·
            conversation_refine · belief_gap
       └─ otherwise: Reality Graph → model-free dispatch → model planner (unchanged)
```

- `context` is optional. A phone fix is used only if complete, finite, and captured < 15 min ago; otherwise the turn says why no location is known. The iPhone attaches a fix only when location access is already authorized and a cached fix is < 10 min old (no new location prompt).
- Follow-up focus (last object, place, calendar read, alert) is in-process memory per session with a 10-minute expiry, never persisted. The router records which capability answered the previous turn, so a bare "no, the bottom drawer" only corrects when it actually continues that exchange.

## What a user can say

| Feature | Example | Evidence and honesty rule |
|---|---|---|
| Object memory (4) | "Remember I put my passport in the top drawer of my desk." · "I moved my passport into my suitcase." · "No, the bottom drawer." · "Forget where I put my passport." | Stored as `user_spoken`/`user_typed` assertions with time and exact words. Moves supersede (history kept); immediate corrections mark the old claim *corrected*. Mirrored to the world model as `user_report`, never visual. |
| Physical Ctrl-F (5) | "Where are my jumper cables?" · "What else did I put there?" · "What's in the trunk?" · "Where was it before?" · "How do you know?" · "Have you seen my keys?" | "You last told me…, on Tuesday." Stale after 14 days ("may have moved"). Ambiguity → "I have 2 matches… which one?". Unknown → honest unknown. Optional camera sightings are mentioned separately and labeled. |
| Saved places | "Save this place as home." · "Forget my home location." | Only from a fresh phone fix; Horus never infers home. |
| Situational (6) | "Anything interesting happening around me?" · "What's happening in the airspace around here?" · "Is anything unusual happening near home?" · "What should I know before leaving?" · "What's changed since I was here?" · "Tell me more." | Only fitting sources are called (NWS + modelled AQI, USGS, OpenSky, OSM), cached per ~1 km area. Every unreachable source is named; an outage is never an all-clear. Coarse 30-day area signatures, deletable ("forget my place history"). |
| Watches (7) | "Watch for new severe weather alerts near home for the next three hours." · "Watch air quality here until 6 and tell me if it goes above 100." · "What are you watching?" · "Pause / resume / cancel the weather watch." · "Cancel that." | Typed `external_watches` with exact expiry and cadence; baselines are silent; alerts carry source and evidence; dedupe, cooldown, hourly budget; pause/cancel/expiry re-checked after remote IO. Unsupported domains (flights, transit, traffic…) are refused, not stored. Says so when the background runner has not checked in. |
| Briefings (8) | (proactive) "Your meeting with Dana starts in fifteen minutes. One document changed…" · "Snooze briefings for an hour." · "Set quiet hours from 10 pm to 7 am." · "Why did you tell me that?" · "What did you hold back?" | Scored from `world_prebrief` evidence; below threshold is recorded, never spoken. |
| Delivery | — | Live companion publish records connected-client count; APNs rows are `not_configured` / `queued` / `sent` (only on APNs 200) / `failed`. Nothing is called "delivered" because it was queued. |
| Conversation (2) | "What's on my calendar tomorrow?" → "Just the afternoon." → "The first one." · "Stop." · "Never mind." | Narrowing filters only what the permission-checked calendar read returned. Cut-off voice utterances ("remind me to") are asked to finish. |
| Belief gap (9) | "Draft a note saying the Chronos agreement caps indemnity at ten percent." → "One important thing: the project chronos purchase agreement now says 15%. The last recorded reference, when I told you on Tuesday, used 10%. I don't know whether you've seen the update." · "Why did you warn me?" · "Dismiss that." | Requires a document-version numeric change, a conversation turn *before* it that used the old figure, and decision context (current reliance or a related event within 24 h). No exposure evidence → no warning. Ledger kept 90 days. |
| Callless (3) | "Get me to Alex." · "End the Callless conversation." | Directional open/ask/closed grants; `media_connected` only when both clients report inbound audio. The backend never claims a connection. Details: [Callless design](CALLLESS_DESIGN.md#implementation-status-2026-10). |

iOS earpiece behavior (route-loss stop, interruption recovery, turn-generation stale-response guard, barge-in policy, optional Conversation mode): [iOS guide](../ios/README.md).

## Measured latency (backend only)

In-process FastAPI `TestClient`, Linux container, temporary storage, mocked public providers, median of 20 (10 for watch creation):

| Turn | Median | Max |
|---|---|---|
| Object capture (incl. world-model mirror) | 85 ms | 176 ms |
| Object lookup / follow-up | 18–19 ms | 59 ms |
| Situational answer (providers mocked) | 22 ms | 29 ms |
| Watch create / list | 15–19 ms | 34 ms |
| Callless request → both-media (hub, in-process) | 20–27 ms `connect_ms` | — |

**Not measured:** speech-recognition end → first audio on AirPods, live provider latency (this sandbox's network policy blocks the public hosts), APNs latency, two-device Callless setup.

## Not verified on real hardware or live services

Real AirPods HFP/A2DP routing and disconnect timing; barge-in echo behavior; Action Button invocation on hardware; iOS interruption recovery; live NWS/USGS/Open-Meteo/OpenSky payloads; APNs delivery; the companion actually speaking `proactive_alert` events; two-device Callless audio over real NAT/TURN; iOS Safari mic behavior. Watch times like "until 6" use the server's clock; a "near me" watch stays at the creation point.
