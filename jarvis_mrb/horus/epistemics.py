"""Epistemic Freshness Gate and evidence bookkeeping (Kant / Ariadne).

Implements the future.md "Epistemic Freshness Gate" section plus the small evidence
ideas that share its machinery:

* claim classes (stable, user-supplied, local-observed, externally-verified, inferred,
  current-unverified) with ``as_of``/``verified_at``/``source_ids``/``freshness_ttl``;
* a deterministic pre-model freshness router that detects mutable-world claims;
* configurable freshness TTL policy (Observation TTLs);
* the contradiction trigger (user evidence vs model prior -> live lookup, nobody wins);
* evidence-bound answer checking and a post-generation epistemic linter;
* truthful degraded answers when search fails (tool absence is not evidence);
* verification receipts;
* confidence decay, contradiction detection between sources, a source reputation
  ledger, frozen evidence snapshots, claim lineage, and uncertainty display labels.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from jarvis_mrb.horus._util import as_dt, clamp, plain, stable_id

# --------------------------------------------------------------------------- claim classes

STABLE = "stable"
USER_SUPPLIED = "user-supplied"
LOCAL_OBSERVED = "local-observed"
EXTERNALLY_VERIFIED = "externally-verified"
INFERRED = "inferred"
CURRENT_UNVERIFIED = "current-unverified"
CLAIM_CLASSES = (STABLE, USER_SUPPLIED, LOCAL_OBSERVED, EXTERNALLY_VERIFIED, INFERRED, CURRENT_UNVERIFIED)

# Freshness categories with default TTLs (seconds).  ``None`` = no live refresh needed.
DEFAULT_TTLS: dict[str, float | None] = {
    "traffic": 10 * 60,
    "weather": 15 * 60,
    "outage": 10 * 60,
    "incident": 15 * 60,
    "flight": 10 * 60,
    "sports": 15 * 60,
    "price": 60 * 60,
    "inventory": 30 * 60,
    "availability": 30 * 60,
    "schedule": 6 * 3600,
    "release": 6 * 3600,
    "news": 3 * 3600,
    "public_post": 3 * 3600,
    "software_version": 24 * 3600,
    "model_version": 24 * 3600,
    "law_policy": 7 * 24 * 3600,
    "public_official": 7 * 24 * 3600,
    "election": 6 * 3600,
    "operating_status": 60 * 60,
    "generic_current": 60 * 60,
    "stable": None,
}

_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("traffic", r"\b(traffic|congestion|commute time|road closure|accident on)\b"),
    ("weather", r"\b(weather|forecast|rain(?:ing)?|snow(?:ing)?|temperature|storm|wind|heat advisory)\b"),
    ("outage", r"\b(outage|is (?:it )?down|service status|power cut|blackout)\b"),
    ("incident", r"\b(incident|wildfire|earthquake|evacuat\w+|shooting|explosion)\b"),
    ("flight", r"\b(flight|gate change|delayed|departure|arrival|boarding)\b"),
    ("sports", r"\b(score|won|lost|game tonight|match result|standings)\b"),
    ("price", r"\b(price|cost(?:s)?|how much|\$\d|on sale|discount)\b"),
    ("inventory", r"\b(in stock|out of stock|inventory|restock)\b"),
    ("availability", r"\b(still available|available|sold out|open now|reservation)\b"),
    ("schedule", r"\b(schedule|timetable|hours|opening time|closing time)\b"),
    ("release", r"\b(released?|launch(?:ed)?|announc\w+|unveil\w*|new model|new version)\b"),
    ("news", r"\b(news|breaking|reported|headline)\b"),
    ("public_post", r"\b(posted|tweet(?:ed)?|blog post|press release)\b"),
    ("software_version", r"\b(version \d|v\d+\.\d+|latest version|update(?:d)? to)\b"),
    ("model_version", r"\b(gpt-?\d|claude|gemini|llama|gemma|qwen)\b"),
    ("law_policy", r"\b(law|regulation|policy|rule change|statute|ordinance)\b"),
    ("public_official", r"\b(president|governor|mayor|senator|ceo of|prime minister)\b"),
    ("election", r"\b(election|poll(?:s|ing)?|ballot|vote count)\b"),
    ("operating_status", r"\b(open|closed|operating|running)\b.*\b(today|now|currently)\b"),
]
_TEMPORAL_MARKERS = r"\b(today|tonight|just|currently|right now|now|latest|still|this (?:week|morning|year)|new|recent(?:ly)?|yet)\b"


@dataclass
class Claim:
    text: str
    claim_class: str
    category: str = "stable"
    as_of: datetime | None = None
    verified_at: datetime | None = None
    source_ids: list[str] = field(default_factory=list)
    freshness_ttl: float | None = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if self.claim_class not in CLAIM_CLASSES:
            raise ValueError(f"unknown claim class {self.claim_class!r}")

    def needs_refresh(self, now: datetime | None = None, policy: "FreshnessPolicy | None" = None) -> bool:
        if self.claim_class == STABLE:
            return False
        ttl = self.freshness_ttl
        if ttl is None:
            ttl = (policy or FreshnessPolicy()).ttl(self.category)
        if ttl is None:
            return False
        if self.verified_at is None:
            return True
        return (as_dt(now) - as_dt(self.verified_at)).total_seconds() > ttl

    def to_dict(self) -> dict[str, Any]:
        return plain(self)


class FreshnessPolicy:
    """Configurable, testable freshness TTLs (Observation TTLs / Freshness TTLs)."""

    def __init__(self, overrides: dict[str, float | None] | None = None) -> None:
        self.ttls = dict(DEFAULT_TTLS)
        self.ttls.update(overrides or {})

    def ttl(self, category: str) -> float | None:
        return self.ttls.get(category, self.ttls["generic_current"])

    def is_fresh(self, category: str, observed_at: datetime, now: datetime | None = None) -> bool:
        ttl = self.ttl(category)
        if ttl is None:
            return True
        return (as_dt(now) - as_dt(observed_at)).total_seconds() <= ttl


# --------------------------------------------------------------------------- routing


@dataclass(frozen=True)
class FreshnessRoute:
    requires_live_lookup: bool
    categories: tuple[str, ...]
    reasons: tuple[str, ...]
    contradiction: bool = False


def classify_categories(text: str) -> list[str]:
    lowered = str(text or "").lower()
    return [name for name, pattern in _CATEGORY_PATTERNS if re.search(pattern, lowered)]


def route_claim(
    text: str,
    *,
    user_evidence_conflicts_with_prior: bool = False,
    live_source_available: bool = True,
) -> FreshnessRoute:
    """Deterministic pre-model gate.

    The model may help phrase the query but cannot veto this routing because a claim
    "sounds fake".  A conflict between user evidence and model memory is itself a
    trigger (contradiction trigger), regardless of category.
    """
    categories = classify_categories(text)
    temporal = bool(re.search(_TEMPORAL_MARKERS, str(text or "").lower()))
    reasons: list[str] = []
    if categories:
        reasons.append("mutable-category:" + ",".join(categories))
    if temporal:
        reasons.append("temporal-marker")
        if not categories:
            categories = ["generic_current"]
    if user_evidence_conflicts_with_prior:
        reasons.append("user-evidence-conflicts-with-model-prior")
        if not categories:
            categories = ["generic_current"]
    needs = bool(reasons)
    if needs and not live_source_available:
        reasons.append("live-source-unavailable:answer-must-be-marked-current-unverified")
    return FreshnessRoute(needs, tuple(categories), tuple(reasons), user_evidence_conflicts_with_prior)


# --------------------------------------------------------------------------- evidence


@dataclass
class Evidence:
    id: str
    source: str
    observed_at: datetime
    supports: list[str]  # claim texts / claim ids this item supports
    kind: str = "direct"  # direct | corroborative | conflicting
    first_party: bool = False
    url: str = ""
    category: str = "generic_current"
    upstream: str = ""  # lineage: id of the upstream origin if derivative

    def fresh(self, policy: FreshnessPolicy, now: datetime | None = None) -> bool:
        return policy.is_fresh(self.category, self.observed_at, now)


@dataclass
class VerificationReceipt:
    claim: str
    provider: str
    query: str
    checked_at: datetime
    sources: list[dict[str, Any]]
    verdict: str  # supported | contradicted | conflicting | unverified
    claim_support: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return plain(self)


def verify_claim(
    claim: str,
    evidence: list[Evidence],
    *,
    provider: str,
    query: str,
    now: datetime | None = None,
    policy: FreshnessPolicy | None = None,
    search_failed: bool = False,
) -> VerificationReceipt:
    """Adjudicate a current claim from evidence only, producing a receipt."""
    policy = policy or FreshnessPolicy()
    now = as_dt(now)
    usable = [e for e in evidence if e.fresh(policy, now)]
    support = [e for e in usable if claim in e.supports and e.kind != "conflicting"]
    against = [e for e in usable if claim in e.supports and e.kind == "conflicting"]
    if search_failed or not usable:
        verdict = "unverified"
    elif support and against:
        verdict = "conflicting"
    elif support:
        verdict = "supported"
    elif against:
        verdict = "contradicted"
    else:
        verdict = "unverified"
    return VerificationReceipt(
        claim=claim,
        provider=provider,
        query=query,
        checked_at=now,
        sources=[
            {"id": e.id, "source": e.source, "observed_at": e.observed_at, "kind": e.kind,
             "first_party": e.first_party, "url": e.url}
            for e in usable
        ],
        verdict=verdict,
        claim_support={claim: [e.id for e in support]},
    )


def degraded_answer(claim: str, reason: str = "the live source is unavailable") -> str:
    """Truthful answer when verification is impossible.  Never a negation."""
    return f"I can't verify whether {claim.rstrip('.?!')} because {reason}. That is unverified, not false."


def answer_for_receipt(receipt: VerificationReceipt) -> str:
    if receipt.verdict == "supported":
        names = ", ".join(sorted({s["source"] for s in receipt.sources}))
        return f"Verified: {receipt.claim} (sources: {names}; checked {receipt.checked_at.isoformat()})."
    if receipt.verdict == "contradicted":
        return f"Current sources contradict: {receipt.claim}."
    if receipt.verdict == "conflicting":
        return f"Sources disagree about: {receipt.claim}. Both positions are shown with their sources."
    return degraded_answer(receipt.claim, "no fresh evidence was found")


# Order sequence guard for the evidence-before-explanation rule.
class AdjudicationSequence:
    """Enforces classify -> verify -> (only then) forensic analysis."""

    def __init__(self) -> None:
        self.steps: list[str] = []

    def classify(self) -> None:
        self.steps.append("classify")

    def verify(self, receipt: VerificationReceipt) -> None:
        if "classify" not in self.steps:
            raise RuntimeError("classify before verify")
        self.steps.append("verify:" + receipt.verdict)

    def forensic_analysis(self, observations: list[str]) -> dict[str, Any]:
        if not any(s.startswith("verify:") for s in self.steps):
            raise RuntimeError("evidence-before-explanation: verify the underlying fact first")
        self.steps.append("forensics")
        verified = next(s for s in reversed(self.steps) if s.startswith("verify:")).split(":", 1)[1]
        return {
            "source_verification": verified,
            "image_forensic_hypotheses": [{"observation": o, "status": "hypothesis"} for o in observations],
            "note": "A suspicious artifact does not prove the represented event did not occur.",
        }


# --------------------------------------------------------------------------- linter

CERTAINTY_WORDS = (
    "definitely", "certainly", "never happened", "doesn't exist", "does not exist", "fake",
    "hoax", "still", "today", "currently", "right now", "confirmed", "no such",
)


@dataclass
class LintFinding:
    sentence: str
    problem: str
    words: list[str] = field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "")) if s.strip()]


def lint_answer(
    answer: str,
    evidence: list[Evidence],
    *,
    now: datetime | None = None,
    policy: FreshnessPolicy | None = None,
) -> list[LintFinding]:
    """Post-generation epistemic linter.

    Each sentence that makes a current-world assertion must be supported by a fresh
    evidence item (matched by ``supports`` substring) or explicitly say "unverified".
    Unsupported certainty words are flagged, and expired evidence forces a refresh.
    """
    policy = policy or FreshnessPolicy()
    findings: list[LintFinding] = []
    for sentence in split_sentences(answer):
        lowered = sentence.lower()
        if "unverified" in lowered or "can't verify" in lowered or "cannot verify" in lowered:
            continue
        route = route_claim(sentence)
        hits = [w for w in CERTAINTY_WORDS if re.search(r"\b" + re.escape(w) + r"\b", lowered)]
        if not route.requires_live_lookup and not hits:
            continue
        matching = [e for e in evidence if any(s.lower() in lowered or lowered in s.lower() for s in e.supports)]
        fresh = [e for e in matching if e.fresh(policy, now)]
        if matching and not fresh:
            findings.append(LintFinding(sentence, "evidence-expired:refresh-required", hits))
        elif not matching:
            findings.append(LintFinding(sentence, "unsupported-current-claim", hits))
    return findings


def enforce_evidence_bound(answer: str, evidence: list[Evidence], **kwargs: Any) -> str:
    """Rewrite unsupported current claims as explicitly unverified."""
    flagged = {f.sentence for f in lint_answer(answer, evidence, **kwargs)}
    out = []
    for sentence in split_sentences(answer):
        out.append(f"[unverified] {sentence}" if sentence in flagged else sentence)
    return " ".join(out)


# --------------------------------------------------------------------------- decay / contradiction / reputation


def decayed_confidence(confidence: float, observed_at: datetime, now: datetime | None = None,
                       half_life_s: float = 3600.0) -> float:
    """Confidence decay: inferred physical state fades without corroboration."""
    age = max(0.0, (as_dt(now) - as_dt(observed_at)).total_seconds())
    return clamp(confidence * math.pow(0.5, age / half_life_s))


@dataclass
class SourceAssertion:
    source: str
    entity: str
    attribute: str
    value: Any
    observed_at: datetime


def detect_contradictions(assertions: list[SourceAssertion], *, trusted: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Flag (entity, attribute) pairs where trusted sources disagree, instead of choosing one."""
    allowed = set(trusted) if trusted is not None else None
    groups: dict[tuple[str, str], list[SourceAssertion]] = {}
    for a in assertions:
        if allowed is not None and a.source not in allowed:
            continue
        groups.setdefault((a.entity, a.attribute), []).append(a)
    out = []
    for (entity, attribute), items in sorted(groups.items()):
        values = {repr(i.value) for i in items}
        if len(values) > 1:
            out.append({
                "entity": entity,
                "attribute": attribute,
                "positions": [{"source": i.source, "value": i.value, "observed_at": i.observed_at.isoformat()} for i in items],
            })
    return out


