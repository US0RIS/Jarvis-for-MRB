# Release acceptance runbook (C00–C22)

This runbook is how the real system is deployed and tested against `criteria.md`.
Evidence goes through `jarvis-release-gate`; see `docs/RELEASE_EVIDENCE.md`.
**Terminal commands prepare and inspect a test. They never perform the behavior under test.**
Every behavior under test happens through the iPhone app or voice.

## 0. One-time prerequisites (the user)

| Need | Why | Gate |
|---|---|---|
| Paid Apple Developer Program team and an APNs `.p8` key (Key ID, Team ID) | Closed-app push requires the `aps-environment` entitlement; Personal Team signing cannot carry it | C09, C18, C21 |
| A Mac running `scripts/jarvis-mac-node.py` over Tailscale (see `REALITY_MESH.md`) | C14 requires at least one real configured Mac; C13 targets a paired workstation | C00, C13, C14 |
| One Apple Home light in the iPhone's Home app | Presence acceptance | C19 |
| Groq API key (entered only in iPhone Settings → Cloud Intelligence / Groq) | Real Groq tier | C12 |
| Google authorized on the backend (`jarvis-google-auth`), plus Serper if web search is claimed | Private context | C02–C10 |
| At least three lawful public camera/media sources you may view: two publishers, two regions, including one direct public HTTPS JPEG/MJPEG/HLS URL | C16 campaign | C16 |

## 1. Windows backend environment (service process)

Set these in the environment of the interactive Windows user session that runs `jarvis-service`,
then restart the service. Secrets go in the environment, never in the repository.

```powershell
$env:JARVIS_API_TOKEN = '<existing private bearer>'
$env:JARVIS_WORLD_ARMOR_ENABLED = '1'
$env:JARVIS_WORLD_ARMOR_FULL_ENABLED = '1'          # Presence (C19)
$env:JARVIS_WORLD_ARMOR_CAMERAS_ENABLED = '1'       # C16
$env:JARVIS_WORLD_ARMOR_PLATFORM_ENABLED = '1'      # C16/C17
$env:JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED = '1'      # OpenSky movement (C17), only if claimed
$env:JARVIS_WORLD_ARMOR_WATCHES_ENABLED = '1'       # standing watches (C09/C18/C21)
$env:JARVIS_WORLD_ARMOR_LIVE_ENABLED = '1'
$env:JARVIS_WORLD_ARMOR_LIVE_AUTOSTART = '0'        # use the watchdog (C18 Test B)
$env:JARVIS_WORLD_ARMOR_PUSH_ENABLED = '1'          # APNs (C18)
$env:JARVIS_APNS_TEAM_ID = '<team>'; $env:JARVIS_APNS_KEY_ID = '<key id>'
$env:JARVIS_APNS_BUNDLE_ID = 'com.us0ris.JarvisMRB'; $env:JARVIS_APNS_KEY_FILE = 'C:\secure\AuthKey.p8'
$env:JARVIS_APNS_ENVIRONMENT = 'development'        # matches the development-signed build
$env:JARVIS_CONDUCTOR_ENABLED = '1'                 # C13
$env:JARVIS_MESH_WINDOWS_APP_ENABLED = '1'          # C13/C14 Windows app buttons
$env:JARVIS_REALITY_GRAPH_MISSIONS_ENABLED = '1'    # C15
$env:JARVIS_MESH_MACBOOK_URL = 'http://100.x.y.z:8766'; $env:JARVIS_MESH_MACBOOK_TOKEN = '<mac node token>'
```

In a second terminal on the same host and in the same environment, run `jarvis-world-live-watchdog`.

## 2. Deploy and freeze (C00)

```powershell
cd Jarvis-for-MRB; git fetch origin; git checkout <release branch>; git pull
py -3.14 -m pip install -e .
jarvis-world-prepare
# restart jarvis-service
jarvis-release-gate validate        # must print ok: true
jarvis-release-gate freeze          # records the candidate SHA
```

Build the iOS app from the **same commit** on the Mac: Xcode → JarvisIOS → your paid team → Run to the physical iPhone.
The Xcode build log must show `Stamped JarvisBuildSHA=<sha>`, with no `-dirty` suffix.
iPhone → Settings → Jarvis Server shows **App build SHA**, which must match.

