# Mission Control — a persistent objective, not a single command

## Implemented first execution pack: make the calendar appointment

The first **actual runtime** is built into the iPhone Jarvis app at **Physical → Mission Control**. It is default-off and requires independently enabled Counterfactual Guardian, motion and location context, foreground phone access, and an authenticated existing Jarvis backend with primary Google Calendar access. It operates with no camera and no MemoMind SDK.

**User loop:**
1. Enable Mission Control (the user separately controls Guardian and location consent).
2. Tap **Find appointment missions** or say **“Jarvis, make sure I get to my next meeting on time.”** Voice enrolls only when the nearest eligible event has no same-start ambiguity. The user selects an exact timed primary Calendar event with literal physical destination. No invented "Home" alias, virtual meeting, all-day date or guessed title destination is enrolled. Maximum five active missions.
3. The iPhone stores an exact objective: calendar event ID, literal destination, start and 30-minute observation window, with bounded source-labelled receipts in device-only Keychain. No raw GPS history or audio is copied to the PC. Apple MapKit necessarily receives origin/destination to calculate its route.
4. At foreground checks (~100-second cadence or manual), re-fetch the exact Calendar source, require a fresh accurate Core Location fix, resolve the destination uniquely through MapKit and obtain a **real** driving ETA. If start/location changes, enter **review required** and revoke the unused Maps grant. If provider data, permissions or fresh observations fail, say **unknown**; never silently mark the objective achieved.
5. For threatened start times (MapKit ETA + explicitly stated five-minute buffer), surface a concise private HUD/phone alert. Busy conversation, meeting or driving suppresses vocal interruption; route estimates carry timestamps and the source on the Mission Board.
6. Intervene using only existing affordances: user-tapped driving directions; or a separately enrolled, **RAM-only, exact mission/event/start/destination, one-use Maps authorization**, consumed **before** a single attempted Maps handoff. Failed handoffs do not get automatic retries. A local ETA draft is visible/copyable by tap but has no recipient or sending route.
7. Distinguish **Maps accepted handoff** from **actual arrival**. Only two different GPS fixes at least eight seconds apart with reasonable accuracy and proximity to uniquely resolved destination record "arrival observed"; compare fix time to the original calendar start for on-time vs late. This is proximity evidence, **not verification of attendance**. An observation window that expires without valid arrival becomes **missed/unverified**, not "you definitely missed it."

**Actual action and evidence graph:** calendar.read, location.read, mapkit.route, maps.open, eta.draft. Each node carries its risk/effect, authority, and independently available verification method on the Mission Board. The companion PC also offers an authenticated **read-only** /missions/affordances inventory of named registered Calendar, Gmail, Windows PC, browser, web search, resource and Agency tools, including current policy allowed/confirmation/Agency scope. A known tool is **not** proof that a device or provider is presently online, permission for this mission, or successful execution. This endpoint cannot invoke anything. The model never expands the set.

**Voice:** "mission status", "check my missions", "make sure I get to my next meeting on time" short-circuit Qwen on the iPhone. It can report evidence-backed mission status or request that the user select among simultaneous appointments. Neither prompt grants additional physical acts.

## Relationship to Guardian and Agency

Counterfactual Guardian detects risk; **Mission Control retains the user-authorized outcome, rechecks the original authority source and physical state, and records whether an intervention or outcome occurred.** It reuses, but does not silently widen, Guardian's Calendar access, exact-event principle or the app's existing Core Location data. Agency stays separately governed by its own explicit goal/tool permissions, steps and verification. A Mission status never overrides Agency's protected approval policies.

The current first pack is **appointment travel** only. It is real, source-backed mission execution on the phone, not a generalized planner that can freely operate Gmail, arbitrary apps or all HomeKit devices.

## Next execution packs (not yet deployed)

* **Prepare to leave:** combine an exact approved appointment with enrolled HomeKit lights and modelled weather, with no inferred accessory names or unsafe appliance/lock/garage actions.
* **Guard a public situation:** time-bounded mission combining an exact official road alert, public camera, aviation or maritime watch, and a user-authored impact condition. No fabricated global live video.
* **Set up my workstation:** explicit machine/application target and approved Windows/desktop tool grants, with independently observed running app/window state, rollback and receipts.
* **Owner/dependency follow-up:** use Guardian's explicit enrolled goal and linked pending commitments to prepare a communication draft; sending still requires exact recipient and content confirmation.

Each new pack requires its own typed observation schema, intervention authority, actual provider/device capability check, negative/unknown states, expiry, verification and adversarial tests. No broad "do anything" tool, model-synthesized actuator, guessed permissions or silent third-party communications.

## Device acceptance checklist

Simulator/CI checks do not certify actual hardware. On a real iPhone with the matching backend running: verify primary Calendar consent, LAN/Tailscale reachability and token; test no/denied/background Location, stale fixes, conflicting same-start calendar events, recurring event IDs, moved/cancelled event, ambiguous MapKit result, unavailable route, and iOS background suspension; validate two **distinct** location observations rather than one replayed fix; manually and automatically open Apple Maps with precise one-use grant, revoked/grant-consumed failed handoff, disabled Mission/Guardian/privacy mode; inspect Keychain receipts for no GPS trail and confirm that no message is sent. MemoMind firmware/SDK, real audio/display path and Apple Home devices remain independent hardware tests.
