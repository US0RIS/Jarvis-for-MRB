"""Capability bus, routing and observable autonomy (Kant + Cerberus).

future.md ideas implemented here: "What can you do?" self-describing capability
statement, Capability graph, Model-independent Interaction Bus (typed capability
registry), Semantic-First Computer Control Router (API -> accessibility -> DOM ->
visual, one receipt schema), Model router by cognitive difficulty / Local-First
Cloud-Escalation Router (latency, privacy, cost, capability as inputs),
Cost-aware sensing, Action tray / quick-action palette, Interface-by-Use,
Personal API (local, grant-checked), Composable Capability Blocks, Personal
Micro-App Generator, Observable Autonomy / Mission Recorder (pause / take over /
abort / replay), Mission Mode, Agent State Portability / Personal Digital Twin
packet, Input-Modality Independence (one semantic intent layer), Accessibility as
core architecture (semantic labels on every capability), Compiled Website
Capability (deterministic adapter with verifier + agent fallback), and computer-use
task verification (reference-state evaluators, Cua-Bench pattern).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, plain, stable_id

# =========================================================================== registry


@dataclass
class Capability:
    id: str
    label: str  # accessible semantic label
    description: str
    inputs: dict[str, str] = field(default_factory=dict)  # name -> type
    requires: list[str] = field(default_factory=list)  # providers/hosts/sensors
    permissions: list[str] = field(default_factory=list)
    effect: str = "read"  # read | device | money | message
    offline: bool = False
    modalities: list[str] = field(default_factory=lambda: ["voice", "text", "touch", "keyboard", "automation"])
    entities: list[str] = field(default_factory=list)  # what it can observe/affect
    verbs: list[str] = field(default_factory=list)  # observe | infer | affect


class CapabilityBus:
    def __init__(self) -> None:
        self.caps: dict[str, Capability] = {}
        self.handlers: dict[str, Callable[..., Any]] = {}
        self.usage: dict[str, int] = {}

    def register(self, cap: Capability, handler: Callable[..., Any] | None = None) -> None:
        if not cap.label.strip():
            raise ValueError("every capability needs an accessible label")
        self.caps[cap.id] = cap
        if handler is not None:
            self.handlers[cap.id] = handler

    def available(self, *, up: Iterable[str], granted: Iterable[str], internet: bool = True) -> list[Capability]:
        u, g = set(up), set(granted)
        return [c for c in self.caps.values()
                if set(c.requires) <= u and set(c.permissions) <= g and (internet or c.offline)]

    def describe(self, *, up: Iterable[str], granted: Iterable[str], internet: bool = True) -> str:
        """'Horus, what can you help me with right now?'"""
        avail = self.available(up=up, granted=granted, internet=internet)
        missing = [c for c in self.caps.values() if c not in avail]
        lines = ["Right now I can: " + (", ".join(sorted(c.label for c in avail)) or "nothing yet") + "."]
        if missing:
            lines.append("Unavailable: " + ", ".join(sorted(c.label for c in missing)) + ".")
        if not internet:
            lines.append("I'm offline, so only local capabilities are listed.")
        return " ".join(lines)

    def graph(self) -> dict[str, list[dict[str, Any]]]:
        """Capability graph: entity -> what can be observed/inferred/affected and the
        permission/source enabling it."""
        out: dict[str, list[dict[str, Any]]] = {}
        for c in self.caps.values():
            for e in c.entities:
                for v in c.verbs or ["observe"]:
                    out.setdefault(e, []).append({"verb": v, "capability": c.id, "via": c.requires, "permission": c.permissions})
        return out

    def invoke(self, cap_id: str, *, modality: str, granted: Iterable[str], **kwargs: Any) -> dict[str, Any]:
        """Same semantic intent regardless of modality (input-modality independence)."""
        cap = self.caps[cap_id]
        if modality not in cap.modalities:
            return {"ok": False, "error": f"{modality} not supported for {cap.label}"}
        if not set(cap.permissions) <= set(granted):
            return {"ok": False, "error": "permission not granted"}
        unknown = set(kwargs) - set(cap.inputs)
        if unknown:
            return {"ok": False, "error": f"unexpected inputs {sorted(unknown)}"}
        self.usage[cap_id] = self.usage.get(cap_id, 0) + 1
        handler = self.handlers.get(cap_id)
        result = handler(**kwargs) if handler else None
        return {"ok": True, "capability": cap_id, "result": result}

    def quick_actions(self, pinned: Iterable[str] = (), *, slots: int = 4, min_uses: int = 3) -> list[dict[str, str]]:
        """Action tray + Interface-by-Use: pinned first, then frequently used commands
        crystallise into buttons; rarely used ones recede."""
        pinned = [p for p in pinned if p in self.caps]
        frequent = [c for c, n in sorted(self.usage.items(), key=lambda kv: -kv[1]) if n >= min_uses and c not in pinned]
        return [{"id": c, "label": self.caps[c].label} for c in (pinned + frequent)[:slots]]


# =========================================================================== control-lane router

LANES = ("native_api", "accessibility", "dom", "visual")


def route_control(action: str, available_lanes: dict[str, Callable[[str], dict[str, Any]]]) -> dict[str, Any]:
    """Semantic-First Computer Control Router: strongest lane first, VLM last; every
    lane yields the same receipt schema, and lane failures fall through."""
    attempts = []
    for lane in LANES:
        fn = available_lanes.get(lane)
        if fn is None:
            continue
        try:
            r = fn(action)
        except Exception as exc:  # noqa: BLE001
            r = {"ok": False, "error": repr(exc)}
        attempts.append({"lane": lane, "ok": bool(r.get("ok"))})
        if r.get("ok"):
            return {"action": action, "lane": lane, "ok": True, "detail": r, "attempts": attempts,
                    "receipt_id": stable_id(action, lane, length=10)}
    return {"action": action, "lane": None, "ok": False, "attempts": attempts}


# =========================================================================== model / sensing router


@dataclass
class ModelLane:
    name: str
    tier: int  # 0 deterministic, 1 small local, 2 large local, 3 cloud
    local: bool
    latency_ms: float
    cost: float
    max_difficulty: float  # 0..1 calibrated competence


_HARD = re.compile(r"\b(prove|derive|architecture|trade-?offs?|debug|root cause|plan .* steps|legal|diagnos)", re.I)
_BOUNDED = re.compile(r"\b(classify|extract|is this|yes or no|which category|tag|label)\b", re.I)


def difficulty(task: str, *, deterministic_match: bool = False) -> float:
    if deterministic_match:
        return 0.0
    d = 0.35
    if _BOUNDED.search(task):
        d = 0.2
    if _HARD.search(task):
        d = 0.8
    if len(task) > 600:
        d = max(d, 0.6)
    return d


def route_model(task: str, lanes: list[ModelLane], *, deterministic_match: bool = False, private: bool = False,
                max_latency_ms: float | None = None, online: bool = True, budget: float | None = None) -> dict[str, Any]:
    """Local-first, escalate only when difficulty requires it; privacy can forbid
    cloud; latency/cost are constraints, not afterthoughts."""
    d = difficulty(task, deterministic_match=deterministic_match)
    ok = []
    for l in sorted(lanes, key=lambda l: (l.tier, l.cost, l.latency_ms)):
        if l.max_difficulty < d:
            continue
        if private and not l.local:
            continue
        if not online and not l.local:
            continue
        if max_latency_ms is not None and l.latency_ms > max_latency_ms:
            continue
        if budget is not None and l.cost > budget:
            continue
        ok.append(l)
    if not ok:
        return {"lane": None, "difficulty": d, "reason": "no lane satisfies constraints; answer with explicit uncertainty"}
    return {"lane": ok[0].name, "difficulty": d, "tier": ok[0].tier}


def should_sense(expected_gain_bits: float, cost: float, *, value_per_bit: float = 1.0, cached_age_s: float | None = None,
                 ttl_s: float | None = None) -> dict[str, Any]:
    """Cost-aware sensing: use cached data within TTL; spend on an observation only
    when expected information value exceeds its cost."""
    if cached_age_s is not None and ttl_s is not None and cached_age_s <= ttl_s:
        return {"sense": False, "reason": "cached observation still fresh"}
    value = expected_gain_bits * value_per_bit
    return {"sense": value > cost, "reason": f"value {value:.2f} vs cost {cost:.2f}"}


# =========================================================================== personal API / blocks / micro apps


class PersonalAPI:
    """Stable local API over authorized world-model pieces.  Paths: ``entity/attr``.
    Tokens carry explicit read/write scopes per path prefix."""

    def __init__(self, read: Callable[[str, str], Any], write: Callable[[str, str, Any], dict[str, Any]]) -> None:
        self._read, self._write = read, write
        self.tokens: dict[str, dict[str, set[str]]] = {}
        self.audit: list[dict[str, Any]] = []

    def issue(self, name: str, *, read: Iterable[str] = (), write: Iterable[str] = ()) -> str:
        token = hashlib.sha256(f"{name}|{sorted(read)}|{sorted(write)}".encode()).hexdigest()[:20]
        self.tokens[token] = {"read": set(read), "write": set(write)}
        return token

    @staticmethod
    def _allowed(path: str, prefixes: set[str]) -> bool:
        return any(path == p or path.startswith(p.rstrip("*")) for p in prefixes)

    def request(self, token: str, method: str, path: str, body: Any = None) -> dict[str, Any]:
        scopes = self.tokens.get(token)
        method = method.upper()
        if scopes is None:
            status = {"status": 401}
        elif "/" not in path:
            status = {"status": 400, "error": "path must be entity/attribute"}
        else:
            entity, attr = path.split("/", 1)
            if method == "GET" and self._allowed(path, scopes["read"]):
                status = {"status": 200, "value": self._read(entity, attr)}
            elif method == "PUT" and self._allowed(path, scopes["write"]):
                status = {"status": 200, "receipt": self._write(entity, attr, body)}
            else:
                status = {"status": 403}
        self.audit.append({"token": (token or "")[:6], "method": method, "path": path, "status": status["status"]})
        return status


def compose(blocks: dict[str, Callable[[Any], Any]], pipeline: list[str]) -> Callable[[Any], dict[str, Any]]:
    """Composable Capability Blocks: wire named primitives into a workflow with a trace."""
    missing = [b for b in pipeline if b not in blocks]
    if missing:
        raise KeyError(f"unknown blocks {missing}")

    def run(value: Any) -> dict[str, Any]:
        trace = []
        for name in pipeline:
            value = blocks[name](value)
            trace.append({"block": name, "output": plain(value)})
            if value is None:
                return {"result": None, "stopped_at": name, "trace": trace}
        return {"result": value, "trace": trace}

    return run


def micro_app(title: str, capability: Capability, *, endpoint: str) -> str:
    """Personal Micro-App Generator: a tiny standalone accessible HTML form that calls
    a local Personal API endpoint for one capability."""
    fields = []
    for name, typ in capability.inputs.items():
        input_type = {"int": "number", "float": "number", "bool": "checkbox", "date": "date"}.get(typ, "text")
        fid = f"f_{re.sub(r'[^a-z0-9_]', '_', name.lower())}"
        fields.append(f'<label for="{fid}">{html.escape(name)}</label><input id="{fid}" name="{html.escape(name)}" type="{input_type}">')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>body{{font-family:system-ui;margin:16px;max-width:32rem}}label{{display:block;margin-top:12px}}
input,button{{font-size:1rem;padding:8px;width:100%;box-sizing:border-box}}button{{margin-top:16px}}</style></head>
<body><h1>{html.escape(title)}</h1><p>{html.escape(capability.description)}</p>
<form id="f" aria-label="{html.escape(capability.label)}">{''.join(fields)}
<button type="submit">{html.escape(capability.label)}</button></form><output id="out" aria-live="polite"></output>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target).entries());
  const r = await fetch({json.dumps(endpoint)}, {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{capability: {json.dumps(capability.id)}, inputs: data}})}});
  document.getElementById('out').textContent = await r.text();
}});
</script></body></html>
"""


