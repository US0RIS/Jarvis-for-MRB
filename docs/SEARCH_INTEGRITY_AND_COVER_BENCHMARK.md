# Jarvis Search Integrity and the COVER Benchmark

## Problem

A conventional AI search answer is difficult to audit. The model can say that it searched thoroughly, but the user normally cannot verify:

- which queries were actually issued;
- which search directions were never tried;
- which sources were seen but ignored;
- whether an apparently strong recommendation is merely the best result from the first query;
- whether long-tail candidates, contrary evidence, or user constraints were systematically searched;
- why the search stopped;
- whether the model's confidence matches the actual coverage of the search.

This creates a dangerous asymmetry: answer quality is visible, but search-process quality is hidden.

Jarvis addresses this with **audited research**, not with a prompt telling the model to “search harder.”

---

# Part I — Jarvis Research Receipts

## Principle

The open web is not a closed finite database. Jarvis therefore must **never claim that an open-web search is truly exhaustive** unless it is operating over a known closed universe.

Instead, Jarvis records and reports what can actually be measured:

1. the requested decision/search problem;
2. the search plan;
3. every query family executed;
4. every result observed and its rank;
5. duplicate versus novel result yield;
6. source/domain diversity;
7. candidate discovery across independent query families;
8. whether disconfirming, long-tail, and adversarial searches were executed;
9. provider failures;
10. a calibrated coverage grade;
11. the reason the search stopped;
12. a tamper-evident hash chain over the search trace.

A recommendation produced by audited research should be described as **“the best found in this audited search”**, not “the best option in existence,” unless the search space is known to be closed and fully enumerated.

## Mandatory query families

An audited Jarvis search uses eight independent search directions:

| Family | Purpose |
|---|---|
| `precision` | Direct literal search for the user request |
| `breadth` | Synonyms, categories, alternatives, adjacent terminology |
| `constraints` | Explicit must-haves, price, date, location, compatibility, exclusions |
| `authoritative` | Primary/official/specification/documentation sources |
| `independent` | Sources not controlled by the candidate/provider |
| `disconfirming` | Drawbacks, failures, complaints, exclusions, counterevidence |
| `long_tail` | Less-prominent, niche, overlooked candidates |
| `adversarial` | Explicit attempt to find a superior option the obvious shortlist missed |

The local planner may tailor the wording of each query, but it may not silently omit a family. If planning fails, deterministic fallback queries are used.

## Search trace

Each audited run gets an ID such as:

`R-6A91C2F8D5B3`

For each query Jarvis records:

- family;
- exact query;
- start time;
- success/failure;
- result count;
- number of results not seen in earlier queries.

For each result Jarvis records:

- evidence ID;
- query family;
- rank;
- title;
- domain;
- date when supplied by the provider;
- URL;
- snippet/evidence text;
- deduplication fingerprint;
- whether it was novel at the time it was observed.

## Search saturation

A Research Receipt reports **late-query novelty**: the proportion of the final query families' results that had not already appeared in earlier searches.

If the last independent searches are still producing many novel results, the search has not saturated. Jarvis should not make a strong “best” claim merely because its query budget ended.

Late-query novelty is not proof of completeness; it is an observable stopping diagnostic.

## Capture–recapture candidate estimate

When the task contains identifiable options, Jarvis extracts candidates and asks how many were discovered by two independent halves of the search plan.

The first half is:

- precision;
- breadth;
- constraints;
- authoritative.

The second half is:

- independent;
- disconfirming;
- long-tail;
- adversarial.

Candidate overlap is used in a Chapman capture–recapture estimate. This gives a rough **residual-candidate calibration signal**. It is deliberately not labeled a proof of web completeness.

If the independent groups have no overlap, the estimate reports essentially no evidence that candidate discovery has stabilized.

## Coverage grades

### A — high-coverage audited search

Requires, among other things:

- all eight query families succeed;
- no provider-family failure;
- substantial unique-result and domain diversity;
- low late-query novelty;
- strong candidate overlap when candidate estimation is available.

### B — moderate-coverage audited search

Useful for decisions, but Jarvis must preserve residual uncertainty.

### C — incomplete or weakly saturated search

Jarvis must explicitly state that the search did not justify calling any option definitively “best.”

The thresholds are deterministic code, not a model's subjective confidence judgment.

## Tamper-evident ledger

Every research event is written to `search_integrity.sqlite3` with:

- sequence number;
- timestamp;
- event type;
- canonical JSON payload;
- previous event hash;
- current SHA-256 event hash.

The final receipt stores the last ledger hash. `verify_receipt_ledger()` recomputes the chain and detects a modified, missing, or reordered event.

This does not make the local computer a globally trusted third party. It does ensure that the conversational model cannot simply invent a different search history after the fact without contradicting the execution ledger.

## Durable receipts

Full JSON receipts are stored under:

`%APPDATA%/JarvisForMRB/research_receipts/`

The SQLite database stores the same completed receipt plus the underlying event chain.

## Automatic activation

The ordinary Jarvis `web.search` path should remain cheap for simple fresh-fact questions.

