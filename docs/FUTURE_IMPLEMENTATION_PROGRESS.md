# Implementation and acceptance status — October 2026

**Not a completion certificate.** `future.md` is a very large speculative
backlog, not a set of already-shipped features. This branch adds bounded,
executable slices. Never equate a passing Python test, simulator build,
documented architecture, or GitHub commit with functioning deployment on the
user's devices.

## Current feature work

| Feature | Branch implementation | Evidence still required |
|---|---|---|
| AirPods headset audio | iPhone AudioRouteManager explicitly prefers named AirPods, Meta or automatic, with deterministic built-in-mic fallback and a settings diagnostic | iOS physical microphone/output, interruption, reconnect and background-state testing; arbitrary AirPods renames cannot be identified reliably |
| Current public claim freshness | Deterministic pre-model check in normal and streaming chat; public-post contradictions trigger a stricter first-party verifier | Real official-source queries; universal per-claim evidence entailment, TTLs, image authenticity, complete false/true detection |\n| Official-source verifier | A bounded URL allowlist fetches primary HTML (not just snippets); reports only an official page's actual mention, never asserts an absent post is fake | Live source checks, broader issuer coverage, evidence-to-claim entailment and exact X-post authenticity |
| User Belief Model | Opt-in independent SQLite model for stated user beliefs, exposures, acknowledgments, operator-attested world observations, exact enrolled decisions and read-only divergence warnings | Actual independently verified world-fact adapter, end-to-end calendar/deadline linkage, real-world consent and intervention evaluation |
| VoiceStudio alternate TTS | Optional OpenAI-compatible VoiceStudio provider with discovery-based availability and explicit URL/model/voice selection | VoiceStudio installed on user PC, correct engine/profile, spoken quality and latency tests, AirPods physical playback |
| Gemma 4 planner | Real local Ollama benchmark command comparing candidate routing accuracy and measured token/TTFT latency | RTX 5080 measurements, multimodal test corpus, full Jarvis tool and context correctness, memory contention and deployment; **not promoted** |
| Capability evidence ledger | Strictly scoped local unit execution receipts, per-commit/fixture validity, voice-query and authenticated evidence status | Trusted physical/production evidence adapters; all hardware and live external scopes remain unverified |
| Shared interruption budget | Opt-in, process-memory-only 3-information-alerts/hour governor at the common proactive emitter. Warnings and urgent alerts bypass it | Human acceptance of rate and severity classification; default stays disabled |

## Activation

These are opt-in environment examples, not evidence the corresponding backend is installed.

### VoiceStudio

Run a separately installed trusted local VoiceStudio server. Point Jarvis to it
before starting its backend:

```text
JARVIS_TTS_PROVIDER=voicestudio
JARVIS_TTS_URL=http://127.0.0.1:3900
JARVIS_TTS_MODEL=tts-1
JARVIS_TTS_VOICE=alloy
```

A saved VoiceStudio voice-profile **ID** can replace `alloy`. For remotely
hosted VoiceStudio, a bearer token must travel over HTTPS (except loopback).
Jarvis never starts its Kokoro WSL process when VoiceStudio is selected.
VoiceStudio's discovery endpoint proves only that its local API responded;
model residency and valid WAV output are independently established by
synthesis, **not** by the “API reachable” label. Switch back by restoring
`JARVIS_TTS_PROVIDER=kokoro` and the existing Kokoro URL/model/voice settings.

### Gemma 4

```powershell
ollama pull gemma4:12b
python -m jarvis_mrb.model_bakeoff --models qwen3:8b gemma4:12b qwen3.8:27b --output .\gemma-local-bakeoff.json
```

This does not install the model automatically, change the production planner,
execute any tools, or produce evidence of real-task completion. The default
models remain unchanged until an acceptance suite justifies promotion.

### User Belief Model

```text
JARVIS_USER_BELIEF_MODEL_ENABLED=1
```

The private bearer-token-authenticated API exposes:
`POST /belief-model/exposure`, `POST /belief-model/world`,
`POST /belief-model/decision`, `POST /belief-model/decision/resolve`,
`GET /belief-model/divergences`, and `POST /belief-model/forget`.
A forget operation requires the explicit literal
`DELETE_USER_BELIEF_MODEL`. World values submitted by an API client are
classified **attested, not verified**; they cannot trigger a divergence
warning by themselves. No mind reading, passive text capture or automated
contract action is implied.

### Capability evidence and attention budget

```powershell
python -m jarvis_mrb.capability_evidence
python -m jarvis_mrb.capability_evidence --run-unit user_belief_model
```

The authenticated `GET /capabilities/evidence` endpoint and exact spoken
question "What capabilities are verified?" report the seven tracked feature
slices and **missing** acceptance scopes. A passing local unit test cannot
claim hardware acceptance.

Set `JARVIS_ATTENTION_BUDGET_ENABLED=1` to enable the three-per-hour budget
for informational proactive alerts. This setting does not throttle warnings,
urgents or unclassified severity; status can be inspected via authenticated
`GET /attention/budget`. It intentionally does not silence critical warnings.

## Required build/release evidence

1. Full Windows Python regressions and isolated world acceptance.
2. macOS iOS simulator compile and iOS frontend integration checks.
3. Controlled local model/voice tests on the actual GPU with representative
   prompts, memory load and live audio routing.
4. Read-only live search and failure-mode tests without a working provider.
5. Real iPhone/AirPods reconnection, barge-in and output-route observation.
6. Explicit deployment/restart and version/commit identity on the user's
   running services. **No claim of deployment is made by this document.**

See [AirPods and freshness hardware acceptance](AIRPODS_AND_FRESHNESS_ACCEPTANCE.md).
