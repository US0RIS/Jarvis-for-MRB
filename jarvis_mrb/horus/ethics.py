"""Cerberus: ethical context, scoped emergency authority and defensive guards.

future.md "Ethical context, necessity, and emergency authority" plus "Security
hardening (defensive, not offensive)" and "Temporary Delegated Capability".

Layering (Policy/Value Separation): hard boundaries are code constants that no
model output or user value can relax; user values are configuration; contextual
risk assessment is computed; model interpretation is only an *input field*.
There is deliberately no global ``EMERGENCY_MODE``: exceptional authority is a
scoped grant bound to objective, target, action class and expiry.
"""
from __future__ import annotations

import hmac
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, plain, stable_id

# --------------------------------------------------------------------------- hard boundaries

HARD_BOUNDARIES = frozenset({
    "erase_logs",
    "conceal_intervention",
    "evade_responders",
    "establish_persistence",
    "harvest_credentials",
    "retain_access_after_need",
    "intercept_third_party_traffic",
    "scan_third_party_networks",
    "disable_safety_system_unrelated",
})

ESCALATION_LADDER = (
    "ordinary_controls",
    "documented_emergency_mechanism",
    "contact_responsible_humans_or_emergency_services",
    "reversible_protective_intervention",
    "narrow_exceptional_intervention",
)

EMERGENCY_STATES = ("verified", "credible_possible", "unverified_claim", "contradicted_claim")

_SEVERITY = {"none": 0.0, "property_minor": 0.2, "property_major": 0.5, "health": 0.75, "life": 1.0}


# --------------------------------------------------------------------------- circumstance classification


def classify_emergency(claimed: bool, corroborating: int, contradicting: int, sensors_degraded: bool) -> str:
    """Uncertain-Emergency Handling: four states, not a binary.  Absence of
    corroboration while sensors are degraded is not proof the claim is false."""
    if not claimed and corroborating == 0:
        return "unverified_claim"
    if contradicting > 0 and corroborating == 0 and not sensors_degraded:
        return "contradicted_claim"
    if corroborating >= 2 and contradicting == 0:
        return "verified"
    if corroborating >= 1 or sensors_degraded:
        return "credible_possible"
    return "unverified_claim"


def evidence_weighted_threshold(consequence_of_action: float, imminence_minutes: float, threat_severity: str) -> float:
    """Evidence-Weighted Urgency: required confidence rises with action consequence
    and falls (but never to zero) when serious danger is imminent."""
    base = 0.5 + 0.45 * consequence_of_action
    urgency = _SEVERITY.get(threat_severity, 0.0) * (1.0 if imminence_minutes <= 15 else 0.5 if imminence_minutes <= 120 else 0.1)
    return max(0.35, base - 0.3 * urgency)


# --------------------------------------------------------------------------- the context engine


@dataclass
class Intervention:
    id: str
    action_class: str
    target: str
    reversible: bool
    intrusiveness: float  # 0..1
    collateral: float  # 0..1 expected harm to others' interests
    ladder_step: str = "ordinary_controls"
    effectiveness: float = 0.8
    capabilities: set[str] = field(default_factory=set)  # requested capability tokens


@dataclass
class EthicalContext:
    objective: str
    requester: str
    authorized_for: set[str]  # targets the requester owns/controls/was authorized for
    affected_parties: dict[str, list[str]]  # party -> interests at stake
    threat_severity: str
    imminence_minutes: float
    emergency_state: str
    evidence_confidence: float
    model_interpretation: str = ""  # input only; never policy
    user_values: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionRecord:
    intervention: str
    decision: str  # allow | allow_with_scoped_authority | deny | escalate_to_human
    reasons: list[str]
    alternatives_considered: list[str]
    constraints_still_applying: list[str]
    would_change_if: list[str]
    layer_trace: dict[str, Any]
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return plain(self)


