"""Mercury: presence, sessions, handoff and conversation/execution split.

future.md ideas implemented here: Cross-device continuation for general
productivity, Conversation Handoff, Transport-Independent Presence,
Conversation/Execution Split (conversation continues while durable jobs run),
Presence-as-Invocation, Personalized Environment Profiles (multi-person conflict
resolution), World-Aware Media (follow, pause on conversation, preserve position),
and the iPhone/glasses/desktop output expansion rule.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, stable_id

# Surface capabilities used for output expansion on handoff.
DEVICES = {
    "glasses": {"display": "glance", "audio": True, "max_chars": 80},
    "watch": {"display": "glance", "audio": False, "max_chars": 60},
    "phone": {"display": "card", "audio": True, "max_chars": 600},
    "car": {"display": "none", "audio": True, "max_chars": 0},
    "desktop": {"display": "full", "audio": True, "max_chars": 20000},
    "room_speaker": {"display": "none", "audio": True, "max_chars": 0},
}
TRANSPORT_PREFERENCE = ("lan", "internet", "webrtc", "push", "sms", "lora")


@dataclass
class Session:
    id: str
    user: str
    device: str
    transport: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    open_tasks: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def say(self, role: str, text: str, at: datetime) -> None:
        self.turns.append({"role": role, "text": text, "at": as_dt(at).isoformat(), "device": self.device})

    def handoff(self, device: str, at: datetime) -> dict[str, Any]:
        """Continue the same conversation on a new device; expand or compress output."""
        if device not in DEVICES:
            raise ValueError(device)
        prev = self.device
        self.device = device
        self.history.append({"event": "handoff", "from": prev, "to": device, "at": as_dt(at).isoformat()})
        return {"session": self.id, "from": prev, "to": device, "context_turns": len(self.turns),
                "render": DEVICES[device]["display"], "expanded": DEVICES[device]["max_chars"] > DEVICES[prev]["max_chars"]}

    def switch_transport(self, available: Iterable[str], at: datetime) -> str | None:
        """Transport-Independent Presence: keep the session on the best live path."""
        avail = set(available)
        for t in TRANSPORT_PREFERENCE:
            if t in avail:
                if t != self.transport:
                    self.history.append({"event": "transport", "from": self.transport, "to": t, "at": as_dt(at).isoformat()})
                    self.transport = t
                return t
        self.history.append({"event": "transport_lost", "at": as_dt(at).isoformat()})
        return None

    def render(self, text: str) -> str:
        cap = DEVICES[self.device]["max_chars"]
        if cap == 0:
            return ""  # audio-only surface; caller speaks instead
        return text if len(text) <= cap else text[: max(0, cap - 1)].rstrip() + "…"

    def continuation_packet(self) -> str:
        """Cross-device continuation packet for any task (not only Life Fabric)."""
        return json.dumps({"session": self.id, "user": self.user, "recent_turns": self.turns[-10:],
                           "open_tasks": self.open_tasks}, sort_keys=True)

    @classmethod
    def resume(cls, packet: str, *, device: str, transport: str) -> "Session":
        data = json.loads(packet)
        s = cls(data["session"], data["user"], device, transport)
        s.turns = list(data["recent_turns"])
        s.open_tasks = list(data["open_tasks"])
        s.history.append({"event": "resumed", "device": device})
        return s


# =========================================================================== conversation / execution split


class JobManager:
    """Durable background jobs decoupled from conversational responsiveness.  The
    conversation can query progress, cancel, and receive results as they land."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.inbox: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def submit(self, name: str, work: Callable[[Callable[[float, str], None], Callable[[], bool]], Any], *,
               background: bool = True) -> str:
        jid = stable_id(name, len(self.jobs), length=8)
        job = {"id": jid, "name": name, "status": "running", "progress": 0.0, "note": "", "result": None,
               "cancel": threading.Event()}
        self.jobs[jid] = job

        def progress(frac: float, note: str = "") -> None:
            with self._lock:
                job["progress"], job["note"] = frac, note

        def cancelled() -> bool:
            return job["cancel"].is_set()

        def run() -> None:
            try:
                result = work(progress, cancelled)
                status = "cancelled" if cancelled() else "done"
            except Exception as exc:  # noqa: BLE001
                result, status = repr(exc), "failed"
            with self._lock:
                job["status"], job["result"] = status, result
                self.inbox.append({"job": jid, "name": name, "status": status, "result": result})

        if background:
            t = threading.Thread(target=run, daemon=True)
            job["thread"] = t
            t.start()
        else:
            run()
        return jid

    def status(self, jid: str) -> dict[str, Any]:
        j = self.jobs[jid]
        return {k: j[k] for k in ("id", "name", "status", "progress", "note")}

    def cancel(self, jid: str) -> None:
        self.jobs[jid]["cancel"].set()

    def wait(self, jid: str, timeout: float = 5.0) -> None:
        t = self.jobs[jid].get("thread")
        if t is not None:
            t.join(timeout)

    def drain_results(self) -> list[dict[str, Any]]:
        """Results return naturally into the ongoing conversation."""
        with self._lock:
            out, self.inbox = self.inbox, []
        return out