class SourceReputationLedger:
    """Empirical reliability/freshness per source (Beta posterior), used in fusion."""

    def __init__(self) -> None:
        self.stats: dict[str, dict[str, float]] = {}

    def record(self, source: str, *, correct: bool, latency_s: float | None = None) -> None:
        s = self.stats.setdefault(source, {"ok": 0.0, "bad": 0.0, "latency_sum": 0.0, "latency_n": 0.0})
        s["ok" if correct else "bad"] += 1
        if latency_s is not None:
            s["latency_sum"] += latency_s
            s["latency_n"] += 1

    def reliability(self, source: str) -> float:
        s = self.stats.get(source, {"ok": 0.0, "bad": 0.0})
        return (s["ok"] + 1.0) / (s["ok"] + s["bad"] + 2.0)

    def mean_latency(self, source: str) -> float | None:
        s = self.stats.get(source)
        if not s or not s["latency_n"]:
            return None
        return s["latency_sum"] / s["latency_n"]

    def fuse(self, positions: list[tuple[str, Any]]) -> dict[str, Any]:
        """Reliability-weighted vote; returns best value plus its weighted share."""
        weights: dict[str, float] = {}
        labels: dict[str, Any] = {}
        for source, value in positions:
            key = repr(value)
            labels[key] = value
            weights[key] = weights.get(key, 0.0) + self.reliability(source)
        if not weights:
            return {"value": None, "confidence": 0.0}
        total = sum(weights.values())
        best = max(weights, key=lambda k: weights[k])
        return {"value": labels[best], "confidence": weights[best] / total, "contested": len(weights) > 1}

    def to_dict(self) -> dict[str, Any]:
        return {"stats": self.stats}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceReputationLedger":
        ledger = cls()
        ledger.stats = {k: dict(v) for k, v in data.get("stats", {}).items()}
        return ledger