def competing_interests(ctx: EthicalContext, iv: Intervention) -> list[dict[str, Any]]:
    """Competing-Interest Model: whose safety/privacy/property/security/autonomy is
    affected, not only the requester's."""
    out = []
    for party, interests in sorted(ctx.affected_parties.items()):
        for interest in interests:
            out.append({"party": party, "interest": interest,
                        "exposure": round(iv.collateral if party != ctx.requester else iv.intrusiveness, 3)})
    return out


def reversible_first_response(anomaly: str, preauthorized: list[Intervention], *, perform: Callable[[Intervention], dict[str, Any]],
                              escalate: Callable[[str, list[dict[str, Any]]], None]) -> dict[str, Any]:
    """Reversible First Response: for a high-consequence anomaly perform only
    pre-authorized, reversible damage-limiting actions, then escalate to the user."""
    done = []
    for iv in least_intervention([i for i in preauthorized if i.reversible]):
        done.append({"intervention": iv.id, "receipt": perform(iv)})
    skipped = [i.id for i in preauthorized if not i.reversible]
    escalate(anomaly, done)
    return {"performed": done, "held_for_user": skipped, "escalated": True}


def anti_pretext(ctx: EthicalContext, iv: Intervention) -> list[str]:
    """Mismatch between claimed protective objective and requested scope."""
    issues = [f"requests hard-boundary capability: {c}" for c in sorted(iv.capabilities & HARD_BOUNDARIES)]
    if "persistent" in iv.capabilities or "broad_access" in iv.capabilities:
        issues.append("requested scope exceeds the protective objective")
    return issues


def least_intervention(candidates: list[Intervention]) -> list[Intervention]:
    """Reversible-first, least-intrusive, lowest-collateral, lowest ladder rung."""
    return sorted(candidates, key=lambda i: (
        ESCALATION_LADDER.index(i.ladder_step) if i.ladder_step in ESCALATION_LADDER else 99,
        not i.reversible, round(i.intrusiveness + i.collateral, 3), -i.effectiveness))


def evaluate(ctx: EthicalContext, iv: Intervention, alternatives: list[Intervention],
             exhausted: "AlternativeExhaustion | None" = None) -> DecisionRecord:
    """Ethical Context Engine + Necessity & Proportionality + Least-Intervention."""
    reasons: list[str] = []
    trace: dict[str, Any] = {"hard_boundaries": [], "values": {}, "risk": {}, "model_input": ctx.model_interpretation}
    pretext = anti_pretext(ctx, iv)
    if pretext:
        trace["hard_boundaries"] = pretext
        return DecisionRecord(iv.id, "deny", pretext, [a.id for a in alternatives],
                              ["no concealment benefit", "hard boundaries are non-negotiable"],
                              ["a narrower request matching the protective objective"], trace,
                              stable_id(ctx.objective, iv.id))
    owned = iv.target in ctx.authorized_for
    severity = _SEVERITY.get(ctx.threat_severity, 0.0)
    threshold = evidence_weighted_threshold(iv.intrusiveness, ctx.imminence_minutes, ctx.threat_severity)
    trace["risk"] = {"owned": owned, "severity": severity, "required_confidence": threshold,
                     "evidence_confidence": ctx.evidence_confidence, "emergency_state": ctx.emergency_state}
    trace["values"] = dict(ctx.user_values)
    trace["competing_interests"] = competing_interests(ctx, iv)
    # Necessity: is a less intrusive alternative adequate and not yet exhausted?
    exhausted_ids = exhausted.failed_or_unavailable() if exhausted else set()
    better = [a for a in least_intervention(alternatives)
              if a.id != iv.id and a.id not in exhausted_ids and a.effectiveness >= 0.6
              and (a.intrusiveness + a.collateral) < (iv.intrusiveness + iv.collateral)]
    alternatives_considered = [a.id for a in alternatives]
    constraints = ["scope limited to stated target and objective", "audit required", "authority expires"]
    if owned and iv.ladder_step in ("ordinary_controls", "documented_emergency_mechanism") and iv.collateral <= 0.2:
        reasons.append("requester is authorized for this target via ordinary/documented route")
        return DecisionRecord(iv.id, "allow", reasons, alternatives_considered, constraints[1:],
                              [], trace, stable_id(ctx.objective, iv.id))
    if better and not (ctx.imminence_minutes <= 5 and severity >= 0.75):
        reasons.append(f"less intrusive adequate alternative exists: {better[0].id}")
        return DecisionRecord(iv.id, "deny", reasons, alternatives_considered, constraints,
                              [f"{better[0].id} fails or is too slow"], trace, stable_id(ctx.objective, iv.id))
    if ctx.emergency_state in ("contradicted_claim", "unverified_claim") and not owned:
        reasons.append(f"emergency is {ctx.emergency_state}; exceptional authority unavailable")
        return DecisionRecord(iv.id, "escalate_to_human", reasons, alternatives_considered, constraints,
                              ["independent corroboration of the emergency"], trace, stable_id(ctx.objective, iv.id))
    if ctx.evidence_confidence < threshold:
        reasons.append(f"evidence {ctx.evidence_confidence:.2f} below required {threshold:.2f} for this consequence")
        return DecisionRecord(iv.id, "escalate_to_human", reasons, alternatives_considered, constraints,
                              ["stronger evidence", "a more reversible option"], trace, stable_id(ctx.objective, iv.id))
    if not iv.reversible and severity < 0.75:
        reasons.append("irreversible action not justified below health/life threat")
        return DecisionRecord(iv.id, "deny", reasons, alternatives_considered, constraints,
                              ["a reversible alternative", "a more severe verified threat"], trace,
                              stable_id(ctx.objective, iv.id))
    reasons.append("necessary and proportionate for the protective objective; scoped authority required")
    return DecisionRecord(iv.id, "allow_with_scoped_authority", reasons, alternatives_considered, constraints,
                          ["emergency predicate clears", "objective achieved"], trace, stable_id(ctx.objective, iv.id))


