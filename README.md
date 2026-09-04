# Jarvis for MRB

A personal agent designed to use Ray-Ban Meta glasses as an always-available voice/vision interface while the actual agent and tools run on trusted devices and services.

## Current milestone

The first milestone deliberately does **not** depend on the glasses. It proves the action layer first:

- run Jarvis from a terminal
- check whether Minecraft is running on Windows
- launch Minecraft
- keep tool execution explicit and inspectable

Once this works, the planned progression is:

1. Add model-driven tool selection.
2. Add Gmail/Calendar and other service tools.
3. Add persistent/conditional commands such as “make sure Minecraft is open when I get home.”
4. Add an iPhone client.
5. Integrate Ray-Ban Meta through Meta's Wearables Device Access Toolkit.
6. Add a local `Jarvis` wake word.

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

The PC is a tool Jarvis can control, not the single point of failure for the entire assistant.

## Safety model

Jarvis uses explicit tools rather than handing an LLM unrestricted shell access. Tool permissions will be configurable. Destructive, security-sensitive, financial, and other high-impact operations should require stronger confirmation by default.

## Requirements

- Windows 10/11 for the PC-control milestone
- Python 3.12+

## Quick start

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
jarvis
```

Then try:

```text
jarvis> status minecraft
jarvis> open minecraft
jarvis> quit
```

`open minecraft` attempts several normal Windows launch paths, including the `minecraft:` URI and the Microsoft Store app launcher.

## Repository layout

```text
jarvis_mrb/
  cli.py          interactive terminal
  tools/
    pc.py         controlled Windows actions
```

## Near-term goal

The next functional checkpoint is:

> “Jarvis, open Minecraft.”

Jarvis should translate that request into one explicit tool invocation, execute it on the PC, and report success or failure. The glasses are integrated only after this path is reliable.