# --------------------------------------------------------------------------- snapshots / lineage / labels


@dataclass(frozen=True)
class EvidenceSnapshot:
    id: str
    conclusion: str
    frozen_at: str
    evidence: tuple[dict[str, Any], ...]


def freeze_evidence(conclusion: str, evidence: list[Evidence], now: datetime | None = None) -> EvidenceSnapshot:
    """Evidence snapshots: immutable copy of the exact evidence behind a conclusion."""
    items = tuple(plain(e) for e in sorted(evidence, key=lambda e: e.id))
    frozen_at = as_dt(now).isoformat()
    return EvidenceSnapshot(stable_id(conclusion, items), conclusion, frozen_at, items)


@dataclass
class LineageNode:
    id: str
    stage: str  # raw_observation | extraction | inference | corroboration | conclusion
    text: str
    parents: list[str] = field(default_factory=list)


class ClaimLineage:
    STAGES = ("raw_observation", "extraction", "inference", "corroboration", "conclusion")

    def __init__(self) -> None:
        self.nodes: dict[str, LineageNode] = {}

    def add(self, stage: str, text: str, parents: Iterable[str] = ()) -> str:
        if stage not in self.STAGES:
            raise ValueError(stage)
        parents = list(parents)
        for p in parents:
            if p not in self.nodes:
                raise KeyError(p)
        node_id = stable_id(stage, text, parents, length=12)
        self.nodes[node_id] = LineageNode(node_id, stage, text, parents)
        return node_id

    def expand(self, node_id: str) -> list[dict[str, Any]]:
        """Return the chain from raw observations down to ``node_id`` (topological)."""
        seen: list[str] = []

        def visit(n: str) -> None:
            for p in self.nodes[n].parents:
                visit(p)
            if n not in seen:
                seen.append(n)

        visit(node_id)
        return [plain(self.nodes[n]) for n in seen]

    def raw_sources(self, node_id: str) -> list[str]:
        return [n["text"] for n in self.expand(node_id) if n["stage"] == "raw_observation"]


