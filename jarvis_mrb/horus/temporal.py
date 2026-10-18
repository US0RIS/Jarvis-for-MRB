"""Carcosa: temporal truth model, Reality Rewind and Reality Diff.

future.md ideas implemented here: Temporal Truth Model (observed-at, valid-from,
valid-to/superseded-at, source episode, confidence, derivation), Reality Rewind
(``state_at(t)``), Reality Diff, temporal questions as a first-class query language
(before/after, since/until, first/last, duration, recurrence, change points),
world-model bookmarks in conversation ("what changed since this?"), world-model
garbage collection (duplicate merge / zombie retirement with provenance), personal
vocabulary/alias graph with collision disambiguation, teach-by-correction with
propagation and audit history, Reality Graph debugger, Memory Provenance + Revision,
and Long-Now Export of the store.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

from jarvis_mrb.horus._util import as_dt, plain, stable_id


@dataclass
class Fact:
    entity: str
    attribute: str
    value: Any
    valid_from: datetime
    observed_at: datetime
    source_episode: str
    confidence: float = 1.0
    derivation: str = "observed"  # observed | inferred:<rule> | corrected
    derived_from: list[str] = field(default_factory=list)
    valid_to: datetime | None = None
    superseded_by: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        self.valid_from = as_dt(self.valid_from)
        self.observed_at = as_dt(self.observed_at)
        if self.valid_to is not None:
            self.valid_to = as_dt(self.valid_to)
        if not self.id:
            self.id = stable_id(self.entity, self.attribute, self.value, self.valid_from, self.source_episode, length=12)

    def valid_at(self, t: datetime) -> bool:
        t = as_dt(t)
        return self.valid_from <= t and (self.valid_to is None or t < self.valid_to)


class TemporalStore:
    def __init__(self) -> None:
        self.facts: dict[str, Fact] = {}
        self.audit: list[dict[str, Any]] = []
        self.bookmarks: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ writes
    def assert_fact(self, entity: str, attribute: str, value: Any, *, at: datetime, source_episode: str,
                    observed_at: datetime | None = None, confidence: float = 1.0, derivation: str = "observed",
                    derived_from: Iterable[str] = ()) -> Fact:
        """Record that ``attribute`` of ``entity`` became ``value`` at ``at``.
        The currently-open fact (if different) is closed rather than overwritten."""
        at = as_dt(at)
        current = self._open(entity, attribute, at)
        if current is not None and repr(current.value) == repr(value):
            return current
        fact = Fact(entity, attribute, value, at, as_dt(observed_at, at), source_episode, confidence,
                    derivation, list(derived_from))
        if current is not None and current.valid_from <= at:
            current.valid_to = at
            current.superseded_by = fact.id
        # Late-arriving older observation: bound it by the next known fact.
        later = sorted((f for f in self._history(entity, attribute) if f.valid_from > at), key=lambda f: f.valid_from)
        if later:
            fact.valid_to = later[0].valid_from
            fact.superseded_by = later[0].id
        self.facts[fact.id] = fact
        return fact

    def retract(self, fact_id: str, *, at: datetime, reason: str) -> None:
        fact = self.facts[fact_id]
        fact.valid_to = as_dt(at)
        self.audit.append({"op": "retract", "fact": fact_id, "reason": reason, "at": as_dt(at).isoformat()})

    def _history(self, entity: str, attribute: str) -> list[Fact]:
        return sorted((f for f in self.facts.values() if f.entity == entity and f.attribute == attribute),
                      key=lambda f: (f.valid_from, f.observed_at))

    def _open(self, entity: str, attribute: str, at: datetime) -> Fact | None:
        candidates = [f for f in self._history(entity, attribute) if f.valid_at(at)]
        return candidates[-1] if candidates else None

    # ------------------------------------------------------------------ reads
    def value_at(self, entity: str, attribute: str, t: datetime) -> Fact | None:
        return self._open(entity, attribute, as_dt(t))

    def state_at(self, t: datetime, entity: str | None = None) -> dict[str, dict[str, Any]]:
        """Reality Rewind: the world as recorded to be valid at time ``t``."""
        t = as_dt(t)
        out: dict[str, dict[str, Any]] = {}
        for f in self.facts.values():
            if (entity is None or f.entity == entity) and f.valid_at(t):
                out.setdefault(f.entity, {})[f.attribute] = f.value
        return out

    def known_at(self, t: datetime, entity: str | None = None) -> dict[str, dict[str, Any]]:
        """What Jarvis *knew* at ``t`` (bitemporal: excludes facts observed later)."""
        t = as_dt(t)
        out: dict[str, dict[str, Any]] = {}
        for f in sorted(self.facts.values(), key=lambda f: f.valid_from):
            if f.observed_at <= t and f.valid_from <= t and (entity is None or f.entity == entity):
                out.setdefault(f.entity, {})[f.attribute] = f.value
        return out

    def diff(self, t0: datetime, t1: datetime) -> list[dict[str, Any]]:
        """Reality Diff: meaningful changes between two instants."""
        a, b = self.state_at(t0), self.state_at(t1)
        changes = []
        for entity in sorted(set(a) | set(b)):
            ea, eb = a.get(entity, {}), b.get(entity, {})
            if entity not in a:
                changes.append({"entity": entity, "change": "appeared", "state": eb})
                continue
            if entity not in b:
                changes.append({"entity": entity, "change": "disappeared", "state": ea})
                continue
            for attr in sorted(set(ea) | set(eb)):
                if repr(ea.get(attr)) != repr(eb.get(attr)):
                    changes.append({"entity": entity, "attribute": attr, "change": "changed",
                                    "before": ea.get(attr), "after": eb.get(attr)})
        return changes

    # ------------------------------------------------------------------ temporal query language
    def first(self, entity: str, attribute: str, value: Any | None = None) -> Fact | None:
        h = [f for f in self._history(entity, attribute) if value is None or repr(f.value) == repr(value)]
        return h[0] if h else None

    def last(self, entity: str, attribute: str, value: Any | None = None) -> Fact | None:
        h = [f for f in self._history(entity, attribute) if value is None or repr(f.value) == repr(value)]
        return h[-1] if h else None

    def between(self, entity: str, attribute: str, since: datetime, until: datetime) -> list[Fact]:
        s, u = as_dt(since), as_dt(until)
        return [f for f in self._history(entity, attribute)
                if f.valid_from < u and (f.valid_to is None or f.valid_to > s)]

    def duration(self, entity: str, attribute: str, value: Any, since: datetime, until: datetime) -> timedelta:
        s, u = as_dt(since), as_dt(until)
        total = timedelta()
        for f in self.between(entity, attribute, s, u):
            if repr(f.value) != repr(value):
                continue
            start = max(s, f.valid_from)
            end = min(u, f.valid_to or u)
            if end > start:
                total += end - start
        return total

    def change_points(self, entity: str, attribute: str) -> list[datetime]:
        h = self._history(entity, attribute)
        return [f.valid_from for prev, f in zip(h, h[1:]) if repr(prev.value) != repr(f.value)]

    def recurrence(self, entity: str, attribute: str, value: Any) -> dict[str, Any]:
        starts = [f.valid_from for f in self._history(entity, attribute) if repr(f.value) == repr(value)]
        gaps = [(b - a).total_seconds() for a, b in zip(starts, starts[1:])]
        return {"occurrences": len(starts), "mean_interval_s": sum(gaps) / len(gaps) if gaps else None,
                "last": starts[-1].isoformat() if starts else None}

    def before(self, entity: str, attribute: str, t: datetime) -> Fact | None:
        h = [f for f in self._history(entity, attribute) if f.valid_from < as_dt(t)]
        return h[-1] if h else None

    def after(self, entity: str, attribute: str, t: datetime) -> Fact | None:
        h = [f for f in self._history(entity, attribute) if f.valid_from > as_dt(t)]
        return h[0] if h else None

    # ------------------------------------------------------------------ bookmarks
    def bookmark(self, name: str, *, at: datetime, entities: Iterable[str], evidence: Iterable[str] = ()) -> dict[str, Any]:
        ents = list(entities)
        snap = {e: self.state_at(at, e).get(e, {}) for e in ents}
        bm = {"name": name, "at": as_dt(at).isoformat(), "entities": ents, "evidence": list(evidence), "state": snap}
        self.bookmarks[name] = bm
        return bm

    def changed_since(self, name: str, now: datetime) -> list[dict[str, Any]]:
        bm = self.bookmarks[name]
        ents = set(bm["entities"])
        return [c for c in self.diff(as_dt(bm["at"]), now) if c["entity"] in ents]

    # ------------------------------------------------------------------ debugger / provenance
    def explain(self, fact_id: str) -> dict[str, Any]:
        """Reality Graph debugger: why this fact exists and what would invalidate it."""
        f = self.facts[fact_id]
        parents = [self.explain(p) for p in f.derived_from if p in self.facts]
        dependents = [g.id for g in self.facts.values() if fact_id in g.derived_from]
        return {
            "fact": plain(f),
            "created_by": f.source_episode,
            "derivation": f.derivation,
            "derived_from": parents,
            "dependents": dependents,
            "invalidated_if": [
                f"a newer observation of {f.entity}.{f.attribute} with a different value",
                *[f"retraction of {p}" for p in f.derived_from],
            ],
            "audit": [a for a in self.audit if a.get("fact") == fact_id],
        }

    def correct(self, fact_id: str, new_value: Any, *, at: datetime, by: str) -> dict[str, Any]:
        """Teach-by-correction: replace a wrong fact and flag dependent inferences."""
        old = self.facts[fact_id]
        old.valid_to = old.valid_from  # zero-width: never true
        new = Fact(old.entity, old.attribute, new_value, old.valid_from, as_dt(at), f"correction:{by}",
                   1.0, "corrected", [], None)
        old.superseded_by = new.id
        self.facts[new.id] = new
        affected = self._dependents_closure(fact_id)
        for d in affected:
            self.facts[d].confidence = 0.0
        entry = {"op": "correct", "fact": fact_id, "replacement": new.id, "by": by,
                 "at": as_dt(at).isoformat(), "invalidated_dependents": affected}
        self.audit.append(entry)
        return entry

    def _dependents_closure(self, fact_id: str) -> list[str]:
        out, stack = [], [fact_id]
        while stack:
            cur = stack.pop()
            for g in self.facts.values():
                if cur in g.derived_from and g.id not in out:
                    out.append(g.id)
                    stack.append(g.id)
        return out

    # ------------------------------------------------------------------ GC
    def garbage_collect(self, *, now: datetime, stale_after: timedelta, merges: dict[str, str] | None = None) -> dict[str, Any]:
        """Merge duplicate entities (``merges`` old->canonical), retire zombie open facts
        that have not been re-observed within ``stale_after``.  Provenance is preserved:
        facts are closed and annotated, never deleted."""
        now = as_dt(now)
        merged = 0
        for f in self.facts.values():
            if merges and f.entity in merges:
                self.audit.append({"op": "merge", "fact": f.id, "from": f.entity, "to": merges[f.entity],
                                   "at": now.isoformat()})
                f.entity = merges[f.entity]
                merged += 1
        retired = []
        for f in self.facts.values():
            if f.valid_to is None and f.derivation != "stable" and now - f.observed_at > stale_after:
                f.valid_to = now
                f.confidence = min(f.confidence, 0.2)
                retired.append(f.id)
                self.audit.append({"op": "retire-stale", "fact": f.id, "at": now.isoformat()})
        # Collapse exact duplicate open facts produced by merges.
        seen: dict[tuple, str] = {}
        collapsed = []
        for f in sorted(self.facts.values(), key=lambda f: f.valid_from):
            if f.valid_to is not None:
                continue
            key = (f.entity, f.attribute)
            if key in seen:
                prior = self.facts[seen[key]]
                if repr(prior.value) == repr(f.value):
                    f.valid_to = f.valid_from
                    f.superseded_by = prior.id
                    collapsed.append(f.id)
                    continue
            seen[key] = f.id
        return {"merged_facts": merged, "retired": retired, "collapsed_duplicates": collapsed}

    # ------------------------------------------------------------------ export
    def export(self) -> str:
        """Long-Now Export: documented portable JSON (schema version + provenance)."""
        return json.dumps({
            "format": "horus-temporal-store",
            "version": 1,
            "doc": "facts are bitemporal: valid_from/valid_to (world time) and observed_at (knowledge time)",
            "facts": [plain(f) for f in sorted(self.facts.values(), key=lambda f: f.id)],
            "audit": self.audit,
            "bookmarks": self.bookmarks,
        }, indent=1, sort_keys=True)

    @classmethod
    def import_(cls, payload: str) -> "TemporalStore":
        data = json.loads(payload)
        if data.get("format") != "horus-temporal-store":
            raise ValueError("not a HORUS temporal export")
        store = cls()
        for raw in data["facts"]:
            f = Fact(**{k: v for k, v in raw.items()})
            store.facts[f.id] = f
        store.audit = list(data.get("audit", []))
        store.bookmarks = dict(data.get("bookmarks", {}))
        return store


class AliasGraph:
    """Personal vocabulary: informal names -> entity ids, with collision handling."""

    def __init__(self) -> None:
        self.aliases: dict[str, dict[str, float]] = {}
        self.history: list[dict[str, Any]] = []

    @staticmethod
    def _norm(alias: str) -> str:
        return " ".join(alias.lower().replace("’", "'").split()).removeprefix("the ")

    def learn(self, alias: str, entity: str, weight: float = 1.0) -> None:
        bucket = self.aliases.setdefault(self._norm(alias), {})
        bucket[entity] = bucket.get(entity, 0.0) + weight

    def resolve(self, alias: str, context_entities: Iterable[str] = ()) -> dict[str, Any]:
        bucket = self.aliases.get(self._norm(alias), {})
        if not bucket:
            return {"status": "unknown", "candidates": []}
        ctx = set(context_entities)
        scored = sorted(((e, w + (2.0 if e in ctx else 0.0)) for e, w in bucket.items()), key=lambda x: -x[1])
        if len(scored) == 1 or scored[0][1] >= 2 * scored[1][1]:
            return {"status": "resolved", "entity": scored[0][0], "candidates": [e for e, _ in scored]}
        return {"status": "ambiguous", "candidates": [e for e, _ in scored],
                "question": f"Which do you mean by '{alias}': " + " or ".join(e for e, _ in scored[:3]) + "?"}

    def correct(self, alias: str, wrong: str, right: str, *, at: datetime) -> None:
        bucket = self.aliases.setdefault(self._norm(alias), {})
        bucket.pop(wrong, None)
        bucket[right] = bucket.get(right, 0.0) + 3.0
        self.history.append({"alias": alias, "wrong": wrong, "right": right, "at": as_dt(at).isoformat()})