# =========================================================================== mission recorder / mission mode


class MissionRecorder:
    """Observable Autonomy: live goal/subgoal, append-only action stream with state
    snapshots, pause/take-over/abort controls, and deterministic replay."""

    def __init__(self, goal: str) -> None:
        self.goal = goal
        self.subgoal = ""
        self.events: list[dict[str, Any]] = []
        self.state = "running"  # running | paused | human_control | aborted | done

    def _append(self, kind: str, at: datetime, **data: Any) -> dict[str, Any]:
        prev = self.events[-1]["hash"] if self.events else ""
        body = {"seq": len(self.events), "kind": kind, "at": as_dt(at).isoformat(), **plain(data)}
        body["hash"] = hashlib.sha256((prev + json.dumps(body, sort_keys=True)).encode()).hexdigest()[:16]
        self.events.append(body)
        return body

    def set_subgoal(self, subgoal: str, at: datetime) -> None:
        self.subgoal = subgoal
        self._append("subgoal", at, subgoal=subgoal)

    def act(self, action: str, at: datetime, *, snapshot: dict[str, Any] | None = None, receipt: dict[str, Any] | None = None) -> bool:
        if self.state != "running":
            self._append("blocked_action", at, action=action, state=self.state)
            return False
        self._append("action", at, action=action, snapshot=snapshot or {}, receipt=receipt or {})
        return True

    def control(self, command: str, at: datetime, by: str = "user") -> str:
        transitions = {"pause": "paused", "resume": "running", "take_over": "human_control", "abort": "aborted",
                       "hand_back": "running", "complete": "done"}
        if command not in transitions:
            raise ValueError(command)
        if self.state in ("aborted", "done"):
            return self.state
        self.state = transitions[command]
        self._append("control", at, command=command, by=by)
        return self.state

    def live_view(self) -> dict[str, Any]:
        last = [e for e in self.events if e["kind"] == "action"][-3:]
        return {"goal": self.goal, "subgoal": self.subgoal, "state": self.state, "recent_actions": last}

    def verify_integrity(self) -> bool:
        prev = ""
        for e in self.events:
            body = {k: v for k, v in e.items() if k != "hash"}
            if hashlib.sha256((prev + json.dumps(body, sort_keys=True)).encode()).hexdigest()[:16] != e["hash"]:
                return False
            prev = e["hash"]
        return True

    def replay(self, execute: Callable[[str], Any]) -> list[Any]:
        return [execute(e["action"]) for e in self.events if e["kind"] == "action"]


