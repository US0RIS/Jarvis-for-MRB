# Human Extension v1 — Reality Lens

This branch is the first executable slice of the **expandable human interface
to reality** discussed in September 2026. It is deliberately not a claim to
have implemented omnipresence, prediction, autonomous manufacturing, embodied
robotics, or a new human sensory organ.

## What actually works in source

The iPhone/iPad Mesh tab already resolves an **exact named place** through
Apple MapKit and requires selecting among ambiguous results. After an
authorized one-shot public-world observation, open **Reality Lens • sense and
remember**. This adds three concrete capabilities in one interaction:

1. **Remote sensory extension:** explicitly tap **Sense and compare** to read
   the real providers already integrated at that place. Four small supported
   scalar families are available when their actual evidence is fresh: modelled
   US AQI, NWS point alert count (supported US regions only), USGS regional
   earthquake event count, and OSM mapped facility count. Unavailable, stale
   and unsupported providers remain visibly unknown.
2. **External episodic memory:** explicitly tap **Remember now • 30 days** to
   save that exact place's label, the observation time, and fresh source-backed
   scalar facts in the private Windows Jarvis data directory's
   `reality_lens.sqlite3`. Coordinates are used to calculate a place key but
   **are not persisted** in this new ledger. No camera images, raw provider
   response, passive microphone data, continuous location trail or full device
   screen is stored by Reality Lens. Saved records expire from queries after
   30 days and the ledger prunes on subsequent explicit saves. Its maximum is
   120 snapshots. The user can inspect the newest 30 memory records.
3. **Tactile change sense:** explicitly tap **Sense and compare** again. The
   backend compares each current fresh scalar only with the latest saved
   snapshot for the exact coordinates and same provider. Changes are displayed
   with before/after, source and observed timestamp. If a change exists and
   the phone remains foregrounded, the phone emits two or three light haptic
   pulses. No change/unknown results produce **no haptic**; silence is not a
   safety clearance. There is no unattended phone-background haptic loop.

**Forget this place** requires an explicit destructive confirmation and deletes
only Reality Lens snapshots matching the currently selected coordinates.
It does not delete user-enrolled external watches, Camera metadata, or the
long-lived world model. Turning off Mesh clears the current lens view and does
not silently delete an explicitly saved backend memory.

These capabilities reuse the existing local-first authentication, the
deterministic Reality Graph and iPhone MapKit place-resolution boundaries.
This feature never delegates sensitive provider values or haptic selection to
Qwen. Its backend endpoints are authenticated and set `Cache-Control:
private, no-store`:

- `POST /reality/lens/sense`: exact lat/lon, label and `remember` flag.
- `GET /reality/lens/memories`: bounded memory metadata, no coordinates.
- `POST /reality/lens/forget`: exact selected lat/lon only.

## Install and acceptance

Build the Windows backend and iPhone app from the **same**
`jarvis/human-extension-v1` branch. Configure the existing private Jarvis
token and Mesh. On an actual iPhone, pick a named public place, tap
**Remember now**, change the upstream observation legitimately or wait for a
real measurement change, and tap **Sense and compare**. Verify that the
source-qualified diff and haptic agree, stale/out-of-coverage sources do not
become zero, and **Forget this place** removes its records. Repeat with
another place to confirm no cross-place comparison. Test foreground/background
transitions and Privacy/Mesh off. Backend data removal must be observed via
the authenticated memory list.

CI checks the deterministic module, permission-protected route contracts and
iOS simulator build. It does **not** establish that an outdoor measurement,
Apple haptics or a physical iPhone have been exercised.

## The rest of the human extension is not implemented by this release

The Reality Mesh still provides independently opted-in remote desktop
snapshots and exact benign app launches, the public source adapters still
provide bounded remote observations, and existing watches can continue on
the backend independently of the phone. These are adjacent existing
capabilities, **not** permissions inherited by Reality Lens.

Remote robot telepresence, sensory substitution through a dedicated wearable,
universal camera coverage, global historical video search, physical
manufacturing and autonomous scientific experimentation require real hardware,
documented provider access, consent and independent acceptance. They remain
separate milestones, not fabricated buttons or placeholder endpoints.
