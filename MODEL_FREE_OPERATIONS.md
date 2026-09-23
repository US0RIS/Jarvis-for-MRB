# Jarvis model-free execution audit

Branch: `jarvis/memomind-prep`. This document records **what no longer needs Qwen**, what already used deterministic code, and what genuinely remains semantic/model-based.

The purpose is **reliable tool selection and factual source retrieval**, not blanket replacement of language understanding with regexes. A no-match deliberately falls through to the existing Qwen planner rather than inventing recipients, misinterpreting references, applying instructions embedded in retrieved data, or silently making a consequential decision.

## Replaced/short-circuited Qwen calls

| Original Qwen role | Current deterministic approach |
|---|---|
| `agent._ollama_plan`: parse ordinary spoken tool requests, names, dates, arguments | `deterministic_dispatch.dispatch` matches anchored explicit command families before the non-streaming planner. The streaming agent uses the **same** `agent._fast_path`, also before Ollama. |
| Qwen needed to decide Gmail inbox/unread/sent/search | Literal Gmail query syntax, exact sender addresses, preserved user query and bounds. Never guess a contact address. |
| Qwen needed to choose Calendar reads/day filters | Explicit, calculated start/end instants for today/tomorrow/yesterday, bounded future/past/calendar subject search. |
| Qwen needed to choose browser/PC/status/Agency/read-only memory commands | Exact, strongly typed tools and original proper-noun arguments. Relative/contextual pronouns remain model-routed. |
| Qwen needed to form common reminders, explicit email and ISO calendar writes | High-precision grammar extracts unambiguous fields. **Existing** `execute_tool` permission decisions and foreground confirmation still execute on every selected tool. |
| Qwen needed to answer simple local clock/world time or four-function arithmetic | Python local clock, IANA timezones (bundled `tzdata` on Windows) and bounded `Decimal`; no opening Clock/Calculator. |
| `workflow_engine.plan_workflow` needed Qwen for simple two-source reads | An exact two-source whitelist compiles a read-only, independent DAG; `_validate_plan` and node-level permission policy remain active. Other multi-step workflows still use the model. |
| `briefing.generate_briefing` used Qwen merely to paraphrase calendar/mail/weather/news | Default briefing now deterministically formats actual Calendar/Gmail results, attributed web-search excerpts and background status. Inference is **not** used to turn a search snippet into a confirmed fact. |
| `daily_journal._render_with_model` used Qwen to narrate local activity | Default renders dated, evidence-only sections deterministically; obvious secret keywords in conversation excerpts are suppressed. Opt-in previous narrative mode: `JARVIS_JOURNAL_USE_QWEN=1`. |
| `tools.web.refine_query` sent long voice queries to Qwen to remove filler | Default strips only known fixed prefixes and otherwise retains the original query, preserving requirements, negations and identifiers. Opt-in: `JARVIS_WEB_QUERY_USE_QWEN=1`. |
| `search_integrity._plan_queries` used Qwen to generate the mandatory eight search families | Default builds and audits all eight families deterministically. Opt-in semantic expansion: `JARVIS_RESEARCH_PLAN_USE_QWEN=1`. |
| `agency_goal_compiler.compile_observable_contract` used Qwen even for explicit achieved-state goals | Existing safe, grounded `_fallback_contract` is validated **first** for directly observable states; Qwen remains necessary for goals whose actual completion evidence is not spelled out. Tests that inject a custom compiler retain exact behavior. |
| `meeting_notes._extract_actions` used Qwen even for explicit machine-readable action records | Strictly structured `ACTION: owner | task | deadline` lines are extracted with a bounded parser and quoted evidence; mixed/ordinary speech still uses semantic extraction. |

## Reality Graph offload

Routine physical-world reasoning now has a deterministic intermediate layer in `jarvis_mrb.reality_graph`. Place snapshots normalize existing camera-catalog, environmental, alert, incident and facility evidence with explicit freshness and provider state. Mission graphs additionally accept already-authorized normalized order/courier/traffic/public-camera/device observations and compute freshness, ETA/deadline math, stationary thresholds, route delays, provider delivery state and conservative cross-source delay correlation with **zero Qwen calls**.

The graph deliberately distinguishes provider-reported delivery from personal receipt and camera congestion from person/vehicle identity. Stale observations cannot drive current facts. Routine questions such as whether a delivery is late, whether a provider reports it delivered, and whether fresh courier + route evidence are consistent with a traffic delay are answered deterministically. Unknown questions receive only a bounded semantic packet (derived facts + short evidence claims), never the raw provider payload, for optional model escalation. The graph has no action authority; Conductor/permission policy remains a separate boundary.

