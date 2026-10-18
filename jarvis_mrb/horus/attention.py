"""Mercury + Cassandra: attention arbitration, contextual delivery and modes.

future.md ideas implemented here: Contextual Delivery / Follow-Me Information
(routable information objects), Ambient Output Fabric (least-intrusive adequate
channel), Social Context Modes, Context-gated capability sets, Sterile-Cockpit
Mode, Attention budget, Attention Commander, Information Triage Officer, Decision
Window Detection, Operational Tempo, Cognitive-Load Governor, Falsifiable
Proactivity / "Why did you tell me this?", Multi-Modal Escalation Ladder
(acknowledge-anywhere cancels elsewhere), Interaction Capability Negotiation,
Input/Output-Modality Independence, Physical Status Vocabulary, Mode Annunciation,
Automation Surprise Detector, Return-to-Manual Handoff, Behavioral Automation
Success Metrics, Alarm Rationalization, Alarm Flood Mode, First-Out Analysis,
Named preset/loadout invocation, Passive system status indicators, and the
guaranteed barge-in / interruptibility primitive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, clamp, plain, stable_id

URGENCY = ("ambient", "low", "normal", "high", "critical")
_U = {u: i for i, u in enumerate(URGENCY)}

# Channels ordered from least to most intrusive with properties.
CHANNELS: dict[str, dict[str, Any]] = {
    "silence": {"intrusion": 0, "visual": False, "audio": False, "haptic": False, "capacity": 0},
    "status_glyph": {"intrusion": 1, "visual": True, "audio": False, "haptic": False, "capacity": 1},
    "room_display": {"intrusion": 2, "visual": True, "audio": False, "haptic": False, "capacity": 3},
    "watch_complication": {"intrusion": 2, "visual": True, "audio": False, "haptic": False, "capacity": 1},
    "hud_text": {"intrusion": 3, "visual": True, "audio": False, "haptic": False, "capacity": 2},
    "desktop_overlay": {"intrusion": 3, "visual": True, "audio": False, "haptic": False, "capacity": 4},
    "phone_notification": {"intrusion": 4, "visual": True, "audio": False, "haptic": True, "capacity": 3},
    "private_audio": {"intrusion": 5, "visual": False, "audio": True, "haptic": False, "capacity": 3},
    "speaker": {"intrusion": 6, "visual": False, "audio": True, "haptic": False, "capacity": 3},
    "phone_alarm": {"intrusion": 7, "visual": True, "audio": True, "haptic": True, "capacity": 3},
}

# Social Context Modes: what each mode permits.
SOCIAL_MODES: dict[str, dict[str, Any]] = {
    "alone": {"max_privacy": "private", "speaker_ok": True, "min_urgency": "low", "narration": "full"},
    "family": {"max_privacy": "household", "speaker_ok": True, "min_urgency": "normal", "narration": "brief"},
    "guest": {"max_privacy": "public", "speaker_ok": False, "min_urgency": "high", "narration": "minimal"},
    "babysitter": {"max_privacy": "public", "speaker_ok": False, "min_urgency": "high", "narration": "minimal"},
    "dinner_party": {"max_privacy": "public", "speaker_ok": False, "min_urgency": "high", "narration": "minimal"},
    "meeting": {"max_privacy": "private", "speaker_ok": False, "min_urgency": "high", "narration": "none"},
    "confidential_work": {"max_privacy": "private", "speaker_ok": False, "min_urgency": "high", "narration": "none"},
    "public": {"max_privacy": "public", "speaker_ok": False, "min_urgency": "normal", "narration": "minimal"},
    "sleep": {"max_privacy": "private", "speaker_ok": False, "min_urgency": "critical", "narration": "none"},
    "driving": {"max_privacy": "private", "speaker_ok": True, "min_urgency": "normal", "narration": "audio_only"},
}
PRIVACY = ("public", "household", "private")

# Context-gated capability sets: capability -> modes in which it is disabled.
CAPABILITY_GATES: dict[str, set[str]] = {
    "read_messages_aloud": {"guest", "babysitter", "dinner_party", "meeting", "confidential_work", "public"},
    "visual_dashboard": {"driving"},
    "compose_long_reply": {"driving"},
    "speaker_announcements": {"sleep", "meeting", "confidential_work"},
    "proactive_chatter": {"sleep", "meeting"},
    "financial_details": {"guest", "babysitter", "dinner_party", "public"},
    "camera_sensing": {"guest", "babysitter", "dinner_party"},
}


@dataclass
class InfoObject:
    """A routable information object (Contextual Delivery)."""

    id: str
    title: str
    body: str
    urgency: str = "normal"
    recipient: str = "user"
    privacy: str = "private"
    expires_at: datetime | None = None
    prerequisites: list[str] = field(default_factory=list)  # context facts that must hold to be actionable
    acceptable_channels: list[str] | None = None
    evidence: list[str] = field(default_factory=list)
    reason: str = ""  # rule/assertion/mission that produced it
    confidence: float = 1.0
    source: str = ""
    decision_deadline: datetime | None = None
    consequence: float = 0.5
    novelty: float = 0.5
    relevance: float = 0.5
    created_at: datetime | None = None

    def why(self) -> dict[str, Any]:
        """'Why did you tell me this?'"""
        return {"reason": self.reason or "unspecified", "evidence": self.evidence, "confidence": self.confidence,
                "source": self.source, "urgency": self.urgency}


@dataclass
class Context:
    mode: str = "alone"
    location: str = ""
    available_surfaces: set[str] = field(default_factory=lambda: {"phone_notification", "status_glyph"})
    facts: set[str] = field(default_factory=set)
    hands_busy: bool = False
    noisy: bool = False
    display_available: bool = True
    cognitive_load: float = 0.0  # 0..1
    sterile: bool = False
    now: datetime | None = None


def capability_allowed(capability: str, ctx: Context) -> bool:
    return ctx.mode not in CAPABILITY_GATES.get(capability, set())


def negotiate_modalities(ctx: Context) -> dict[str, bool]:
    """Interaction Capability Negotiation."""
    mode = SOCIAL_MODES.get(ctx.mode, SOCIAL_MODES["alone"])
    return {
        "visual": ctx.display_available and ctx.mode != "driving",
        "audio_out": not ctx.noisy and ctx.mode not in ("meeting", "confidential_work", "sleep"),
        "speaker": mode["speaker_ok"] and not ctx.noisy,
        "voice_in": not ctx.noisy and ctx.mode not in ("meeting", "confidential_work"),
        "touch_in": not ctx.hands_busy and ctx.mode != "driving",
        "haptic": True,
    }


def falsifiable(info: InfoObject, min_confidence: float = 0.6) -> tuple[bool, str]:
    """Falsifiable Proactivity: interrupt only with concrete evidence + opportunity."""
    if not info.evidence:
        return False, "no concrete evidence"
    if not info.reason:
        return False, "no rule/assertion/mission justifies interrupting"
    if info.confidence < min_confidence and _U[info.urgency] < _U["critical"]:
        return False, f"confidence {info.confidence:.2f} below {min_confidence}"
    return True, "justified"


def choose_channel(info: InfoObject, ctx: Context) -> dict[str, Any]:
    """Ambient Output Fabric + Contextual Delivery: least intrusive adequate channel,
    deferral when unactionable, silence when the case is weak."""
    now = as_dt(ctx.now)
    if info.expires_at is not None and now >= as_dt(info.expires_at):
        return {"action": "drop", "reason": "expired"}
    ok, why = falsifiable(info)
    if not ok and _U[info.urgency] >= _U["normal"]:
        return {"action": "silence", "reason": why}
    mode = SOCIAL_MODES.get(ctx.mode, SOCIAL_MODES["alone"])
    if PRIVACY.index(info.privacy) > PRIVACY.index(mode["max_privacy"]) and _U[info.urgency] < _U["critical"]:
        return {"action": "defer", "reason": f"privacy {info.privacy} exceeds mode {ctx.mode}"}
    missing = [p for p in info.prerequisites if p not in ctx.facts]
    if missing and _U[info.urgency] < _U["critical"]:
        return {"action": "defer", "reason": "not actionable yet", "waiting_for": missing}
    effective_min = mode["min_urgency"]
    if ctx.sterile:
        effective_min = "critical"
    elif ctx.cognitive_load >= 0.7:
        effective_min = URGENCY[max(_U[effective_min], _U["high"])]
    if _U[info.urgency] < _U[effective_min]:
        target = "status_glyph" if "status_glyph" in ctx.available_surfaces else None
        return {"action": "defer" if target is None else "ambient", "channel": target,
                "reason": f"below {effective_min} threshold in {ctx.mode}{' (sterile)' if ctx.sterile else ''}"}
    mods = negotiate_modalities(ctx)
    needed_capacity = 1 if len(info.body) < 40 else 3
    min_intrusion = {"ambient": 0, "low": 1, "normal": 2, "high": 4, "critical": 5}[info.urgency]
    candidates = []
    for name in sorted(ctx.available_surfaces, key=lambda c: CHANNELS[c]["intrusion"]):
        props = CHANNELS[name]
        if info.acceptable_channels is not None and name not in info.acceptable_channels:
            continue
        if props["intrusion"] < min_intrusion:
            continue
        if props["visual"] and not props["audio"] and not mods["visual"]:
            continue
        if props["audio"] and not props["visual"] and not mods["audio_out"]:
            continue
        if name == "speaker" and (not mods["speaker"] or info.privacy != "public" and ctx.mode != "alone"):
            continue
        if props["capacity"] < needed_capacity and info.urgency != "critical":
            continue
        candidates.append(name)
    if not candidates and info.urgency == "critical" and ctx.available_surfaces:
        # Critical information is never deferred for lack of an ideal surface.
        candidates = [max(ctx.available_surfaces, key=lambda c: CHANNELS[c]["intrusion"])]
    if not candidates:
        return {"action": "defer", "reason": "no adequate surface in current context"}
    return {"action": "deliver", "channel": candidates[0], "why": info.why()}


def render_all_modalities(info: InfoObject) -> dict[str, str]:
    """Output-Modality Independence: equivalent visual, auditory and haptic forms."""
    pulses = {"ambient": 0, "low": 1, "normal": 1, "high": 2, "critical": 3}[info.urgency]
    return {
        "visual": f"{info.title}: {info.body}",
        "audio": f"{info.title}. {info.body}",
        "haptic": "-".join(["pulse"] * pulses) or "none",
        "glyph": STATUS_VOCABULARY.get(info.urgency, "•"),
    }


STATUS_VOCABULARY = {
    "ambient": "·", "low": "○", "normal": "◔", "high": "◑", "critical": "●",
    "offline": "⊘", "listening": "◉", "muted": "⊗", "syncing": "↻",
}


# =========================================================================== budget / commander / triage


class AttentionBudget:
    """Shared interruption budget across all proactive subsystems (per rolling hour)."""

    def __init__(self, per_hour: int = 4, critical_exempt: bool = True) -> None:
        self.per_hour = per_hour
        self.critical_exempt = critical_exempt
        self.spent: list[tuple[datetime, str]] = []

    def try_spend(self, info: InfoObject, now: datetime) -> bool:
        now = as_dt(now)
        if self.critical_exempt and info.urgency == "critical":
            self.spent.append((now, info.id))
            return True
        recent = [t for t, _ in self.spent if now - t < timedelta(hours=1)]
        if len(recent) >= self.per_hour:
            return False
        self.spent.append((now, info.id))
        return True


def triage_score(info: InfoObject, now: datetime) -> float:
    """Information Triage Officer: decision relevance, novelty, confidence,
    consequence and time sensitivity — not recency."""
    time_pressure = 0.0
    if info.decision_deadline is not None:
        minutes_left = (as_dt(info.decision_deadline) - as_dt(now)).total_seconds() / 60
        time_pressure = 1.0 if minutes_left <= 0 else clamp(1.0 - minutes_left / 240)
    return round(0.3 * info.relevance + 0.15 * info.novelty + 0.15 * info.confidence
                 + 0.25 * info.consequence + 0.15 * time_pressure, 4)


def decision_window(info: InfoObject, now: datetime) -> dict[str, Any]:
    """Decision Window Detection: escalate urgency as a closing window shrinks."""
    if info.decision_deadline is None:
        return {"has_window": False, "urgency": info.urgency}
    left = (as_dt(info.decision_deadline) - as_dt(now)).total_seconds() / 60
    if left <= 0:
        return {"has_window": True, "closed": True, "urgency": info.urgency}
    urgency = "critical" if left <= 10 else "high" if left <= 60 else "normal" if left <= 24 * 60 else "low"
    if _U[urgency] < _U[info.urgency]:
        urgency = info.urgency
    return {"has_window": True, "closed": False, "minutes_left": round(left, 1), "urgency": urgency}


class AttentionCommander:
    """Single arbitration layer deciding what occupies scarce attention slots."""

    def __init__(self, slots: int = 3, budget: AttentionBudget | None = None) -> None:
        self.slots = slots
        self.budget = budget or AttentionBudget()
        self.policy_overrides: dict[str, float] = {}  # source -> weight (missions/emergencies)
        self.demoted: list[dict[str, Any]] = []

    def set_policy(self, source: str, weight: float) -> None:
        self.policy_overrides[source] = weight

    def arbitrate(self, items: list[InfoObject], ctx: Context) -> dict[str, Any]:
        now = as_dt(ctx.now)
        scored = []
        for it in items:
            win = decision_window(it, now)
            if win.get("closed"):
                continue
            it.urgency = win["urgency"]
            score = triage_score(it, now) * self.policy_overrides.get(it.source, 1.0) + 0.2 * _U[it.urgency]
            scored.append((score, it))
        scored.sort(key=lambda x: -x[0])
        shown, demoted = [], []
        for score, it in scored:
            decision = choose_channel(it, ctx)
            if len(shown) < self.slots and decision["action"] == "deliver" and self.budget.try_spend(it, now):
                shown.append({"id": it.id, "score": round(score, 4), **decision})
            else:
                demoted.append({"id": it.id, "score": round(score, 4), "reason": decision.get("reason", "slot/budget")})
        self.demoted.extend(demoted)
        return {"shown": shown, "demoted": demoted}


# =========================================================================== tempo / load


def operational_tempo(event_times: list[datetime], now: datetime, window: timedelta = timedelta(minutes=30)) -> dict[str, Any]:
    """Stable / accelerating / resolving / chaotic, plus suggested refresh interval."""
    now = as_dt(now)
    recent = [as_dt(t) for t in event_times if now - as_dt(t) <= window]
    prior = [as_dt(t) for t in event_times if window < now - as_dt(t) <= 2 * window]
    r, p = len(recent), len(prior)
    if r >= 20:
        tempo = "chaotic"
    elif r > max(2, 1.5 * p):
        tempo = "accelerating"
    elif p > max(2, 1.5 * r):
        tempo = "resolving"
    else:
        tempo = "stable"
    refresh = {"chaotic": 15, "accelerating": 30, "stable": 300, "resolving": 120}[tempo]
    density = {"chaotic": "compact", "accelerating": "focused", "stable": "normal", "resolving": "normal"}[tempo]
    return {"tempo": tempo, "recent": r, "prior": p, "refresh_s": refresh, "display_density": density}


def cognitive_load(*, driving: bool = False, in_conversation: bool = False, in_meeting: bool = False,
                   active_alerts: int = 0, app_switches_per_min: float = 0.0, typing: bool = False) -> float:
    """Cognitive-Load Governor estimate (0..1)."""
    load = 0.0
    load += 0.5 if driving else 0.0
    load += 0.3 if in_conversation else 0.0
    load += 0.35 if in_meeting else 0.0
    load += min(0.3, 0.1 * active_alerts)
    load += min(0.2, 0.05 * app_switches_per_min)
    load += 0.1 if typing else 0.0
    return clamp(load)


# =========================================================================== escalation ladder


class EscalationLadder:
    """Escalate across surfaces only if unacknowledged or worsening; acknowledgement
    on any surface cancels redundant noise elsewhere."""

    def __init__(self, steps: list[tuple[str, timedelta]]) -> None:
        self.steps = steps
        self.active: dict[str, dict[str, Any]] = {}

    def start(self, alert_id: str, now: datetime) -> str:
        self.active[alert_id] = {"step": 0, "since": as_dt(now), "acked": None, "surfaces": [self.steps[0][0]]}
        return self.steps[0][0]

    def tick(self, alert_id: str, now: datetime, *, worsened: bool = False) -> str | None:
        st = self.active.get(alert_id)
        if st is None or st["acked"]:
            return None
        step = st["step"]
        due = as_dt(now) - st["since"] >= self.steps[step][1]
        if (due or worsened) and step + 1 < len(self.steps):
            st["step"] += 1
            st["since"] = as_dt(now)
            surface = self.steps[st["step"]][0]
            st["surfaces"].append(surface)
            return surface
        return None

    def acknowledge(self, alert_id: str, surface: str, now: datetime) -> list[str]:
        st = self.active[alert_id]
        st["acked"] = {"surface": surface, "at": as_dt(now).isoformat()}
        return [s for s in st["surfaces"] if s != surface]  # surfaces to clear


# =========================================================================== modes / annunciation / loadouts


class ModeManager:
    """Mode Annunciation + Automation Surprise + Return-to-Manual handoff."""

    def __init__(self) -> None:
        self.modes: dict[str, str] = {}
        self.controlling: dict[str, str] = {}  # entity -> automation id
        self.log: list[dict[str, Any]] = []

    def set_mode(self, domain: str, mode: str, *, cause: str, at: datetime) -> dict[str, Any]:
        before = self.modes.get(domain)
        self.modes[domain] = mode
        entry = {"domain": domain, "from": before, "to": mode, "cause": cause, "at": as_dt(at).isoformat(),
                 "annunciation": f"{domain} is now in {mode} mode (was {before or 'unset'}) because {cause}."}
        self.log.append(entry)
        return entry

    def take_control(self, entity: str, automation: str) -> None:
        self.controlling[entity] = automation

    def status(self) -> dict[str, Any]:
        return {"modes": dict(self.modes), "controlling": dict(self.controlling)}

    def surprise(self, entity: str, expected: Any, observed: Any) -> dict[str, Any] | None:
        """Explain divergence between declared automation state and observation."""
        if repr(expected) == repr(observed):
            return None
        ctrl = self.controlling.get(entity)
        return {"entity": entity, "expected": expected, "observed": observed,
                "explanation": f"{entity} is under {ctrl}" if ctrl else f"{entity} is not under any HORUS automation",
                "recent_mode_changes": self.log[-3:]}

    def return_to_manual(self, entity: str, *, lost: str, left_state: Any, at: datetime) -> dict[str, Any]:
        automation = self.controlling.pop(entity, None)
        return {"entity": entity, "stopped_automation": automation, "because": lost, "left_in_state": left_state,
                "you_now_control": entity, "at": as_dt(at).isoformat(),
                "message": f"I stopped automating {entity} ({automation}) because {lost}. It is {left_state}; it's manual now."}


@dataclass
class Loadout:
    name: str
    actions: list[str]
    mode: str | None = None
    restore_on_exit: bool = True


class LoadoutRunner:
    """Named preset/loadout invocation with state restoration on exit."""

    def __init__(self, execute: Callable[[str], dict[str, Any]], snapshot: Callable[[], dict[str, Any]],
                 restore: Callable[[dict[str, Any]], None]) -> None:
        self.execute, self.snapshot, self.restore = execute, snapshot, restore
        self.loadouts: dict[str, Loadout] = {}
        self.active: dict[str, dict[str, Any]] = {}

    def define(self, lo: Loadout) -> None:
        self.loadouts[lo.name] = lo

    def invoke(self, text: str) -> dict[str, Any]:
        m = re.search(r"(?:set up|start|enable) (?:my )?([\w ]+?) (?:loadout|mode|preset)", text.lower())
        name = m.group(1).strip() if m else text.strip().lower()
        lo = self.loadouts.get(name)
        if lo is None:
            return {"status": "unknown_loadout", "known": sorted(self.loadouts)}
        before = self.snapshot()
        receipts = [self.execute(a) for a in lo.actions]
        self.active[name] = before
        return {"status": "active", "loadout": name, "receipts": receipts}

    def exit(self, name: str) -> dict[str, Any]:
        before = self.active.pop(name)
        if self.loadouts[name].restore_on_exit:
            self.restore(before)
        return {"status": "exited", "restored": self.loadouts[name].restore_on_exit}


# =========================================================================== interruptibility


class BargeIn:
    """Guaranteed low-latency interrupt: stop/pause/shorten/redirect.  Matching is a
    deterministic keyword check that runs *before* any model."""

    COMMANDS = {
        "stop": r"^(?:horus[, ]+)?(?:stop|quiet|shut up|enough|cancel|silence)\b",
        "pause": r"^(?:horus[, ]+)?(?:pause|hold on|wait)\b",
        "shorter": r"\b(?:shorter|tl;?dr|summari[sz]e|get to the point)\b",
        "redirect_device": r"\b(?:on|to) (?:my )?(phone|desktop|speaker|glasses|watch)\b",
        "correct": r"^(?:no|actually)[, ]",
    }

    def __init__(self) -> None:
        self.cancelled: set[str] = set()

    def classify(self, utterance: str) -> dict[str, Any] | None:
        text = utterance.strip().lower()
        for name, pattern in self.COMMANDS.items():
            m = re.search(pattern, text)
            if m:
                out: dict[str, Any] = {"command": name}
                if name == "redirect_device":
                    out["device"] = m.group(1)
                return out
        return None

    def interrupt(self, utterance: str, running: Iterable[str]) -> dict[str, Any]:
        cmd = self.classify(utterance)
        if cmd is None:
            return {"interrupted": False}
        if cmd["command"] in ("stop", "pause"):
            ids = list(running)
            self.cancelled.update(ids)
            return {"interrupted": True, **cmd, "cancelled": ids}
        return {"interrupted": True, **cmd, "cancelled": []}


# =========================================================================== metrics / alarms


class NudgeMetrics:
    """Behavioral Automation Success Metrics with threshold adaptation/retirement."""

    OUTCOMES = ("acted", "dismissed", "snoozed", "overridden", "ignored")

    def __init__(self) -> None:
        self.data: dict[str, dict[str, int]] = {}

    def record(self, behavior: str, outcome: str) -> None:
        if outcome not in self.OUTCOMES:
            raise ValueError(outcome)
        self.data.setdefault(behavior, {o: 0 for o in self.OUTCOMES})[outcome] += 1

    def usefulness(self, behavior: str) -> float | None:
        d = self.data.get(behavior)
        if not d or sum(d.values()) == 0:
            return None
        return (d["acted"] + 0.3 * d["snoozed"]) / sum(d.values())

    def recommendations(self, min_samples: int = 10) -> dict[str, str]:
        out = {}
        for b, d in self.data.items():
            n = sum(d.values())
            if n < min_samples:
                continue
            u = self.usefulness(b) or 0.0
            out[b] = "retire" if u < 0.1 else "raise_threshold" if u < 0.3 else "keep"
        return out


def rationalize_alarms(history: list[dict[str, Any]], *, window: timedelta = timedelta(days=30),
                       now: datetime | None = None) -> list[dict[str, Any]]:
    """Alarm Rationalization: nuisance, duplicate, standing and behaviour-free alarms.
    History items: ``{"alarm", "at", "cleared_at"?, "acked": bool, "action_taken": bool}``."""
    now = as_dt(now)
    by: dict[str, list[dict[str, Any]]] = {}
    for h in history:
        if now - as_dt(h["at"]) <= window:
            by.setdefault(h["alarm"], []).append(h)
    findings = []
    for alarm, hs in sorted(by.items()):
        issues = []
        if len(hs) >= 20:
            issues.append("nuisance:frequent")
        if any(h.get("cleared_at") is None and now - as_dt(h["at"]) > timedelta(days=1) for h in hs):
            issues.append("standing:permanently-active")
        if hs and not any(h.get("action_taken") for h in hs):
            issues.append("never-changes-behavior")
        if issues:
            findings.append({"alarm": alarm, "count": len(hs), "issues": issues})
    times: dict[str, list[datetime]] = {a: sorted(as_dt(h["at"]) for h in hs) for a, hs in by.items()}
    names = sorted(times)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pairs = sum(1 for t in times[a] if any(abs((t - u).total_seconds()) <= 60 for u in times[b]))
            if pairs >= 3 and pairs >= 0.8 * min(len(times[a]), len(times[b])):
                findings.append({"alarm": f"{a}+{b}", "issues": ["duplicate:co-fire"], "count": pairs})
    return findings


def collapse_flood(alarms: list[dict[str, Any]], causes: dict[str, str], *, window: timedelta = timedelta(minutes=5)) -> list[dict[str, Any]]:
    """Alarm Flood Mode + First-Out Analysis.  ``causes`` maps alarm -> likely shared
    cause (e.g. from the dependency map).  Returns one incident per cause with the
    earliest meaningful state change highlighted."""
    incidents: dict[str, dict[str, Any]] = {}
    for a in sorted(alarms, key=lambda a: as_dt(a["at"])):
        cause = causes.get(a["alarm"], a["alarm"])
        inc = incidents.get(cause)
        if inc and as_dt(a["at"]) - as_dt(inc["first_out"]["at"]) <= window:
            inc["symptoms"].append(a["alarm"])
        else:
            incidents[cause] = {"incident": stable_id(cause, a["at"], length=8), "cause": cause,
                                "first_out": plain(a), "symptoms": [a["alarm"]]}
    return [{**i, "symptom_count": len(i["symptoms"])} for i in incidents.values()]


def status_indicators(health: dict[str, dict[str, Any]], now: datetime, stale_after: timedelta = timedelta(minutes=10)) -> list[dict[str, str]]:
    """Passive system status indicators: PC reachable, phone sensors syncing, last
    world-model sync — derived from health records ``{"ok": bool, "last_seen": iso}``."""
    out = []
    for name, rec in sorted(health.items()):
        last = rec.get("last_seen")
        if last is None:
            state = "unknown"
        elif as_dt(now) - as_dt(last) > stale_after:
            state = "stale"
        else:
            state = "ok" if rec.get("ok") else "failing"
        glyph = {"ok": "●", "stale": "◌", "failing": "⊘", "unknown": "?"}[state]
        out.append({"name": name, "state": state, "glyph": glyph})
    return out
