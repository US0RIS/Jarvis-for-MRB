# JARVIS EVERYWHERE — Reality Mesh

**Implemented first cross-device slice on `jarvis/memomind-prep`:** explicitly configured Windows host + MacBook Air + Mac mini device fabric; actual authenticated Mac process and screen snapshots; global *place lookup* using Apple MapKit and existing supported public providers; iPhone/iPad **Mesh** tab. No model-created computers, network scanning, invented remote cameras, desktop mouse/keyboard control or unrestricted cross-device actions.

## Topology

```
iPhone / iPad Mesh tab (explicit opt-in)
   ├─ Apple MapKit: user-specified named place -> one uniquely resolved location
   └─ existing authenticated private Jarvis API on Windows (LAN/Tailscale)
        ├─ Windows host status / observed foreground process
        ├─ MacBook Air node [explicit Tailscale IP + separate 32+ character secret]
        ├─ Mac mini node [explicit Tailscale IP + separate 32+ character secret]
        ├─ source registry [provider scope is a fact about integration, not a live feed]
        └─ one-time public-place observation [existing real provider adapters]
```

**What is actually real:** `scripts/jarvis-mac-node.py` is a standalone Python 3 macOS HTTP agent with a bearer-token gate. It publishes a bounded, live system/capability observation on GET `/v1/health`; a Mac started with `--allow-screen` can accept a separate, explicitly tapped **120-second screen session**. The phone requests `POST /mesh/screen/begin` via the existing authenticated Windows backend. The backend forwards to one **configured**, matching Mac only; the Mac itself expires consent after at most five minutes. GET `/mesh/screen/{node_id}` provides screenshot *snapshots*, no more than 4 MB, every approximately 5 seconds while foregrounded. A Stop tap, leaving the screen, disabling Mesh or putting the app in background stops local viewing and requests remote revocation. If that final network call fails, the Mac still expires the consent. The Mac creates a temporary capture file only for the duration of the screenshot and removes it immediately. The iPhone image is RAM-only, not saved to Photos or Jarvis world history. Actual Mac Screen Recording permission must be granted to the process executing `screencapture`.

**What is not implemented:** full low-latency remote desktop protocol, remote keyboard/mouse, OS window transfer/drag-and-drop, clipboard/file transfer, Wake-on-LAN, auto-discovery of Mac devices, silent background iOS capture, Mac/PC arbitrary command execution, direct physical MemoMind hardware. The Windows host status response is real backend status and a foreground-process observation; with separate Windows opt-in, there are also real view-only Windows screenshot snapshots, not a video stream. This first slice makes remote Mac and optionally Windows screen snapshots *viewable on iPad* under explicit permission, not controllable there. It is not a general-purpose VNC/Screen Sharing replacement.

## Setup: an explicitly paired MacBook Air

1. Ensure the Windows PC, Mac and phone are reachable through your **private** Tailscale network. Do not enable Tailscale Funnel or forward the Jarvis ports publicly. The existing Jarvis Windows API must be configured with an authentication bearer token. Keep the Mac bind address on an explicitly assigned Tailscale IP or loopback, not `0.0.0.0`.
2. On the Mac, in its copy of this repository, generate a distinct secret (do **not** commit it):
   ```sh
   export JARVIS_MESH_NODE_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
   ```
   Keep that value available through your normal private password manager. A token printed/exported in a shell is secret; do not paste it into chat, logs or a GitHub issue.
3. On that Mac:
   ```sh
   python3 scripts/jarvis-mac-node.py \
     --device-id macbook --label "MacBook Air" \
     --bind "$(tailscale ip -4)" --port 8766 --allow-screen
   ```
   Without `--allow-screen`, the device reports status but **cannot** start a screen session. macOS System Settings → Privacy & Security → Screen & System Audio Recording must independently permit the Terminal/Python running the agent. The agent intentionally runs only while this process is running.
4. In the **Windows Jarvis service process environment**, set `JARVIS_MESH_MACBOOK_URL=http://<the Mac's Tailscale IP>:8766` and `JARVIS_MESH_MACBOOK_TOKEN=<that Mac's exact random token>`. Do not put the token into the iPhone app: the existing Jarvis API bearer token is used from iPhone to Windows. Restart the Windows Jarvis backend to read the new environment values. For a Mac mini use `--device-id macmini`, its own random secret and independent Windows `JARVIS_MESH_MACMINI_URL` / `JARVIS_MESH_MACMINI_TOKEN` variables.
5. In the iPhone/iPad app open **Mesh**, enable its separate switch, tap **Check connected nodes**, then **View Mac screen for 2 minutes**. The Mac must answer with an exact device ID, supported protocol version, fresh timestamp and a real screen-session capability. Neither the phone nor the PC asserts a Mac is online just because it was configured. For a manually operated privacy shutdown, tap **Stop Mac screen** and quit the agent on the Mac.

