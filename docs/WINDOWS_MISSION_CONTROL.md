# Horus Mission Control — native Windows desktop

The Windows interface is now a Qt desktop app, not a Tkinter setup dialog.
The iPhone/AirPods remain the primary wearable voice experience.

## Workspace

- **Conversation** sends real authenticated `/command` requests with a stable
  desktop session. Suggested prompts are genuine commands, not demo replies.
- **Awareness** reads `/health`, `/proactive/watches`,
  `/proactive/ledger` and `/memory/objects`. Backend outage/endpoint
  failures show as unavailable, rather than fabricated monitoring status.
- **Control** starts the Horus service, restarts only the current install's
  `--service` process, enables local-network access on explicit confirmation,
  and lets you copy the LAN URL and API token to the iPhone.
- **Settings** configure local Ollama or BYOK OpenAI, Anthropic and OpenRouter,
  with provider/model validation. Credentials are written to Windows
  Credential Manager and never displayed in the activity dashboard.

## Safety and scope

Enabling LAN binds the PC admin API on network interfaces: only do this on a
trusted private network. Never port-forward 8765 or put it on the public
internet. HTTP traffic on the LAN is unencrypted. API keys must be entered
in the Windows app rather than sent over HTTP from the phone. Clipboard tokens
are sensitive.

No tracking, sensor feeds, watches, companion connections or notifications are
simulated. The status view is read-only. Callless remains a separate browser
prototype; the iPhone app is separately built with Xcode.

## Build and verification

Windows installation from GitHub Actions produces `HorusSetup-0.15.0.exe`.
PySide6 is bundled via PyInstaller. The workflow runs:

1. Native UI source contract checks.
2. A source-run Windows Qt offscreen smoke test.
3. PyInstaller frozen `Horus.exe --self-test`, creating and switching
   through all four genuine Qt pages offscreen.
4. Installer packaging and checksum.

Local developer mode:

    python -m pip install -e .
    python packaging/horus_desktop.py

`--self-test` requires a Qt environment. It does not contact an AI service,
enable LAN or initiate a microphone session.

Current limitations: signed distribution and clean-machine acceptance are
outstanding; live model, Windows DPI/font rendering, real iPhone and AirPods,
and background automation must be tested on actual hardware.