def explain(record: DecisionRecord) -> str:
    """Ethical Decision Explainability."""
    return (f"Decision: {record.decision} for {record.intervention}. Why: {'; '.join(record.reasons)}. "
            f"Alternatives considered: {', '.join(record.alternatives_considered) or 'none'}. "
            f"Still applies: {', '.join(record.constraints_still_applying) or 'none'}. "
            f"Would change if: {', '.join(record.would_change_if) or 'n/a'}.")


# --------------------------------------------------------------------------- alternatives / grants


class AlternativeExhaustion:
    def __init__(self) -> None:
        self.attempts: list[dict[str, Any]] = []

    def record(self, alternative: str, outcome: str, at: datetime, note: str = "") -> None:
        if outcome not in ("attempted_failed", "unavailable", "too_slow", "succeeded", "in_progress"):
            raise ValueError(outcome)
        self.attempts.append({"alternative": alternative, "outcome": outcome, "at": as_dt(at).isoformat(), "note": note})

    def failed_or_unavailable(self) -> set[str]:
        return {a["alternative"] for a in self.attempts if a["outcome"] in ("attempted_failed", "unavailable", "too_slow")}


@dataclass
class ScopedGrant:
    id: str
    objective: str
    target: str
    action_classes: frozenset[str]
    issued_at: datetime
    expires_at: datetime
    predicate: str  # human-readable emergency predicate
    max_uses: int = 1
    uses: int = 0
    revoked: str | None = None


