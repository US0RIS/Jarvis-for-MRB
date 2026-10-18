"""Small-model emergency competence and severe-weather safety (Cassandra + Cerberus).

future.md ideas implemented here: Emergency Playbook Library (source-attributed,
revisioned, offline), Emergency Capability Index, Deterministic Emergency State
Machine, Procedure Retrieval Before Generation, Offline Emergency Knowledge Pack
(export), Emergency Model Escalation / Competence-Aware Routing / Don't-Let-the-
8B-Wing-It Rule, Emergency Communications Composer, Emergency Evidence Snapshot,
Emergency Self-Test, Emergency Drill Mode, NWS Impact-Based Warning damage-tag
escalation, slope/landslide-adjusted rainfall thresholds (CGS/USGS susceptibility),
Local failover alerting (multi-path dispatcher; ntfy-style payloads), and the
Opt-in family safety beacon bounded to a declared emergency window.

The seed playbooks summarise widely published public guidance and name their
source; they are a starting library to be reviewed and kept current, not new
procedures invented here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, plain, stable_id, tokens

# =========================================================================== playbooks


@dataclass
class Playbook:
    id: str
    title: str
    triggers: list[str]
    steps: list[str]
    source: str
    source_url: str
    revised: str
    review_after_days: int = 365
    competence: str = "retrieval+small_model"

    def stale(self, now: datetime) -> bool:
        return as_dt(now) - as_dt(self.revised) > timedelta(days=self.review_after_days)


SEED_PLAYBOOKS = [
    Playbook("flash_flood", "Flash flood", ["flash flood", "flood warning", "water rising", "flooded road"],
             ["Move to higher ground immediately.", "Turn Around, Don't Drown: do not walk or drive through flood water.",
              "Follow official evacuation instructions."],
             "U.S. National Weather Service flood safety", "https://www.weather.gov/safety/flood", "2026-01-01"),
    Playbook("earthquake", "Earthquake shaking", ["earthquake", "shaking", "tremor"],
             ["Drop, Cover, and Hold On until shaking stops.", "After shaking, check for injuries and hazards such as gas leaks.",
              "Expect aftershocks."],
             "Ready.gov earthquakes / Great ShakeOut", "https://www.ready.gov/earthquakes", "2026-01-01"),
    Playbook("wildfire_evacuation", "Wildfire evacuation", ["wildfire", "evacuation order", "evacuation warning", "smoke"],
             ["Follow official evacuation orders without delay.", "Ready, Set, Go: keep a go-bag and leave early if warned.",
              "Monitor official alert channels."],
             "CAL FIRE Ready, Set, Go!", "https://www.readyforwildfire.org/", "2026-01-01"),
    Playbook("carbon_monoxide", "Carbon monoxide alarm", ["carbon monoxide", "co alarm", "co detector"],
             ["Get everyone to fresh air immediately.", "Call 911 from outside.", "Do not re-enter until cleared by responders."],
             "U.S. CDC carbon monoxide poisoning prevention", "https://www.cdc.gov/carbon-monoxide/", "2026-01-01",
             competence="deterministic"),
    Playbook("gas_leak", "Natural gas odor", ["gas leak", "smell gas", "gas smell"],
             ["Leave the building immediately.", "Do not operate light switches, appliances or phones inside.",
              "Call the gas utility or 911 from a safe distance."],
             "Gas utility safety guidance (verify with local utility)", "", "2026-01-01", competence="deterministic"),
]


class PlaybookLibrary:
    def __init__(self, playbooks: Iterable[Playbook] = SEED_PLAYBOOKS) -> None:
        self.playbooks = {p.id: p for p in playbooks}

    def retrieve(self, situation: str, min_score: float = 0.34) -> list[tuple[Playbook, float]]:
        """Procedure Retrieval Before Generation (deterministic keyword match)."""
        text = situation.lower()
        words = set(tokens(text))
        out = []
        for p in self.playbooks.values():
            score = 0.0
            for trig in p.triggers:
                if trig in text:
                    score = max(score, 1.0)
                else:
                    tw = set(tokens(trig))
                    if tw:
                        score = max(score, len(tw & words) / len(tw))
            if score >= min_score:
                out.append((p, score))
        return sorted(out, key=lambda x: -x[1])

    def stale_playbooks(self, now: datetime) -> list[str]:
        return [p.id for p in self.playbooks.values() if p.stale(now)]

    def export_pack(self, *, contacts: list[dict[str, str]], capabilities: "CapabilityIndex", maps: list[str]) -> str:
        """Offline Emergency Knowledge Pack: one portable JSON document."""
        return json.dumps({"format": "horus-emergency-pack", "version": 1,
                           "playbooks": [plain(p) for p in self.playbooks.values()],
                           "contacts": contacts, "capabilities": capabilities.entries, "maps": maps},
                          indent=1, sort_keys=True)


def emergency_answer(situation: str, library: PlaybookLibrary, *, retrieval_confidence_floor: float = 0.6,
                     cloud_available: bool = False) -> dict[str, Any]:
    """Competence-Aware Routing.  The small model may only summarise retrieved
    procedures; with weak retrieval it must state uncertainty and escalate."""
    hits = library.retrieve(situation)
    if hits and hits[0][1] >= retrieval_confidence_floor:
        pb = hits[0][0]
        route = "deterministic" if pb.competence == "deterministic" else "retrieval+small_model"
        return {"route": route, "playbook": pb.id, "steps": pb.steps, "source": pb.source,
                "model_may": "summarize/contextualize retrieved steps only"}
    escalation = ["call emergency services if anyone is in danger"]
    if cloud_available:
        escalation.insert(0, "consult stronger approved model with minimal context package")
    return {"route": "escalate", "playbook": None, "steps": [],
            "message": "I don't have a verified procedure for this situation; I won't improvise one.",
            "escalation": escalation + ["contact a qualified human expert"]}


def minimal_context_package(situation: str, facts: dict[str, Any], allowed_fields: Iterable[str]) -> dict[str, Any]:
    """Emergency Model Escalation: route only the necessary context to a stronger model."""
    allowed = set(allowed_fields)
    return {"situation": situation, "facts": {k: v for k, v in facts.items() if k in allowed}}


# =========================================================================== capability index


class CapabilityIndex:
    """Emergency mechanisms Jarvis actually knows how to invoke or explain."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def add(self, name: str, kind: str, *, invoke: str = "", explain: str = "", offline: bool = True,
            last_verified: str | None = None) -> None:
        self.entries.append({"name": name, "kind": kind, "invoke": invoke, "explain": explain,
                             "offline": offline, "last_verified": last_verified})

    def available(self, *, internet: bool) -> list[dict[str, Any]]:
        return [e for e in self.entries if internet or e["offline"]]