Node URLs are read only from the Windows process environment, **not supplied by phone/API request input**, and are restricted to loopback, Tailscale IPv4 `100.64.0.0/10` over HTTP, or `*.ts.net` via HTTPS. Redirects, oversized responses, unexpected image types and wrong node IDs fail closed. A missing/unavailable node is displayed as such. You do not need jailbreak, macOS private APIs or proprietary hardware protocols.

## Optional view-only Windows screen

The Windows PC was initially exposed as a status/foreground-process node. The source now implements a **separately enabled, view-only primary Windows desktop screenshot** through the same authenticated Mesh broker, with no remote shell, keystrokes, mouse, clipboard or file transfer. It is off by default even if Mesh is enabled on your phone.

Enable only if Jarvis runs in your **interactive logged-in Windows user session**, rather than as a headless Windows service running in Session 0:

```powershell
$env:JARVIS_MESH_WINDOWS_SCREEN_ENABLED = '1'
# Start the normal authenticated Jarvis backend from this same user session.
```

The setting must be present in the Jarvis **backend process environment**, not just a different terminal. The Python backend dependency now includes Pillow's `ImageGrab`. On your iPhone/iPad, Mesh → Check connected nodes → **View host screen for 2 minutes** on **Jarvis Windows host**. The user tap creates a distinct 120-second session; a fixed-size JPEG image is captured in RAM at a capped resolution, no more than 4 MB per image and about one image every five seconds while foregrounded. Stop/leave Mesh or app background revokes the session, and the server expires it even if the phone disconnects.

If Windows desktop capture cannot access a real interactive screen, Jarvis reports **unavailable**, rather than showing a fabricated or stale image. The backend auth token must be configured; tokenless localhost and public forwarding do not authorize Mesh. Disable the environment setting and restart Jarvis to remove even the ability to enroll a screen session. No webcam or microphone activation is involved.

## Presence at any named place

On **Mesh → Presence anywhere**, enter a specific place such as **Melbourne Airport, Victoria**. The iPhone uses an explicit MapKit lookup. If several candidates remain, it asks for a more precise name instead of inventing a location. After the user taps **Establish remote presence**, the iPhone sends that resolved coordinate to the authenticated Windows service, which delegates to its existing four-source public awareness adapter:

- **Caltrans:** official California highway camera catalog. A listed image is a periodically published still unless a separately valid stream URL exists. **No integrated Melbourne traffic-camera API** is claimed. VicTraffic is a public information website, not proof its video streams are available.
- **Open-Meteo/CAMS:** coarse *modelled* air quality with model timestamp, global scope; not a local sensor.
- **NWS:** only supported US point weather warnings; a Melbourne lookup must report unsupported coverage.
- **USGS:** earthquake event observations, not every public safety event.
- **OSM/Overpass:** available community-mapped public facilities, not verified opening or universal completeness.

The interface shows individual source coverage/status, source notes and provider-published camera stills/streams only when supplied by the allowlisted camera catalog. These public camera stills are fetched for the iOS preview by the phone directly from the allowlisted HTTPS government media URL; they are not private Mac screen captures. Unsupported, stale, offline, rate-limited or empty results are **never** converted into "everything is safe". The source manifest `GET /mesh/public-sources` describes integrations, **not** live measurements. The phone's named place is resolved by Apple and the coordinate is shared only after the button tap with the configured Windows service and corresponding external providers; Reality Mesh itself does not store a new location history. The Mesh screen additionally exposes explicit **Watch aircraft • 3h** and **Watch USGS events • 3h** buttons *after* the named place has been resolved and observed. These reuse the existing authenticated, time-bounded `external_watches` scheduler, at 30-minute/15-minute intervals respectively, with visible per-watch stop controls. Enrolling a watch stores the **selected coordinate** in Jarvis's separate local external-watch ledger for three hours; this is a distinct, user-triggered step, not storage from the one-shot place query. Aircraft feeds may be incomplete; a changing aircraft count does not imply a specific flight change, and seismic event reporting is neither instant nor comprehensive. Other watch types (e.g. private CCTV, non-integrated Melbourne feeds) are not silently accepted. This view does not take control of an existing Mission merely from a place query.

## Safety / privacy acceptance

A completed source and CI build is distinct from deployed runtime acceptance. On your actual Macs and iPad, check separate Mac and iOS opt-ins, firewall/Tailscale reachability, macOS Screen Recording permission, private two-minute screenshot expiration, hidden content in screenshots, back-to-back session revocation, app background, network loss while stopping, independent node secrets, wrong ID/token, and offline/stale provider behavior. Windows/Tailscale bearer settings and actual remote display streaming need device tests. No MemoMind official SDK/protocol is fabricated.
