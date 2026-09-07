from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable


ARCHETYPES = (
    "no_search",
    "lookup",
    "verification",
    "multi_hop",
    "synthesis",
    "decision",
    "comprehensive",
    "temporal",
    "adversarial",
    "long_horizon",
)

RESEARCH_LEVELS = {
    "none": 0,
    "lookup": 1,
    "verify": 2,
    "synthesize": 3,
    "compare": 4,
    "comprehensive": 5,
}

STANDARD_PROFILE = {name: 1.0 for name in ARCHETYPES}

# Jarvis keeps a separate deployment-oriented view without changing the universal
# headline score. This reflects the higher cost of missing an option in personal
# recommendations, purchases, travel, local search, and decision support.
JARVIS_PROFILE = {
    "no_search": 0.65,
    "lookup": 0.75,
    "verification": 1.15,
    "multi_hop": 1.10,
    "synthesis": 1.20,
    "decision": 1.70,
    "comprehensive": 2.00,
    "temporal": 1.20,
    "adversarial": 1.35,
    "long_horizon": 1.30,
}


@dataclass(frozen=True)
class UniversalTaskScore:
    archetype: str
    difficulty: float
    outcome: float
    evidence: float
    contradiction: float
    provenance: float
    research_policy: float
    calibration: float
    audit_fidelity: float
    temporal: float
    efficiency: float
    composite: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UniversalSuiteScore:
    profile: str
    score: float
    archetype_scores: dict[str, float]
    domain_scores: dict[str, float]
    difficulty_scores: dict[str, float]
    task_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_universal_task(
    gold: dict[str, Any],
    submission: dict[str, Any],
    actual_trace: dict[str, Any],
) -> UniversalTaskScore:
    """Score one COVER-U task deterministically.

    COVER-U evaluates research *policy*, not merely exhaustive recall. A benchmark
    task declares an archetype and an appropriate research level. Trivial tasks can
    therefore punish unnecessary browsing while high-recall tasks punish shallow
    search.

    Core gold fields:
      archetype: one of ARCHETYPES
      difficulty: 1..6 (higher means harder)
      answer / acceptable_answers OR candidate_utilities / best_candidate
      answerable: bool (default true)
      required_research_level: none|lookup|verify|synthesize|compare|comprehensive
      relevant_evidence: [doc_id] or {doc_id: weight}
      contradiction_evidence: [doc_id]
      required_open_documents: [doc_id]
      stale_documents: [doc_id]
      current_documents: [doc_id]
      query_budget / open_budget

    Core submission fields:
      answer or recommendation
      abstain: bool
      confidence: 0..1
      cited_evidence: [doc_id]
      found_contradictions: [doc_id]
      reported_queries: [str]
      reported_opened_documents: [doc_id]

    actual_trace is supplied by the external harness, not the model:
      queries: [str]
      opened_documents: [doc_id]
      research_level: optional explicit level selected by the system
    """
    archetype = str(gold.get("archetype") or "multi_hop").strip().lower()
    if archetype not in ARCHETYPES:
        archetype = "multi_hop"
    difficulty = _clamp(_float(gold.get("difficulty"), 3.0) / 6.0, 1 / 6, 1.0)

    outcome = _outcome_score(gold, submission)
    evidence = _evidence_score(gold, submission)
    contradiction = _contradiction_score(gold, submission)
    provenance = _provenance_score(gold, submission, actual_trace)
    research_policy = _research_policy_score(gold, actual_trace)
    calibration = _calibration_score(gold, submission, outcome)
    audit_fidelity = _audit_fidelity(submission, actual_trace)
    temporal = _temporal_score(gold, submission)
    efficiency = _efficiency_score(gold, actual_trace)

    # Dimensions can be inapplicable for some task classes. The score functions
    # return 1.0 when a dimension is genuinely absent from the task contract.
    core = [
        outcome,
        evidence,
        contradiction,
        provenance,
        research_policy,
        calibration,
        temporal,
    ]
    # A fabricated trace is a benchmark integrity failure, not merely a weak answer.
    composite = 0.0 if audit_fidelity <= 0 else _geometric_mean(core) * audit_fidelity
    # Efficiency is deliberately a bounded modifier: exhaustive research should not
    # lose to shallow research merely because it used more justified tool calls.
    composite *= 0.90 + 0.10 * efficiency

    return UniversalTaskScore(
        archetype=archetype,
        difficulty=round(difficulty * 6.0, 3),
        outcome=round(outcome, 6),
        evidence=round(evidence, 6),
        contradiction=round(contradiction, 6),
        provenance=round(provenance, 6),
        research_policy=round(research_policy, 6),
        calibration=round(calibration, 6),
        audit_fidelity=round(audit_fidelity, 6),
        temporal=round(temporal, 6),
        efficiency=round(efficiency, 6),
        composite=round(_clamp(composite), 6),
    )


