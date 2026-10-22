# Horus

Horus is a **local-first assistant** with a native Windows **Mission Control**, an optional iPhone voice client, local or BYOK model inference, and a prototype Callless network.

**The implementation has outgrown the shipped product.** Use the [capability status ledger](docs/CAPABILITIES.md) to distinguish source code, CI validation, physical-device testing and release. The [docs index](docs/INDEX.md) contains the full technical history.

## Windows quick start

1. Open the [Windows Installer workflow](https://github.com/US0RIS/Jarvis-for-MRB/actions/workflows/windows-installer.yml), choose a successful run for the desired commit, and download **HorusSetup-Windows**.
2. Extract the artifact ZIP and run `HorusSetup-0.15.0.exe`. It is currently **unsigned**. The bundle includes Python but does not install AI models, service accounts or hosted networking.
3. Open **Horus Mission Control**. Use **Settings** for Ollama or BYOK OpenAI/Anthropic/OpenRouter, **Conversation** for chat, **Awareness** for real watch/alert/memory status, and **Control** for the private phone connection. See [Mission Control](docs/WINDOWS_MISSION_CONTROL.md).

For development, the legacy `setup_horus.cmd` remains available and requires a compatible local Python installation.

## iPhone and wearable interfaces

Open `ios/JarvisIOS.xcodeproj` in Xcode and sign to install on a physical iPhone. The *Talk to Horus* App Shortcut can be mapped to the iPhone Action Button on supported models. **Push-to-talk is the default**; optional always-listening mode is separate. AirPods/Bluetooth audio can work where the OS permits it. Meta Ray-Bans are optional, not a baseline requirement. See the [iOS guide](ios/README.md).

A simulator build is not a device-tested or App Store release; ordinary mobile conversation still relies on the backend for many features.

## Callless is an early prototype

The self-hosted `/callless/` browser client has accounts, mutually approved contacts, Open/Ask/Closed presence and WebRTC signaling. The recipient currently needs a live browser tab and must tap **Join** to activate audio. Real remote use requires HTTPS/WSS and frequently TURN. **Do not expose the main Horus PC/admin API to the public internet.** Native CallKit/PushKit delivery, one-way permissions, screening, calendar/bypass logic and non-user fallback are **not shipped**.

[Current deployment notes](docs/SHIPPING.md) · [Next-generation Callless design](docs/CALLLESS_DESIGN.md)

## Developer checks

```bash
python -m pip install -e .
python -m compileall -q jarvis_mrb tests
python -m unittest discover -s tests -v
```

CI workflows: [Windows installer](.github/workflows/windows-installer.yml) · [Agency tests](.github/workflows/agency-ci.yml) · [iOS tests](.github/workflows/memomind-ios.yml).

Secrets for hosted model calls use the OS credential store, and prompts may be sent to the selected model provider. Installing Horus should not silently enable ambient microphones, recording, physical actuators or external side effects.

## Where the documentation went

- [Documentation index](docs/INDEX.md) — technical guides and design history.
- [Capabilities](docs/CAPABILITIES.md) — implemented versus tested versus released.
- [Short future roadmap](future.md) — fewer than 100 lines.
- [Housekeeping](docs/HORUS_HOUSEKEEPING.md) — staged scope reduction.
- [Original long README](docs/archive/README_LEGACY_2026_10.md) and [original idea backlog](docs/archive/FUTURE_IDEAS_2026_10.md) — preserved verbatim as dated historical records.

Internal `jarvis_mrb`, `JARVIS_*` names and stored data paths are kept for compatibility despite public **Horus** branding.
