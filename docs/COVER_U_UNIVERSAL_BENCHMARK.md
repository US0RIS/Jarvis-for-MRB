# COVER-U: Universal Benchmark for Research Intelligence

## Purpose

COVER-U is designed to answer a broader question than whether an AI can conduct a comprehensive search:

> Does the system know **whether** research is needed, **what kind** of research is needed, **how far** to pursue it, **which evidence** deserves trust, **when** to stop, and **how strongly** its conclusion is justified?

The benchmark is deliberately system-level. It can compare a base model plus standardized tools, a proprietary research product, a custom agent, or Jarvis.

The universal headline score is application-neutral. Jarvis also receives a separate application profile that places more weight on comprehensive discovery and decision-support tasks. The Jarvis profile never replaces or alters the universal score.

---

## Why a new benchmark is needed

Single-answer browsing benchmarks test an important capability but are increasingly close to saturation for frontier systems. They also usually reward only the final answer. That leaves several failure modes poorly measured:

- getting the right answer by luck after shallow search;
- searching far too much for a trivial question;
- failing to discover viable alternatives in a recommendation task;
- trusting SEO repetition rather than independent evidence;
- missing contradictory or current evidence;
- claiming to have reviewed sources that were never opened;
- expressing near-certainty when the evidence only supports a tentative answer;
- continuing to search long after marginal information gain has collapsed;
- stopping while late searches are still discovering important new candidates;
- failing to abstain when the task is genuinely unresolved or unsatisfiable.

COVER-U evaluates these behaviors directly.

---

# 1. Two benchmark tracks

## 1.1 Standardized sealed-web track

This is the primary scientific leaderboard.

Every system receives the same tools and the same frozen corpus:

```text
search(query) -> ranked result IDs + snippets
open(document_id) -> document contents
```

The evaluator knows the full corpus, gold evidence, eligible candidate universe, stale/current documents, contradictions, and hidden distractors. The model does not.

This permits exact measurement of recall and research completeness while avoiding the reproducibility problems of the live web.

## 1.2 Native-system / live-web track

This measures the product as users actually experience it.

Systems may use their native browser, search APIs, memory, retrieval stack, and research UX. The harness records externally visible actions wherever possible.

Live-web results are reported separately because different search providers, dates, personalization, geographies, and inaccessible pages make exact cross-system comparisons less controlled.

---

# 2. Universal task archetypes

A genuinely universal benchmark must include tasks where comprehensive search is correct **and** tasks where it is wasteful.

The Standard score weights ten archetypes equally at the archetype level.

## A0 — No-search

The answer is already supplied, is directly computable, or is stable enough that browsing adds no value. The system should avoid unnecessary retrieval.

Measures:
- restraint;
- instruction following;
- latency/cost discipline;
- resistance to tool-call reflexes.

## A1 — Lookup

One narrow current fact or direct source should suffice.

Measures:
- query formation;
- correct source identification;
- quick stopping.

## A2 — Verification

A claim must be checked against authoritative evidence, ideally by opening the source rather than relying on a search snippet.

Measures:
- provenance;
- primary-source preference;
- claim/evidence correspondence.

## A3 — Multi-hop investigation

The answer requires several linked discoveries, entity resolution, or search pivots.

Measures:
- persistence;
- strategic query reformulation;
- maintaining intermediate state.

## A4 — Synthesis

Several sources contain complementary or conflicting pieces of the answer.

Measures:
- evidence integration;
- conflict handling;
- source weighting;
- long-context discipline.

## A5 — Decision / recommendation

The system must discover alternatives, enforce user constraints, compare tradeoffs, and select an option.

Measures:
- candidate recall;
- constraint accuracy;
- decision regret;
- disconfirming search.

## A6 — Comprehensive enumeration

High recall is explicitly required: all qualifying products, laws, studies, locations, options, or records in the sealed universe must be found.

Measures:
- exhaustive search strategy;
- synonym/category expansion;
- saturation detection;
- long-tail discovery;
- completeness calibration.

This is especially important for Jarvis.

## A7 — Temporal/version resolution

Old and new sources conflict. The system must identify which state is current and preserve chronology.

Measures:
- freshness;
- version resolution;
- stale-source handling;
- date reasoning.

