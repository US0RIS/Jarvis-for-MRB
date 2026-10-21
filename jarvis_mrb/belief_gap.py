from __future__ import annotations

"""User belief-gap warnings for one narrow, evidence-backed domain.

Domain: explicit numeric/date terms in a document whose newer version changed
them (``document.version_changed`` events from ``world_document_versions``).

A warning needs all three pieces of evidence:

1. **Change evidence** — a deterministic version comparison found ``old`` →
   ``new`` in a changed passage of the same document family.
2. **Prior exposure** — a recorded Horus conversation turn *before* the change
   mentioned the document and the old value (the user said it, or Horus told
   them). Receiving a file is not counted as exposure to a value.
3. **Decision context** — the user is relying on the old value right now (the
   current utterance mentions the document and the old value) or an upcoming
   calendar event within 24 h references the document.

If a later turn mentions the document with the new value, or the user
dismissed the warning, there is no gap. Horus never states what the user
believes: it says what the *last recorded reference* used and that it does
not know whether the user has seen the update. Missing exposure evidence
produces nothing.

Stored state is only dismissals and issued warnings (document family, the two
values, timestamps, evidence ids), pruned after 90 days.
"""

import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jarvis_mrb.voice_router import VoiceTurn, get_focus, register, register_observer, set_focus

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "belief_gaps.sqlite3"
RETENTION = timedelta(days=90)
LOOKBACK = timedelta(days=90)
DECISION_WINDOW = timedelta(hours=24)
REPEAT_COOLDOWN = timedelta(hours=12)
_LOCK = threading.RLock()

_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_GENERIC = {"draft", "revised", "revision", "rev", "updated", "update", "final", "clean", "redline", "v", "project",
            "copy", "new", "latest", "working", "version", "the", "and", "of", "pdf", "docx", "doc", "xlsx"}
