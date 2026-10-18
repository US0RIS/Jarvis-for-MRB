"""Mnemosyne: capture, promotion and memory that returns at the useful moment.

future.md ideas implemented here: Zero-Friction Capture Bus, Capture Current
Context Automatically, Why-I-Saved-It Memory, Ambient "remember this" capture
auto-tagged to entities, Automatic Connection Discovery (suggested, never silently
applied), Memory Promotion Pipeline, Memory Provenance + Revision, Contextual
Resurfacing, Knowledge Activation Queue, Application Test for Knowledge, Memory
Utility Tracking, Forgetting-Aware Compression, Spaced Resurfacing, Unified "ask
everything I know" search with source/freshness disclosure, "Why isn't this
automatic?" log, Personal Friction Miner, Capability Gap Detection,
Feature-Idea Harvester review queue, Spatial Bookmarks, Physical Ctrl-F and the
Spatial Inbox.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

from jarvis_mrb.horus._util import as_dt, haversine_m, jaccard, plain, stable_id, tokens

KINDS = ("thought", "screenshot", "photo", "url", "media", "selection", "file", "location", "object", "gesture", "voice")


@dataclass
class Capture:
    id: str
    kind: str
    raw: str  # raw source preserved verbatim (text, URL, file path, transcript...)
    at: datetime
    context: dict[str, Any] = field(default_factory=dict)
    why: str = ""
    entities: list[str] = field(default_factory=list)
    status: str = "saved"  # saved | processed | understood | applied
    retrievals: int = 0
    decisions_changed: int = 0
    summaries: dict[str, str] = field(default_factory=dict)


@dataclass
class MemoryFact:
    id: str
    statement: str
    kind: str  # fact | preference | procedure | project_knowledge
    provenance: list[str]  # capture ids / message ids / document ids
    confidence: float
    created_at: datetime
    status: str = "active"  # active | superseded | expired | retracted
    superseded_by: str | None = None
    expires_at: datetime | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


class EntityTagger:
    """Auto-tags captures into known world-model entities by name/alias mention."""

    def __init__(self, entities: dict[str, Iterable[str]] | None = None) -> None:
        self.aliases: dict[str, set[str]] = {}
        for eid, names in (entities or {}).items():
            self.add(eid, names)

    def add(self, entity_id: str, names: Iterable[str]) -> None:
        self.aliases[entity_id] = {n.lower() for n in names}

    def tag(self, text: str) -> list[str]:
        lowered = text.lower()
        return sorted(e for e, names in self.aliases.items()
                      if any(re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", lowered) for n in names))


class MemoryStore:
    def __init__(self, tagger: EntityTagger | None = None) -> None:
        self.captures: dict[str, Capture] = {}
        self.facts: dict[str, MemoryFact] = {}
        self.tagger = tagger or EntityTagger()
        self.suggestions: list[dict[str, Any]] = []
        self.review_queue: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ capture bus
    def capture(self, kind: str, raw: str, *, at: datetime, context: dict[str, Any] | None = None,
                why: str = "") -> Capture:
        """One action, no metadata demanded.  Context (on-screen app/document, playing
        media, place, mission, nearby entities, recent conversation) is attached when
        the caller provides it; the reason is inferred from active goal if absent."""
        if kind not in KINDS:
            raise ValueError(f"unknown capture kind {kind}")
        ctx = dict(context or {})
        reason = why or (f"while working on {ctx['mission']}" if ctx.get("mission") else
                         f"while viewing {ctx['document']}" if ctx.get("document") else "")
        text_for_tags = " ".join([raw, str(ctx.get("conversation", ""))])
        entities = sorted(set(self.tagger.tag(text_for_tags)) | set(ctx.get("nearby_entities", [])))
        c = Capture(stable_id(kind, raw, at, length=12), kind, raw, as_dt(at), ctx, reason, entities)
        self.captures[c.id] = c
        return c

    def remember_this(self, utterance: str, *, at: datetime, context: dict[str, Any] | None = None) -> Capture:
        """Ambient voice capture: strips the command phrase and tags entities."""
        text = re.sub(r"^(?:horus[, ]+)?(?:remember (?:this|that)|note (?:this|that)|remind me)[:, ]*", "", utterance.strip(),
                      flags=re.I)
        return self.capture("voice", text, at=at, context=context)

    # ------------------------------------------------------------------ connections
    def discover_connections(self, *, min_similarity: float = 0.25, temporal_window: timedelta = timedelta(hours=2),
                             spatial_m: float = 150.0) -> list[dict[str, Any]]:
        """Suggest semantic/temporal/spatial/people-project links; never auto-apply."""
        caps = sorted(self.captures.values(), key=lambda c: c.at)
        out = []
        for i, a in enumerate(caps):
            ta = set(tokens(a.raw))
            for b in caps[i + 1:]:
                reasons = []
                sim = jaccard(ta, tokens(b.raw))
                if sim >= min_similarity:
                    reasons.append(f"semantic:{sim:.2f}")
                shared = set(a.entities) & set(b.entities)
                if shared:
                    reasons.append("shared-entities:" + ",".join(sorted(shared)))
                if abs(b.at - a.at) <= temporal_window and a.context.get("mission") and \
                        a.context.get("mission") == b.context.get("mission"):
                    reasons.append("same-mission-same-time")
                la, lb = a.context.get("latlon"), b.context.get("latlon")
                if la and lb and haversine_m(*la, *lb) <= spatial_m:
                    reasons.append("same-place")
                if reasons:
                    out.append({"a": a.id, "b": b.id, "reasons": reasons, "status": "suggested"})
        self.suggestions = out
        return out

    # ------------------------------------------------------------------ promotion / provenance
    def propose_promotions(self, *, min_occurrences: int = 2) -> list[dict[str, Any]]:
        """Repeated/corroborated statements become promotion proposals; conflicts → review."""
        norm: dict[str, list[Capture]] = {}
        for c in self.captures.values():
            key = " ".join(tokens(c.raw))
            if key:
                norm.setdefault(key, []).append(c)
        proposals = []
        for key, cs in norm.items():
            if len(cs) >= min_occurrences:
                kind = "preference" if re.search(r"\b(prefer\w*|like[sd]?|hates?|favou?rite|always|never)\b", cs[0].raw.lower()) else \
                    "procedure" if re.search(r"\b(step|first|then|how to)\b", cs[0].raw.lower()) else "fact"
                proposals.append({"statement": cs[0].raw, "kind": kind, "provenance": [c.id for c in cs],
                                  "status": "proposed"})
        for p in proposals:
            for f in self.facts.values():
                if f.status == "active" and _contradicts(f.statement, p["statement"]):
                    p["status"] = "needs_review"
                    p["conflicts_with"] = f.id
        return proposals

    def promote(self, statement: str, kind: str, provenance: list[str], *, at: datetime,
                confidence: float = 0.8, expires_at: datetime | None = None) -> MemoryFact:
        missing = [p for p in provenance if p not in self.captures]
        if not provenance or missing:
            raise ValueError("durable memories require existing provenance")
        f = MemoryFact(stable_id(statement, at, length=12), statement, kind, list(provenance), confidence, as_dt(at),
                       expires_at=as_dt(expires_at) if expires_at else None)
        f.history.append({"op": "create", "at": as_dt(at).isoformat()})
        self.facts[f.id] = f
        return f

    def revise(self, fact_id: str, new_statement: str, *, at: datetime, provenance: list[str], reason: str) -> MemoryFact:
        old = self.facts[fact_id]
        new = self.promote(new_statement, old.kind, provenance or old.provenance, at=at, confidence=old.confidence)
        old.status, old.superseded_by = "superseded", new.id
        old.history.append({"op": "superseded", "by": new.id, "reason": reason, "at": as_dt(at).isoformat()})
        return new

    def expire(self, now: datetime) -> list[str]:
        out = []
        for f in self.facts.values():
            if f.status == "active" and f.expires_at and as_dt(now) >= f.expires_at:
                f.status = "expired"
                out.append(f.id)
        return out

    def provenance(self, fact_id: str) -> list[dict[str, Any]]:
        return [plain(self.captures[p]) for p in self.facts[fact_id].provenance if p in self.captures]

    # ------------------------------------------------------------------ resurfacing
    def resurface(self, *, query_text: str = "", entities: Iterable[str] = (), latlon: tuple[float, float] | None = None,
                  limit: int = 3) -> list[dict[str, Any]]:
        """Contextual Resurfacing: relevance to the current problem/person/place."""
        qt = set(tokens(query_text))
        ents = set(entities)
        scored = []
        for c in self.captures.values():
            score = 0.6 * jaccard(qt, tokens(c.raw)) if qt else 0.0
            score += 0.3 * len(ents & set(c.entities))
            if latlon and c.context.get("latlon") and haversine_m(*latlon, *c.context["latlon"]) <= 200:
                score += 0.4
            if score > 0.15:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        out = []
        for s, c in scored[:limit]:
            c.retrievals += 1
            out.append({"id": c.id, "score": round(s, 3), "raw": c.raw, "why_saved": c.why,
                        "saved_at": c.at.isoformat()})
        return out

    def activation_queue(self, *, available_minutes: float) -> list[dict[str, Any]]:
        """Knowledge Activation Queue: saved-but-unprocessed items that fit the window."""
        pending = [c for c in self.captures.values() if c.status in ("saved", "processed")]
        est = lambda c: 2 if c.kind in ("thought", "voice") else 5 if c.kind in ("url", "selection") else 3  # noqa: E731
        pending.sort(key=lambda c: (-len(c.entities), c.at))
        out, used = [], 0.0
        for c in pending:
            if used + est(c) <= available_minutes:
                out.append({"id": c.id, "minutes": est(c), "prompt": application_prompt(c)})
                used += est(c)
        return out

    def mark(self, capture_id: str, status: str, *, decision_changed: bool = False) -> None:
        c = self.captures[capture_id]
        order = ("saved", "processed", "understood", "applied")
        if status not in order:
            raise ValueError(status)
        c.status = status
        if decision_changed:
            c.decisions_changed += 1

    def utility_report(self) -> dict[str, Any]:
        """Memory Utility Tracking: which kinds actually get used (provenance kept)."""
        by_kind: dict[str, dict[str, int]] = {}
        for c in self.captures.values():
            k = by_kind.setdefault(c.kind, {"count": 0, "retrieved": 0, "decisions": 0, "applied": 0})
            k["count"] += 1
            k["retrieved"] += 1 if c.retrievals else 0
            k["decisions"] += c.decisions_changed
            k["applied"] += 1 if c.status == "applied" else 0
        return by_kind

    # ------------------------------------------------------------------ unified search
    def ask(self, question: str, corpora: dict[str, list[dict[str, Any]]], *, now: datetime, limit: int = 5) -> dict[str, Any]:
        """Unified 'ask everything I know' with source + freshness disclosure.
        ``corpora``: name -> items ``{"id", "text", "at"}`` (email, documents, notes, world)."""
        qt = set(tokens(question))
        hits = []
        all_items = dict(corpora)
        all_items.setdefault("captures", [{"id": c.id, "text": c.raw, "at": c.at} for c in self.captures.values()])
        for source, items in all_items.items():
            for it in items:
                s = jaccard(qt, tokens(it["text"]))
                if s > 0:
                    age = as_dt(now) - as_dt(it["at"])
                    hits.append({"source": source, "id": it["id"], "score": round(s, 3), "text": it["text"],
                                 "as_of": as_dt(it["at"]).isoformat(), "age_days": round(age.total_seconds() / 86400, 1)})
        hits.sort(key=lambda h: -h["score"])
        top = hits[:limit]
        disclosure = [f"{h['source']}:{h['id']} ({h['age_days']} days old)" for h in top]
        return {"answers": top, "disclosure": disclosure,
                "note": "fused results are listed per source, not merged into one unsourced fact",
                "found": bool(top)}


def _contradicts(a: str, b: str) -> bool:
    neg = {"not", "never", "no", "don't", "doesn't", "isn't", "won't"}
    aux = {"does", "do", "did", "will", "would"}

    def norm(text: str) -> set[str]:
        return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in tokens(text) if w not in aux}

    ta, tb = norm(a), norm(b)
    return jaccard(ta - neg, tb - neg) >= 0.6 and bool((ta & neg) ^ (tb & neg))


def application_prompt(c: Capture) -> str:
    """Application Test for Knowledge."""
    target = c.entities[0] if c.entities else "something you currently do"
    return f"Where could '{c.raw[:60]}' change {target}?"


def compress(text: str, levels: tuple[int, ...] = (60, 25, 10)) -> dict[str, Any]:
    """Forgetting-Aware Compression: progressively shorter extractive representations
    (word budgets) with the full source retained."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    freq = Counter(tokens(text))
    ranked = sorted(range(len(sentences)), key=lambda i: -sum(freq[w] for w in tokens(sentences[i])) / (1 + len(tokens(sentences[i])) ** 0.5))
    out: dict[str, Any] = {"full": text}
    for budget in levels:
        chosen, words = [], 0
        for i in ranked:
            n = len(sentences[i].split())
            if words + n <= budget or not chosen:
                chosen.append(i)
                words += n
        summary = " ".join(sentences[i] for i in sorted(chosen))
        words_list = summary.split()
        out[f"w{budget}"] = " ".join(words_list[:budget]) + ("…" if len(words_list) > budget else "")
    return out