## A8 — Adversarial / unsatisfiable

The corpus contains SEO spam, duplicated claims, attractive false leads, poisoned snippets, or no candidate satisfying all constraints.

Measures:
- skepticism;
- abstention;
- contradiction discovery;
- resistance to popularity bias.

## A9 — Long-horizon research

The task requires dozens of searches/opens, branching hypotheses, recovery from dead ends, and state preservation over a long trace.

Measures:
- planning;
- memory;
- search creativity;
- recovery;
- termination policy.

---

# 3. Difficulty ladder designed not to saturate

Each archetype contains six difficulty levels.

### D1
Direct evidence, low distractor density, obvious terminology.

### D2
Several plausible sources, minor terminology variation.

### D3
Multi-source or multi-constraint reasoning, stale or redundant distractors.

### D4
Buried alternatives, conflicting evidence, entity ambiguity, significant search branching.

### D5
Long-tail sources, adversarial ranking, substantial distractor corpus, multiple plausible dead ends.

### D6
Frontier-tail tasks requiring long-horizon search, rare terminology, hidden category bridges, deliberate negative evidence, version changes, and/or near-exhaustive recall over a large candidate universe.

The task bank should be calibrated so that the best public frontier system is **well below 100** on the hidden Standard suite. A target band of roughly 45–75 for the strongest system at release is desirable; the exact value is empirical, not hard-coded.

A perfect 100 remains possible for an oracle-quality system. There is no artificial score cap.

---

# 4. Anti-saturation design

COVER-U should not become another benchmark that is solved and then frozen forever.

## 4.1 Large private task bank

Maintain thousands of tasks. Only a minority appear in any public evaluation.

## 4.2 Anchor items

A stable hidden anchor set permits longitudinal comparison across benchmark versions.

## 4.3 Fresh generated variants

Facts and causal structure can remain fixed while surface form changes:
- document names;
- ranking order;
- synonyms;
- distractor wording;
- entity aliases;
- irrelevant document placement;
- source authority hierarchy.

This makes memorizing a search path less useful.

## 4.4 Difficulty refresh

When top systems exceed an agreed saturation threshold on D6, add harder D6 items and preserve historical anchors. Do not redefine old scores retroactively.

## 4.5 Canary and leakage checks

Private corpora receive canary strings and seeded phrases. Evaluators monitor for evidence that benchmark documents entered training corpora.

---

# 5. Corpus construction

The sealed web should resemble the real web rather than a clean QA dataset.

A serious corpus includes:
- primary sources;
- secondary reporting;
- reviews;
- forums/community discussions;
- marketing pages;
- copied/duplicated articles;
- stale versions;
- partially correct pages;
- broken links represented as inaccessible documents;
- contradictory numeric claims;
- aliases and renamed entities;
- irrelevant high-ranking pages;
- niche low-ranking pages containing critical evidence.

For recommendation/comprehensive tasks, the evaluator must know the complete eligible candidate set in the sealed universe.

For verification tasks, the evaluator marks which sources must actually be opened rather than merely surfaced as snippets.

---

# 6. Scoring dimensions

Each task receives deterministic scores where possible. LLM-as-judge should be avoided for the core leaderboard.

## Outcome

Did the system answer correctly, choose a high-utility option, or abstain when appropriate?

Decision tasks may be scored continuously by regret rather than binary exact match.

## Evidence

Weighted recall and precision over decision-relevant evidence. COVER-U uses recall-favoring scoring because missing decisive evidence is usually more serious than citing one extra source.

## Contradiction discovery

Did the system find evidence that invalidates or weakens an attractive answer?

## Provenance

Were cited sources actually opened? Were required primary/authoritative sources inspected?

Search-result snippets do not count as full-source review.

## Research-policy accuracy

Did the system choose an appropriate research depth?

The scale is:

```text
0 none
1 lookup
2 verify
3 synthesize
4 compare
5 comprehensive
```

Under-research is penalized more heavily than over-research, while over-research also loses efficiency.

## Calibration

Does stated confidence match actual correctness/completeness? Correct abstention on unanswerable tasks is explicitly rewarded.

## Audit fidelity

The external harness records actual queries and document opens. If the system reports a research trace, that report is compared to the real trace.

