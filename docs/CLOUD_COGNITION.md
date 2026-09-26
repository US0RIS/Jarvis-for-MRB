# Cloud Cognition: Groq GPT-OSS 120B

## Purpose

Jarvis uses a heterogeneous cognitive hierarchy:

```
deterministic capabilities -> local Qwen -> optional cloud reasoning
```

Groq GPT-OSS 120B is the first cloud reasoning provider. It is an escalation tier, not the default planner and not an execution authority.

Current Groq model identifier: `openai/gpt-oss-120b`.

## Routing

`jarvis_mrb.cloud_cognition.route_cognition` uses deterministic signals rather than asking Qwen whether Qwen is capable enough. Signals include:

- an existing deterministic capability;
- difficult/novel reasoning cues;
- uncertainty, ambiguity and conflicting evidence;
- prior local-planner failures and malformed results;
- long context;
- multi-step dependency count;
- source diversity;
- consequence severity;
- authoritative-retrieval requirements.

Ordinary requests remain local. Harmless but genuinely difficult reasoning can escalate. Consequence severity raises scrutiny but does not automatically force the cloud when authoritative retrieval or deterministic logic is the better first step.

Automatic escalation uses `medium` reasoning effort by default and `high` for unusually difficult or difficult-plus-consequential cases.

## Provider abstraction

`CloudReasoningProvider` is a protocol. `GroqProvider` is the first implementation. The routing/context layers do not require Groq-specific behavior, and the regression suite includes a mock alternative provider.

The server-side developer path reads `GROQ_API_KEY` only when explicitly configured. The normal iPhone/iPad path does not provision the secret to the backend.

## Normal iPhone/iPad credential flow

1. Open **Jarvis -> Settings -> Cloud Intelligence / Groq**.
2. Paste the Groq API key.
3. Tap **Save Key**.
4. Tap **Test Connection**.
5. Enable **Cloud cognition**.

The key is stored under `jarvis.groqAPIKey` in the app's Apple Keychain using `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.

The key is not written to UserDefaults, source, repository files, Reality Graph state, conversation history, analytics, or backend configuration.

For an escalated app request:

1. The app asks the authenticated Jarvis backend to prepare cloud reasoning.
2. The backend deterministically routes the request and compiles a minimized cloud context.
3. The backend strips local-only material, bounds history, removes irrelevant older conversation and redacts credential-like secrets.
4. The backend returns a short-lived task ID, provider/model/effort metadata, and the minimized context.
5. The app calls Groq directly with the Keychain credential.
6. Groq returns a strict JSON-schema proposal.
7. The app posts the proposal (not the credential) to `/cloud-cognition/resolve`.
8. The backend validates the proposal.
9. A proposed tool call still enters Jarvis through `execute_tool`, preserving the existing permission, confirmation, audit and verification architecture.

The task ID expires after five minutes and is single-use.

## Structured proposal contract

Groq returns:

- `response`
- `tool` (nullable)
- `arguments_json` (JSON object encoded as a string)
- `evidence_requests`
- `assumptions`
- `uncertainties`
- `expected_outcomes`
- `verification_criteria`
- `confidence`

`arguments_json` is a string because Groq strict structured outputs require closed objects with `additionalProperties: false`; arbitrary Jarvis tool argument dictionaries are therefore parsed and validated on the Jarvis side rather than weakening the strict schema.

Cloud output is untrusted proposal data. It is never itself a permission grant.

## Context compiler/privacy

`compile_cloud_context`:

- includes the current request;
- includes at most the most recent eight relevant user/assistant messages;
- excludes messages marked `[local-only]` / `[local_only]`;
- accepts source-labelled evidence with observed time, staleness and uncertainty fields;
- excludes evidence explicitly classified local-only;
- deterministically redacts API keys, passwords, bearer/auth tokens, private keys and common secret formats;
- caps the compiled cloud prompt size;
- returns inspectable classification/redaction counts and a content fingerprint.

The compiler intentionally does not dump the complete Reality Graph, memory store, or entire conversation into the cloud.

## Reliability

Cloud cognition is optional.

Failures caused by offline state, missing credential, auth failure, rate limits, model/provider outage, timeout, malformed output or the circuit breaker fall back to the existing local Jarvis path.

The backend Groq provider uses bounded timeouts, at most one retry for transient conditions, and a short circuit breaker after repeated failures. There is no retry storm.

No free-tier quota is hard-coded.

## Ethical Context / emergencies

Cloud cognition is deliberately downstream of evidence collection and upstream of existing authorization/execution:

```
observe
-> establish circumstances
-> authoritative retrieval where needed
-> reason
-> propose
-> authorization / ethical validation
-> execute permitted action
-> observe
-> verify
-> replan or stop
```

The cloud layer does not implement an ethical override and does not substitute an LLM refusal for security.

For emergency/high-consequence work, deterministic emergency logic and authoritative retrieval remain available without Groq. Cloud failure cannot disable local emergency capability. The router marks authoritative-retrieval cases so model reasoning is not treated as a source of invented procedures.

The broader Ethical Context Engine / Necessity & Proportionality design remains a distinct authority layer. This implementation provides a clean proposal/metadata seam for that engine; it does not pretend the entire future engine is already implemented.

## User controls

- **Enable cloud cognition** / disable cloud cognition in Settings.
- **Routing: Automatic / Force local / Force cloud** in Settings.
- Prefix one request with `local:` / `use local:` / `force local:`.
- Prefix one request with `cloud:` / `use cloud:` / `force cloud:`.

If force-cloud cannot use the cloud, Jarvis remains locally usable rather than failing the whole request.

## Debug/telemetry

`GET /cloud-cognition/status` exposes authenticated routing telemetry such as:

- tier;
- escalation reason and deterministic signals;
- provider/model;
- reasoning effort;
- context fingerprint and redaction count;
- latency/tokens when returned by the cloud caller;
- structured-output validity;
- fallback/circuit state.

Telemetry stores request/response fingerprints and routing metadata rather than raw secrets. Suggested routing changes remain an offline/inspectable engineering decision; there is no uncontrolled self-modification.

## API

Authenticated backend endpoints:

- `GET /cloud-cognition/status`
- `POST /cloud-cognition/prepare`
- `POST /cloud-cognition/resolve`

The normal app does not send its Groq credential to these endpoints.

## Benchmark

Run:

```powershell
py -3.14 -m jarvis_mrb.cognitive_benchmark
```

or after reinstall:

```powershell
jarvis-cognition-benchmark
```

The benchmark covers deterministic commands, ordinary conversation, simple/difficult reasoning, coding/debugging, ambiguity, Reality Graph, World Armor, investigations, privacy-sensitive requests, consequential cases, authoritative emergency retrieval, repeated local failure and malformed local output.

## Acceptance boundary

Automated tests can prove routing, minimization/redaction logic, proposal validation, source-level Keychain wiring, endpoint behavior and iOS compilation.

They cannot prove real Groq account availability, real free-tier quotas, Internet conditions, Keychain persistence on a particular physical device, or live latency without a configured key/device/network. Those remain environment acceptance.