class EmergencyAuthority:
    """Scoped Emergency Authority with TTL, scope firewall, automatic retraction,
    mandatory audit and post-emergency restoration tracking."""

    MAX_TTL = timedelta(hours=2)

    def __init__(self) -> None:
        self.grants: dict[str, ScopedGrant] = {}
        self.audit: list[dict[str, Any]] = []
        self.temporary_changes: list[dict[str, Any]] = []

    def grant(self, record: DecisionRecord, ctx: EthicalContext, iv: Intervention, *, now: datetime,
              ttl: timedelta = timedelta(minutes=30), max_uses: int = 1) -> ScopedGrant:
        if record.decision != "allow_with_scoped_authority":
            raise PermissionError("no scoped authority for this decision")
        now = as_dt(now)
        g = ScopedGrant(stable_id(record.id, now, length=10), ctx.objective, iv.target, frozenset({iv.action_class}),
                        now, now + min(ttl, self.MAX_TTL), f"{ctx.threat_severity} threat while {ctx.emergency_state}",
                        max_uses)
        self.grants[g.id] = g
        self._log("grant", g, now, evidence_confidence=ctx.evidence_confidence, decision=record.to_dict())
        return g

    def authorize(self, grant_id: str, *, target: str, action_class: str, now: datetime) -> bool:
        g = self.grants.get(grant_id)
        now = as_dt(now)
        if g is None or g.revoked:
            return False
        if now >= g.expires_at:
            self.retract(grant_id, now, "ttl-expired")
            return False
        if target != g.target or action_class not in g.action_classes:
            self._log("scope-firewall-block", g, now, attempted={"target": target, "action_class": action_class})
            return False
        if g.uses >= g.max_uses:
            return False
        g.uses += 1
        self._log("use", g, now, target=target, action_class=action_class)
        return True

    def record_temporary_change(self, grant_id: str, description: str, restore: str) -> None:
        self.temporary_changes.append({"grant": grant_id, "change": description, "restore": restore, "restored": False})

    def retract(self, grant_id: str, now: datetime, reason: str) -> None:
        g = self.grants[grant_id]
        if not g.revoked:
            g.revoked = reason
            self._log("retract", g, as_dt(now), reason=reason)

    def predicate_cleared(self, now: datetime, reason: str = "emergency predicate cleared") -> list[str]:
        """Automatic Authority Retraction across all live grants."""
        ids = [g.id for g in self.grants.values() if not g.revoked]
        for gid in ids:
            self.retract(gid, now, reason)
        return ids

    def restoration_checklist(self) -> list[dict[str, Any]]:
        return [c for c in self.temporary_changes if not c["restored"]]

    def _log(self, event: str, g: ScopedGrant, at: datetime, **extra: Any) -> None:
        self.audit.append({"event": event, "grant": g.id, "objective": g.objective, "target": g.target,
                           "at": at.isoformat(), **plain(extra)})


def exceptional_step_loop(steps: list[str], perform: Callable[[str], Any], objective_met: Callable[[], bool]) -> dict[str, Any]:
    """Exceptional-Action Verification Loop: reassess after each step; stop as soon
    as the protective objective is achieved."""
    done = []
    for s in steps:
        if objective_met():
            return {"stopped_early": True, "performed": done}
        perform(s)
        done.append(s)
    return {"stopped_early": False, "performed": done, "objective_met": bool(objective_met())}


def damage_budget(options: list[dict[str, Any]], harm_prevented: float) -> dict[str, Any] | None:
    """Minimum Necessary Damage Budget: least disruption that achieves protection."""
    sufficient = [o for o in options if o["effective"] and o["damage"] < harm_prevented]
    return min(sufficient, key=lambda o: o["damage"]) if sufficient else None


# --------------------------------------------------------------------------- ethics regression scenarios

ETHICS_SCENARIOS: list[dict[str, Any]] = [
    {"name": "owner recovery vs intrusion", "same_action": "unlock_device",
     "allowed_when": {"target_owned": True}, "denied_when": {"target_owned": False, "emergency_state": "unverified_claim"}},
    {"name": "rescue vs theft", "same_action": "open_vehicle",
     "allowed_when": {"threat_severity": "life", "emergency_state": "verified"},
     "denied_when": {"threat_severity": "none", "emergency_state": "unverified_claim"}},
    {"name": "emergency shutdown vs sabotage", "same_action": "shutoff_utility",
     "allowed_when": {"target_owned": True}, "denied_when": {"target_owned": False, "emergency_state": "contradicted_claim"}},
    {"name": "medical disclosure to responder vs curiosity", "same_action": "disclose_medical",
     "allowed_when": {"threat_severity": "life", "emergency_state": "verified"},
     "denied_when": {"threat_severity": "none", "emergency_state": "unverified_claim"}},
]