class SpacedResurfacer:
    """Spaced Resurfacing for important non-tasks (expanding intervals, SM-2-lite)."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def add(self, item_id: str, now: datetime) -> None:
        self.items[item_id] = {"interval_days": 1.0, "ease": 2.5, "due": as_dt(now) + timedelta(days=1), "reviews": 0}

    def review(self, item_id: str, recalled: bool, now: datetime) -> datetime:
        it = self.items[item_id]
        if recalled:
            it["interval_days"] *= it["ease"]
            it["ease"] = min(3.0, it["ease"] + 0.1)
        else:
            it["interval_days"] = 1.0
            it["ease"] = max(1.3, it["ease"] - 0.2)
        it["reviews"] += 1
        it["due"] = as_dt(now) + timedelta(days=it["interval_days"])
        return it["due"]

    def due(self, now: datetime, context_entities: Iterable[str] = (), tags: dict[str, set[str]] | None = None) -> list[str]:
        """Due items, preferring those relevant to the current real context."""
        ctx = set(context_entities)
        due = [i for i, it in self.items.items() if as_dt(now) >= it["due"]]
        return sorted(due, key=lambda i: -len(ctx & (tags or {}).get(i, set())))


# =========================================================================== friction / gaps


class FrictionLog:
    """'Why isn't this automatic?' log + Personal Friction Miner + Capability Gap
    Detection + Feature-Idea Harvester review queue."""

    def __init__(self) -> None:
        self.moments: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.commands: list[tuple[datetime, str]] = []
        self.review_queue: list[dict[str, Any]] = []

    def why_not_automatic(self, note: str, *, at: datetime, state: dict[str, Any] | None = None) -> None:
        self.moments.append({"note": note, "at": as_dt(at).isoformat(), "state": state or {}})

    def record_command(self, text: str, at: datetime) -> None:
        self.commands.append((as_dt(at), text.strip().lower()))

    def record_failure(self, request: str, missing: str, at: datetime) -> None:
        """``missing`` names the absent sensor/API/permission/function/UI primitive."""
        self.failures.append({"request": request, "missing": missing, "at": as_dt(at).isoformat()})

    def cluster_moments(self, threshold: float = 0.3) -> list[dict[str, Any]]:
        clusters: list[tuple[set[str], list[str]]] = []
        for m in self.moments:
            t = set(tokens(m["note"]))
            for sig, notes in clusters:
                if jaccard(t, sig) >= threshold:
                    notes.append(m["note"])
                    sig |= t
                    break
            else:
                clusters.append((t, [m["note"]]))
        return [{"theme": " ".join(sorted(sig)[:6]), "count": len(n), "examples": n[:3]}
                for sig, n in sorted(clusters, key=lambda x: -len(x[1]))]

    def repeated_sequences(self, n: int = 3, min_count: int = 3) -> list[dict[str, Any]]:
        """Repeated command sequences → candidate macros (Routine Learning input)."""
        seq = [c for _, c in sorted(self.commands)]
        grams = Counter(tuple(seq[i:i + n]) for i in range(len(seq) - n + 1))
        return [{"sequence": list(g), "count": c, "proposal": "make this a one-tap macro?"}
                for g, c in grams.most_common() if c >= min_count]

    def capability_gaps(self, min_count: int = 2) -> list[dict[str, Any]]:
        counts = Counter(f["missing"] for f in self.failures)
        return [{"missing": m, "failed_requests": c,
                 "examples": [f["request"] for f in self.failures if f["missing"] == m][:3],
                 "proposal": f"add {m}"} for m, c in counts.most_common() if c >= min_count]

    def harvest(self, candidates: list[dict[str, Any]], existing_titles: Iterable[str]) -> list[dict[str, Any]]:
        """Feature-Idea Harvester: dedupe evidence-backed ideas into a review queue
        (human review before anything reaches future.md)."""
        known = [set(tokens(t)) for t in existing_titles] + [set(tokens(r["title"])) for r in self.review_queue]
        added = []
        for c in candidates:
            if not c.get("evidence"):
                continue
            t = set(tokens(c["title"]))
            if any(jaccard(t, k) >= 0.6 for k in known):
                continue
            item = {"title": c["title"], "evidence": c["evidence"], "source": c.get("source", ""), "status": "awaiting_review"}
            self.review_queue.append(item)
            known.append(t)
            added.append(item)
        return added


# =========================================================================== spatial memory


@dataclass
class SpatialBookmark:
    id: str
    label: str
    latlon: tuple[float, float]
    at: datetime
    heading_deg: float | None = None
    objects: list[str] = field(default_factory=list)
    snapshot_ref: str = ""
    note: str = ""


class SpatialMemory:
    """Spatial Bookmarks, Physical Ctrl-F (last-observed evidence, never current
    location claims) and the Spatial Inbox."""

    def __init__(self) -> None:
        self.bookmarks: list[SpatialBookmark] = []
        self.sightings: list[dict[str, Any]] = []
        self.inbox: list[dict[str, Any]] = []

    def bookmark(self, label: str, latlon: tuple[float, float], at: datetime, **kw: Any) -> SpatialBookmark:
        b = SpatialBookmark(stable_id(label, latlon, at, length=10), label, latlon, as_dt(at), **kw)
        self.bookmarks.append(b)
        for obj in b.objects:
            self.saw(obj, latlon, at, place=label, confidence=0.9, evidence=b.snapshot_ref or b.id)
        return b

    def saw(self, obj: str, latlon: tuple[float, float], at: datetime, *, place: str = "", confidence: float = 0.7,
            evidence: str = "") -> None:
        self.sightings.append({"object": obj.lower(), "latlon": latlon, "at": as_dt(at), "place": place,
                               "confidence": confidence, "evidence": evidence})

    def where_is(self, obj: str, now: datetime) -> dict[str, Any]:
        matches = [s for s in self.sightings if obj.lower() in s["object"]]
        if not matches:
            return {"object": obj, "status": "never_observed"}
        last = max(matches, key=lambda s: s["at"])
        age_h = (as_dt(now) - last["at"]).total_seconds() / 3600
        return {"object": obj, "status": "last_observed", "place": last["place"], "latlon": last["latlon"],
                "observed_at": last["at"].isoformat(), "hours_ago": round(age_h, 1),
                "confidence_now": round(last["confidence"] * (0.5 ** (age_h / 72)), 3),
                "evidence": last["evidence"],
                "caveat": "This is where it was last seen, not a claim about where it is now."}

    def leave_note(self, recipient: str, latlon: tuple[float, float], text: str, *, radius_m: float = 50,
                   expires_at: datetime | None = None) -> None:
        self.inbox.append({"to": recipient, "latlon": latlon, "text": text, "radius_m": radius_m,
                           "expires_at": expires_at, "delivered": False})

    def arrive(self, person: str, latlon: tuple[float, float], now: datetime) -> list[str]:
        out = []
        for n in self.inbox:
            if n["delivered"] or n["to"] != person:
                continue
            if n["expires_at"] is not None and as_dt(now) >= as_dt(n["expires_at"]):
                continue
            if haversine_m(*latlon, *n["latlon"]) <= n["radius_m"]:
                n["delivered"] = True
                out.append(n["text"])
        return out