## Already deterministic before this work

Permission risk labels, staged confirmation binding, verified execution/readback, most world-model/entity/term/conflict/chronology SQL, source timestamps, source-specific camera/world/sanctions/SEC/EPA contracts, iPhone location/button paths, Agency persisted status, jobs scheduling/cancellation execution, real provider authentication, transport framing and basic model selection were already code, **not** Qwen decisions.

The existing `agent._fast_path` already covered many literal commands such as Agency mode, web search, direct vision/expense actions, latest email, calendar conflicts, job cancellation, system resources and explicit app open/close; new dispatch extends it rather than replacing its confirmation boundaries.

## Retained model calls that cannot be hardcoded reliably

- **Open-ended chat, explanation, nuanced follow-ups and complex tool choices:** use Qwen only when an explicit deterministic route cannot be established.
- **Semantic search-result synthesis, cross-source relevance, audited research candidate extraction:** require reading unfamiliar evidence, deduplicating/qualifying entities, balancing conflicting sources and user constraints; hardcoded rules may do safe filtering, but cannot substitute for all semantic judgment. `tools.web.web_answer` and `search_integrity._extract_candidates/_synthesize` remain model-based.
- **`fact_checker.check_claim`:** evaluating nontrivial natural-language consistency against messy local records requires semantic interpretation; automated numerical SEC XBRL comparisons already use hardcoded same-period/unit rules.
- **`agency_deliberation` perspectives/synthesis, genuinely new `agency_goal_compiler` evidence contracts, general `workflow_engine.plan_workflow` DAGs, and `tool_repair` generated code:** retaining model use is preferable to a misleading rule engine claiming it understood novel commitments, business implications or arbitrary APIs.
- **Moondream/vision transcription/OCR, speech recognition and speech synthesis:** inherently model-based perception/generation, but do not need a Qwen *tool planner* for a correctly routed request.
- **Future broader physical-world control and third-party licensed interfaces:** need actual authorized integrations, not simply a stronger model or guessed endpoints.

## Conversation and opinions (without sacrificing precision)

The shared `personality.JARVIS_PERSONALITY` applies to **both** normal JSON-planned requests and streaming voice replies. Jarvis should have an actual, context-sensitive point of view on non-political taste, design, engineering trade-offs, and what to pursue; it should react to what was said, disagree when warranted, and distinguish a subjective preference from a verified fact. Natural dialogue must not default to generic pros/cons recitals, flattery or compulsory "Sir" preambles.

The streaming transport and ordinary `agent._respectful` **no longer inject a form of address or downcase the generated answer**. The model can use "sir" occasionally where it fits. Briefings and hardcoded status/tool responses remain deterministic; the new tone does not create imagined personal experiences or bypass actions/permission checks. A small streaming creativity allowance improves phrasing while retaining a conservative first-line JSON tool protocol for ambiguous/actionable requests. Strictly in-context opinions on already supplied ideas now bypass that JSON preamble and use the direct conversational stream; the same public-research and deterministic-execution gates run first, and the direct conversation route has no tool authority.

## Runtime verification

Authenticated `GET /routing/status` reports per-process counts for `model_bypass`, `model_planner_attempt`, and selected direct-route families **without storing utterances or arguments**. The normal `GET /health` includes the same process-local counters as `model_free_routing`. These counts are not a CPU/GPU benchmark, and they do not include intentional Qwen research/vision/subsystem synthesis.

After upgrading the backend, compare these counters while giving explicit commands:

```text
What time is it in Melbourne?
What's on my calendar tomorrow?
Search my email for Project Apollo
Check my calendar and email
Remind me every weekday at 8:15 AM to check mail
```

Check confirmations separately for literal structured writes. The last two examples can alter local scheduled state if allowed by the configured permission policy; avoid creating test reminders unnecessarily.

## Safeguards

1. Case/proper nouns, requested time windows and Gmail unread filters must survive deterministic extraction.
2. No matching user utterance means **no deterministic action**. Do not default to an older topic or infer a recipient/meeting duration from memory.
3. Writes are still subject to `permissions.decide`, staged explicit confirmation where applicable, and action readback/verification.
   The literal phrase “this week” uses the current calendar week, not the next seven days; ambiguous “messages” and “meeting” are left for context-aware selection rather than assumed to be Gmail or Calendar.
4. A model-free briefing quotes source snippets as excerpts, not a verified forecast or definitive current-news summary.
5. The work changes the backend routing/synthesis defaults, not the iPhone layout or which local models are installed. The physical iPhone and Windows host still require a new deployment from this feature branch.
