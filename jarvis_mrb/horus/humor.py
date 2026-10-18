"""HORUS Ambient Commentary and Suggestion Mode (private personal comedian).

Implements the future.md section as the deterministic part of the candidate
pipeline: rolling transcript context -> cheap opportunity filter -> repertoire
candidate -> timing / cooldown / privacy / sensitivity gates -> private delivery.
A local LLM can be slotted in as an additional candidate generator; every
candidate (rule-based or generated) passes through the same gates.

Gates that are deliberately non-negotiable here:
* delivery only to a verified private output device; never a public speaker;
* silence during genuine distress or important conversation;
* never mock a speech disability (stumble lines are disabled for flagged speakers);
* dark/taboo lines only in Commentary Mode, only in a retrospective joking context;
* Suggestion Mode never speaks aloud and never impersonates the user;
* listening is session-scoped and opt-in; transcripts are not retained by default.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

from jarvis_mrb.horus._util import as_dt, jaccard, tokens

MODES = ("commentary", "suggestion", "off")
PRIVATE_DEVICES = {"earbud", "headphones", "glasses_private_audio", "hearing_aid"}


@dataclass
class Segment:
    speaker: str  # "user" or another speaker label
    text: str
    start: datetime
    end: datetime
    laughter: bool = False


@dataclass
class Bit:
    id: str
    lines: list[str]
    trigger: str
    dark: bool = False
    suggestion_ok: bool = True
    min_gap_s: float = 900.0  # per-bit repetition cooldown


REPERTOIRE: list[Bit] = [
    Bit("nonsense", ["Onto something or on something?"], "nonsense_explanation"),
    Bit("lost_plot", ["Houston, we lost the plot."], "lost_plot"),
    Bit("no_plan", ["In terms of a plan, there is no plan."], "plan_without_execution"),
    Bit("obvious", ["You don't say.", "You would think."], "states_obvious"),
    Bit("bizarre", ["That's what I'm saying."], "bizarre_statement"),
    Bit("rome", ["Look, Rome wasn't built in a day."], "user_called_slow"),
    Bit("stumble", ["Couldn't have said it better myself."], "stumble", suggestion_ok=False),
    Bit("checkout", ["You come here often?"], "mundane_checkout"),
    Bit("be_honest", ["Okay, be honest with me here."], "ordinary_question_setup"),
    Bit("trout", ["How is this going to affect local trout populations?"], "minor_mishap", min_gap_s=7200.0),
    Bit("not_their_fault", ["Probably told them it wasn't their fault too."], "retrospective_divorce_joke",
        dark=True, suggestion_ok=False, min_gap_s=86400.0),
]

_DISTRESS = re.compile(r"\b(passed away|died|funeral|diagnos\w+|i'?m scared|can'?t cope|panic|crying|hospital|"
                       r"suicid\w*|abus\w+|laid off|miscarr\w+|terrified|i need help)\b", re.I)
_IMPORTANT = re.compile(r"\b(contract|offer letter|interview|diagnosis|lawyer|police|officer|emergency|"
                        r"performance review|sign here|wedding vows)\b", re.I)
_NONSENSE = re.compile(r"\b(basically|energy|vibes?|quantum|frequenc\w+|trust me|manifest\w*|alignment|the universe)\b", re.I)
_PLAN = re.compile(r"\b(we should|what if we|imagine if|i'?m going to|let'?s just|my idea is)\b", re.I)
_EXECUTION = re.compile(r"\b(how|first|step|budget|by (?:monday|friday|next)|deadline|cost|then we)\b", re.I)
_OBVIOUS = re.compile(r"\b(turns out|who knew|it is what it is|water is wet|apparently it'?s|it'?s (?:cold|hot) (?:out|in here))\b", re.I)
_BIZARRE = re.compile(r"\b(aliens?|lizard people|birds aren'?t real|flat earth|ghosts? told|time travel(?:er|ed))\b", re.I)
_SLOW = re.compile(r"\b(you'?re (?:so )?slow|took you long enough|keep up|hurry up|finally!?)\b", re.I)
_CHECKOUT = re.compile(r"\b(paper or plastic|receipt|card or cash|find everything okay|rewards number|next in line)\b", re.I)
_QUESTION_SETUP = re.compile(r"\b(can i ask you something|quick question|let me ask you)\b", re.I)
_MISHAP = re.compile(r"\b(oops|dropped|spilled|broke|tripped|missed the bus|forgot my)\b", re.I)
_DIVORCE = re.compile(r"\b(parents? (?:got )?divorced|when my parents split)\b", re.I)
_FILLERS = re.compile(r"\b(uh|um|er|like,)\b", re.I)


def detect_triggers(window: list[Segment], *, stutter_speakers: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Cheap opportunity filter over the rolling window (latest segment last)."""
    if not window:
        return []
    last = window[-1]
    text = last.text
    stutter = set(stutter_speakers)
    found = []
    words = len(text.split())
    if last.speaker != "user" and words >= 40 and len(_NONSENSE.findall(text)) >= 2:
        found.append({"trigger": "nonsense_explanation", "target": last.speaker})
    if len(window) >= 4:
        opening = set(tokens(" ".join(s.text for s in window[:2])))
        recent = set(tokens(" ".join(s.text for s in window[-2:])))
        if opening and recent and jaccard(opening, recent) < 0.05 and re.search(r"\b(anyway|where was i|what were we)\b", text, re.I):
            found.append({"trigger": "lost_plot", "target": "conversation"})
    if _PLAN.search(text) and not _EXECUTION.search(text) and words >= 6:
        found.append({"trigger": "plan_without_execution", "target": last.speaker})
    if _OBVIOUS.search(text):
        found.append({"trigger": "states_obvious", "target": last.speaker})
    if _BIZARRE.search(text):
        found.append({"trigger": "bizarre_statement", "target": last.speaker})
    if last.speaker != "user" and _SLOW.search(text):
        found.append({"trigger": "user_called_slow", "target": "user"})
    fillers = len(_FILLERS.findall(text))
    repeated = len(re.findall(r"\b(\w+) \1\b", text.lower()))
    if last.speaker != "user" and last.speaker not in stutter and words >= 8 and (fillers + repeated) / words >= 0.25:
        found.append({"trigger": "stumble", "target": last.speaker})
    if _CHECKOUT.search(text):
        found.append({"trigger": "mundane_checkout", "target": last.speaker})
    if last.speaker == "user" and _QUESTION_SETUP.search(text):
        found.append({"trigger": "ordinary_question_setup", "target": "user"})
    if _MISHAP.search(text):
        found.append({"trigger": "minor_mishap", "target": last.speaker})
    if _DIVORCE.search(text) and any(s.laughter for s in window[-3:]) and re.search(r"\b(was|were|back when|years ago|used to)\b", text, re.I):
        found.append({"trigger": "retrospective_divorce_joke", "target": last.speaker})
    return found


