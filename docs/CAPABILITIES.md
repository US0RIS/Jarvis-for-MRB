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
| Callless hub | Single-hub browser WebRTC prototype; [north star: ambient, permission-based conversational proximity](CALLLESS_DESIGN.md), **not** phone replacement | Actual near-instant headset audio, native OS compliance, two-device media and security acceptance outstanding |
| Callless native calling | Not implemented | CallKit/PushKit/APNs device validation |
| Callless policy/screener/bypass/recording | Design only | [Callless design](CALLLESS_DESIGN.md) and gated implementation |
| World Armor / executive research subsystems | Significant experimental source | Independent production provider, sensor and real-action validation |
| Shadow Reality P06-005 (mission ETA what-if slice) | Committed to main; conditional scenario engine and private endpoints | 8 new tests passed in 854-test Linux CI suite; iOS bridge validation and Windows installer packaging passed. Separate Windows full regression still running at latest check; live provider/device testing outstanding. No autonomous action or forecast. |
| Reality Rewind P06-006 (mission event-time replay slice) | Bounded as-of replay of retained, enrolled mission observations; read-only private endpoint and tests | Source merged and targeted test coverage; live physical sensor/provider acceptance outstanding. No continuous DVR, original ingestion-time history or place-wide timeline. |\n| Reality Diff P06-007 (reported fact changes slice) | [Read-only two-time-point, evidence-linked mission comparison](REALITY_DIFF_ASSERTIONS.md); private API and regression tests committed | CI verdict pending on latest commit. No continuously running diff, observed physical appearance/disappearance, provider authenticity or actual-device verification. |\n| World Assertions P06-008 (reported-state monitoring slice) | [Separate opt-in, stored typed predicates](REALITY_DIFF_ASSERTIONS.md), append-time/on-request evaluation, receipts and revocation, no actuators | CI verdict pending on latest commit. No background scheduler, autonomous repair/notification, real-world outcome verification or device acceptance. |
| Hosted identity, mobile-only Horus, global relay | Not released | Security, infrastructure, cost and distribution gates |

**Release stages:** proposed → source merged → isolated tests → CI green → real-device validated → deployed/released. No feature should skip a stage. The [legacy long README](archive/README_LEGACY_2026_10.md) is history, not release authority.
