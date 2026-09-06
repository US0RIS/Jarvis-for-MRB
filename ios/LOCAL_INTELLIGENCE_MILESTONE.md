# Jarvis iPhone Milestone — Local Intelligence & Reliability

Status: **implemented in iOS source; requires an iPhone build/test.**

This milestone intentionally does **not** require a Windows/backend deployment. Its purpose is to make the iPhone a smarter front door to Jarvis so routine questions are not unnecessarily exposed to backend tool-selection mistakes.

## Architecture

```text
voice / typed request
        |
        v
Local Intelligence router (iPhone)
        |
        +--> deterministic utility? ------> local answer
        |
        +--> iPhone Calendar/Reminder/
        |    Contacts/timer request? -----> native iOS framework
        |
        +--> existing local Jarvis tool? -> Known People / OCR / Power / Productivity
        |
        +--> stable general question? ----> Apple on-device Foundation Model
        |
        `--> actually needs PC/web/action -> existing authenticated backend
```

The milestone starts **after** the existing frontend controllers so it becomes the outermost local routing layer without replacing them.

## 1. Local-first routing

The iPhone gets first refusal on every Jarvis command. It handles requests locally when doing so is both useful and safe, then delegates to the existing frontend handlers and finally to the PC only when necessary.

This specifically prevents failures such as:

> “What time is it in DC?” → inspect whether Clock.app is running

The intended route is now:

> “What time is it in DC?” → deterministic iPhone timezone calculation → answer

Tool-like/backend routing remains appropriate for fresh web data, private PC state, Gmail/backend actions, Windows/browser control, or other requests the iPhone cannot truthfully satisfy.

## 2. Deterministic local utilities

The iPhone handles common stable utility questions without an LLM:

- current local time
- common-city/timezone time questions (including Washington, DC)
- current date/day
- simple arithmetic
- percentages
- common length, mass, volume, speed and temperature conversions

These routes are intentionally deterministic rather than model-generated.

## 3. Apple on-device answer path

On supported Apple Intelligence hardware/OS versions, stable explanatory questions can use the existing Foundation Models integration **before** going to the PC.

The local router refuses this path when the wording indicates likely need for:

- fresh/current web information
- Gmail/inbox information
- private PC/browser/file state
- external actions
- device/app control
- current visual-scene questions

If Apple's on-device model is unavailable or declines to answer, normal backend routing remains the fallback.

## 4. Native iPhone Calendar

Using EventKit and explicit permission, Jarvis can locally answer examples such as:

- “What meetings do I have tomorrow?”
- “What's on my calendar today?”
- “What's my next meeting?”

This reads calendars already available through the iPhone Calendar database. It does not require the PC Google connector.

## 5. Native Apple Reminders

With explicit Reminders permission, requests beginning with “Remind me…” can create Apple Reminders directly on the phone. Relative reminders such as “Remind me in 20 minutes to…” are resolved locally.

This is separate from backend scheduled jobs.

## 6. Local Jarvis timers

Jarvis can schedule notification-backed local timers without opening or querying Clock.app.

Examples:

- “Set a timer for 10 minutes.”
- “How much time is left on my timer?”
- “Cancel my timer.”

The timer persists through app suspension because delivery is owned by `UNUserNotificationCenter`.

## 7. Native Contacts bridge

With Contacts permission, Jarvis can locally answer contact-detail requests such as phone number/email lookups.

Explicitly enrolled Known People profiles can be linked to iPhone contacts by name. Auto-linking occurs only when there is a unique match; ambiguous results are deliberately left unlinked.

Face recognition remains closed-set and advisory. A face match alone is not sufficient authority for a consequential action.

## 8. Encrypted Context Capsules

“Remember this context” saves an explicit local snapshot containing available context such as:

- active Jarvis conversation mode
- currently matched enrolled person, if any
- recent on-device OCR text
- last recognized command
- last Jarvis response
- bounded clipboard excerpt
- coarse local coordinates when location context is enabled

Capsules are encrypted with AES-GCM using a device Keychain-protected key and complete file protection.

The capsule does **not** silently persist raw camera frames or the rolling raw microphone buffer.

## 9. Unified local memory search

The new Local Memory screen searches across iPhone-side Jarvis data in one place:

- context capsules
- device-session conversation history
- Known People profiles/notes
- local perception/power events
- captured known-person encounters
- enrolled inventory
- goals
- waiting-on items
- local action receipts

A voice query can also ask:

> “Search local memory for Japan flight.”

When the Apple on-device model is available, Jarvis can synthesize an answer **only from the retrieved local records**; otherwise it returns the matching records directly.

## 10. Local Intelligence UI

The app now has a second `Local` tab. It provides:

- local-first routing toggle
- stable on-device answer toggle
- Calendar / Reminders / Contacts toggles and permission status
- Known People → Contacts linking
- context-capsule controls
- Local Memory search
- active local timer display
- local-route diagnostics
- reproducible verification prompts

## Permission model

New permission descriptions were added for:

- Calendar full access
- Reminders full access
- Contacts

No permission is requested merely because the app launches. The user grants access through an actual feature request or the Local Intelligence screen.

## Explicit boundaries

This milestone does **not**:

- modify or require deployment of the Windows backend
- make the pending backend conversational `what can you see right now?` fix count as deployed
- weaken the Stop Camera master kill switch
- add public/cloud face recognition
- intercept third-party iPhone notifications
- add a WidgetKit / Dynamic Island / Control Center extension target

Dynamic Island, Lock Screen widgets and Control Center controls remain a separate frontend milestone because they introduce additional extension targets, provisioning/signing and lifecycle behavior rather than ordinary in-app code.

## Verification

After rebuilding the iPhone app, use the `Local` tab and run:

1. `What time is it in DC?` — should answer the Eastern time directly and never inspect Clock.app.
2. `What is 17 times 24?` — should answer `408` locally.
3. `Convert 5 miles to kilometers` — should convert locally.
4. `What meetings do I have tomorrow?` — should request/use iPhone Calendar access.
5. `Set a timer for 2 minutes` — should create a local notification timer.
6. `Remember this context` — should create an encrypted context capsule visible in the Local tab.

Session History should identify local responses as iPhone/frontend responses rather than Qwen backend responses.