```powershell
jarvis-release-gate start C00 --user-entry-surface "iPhone app" --literal-user-request "n/a (deployment)" `
  --devices "Windows host; iPhone <model>; MacBook Air node" --real-services-or-providers "none" `
  --expected-observable-result "all components report the frozen SHA"
# open Jarvis on the iPhone (any request), then:
jarvis-release-gate evaluate <session>
jarvis-release-gate finalize <session> --result PASS|FAIL ...
```

Any later code change requires a new `validate` → `freeze` → C00, and every other gate is rerun on the new SHA.

## 3. Gate sessions

For each gate: `start` → the user does the listed steps through the app or voice → `evaluate` → `finalize`.
Where an Agency receipt is required, run the matching `jarvis-agency-real-gate` session **inside** the C session
(see `AGENCY_ACCEPTANCE.md`).

| Gate | User steps (normal Jarvis use only) | Machine checks |
|---|---|---|
| C02 | Ask: a clock/arithmetic question; a casual question; "What's on my calendar tomorrow?"; "What can you do right now?" | common |
| C03 | Have an entity present in Calendar, Gmail and a stated fact. "Remember that Project X's owner is A." Receive a conflicting email. Restart the service. "What do you know about Project X?" "Actually, Project X's owner is B." | common (+ record artifacts) |
| C04 | "My goal is …" → confirm. Let one step verify and one wait for approval. Restart the service; reopen the phone; "agency status" | A1 |
| C05 | A goal needing two distinct writes (for example two calendar holds, or a light on after a calendar hold) | A2 |
| C06 | A plan with a safe read, an approved write ("approve agency …") and a denied write ("deny agency …") | A3, A11 |
| C07 | A verified calendar write; then a failure (revoke Google, or a target that is unreachable); "did that work?" | A4 |
| C08 | (A) change a real fact mid-plan; (B) a goal that waits on a real condition (for example air quality or a light state) until it changes | A5, A6, dormant/wake events |
| C09 | During a controlled window: ≥5 low-value changes, one high-value event for an enrolled goal, delivered twice; the phone locked | A8 (+ push record in C18) |
| C10 | Before a real meeting: "Anything I need to know before I go in?" | common (+ artifacts) |
| C11 | A real ambiguous research decision; two counterfactual branches; an objective needing a missing capability | A7, A9 |
| C12 | Deterministic, ordinary and hard requests; a request containing `api_key=…`; airplane-mode the Mac/Windows internet or revoke the key once; a cloud answer proposing a protected action | tiers, Groq result, fallback, redaction, protected proposal |
| C13 | "Open Safari on my MacBook Air" (enabled voice switch) or Mesh → Review exact workstation mission → confirm; replay/expired attempt; ask for a shell command | common (+ artifacts) |
| C14 | Mesh: check nodes; 2-minute screen view; change the Mac screen; stop; retry after expiry; unplug the Mac network and replug | common (+ artifacts) |
| C15 | Mesh → place mission with ≥2 sources, a change over time; query it | common (+ artifacts) |
| C16 | Enrol ≥3 sources (2 publishers, 2 regions, one arbitrary HTTPS media URL); observe each; pause/stop one; one fails or goes stale; forget one | sources/publishers/regions/failure/pause checks |
| C17 | Ask Jarvis about conditions at a place (NWS/air/USGS) and aircraft nearby; one provider unavailable | per-provider real request + gap |
| C18 | Enable push in the app; lock the phone; trigger a warning (an Agency approval request); duplicate it; disable/re-enable push; `taskkill` the live child; drop the network; restart the service | push sent, dedup, token handling, watchdog restart, service restart, no duplicate writes |
| C19 | "Turn on the desk lamp" (confirm) or the Presence panel; look at the lamp; try again after the grant is spent; unplug the lamp and try | grant bound, readback, later refusal, failure case (+ `--attest`) |
| C20 | Run the live probes on the deployed build, plus revoke and stop during a collection | bearer, grant, private targets, disabled flag, node, redaction, no leakage |
| C21 | `jarvis-release-gate start C21`, then `jarvis-release-soak run --session <id>` for 24 h+ | soak checks |
| C22 | After the freeze, you choose one bounded objective and state it once; only approve, deny, answer value questions, perturb once, observe | Agency trace (+ `--attest`) |