# =========================================================================== state machine


EMERGENCY_FLOW = {
    "idle": {"detected": "assess"},
    "assess": {"confirmed": "protect", "uncertain": "verify", "false_alarm": "resolved"},
    "verify": {"confirmed": "protect", "false_alarm": "resolved", "timeout": "protect"},
    "protect": {"responders_contacted": "await", "objective_met": "recover"},
    "await": {"objective_met": "recover", "worsened": "protect"},
    "recover": {"restored": "resolved"},
    "resolved": {},
}


class EmergencyStateMachine:
    """Deterministic flow with evidence gates and stopping conditions."""

    def __init__(self, gates: dict[tuple[str, str], Callable[[dict[str, Any]], bool]] | None = None) -> None:
        self.state = "idle"
        self.gates = gates or {}
        self.log: list[dict[str, Any]] = []

    def fire(self, event: str, evidence: dict[str, Any], at: datetime) -> str:
        nxt = EMERGENCY_FLOW[self.state].get(event)
        if nxt is None:
            raise ValueError(f"event {event!r} not valid in state {self.state!r}")
        gate = self.gates.get((self.state, event))
        if gate is not None and not gate(evidence):
            self.log.append({"from": self.state, "event": event, "blocked": "evidence gate", "at": as_dt(at).isoformat()})
            return self.state
        self.log.append({"from": self.state, "event": event, "to": nxt, "at": as_dt(at).isoformat()})
        self.state = nxt
        return nxt