class Mission:
    """Mission Mode: promote a goal into a temporary attention domain with bound
    people/places/messages/documents/sensors/deadlines/automations, then archive."""

    def __init__(self, name: str, *, started: datetime, ends: datetime | None = None) -> None:
        self.name = name
        self.started = as_dt(started)
        self.ends = as_dt(ends) if ends else None
        self.bindings: dict[str, set[str]] = {}
        self.status = "active"
        self.archive: dict[str, Any] | None = None

    def bind(self, kind: str, *ids: str) -> None:
        self.bindings.setdefault(kind, set()).update(ids)

    def auto_bind(self, items: list[dict[str, Any]], keywords: Iterable[str]) -> int:
        kws = [k.lower() for k in keywords]
        n = 0
        for it in items:
            if any(k in it.get("text", "").lower() for k in kws):
                self.bind(it["kind"], it["id"])
                n += 1
        return n

    def attention_weight(self, source_kind: str, item_id: str) -> float:
        return 2.0 if self.status == "active" and item_id in self.bindings.get(source_kind, set()) else 1.0

    def close(self, at: datetime, outcome: str) -> dict[str, Any]:
        self.status = "archived"
        self.archive = {"mission": self.name, "outcome": outcome, "closed_at": as_dt(at).isoformat(),
                        "bindings": {k: sorted(v) for k, v in self.bindings.items()},
                        "retire": ["temporary watches", "mission collectors", "mission automations"]}
        return self.archive