# =========================================================================== presence as invocation


INVOCATION_TRIGGERS = {
    "entered_place": 0.6,
    "looked_at_object": 0.7,
    "began_routine": 0.6,
    "picked_up_device": 0.4,
    "state_transition": 0.5,
    "wake_word": 1.0,
}


def presence_invocation(trigger: str, *, relevance: float, mode: str, recently_invoked_s: float | None,
                        cooldown_s: float = 600) -> dict[str, Any]:
    """Wake words are only one trigger; others may open a conversational opportunity
    when policy permits (never in sleep/meeting, with cooldown)."""
    if trigger == "wake_word":
        return {"open": True, "reason": "explicit wake word"}
    if mode in ("sleep", "meeting", "confidential_work"):
        return {"open": False, "reason": f"mode {mode} forbids unsolicited conversation"}
    if recently_invoked_s is not None and recently_invoked_s < cooldown_s:
        return {"open": False, "reason": "cooldown"}
    score = INVOCATION_TRIGGERS.get(trigger, 0.0) * relevance
    return {"open": score >= 0.5, "score": round(score, 3), "reason": "relevance x trigger strength"}


# =========================================================================== environment profiles


@dataclass
class Profile:
    person: str
    authorized: bool
    prefs: dict[str, Any]
    priority: int = 0  # e.g. accessibility needs > comfort


def resolve_environment(present: list[Profile], *, numeric_keys: Iterable[str] = ("temperature_c", "audio_level",
                                                                                     "display_density", "lighting")) -> dict[str, Any]:
    """Environment follows authorized people; numeric conflicts → priority-weighted
    mean; categorical conflicts → highest priority; privacy → strictest."""
    people = [p for p in present if p.authorized]
    if not people:
        return {"prefs": {}, "conflicts": []}
    keys = set().union(*(p.prefs.keys() for p in people))
    out, conflicts = {}, []
    numeric = set(numeric_keys)
    for k in sorted(keys):
        vals = [(p, p.prefs[k]) for p in people if k in p.prefs]
        distinct = {json.dumps(v, default=str) for _, v in vals}
        if len(distinct) > 1:
            conflicts.append(k)
        if k == "privacy":
            order = ["public", "household", "private"]
            out[k] = max((v for _, v in vals), key=lambda v: order.index(v) if v in order else 0)
        elif k in numeric:
            w = [(p.priority + 1) for p, _ in vals]
            out[k] = round(sum(float(v) * wi for (_, v), wi in zip(vals, w)) / sum(w), 2)
        else:
            out[k] = max(vals, key=lambda pv: pv[0].priority)[1]
    return {"prefs": out, "conflicts": conflicts}


# =========================================================================== world-aware media


class MediaFollower:
    """Playback follows the user across rooms, pauses when conversation begins,
    preserves position, and adjusts for ambient noise."""

    def __init__(self) -> None:
        self.state = {"playing": False, "item": None, "position_s": 0.0, "device": None, "volume": 0.4,
                      "paused_for": None}
        self._last = None

    def play(self, item: str, device: str, at: datetime) -> None:
        self.state.update(playing=True, item=item, device=device, position_s=0.0, paused_for=None)
        self._last = as_dt(at)

    def _advance(self, at: datetime) -> None:
        if self.state["playing"] and self._last is not None:
            self.state["position_s"] += (as_dt(at) - self._last).total_seconds()
        self._last = as_dt(at)

    def user_moved(self, room_device: str, at: datetime) -> dict[str, Any]:
        self._advance(at)
        if self.state["item"] and room_device != self.state["device"]:
            prev = self.state["device"]
            self.state["device"] = room_device
            return {"moved_from": prev, "to": room_device, "resume_at_s": round(self.state["position_s"], 1)}
        return {}

    def conversation_started(self, at: datetime) -> None:
        self._advance(at)
        if self.state["playing"]:
            self.state.update(playing=False, paused_for="conversation")

    def conversation_ended(self, at: datetime) -> None:
        self._advance(at)
        if self.state["paused_for"] == "conversation":
            self.state.update(playing=True, paused_for=None)

    def ambient_noise(self, dba: float) -> float:
        self.state["volume"] = round(min(1.0, max(0.1, 0.2 + (dba - 35) / 60)), 2)
        return self.state["volume"]