_VALUE = re.compile(
    r"(?<![\w.])([$€£])?\s?(\d[\d,]*(?:\.\d+)?)\s*(%|percent\b|per cent\b|bps\b|basis points\b|"
    r"thousand\b|million\b|billion\b|k\b|m\b|bn\b|days?\b|months?\b|years?\b|x\b)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValueChange:
    family: str
    title: str
    old: str
    new: str
    changed_at: datetime
    event_id: int
    passage: str


@dataclass(frozen=True)
class Turn:
    occurred_at: datetime
    user: str
    assistant: str
    event_id: int


@dataclass
class Gap:
    change: ValueChange
    exposure: Turn
    exposure_role: str  # "you said" | "I told you"
    decision: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Normalization

def _spoken_numbers(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        words = match.group(0).lower().split()
        total = 0
        for w in words:
            value = _WORD_NUMBERS.get(w.strip("-"), None)
            if value is None:
                return match.group(0)
            total = total * 100 if value == 100 else total + value
        return str(total)
    names = "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True))
    return re.sub(rf"\b(?:{names})(?:[ -](?:{names}))*\b", repl, text, flags=re.IGNORECASE)


def value_keys(text: str) -> set[str]:
    """Canonical numeric terms: '10 percent', 'ten percent', '10%' → '10%'."""
    keys: set[str] = set()
    for match in _VALUE.finditer(_spoken_numbers(str(text or ""))):
        currency, number, unit = match.group(1) or "", match.group(2).replace(",", ""), (match.group(3) or "").lower()
        try:
            numeric = float(number)
        except ValueError:
            continue
        unit = {"percent": "%", "per cent": "%", "basis points": "bps", "k": "thousand", "m": "million",
                "bn": "billion", "day": "days", "month": "months", "year": "years"}.get(unit, unit)
        shown = f"{numeric:g}"
        keys.add(f"{currency}{shown}{unit}")
    return keys


def _key(value: str) -> str:
    keys = value_keys(value)
    return sorted(keys)[0] if keys else " ".join(value.lower().split())


def doc_tokens(family: str, title: str = "") -> list[str]:
    raw = re.sub(r"\.[a-z0-9]{2,5}$", "", (title or family).lower())
    words = [w for w in re.split(r"[^a-z0-9]+", raw) if w and w not in _GENERIC and not re.fullmatch(r"v?\d+", w)]
    return words[:4]


def mentions_document(text: str, tokens: Iterable[str]) -> bool:
    words = set(re.split(r"[^a-z0-9]+", str(text or "").lower()))
    toks = list(tokens)
    # Every distinctive token must be present. Shared generic words ("purchase",
    # "agreement") must never tie one document's mention to another document.
    return bool(toks) and all(t in words or t.rstrip("s") in words or t + "s" in words for t in toks)


def _parse(raw: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Evidence loaders (world model)

def _world() -> sqlite3.Connection:
    from jarvis_mrb.world_model import DB_PATH as WORLD_DB
    conn = sqlite3.connect(WORLD_DB, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _pairs(old_numbers: list[str], new_numbers: list[str]) -> list[tuple[str, str]]:
    old_keys = [(_key(v), v) for v in old_numbers]
    new_keys = [(_key(v), v) for v in new_numbers]
    if len(old_keys) == len(new_keys):
        return [(o[1], n[1]) for o, n in zip(old_keys, new_keys) if o[0] != n[0]]
    removed = [o for o in old_keys if o[0] not in {n[0] for n in new_keys}]
    added = [n for n in new_keys if n[0] not in {o[0] for o in old_keys}]
    return [(removed[0][1], added[0][1])] if len(removed) == 1 and len(added) == 1 else []


def load_changes(now: datetime | None = None) -> list[ValueChange]:
    since = ((now or datetime.now(timezone.utc)) - LOOKBACK).isoformat()
    try:
        with _world() as conn:
            rows = conn.execute(
                "SELECT id, occurred_at, payload_json FROM events WHERE event_type='document.version_changed' "
                "AND occurred_at>=? ORDER BY id DESC LIMIT 200", (since,)
            ).fetchall()
    except sqlite3.Error:
        return []
    return changes_from_events([dict(r) for r in rows])


def changes_from_events(rows: list[dict[str, Any]]) -> list[ValueChange]:
    out: list[ValueChange] = []
    for row in rows:
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except (TypeError, ValueError):
            continue
        changed_at = _parse(row.get("occurred_at"))
        if changed_at is None:
            continue
        title = str((payload.get("newer") or {}).get("title") or payload.get("family") or "")
        for passage in payload.get("changes") or []:
            if not passage.get("numeric_change"):
                continue
            for old, new in _pairs(list(passage.get("old_numbers") or []), list(passage.get("new_numbers") or [])):
                out.append(ValueChange(str(payload.get("family") or title), title, old, new, changed_at,
                                       int(row.get("id") or 0), str(passage.get("new") or "")[:300]))
    return out


def load_turns(now: datetime | None = None) -> list[Turn]:
    since = ((now or datetime.now(timezone.utc)) - LOOKBACK).isoformat()
    try:
        with _world() as conn:
            rows = conn.execute(
                "SELECT id, occurred_at, payload_json FROM events WHERE event_type='conversation.turn' "
                "AND occurred_at>=? ORDER BY id DESC LIMIT 3000", (since,)
            ).fetchall()
    except sqlite3.Error:
        return []
    turns = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
        when = _parse(row["occurred_at"])
        if when:
            turns.append(Turn(when, str(payload.get("user") or ""), str(payload.get("assistant") or ""), int(row["id"])))
    return turns


# --------------------------------------------------------------------------
# Local ledger: dismissals and issued warnings

def _connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS dismissals(
               gap_key TEXT PRIMARY KEY, dismissed_at TEXT NOT NULL, reason TEXT NOT NULL);
           CREATE TABLE IF NOT EXISTS warnings(
               id INTEGER PRIMARY KEY AUTOINCREMENT, gap_key TEXT NOT NULL, issued_at TEXT NOT NULL,
               trigger TEXT NOT NULL, evidence_json TEXT NOT NULL);"""
    )
    cutoff = (datetime.now(timezone.utc) - RETENTION).isoformat()
    conn.execute("DELETE FROM dismissals WHERE dismissed_at<?", (cutoff,))
    conn.execute("DELETE FROM warnings WHERE issued_at<?", (cutoff,))
    conn.commit()
    return conn


def gap_key(change: ValueChange) -> str:
    return f"{change.family.lower()}|{_key(change.old)}|{_key(change.new)}"


def dismiss(change: ValueChange, reason: str = "user_dismissed") -> None:
    with _LOCK, _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO dismissals(gap_key,dismissed_at,reason) VALUES(?,?,?)",
                     (gap_key(change), datetime.now(timezone.utc).isoformat(), reason[:40]))
        conn.commit()


def _dismissed(change: ValueChange) -> bool:
    with _LOCK, _connect() as conn:
        return conn.execute("SELECT 1 FROM dismissals WHERE gap_key=?", (gap_key(change),)).fetchone() is not None


def _recently_warned(change: ValueChange, now: datetime, window: timedelta = REPEAT_COOLDOWN) -> bool:
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT issued_at FROM warnings WHERE gap_key=? ORDER BY id DESC LIMIT 1",
                           (gap_key(change),)).fetchone()
    last = _parse(row["issued_at"]) if row else None
    return bool(last and now - last < window)


def _record_warning(gap: Gap, trigger: str, now: datetime) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("INSERT INTO warnings(gap_key,issued_at,trigger,evidence_json) VALUES(?,?,?,?)",
                     (gap_key(gap.change), now.isoformat(), trigger, json.dumps(gap.evidence, default=str)))
        conn.commit()


def clear_all() -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM dismissals")
        conn.execute("DELETE FROM warnings")
        conn.commit()


# --------------------------------------------------------------------------
# Assessment

def assess(change: ValueChange, turns: list[Turn]) -> Gap | None:
    tokens = doc_tokens(change.family, change.title)
    old_key, new_key = _key(change.old), _key(change.new)
    prior: tuple[Turn, str] | None = None
    for turn in sorted(turns, key=lambda t: t.occurred_at):
        if turn.occurred_at >= change.changed_at:
            for text in (turn.user, turn.assistant):
                if mentions_document(text, tokens) and new_key in value_keys(text):
                    return None  # recorded exposure to the new value after the change
            continue
        for text, role in ((turn.user, "you said"), (turn.assistant, "I told you")):
            if mentions_document(text, tokens) and old_key in value_keys(text):
                prior = (turn, role)
    if prior is None or _dismissed(change):
        return None
    turn, role = prior
    return Gap(change, turn, role, evidence={
        "change_event_id": change.event_id, "changed_at": change.changed_at.isoformat(),
        "exposure_event_id": turn.event_id, "exposed_at": turn.occurred_at.isoformat(),
        "exposure_role": role, "old": change.old, "new": change.new, "document": change.title,
        "passage": change.passage,
    })


def _when(moment: datetime, now: datetime) -> str:
    days = (now.astimezone().date() - moment.astimezone().date()).days
    if days <= 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return "on " + moment.astimezone().strftime("%A")
    return "on " + moment.astimezone().strftime("%B ") + str(moment.astimezone().day)


def _doc_name(change: ValueChange) -> str:
    words = doc_tokens(change.family, change.title)
    return "the " + " ".join(words) if words else "that document"


def warning_text(gap: Gap, now: datetime | None = None) -> str:
    instant = now or datetime.now(timezone.utc)
    when = _when(gap.exposure.occurred_at, instant)
    lead = "One important thing: " if gap.decision else ""
    return (f"{lead}{_doc_name(gap.change)} now says {gap.change.new}. "
            f"The last recorded reference, when {gap.exposure_role} {when}, used {gap.change.old}. "
            "I don't know whether you've seen the update.")


def explain(gap: Gap) -> str:
    return (f"I warned you because a newer version of {gap.change.title or _doc_name(gap.change)} changed "
            f"{gap.change.old} to {gap.change.new}, our conversation {_when(gap.exposure.occurred_at, datetime.now(timezone.utc))} "
            f"used {gap.change.old}, I have no record of you discussing the new figure since, and "
            f"{gap.decision or 'you asked'}. Say 'dismiss that' if you already knew.")


def find_gaps(*, changes: list[ValueChange] | None = None, turns: list[Turn] | None = None,
              now: datetime | None = None) -> list[Gap]:
    instant = now or datetime.now(timezone.utc)
    changes = load_changes(instant) if changes is None else changes
    if not changes:
        return []
    turns = load_turns(instant) if turns is None else turns
    gaps = []
    for change in changes:
        gap = assess(change, turns)
        if gap:
            gaps.append(gap)
    return gaps


def relying_now(text: str, gaps: list[Gap]) -> Gap | None:
    keys = value_keys(text)
    for gap in gaps:
        if _key(gap.change.old) in keys and mentions_document(text, doc_tokens(gap.change.family, gap.change.title)):
            gap.decision = "you were about to rely on the old figure"
            return gap
    return None


def upcoming_decision_gaps(events: list[dict[str, Any]], *, now: datetime | None = None,
                           changes: list[ValueChange] | None = None,
                           turns: list[Turn] | None = None) -> list[tuple[Gap, dict[str, Any]]]:
    """Gaps whose document is referenced by a calendar event in the next 24 h.

    ``events`` are dicts with ``title``/``summary``, ``description`` and
    ``start``. Used by the proactive briefing path; returns nothing without
    exposure evidence.
    """
    instant = now or datetime.now(timezone.utc)
    out = []
    gaps = find_gaps(changes=changes, turns=turns, now=instant)
    for event in events:
        start = _parse(event.get("start"))
        if start is None or not instant <= start <= instant + DECISION_WINDOW:
            continue
        text = " ".join(str(event.get(k) or "") for k in ("title", "summary", "description"))
        for gap in gaps:
            if mentions_document(text, doc_tokens(gap.change.family, gap.change.title)) and not _recently_warned(gap.change, instant):
                gap.decision = f"'{str(event.get('title') or event.get('summary') or 'an event')[:60]}' is coming up"
                out.append((gap, event))
    return out


def deliver_upcoming(gap: Gap, event: dict[str, Any], *, now: datetime | None = None) -> str:
    instant = now or datetime.now(timezone.utc)
    _record_warning(gap, "upcoming_event", instant)
    return warning_text(gap, instant)


# --------------------------------------------------------------------------
# Voice integration

def observe(text: str, turn: VoiceTurn) -> str | None:
    """Preface for the current turn when the user is relying on an old figure."""
    if not value_keys(text):
        return None
    now = datetime.now(timezone.utc)
    gap = relying_now(text, find_gaps(now=now))
    # The user restating the old figure moments after a warning is not a new
    # reliance signal; don't repeat the same warning within ten minutes.
    if gap is None or _recently_warned(gap.change, now, timedelta(minutes=10)):
        return None
    _record_warning(gap, "current_utterance", now)
    set_focus("belief_gap.last", gap, session_id=turn.session_id)
    return warning_text(gap, now)


_DISMISS = re.compile(r"^(?:dismiss that|dismiss the warning|i know|i knew|i've seen it|i have seen it|i saw (?:it|the update)|already knew|got it,? dismiss)$")
_WHY = re.compile(r"^(?:why did you warn me(?: about that)?|why the warning|why are you warning me)$")


def handle(text: str, turn: VoiceTurn) -> str | None:
    gap = get_focus("belief_gap.last", session_id=turn.session_id)
    if gap is None:
        return None
    n = " ".join(text.lower().replace("’", "'").split()).strip(" .!?")
    if _DISMISS.match(n):
        dismiss(gap.change)
        set_focus("belief_gap.last", None, session_id=turn.session_id)
        return "Okay. I won't warn you about that change again."
    if _WHY.match(n):
        return explain(gap)
    return None


register("belief_gap", handle)
register_observer("belief_gap", observe)
