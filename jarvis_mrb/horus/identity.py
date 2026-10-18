"""Identity Resolver / evidence-debugging public research (Ariadne + Cerberus).

Implements the future.md "Identity Resolver" section as an evidence-quality engine:
biographical attributes are *claims* with source lineage, never facts; broker
results are lead generators; corroboration counts independent origins only; known
contamination hypotheses are generated and tested; aliases are hypothesis sets;
surprise drives extra verification, not rejection; salience thresholds and separate
retrieval/disclosure/action/retention permissions minimise what is surfaced.

This module performs no lookups itself.  It reasons over claims a caller has
already gathered from lawful, purpose-appropriate sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Iterable

from jarvis_mrb.horus._util import plain, stable_id

SOURCE_WEIGHTS = {
    "primary_record": 0.9,  # e.g. licensing board, court record, official filing
    "person_specific_professional": 0.85,  # employer staff page, own professional profile
    "commercial_public": 0.7,  # deliberately public business listing
    "news": 0.65,
    "archive": 0.6,
    "broker": 0.25,  # people-search aggregator: lead generator only
    "derivative": 0.15,
}
SENSITIVE_ATTRIBUTES = {"residential_address", "phone", "email", "relative", "date_of_birth", "household_member"}
PROFESSIONAL_ATTRIBUTES = {"employer", "title", "business", "license", "publication", "seller_contact"}


@dataclass
class IdentityClaim:
    subject: str
    attribute: str
    value: str
    source: str
    source_type: str
    retrieved_at: datetime
    upstream: str = ""  # origin dataset when known (lineage)
    period: str = ""  # e.g. "2015-2018"
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = stable_id(self.subject, self.attribute, self.value, self.source, length=12)

    @property
    def origin(self) -> str:
        return self.upstream or self.source

    @property
    def weight(self) -> float:
        return SOURCE_WEIGHTS.get(self.source_type, 0.3)


@dataclass
class Relationship:
    a: str
    b: str
    kind: str  # relative | spouse | household | same_address | colleague


@dataclass
class ClaimAssessment:
    subject: str
    attribute: str
    value: str
    status: str  # verified | supported | lead_only | contested | unknown
    confidence: float
    independent_origins: int
    supporting: list[str]
    contradicting: list[str]
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    surprise: float = 0.0
    required_verification_rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return plain(self)


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().replace(".", ""), b.lower().replace(".", "")).ratio()


def cluster_aliases(names: Iterable[str], threshold: float = 0.85) -> list[dict[str, Any]]:
    """'Also seen as' is a hypothesis set.  Near-identical spellings cluster as likely
    transcription variants; distinct names stay separate hypotheses (possible
    contamination), and no reason for a name change is inferred."""
    clusters: list[list[str]] = []
    for n in names:
        for c in clusters:
            if max(name_similarity(n, m) for m in c) >= threshold:
                c.append(n)
                break
        else:
            clusters.append([n])
    return [
        {"names": c, "interpretation": "likely spelling/transcription variants" if len(c) > 1 else "distinct name hypothesis",
         "status": "hypothesis"}
        for c in clusters
    ]


class IdentityGraph:
    def __init__(self) -> None:
        self.claims: list[IdentityClaim] = []
        self.relationships: list[Relationship] = []
        self.same_name_entities: dict[str, list[str]] = {}

    def add_claim(self, claim: IdentityClaim) -> None:
        self.claims.append(claim)

    def add_relationship(self, rel: Relationship) -> None:
        self.relationships.append(rel)

    def register_same_name(self, name: str, entity_ids: list[str]) -> None:
        self.same_name_entities[name] = entity_ids

    def related(self, subject: str) -> list[tuple[str, str]]:
        out = []
        for r in self.relationships:
            if r.a == subject:
                out.append((r.b, r.kind))
            elif r.b == subject:
                out.append((r.a, r.kind))
        return out

    def claims_for(self, subject: str, attribute: str | None = None) -> list[IdentityClaim]:
        return [c for c in self.claims if c.subject == subject and (attribute is None or c.attribute == attribute)]

    # ---- contamination hypotheses
    def contamination_hypotheses(self, claim: IdentityClaim) -> list[dict[str, Any]]:
        hyps = []
        own_support = [c for c in self.claims_for(claim.subject, claim.attribute)
                       if c.value == claim.value and c.source_type not in ("broker", "derivative")]
        for other, kind in self.related(claim.subject):
            if kind in ("relative", "spouse", "household", "same_address"):
                theirs = [c for c in self.claims_for(other, claim.attribute)
                          if c.value == claim.value and c.weight >= 0.6]
                if theirs and not own_support:
                    hyps.append({
                        "type": "HOUSEHOLD_RELATIVE_ATTRIBUTE_CONTAMINATION",
                        "explanation": f"{claim.attribute}={claim.value} is independently supported for {kind} {other}, "
                                       f"not for {claim.subject}",
                        "discriminating_evidence": [
                            f"person-specific record tying {claim.subject} to {claim.value}",
                            f"archived directory listing for {claim.value}",
                        ],
                        "status": "candidate",
                    })
        for name, entities in self.same_name_entities.items():
            if claim.subject in entities and len(entities) > 1:
                hyps.append({"type": "SAME_NAME_ENTITY_MERGE",
                             "explanation": f"{len(entities)} distinct people share the name {name!r}",
                             "discriminating_evidence": ["geography/time consistency", "unique identifiers"],
                             "status": "candidate"})
        if claim.attribute in ("phone", "email"):
            hyps.append({"type": "STALE_CONTACT_REASSIGNMENT",
                         "explanation": "contact points are reassigned over time",
                         "discriminating_evidence": ["recent first-party use of the contact"], "status": "candidate"})
        if claim.period:
            periods = {c.period for c in self.claims_for(claim.subject, claim.attribute) if c.period}
            if len(periods) > 1:
                hyps.append({"type": "TEMPORAL_COMBINATION",
                             "explanation": "record may combine legitimate attributes from different periods",
                             "periods": sorted(periods), "status": "candidate"})
        derivative = [c for c in self.claims if c.value == claim.value and c.attribute == claim.attribute
                      and c.subject == claim.subject and c.source_type in ("broker", "derivative")]
        if len(derivative) >= 2 and len({c.origin for c in derivative}) == 1:
            hyps.append({"type": "DERIVATIVE_REPRODUCTION",
                         "explanation": f"{len(derivative)} sites repeat one upstream origin ({derivative[0].origin})",
                         "status": "candidate"})
        return hyps

    # ---- assessment
    def assess(self, subject: str, attribute: str, value: str, *, surprise: float = 0.0,
               consequence: str = "medium") -> ClaimAssessment:
        support = [c for c in self.claims_for(subject, attribute) if c.value == value]
        contra = [c for c in self.claims_for(subject, attribute) if c.value != value and not c.period]
        origins = {c.origin for c in support}
        strong = [c for c in support if c.weight >= 0.6]
        strong_origins = {c.origin for c in strong}
        # Confidence: noisy-OR over *independent* origins, using the best weight per origin.
        best_per_origin: dict[str, float] = {}
        for c in support:
            best_per_origin[c.origin] = max(best_per_origin.get(c.origin, 0.0), c.weight)
        miss = 1.0
        for w in best_per_origin.values():
            miss *= 1.0 - w
        confidence = 1.0 - miss
        if contra:
            contra_strength = max(c.weight for c in contra)
            confidence *= 1.0 - 0.5 * contra_strength
        hyps = []
        if support:
            hyps = self.contamination_hypotheses(support[0])
        if not support:
            status = "unknown"
        elif not strong:
            status = "lead_only"
        elif contra and max(c.weight for c in contra) >= 0.6:
            status = "contested"
        elif len(strong_origins) >= 2:
            status = "verified"
        else:
            status = "supported"
        if hyps and status in ("verified", "supported") and not strong:
            status = "lead_only"
        rounds = {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(consequence, 1)
        if surprise >= 0.8 and confidence >= 0.5:
            rounds += 3
            if status == "verified" and len(strong_origins) < 3:
                status = "supported"  # extra scrutiny required before reporting as verified
        if status == "lead_only":
            rounds += 1
        return ClaimAssessment(subject, attribute, value, status, round(confidence, 4), len(origins),
                               [c.id for c in support], [c.id for c in contra], hyps, surprise, rounds)


# --------------------------------------------------------------------------- minimisation / permissions

SALIENCE_LEVELS = ("discoverable", "internally_useful", "worth_mentioning", "worth_interrupting")


@dataclass
class Purpose:
    description: str
    relevant_attributes: set[str]
    disclosure_allowed: set[str] = field(default_factory=set)
    action_allowed: bool = False
    retain: bool = False


def salience(claim: IdentityClaim, purpose: Purpose) -> str:
    if claim.attribute not in purpose.relevant_attributes:
        return "discoverable"
    if claim.attribute in SENSITIVE_ATTRIBUTES and claim.attribute not in purpose.disclosure_allowed:
        return "internally_useful"
    return "worth_mentioning"


def permissions(claim: IdentityClaim, purpose: Purpose) -> dict[str, bool]:
    """Retrieval, disclosure, action and retention are separate permissions.
    Discovering a phone or address never authorises a downstream action."""
    sensitive = claim.attribute in SENSITIVE_ATTRIBUTES
    return {
        "retrieve": claim.attribute in purpose.relevant_attributes or not sensitive,
        "disclose": claim.attribute in purpose.disclosure_allowed or (
            not sensitive and claim.attribute in purpose.relevant_attributes),
        "act": purpose.action_allowed and not sensitive,
        "retain": purpose.retain and claim.source_type != "broker",
    }


def research_receipt(graph: IdentityGraph, assessment: ClaimAssessment, purpose: Purpose) -> dict[str, Any]:
    """Auditable receipt for a material identity conclusion with minimised disclosure."""
    by_id = {c.id: c for c in graph.claims}

    def show(cid: str) -> dict[str, Any]:
        c = by_id[cid]
        perms = permissions(c, purpose)
        return {"source": c.source, "source_type": c.source_type, "origin": c.origin,
                "value": c.value if perms["disclose"] else "[withheld: not needed for purpose]",
                "retrieved_at": c.retrieved_at.isoformat()}

    roles_note = ("A listing establishes the role it states (e.g. seller/contact), "
                  "not legal ownership or other unstated roles.")
    return {
        "claim": f"{assessment.subject}.{assessment.attribute} = {assessment.value}",
        "status": assessment.status,
        "confidence": assessment.confidence,
        "independent_origins": assessment.independent_origins,
        "evidence_for": [show(c) for c in assessment.supporting],
        "evidence_against": [show(c) for c in assessment.contradicting],
        "competing_explanations": assessment.hypotheses,
        "unknown_if_unresolved": assessment.status in ("unknown", "lead_only", "contested"),
        "role_precision": roles_note,
        "purpose": purpose.description,
    }
