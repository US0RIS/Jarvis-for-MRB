# Jarvis for MRB

A personal agent designed to use Ray-Ban Meta glasses as an always-available voice/vision interface while the actual agent and tools run on trusted devices and services.

## Current milestone

Milestone 2 is now implemented. Jarvis can:

- accept ordinary-language commands
- check whether Minecraft is running
- launch Minecraft
- ensure Minecraft is running
- expose the agent through a persistent local HTTP service
- automatically start that local service from the terminal client
- optionally register the service to start when you log into Windows

Examples:

```text
Open Minecraft.
Is Minecraft running?
Make sure Minecraft is running.
```

The current natural-language router is deliberately deterministic. The execution boundary is already separated from the planner, so a model-based planner can be added without giving the model unrestricted shell access.

## Architecture

```text
Ray-Ban Meta
    |
    v
iPhone client
    |
    v
Jarvis agent/gateway ---- Gmail / Calendar / Web / other services
    |
    v
Windows PC agent ---- apps / files / local automation
```

For the current milestone, the Jarvis service is bound only to `127.0.0.1:8765`, so it is not exposed to the LAN or Internet.

## Safety model

Jarvis uses explicit tools rather than handing an LLM unrestricted shell access. Tool permissions will be configurable. Destructive, security-sensitive, financial, and other high-impact operations should require stronger confirmation by default.

## Requirements

- Windows 10/11 for the PC-control milestone
- Python 3.12+

## Install or update

From the repository directory:

```cmd
git pull
py -3.14 -m pip install -e .
```

Python 3.12+ is supported. If `py -3.14` is unavailable, use your installed Python 3.12+ executable instead.

## Run Jarvis without relying on PATH

```cmd
py -3.14 -m jarvis_mrb.cli
```

Or double-click/run:

```cmd
run_jarvis.cmd
```

Then type commands naturally:

```text
jarvis> Open Minecraft
jarvis> Is Minecraft running?
jarvis> Make sure Minecraft is running
```

The terminal automatically starts the background Jarvis service if it is not already running.

## Start Jarvis automatically with Windows

Run once:

```cmd
py -3.14 -m jarvis_mrb.startup
```

That registers a Windows Scheduled Task named `JarvisForMRB` which starts the local Jarvis service at logon.

## Local API

Health check:

```text
GET http://127.0.0.1:8765/health
```

Natural-language command:

```text
POST http://127.0.0.1:8765/command
Content-Type: application/json

{"text":"Open Minecraft"}
```

## Repository layout

```text
jarvis_mrb/
  agent.py        natural-language planner/router
  cli.py          terminal client
  service.py      persistent local API service
  startup.py      Windows startup registration
  tools/
    pc.py         controlled Windows actions
run_jarvis.cmd    PATH-independent Windows launcher
```

## Next milestones

1. Add model-driven tool selection over the existing explicit tool boundary.
2. Add Gmail and Contacts tools with configurable confirmation policy.
3. Add persistent/conditional jobs such as “make sure Minecraft is open when I get home.”
4. Add an iPhone client and secure remote transport.
5. Integrate Ray-Ban Meta through Meta's Wearables Device Access Toolkit.
6. Add a local `Jarvis` wake word.
