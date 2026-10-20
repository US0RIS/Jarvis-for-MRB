# Horus capabilities — evidence ledger

**Scope:** factual baseline for the repository; update after CI, device and public deployment acceptance. Source presence is not release. [Roadmap](../future.md) · [Shipping](SHIPPING.md).

| Capability | Source state | Verification boundary |
|---|---|---|
| Windows .exe installer | Implemented; GitHub packaging artifact generated | Unsigned; clean-machine acceptance outstanding |
| Windows desktop text chat | Implemented in installer | Live provider/clean-install acceptance outstanding |
| Local Ollama | Backend integrated | Optional local model and installation prerequisites |
| BYOK OpenAI / Anthropic / OpenRouter | Backend and settings implemented; targeted tests | Live provider/model compatibility and spend limits outstanding |
| iPhone push-to-talk / Action Button | Swift source and simulator build | Real iPhone permission/audio-route testing outstanding |
| AirPods / Bluetooth and Meta glasses | Optional integration surfaces | Device/OS restrictions and hardware testing |
| Callless hub | Single-hub accounts, mutual grants, presence and WebRTC prototype | Two-device live media and production security audit outstanding |
| Callless native calling | Not implemented | CallKit/PushKit/APNs device validation |
| Callless policy/screener/bypass/recording | Design only | [Callless design](CALLLESS_DESIGN.md) and gated implementation |
| World Armor / executive research subsystems | Significant experimental source | Independent production provider, sensor and real-action validation |
| Shadow Reality P06-005 (mission ETA what-if slice) | Read-only conditional scenario engine and private endpoints source-implemented; synthetic/unit and endpoint regressions added | Local arithmetic smoke passed; CI/regression verdict and live provider/device acceptance outstanding. No autonomous action or forecast. |
| Hosted identity, mobile-only Horus, global relay | Not released | Security, infrastructure, cost and distribution gates |

**Release stages:** proposed → source merged → isolated tests → CI green → real-device validated → deployed/released. No feature should skip a stage. The [legacy long README](archive/README_LEGACY_2026_10.md) is history, not release authority.