def aggregate_universal_suite(
    rows: Iterable[dict[str, Any]],
    *,
    profile: str = "standard",
) -> UniversalSuiteScore:
    """Aggregate task rows into a 0-100 COVER-U score.

    Each row must contain ``gold``, ``submission``, and ``actual_trace``. The
    universal Standard profile gives each archetype equal importance regardless of
    task-bank frequency. The Jarvis profile is a separate application-weighted view.
    Difficulty contributes a mild weight so easy-item padding cannot inflate scores.
    """
    profile_name = profile.strip().lower()
    if profile_name == "jarvis":
        archetype_weights = JARVIS_PROFILE
    else:
        profile_name = "standard"
        archetype_weights = STANDARD_PROFILE

    task_records: list[tuple[dict[str, Any], UniversalTaskScore]] = []
    for row in rows:
        gold = row.get("gold") if isinstance(row, dict) else None
        submission = row.get("submission") if isinstance(row, dict) else None
        trace = row.get("actual_trace") if isinstance(row, dict) else None
        if not isinstance(gold, dict) or not isinstance(submission, dict) or not isinstance(trace, dict):
            continue
        task_records.append((gold, score_universal_task(gold, submission, trace)))

    if not task_records:
        return UniversalSuiteScore(profile_name, 0.0, {}, {}, {}, 0)

    by_arch: dict[str, list[tuple[float, float]]] = {name: [] for name in ARCHETYPES}
    by_domain: dict[str, list[tuple[float, float]]] = {}
    by_difficulty: dict[str, list[float]] = {}

    for gold, score in task_records:
        difficulty_weight = 0.75 + 0.25 * (score.difficulty / 6.0)
        by_arch[score.archetype].append((score.composite, difficulty_weight))
        domain = str(gold.get("domain") or "unspecified").strip().lower() or "unspecified"
        by_domain.setdefault(domain, []).append((score.composite, difficulty_weight))
        bucket = f"D{max(1, min(6, int(round(score.difficulty))))}"
        by_difficulty.setdefault(bucket, []).append(score.composite)

    archetype_scores = {
        name: _weighted_mean(values)
        for name, values in by_arch.items()
        if values
    }
    domain_scores = {
        name: _weighted_mean(values)
        for name, values in by_domain.items()
        if values
    }
    difficulty_scores = {
        name: sum(values) / len(values)
        for name, values in by_difficulty.items()
        if values
    }

    weighted_arches = [
        (score, archetype_weights.get(name, 1.0))
        for name, score in archetype_scores.items()
    ]
    headline = _weighted_geometric_mean(weighted_arches)

    return UniversalSuiteScore(
        profile=profile_name,
        score=round(100.0 * headline, 3),
        archetype_scores={k: round(v * 100.0, 3) for k, v in archetype_scores.items()},
        domain_scores={k: round(v * 100.0, 3) for k, v in domain_scores.items()},
        difficulty_scores={k: round(v * 100.0, 3) for k, v in difficulty_scores.items()},
        task_count=len(task_records),
    )