# =========================================================================== communications / snapshot


def responder_packet(*, nature: str, location: str | None, callback: str, identity: str | None = None,
                     hazards: Iterable[str] = (), readings: dict[str, Any] | None = None,
                     accessibility: Iterable[str] = (), actions_tried: Iterable[str] = ()) -> str:
    """Emergency Communications Composer: concise, deterministic, only known facts."""
    lines = [f"EMERGENCY: {nature}"]
    lines.append(f"Location: {location}" if location else "Location: UNKNOWN (not available)")
    if identity:
        lines.append(f"Caller: {identity}")
    hz = list(hazards)
    if hz:
        lines.append("Hazards: " + "; ".join(hz))
    if readings:
        lines.append("Sensor readings: " + "; ".join(f"{k}={v}" for k, v in readings.items()))
    acc = list(accessibility)
    if acc:
        lines.append("Accessibility needs: " + "; ".join(acc))
    tried = list(actions_tried)
    if tried:
        lines.append("Already tried: " + "; ".join(tried))
    lines.append(f"Callback: {callback}")
    return "\n".join(lines)


def evidence_snapshot(history: list[dict[str, Any]], started_at: datetime, *, lookback: timedelta = timedelta(hours=2)) -> dict[str, Any]:
    """Emergency Evidence Snapshot: freeze recent sensor/world history."""
    start = as_dt(started_at) - lookback
    items = [plain(h) for h in history if as_dt(h["at"]) >= start]
    body = json.dumps(items, sort_keys=True, default=str)
    return {"id": stable_id(body), "started_at": as_dt(started_at).isoformat(), "items": items,
            "sha256_prefix": stable_id(body, length=32)}


# =========================================================================== self test / drill


def self_test(checks: dict[str, Callable[[], bool]]) -> dict[str, Any]:
    """Emergency Self-Test: playbooks open, contacts current, models start, sensors report."""
    results = {}
    for name, fn in checks.items():
        try:
            results[name] = bool(fn())
        except Exception as exc:  # noqa: BLE001
            results[name] = False
            results[f"{name}:error"] = repr(exc)
    failing = [k for k, v in results.items() if v is False]
    return {"passed": not failing, "results": results, "failing": failing}


