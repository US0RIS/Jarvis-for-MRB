# Jarvis for MRB

A personal agent designed to use Ray-Ban Meta glasses as an always-available voice/vision interface while the actual agent and tools run on trusted devices and services.

## Milestone 8

The backend, native iPhone client, Meta camera path, hands-free voice loop, and persistent short-term conversational memory now exist in the repository.

Backend capabilities:

- local Ollama planner (`qwen3.8:27b` by default), with thinking explicitly disabled
- deterministic fast paths for routine commands
- persistent per-session conversational history in SQLite
- the most recent 20 user/assistant messages are supplied to the planner on each non-trivial request
- contextual follow-ups such as `what about Friday?`, `close it`, or `email him that I'll be late`
- ordinary conversation when no tool is required
- Windows app/process control
- Opera/Chromium tab discovery, focus, open, status, and close via CDP
- Gmail send with confirmation policy
- Google Contacts lookup
- general Google Calendar queries and event creation
- persistent scheduled jobs in SQLite
- event-triggered jobs such as `home_arrival`
- configurable permission classes
- authenticated private-network API

Native iPhone client:

- standard `ios/JarvisIOS.xcodeproj`
- stable per-install conversation session ID so context survives app/backend restarts
- SwiftUI text command interface
- push-to-talk speech recognition
- spoken responses
- hands-free `Jarvis` interaction loop with silence-based end-of-command detection
- five-second post-response conversational listening window: follow-ups do not require saying `Jarvis` again
- longer confirmation follow-up window for protected actions
- extended dictation handling for email addresses, URLs, spelling, and long message bodies
- personal speech vocabulary/correction for `Dubeck`
- explicit Bluetooth HFP input selection so a connected Ray-Ban microphone is preferred over the iPhone microphone
- response playback over the matching Bluetooth hands-free route
- automatic speech-recognition restart when an Apple recognition task ends
- recovery from audio interruptions and iOS media-service resets
- Core Location home geofence that fires `home_arrival`
- Meta Wearables Device Access Toolkit 0.9+ via Swift Package Manager
- Meta AI registration and camera permission flows
- live Ray-Ban camera streaming and photo capture

The model never receives unrestricted shell access. It chooses among explicit tools.

## Update the Windows backend

```powershell
cd C:\Users\emmet\Jarvis-for-MRB
git pull
py -3.14 -m pip install -e .
```

After code updates, stop the old background service so the new code loads:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen |
  Select-Object -ExpandProperty OwningProcess |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

Then:

```powershell
py -3.14 -m jarvis_mrb.service
```

## Example commands

```text
Open Spotify
Close Spotify
Is YouTube open?
List tabs

Email alex@example.com saying I can talk later and do not use emojis
confirm

What was the most recent event on my calendar?
When was my last dentist appointment?
Create a calendar event called Dentist tomorrow at 3 PM
confirm

At 8 PM open Spotify
When I get home, make sure Minecraft is running
List jobs
```

Conversation context also supports sequences such as:

```text
What's on my calendar Friday?
What about Saturday?
Move back to Friday — which one is earliest?
```

or:

```text
Open Spotify.
[Jarvis responds]
Close it.
```

## Conversation memory

Every `/command` request may include a `session_id`. Jarvis stores conversation turns under that session in:

```text
%APPDATA%\JarvisForMRB\conversation.sqlite3
```

The iPhone creates one stable random session ID and reuses it. The backend retains up to 200 messages per session and sends the most recent 20 messages (at least ten full user/assistant turns in typical use) to Qwen when contextual reasoning is required.

Fast deterministic commands still bypass Qwen when no conversational resolution is needed. Commands with contextual pronouns such as `close it` deliberately fall through to Qwen so the recent history can resolve the target.

Background scheduled jobs do not share the live conversation session, so job execution cannot contaminate the user's dialogue history.

## Model

Default planner:

```text
qwen3.8:27b
```

Ollama requests include `think: false` and keep the model warm for 30 minutes by default. Routine commands bypass the LLM when possible.

## Google setup

Jarvis uses Gmail API, People API, and Google Calendar API through your Desktop OAuth client. Credentials and tokens live outside the repository under:

```text
%APPDATA%\JarvisForMRB
```

Authenticate with:

```powershell
py -3.14 -m jarvis_mrb.google_auth
```

Outbound email and Calendar writes are `external_write` actions and require confirmation by default.

## Opera browser control

Fully quit Opera, then run:

```powershell
py -3.14 -m jarvis_mrb.browser_setup
```

