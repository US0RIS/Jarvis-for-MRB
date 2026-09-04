# Jarvis iOS client

`JarvisIOS.xcodeproj` is a native SwiftUI iPhone app. It connects to the Jarvis backend, supports text and voice commands, speaks responses, fires a `home_arrival` event from a Core Location geofence, and integrates Meta's Wearables Device Access Toolkit for registration, camera permission, and live Ray-Ban camera preview.

## Requirements

- macOS with Xcode
- iPhone running a current iOS release (deployment target is iOS 17+)
- Meta AI app on the iPhone
- compatible Meta AI glasses paired to Meta AI
- Developer Mode enabled for the glasses
- Apple developer signing team selected in Xcode

The Xcode project includes Meta Wearables DAT through Swift Package Manager:

- package: `https://github.com/facebook/meta-wearables-dat-ios`
- minimum version: `0.9.0`
- products: `MWDATCore`, `MWDATCamera`

## Open the project

```text
ios/JarvisIOS.xcodeproj
```

On first open, allow Xcode to resolve Swift packages. Select the `JarvisIOS` target, choose your Apple development team under **Signing & Capabilities**, connect your iPhone, and run the app on the physical phone.

## Connect the phone to the Windows Jarvis service

On the Windows PC, after updating/installing the Python package, run:

```powershell
py -3.14 -m jarvis_mrb.remote_setup
```

This creates `%APPDATA%\JarvisForMRB\server.json`, generates a random bearer token, and configures Jarvis to listen on the private network. Restart the Jarvis service afterward.

In the iPhone app's Settings screen enter:

- **Base URL:** one of the private URLs printed by `remote_setup`, such as `http://192.168.1.50:8765`
- **API token:** the generated token

Do not forward port `8765` from the router to the public Internet. For access away from home, use a private tunnel such as Tailscale and point the app at the PC's private tunnel address.

## Hands-free voice

The app has two voice paths:

- **Push to Talk** for explicit one-shot commands
- **Hands-free Jarvis** for a continuous `Jarvis` interaction loop

The hands-free path configures an iOS `playAndRecord` / `voiceChat` session and explicitly prefers an available Bluetooth HFP microphone. If the Ray-Bans expose an HFP input, Jarvis selects it instead of assuming the system has already chosen the glasses. iOS then routes playback to the matching Bluetooth hands-free output.

The main screen shows the actual audio route. With the glasses working as the voice terminal, it should identify the Ray-Ban / Meta Bluetooth route rather than the iPhone microphone.

Try either form:

```text
Jarvis, open Spotify.
```

or:

```text
Jarvis.
```

After the second form, Jarvis says `Yes?` and treats the next utterance as the command.

The loop waits for a short period of transcript stability before submitting a command, stops recognition while Jarvis speaks so the TTS cannot trigger itself, and automatically restarts an Apple Speech recognition task when it naturally ends.

The app has the `audio` background mode enabled and keeps its duplex audio session active while hands-free mode is running. Physical-device testing is still required to establish how reliably the current Speech-framework implementation survives screen lock, interruptions, and long sessions on the target iPhone/Ray-Ban combination.

This is not yet a dedicated low-power keyword spotter. For truly all-day operation, the next voice-specific upgrade would be a local keyword detector for `Jarvis` rather than continuously transcribing audio with the Speech framework.

## Home arrival

Set your home latitude, longitude, and radius under Settings, then tap **Enable Home Arrival Automation**. iOS region monitoring posts:

```json
{"event":"home_arrival"}
```

to the Jarvis backend. This completes commands such as:

```text
When I get home, make sure Minecraft is running.
```

For that event to reach the PC while the phone is away from the home LAN, configure a private remote path such as Tailscale; do not expose the Jarvis port directly to the Internet.

## Meta Ray-Ban setup

The app configures Meta Wearables DAT with the development `MetaAppID` of `0` and URL scheme `jarvismrb://`.

In the app:

1. Tap **Register**. Meta AI opens to authorize the integration.
2. Return to Jarvis after the callback.
3. Tap **Camera Access** and approve camera permission in Meta AI.
4. Wait for **DAT eligible: Yes**.
5. Tap **Start Camera** to create a device session and display the live glasses camera feed.

The app keeps one `AutoDeviceSelector` alive from initialization so device eligibility is populated before camera-session creation. This avoids the `noEligibleDevice` race that occurs when a selector is created immediately before `createSession`. Camera stream listener tokens are retained until the stream is stopped.

## Current architecture

```text
Ray-Ban Meta
  - Meta DAT camera
  - Bluetooth HFP microphone/speakers
        |
        v
Jarvis iOS client
  - hands-free speech recognition/TTS
  - live camera
  - home geofence
        |
        v
Authenticated Jarvis API
        |
        +-- Windows tools
        +-- Opera tabs
        +-- Gmail / Contacts / Calendar
        +-- persistent jobs
        +-- local Ollama planner
```
