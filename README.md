# Jarvis for MRB

A personal agent designed to use Ray-Ban Meta glasses as an always-available voice/vision interface while the actual agent and tools run on trusted devices and services.

## Current milestone

Jarvis now uses the local Ollama model `qwen3.8:27b` as a planner with thinking disabled. Obvious low-risk commands bypass the model for low latency.

Current tools include:

- launch arbitrary Windows applications
- close applications
- check whether an application/process is running
- list running processes
- open URLs
- open local files/folders
- Minecraft-specific status/launch/ensure helpers
- Google Contacts lookup
- Gmail send preparation with explicit confirmation before sending

Examples:

```text
Open Spotify.
Is Discord running?
Close Spotify.
Open https://youtube.com
Email alex@example.com saying I can talk later. Do not use emojis.
```

For email, Jarvis prepares the message and asks for `confirm` before sending.

## Architecture

```text
Ray-Ban Meta
    |
    v
iPhone client
    |
    v
Jarvis agent/gateway ---- Gmail / Contacts / Calendar / Web
    |
    v
Windows PC agent ---- apps / files / local automation
```

The current Jarvis service is bound only to `127.0.0.1:8765`, so it is not exposed to the LAN or Internet.

## Safety model

Jarvis uses explicit tools rather than unrestricted shell access. Outbound email requires confirmation. More consequential actions will use stronger confirmation policies as additional tools are added.

## Requirements

- Windows 10/11
- Python 3.12+
- Ollama with `qwen3.8:27b` installed (or another model selected with `JARVIS_MODEL`)

## Install or update

```powershell
cd C:\Users\emmet\Jarvis-for-MRB
git pull
py -3.14 -m pip install -e .
```

Restart the old background service after pulling code changes:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen |
  Select-Object -ExpandProperty OwningProcess |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

Then run:

```powershell
py -3.14 -m jarvis_mrb.cli
```

## Model configuration

Default planner:

```text
qwen3.8:27b
```

Thinking is explicitly disabled for latency. The model is kept warm for 30 minutes by default.

To use another Ollama model:

```powershell
$env:JARVIS_MODEL="qwen3:32b"
```

## Gmail and Google Contacts setup

Jarvis uses Google's official OAuth APIs. Create a Google Cloud **Desktop OAuth client**, enable the **Gmail API** and **People API**, then save the downloaded OAuth client JSON here:

```text
%APPDATA%\JarvisForMRB\google_credentials.json
```

Alternatively set `JARVIS_GOOGLE_CREDENTIALS` to another JSON path.

Then run:

```powershell
py -3.14 -m jarvis_mrb.google_auth
```

A browser window will ask you to authorize Gmail send access and read-only Contacts access. The resulting token is stored under `%APPDATA%\JarvisForMRB`, outside the repository.

Test with:

```text
jarvis> gmail status
jarvis> Email alex@example.com saying I can talk later and do not use emojis
jarvis> confirm
```

## Windows startup

```powershell
py -3.14 -m jarvis_mrb.startup
```

That registers a Windows Scheduled Task named `JarvisForMRB` which starts the local service at logon.

## Next milestones

1. Persistent/conditional jobs such as “make sure Minecraft is open when I get home.”
2. Calendar and broader service integrations.
3. iPhone client and secure remote transport.
4. Ray-Ban Meta integration through Meta's Wearables Device Access Toolkit.
5. Local `Jarvis` wake word.
