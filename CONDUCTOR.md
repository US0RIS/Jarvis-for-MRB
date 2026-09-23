# Jarvis Conductor v1 — "Prepare my workstation"

Conductor v1 is a **bounded, implemented** cross-device mission executor that
sits above the Reality Mesh. This is not a general autonomous computer operator
or universal EDITH implementation.

## Operator activation

Both the Windows API server bearer token and the private Reality Mesh must
already be configured. Set in the **Windows Jarvis backend process**:

```powershell
$env:JARVIS_CONDUCTOR_ENABLED = '1'
# Also JARVIS_MESH_WINDOWS_APP_ENABLED = '1' if the selected host is Windows.
# Also JARVIS_MESH_WINDOWS_SCREEN_ENABLED = '1' if a Windows view is selected.
# Restart the authenticated Jarvis backend in the same interactive user session.
```

For Macs the existing separate Mac node's `--allow-app-launch`, optionally
`--allow-screen`, its distinct Mac token and its private Tailscale address
must be configured. macOS Screen Recording needs its genuine OS permission
when selecting the view. All remote Mac paths must resolve to the configured
exact node; no LAN discovery, custom hostname from the mission or arbitrary
shell input.

On the iPhone/iPad open **Mesh**, enable Mesh and the independent Conductor
switch, check devices, select **one exact device** and 1–3 literal apps.
Optionally request a two-minute private, view-only screen. **Review exact
workstation mission** creates a draft valid for two minutes and a fresh,
cryptographically random **one-use grant returned once to iPhone RAM**.
Nothing launches during preview. The final visible iPhone confirmation
redeems that exact ID + selected device + ordered app list + token. The
backend reserves/consumes it before external execution. Replaying the
token, changing target or app list, expiring or revoking it fails closed.

Mac app names: Safari, Notes, Calendar, Preview, Finder. Windows app names:
Notepad, Calculator, File Explorer, Paint. No terminal, file transfer,
arbitrary executables, generalized remote keyboard/mouse, clipboard, email,
purchases, locks, weapons, or physical-force action is included.

## Real execution and independent verification

Each step checks the live target and exact app capability; before any
attempt Jarvis records the current process observation with node/source/time.
An app already observed running is **not re-launched**. If absent, Jarvis
reserves the step in its private SQLite ledger **before** contacting the host
or launching a fixed Windows process. Consecutive launches are paced to
respect the Mac/Windows local 3-second rate limit. After launch it calls a
**different fresh status-observation endpoint**: /v1/apps on a paired Mac,
or fresh Windows psutil process enumeration on the current Windows host.
Only a newer, matching-node process observation can label the desired
app state running. Zero-exit on macOS open or a Windows Popen handle alone
does not qualify.

If source data is missing/stale, the node disconnects, a result is ambiguous,
or any app does not appear running, the mission is
`partial_or_unverified` or `blocked`. Failed/uncertain actions **do not
automatically retry**. `verified_apps` asserts only that specified process
names were observed running at a checked time, **not** that the app is in
the foreground, a new window opened, or the user is viewing its contents.
Before-start running processes can also satisfy the user's desired state
without being caused by Conductor.

Each mission ID, selected node/apps, grant **hash** (not raw token),
status, step reservation, observed process state, timestamp, and brief
source/error receipt are stored in `conductor.sqlite3` under the existing
Jarvis private app directory. Screen pixels and raw API/Mac secrets are
**never** stored there. `Inspect persisted mission state` fetches the
specific last session ID. The iPad button **View recent Conductor receipts after
restart** retrieves up to 15 persisted source summaries **without** returning
historical one-use grants; opening a past draft cannot execute it after the
app's RAM-only approval is gone. Revocation blocks future steps; a host action
already in flight cannot be rolled back. Server restart with a `running`
record is an **unknown/inspect** situation, not authority to replay it.

When a screen was specifically included, the same iPhone confirmation may
then request the existing 120-second private Mesh view only *after* apps
verify. The iOS app must accept real image bytes before it says the view
is available. A host may deny access or an app can suspend; in this case
the apps can be independently verified but screen viewing is unavailable.
App foreground/background, stopping the view, phone privacy mode and the
Conductor disable switch clear/revoke consent where the system can reach
the backend. A failed revocation request is reported as **unconfirmed**,
not assumed successful.

## EDITH-style "say it and it happens", only for low-risk exact actions

The **separate** default-off switch "Allow exact spoken app actions on paired
computers" enables literal requests such as:

- "Jarvis, open Safari on my MacBook Air."
- "Jarvis, open Notes on my Mac mini."
- "Jarvis, open Notepad on my PC."

The deterministic iPhone parser recognizes only exact registered app/device
names. It does **not** route that command through the general model, infer
another app, open a custom file or capture the screen. If all three iPhone
switches, the Windows Conductor operator flag and target host's exact-app
flag remain on and the host answers live, the phone stages and redeems a
fresh **single-app, no-screen, one-use mission for that utterance**. The
host checks independent process state and Jarvis reports verified, unverified,
or blocked. There is still a 3-second host rate limit; no automatic repeat.

**Important limitation:** the existing speech system recognizes a
*transcript*, not a cryptographically authenticated person's voice.
Anyone who can trigger the mic/wake-word while this low-risk switch is
on may cause those registered benign app launches. Keep it off in shared
environments. **A UI tap and this voice switch are iPhone-side user intent
checks, not server-verifiable physical-presence attestation**: a holder of
the Windows Jarvis API bearer can also request plans and spend returned
grants through the authenticated API. Never give the token to untrusted
clients. Add device-bound signed action approvals before extending Conductor
to consequential real-world actions.

## Test and release boundaries

`tests/test_conductor.py` covers draft/no-actuation, app/host binding,
hashed grants, repeat/expiry/revocation, fresh process checks, already-running
success, unknown/stale verification and ambiguous response no-retry, plus
Swift voice/approval/Privacy contracts. Existing Mac HTTP protocol and Windows
mock OS process tests remain in the configured workflow. Python+simulator
CI is not real interactive Windows/Mac/iPad acceptance. Test the full
workflow on the actual workstation with existing permissions and with
the iPad in/out of foreground before calling this deployed.