# =========================================================================== state portability


def state_packet(*, mission: str | None, salient_memories: list[str], commitments: list[dict[str, Any]],
                 hypotheses: list[dict[str, Any]], grants: list[dict[str, Any]], provenance: list[str],
                 preferences: dict[str, Any] | None = None) -> str:
    """Agent State Portability / Personal Digital Twin: a serialisable cognitive-state
    packet that survives switching model/runtime backends."""
    body = {"format": "horus-state-packet", "version": 1, "mission": mission, "salient_memories": salient_memories,
            "commitments": commitments, "hypotheses": hypotheses, "grants": grants, "provenance": provenance,
            "preferences": preferences or {}}
    raw = json.dumps(body, sort_keys=True)
    body["checksum"] = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return json.dumps(body, sort_keys=True)


def load_state_packet(payload: str) -> dict[str, Any]:
    body = json.loads(payload)
    checksum = body.pop("checksum", None)
    if body.get("format") != "horus-state-packet":
        raise ValueError("not a HORUS state packet")
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16] != checksum:
        raise ValueError("state packet checksum mismatch")
    return body


def context_preamble(packet: dict[str, Any], max_items: int = 5) -> str:
    """Render the packet as a bounded preamble for whichever model is now active."""
    lines = []
    if packet.get("mission"):
        lines.append(f"Active mission: {packet['mission']}")
    for m in packet.get("salient_memories", [])[:max_items]:
        lines.append(f"Memory: {m}")
    for c in packet.get("commitments", [])[:max_items]:
        lines.append(f"Commitment: {c.get('task')} (due {c.get('due')})")
    for h in packet.get("hypotheses", [])[:max_items]:
        lines.append(f"Open hypothesis: {h.get('text')} ({h.get('confidence')})")
    return "\n".join(lines)


