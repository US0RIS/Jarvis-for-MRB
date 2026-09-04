# Jarvis for MRB

A personal agent designed to use Ray-Ban Meta glasses as an always-available voice/vision interface while the actual agent and tools run on trusted devices and services.

## Milestone 6

The backend and first native iPhone/glasses client now exist in the repository.

Backend capabilities:

- local Ollama planner (`qwen3.8:27b` by default), with thinking explicitly disabled
- deterministic fast paths for routine commands
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
- SwiftUI text command interface
- push-to-talk speech recognition
- spoken responses over the active iOS audio route
- foreground `Jarvis` wake-word prototype
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
py -3.14 -m jarvis_mrb.cli
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

Restart the Jarvis service after running it. Do **not** forward port `8765` from your router to the public Internet. For away-from-home access, use a private tunnel such as Tailscale.

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

Speech input/output uses iOS Bluetooth audio. When the Ray-Bans are the active audio route, Jarvis can use the glasses microphone and speakers.

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
  microphone/speakers via iOS Bluetooth
        |
        v
Native Jarvis iPhone app
  voice / wake prototype / geofence
        |
        v
Authenticated Jarvis API
        |
        +-- Windows PC tools
        +-- Opera tabs
        +-- Gmail / Contacts / Calendar
        +-- persistent jobs
        +-- local Qwen planner
```

## Remaining major work

1. Build/sign/test the Xcode project on a physical iPhone and fix any device-specific SDK issues.
2. Replace foreground speech-recognition wake detection with a low-latency local keyword spotter for `Jarvis`.
3. Add vision requests so camera frames/photos can be sent to a multimodal model when a command needs visual context.
4. Add Tailscale/private remote connectivity for away-from-home use.
5. Add durable conversational memory/context and reliability hardening for all-day use.