@dataclass
class HumorState:
    mode: str = "off"
    output_device: str | None = None
    output_verified: bool = False
    session_consented: bool = False
    last_delivery: datetime | None = None
    cooldown_s: float = 300.0
    history: list[dict[str, Any]] = field(default_factory=list)
    preferences: dict[str, float] = field(default_factory=dict)  # bit -> weight
    retain_transcripts: bool = False


class HumorEngine:
    def __init__(self, state: HumorState | None = None, repertoire: list[Bit] | None = None, seed: int = 3,
                 threshold: float = 0.55) -> None:
        self.state = state or HumorState()
        self.bits = {b.trigger: b for b in (repertoire or REPERTOIRE)}
        self.rng = random.Random(seed)
        self.threshold = threshold

    # ------------------------------------------------------------------ controls
    def set_mode(self, mode: str) -> str:
        """Fast hands-free toggle: Commentary / Suggestion / Off."""
        if mode not in MODES:
            raise ValueError(mode)
        self.state.mode = mode
        return mode

    def mute(self) -> None:
        self.state.mode = "off"

    def verify_output(self, device: str, *, connected: bool) -> bool:
        """Explicit private output-device verification; no public fallback."""
        self.state.output_device = device
        self.state.output_verified = connected and device in PRIVATE_DEVICES
        return self.state.output_verified

    # ------------------------------------------------------------------ gates
    def _blocked(self, window: list[Segment], now: datetime) -> str | None:
        st = self.state
        if st.mode == "off":
            return "mode off"
        if not st.session_consented:
            return "no consented listening session"
        if not st.output_verified:
            return "private output device not verified"
        recent = " ".join(s.text for s in window[-4:])
        if _DISTRESS.search(recent):
            return "distress detected: silence"
        if _IMPORTANT.search(recent):
            return "important conversation: silence"
        if st.last_delivery is not None:
            jitter = self.rng.uniform(0.75, 1.5)  # variable cooldown
            if (as_dt(now) - st.last_delivery).total_seconds() < st.cooldown_s * jitter:
                return "cooldown"
        return None

    def _recently_used(self, bit: Bit, now: datetime) -> bool:
        for h in reversed(self.state.history):
            if h.get("bit") == bit.id:
                return (as_dt(now) - as_dt(h["at"])).total_seconds() < bit.min_gap_s
        return False

    def consider(self, window: list[Segment], now: datetime, *, latency_s: float = 0.8, audience: str = "friends",
                 stutter_speakers: Iterable[str] = ()) -> dict[str, Any]:
        """Return a delivery decision for the moment right after ``window[-1]``."""
        blocked = self._blocked(window, now)
        if blocked:
            return {"deliver": False, "reason": blocked}
        triggers = detect_triggers(window, stutter_speakers=stutter_speakers)
        if not triggers:
            return {"deliver": False, "reason": "no opportunity"}
        last = window[-1]
        # Timing: discard jokes that land after the moment has passed.
        moment_age = (as_dt(now) - as_dt(last.end)).total_seconds() + latency_s
        max_age = 2.5 if self.state.mode == "commentary" else 1.5
        if moment_age > max_age:
            return {"deliver": False, "reason": "too late; moment passed"}
        candidates = []
        for t in triggers:
            bit = self.bits.get(t["trigger"])
            if bit is None or self._recently_used(bit, now):
                continue
            if bit.dark and self.state.mode != "commentary":
                continue
            if self.state.mode == "suggestion":
                if not bit.suggestion_ok:
                    continue
                if audience in ("work", "formal", "strangers") and bit.trigger in ("bizarre_statement", "nonsense_explanation"):
                    continue
            weight = self.state.preferences.get(bit.id, 0.6)
            candidates.append((weight, bit))
        if not candidates:
            return {"deliver": False, "reason": "no suitable line"}
        weight, bit = max(candidates, key=lambda c: c[0])
        if weight < self.threshold:
            return {"deliver": False, "reason": "below quality threshold; silence is the default"}
        line = self._fresh_variant(bit)
        self.state.last_delivery = as_dt(now)
        self.state.history.append({"bit": bit.id, "line": line, "at": as_dt(now).isoformat(), "mode": self.state.mode})
        return {"deliver": True, "line": line, "bit": bit.id, "mode": self.state.mode, "device": self.state.output_device,
                "cue": "suggestion_chime" if self.state.mode == "suggestion" else None,
                "speak_publicly": False}

    def _fresh_variant(self, bit: Bit) -> str:
        used = [h["line"] for h in self.state.history if h.get("bit") == bit.id]
        unused = [l for l in bit.lines if l not in used]
        return self.rng.choice(unused or bit.lines)

    # ------------------------------------------------------------------ learning
    FEEDBACK = {"laughed_privately": 0.1, "said_it_landed": 0.15, "said_it_flopped": -0.15, "too_late": -0.05,
                "repetitive": -0.1, "socially_off": -0.2, "felt_natural": 0.05}

    def feedback(self, bit_id: str, kind: str) -> float:
        """Explicit feedback only; silence is not treated as dislike."""
        if kind not in self.FEEDBACK:
            raise ValueError(kind)
        w = self.state.preferences.get(bit_id, 0.6) + self.FEEDBACK[kind]
        self.state.preferences[bit_id] = max(0.0, min(1.0, w))
        return self.state.preferences[bit_id]

    def add_bit(self, bit: Bit) -> None:
        """Curate the repertoire from user-supplied examples."""
        self.bits[bit.trigger] = bit


def evaluate_transcript(engine: HumorEngine, segments: list[Segment], *, openings: dict[int, str] | None = None,
                        latency_s: float = 0.8) -> dict[str, Any]:
    """Text-transcript evaluation harness: replay segments, deliver right after each
    one, and compare against labelled openings ``{segment_index: expected_bit}``."""
    openings = openings or {}
    delivered, hits, false_interruptions = [], 0, 0
    for i in range(len(segments)):
        now = segments[i].end + timedelta(seconds=0.2)
        d = engine.consider(segments[: i + 1], now, latency_s=latency_s)
        if d["deliver"]:
            delivered.append({"index": i, "bit": d["bit"], "line": d["line"]})
            if openings.get(i) == d["bit"]:
                hits += 1
            elif i not in openings:
                false_interruptions += 1
    return {"delivered": delivered, "hits": hits, "labelled": len(openings),
            "false_interruptions": false_interruptions,
            "repetition": len(delivered) - len({d["line"] for d in delivered})}