This starts Opera with Chromium DevTools enabled so Jarvis can work with individual browser tabs rather than killing the whole browser.

## Connect the iPhone

First configure a private-network API token on the Windows PC:

```powershell
py -3.14 -m jarvis_mrb.remote_setup
```

This writes `%APPDATA%\JarvisForMRB\server.json`, generates a random bearer token, and prints possible private LAN URLs for the iPhone.

Restart the Jarvis service after running it. Do **not** forward port `8765` from the router to the public Internet. For access away from home, use a private tunnel such as Tailscale and point the app at the PC's private tunnel address.

Then open on a Mac:

```text
ios/JarvisIOS.xcodeproj
```

Let Xcode resolve the Meta Wearables Swift package, select your Apple development team, connect your iPhone, and run the `JarvisIOS` target. Enter the server URL and API token in the app's Settings screen.

Detailed iOS instructions are in `ios/README.md`.

## Meta Ray-Ban integration

The iOS project uses Meta's official Wearables Device Access Toolkit and links:

```text
MWDATCore
MWDATCamera
```

The development configuration uses URL scheme `jarvismrb://` and Meta App ID `0`, which is the documented Developer Mode setup.

In the app:

1. Tap **Register** to authorize the integration through Meta AI.
2. Tap **Camera Access** to grant camera permission.
3. Tap **Start Camera** to begin a Ray-Ban device session and show the live camera feed.

The device selector is kept alive from app initialization so it can learn the active DAT device before a session is created. Stream listener tokens are retained for the lifetime of the stream.

## Hands-free voice

Enable the switch in **Voice & Commands**. Jarvis keeps a voice-recognition session active and prefers a connected Bluetooth HFP microphone. On an iPhone with the Ray-Bans available as an HFP device, that explicitly selects the glasses microphone; iOS then routes playback to the matching hands-free output.

Start a conversation with either:

```text
Jarvis, what's on my calendar Friday?
```

or:

```text
Jarvis.
```

Jarvis replies `Yes?`, then listens for the next utterance as the command.

After Jarvis finishes speaking any normal hands-free response, it immediately reopens recognition for five seconds. If the user starts speaking during that window, the utterance is treated as a conversational follow-up without another wake word. Each response opens a new five-second window, so conversation can continue naturally until the user pauses for more than five seconds; after that Jarvis returns to wake-word mode.

The deadline controls when follow-up speech must **start**. It does not truncate an utterance already in progress. Long dictation can also survive Apple Speech task finalization: Jarvis buffers the partial command, creates a new recognition task, and appends the continuation.

Protected actions remain conversational. A pending Gmail/Calendar/destructive action gets a longer confirmation window, and `confirm` or `cancel` works without repeating `Jarvis`.

The voice loop does not listen while Jarvis itself is speaking, preventing TTS from triggering the assistant. It restarts recognition tasks that terminate naturally and recreates the audio path after phone-call/Siri/media-service interruptions.

This still uses Apple's Speech framework as the wake detector. A dedicated low-power keyword spotter remains desirable for true all-day, system-assistant-like behavior.

## Home arrival automation

Create a job:

```text
When I get home, make sure Minecraft is running
```

Then configure your home geofence in the iPhone app. iOS posts the `home_arrival` event when the region is entered, and the persistent backend executes the matching job.

## Permission policy

Defaults:

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

Examples:

```text
permissions
set external_write actions to auto
set destructive actions to deny
```

## Architecture

```text
Ray-Ban Meta
  camera via Meta DAT
  microphone/speakers via Bluetooth HFP
        |
        v
Native Jarvis iPhone app
  hands-free voice / TTS / camera / geofence
  stable conversation session ID
        |
        v
Authenticated Jarvis API
        |
        +-- persistent conversation history
        +-- Windows PC tools
        +-- Opera tabs
        +-- Gmail / Contacts / Calendar
        +-- persistent jobs
        +-- local Qwen planner
```

## Remaining major work

1. Validate and tune the five-second conversational loop on the physical Ray-Bans, including screen-locked/background behavior and noisy-room thresholds.
2. Replace Speech-framework wake detection with a dedicated low-power local keyword spotter for `Jarvis` if all-day operation requires it.
3. Add vision requests so camera frames/photos can be sent to a multimodal model when a command needs visual context.
4. Add Tailscale/private remote connectivity for away-from-home use so voice and geofence events can reach the PC outside the LAN.
5. Add longer-term semantic memory beyond the current durable short-term conversation window.
