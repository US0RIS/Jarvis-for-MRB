# Jarvis iOS client

`JarvisIOS.xcodeproj` is a native SwiftUI iPhone app. It connects to the Jarvis backend, supports text and voice commands, speaks responses over the active iOS audio route, fires a `home_arrival` event from a Core Location geofence, and integrates Meta's Wearables Device Access Toolkit for registration, camera permission, and live Ray-Ban camera preview.

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

## Voice

**Push to Talk** records a command and sends it to Jarvis. **Jarvis wake** is an initial foreground prototype: while enabled and the app remains active, speech recognition listens for the word `Jarvis` followed by a command.

Audio uses iOS's active route. When the Ray-Bans are selected as the Bluetooth audio device, speech input/output can route through the glasses microphone and speakers.

The foreground speech recognizer is not the final low-power always-on wake-word implementation. A dedicated local keyword spotter is a later step.

## Home arrival

Set your home latitude, longitude, and radius under Settings, then tap **Enable Home Arrival Automation**. iOS region monitoring posts:

```json
{"event":"home_arrival"}
```

to the Jarvis backend. This completes commands such as:

```text
When I get home, make sure Minecraft is running.
```

## Meta Ray-Ban setup

The app configures Meta Wearables DAT with the development `MetaAppID` of `0` and URL scheme `jarvismrb://`.

In the app:

1. Tap **Register**. Meta AI opens to authorize the integration.
2. Return to Jarvis after the callback.
3. Tap **Camera Access** and approve camera permission in Meta AI.
4. Tap **Start Camera** to create a device session and display the live glasses camera feed.

The app uses Meta's documented `Wearables`, `AutoDeviceSelector`, `DeviceSession`, and `MWDATCamera` APIs.

## Current architecture

```text
Ray-Ban Meta camera/audio
        |
        v
Jarvis iOS client
  - Meta DAT camera
  - iOS Bluetooth audio
  - speech recognition/TTS
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