UNCERTAINTY_LABELS = {
    "observed": {"glyph": "●", "label": "Directly observed", "style": "solid"},
    "verified": {"glyph": "◉", "label": "Externally verified", "style": "solid"},
    "inferred": {"glyph": "◐", "label": "Inferred", "style": "dashed"},
    "stale": {"glyph": "◌", "label": "Stale", "style": "faded"},
    "unknown": {"glyph": "?", "label": "Unknown / no evidence", "style": "hatched"},
}


def uncertainty_label(claim: Claim, now: datetime | None = None, policy: FreshnessPolicy | None = None) -> dict[str, str]:
    """Uncertainty UI: map a claim to a visually distinct status token."""
    if claim.claim_class in (CURRENT_UNVERIFIED,) or (not claim.source_ids and claim.claim_class != STABLE
                                                      and claim.claim_class != USER_SUPPLIED):
        key = "unknown"
    elif claim.needs_refresh(now, policy):
        key = "stale"
    elif claim.claim_class == INFERRED:
        key = "inferred"
    elif claim.claim_class == LOCAL_OBSERVED:
        key = "observed"
    else:
        key = "verified"
    return {"status": key, **UNCERTAINTY_LABELS[key]}


def epistemic_cutoff_guard(model_prior_says_false: bool, receipt: VerificationReceipt | None) -> str:
    """Pass condition from the acceptance tests: never confidently negate a mutable
    external fact without fresh evidence.  ``model_prior_says_false`` is accepted
    deliberately and ignored: the model prior has no vote."""
    if receipt is None or receipt.verdict == "unverified":
        return "unverified"
    if receipt.verdict == "supported":
        return "true"
    if receipt.verdict == "contradicted":
        return "false"
    return "conflicting"

