"""Ariadne: intelligence-analysis primitives and bounded investigation.

Covers future.md: Analysis of Competing Hypotheses, Key-Assumption Register,
Assumption Expiry, Disconfirm-Me Mode, Evidence Diagnosticity Scoring,
Information-Gain Planner, Source Independence Graph, Collection Plan Generator,
Investigation Stop Rule, Alternative-Explanation Prompt, Analytic Confidence
Calibration, Autonomous Investigation, Surprise-weighted verification, the
Counterfactual Engine / Shadow Reality, Sensor-Fusion Superresolution, and the
Physical Consequence Graph.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, clamp, plain

# --------------------------------------------------------------------------- ACH

# Consistency codes: CC strongly consistent, C consistent, N neutral, I inconsistent,
# II strongly inconsistent.  Likelihood of the evidence under the hypothesis.
_LIKELIHOOD = {"CC": 0.9, "C": 0.7, "N": 0.5, "I": 0.3, "II": 0.1}


@dataclass
class EvidenceItem:
    id: str
    description: str
    reliability: float = 0.8  # source reliability 0..1
    source: str = ""


class ACHMatrix:
    """Analysis of Competing Hypotheses with reliability-weighted Bayesian scoring."""

    def __init__(self, hypotheses: Iterable[str], priors: dict[str, float] | None = None) -> None:
        self.hypotheses = list(hypotheses)
        if len(self.hypotheses) < 2:
            raise ValueError("ACH needs at least two competing hypotheses")
        p = priors or {}
        self.priors = {h: float(p.get(h, 1.0)) for h in self.hypotheses}
        self.evidence: dict[str, EvidenceItem] = {}
        self.ratings: dict[tuple[str, str], str] = {}

    def add_evidence(self, item: EvidenceItem, ratings: dict[str, str]) -> None:
        self.evidence[item.id] = item
        for h in self.hypotheses:
            code = ratings.get(h, "N")
            if code not in _LIKELIHOOD:
                raise ValueError(code)
            self.ratings[(item.id, h)] = code

    def _likelihood(self, eid: str, h: str) -> float:
        base = _LIKELIHOOD[self.ratings.get((eid, h), "N")]
        r = self.evidence[eid].reliability
        return r * base + (1 - r) * 0.5  # unreliable evidence regresses to neutral

    def posteriors(self) -> dict[str, float]:
        logp = {h: math.log(self.priors[h]) for h in self.hypotheses}
        for eid in self.evidence:
            for h in self.hypotheses:
                logp[h] += math.log(self._likelihood(eid, h))
        m = max(logp.values())
        exp = {h: math.exp(v - m) for h, v in logp.items()}
        z = sum(exp.values())
        return {h: exp[h] / z for h in self.hypotheses}

    def inconsistency_scores(self) -> dict[str, float]:
        """Heuer's ACH emphasis: rank by evidence *against*, not for."""
        scores = {h: 0.0 for h in self.hypotheses}
        for (eid, h), code in self.ratings.items():
            if code == "I":
                scores[h] += self.evidence[eid].reliability
            elif code == "II":
                scores[h] += 2 * self.evidence[eid].reliability
        return scores

    def diagnosticity(self, eid: str) -> float:
        """Spread of likelihoods across hypotheses; 0 = consistent with all (useless)."""
        values = [self._likelihood(eid, h) for h in self.hypotheses]
        return max(values) - min(values)

    def rank_evidence(self) -> list[tuple[str, float]]:
        return sorted(((e, self.diagnosticity(e)) for e in self.evidence), key=lambda x: -x[1])

    def summary(self) -> dict[str, Any]:
        post = self.posteriors()
        return {
            "posteriors": post,
            "leading": max(post, key=post.get),
            "inconsistency": self.inconsistency_scores(),
            "evidence_by_diagnosticity": self.rank_evidence(),
            "non_diagnostic": [e for e, d in self.rank_evidence() if d < 0.05],
        }


def entropy(dist: dict[str, float]) -> float:
    return -sum(p * math.log2(p) for p in dist.values() if p > 0)


@dataclass
class CandidateObservation:
    id: str
    cost: float
    # outcome -> {hypothesis: P(outcome | hypothesis)}
    outcomes: dict[str, dict[str, float]]
    lawful: bool = True
    authorized: bool = True


def expected_information_gain(prior: dict[str, float], obs: CandidateObservation) -> float:
    h0 = entropy(prior)
    expected = 0.0
    for likelihoods in obs.outcomes.values():
        p_outcome = sum(prior[h] * likelihoods.get(h, 0.0) for h in prior)
        if p_outcome <= 0:
            continue
        posterior = {h: prior[h] * likelihoods.get(h, 0.0) / p_outcome for h in prior}
        expected += p_outcome * entropy(posterior)
    return h0 - expected