# =========================================================================== compiled website capability / task verification


class CompiledSiteCapability:
    """After a general browser agent succeeds, keep a deterministic adapter; use the
    agent only when the adapter stops satisfying its verifier."""

    def __init__(self, name: str, adapter: Callable[[dict[str, Any]], dict[str, Any]],
                 verifier: Callable[[dict[str, Any]], bool], agent_fallback: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.name, self.adapter, self.verifier, self.agent = name, adapter, verifier, agent_fallback
        self.stats = {"adapter_ok": 0, "adapter_fail": 0, "agent_ok": 0, "agent_fail": 0}

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            out = self.adapter(request)
            if self.verifier(out):
                self.stats["adapter_ok"] += 1
                return {"via": "deterministic_adapter", "result": out}
        except Exception:  # noqa: BLE001
            pass
        self.stats["adapter_fail"] += 1
        out = self.agent(request)
        ok = self.verifier(out)
        self.stats["agent_ok" if ok else "agent_fail"] += 1
        return {"via": "agent_fallback", "result": out, "verified": ok,
                "recompile_suggested": self.stats["adapter_fail"] >= 3}


@dataclass
class ComputerTask:
    id: str
    instruction: str
    reference_state: dict[str, Any]


def evaluate_task(task: ComputerTask, final_state: dict[str, Any]) -> dict[str, Any]:
    """'Clicked the right thing' is not completion: the resulting computer state must
    match the task's reference state."""
    mismatches = {k: {"expected": v, "actual": final_state.get(k)} for k, v in task.reference_state.items()
                  if final_state.get(k) != v}
    return {"task": task.id, "passed": not mismatches, "mismatches": mismatches}