def _outcome_score(gold: dict[str, Any], submission: dict[str, Any]) -> float:
    answerable = bool(gold.get("answerable", True))
    abstained = bool(submission.get("abstain", False))
    if not answerable:
        return 1.0 if abstained else 0.0
    if abstained:
        return 0.0

    answer = _key(submission.get("answer") or submission.get("recommendation"))
    acceptable = gold.get("acceptable_answers")
    if isinstance(acceptable, list) and acceptable:
        return 1.0 if answer in {_key(v) for v in acceptable} else 0.0
    if gold.get("answer") is not None:
        return 1.0 if answer == _key(gold.get("answer")) else 0.0
    if gold.get("best_candidate") is not None:
        best = _key(gold.get("best_candidate"))
        if answer == best:
            return 1.0

    utilities = gold.get("candidate_utilities")
    if isinstance(utilities, dict) and utilities and answer:
        norm: dict[str, float] = {}
        for name, value in utilities.items():
            try:
                norm[_key(name)] = float(value)
            except (TypeError, ValueError):
                continue
        if answer in norm and norm:
            hi, lo = max(norm.values()), min(norm.values())
            if math.isclose(hi, lo):
                return 1.0
            return _clamp((norm[answer] - lo) / (hi - lo))
    return 0.0


def _evidence_score(gold: dict[str, Any], submission: dict[str, Any]) -> float:
    raw = gold.get("relevant_evidence")
    if isinstance(raw, dict):
        weights = {_key(k): max(0.0, _float(v, 1.0)) for k, v in raw.items() if _key(k)}
    elif isinstance(raw, list):
        weights = {_key(v): 1.0 for v in raw if _key(v)}
    else:
        return 1.0
    if not weights:
        return 1.0
    cited = {_key(v) for v in submission.get("cited_evidence", []) if _key(v)}
    total = sum(weights.values())
    recall = sum(weight for key, weight in weights.items() if key in cited) / total if total else 1.0
    if not cited:
        return 0.0
    precision = len(cited & set(weights)) / len(cited)
    # F2 favors recall because missing decision-relevant evidence is typically more
    # damaging than citing one extra relevant-ish source.
    if precision <= 0 or recall <= 0:
        return 0.0
    return (5 * precision * recall) / (4 * precision + recall)


def _contradiction_score(gold: dict[str, Any], submission: dict[str, Any]) -> float:
    required = {_key(v) for v in gold.get("contradiction_evidence", []) if _key(v)}
    if not required:
        return 1.0
    found = {_key(v) for v in submission.get("found_contradictions", []) if _key(v)}
    return len(required & found) / len(required)


def _provenance_score(gold: dict[str, Any], submission: dict[str, Any], trace: dict[str, Any]) -> float:
    required = {_key(v) for v in gold.get("required_open_documents", []) if _key(v)}
    cited = {_key(v) for v in submission.get("cited_evidence", []) if _key(v)}
    opened = {_key(v) for v in trace.get("opened_documents", []) if _key(v)}
    if required:
        required_score = len(required & opened) / len(required)
    else:
        required_score = 1.0
    if not cited:
        citation_open_score = 1.0 if not gold.get("relevant_evidence") else 0.0
    else:
        citation_open_score = len(cited & opened) / len(cited)
    return 0.6 * required_score + 0.4 * citation_open_score


def _research_policy_score(gold: dict[str, Any], trace: dict[str, Any]) -> float:
    required_name = str(gold.get("required_research_level") or "synthesize").strip().lower()
    required = RESEARCH_LEVELS.get(required_name, 3)
    explicit = str(trace.get("research_level") or "").strip().lower()
    if explicit in RESEARCH_LEVELS:
        actual = RESEARCH_LEVELS[explicit]
    else:
        actual = _infer_research_level(trace)

    delta = actual - required
    if delta == 0:
        return 1.0
    if delta < 0:
        # Under-research is especially serious because the conclusion can look clean
        # while the relevant universe was never explored.
        return max(0.0, 1.0 - 0.28 * abs(delta))
    # Over-research is a real universal failure mode too, but it is less dangerous
    # than under-research and is additionally captured by efficiency.
    return max(0.35, 1.0 - 0.12 * delta)


def _infer_research_level(trace: dict[str, Any]) -> int:
    q = len(trace.get("queries", []) or [])
    o = len(trace.get("opened_documents", []) or [])
    if q == 0 and o == 0:
        return 0
    if q <= 1 and o <= 1:
        return 1
    if q <= 2 and o <= 3:
        return 2
    if q <= 5 and o <= 8:
        return 3
    if q <= 9 and o <= 16:
        return 4
    return 5


