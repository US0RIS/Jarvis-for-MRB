"""Standing Query Reality Engine, Reality Compiler and watch lifecycle (Cassandra).

future.md ideas implemented here: Standing Query Reality Engine (persistent queries
emitting events only on result-set changes), Reality Compiler (English -> inspectable
monitoring program), Editable Generated Logic (the program is a readable DSL),
One-command temporary watch, Automatic watch retirement, Follow-the-entity,
World Assertions / desired-state controller, Invariant Watchdog (level-triggered,
re-evaluated on startup/reconnect), Failure-State Awareness ("no alert" != "all
clear"), Critical-Sensor Redundancy, Replayable automations and Counterfactual
Automation Testing (dry-run over history), Condition-Relative Recurrence,
Auto-Resolving Tasks, Eventification Layer (continuous -> sparse typed events),
Web Observation Fabric (normalised value diffing), Automation State Machines,
State Restoration, Automation Versioning, and Closed-loop Outcome Mode.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, plain, stable_id

# =========================================================================== predicate DSL

_TOKEN = re.compile(
    r"\s*(?:(?P<num>-?\d+(?:\.\d+)?)|(?P<str>'[^']*'|\"[^\"]*\")|(?P<op><=|>=|==|!=|<|>|\(|\)|,)"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_.]*))"
)


class PredicateError(ValueError):
    pass


def _tokenize(text: str) -> list[tuple[str, Any]]:
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise PredicateError(f"cannot parse near {text[pos:pos + 12]!r}")
        pos = m.end()
        if m.group("num") is not None:
            out.append(("lit", float(m.group("num"))))
        elif m.group("str") is not None:
            out.append(("lit", m.group("str")[1:-1]))
        elif m.group("op") is not None:
            out.append(("op", m.group("op")))
        else:
            w = m.group("word")
            lw = w.lower()
            if lw in ("and", "or", "not", "in"):
                out.append(("kw", lw))
            elif lw in ("true", "false"):
                out.append(("lit", lw == "true"))
            elif lw in ("null", "none"):
                out.append(("lit", None))
            else:
                out.append(("field", w))
    return out


class Predicate:
    """Safe boolean expression over a record (no ``eval``).

    Grammar: expr := or ; or := and ('or' and)* ; and := not ('and' not)* ;
    not := 'not' not | cmp ; cmp := atom (op atom | 'in' '(' list ')')? ;
    atom := number | string | true/false/null | field.path | '(' expr ')'.
    """

    def __init__(self, source: str) -> None:
        self.source = source.strip()
        self._toks = _tokenize(self.source)
        self._i = 0
        self.ast = self._or()
        if self._i != len(self._toks):
            raise PredicateError(f"unexpected token {self._toks[self._i]}")

    def _peek(self) -> tuple[str, Any] | None:
        return self._toks[self._i] if self._i < len(self._toks) else None

    def _take(self) -> tuple[str, Any]:
        tok = self._peek()
        if tok is None:
            raise PredicateError("unexpected end of expression")
        self._i += 1
        return tok

    def _or(self) -> Any:
        node = self._and()
        while self._peek() == ("kw", "or"):
            self._take()
            node = ("or", node, self._and())
        return node

    def _and(self) -> Any:
        node = self._not()
        while self._peek() == ("kw", "and"):
            self._take()
            node = ("and", node, self._not())
        return node

    def _not(self) -> Any:
        if self._peek() == ("kw", "not"):
            self._take()
            return ("not", self._not())
        return self._cmp()

    def _cmp(self) -> Any:
        left = self._atom()
        tok = self._peek()
        if tok and tok[0] == "op" and tok[1] in ("<", ">", "<=", ">=", "==", "!="):
            self._take()
            return ("cmp", tok[1], left, self._atom())
        if tok == ("kw", "in"):
            self._take()
            if self._take() != ("op", "("):
                raise PredicateError("expected ( after in")
            items = [self._atom()]
            while self._peek() == ("op", ","):
                self._take()
                items.append(self._atom())
            if self._take() != ("op", ")"):
                raise PredicateError("expected )")
            return ("in", left, items)
        return ("truthy", left)

    def _atom(self) -> Any:
        tok = self._take()
        if tok == ("op", "("):
            node = self._or()
            if self._take() != ("op", ")"):
                raise PredicateError("expected )")
            return node
        if tok[0] in ("lit", "field"):
            return tok
        raise PredicateError(f"unexpected {tok}")

    @staticmethod
    def _get(record: dict[str, Any], path: str) -> Any:
        cur: Any = record
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    def _eval(self, node: Any, rec: dict[str, Any]) -> Any:
        kind = node[0]
        if kind == "lit":
            return node[1]
        if kind == "field":
            return self._get(rec, node[1])
        if kind == "and":
            return bool(self._eval(node[1], rec)) and bool(self._eval(node[2], rec))
        if kind == "or":
            return bool(self._eval(node[1], rec)) or bool(self._eval(node[2], rec))
        if kind == "not":
            return not bool(self._eval(node[1], rec))
        if kind == "truthy":
            return bool(self._eval(node[1], rec))
        if kind == "in":
            v = self._eval(node[1], rec)
            return v in [self._eval(i, rec) for i in node[2]]
        if kind == "cmp":
            op, a, b = node[1], self._eval(node[2], rec), self._eval(node[3], rec)
            if op == "==":
                return a == b
            if op == "!=":
                return a != b
            if a is None or b is None:
                return False  # missing evidence never satisfies an ordering comparison
            try:
                return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
            except TypeError:
                return False
        raise PredicateError(kind)

    def __call__(self, record: dict[str, Any]) -> bool:
        return bool(self._eval(self.ast, record))

    def fields(self) -> set[str]:
        out: set[str] = set()

        def walk(n: Any) -> None:
            if isinstance(n, list):
                for item in n:
                    walk(item)
            elif isinstance(n, tuple) and n:
                if n[0] == "field":
                    out.add(n[1])
                elif n[0] != "lit":
                    for item in n[1:]:
                        walk(item)

        walk(self.ast)
        return out


# =========================================================================== standing queries


@dataclass
class StandingQuery:
    id: str
    where: str
    key: str = "id"
    expires_at: datetime | None = None
    purpose: str = ""
    owner: str = "user"
    _members: set[str] = field(default_factory=set, repr=False)
    _pred: Predicate | None = field(default=None, repr=False)

    def predicate(self) -> Predicate:
        if self._pred is None:
            self._pred = Predicate(self.where)
        return self._pred


class StandingQueryEngine:
    """Emits ``entered``/``left`` events only when a query's result set changes."""

    def __init__(self) -> None:
        self.queries: dict[str, StandingQuery] = {}
        self.retired: list[dict[str, Any]] = []

    def register(self, q: StandingQuery) -> StandingQuery:
        q.predicate()  # validate eagerly
        self.queries[q.id] = q
        return q

    def evaluate(self, records: Iterable[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
        now = as_dt(now)
        recs = list(records)
        events = []
        for q in list(self.queries.values()):
            if q.expires_at is not None and now >= as_dt(q.expires_at):
                self.retire(q.id, now, "ttl-expired")
                continue
            pred = q.predicate()
            current = {str(r.get(q.key)) for r in recs if pred(r)}
            for k in sorted(current - q._members):
                events.append({"query": q.id, "event": "entered", "key": k, "at": now.isoformat()})
            for k in sorted(q._members - current):
                events.append({"query": q.id, "event": "left", "key": k, "at": now.isoformat()})
            q._members = current
        return events

    def retire(self, query_id: str, now: datetime, reason: str) -> None:
        q = self.queries.pop(query_id, None)
        if q is not None:
            self.retired.append({"query": query_id, "reason": reason, "at": as_dt(now).isoformat()})


# =========================================================================== reality compiler

_DURATION = re.compile(r"(?:for )?(?:the )?next (\w+) (minute|minutes|hour|hours|day|days)")
_WORD_NUM = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "ten": 10, "twelve": 12, "twenty": 20, "thirty": 30, "few": 3}


def _parse_duration(text: str) -> timedelta | None:
    m = _DURATION.search(text)
    if not m:
        return None
    n_raw = m.group(1)
    n = float(n_raw) if n_raw.replace(".", "").isdigit() else _WORD_NUM.get(n_raw)
    if n is None:
        return None
    unit = m.group(2).rstrip("s")
    return timedelta(**{unit + "s": n})


_COMPILE_RULES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], dict[str, Any]]]] = [
    (re.compile(r"(?:tell|alert|notify) me (?:if|when) (?:the )?([\w .]+?) (?:drops|falls|goes) below ([\d.]+)"),
     lambda m: {"collector": m.group(1).strip(), "where": f"{_field(m.group(1))} < {m.group(2)}"}),
    (re.compile(r"(?:tell|alert|notify) me (?:if|when) (?:the )?([\w .]+?) (?:rises|goes|gets) above ([\d.]+)"),
     lambda m: {"collector": m.group(1).strip(), "where": f"{_field(m.group(1))} > {m.group(2)}"}),
    (re.compile(r"(?:tell|alert|notify) me (?:if|when) (?:the )?([\w .]+?) (?:enters|arrives at|reaches) (?:the )?([\w .]+)"),
     lambda m: {"collector": "geofence", "where": f"entity == '{m.group(1).strip()}' and zone == '{m.group(2).strip()}'"}),
    (re.compile(r"(?:tell|alert|notify) me (?:if|when) (?:the )?([\w .]+?) (?:changes|is updated)"),
     lambda m: {"collector": "web_observation", "where": f"subject == '{m.group(1).strip()}' and changed == true"}),
    (re.compile(r"watch (?:the )?([\w .]+?)(?: for| $|$)"),
     lambda m: {"collector": m.group(1).strip(), "where": f"subject == '{m.group(1).strip()}' and changed == true"}),
]