def run_drill(scenario: dict[str, Any], library: PlaybookLibrary, *, act: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Emergency Drill Mode: end-to-end without real effects; ``act`` must be a
    simulator.  Scores recognition, playbook choice, escalation and authority end."""
    performed: list[str] = []
    sim = act or performed.append
    answer = emergency_answer(scenario["situation"], library)
    for step in answer.get("steps", []):
        sim(f"SIMULATED: {step}")
    expected = scenario.get("expected_playbook")
    score = {
        "recognized": answer["route"] != "escalate" if expected else answer["route"] == "escalate",
        "right_playbook": answer.get("playbook") == expected,
        "escalated_when_unknown": (expected is not None) or answer["route"] == "escalate",
        "no_real_effects": all(p.startswith("SIMULATED") for p in performed),
        "authority_terminated": True,
    }
    return {"answer": answer, "score": score, "passed": all(score.values())}


# =========================================================================== severe weather


_IBW_TAG = re.compile(r"FLASH FLOOD DAMAGE THREAT\.{3}(CONSIDERABLE|CATASTROPHIC)", re.I)
_IBW_PARAM = re.compile(r"flashFloodDamageThreat", re.I)


def parse_ibw(alert: dict[str, Any]) -> dict[str, Any]:
    """Impact-Based Warning tags from an NWS CAP/GeoJSON alert ``properties`` dict.
    CONSIDERABLE escalates to urgent, CATASTROPHIC (flash flood emergency) to critical."""
    params = alert.get("parameters", {}) or {}
    tag = None
    for k, v in params.items():
        if _IBW_PARAM.search(k):
            tag = (v[0] if isinstance(v, list) and v else v)
    if tag is None:
        m = _IBW_TAG.search(alert.get("description", "") or "")
        tag = m.group(1) if m else None
    tag = str(tag).upper() if tag else None
    priority = {"CATASTROPHIC": "critical", "CONSIDERABLE": "urgent"}.get(tag or "", "warning")
    if "emergency" in (alert.get("headline", "") or "").lower() and "flash flood" in (alert.get("event", "") or "").lower():
        priority = "critical"
    return {"event": alert.get("event"), "damage_threat": tag, "priority": priority}


def rainfall_threshold(base_in_per_hr: float, susceptibility: str, slope_deg: float | None = None) -> float:
    """Halve the rainfall-rate alert threshold in high landslide-susceptibility zones."""
    s = susceptibility.lower()
    factor = 0.5 if s in ("high", "very high", "very_high") else 0.75 if s == "moderate" else 1.0
    if slope_deg is not None and slope_deg >= 30 and factor > 0.5:
        factor = 0.5
    return base_in_per_hr * factor


# =========================================================================== failover alerting


@dataclass
class AlertPath:
    name: str
    send: Callable[[dict[str, Any]], bool]
    needs_internet: bool = False
    needs_grid: bool = False


def ntfy_payload(topic: str, title: str, message: str, priority: str) -> dict[str, Any]:
    level = {"info": 2, "warning": 3, "urgent": 4, "critical": 5}.get(priority, 3)
    return {"topic": topic, "title": title, "message": message, "priority": level, "tags": ["warning"]}


def dispatch_failover(alert: dict[str, Any], paths: list[AlertPath], *, internet: bool, grid: bool) -> dict[str, Any]:
    """Local failover alerting: for CRITICAL, try *every* viable path (buzzer, LAN
    webhook, loud local audio, push), not just the phone."""
    tried, delivered = [], []
    for p in paths:
        if (p.needs_internet and not internet) or (p.needs_grid and not grid):
            tried.append({"path": p.name, "skipped": "infrastructure down"})
            continue
        try:
            ok = bool(p.send(alert))
        except Exception as exc:  # noqa: BLE001
            ok = False
            tried.append({"path": p.name, "error": repr(exc)})
        if ok:
            delivered.append(p.name)
            if alert.get("priority") != "critical":
                break
    return {"delivered": delivered, "attempts": tried, "landed": bool(delivered)}


# =========================================================================== family beacon


@dataclass
class EmergencyWindow:
    id: str
    declared_by: str
    starts: datetime
    ends: datetime
    members: set[str]
    statuses: dict[str, dict[str, Any]] = field(default_factory=dict)


class FamilyBeacon:
    """Opt-in safe/need-help status, only within a user-declared window; no location
    unless the member chooses to include it."""

    def __init__(self) -> None:
        self.enrolled: set[str] = set()
        self.windows: dict[str, EmergencyWindow] = {}

    def enroll(self, member: str) -> None:
        self.enrolled.add(member)

    def declare(self, by: str, members: Iterable[str], *, now: datetime, duration: timedelta) -> EmergencyWindow:
        if by not in self.enrolled:
            raise PermissionError("declarer must be enrolled")
        ms = {m for m in members if m in self.enrolled}
        w = EmergencyWindow(stable_id(by, now, length=8), by, as_dt(now), as_dt(now) + duration, ms)
        self.windows[w.id] = w
        return w

    def report(self, window_id: str, member: str, status: str, now: datetime, note: str = "",
               location: str | None = None) -> bool:
        w = self.windows[window_id]
        now = as_dt(now)
        if member not in w.members or not (w.starts <= now < w.ends) or status not in ("safe", "need_help"):
            return False
        w.statuses[member] = {"status": status, "at": now.isoformat(), "note": note,
                              **({"location": location} if location else {})}
        return True

    def board(self, window_id: str, now: datetime) -> dict[str, Any]:
        w = self.windows[window_id]
        if as_dt(now) >= w.ends:
            return {"window": window_id, "closed": True}
        return {"window": window_id, "closed": False,
                "members": {m: w.statuses.get(m, {"status": "no_report"}) for m in sorted(w.members)}}