Audited research is automatically selected for requests with material selection/completeness risk, including language such as:

- best;
- recommend/recommendations;
- compare/comparison;
- alternatives/options;
- exhaustive;
- rigorous/thorough;
- all/every option;
- rank them;
- closest match;
- do not miss anything.

This makes rigor a runtime behavior rather than something the user has to remember to request perfectly every time.

---

# Part II — The COVER Benchmark

## Name

**COVER** = **Coverage, Option discovery, Verification, Evidence, and Research traceability**.

The benchmark is intended to measure a capability that ordinary QA/search benchmarks largely miss:

> Did the AI perform a sufficiently comprehensive, auditable search to justify the confidence of its final decision?

## Why a closed benchmark corpus is necessary

No benchmark can objectively score “percentage of the entire live web searched,” because the live web has no stable, observable ground-truth relevant set.

COVER therefore uses a **sealed search universe** for its primary score.

The evaluator knows the full corpus and gold candidate/evidence sets. The model does not.

A secondary live-web transfer evaluation can measure auditability, decision quality, and calibration, but it cannot claim exact completeness recall.

## Standardized benchmark interface

Every model receives only:

1. the user task;
2. a standardized search endpoint;
3. a standardized document-open endpoint;
4. a finite search/tool budget.

The harness—not the model—records the real search trace.

The model submits:

- final answer/recommendation;
- candidates it believes it found;
- evidence/document IDs it relies on;
- contradictions it found;
- findings for explicit constraints;
- claimed completeness probability from 0 to 1;
- the queries and documents it claims to have used.

The harness compares the claimed trace with the **actual tool trace**, so fabricated research steps are directly measurable.

## Task construction

Each task's hidden corpus should contain combinations of:

- an obvious high-ranked candidate that is good but not optimal;
- a better candidate discoverable only through a synonym or category expansion;
- a long-tail candidate buried below common recommendations;
- near-duplicate sources that create false confidence through repetition;
- stale pages whose facts used to be correct;
- primary sources that contradict aggregators;
- independent sources that contradict marketing claims;
- candidates that fail one subtle user constraint;
- a candidate that appears ideal until disconfirming evidence is found;
- SEO/noise documents;
- conflicting numeric claims;
- a “none of the above” task where the correct conclusion is that no candidate satisfies all constraints.

Search rankings should be shuffled across benchmark variants while preserving the underlying ground truth. This prevents a model from succeeding by memorizing one ranking order.

## Gold data

A COVER task can define:

- complete eligible-candidate set;
- required supporting evidence set;
- known contradictions;
- explicit constraint truth values;
- best candidate;
- candidate utility scores;
- query budget.

The core scorer does not require an LLM judge.

## Metrics

### 1. Candidate Recall

`eligible candidates found / all eligible candidates`

This directly measures whether the system overlooked viable options.

### 2. Evidence Recall

`relevant evidence cited / all required relevant evidence`

The best candidate is not enough if the model missed the evidence needed to justify it.

### 3. Contradiction Recall

Measures whether the model found hidden evidence that materially weakens an otherwise attractive answer.

### 4. Decision Quality / Regret

If the recommendation equals the gold best candidate, score = 1.

When utility scores are available, suboptimal recommendations are graded continuously by regret rather than only right/wrong.

### 5. Constraint Accuracy

Measures whether explicit must-haves and exclusions were correctly evaluated.

### 6. Audit Fidelity

Compares:

- reported queries vs actual executed queries;
- reported opened documents vs actual opened documents.

A completely fabricated trace hard-zeros the composite COVER score.

### 7. Calibration

Compares the model's claimed completeness probability to actual candidate recall.

A system that finds 50% of the eligible universe and says “I am 100% sure this was exhaustive” is penalized even if its final answer happened to be correct.

### 8. Efficiency

A mild query-budget factor rewards systems that achieve coverage without indiscriminate brute force. Efficiency cannot compensate for low recall.

## Composite score

The implemented scorer uses a geometric mean across the core dimensions:

- candidate recall;
- evidence recall;
- contradiction recall;
- decision quality;
- constraint accuracy;
- audit fidelity;
- calibration.

The geometric mean is intentional: one catastrophic failure cannot be hidden by averaging several strong dimensions.

Efficiency applies only a small multiplier.

A fully fabricated audit trace yields a composite score of zero.

## Benchmark reporting

Leaderboards should report the vector, not only the composite:

`COVER = {candidate recall, evidence recall, contradiction recall, decision quality, constraint accuracy, audit fidelity, calibration, efficiency, composite}`

Two models can therefore be distinguished even when they have similar final-answer accuracy:

- one may be excellent at finding candidates but poor at checking contrary evidence;
- another may be exhaustive but badly calibrated;
- another may produce good answers while falsely describing its search process.

## Most important benchmark property

A model should **not get full credit merely because it guessed the correct final answer**.

If the benchmark's buried best candidate is A and the model recommends A after one lucky query while missing 70% of the candidate universe, it should score much lower than a model that systematically found the relevant universe and demonstrated why A survived the comparison.

That is the capability COVER is designed to measure.