def plan_next_observation(prior: dict[str, float], candidates: list[CandidateObservation]) -> list[dict[str, Any]]:
    """Information-Gain Planner: only lawful/authorized observations, ranked by gain/cost."""
    ranked = []
    for c in candidates:
        if not (c.lawful and c.authorized):
            continue
        gain = expected_information_gain(prior, c)
        ranked.append({"id": c.id, "gain_bits": round(gain, 4), "cost": c.cost,
                       "value": round(gain / max(c.cost, 1e-9), 4)})
    return sorted(ranked, key=lambda r: -r["value"])


# --------------------------------------------------------------------------- assumptions


@dataclass
class Assumption:
    id: str
    statement: str
    supports: list[str]  # conclusions that depend on it
    valid_until: datetime | None = None
    invalidated_by: list[str] = field(default_factory=list)  # evidence keywords
    status: str = "holding"  # holding | expired | invalidated


class KeyAssumptionRegister:
    def __init__(self) -> None:
        self.assumptions: dict[str, Assumption] = {}
        self.reopened: list[dict[str, Any]] = []

    def add(self, a: Assumption) -> None:
        self.assumptions[a.id] = a

    def check(self, *, now: datetime | None = None, new_evidence: Iterable[str] = ()) -> list[str]:
        """Return conclusions that must be reopened (assumption expiry / invalidation)."""
        now = as_dt(now)
        texts = [t.lower() for t in new_evidence]
        reopened: list[str] = []
        for a in self.assumptions.values():
            if a.status != "holding":
                continue
            if a.valid_until is not None and now > as_dt(a.valid_until):
                a.status = "expired"
            elif any(k.lower() in t for k in a.invalidated_by for t in texts):
                a.status = "invalidated"
            else:
                continue
            for c in a.supports:
                if c not in reopened:
                    reopened.append(c)
            self.reopened.append({"assumption": a.id, "status": a.status, "conclusions": list(a.supports),
                                  "at": now.isoformat()})
        return reopened


def disconfirmation_queries(conclusion: str, assumptions: Iterable[str] = ()) -> list[str]:
    """Disconfirm-Me Mode: queries designed to find evidence that the conclusion is wrong."""
    c = conclusion.rstrip(".")
    queries = [
        f"evidence against: {c}",
        f"{c} false OR incorrect OR debunked",
        f"alternative explanation for {c}",
        f"what would have to be true if NOT ({c})",
    ]
    queries += [f"is it still true that {a.rstrip('.')}" for a in assumptions]
    return queries


ALTERNATIVE_TEMPLATES = (
    "measurement or sensor error produced the observation",
    "a common upstream source explains the agreement",
    "a different actor/entity with similar attributes",
    "timing coincidence rather than causation",
    "the observation is stale and the state has since changed",
)


def alternative_explanations(conclusion: str, impact: str, domain_alternatives: Iterable[str] = ()) -> list[str]:
    """Alternative-Explanation Prompt: high-impact conclusions get >=1 material alternative."""
    alts = list(domain_alternatives)
    if impact in ("high", "critical"):
        alts.extend(a for a in ALTERNATIVE_TEMPLATES if a not in alts)
    return alts


# --------------------------------------------------------------------------- source independence