def _calibration_score(gold: dict[str, Any], submission: dict[str, Any], outcome: float) -> float:
    try:
        confidence = float(submission.get("confidence"))
    except (TypeError, ValueError):
        return 0.5
    confidence = _clamp(confidence)
    answerable = bool(gold.get("answerable", True))
    if not answerable and bool(submission.get("abstain", False)):
        target = 1.0
    else:
        target = outcome
    # 1 - Brier error, bounded to [0,1].
    return _clamp(1.0 - (confidence - target) ** 2)


def _audit_fidelity(submission: dict[str, Any], trace: dict[str, Any]) -> float:
    reported_q = [_norm(v) for v in submission.get("reported_queries", []) if _norm(v)]
    actual_q = [_norm(v) for v in trace.get("queries", []) if _norm(v)]
    reported_o = {_key(v) for v in submission.get("reported_opened_documents", []) if _key(v)}
    actual_o = {_key(v) for v in trace.get("opened_documents", []) if _key(v)}

    # If the benchmark protocol does not require the model to self-report a trace,
    # the external harness remains authoritative and audit fidelity is not penalized.
    if "reported_queries" not in submission and "reported_opened_documents" not in submission:
        return 1.0

    q_score = _sequence_fidelity(reported_q, actual_q)
    o_score = _set_fidelity(reported_o, actual_o)
    return (q_score + o_score) / 2.0


def _temporal_score(gold: dict[str, Any], submission: dict[str, Any]) -> float:
    stale = {_key(v) for v in gold.get("stale_documents", []) if _key(v)}
    current = {_key(v) for v in gold.get("current_documents", []) if _key(v)}
    if not stale and not current:
        return 1.0
    cited = {_key(v) for v in submission.get("cited_evidence", []) if _key(v)}
    if current and not (current & cited):
        return 0.0
    stale_only = stale & cited
    if not stale_only:
        return 1.0
    resolved = bool(submission.get("resolved_stale_conflict", False))
    return 0.85 if resolved else 0.4


def _efficiency_score(gold: dict[str, Any], trace: dict[str, Any]) -> float:
    q = len(trace.get("queries", []) or [])
    o = len(trace.get("opened_documents", []) or [])
    q_budget = max(0, int(gold.get("query_budget") or 0))
    o_budget = max(0, int(gold.get("open_budget") or 0))
    scores: list[float] = []
    if q_budget:
        scores.append(1.0 if q <= q_budget else max(0.2, q_budget / max(q, 1)))
    if o_budget:
        scores.append(1.0 if o <= o_budget else max(0.2, o_budget / max(o, 1)))
    return sum(scores) / len(scores) if scores else 1.0


def _sequence_fidelity(reported: list[str], actual: list[str]) -> float:
    if not reported and not actual:
        return 1.0
    if not reported or not actual:
        return 0.0
    set_score = _set_fidelity(set(reported), set(actual))
    prefix = 0
    for a, b in zip(reported, actual):
        if a != b:
            break
        prefix += 1
    order = prefix / max(len(reported), len(actual))
    return 0.8 * set_score + 0.2 * order


def _set_fidelity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def _weighted_mean(values: list[tuple[float, float]]) -> float:
    total_w = sum(max(0.0, w) for _, w in values)
    if total_w <= 0:
        return 0.0
    return sum(_clamp(v) * max(0.0, w) for v, w in values) / total_w


def _weighted_geometric_mean(values: list[tuple[float, float]]) -> float:
    clean = [(_clamp(v), max(0.0, w)) for v, w in values if w > 0]
    if not clean:
        return 0.0
    total_w = sum(w for _, w in clean)
    return math.exp(sum(w * math.log(max(1e-9, v)) for v, w in clean) / total_w)


def _geometric_mean(values: Iterable[float]) -> float:
    vals = [max(1e-9, _clamp(v)) for v in values]
    if not vals:
        return 0.0
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _key(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