Fabricated research history hard-zeros the task composite.

## Temporal correctness

Did the system identify current evidence and resolve stale/current conflicts?

## Efficiency

Search and document-open budgets measure wasted effort, but efficiency is only a bounded modifier. A thorough justified search should not lose to shallow luck simply because it used more calls.

---

# 7. Headline aggregation

COVER-U does **not** simply average every task. That would let a benchmark become dominated by whichever archetype is cheapest to generate.

The Standard score:

1. computes deterministic task scores;
2. applies mild difficulty weighting;
3. computes an archetype score for each of the ten archetypes;
4. takes a weighted geometric mean across archetypes;
5. reports the result on a 0–100 scale.

The geometric mean prevents a system that is excellent at lookup but terrible at comprehensive research from hiding the weakness behind easy-task volume.

Always publish the full scorecard alongside the headline:

```text
COVER-U Standard      63.4
No-search             91.2
Lookup                88.5
Verification          74.1
Multi-hop             66.9
Synthesis             61.8
Decision              58.0
Comprehensive         42.7
Temporal              69.3
Adversarial           48.1
Long-horizon          39.6
```

The profile matters as much as the headline.

---

# 8. Jarvis profile

Jarvis should be judged on the universal Standard score **and** a separate deployment score.

The Jarvis profile weights:

| Archetype | Weight |
|---|---:|
| No-search | 0.65 |
| Lookup | 0.75 |
| Verification | 1.15 |
| Multi-hop | 1.10 |
| Synthesis | 1.20 |
| Decision | 1.70 |
| Comprehensive | 2.00 |
| Temporal | 1.20 |
| Adversarial | 1.35 |
| Long-horizon | 1.30 |

Why: Jarvis is frequently asked to make consequential real-world recommendations involving products, travel, local services, purchases, schedules, people, and ongoing objectives. In those settings a missed alternative can matter more than an extra second of search latency.

This weighting is intentionally **not** used for the universal leaderboard.

---

# 9. Benchmark fairness across models

For the sealed-web Standard track:

- same corpus;
- same search index;
- same search/open tool contract;
- same tool-call budget by task;
- same wall-clock policy;
- same context about current date/time;
- no private memory unless the task explicitly supplies it;
- no hidden vendor-specific search engine advantages.

A system may use internal reasoning however it wants.

Three leaderboards should be kept separate:

1. **Model + standardized tools** — best comparison of research intelligence.
2. **Native research product** — best comparison of what users can buy/use.
3. **Jarvis deployment** — real system with its local/private capabilities.

---

# 10. Why frontier models should not get 100

The benchmark ceiling is protected by combining capabilities that are individually difficult and interact badly:

- hard retrieval;
- broad candidate recall;
- correct stopping;
- contradiction search;
- source opening and provenance;
- temporal resolution;
- long-horizon state maintenance;
- calibration;
- abstention;
- efficiency;
- audit honesty.

A system that reaches the right final answer through luck can still score poorly.

A system that searches exhaustively on every task can also score poorly.

A system that is excellent at short-answer browsing but weak at exhaustive enumeration cannot hide behind its lookup performance.

A system that fabricates its search process gets zero for the affected task.

This makes 100 represent something close to an ideal research agent rather than merely an excellent answer generator.

---

# 11. Current implementation in Jarvis

`jarvis_mrb/cover_universal.py` implements:
- the ten universal archetypes;
- six-level difficulty metadata;
- task-level multidimensional scoring;
- appropriate-research-depth scoring;
- evidence/provenance/contradiction scoring;
- abstention and confidence calibration;
- temporal scoring;
- audit-fidelity hard failure;
- efficiency as a bounded modifier;
- Standard suite aggregation;
- separate Jarvis application weighting.

`tests/test_cover_universal.py` contains deterministic regression cases for:
- unnecessary browsing on no-search tasks;
- a lucky correct answer after shallow research;
- correct abstention;
- fabricated search history;
- different Standard vs Jarvis weighting.

The corpus generator, private task bank, standardized search service, and public evaluation harness remain benchmark-infrastructure work. The scorer and benchmark contract exist in source; no claim is made that a full COVER-U leaderboard has been run yet.
