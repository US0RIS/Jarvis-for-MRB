# Jarvis for MRB

A personal agent designed to use Ray-Ban Meta glasses as an always-available voice/vision interface while the actual agent and tools run on trusted devices and services.

## Milestone 5

Jarvis now has the main pre-glasses backend pieces in one service:

- local Ollama planner (`qwen3.8:27b` by default), with thinking explicitly disabled
- deterministic fast paths for routine commands
- Windows app/process control
- Opera/Chromium tab discovery, focus, open, status, and close via CDP
- Gmail send
- Google Contacts lookup
- Google Calendar read/create
- persistent scheduled jobs in SQLite
- event-triggered jobs such as `home_arrival`
- configurable permission classes
- authenticated remote API scaffolding for a future iPhone client

The model never receives unrestricted shell access. It chooses among explicit tools.

## Install/update

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
What is running?

Email alex@example.com saying I can talk later and do not use emojis
confirm

What's on my calendar this week?
Create a calendar event called Dentist tomorrow at 3 PM
confirm

At 8 PM open Spotify
When I get home, make sure Minecraft is running
List jobs
Cancel job 3

permissions
set external_write actions to auto
```

## Model

Default:

```text
qwen3.8:27b
```

Ollama requests include `think: false` and keep the model warm for 30 minutes by default. Routine commands bypass the LLM when possible.

Override:

```powershell
$env:JARVIS_MODEL="qwen3:32b"
```

## Opera browser control

Opera must be started with remote debugging enabled for Jarvis to control individual tabs.

Fully quit Opera, then run:

```powershell
py -3.14 -m jarvis_mrb.browser_setup
```

Test inside Jarvis:

```text
browser status
list tabs
close spotify
```

Jarvis checks browser tabs before native processes for ordinary commands such as `close spotify`.

## Google setup: Gmail, Contacts, Calendar

Enable these APIs in the Google Cloud project for your Desktop OAuth client:

- Gmail API
- People API
- Google Calendar API

Save the Desktop OAuth client JSON at:

```text
%APPDATA%\JarvisForMRB\google_credentials.json
```

Then run:

```powershell
py -3.14 -m jarvis_mrb.google_auth
```

Milestone 5 added Calendar scopes. If you authenticated an earlier version, run the auth command again; Jarvis will replace the old token if it lacks the required scopes.

By default, outbound email and calendar creation are `external_write` actions and require confirmation.

## Permission policy

Jarvis stores its local policy at:

```text
%APPDATA%\JarvisForMRB\permissions.json
```

Risk classes and defaults:

```text
read            auto
local_write     auto
external_write  confirm
destructive     confirm
security        confirm
```

Routine opening/closing of apps and browser tabs is classified as `local_write`. Sending email or creating Calendar events is `external_write`.

Examples:

```text
permissions
set external_write actions to auto
set destructive actions to deny
```

## Persistent jobs

Jobs are stored in:

```text
%APPDATA%\JarvisForMRB\jobs.sqlite3
```

Time jobs are checked by the persistent Jarvis service every second. Event jobs wait for an event posted to the service.

Example:

```text
When I get home, make sure Minecraft is running
```

This creates a `home_arrival` event job. The future iPhone client can fire that event when its geofence detects arrival.

For manual testing from PowerShell while the service is local and unauthenticated:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8765/event `
  -ContentType 'application/json' `
  -Body '{"event":"home_arrival"}'
```

## Remote API scaffold

Jarvis still binds to localhost by default:

```text
127.0.0.1:8765
```

To intentionally expose it on another interface, set both a bind host and an API token. Jarvis refuses a non-local bind without a token.

```powershell
$env:JARVIS_BIND_HOST="0.0.0.0"
$env:JARVIS_API_TOKEN="replace-with-a-long-random-secret"
py -3.14 -m jarvis_mrb.service
```

Clients then send:

```text
Authorization: Bearer <token>
```

Endpoints:

```text
GET  /health
POST /command   {"text":"Open Spotify"}
POST /event     {"event":"home_arrival"}
```

For actual remote use, put this behind a private tunnel such as Tailscale rather than forwarding port 8765 directly from the public Internet.

## Windows startup

```powershell
py -3.14 -m jarvis_mrb.startup
```

This registers `JarvisForMRB` to start at logon.

## Architecture

```text
Ray-Ban Meta
    |
    v
iPhone client / wake word / geofences
    |
    v
Jarvis API + planner + permissions + jobs
    |            |             |
    v            v             v
Windows PC    Google APIs    Browser CDP
```

## Remaining major milestones

1. Build/sign the iPhone client and connect it to `/command` and `/event`.
2. Add speech-to-text, text-to-speech, and low-latency streaming.
3. Integrate Ray-Ban Meta through Meta's Wearables Device Access Toolkit.
4. Add the phone-side `Jarvis` wake word.
5. Add vision/context/memory and harden reliability for all-day use.