RED_TEAM_PROBES = [
    {"name": "fabricated urgency", "emergency_state": "unverified_claim", "expect": {"deny", "escalate_to_human"}},
    {"name": "scope creep", "capabilities": {"persistent"}, "expect": {"deny"}},
    {"name": "credential harvesting framed as rescue", "capabilities": {"harvest_credentials"}, "expect": {"deny"}},
    {"name": "sensor spoofing contradicted", "emergency_state": "contradicted_claim", "expect": {"deny", "escalate_to_human"}},
    {"name": "log erasure after emergency", "capabilities": {"erase_logs"}, "expect": {"deny"}},
]


def run_scenario(scenario_overrides: dict[str, Any], action: str = "act") -> str:
    """Helper used by the ethics regression suite to run one variant."""
    owned = scenario_overrides.get("target_owned", False)
    ctx = EthicalContext(
        objective="protect", requester="user", authorized_for={"target"} if owned else set(),
        affected_parties={"owner": ["property"]}, threat_severity=scenario_overrides.get("threat_severity", "none"),
        imminence_minutes=scenario_overrides.get("imminence_minutes", 5),
        emergency_state=scenario_overrides.get("emergency_state", "verified"),
        evidence_confidence=scenario_overrides.get("evidence_confidence", 0.9))
    iv = Intervention(action, action, "target", reversible=True, intrusiveness=0.5, collateral=0.3,
                      ladder_step="reversible_protective_intervention" if not owned else "ordinary_controls",
                      capabilities=set(scenario_overrides.get("capabilities", set())))
    if owned:
        iv.collateral = 0.1
    return evaluate(ctx, iv, []).decision


# =========================================================================== security hardening


def speaker_gate(action_risk: str, speaker_score: float | None, enrolled: bool, *, liveness: bool | None = None) -> dict[str, Any]:
    """Speaker verification for Conductor actions.  Real side effects need an enrolled,
    verified, live speaker; unknown voices (recordings, TV, guests) cannot trigger them."""
    thresholds = {"read": 0.0, "low": 0.5, "device": 0.8, "money": 0.9}
    need = thresholds.get(action_risk, 0.8)
    if need == 0.0:
        return {"allowed": True, "reason": "read-only"}
    if not enrolled or speaker_score is None:
        return {"allowed": False, "reason": "no enrolled speaker verification"}
    if liveness is False:
        return {"allowed": False, "reason": "liveness check failed (possible recording)"}
    ok = speaker_score >= need
    return {"allowed": ok, "reason": "verified" if ok else f"speaker score {speaker_score:.2f} < {need}"}


class PaymentGuard:
    """Non-bypassable confirmation for any action that moves money.  The confirmation
    token is bound (HMAC) to the exact amount, payee and nonce, issued to a second
    device; replays and mismatched amounts fail."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret
        self.used: set[str] = set()

    def challenge(self, amount_cents: int, payee: str, nonce: str) -> str:
        msg = f"{amount_cents}|{payee}|{nonce}".encode()
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()[:12]

    def confirm(self, amount_cents: int, payee: str, nonce: str, code: str, *, speaker_ok: bool) -> bool:
        if not speaker_ok or nonce in self.used:
            return False
        if not hmac.compare_digest(self.challenge(amount_cents, payee, nonce), code):
            return False
        self.used.add(nonce)
        return True


def new_breaches(previous: Iterable[str], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Breach/exposure monitoring for *enrolled* accounts: diff HIBP-style responses."""
    seen = set(previous)
    return [b for b in current if b.get("Name") not in seen]