def _field(phrase: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", phrase.strip().lower()).strip("_")


def compile_intent(text: str, *, now: datetime | None = None, default_ttl: timedelta | None = None,
                   context_entity: str | None = None) -> dict[str, Any]:
    """Reality Compiler: English intent -> inspectable, editable monitoring program.

    Unrecognised intents are returned as ``needs_clarification`` instead of guessed."""
    now = as_dt(now)
    lowered = " ".join(text.lower().split())
    if context_entity:
        lowered = re.sub(r"\b(this|that|it)\b", context_entity.lower(), lowered, count=1)
    ttl = _parse_duration(lowered) or default_ttl
    for pattern, build in _COMPILE_RULES:
        m = pattern.search(lowered)
        if m:
            spec = build(m)
            Predicate(spec["where"])  # validate
            program = {
                "id": stable_id(text, now, length=10),
                "source_text": text,
                "collector": spec["collector"],
                "where": spec["where"],
                "trigger": "on-result-set-change",
                "notify": {"policy": "attention-budgeted", "explain_why": True},
                "verification": "re-check condition on fresh observation before notifying",
                "expires_at": (now + ttl).isoformat() if ttl else None,
                "cleanup": "retire collector and query at expiry or when mission ends",
                "status": "compiled",
            }
            return program
    return {"source_text": text, "status": "needs_clarification",
            "question": "What should I watch, and what change should trigger a notification?"}


def to_standing_query(program: dict[str, Any]) -> StandingQuery:
    if program.get("status") != "compiled":
        raise ValueError("program not compiled")
    exp = program.get("expires_at")
    return StandingQuery(program["id"], program["where"], key=program.get("key", "id"),
                         expires_at=as_dt(exp) if exp else None, purpose=program["source_text"])


def follow_entity(entity_position: tuple[float, float], sources: list[dict[str, Any]], *, radius_m: float) -> list[str]:
    """Follow-the-entity: choose lawful sources whose coverage contains the entity now."""
    from jarvis_mrb.horus._util import haversine_m

    lat, lon = entity_position
    chosen = [(haversine_m(lat, lon, s["lat"], s["lon"]), s["id"]) for s in sources
              if s.get("lawful", True) and haversine_m(lat, lon, s["lat"], s["lon"]) <= s.get("radius_m", radius_m)]
    return [sid for _, sid in sorted(chosen)]


# =========================================================================== assertions / invariants


@dataclass
class Assertion:
    """World Assertion / invariant with evidence sufficiency (Failure-State Awareness)."""

    id: str
    where: str
    required_sources: int = 1
    max_age_s: float = 900.0
    intervention: str = ""
    critical: bool = False


def evaluate_assertion(a: Assertion, readings: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Readings: ``{"source", "observed_at", "battery"?, "depends_on"?, **fields}``.

    Status is one of ``holds``, ``violated``, ``insufficient_evidence`` (never treated as
    all-clear), or ``sensor_disagreement``."""
    now = as_dt(now)
    pred = Predicate(a.where)
    live, problems = [], []
    for r in readings:
        age = (now - as_dt(r["observed_at"])).total_seconds()
        if age > a.max_age_s:
            problems.append(f"{r['source']}: stale ({int(age)}s)")
        elif r.get("battery") is not None and r["battery"] <= 0.05:
            problems.append(f"{r['source']}: battery dead")
        else:
            live.append(r)
    common = {}
    for r in live:
        for dep in r.get("depends_on", []):
            common.setdefault(dep, []).append(r["source"])
    common_mode = {d: s for d, s in common.items() if len(s) > 1 and len(s) == len(live)}
    independent = 1 if common_mode else len(live)
    verdicts = {r["source"]: pred(r) for r in live}
    if independent < a.required_sources:
        status = "insufficient_evidence"
    elif len(set(verdicts.values())) > 1:
        status = "sensor_disagreement"
    elif all(verdicts.values()):
        status = "holds"
    else:
        status = "violated"
    return {"assertion": a.id, "status": status, "live_sources": [r["source"] for r in live],
            "problems": problems, "common_mode_dependencies": common_mode, "verdicts": verdicts,
            "intervention": a.intervention if status == "violated" else None,
            "all_clear": status == "holds"}


class InvariantWatchdog:
    """Level-triggered checks: re-evaluated on startup/reconnect/recovery and
    periodically, so a bad state that began while offline is still caught."""

    TRIGGERS = ("startup", "reconnect", "sensor_recovery", "periodic")

    def __init__(self, assertions: Iterable[Assertion]) -> None:
        self.assertions = {a.id: a for a in assertions}
        self.last_status: dict[str, str] = {}

    def check(self, trigger: str, readings_by_assertion: dict[str, list[dict[str, Any]]],
              now: datetime | None = None) -> list[dict[str, Any]]:
        if trigger not in self.TRIGGERS:
            raise ValueError(trigger)
        alerts = []
        for aid, a in self.assertions.items():
            result = evaluate_assertion(a, readings_by_assertion.get(aid, []), now)
            if result["status"] != "holds":
                # Level-triggered: violated states alert on every non-periodic re-check
                # and whenever status changes, not only on the first edge.
                if trigger != "periodic" or self.last_status.get(aid) != result["status"]:
                    alerts.append({**result, "trigger": trigger})
            self.last_status[aid] = result["status"]
        return alerts


# =========================================================================== replay / counterfactual testing


def replay_automation(where: str, history: list[dict[str, Any]], *, cooldown_s: float = 0.0,
                      labels: dict[str, bool] | None = None) -> dict[str, Any]:
    """Dry-run a rule over historical records (with ``at`` and optional ``id``).
    ``labels`` maps record id -> whether firing would have been wanted."""
    pred = Predicate(where)
    fires, last = [], None
    for rec in sorted(history, key=lambda r: as_dt(r["at"])):
        if pred(rec):
            at = as_dt(rec["at"])
            if last is None or (at - last).total_seconds() >= cooldown_s:
                fires.append(rec)
                last = at
    result: dict[str, Any] = {"would_fire": len(fires), "fires": [plain(f) for f in fires]}
    if labels is not None:
        fired_ids = {str(f.get("id")) for f in fires}
        fp = [i for i in fired_ids if labels.get(i) is False]
        fn = [i for i, wanted in labels.items() if wanted and i not in fired_ids]
        result.update({"false_positives": sorted(fp), "missed": sorted(fn),
                       "precision": (len(fired_ids) - len(fp)) / len(fired_ids) if fired_ids else None})
    return result


# =========================================================================== recurrence / tasks


@dataclass
class ConditionRecurrence:
    """'30 days after I actually changed the filter' rather than calendar recurrence."""

    task: str
    completion_event: str
    interval: timedelta
    last_completed: datetime | None = None

    def observe(self, event: str, at: datetime) -> None:
        if event == self.completion_event:
            self.last_completed = as_dt(at)

    def due_at(self) -> datetime | None:
        return None if self.last_completed is None else self.last_completed + self.interval

    def is_due(self, now: datetime) -> bool:
        due = self.due_at()
        return due is None or as_dt(now) >= due


@dataclass
class SelfResolvingTask:
    """Auto-Resolving Task: completes when reality proves the condition."""

    title: str
    resolves_when: str
    status: str = "open"
    resolved_by: dict[str, Any] | None = None

    def offer(self, observation: dict[str, Any]) -> bool:
        if self.status == "open" and Predicate(self.resolves_when)(observation):
            self.status = "done"
            self.resolved_by = observation
            return True
        return False


# =========================================================================== eventification / web observation


def eventify(series: list[tuple[datetime, float]], *, threshold: float, hysteresis: float = 0.0,
             name: str = "value", evidence_ref: str = "") -> list[dict[str, Any]]:
    """Convert a continuous series into sparse threshold-crossing events with hysteresis."""
    events, above = [], None
    for t, v in series:
        if above is None:
            above = v > threshold
            continue
        if not above and v > threshold + hysteresis:
            above = True
            events.append({"event": f"{name}_rose_above", "threshold": threshold, "value": v, "at": as_dt(t).isoformat(),
                           "evidence": evidence_ref})
        elif above and v < threshold - hysteresis:
            above = False
            events.append({"event": f"{name}_fell_below", "threshold": threshold, "value": v, "at": as_dt(t).isoformat(),
                           "evidence": evidence_ref})
    return events


def normalize_web_value(text: str, *, ignore_patterns: Iterable[str] = ()) -> str:
    out = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
    out = re.sub(r"<[^>]+>", " ", out)
    for p in ignore_patterns:
        out = re.sub(p, " ", out)
    return " ".join(out.split())


class WebObservation:
    """Web Observation Fabric: page/selector value -> normalised observation -> diff event."""

    def __init__(self, url: str, *, ignore_patterns: Iterable[str] = (r"\b\d{1,2}:\d{2}(?::\d{2})?\b",)) -> None:
        self.url = url
        self.ignore = list(ignore_patterns)
        self.last: str | None = None
        self.history: list[dict[str, Any]] = []

    def observe(self, raw: str, at: datetime) -> dict[str, Any] | None:
        value = normalize_web_value(raw, ignore_patterns=self.ignore)
        if self.last is None:
            self.last = value
            self.history.append({"at": as_dt(at).isoformat(), "value": value})
            return None
        if value == self.last:
            return None
        diff = list(difflib.unified_diff(self.last.split(". "), value.split(". "), lineterm="", n=0))
        event = {"event": "web_changed", "url": self.url, "at": as_dt(at).isoformat(),
                 "diff": [d for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---"))]}
        self.last = value
        self.history.append({"at": as_dt(at).isoformat(), "value": value})
        return event


# =========================================================================== state machines / restoration / versions


class StateMachine:
    """Automation State Machines with explicit permitted transitions and annunciation."""

    def __init__(self, name: str, states: Iterable[str], transitions: dict[str, Iterable[str]], initial: str) -> None:
        self.name = name
        self.states = set(states)
        self.transitions = {k: set(v) for k, v in transitions.items()}
        if initial not in self.states:
            raise ValueError(initial)
        self.state = initial
        self.log: list[dict[str, Any]] = []

    def can(self, target: str) -> bool:
        return target in self.transitions.get(self.state, set())

    def transition(self, target: str, *, cause: str, at: datetime) -> dict[str, Any]:
        if target not in self.states:
            raise ValueError(f"unknown state {target}")
        if not self.can(target):
            raise PermissionError(f"{self.name}: {self.state} -> {target} not permitted")
        entry = {"machine": self.name, "from": self.state, "to": target, "cause": cause,
                 "at": as_dt(at).isoformat(),
                 "announce": f"{self.name} changed from {self.state} to {target} because {cause}"}
        self.state = target
        self.log.append(entry)
        return entry


class StateRestorer:
    """State Restoration: temporary changes remember prior state and restore it."""

    def __init__(self) -> None:
        self.saved: dict[str, list[Any]] = {}

    def apply(self, key: str, current: Any, new: Any, setter: Callable[[Any], None]) -> None:
        self.saved.setdefault(key, []).append(current)
        setter(new)

    def restore(self, key: str, setter: Callable[[Any], None]) -> Any:
        stack = self.saved.get(key)
        if not stack:
            raise KeyError(f"nothing saved for {key}")
        prior = stack.pop()
        setter(prior)
        return prior


class AutomationVersions:
    """Automation Versioning: diffs, tests, rollback, provenance."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.versions: list[dict[str, Any]] = []
        self.active: int | None = None

    def commit(self, rule: str, *, author: str, note: str, tests: list[tuple[dict[str, Any], bool]] = ()) -> int:
        pred = Predicate(rule)
        failures = [rec for rec, expected in tests if pred(rec) != expected]
        if failures:
            raise AssertionError(f"{len(failures)} test(s) fail for new version")
        prev = self.versions[-1]["rule"] if self.versions else ""
        diff = list(difflib.unified_diff([prev], [rule], lineterm="", n=0))
        self.versions.append({"version": len(self.versions) + 1, "rule": rule, "author": author, "note": note,
                              "diff": diff, "tests": len(list(tests))})
        self.active = len(self.versions)
        return self.active

    def rollback(self, to_version: int) -> str:
        if not 1 <= to_version <= len(self.versions):
            raise ValueError(to_version)
        self.active = to_version
        return self.versions[to_version - 1]["rule"]

    def current(self) -> str:
        if self.active is None:
            raise LookupError("no versions")
        return self.versions[self.active - 1]["rule"]


# =========================================================================== closed loop


def closed_loop_step(desired: str, observe: Callable[[], dict[str, Any]], interventions: list[dict[str, Any]],
                     act: Callable[[dict[str, Any]], dict[str, Any]], *, authorized: set[str]) -> dict[str, Any]:
    """Desired World -> Current World -> Difference -> Intervention -> Verification.

    ``interventions`` are tried in order (reversible first); only authorized ids run;
    each action is verified by re-observing.  Returns the full receipt trail."""
    pred = Predicate(desired)
    trail: list[dict[str, Any]] = []
    state = observe()
    if pred(state):
        return {"status": "satisfied", "trail": trail}
    for iv in sorted(interventions, key=lambda i: (not i.get("reversible", False), i.get("cost", 0))):
        if iv["id"] not in authorized:
            trail.append({"intervention": iv["id"], "skipped": "not authorized"})
            continue
        receipt = act(iv)
        after = observe()
        ok = pred(after)
        trail.append({"intervention": iv["id"], "receipt": receipt, "verified": ok, "observed": after})
        if ok:
            return {"status": "satisfied_after_intervention", "trail": trail}
        if iv.get("rollback") and receipt.get("applied"):
            trail.append({"rollback": iv["id"], "result": act({"id": iv["rollback"], "rollback_of": iv["id"]})})
    return {"status": "unsatisfied:escalate_to_user", "trail": trail}