class SourceIndependenceGraph:
    """Detect reports that trace back to one origin so corroboration isn't overstated."""

    def __init__(self) -> None:
        self.parent: dict[str, str | None] = {}

    def add_report(self, report: str, derived_from: str | None = None) -> None:
        self.parent[report] = derived_from
        if derived_from is not None:
            self.parent.setdefault(derived_from, None)

    def origin(self, report: str) -> str:
        seen = set()
        cur = report
        while self.parent.get(cur) is not None and cur not in seen:
            seen.add(cur)
            cur = self.parent[cur]  # type: ignore[assignment]
        return cur

    def independent_count(self, reports: Iterable[str]) -> int:
        return len({self.origin(r) for r in reports})

    def clusters(self, reports: Iterable[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for r in reports:
            out.setdefault(self.origin(r), []).append(r)
        return out


# --------------------------------------------------------------------------- collection / stop


@dataclass
class InformationNeed:
    fact: str
    sources: list[str]
    expected_value: float
    cost: float


def collection_plan(question: str, needs: list[InformationNeed], *, budget: float,
                    target_confidence: float = 0.8) -> dict[str, Any]:
    ordered = sorted(needs, key=lambda n: -(n.expected_value / max(n.cost, 1e-9)))
    chosen, spent = [], 0.0
    for n in ordered:
        if spent + n.cost <= budget:
            chosen.append(n)
            spent += n.cost
    return {
        "question": question,
        "steps": [plain(n) for n in chosen],
        "deferred": [n.fact for n in ordered if n not in chosen],
        "budget": budget,
        "estimated_cost": spent,
        "stopping_conditions": [
            f"leading hypothesis posterior >= {target_confidence}",
            "budget exhausted",
            "remaining observations have negligible expected information gain",
        ],
    }


def should_stop(posteriors: dict[str, float], *, threshold: float, spent: float, budget: float,
                best_remaining_gain_bits: float = 0.0, min_gain_bits: float = 0.05) -> tuple[bool, str]:
    """Investigation Stop Rule tied to the decision at hand."""
    lead = max(posteriors.values()) if posteriors else 0.0
    if lead >= threshold:
        return True, "decision-threshold-reached"
    if spent >= budget:
        return True, "budget-exhausted:report-uncertainty"
    if best_remaining_gain_bits < min_gain_bits:
        return True, "no-informative-observation-left:report-unknown"
    return False, "continue"


# --------------------------------------------------------------------------- calibration


class ConfidenceCalibrator:
    """Analytic Confidence Calibration per domain (Brier score + reliability bins)."""

    def __init__(self) -> None:
        self.records: dict[str, list[tuple[float, bool]]] = {}

    def record(self, domain: str, stated_confidence: float, outcome_true: bool) -> None:
        self.records.setdefault(domain, []).append((clamp(stated_confidence), bool(outcome_true)))

    def brier(self, domain: str) -> float | None:
        r = self.records.get(domain)
        if not r:
            return None
        return sum((p - (1.0 if o else 0.0)) ** 2 for p, o in r) / len(r)

    def adjust(self, domain: str, confidence: float, bins: int = 5) -> float:
        """Map a raw confidence to the observed hit-rate in its bin (shrunk to raw)."""
        r = self.records.get(domain, [])
        idx = min(bins - 1, int(confidence * bins))
        in_bin = [o for p, o in r if min(bins - 1, int(p * bins)) == idx]
        if not in_bin:
            return confidence
        observed = sum(in_bin) / len(in_bin)
        weight = len(in_bin) / (len(in_bin) + 5.0)
        return clamp(weight * observed + (1 - weight) * confidence)

    def language(self, domain: str, confidence: float) -> str:
        c = self.adjust(domain, confidence)
        if c >= 0.95:
            return "almost certainly"
        if c >= 0.8:
            return "very likely"
        if c >= 0.6:
            return "likely"
        if c >= 0.4:
            return "roughly even odds"
        if c >= 0.2:
            return "unlikely"
        return "very unlikely"


# --------------------------------------------------------------------------- surprise-weighted verification


def verification_depth(confidence: float, surprise: float, *, consequence: str = "medium",
                       source_quality: float = 0.5, independent_sources: int = 1) -> dict[str, Any]:
    """Surprise is a verification trigger, never a falsification criterion.

    Depth also depends on consequence, source quality and independence so ordinary
    but wrong claims still receive systematic verification.
    """
    systematic = {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(consequence, 1)
    if source_quality < 0.5:
        systematic += 1
    if independent_sources < 2 and consequence in ("high", "critical"):
        systematic += 1
    if confidence < 0.5:
        action, extra = "qualify-and-investigate", 2
    elif surprise >= 0.8:
        action, extra = "aggressively-corroborate-before-reporting", 3
    else:
        action, extra = "report-normally", 0
    return {"action": action, "verification_rounds": systematic + extra,
            "may_discard_for_surprise": False}


# --------------------------------------------------------------------------- autonomous investigation


@dataclass
class InvestigationStep:
    observation_id: str
    outcome: str
    posteriors: dict[str, float]


def run_investigation(
    hypotheses: dict[str, float],
    candidates: list[CandidateObservation],
    observe: Callable[[str], str],
    *,
    threshold: float = 0.85,
    budget: float = 10.0,
) -> dict[str, Any]:
    """Bounded "figure out what's happening" loop: maintain competing hypotheses, pick
    the most informative lawful observation, update, stop by rule."""
    z = sum(hypotheses.values())
    post = {h: p / z for h, p in hypotheses.items()}
    remaining = list(candidates)
    spent = 0.0
    steps: list[InvestigationStep] = []
    while True:
        plan = plan_next_observation(post, remaining)
        best_gain = plan[0]["gain_bits"] if plan else 0.0
        stop, reason = should_stop(post, threshold=threshold, spent=spent, budget=budget,
                                   best_remaining_gain_bits=best_gain)
        if stop:
            break
        choice = next(c for c in remaining if c.id == plan[0]["id"])
        if spent + choice.cost > budget:
            reason = "budget-exhausted:report-uncertainty"
            break
        remaining.remove(choice)
        spent += choice.cost
        outcome = observe(choice.id)
        lik = choice.outcomes.get(outcome, {})
        unnorm = {h: post[h] * lik.get(h, 1e-6) for h in post}
        z = sum(unnorm.values()) or 1.0
        post = {h: v / z for h, v in unnorm.items()}
        steps.append(InvestigationStep(choice.id, outcome, dict(post)))
    lead = max(post, key=post.get)
    return {
        "best_explanation": lead if post[lead] >= threshold else None,
        "leading_hypothesis": lead,
        "posteriors": post,
        "stop_reason": reason,
        "spent": spent,
        "steps": [plain(s) for s in steps],
        "uncertainty": round(entropy(post), 4),
    }


# --------------------------------------------------------------------------- counterfactual engine


def simulate(
    state: dict[str, Any],
    scenario: Callable[[dict[str, Any], random.Random], dict[str, Any]],
    *,
    outcome: Callable[[dict[str, Any]], float],
    runs: int = 500,
    seed: int = 7,
) -> dict[str, Any]:
    """Counterfactual Engine / Shadow Reality: fork state, apply a stochastic scenario,
    report a distribution (p10/p50/p90), never a single 'prediction'."""
    rng = random.Random(seed)
    values = []
    for _ in range(runs):
        fork = dict(state)
        values.append(float(outcome(scenario(fork, rng))))
    values.sort()

    def pct(q: float) -> float:
        return values[min(len(values) - 1, int(q * len(values)))]

    return {"runs": runs, "p10": pct(0.1), "p50": pct(0.5), "p90": pct(0.9),
            "min": values[0], "max": values[-1], "framing": "simulation, not prediction"}


def departure_time(arrive_by: datetime, legs_minutes: dict[str, tuple[float, float]], *,
                   on_time_probability: float = 0.9, runs: int = 2000, seed: int = 11) -> dict[str, Any]:
    """Shadow-reality departure planner.  Each leg is (mean, stdev) minutes; returns the
    latest departure that arrives on time with the requested probability."""
    rng = random.Random(seed)
    totals = sorted(
        sum(max(0.0, rng.gauss(mu, sd)) for mu, sd in legs_minutes.values()) for _ in range(runs)
    )
    needed = totals[min(runs - 1, int(on_time_probability * runs))]
    return {
        "leave_by": (as_dt(arrive_by) - timedelta(minutes=needed)).isoformat(),
        "buffer_minutes": round(needed, 1),
        "median_trip_minutes": round(totals[runs // 2], 1),
        "on_time_probability": on_time_probability,
    }


# --------------------------------------------------------------------------- sensor fusion superresolution


@dataclass
class DerivedFact:
    statement: str
    confidence: float
    inputs: list[dict[str, Any]]
    rule: str
    label: str = "derived"


def fuse_estimates(name: str, estimates: list[tuple[str, float, float]]) -> DerivedFact:
    """Inverse-variance fusion of independent numeric estimates (source, value, sigma).
    The result is labelled derived and carries provenance for each input."""
    if not estimates:
        raise ValueError("no estimates")
    weights = [(s, v, 1.0 / max(sd, 1e-9) ** 2) for s, v, sd in estimates]
    total = sum(w for _, _, w in weights)
    value = sum(v * w for _, v, w in weights) / total
    sigma = math.sqrt(1.0 / total)
    return DerivedFact(
        statement=f"{name} ≈ {value:.3f} ± {sigma:.3f}",
        confidence=clamp(1.0 - sigma / (abs(value) + sigma + 1e-9)),
        inputs=[{"source": s, "value": v, "sigma": sd} for s, v, sd in estimates],
        rule="inverse-variance",
    )


# --------------------------------------------------------------------------- consequence graph


class ConsequenceGraph:
    """Physical Consequence Graph: prioritise by expected downstream consequence."""

    def __init__(self) -> None:
        self.edges: dict[str, list[tuple[str, float]]] = {}
        self.severity: dict[str, float] = {}

    def add(self, cause: str, effect: str, probability: float) -> None:
        self.edges.setdefault(cause, []).append((effect, probability))

    def set_severity(self, node: str, severity: float) -> None:
        self.severity[node] = severity

    def expected_consequence(self, node: str, _depth: int = 0, _p: float = 1.0) -> float:
        if _depth > 8:
            return 0.0
        total = _p * self.severity.get(node, 0.0)
        for effect, prob in self.edges.get(node, []):
            total += self.expected_consequence(effect, _depth + 1, _p * prob)
        return total

    def prioritize(self, active: Iterable[str]) -> list[tuple[str, float]]:
        return sorted(((n, round(self.expected_consequence(n), 4)) for n in active), key=lambda x: -x[1])
