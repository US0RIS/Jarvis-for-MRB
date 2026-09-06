# Jarvis Frontend Capability Architecture

This frontend-only milestone applies the mature systems ideas from the `.etdk` work to Jarvis without requiring a Windows backend deployment.

## Why this exists

Jarvis has accumulated many independent capabilities: deterministic local utilities, EventKit Calendar/Reminders, Contacts, OCR/QR, Known People, inventory, local memory, goals/waiting-on, frontend controls, Foundation Models, and a large PC tool surface. Historically the iPhone local layers were composed by repeatedly wrapping one `frontendCommandHandler`. That remains compatible, but it becomes difficult to reason about routing as the number of capabilities grows.

The new architecture places a small explicit capability router in front of the complete existing local stack. Existing features are preserved through a compatibility adapter, while high-value intent families are promoted into named capability packs with declared priority, effect class, requirements, and activation policy.

No Windows server update is required.

## Core concepts

### Tiny core

The core does not try to understand or execute every capability itself. It classifies a request against a registry and activates only candidate packs.

### Capability packs

Each pack declares:

- stable ID and human-readable name
- category
- priority
- effect class (`Read-only`, `Local write`, `External write`, `Destructive`, or `Mixed / conditional`)
- requirements
- lazy activation policy
- an intent-claim predicate
- an availability predicate
- an execution handler

Current named packs include:

- Camera Master Privacy Gate
- Read-only Pack Composer
- Deterministic Utilities
- Native Calendar
- Native Reminders
- Jarvis Local Timers
- Context Capsule Writer
- Unified Local Memory
- Native Contacts
- Vision / Known People / Inventory
- Local Executive
- Frontend Controls
- Apple Stable-Question Brain
- Legacy Frontend Compatibility Adapter

The compatibility adapter is intentionally lowest priority. It preserves local features not yet promoted into explicit packs.

## Camera invariant

The Camera Master Privacy Gate has the highest priority. If `Stop Camera` is latched and a command requires visual input, the router answers locally that the camera is stopped. It does not permit the lower visual stack to run. This is in addition to the deeper camera-manager master latch already present.

## Read-only composition

The router can decompose a small compound request when every clause is independently recognized as a safe local read. For example, a time question plus a calendar-read question may be handled by separate local capabilities and combined. Any command containing write/action language is excluded from this composer.

This is the first step toward ETDK-style fine-grained specialist composition within a single task.

## Quality shield

Every local response passes through a synchronous deterministic verifier. It checks for structural contradictions such as:

- empty answer text
- repeated `Sir, sir...`
- a time question receiving Clock application state
- arithmetic/conversion receiving an application-status answer
- read-only packs claiming they performed an external action

A rejected **read-only** response is not spoken as authoritative local output; the request falls through to the existing backend path.

A questionable write is **never automatically replayed**, because retrying a write can duplicate side effects.

An optional background semantic audit can use the existing Apple on-device model after selected read-only answers. It is advisory, does not delay speech, does not authorize actions, and stores its result only in the local audit receipt.

## Execution receipts

The router records bounded per-turn receipts containing:

- selected capability pack
- effect class
- packs considered
- requirements
- routing latency
- accepted/rejected/backend-fallback outcome
- deterministic quality verdict
- bounded command/response excerpts
- optional semantic-audit result

Receipts are AES-GCM encrypted on the iPhone with a Keychain-held key and complete file protection. The UI retains the most recent 200 receipts.

## Canonical regression harness

The `Packs` tab contains a dry-run regression suite. It verifies routing predictions without executing commands or writes. Canonical cases include:

- `What time is it in DC?` -> deterministic utility
- `What is 17 times 24?` -> deterministic utility
- `What meetings do I have tomorrow?` -> native Calendar
- `Remind me in 20 minutes...` -> native Reminders
- `Set a timer for 2 minutes` -> local timer
- `Remember this context` -> context writer
- `Search local memory for Japan flight` -> local memory
- contact lookup -> native Contacts
- `Who is this?` -> visual/person pack
- goals -> Local Executive
- stable explanation -> Apple on-device model
- latest sports score -> backend
- PC Clock status -> backend
- `Open Clock` -> backend

The suite also verifies that the exact previously observed bad response to `What time is it in DC?` is rejected by the quality shield.

## Lazy activation

Packs are not polling workers. Their handlers are considered only when the intent predicate matches. Availability gates prevent unnecessary activation when a required feature is disabled, such as Calendar local routing or the camera master.

The optional semantic verifier is off by default and can be enabled from the `Packs` tab.

## Deployment boundary

This milestone changes only the iOS application. It does not:

- require a Windows backend pull or restart
- deploy the pending backend conversational live-scene fix
- weaken the camera master switch
- add unrestricted shell access
- add new external-write authority
- automatically replay consequential actions

Future integrations such as a Mac Messages bridge, MusicKit, HomeKit, or Maps should be implemented as additional explicit packs rather than new ad-hoc routing branches.
