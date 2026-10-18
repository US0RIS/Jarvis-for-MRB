"""User Belief Model: what the user believes, and the gap to verified state (Mnemosyne).

future.md: "world changed + user probably did not update + user is about to act on
stale state = intervene now."  Beliefs are estimates with provenance and confidence;
the model prefers direct exposure evidence (opened, viewed, acknowledged, discussed)
over assumptions and returns ``unknown`` when it cannot establish a belief.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from jarvis_mrb.horus._util import as_dt, plain

# Strength of evidence that the user actually absorbed a value.
EXPOSURE_WEIGHTS = {
    "explicit_acknowledgment": 0.95,
    "user_stated": 0.95,  # the user said the value themselves
    "spoken_discussion": 0.8,
    "viewed_document": 0.7,
    "opened_message": 0.55,
    "notification_delivered": 0.3,
    "sent_to_user_unopened": 0.1,
    "assumed": 0.05,
}


@dataclass
class Exposure:
    fact_key: str
    value: Any
    kind: str
    at: datetime
    evidence_ref: str = ""

    def weight(self) -> float:
        return EXPOSURE_WEIGHTS.get(self.kind, 0.05)


@dataclass
class VerifiedFact:
    fact_key: str
    value: Any
    verified_at: datetime
    changed_at: datetime
    source_ids: list[str] = field(default_factory=list)


@dataclass
class PendingAction:
    action: str
    depends_on: list[str]
    due_at: datetime
    irreversible: bool = False
    consequence: str = "medium"  # low | medium | high | critical


@dataclass
class BeliefEstimate:
    fact_key: str
    believed_value: Any
    confidence: float
    formed_at: datetime | None
    basis: list[dict[str, Any]]
    status: str  # known | unknown

    def to_dict(self) -> dict[str, Any]:
        return plain(self)


_CONSEQUENCE = {"low": 0.25, "medium": 0.5, "high": 0.8, "critical": 1.0}


class UserBeliefModel:
    def __init__(self, min_confidence: float = 0.3) -> None:
        self.exposures: list[Exposure] = []
        self.facts: dict[str, VerifiedFact] = {}
        self.min_confidence = min_confidence
        # Delivery alone (unopened, notification) is not evidence the user absorbed a change.
        self.meaningful_exposure = 0.5

    # ---- ingestion
    def record_exposure(self, exposure: Exposure) -> None:
        self.exposures.append(exposure)

    def record_fact(self, fact: VerifiedFact) -> None:
        self.facts[fact.fact_key] = fact

    # ---- estimation
    def estimate(self, fact_key: str) -> BeliefEstimate:
        relevant = sorted((e for e in self.exposures if e.fact_key == fact_key), key=lambda e: e.at)
        if not relevant:
            return BeliefEstimate(fact_key, None, 0.0, None, [], "unknown")
        # The most recent exposure strong enough to form a belief wins; weaker later
        # exposures only partially overwrite (the user may not have noticed them).
        believed = None
        confidence = 0.0
        formed_at = None
        basis = []
        for e in relevant:
            w = e.weight()
            basis.append({"kind": e.kind, "value": e.value, "at": e.at.isoformat(), "ref": e.evidence_ref})
            if believed is None or repr(e.value) == repr(believed):
                if believed is None or w > confidence:
                    formed_at = e.at
                believed = e.value
                confidence = max(confidence, w)
            elif w >= confidence * 0.75 or w >= 0.7:
                believed, confidence, formed_at = e.value, w, e.at
            else:
                confidence = max(0.0, confidence - w * 0.5)
        if confidence < self.min_confidence:
            return BeliefEstimate(fact_key, believed, confidence, formed_at, basis, "unknown")
        return BeliefEstimate(fact_key, believed, confidence, formed_at, basis, "known")

    def divergence(self, fact_key: str) -> dict[str, Any] | None:
        fact = self.facts.get(fact_key)
        if fact is None:
            return None
        belief = self.estimate(fact_key)
        stale = belief.status == "known" and repr(belief.believed_value) != repr(fact.value)
        exposed_to_change = any(
            e.fact_key == fact_key and repr(e.value) == repr(fact.value) and e.at >= fact.changed_at
            and e.weight() >= self.meaningful_exposure
            for e in self.exposures
        )
        return {
            "fact_key": fact_key,
            "verified_value": fact.value,
            "believed_value": belief.believed_value,
            "belief_status": belief.status,
            "belief_confidence": belief.confidence,
            "stale_belief": stale,
            "exposed_to_change": exposed_to_change,
            "changed_at": fact.changed_at.isoformat(),
            "last_belief_update": belief.formed_at.isoformat() if belief.formed_at else None,
        }

    def interventions(self, actions: list[PendingAction], now: datetime | None = None,
                      horizon_s: float = 24 * 3600) -> list[dict[str, Any]]:
        """Decision-relevant belief divergence: only changes the user has not absorbed
        that an imminent action depends on, ranked by urgency x consequence."""
        now = as_dt(now)
        out = []
        for action in actions:
            remaining = (as_dt(action.due_at) - now).total_seconds()
            if remaining < 0 or remaining > horizon_s:
                continue
            for key in action.depends_on:
                d = self.divergence(key)
                if not d or not d["stale_belief"] or d["exposed_to_change"]:
                    continue
                urgency = 1.0 - remaining / horizon_s
                score = (0.5 * urgency + 0.5 * _CONSEQUENCE.get(action.consequence, 0.5)) * d["belief_confidence"]
                if action.irreversible:
                    score = min(1.0, score + 0.2)
                minutes_left = int(remaining // 60)
                out.append({
                    **d,
                    "action": action.action,
                    "minutes_until_action": minutes_left,
                    "score": round(score, 4),
                    "message": (
                        f"{key} changed to {d['verified_value']!r}; you were never exposed to the change "
                        f"(you likely still believe {d['believed_value']!r}) and '{action.action}' "
                        f"is in {minutes_left} minutes."
                    ),
                })
        return sorted(out, key=lambda x: -x["score"])
