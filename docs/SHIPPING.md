# Horus 0.14 distribution and Callless deployment

## Windows .exe

The [Windows Installer workflow](https://github.com/US0RIS/Jarvis-for-MRB/actions/workflows/windows-installer.yml)
runs on `main` and on manual dispatch. It builds a PyInstaller
single-folder runtime and wraps it with Inno Setup into
**`HorusSetup-0.14.0.exe`**, uploaded inside the **HorusSetup-Windows**
GitHub Actions artifact ZIP. The installer includes Python and backend
dependencies. The user doesn't need Python, pip, or a terminal.

The installer is **unsigned** (Windows SmartScreen may warn), per-user,
and offers opt-in start-at-sign-in. It opens a native Horus Setup screen
with inference provider/model/API key settings, optional LAN access, and
Callless access. Uninstalling the program does not delete the user's
local Horus memory/configuration or saved OS credentials.

The GitHub workflow runs `Horus.exe --self-test` before packaging. This
verifies that the frozen executable imports the backend. It is **not**
a guarantee that every hardware integration, Ollama, WSL TTS, database
migration or permission requirement works on all Windows PCs.
The bundle does not install Ollama, download models, provision OAuth
providers, set up a public TLS domain, or ship an iOS app.

## BYOK

Select **Local Ollama**, **OpenAI**, **Anthropic** or **OpenRouter** in
Horus Setup. Enter a provider-supported model ID and an API key for
hosted inference. The backend uses the provider for ordinary conversation
and tool planning while retaining deterministic local action confirmation.
The initial hosted path may return an entire answer per request, rather
than token-by-token playback; local Ollama retains normal streaming.

Secrets are stored via Python `keyring` in Windows Credential Manager,
not in `inference.json`; hosted prompts and conversation context leave
the user's PC for their selected provider. Horus does not automatically
track provider-side spending. If a model is unsupported or the provider's
API balance is exhausted, the user sees a provider error, not a silent
switch to a different provider. Remote setting of API keys requires TLS
(HTTPS); enter keys on the installed Windows UI when using LAN HTTP.

> **Future Callless changes:** See [Callless product and systems design](CALLLESS_DESIGN.md) for directed permissions, calendar-driven availability, held calls, screening, bypass, urgency, recording, non-user fallback and native calling. These are proposed improvements—not part of this 0.14 shipping checklist.

## Callless self-hosted hub

The same Horus backend now hosts **`/callless/`**, a responsive web
client with separate user handles/passwords, one-use 15-minute pairing
codes, approved contacts, blocking, and availability **Closed / Ask first /
Open**. The default is Closed. A contact is reachable only while
their live WebSocket is connected and their status permits it.

To connect two people:

1. Run the Horus hub at one shared hostname reachable by both devices.
2. **Outside localhost, terminate TLS at a trusted reverse proxy**:
   serve both `https://HOST/callless/` and WebSockets
   `wss://HOST/callless/v1/socket`. Do not expose the root
   Horus machine-admin API publicly merely to host Callless: isolate
   the Callless routes on the proxy or run a dedicated restricted hub.
3. Each user visits **the same hub URL**, registers an account and
   exchanges one approved invitation code. They set Open or Ask first.
4. The caller presses Connect. Callless confirms the contact permission
   and presence, then establishes a WebRTC DTLS-SRTP peer-media session
   via signaling. The browser recipient must press **Join**, even when
   Open, before the microphone activates due browser permission rules.
5. Disconnect ends the session. Closing or blocking terminates active
   sessions. The Callless database stores identities, salted password
   hashes, expiring token hashes, invitation hashes, contact grants and
   status; not SDP, ICE candidates or microphone recordings.

For NAT traversal, the default public STUN server may be insufficient.
Configure a TURN relay using `CALLLESS_ICE_SERVERS_JSON` as a JSON
array of `RTCIceServer` objects, e.g.:

```text
CALLLESS_ICE_SERVERS_JSON=[{"urls":"turn:turn.example.org:3478","username":"your_user","credential":"your_credential"}]
```

TURN credentials are revealed to authenticated Callless participants as
needed for WebRTC. Rotate them, scope them and use short-lived TURN
credentials for a production public service. Do not expose the main
Horus backend admin routes, unencrypted model API keys or a raw
`0.0.0.0:8765` interface on the public Internet.

### Capability boundaries

This is an operational **single-hub prototype**, not a global Horus
identity federation, subscription-hosted platform, or native iPhone
calling system. It has no APNs incoming-call push, CallKit,
background wakeup, automatic recipient microphone activation, device
handoff, multi-party mixing, or managed TURN. A browser tab must remain
open; shared WebRTC audio may need explicit playback approval.
There is no independent cryptographic identity verification beyond
authenticated hub signaling; do not promise interception resistance
against an untrusted hub operator.

iPhone Settings now has a **Callless hub URL** and opens the web app.
`get me to alex` on iPhone opens the Callless page with that person
selected; the user confirms Connect in the browser. Browser audio
only works under HTTPS outside localhost.

## Security / release checklist

- [x] Self-contained Windows installer build workflow and frozen import smoke test
- [x] BYOK credentials stored via system credential manager, provider allowlist
- [x] Callless default-Closed identity, mutual contacts, block and status
- [x] Signaling sessions restrict participants; browser voice requires user gesture
- [x] Account APIs require HTTPS except loopback
- [ ] Code-sign and notarize/publish trusted binaries
- [ ] Independent security audit of public signaling, token/session handling
- [ ] Deploy hosted TLS Callless hub, multi-process shared presence, TURN
- [ ] Native iOS CallKit/APNs background delivery and permission acceptance
- [ ] End-to-end two-device and Windows clean-machine acceptance testing