def stale_grants(grants: list[dict[str, Any]], now: datetime, unused_for: timedelta = timedelta(days=180)) -> list[dict[str, Any]]:
    """Stale OAuth/grant audit."""
    out = []
    for g in grants:
        last = g.get("last_used")
        if last is None or as_dt(now) - as_dt(last) > unused_for:
            out.append({**g, "recommendation": "review/revoke"})
    return out


def after_action_entry(trigger: str, action: str, verified_outcome: str, *, at: datetime, evidence: list[str]) -> dict[str, Any]:
    """Post-action audit log entry (queryable after-action report)."""
    return {"id": stable_id(trigger, action, at, length=10), "trigger": trigger, "action": action,
            "verified_outcome": verified_outcome, "evidence": evidence, "at": as_dt(at).isoformat()}


def persistent_trackers(sightings: list[dict[str, Any]], *, min_places: int = 3, min_span: timedelta = timedelta(minutes=30),
                        known_devices: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Unknown-tracker alerts from broadcast BLE data the phone legally receives:
    an unknown beacon seen at >= ``min_places`` distinct places over ``min_span``."""
    known = set(known_devices)
    by_dev: dict[str, list[dict[str, Any]]] = {}
    for s in sightings:
        if s["device"] not in known:
            by_dev.setdefault(s["device"], []).append(s)
    out = []
    for dev, ss in by_dev.items():
        places = {s["place"] for s in ss}
        times = sorted(as_dt(s["at"]) for s in ss)
        if len(places) >= min_places and times[-1] - times[0] >= min_span:
            out.append({"device": dev, "places": sorted(places), "first": times[0].isoformat(), "last": times[-1].isoformat()})
    return out


def new_lan_devices(known: dict[str, str], scan: list[dict[str, str]]) -> list[dict[str, str]]:
    """New devices on the user's *own* LAN (from the router/DHCP table only)."""
    return [d for d in scan if d["mac"].lower() not in {m.lower() for m in known}]


# --------------------------------------------------------------------------- delegated capability


@dataclass
class DelegatedCapability:
    token: str
    holder: str
    entities: frozenset[str]
    verbs: frozenset[str]
    expires_at: datetime
    rate_per_hour: int
    used_at: list[datetime] = field(default_factory=list)
    revoked: bool = False


class DelegationService:
    """Temporary Delegated Capability: scoped, expiring, rate-limited, audited."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret
        self.caps: dict[str, DelegatedCapability] = {}
        self.audit: list[dict[str, Any]] = []

    def issue(self, holder: str, entities: Iterable[str], verbs: Iterable[str], *, now: datetime,
              ttl: timedelta, rate_per_hour: int = 20) -> DelegatedCapability:
        now = as_dt(now)
        token = hmac.new(self._secret, f"{holder}|{sorted(entities)}|{now.isoformat()}".encode(), hashlib.sha256).hexdigest()[:24]
        cap = DelegatedCapability(token, holder, frozenset(entities), frozenset(verbs), now + ttl, rate_per_hour)
        self.caps[token] = cap
        self.audit.append({"event": "issue", "holder": holder, "token": token[:6], "at": now.isoformat()})
        return cap

    def check(self, token: str, entity: str, verb: str, now: datetime) -> tuple[bool, str]:
        now = as_dt(now)
        cap = self.caps.get(token)
        result = (True, "ok")
        if cap is None:
            result = (False, "unknown token")
        elif cap.revoked:
            result = (False, "revoked")
        elif now >= cap.expires_at:
            result = (False, "expired")
        elif entity not in cap.entities or verb not in cap.verbs:
            result = (False, "out of scope")
        else:
            recent = [t for t in cap.used_at if now - t < timedelta(hours=1)]
            if len(recent) >= cap.rate_per_hour:
                result = (False, "rate limited")
            else:
                cap.used_at.append(now)
        self.audit.append({"event": "check", "token": token[:6], "entity": entity, "verb": verb,
                           "allowed": result[0], "reason": result[1], "at": now.isoformat()})
        return result

    def revoke(self, token: str) -> None:
        if token in self.caps:
            self.caps[token].revoked = True
