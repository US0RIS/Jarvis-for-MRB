from __future__ import annotations

"""Camera-free, voice-first memory of where the user says physical things are.

"Remember I put my passport in the top drawer of my desk" stores a
*user-reported* placement assertion: the object identity (with aliases), the
place phrase, when it was said, through which channel, and the exact words.
Nothing here is a visual observation. Later "I moved my passport into my
suitcase" supersedes the active placement while keeping the earlier one as
history; "no, the bottom drawer" right after a capture marks the previous
assertion as *corrected* (it was never true) rather than moved.

Lookup ("where are my jumper cables?", "what else did I put there?") answers
from the newest active assertion, says how old it is, and says that it is the
user's own report. Optional camera sightings from ``spatial_memory`` are
mentioned separately and labeled as such; they are never merged into a user
claim. Missing data is an honest unknown.

Storage is one local SQLite file. Deletion is a hard delete of the object's
assertions and aliases. Each placement is also mirrored best-effort into the
world model as a ``user_report`` event so the Reality Graph/Chronos history
sees it with the correct provenance.
"""

import difflib
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jarvis_mrb.voice_router import VoiceTurn, get_focus, register, set_focus

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "object_memory.sqlite3"
SCHEMA_VERSION = 1
MIRROR_WORLD = True
VISUAL_SOURCE = True
STALE_AFTER = timedelta(days=14)
CORRECTION_WINDOW = timedelta(minutes=3)
MAX_UTTERANCE = 400

_LOCK = threading.RLock()

PREPOSITIONS = (
    "in front of", "on top of", "inside of", "next to", "underneath", "inside",
    "into", "onto", "under", "beneath", "behind", "beside", "near", "by",
    "in", "on", "at",
)
_PREP_RE = "|".join(re.escape(p) for p in PREPOSITIONS)
_PLACE_VERBS = (
    "put", "left", "placed", "stored", "stashed", "hid", "hidden", "keep", "kept",
    "dropped", "set", "packed", "moved", "returned", "tucked", "hung", "parked",
    "stuck", "threw", "tossed",
)
_VERB_RE = "|".join(_PLACE_VERBS)
_STOP = {"the", "a", "an", "my", "our", "your", "of", "his", "her", "their", "its"}
_POSSESSIVE = re.compile(r"^(?:my|the|our|a|an|your|his|her|their)\s+")
# Things that sound like "X is at Y" but are not physical objects in places.
_NON_PHYSICAL = {
    "meeting", "flight", "appointment", "call", "birthday", "deadline", "password",
    "number", "name", "train", "bus", "interview", "dinner", "lunch", "party",
    "event", "reservation", "class", "shift", "game", "show", "concert", "doctor",
    "dentist", "pin", "code", "favorite", "favourite", "plan", "budget",
}
_TIME_PLACE = re.compile(
    r"^(?:\d|noon|midnight|tonight|today|tomorrow|yesterday|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|the morning|the afternoon|the evening|"
    r"(?:a|an|one|two|three|four|five|six|ten|\d+) (?:minutes?|hours?|days?|weeks?))"
)
_INVARIANT_PLURALS = {
    "glasses", "sunglasses", "scissors", "pants", "jeans", "headphones", "airpods",
    "earbuds", "clothes", "pliers", "tongs", "shorts", "goggles", "binoculars",
    "tweezers",
}
_SYNONYMS = (
    ("jumper cable", "booster cable", "jump lead", "jumper lead", "jump cable"),
    ("tire inflator", "tyre inflator", "air compressor", "tire pump", "tyre pump"),
    ("flashlight", "torch"),
    ("tv remote", "remote control", "remote"),
    ("passport", "passports"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _db_path() -> Path:
    return Path(DB_PATH)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS objects(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS aliases(
            alias_key TEXT PRIMARY KEY,
            object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assertions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            relation TEXT NOT NULL DEFAULT '',
            place TEXT NOT NULL DEFAULT '',
            place_key TEXT NOT NULL DEFAULT '',
            asserted_at TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            channel TEXT NOT NULL,
            session_ref TEXT NOT NULL DEFAULT '',
            utterance TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            ended_at TEXT,
            ended_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_assert_object ON assertions(object_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_assert_place ON assertions(place_key, status);
        """
    )
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


# --------------------------------------------------------------------------
# Normalization

def _clean(text: str) -> str:
    return " ".join(str(text or "").lower().replace("’", "'").split()).strip(" .,!?;:")


def _singular(word: str) -> str:
    if word in _INVARIANT_PLURALS or len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "sses", "zes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def object_key(name: str) -> str:
    text = _clean(name)
    text = _POSSESSIVE.sub("", text)
    text = re.sub(r"[^a-z0-9' -]", "", text)
    words = [w for w in text.split() if w not in _STOP]
    if not words:
        return ""
    words[-1] = _singular(words[-1])
    return " ".join(words)[:120]


def _display_object(name: str) -> str:
    text = _POSSESSIVE.sub("", _clean(name))
    return text[:120]


def _place_key(place: str) -> str:
    words = [w for w in re.sub(r"[^a-z0-9' -]", "", _clean(place)).split() if w not in _STOP]
    return " ".join(_singular(w) for w in words)[:200]


def _speak_place(place: str) -> str:
    """Render the user's own place words from Horus's side of the conversation."""
    words = _clean(place).split()
    swap = {"my": "your", "our": "your", "i": "you", "me": "you", "mine": "yours"}
    return " ".join(swap.get(w, w) for w in words)


def _plural(display: str) -> bool:
    last = display.split()[-1] if display.split() else ""
    return last in _INVARIANT_PLURALS or (last.endswith("s") and not last.endswith(("ss", "us", "is")))


def _synonym_keys(key: str) -> set[str]:
    out = {key}
    for group in _SYNONYMS:
        keys = {object_key(g) for g in group}
        if key in keys:
            out |= keys
    return out


def _when(instant: datetime, now: datetime | None = None) -> str:
    current = now or _now()
    local = instant.astimezone()
    today = current.astimezone().date()
    delta_days = (today - local.date()).days
    if delta_days <= 0:
        minutes = int((current - instant).total_seconds() // 60)
        if minutes < 2:
            return "just now"
        if minutes < 60:
            return f"{minutes} minutes ago"
        return "earlier today"
    if delta_days == 1:
        return "yesterday"
    if delta_days < 7:
        return "on " + local.strftime("%A")
    if local.year == today.year:
        return "on " + local.strftime("%B ") + str(local.day)
    return "on " + local.strftime("%B ") + str(local.day) + local.strftime(", %Y")


# --------------------------------------------------------------------------
# Storage operations

def _resolve_or_create(conn: sqlite3.Connection, name: str) -> tuple[str, str]:
    key = object_key(name)
    if not key:
        raise ValueError("Object name is empty.")
    row = conn.execute("SELECT id,name FROM objects WHERE key=?", (key,)).fetchone()
    if row:
        return str(row["id"]), str(row["name"])
    alias = conn.execute(
        "SELECT o.id,o.name FROM aliases a JOIN objects o ON o.id=a.object_id WHERE a.alias_key=?", (key,)
    ).fetchone()
    if alias:
        return str(alias["id"]), str(alias["name"])
    for synonym in _synonym_keys(key) - {key}:
        hit = conn.execute("SELECT id,name FROM objects WHERE key=?", (synonym,)).fetchone()
        if hit:
            return str(hit["id"]), str(hit["name"])
    object_id = "obj_" + uuid.uuid4().hex[:16]
    conn.execute(
        "INSERT INTO objects(id,name,key,created_at) VALUES(?,?,?,?)",
        (object_id, _display_object(name), key, _iso(_now())),
    )
    return object_id, _display_object(name)


def _active(conn: sqlite3.Connection, object_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM assertions WHERE object_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (object_id,),
    ).fetchone()


def record_placement(
    name: str,
    place: str,
    *,
    relation: str = "in",
    channel: str = "text",
    session_id: str = "",
    utterance: str = "",
    correction: bool = False,
    kind: str = "placement",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append a user-reported placement (or removal) and end the prior active one.

    ``correction`` marks the prior active assertion as corrected (it was a
    mistake); otherwise it is superseded (it was true, then changed).
    """
    instant = now or _now()
    source_kind = "user_spoken" if channel in {"voice", "conversation"} else "user_typed"
    clean_place = " ".join(str(place or "").split())[:200]
    with _LOCK, _connect() as conn:
        object_id, display = _resolve_or_create(conn, name)
        previous = _active(conn, object_id)
        cursor = conn.execute(
            """INSERT INTO assertions(object_id,kind,relation,place,place_key,asserted_at,
               source_kind,channel,session_ref,utterance) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (object_id, kind, relation if kind == "placement" else "", clean_place,
             _place_key(clean_place), _iso(instant), source_kind, channel[:20],
             str(session_id)[:120], " ".join(str(utterance).split())[:MAX_UTTERANCE]),
        )
        new_id = int(cursor.lastrowid)
        if previous is not None:
            conn.execute(
                "UPDATE assertions SET status=?, ended_at=?, ended_by=? WHERE id=?",
                ("corrected" if correction else "superseded", _iso(instant), new_id, int(previous["id"])),
            )
        conn.commit()
    record = {
        "assertion_id": new_id, "object_id": object_id, "object": display, "kind": kind,
        "relation": relation, "place": clean_place, "asserted_at": _iso(instant),
        "source_kind": source_kind, "previous_assertion_id": int(previous["id"]) if previous else None,
        "previous_place": str(previous["place"]) if previous else None,
        "previous_relation": str(previous["relation"]) if previous else None,
        "previous_ended_as": ("corrected" if correction else "superseded") if previous else None,
    }
    _mirror_world(record)
    return record


def _mirror_world(record: dict[str, Any]) -> None:
    if not MIRROR_WORLD:
        return
    try:
        from jarvis_mrb.world_model import SELF_ID, assert_belief, ensure_entity, record_event

        object_entity = ensure_entity("object", record["object"], confidence=0.9)
        participants: list[tuple[str, str, float]] = [(SELF_ID, "reporter", 1.0), (object_entity, "subject", 0.9)]
        place_entity = None
        if record["kind"] == "placement" and record["place"]:
            place_entity = ensure_entity("place", record["place"], confidence=0.7)
            participants.append((place_entity, "reported_location", 0.7))
        event_id = record_event(
            "memory.user_reported_location",
            f"User reported {record['object']} "
            + (f"{record['relation']} {record['place']}" if place_entity else "no longer at its last place"),
            source_kind="user_report",
            source_ref=f"object_memory:{record['assertion_id']}",
            occurred_at=record["asserted_at"],
            payload={k: record[k] for k in ("object", "kind", "relation", "place", "source_kind")},
            evidence="User's own spoken/typed statement; not a visual or sensor observation.",
            confidence=0.9,
            participants=participants,
            event_key=f"object_memory:{record['assertion_id']}",
        )
        assert_belief(
            object_entity, "user_reported_place",
            object_id=place_entity, value=None if place_entity else "unknown",
            confidence=0.9, source_event_id=event_id,
            evidence="User report (object memory); supersedes the previous user report.",
        )
    except Exception:
        pass


def add_alias(name: str, alias: str) -> dict[str, Any]:
    alias_key = object_key(alias)
    if not alias_key:
        raise ValueError("Alias is empty.")
    with _LOCK, _connect() as conn:
        object_id, display = _resolve_or_create(conn, name)
        clash = conn.execute("SELECT id FROM objects WHERE key=? AND id<>?", (alias_key, object_id)).fetchone()
        if clash:
            raise ValueError("That name already belongs to a different remembered object.")
        conn.execute(
            "INSERT OR REPLACE INTO aliases(alias_key,object_id,created_at) VALUES(?,?,?)",
            (alias_key, object_id, _iso(_now())),
        )
        conn.commit()
    return {"object_id": object_id, "object": display, "alias": alias_key}


def _all_objects(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM objects").fetchall()


def resolve(name: str) -> list[dict[str, Any]]:
    """Return candidate objects for a spoken name, best first.

    Exact name/alias/synonym → one result. Otherwise token-subset matches
    ("keys" → "car keys", "house keys") and close fuzzy matches (speech
    recognition slips) are all returned so the caller can ask which one.
    """
    key = object_key(name)
    if not key:
        return []
    with _LOCK, _connect() as conn:
        exact_ids: list[str] = []
        for candidate in _synonym_keys(key):
            row = conn.execute("SELECT id FROM objects WHERE key=?", (candidate,)).fetchone()
            if row:
                exact_ids.append(str(row["id"]))
            alias = conn.execute("SELECT object_id FROM aliases WHERE alias_key=?", (candidate,)).fetchone()
            if alias:
                exact_ids.append(str(alias["object_id"]))
        rows = _all_objects(conn)
        by_id = {str(r["id"]): r for r in rows}
        if exact_ids:
            ordered = list(dict.fromkeys(exact_ids))
            return [_object_view(conn, by_id[i]) for i in ordered if i in by_id]
        alias_rows = conn.execute("SELECT alias_key,object_id FROM aliases").fetchall()
        query_tokens = set(key.split())
        scored: dict[str, float] = {}
        names = [(str(r["key"]), str(r["id"])) for r in rows]
        names += [(str(a["alias_key"]), str(a["object_id"])) for a in alias_rows]
        for candidate_key, object_id in names:
            tokens = set(candidate_key.split())
            if query_tokens and query_tokens <= tokens:
                scored[object_id] = max(scored.get(object_id, 0), 0.9)
                continue
            ratio = difflib.SequenceMatcher(None, key, candidate_key).ratio()
            if ratio >= 0.84:
                scored[object_id] = max(scored.get(object_id, 0), ratio)
        ordered = sorted(scored, key=lambda i: -scored[i])
        return [_object_view(conn, by_id[i]) for i in ordered if i in by_id][:5]


def _object_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    history = conn.execute(
        "SELECT * FROM assertions WHERE object_id=? ORDER BY id DESC LIMIT 20", (row["id"],)
    ).fetchall()
    return {
        "object_id": str(row["id"]),
        "object": str(row["name"]),
        "aliases": [str(a["alias_key"]) for a in conn.execute(
            "SELECT alias_key FROM aliases WHERE object_id=?", (row["id"],))],
        "current": _assertion_view(history[0]) if history and history[0]["status"] == "active" else None,
        "history": [_assertion_view(h) for h in history],
    }


def _assertion_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "assertion_id": int(row["id"]), "kind": str(row["kind"]), "relation": str(row["relation"]),
        "place": str(row["place"]), "asserted_at": str(row["asserted_at"]),
        "source_kind": str(row["source_kind"]), "channel": str(row["channel"]),
        "status": str(row["status"]), "ended_at": row["ended_at"], "utterance": str(row["utterance"]),
    }


def items_at(place: str, *, exclude: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Objects whose newest active user report places them at ``place``."""
    target = set(_place_key(place).split())
    if not target:
        return []
    skip = set(exclude)
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            """SELECT a.*, o.name AS object_name FROM assertions a JOIN objects o ON o.id=a.object_id
               WHERE a.status='active' AND a.kind='placement' ORDER BY a.id DESC"""
        ).fetchall()
    out = []
    for row in rows:
        if str(row["object_id"]) in skip:
            continue
        if target <= set(str(row["place_key"]).split()):
            item = _assertion_view(row)
            item["object"] = str(row["object_name"])
            item["object_id"] = str(row["object_id"])
            out.append(item)
    return out


def forget(object_id: str) -> bool:
    with _LOCK, _connect() as conn:
        deleted = conn.execute("DELETE FROM objects WHERE id=?", (object_id,)).rowcount
        conn.commit()
    return bool(deleted)


def forget_all() -> int:
    with _LOCK, _connect() as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0])
        conn.execute("DELETE FROM objects")
        conn.commit()
    return count


def list_objects(limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            """SELECT o.* FROM objects o LEFT JOIN assertions a ON a.object_id=o.id
               GROUP BY o.id ORDER BY MAX(a.id) DESC LIMIT ?""", (max(1, min(int(limit), 500)),)
        ).fetchall()
        return [_object_view(conn, r) for r in rows]


def status() -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        objects = int(conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0])
        assertions = int(conn.execute("SELECT COUNT(*) FROM assertions").fetchone()[0])
    return {
        "objects": objects, "assertions": assertions, "database": str(_db_path()),
        "schema_version": SCHEMA_VERSION, "evidence": "user_reported",
        "camera_required": False,
    }


def _visual_sighting(name: str) -> dict[str, Any] | None:
    if not VISUAL_SOURCE:
        return None
    try:
        from jarvis_mrb.spatial_memory import find_object
        hits = find_object(name, limit=1)
    except Exception:
        return None
    return hits[0] if hits else None


# --------------------------------------------------------------------------
# Spoken interface

_WAKE = re.compile(r"^(?:(?:hey|ok|okay)\s+)?(?:horus|jarvis)[,:!]?\s+")
_REMEMBER = re.compile(
    r"^(?:please\s+)?(?:remember|note|make a note|keep in mind|just so you know|fyi|for the record)"
    r"(?:\s+that)?[,:]?\s+(.+)$"
)
_PLACED = re.compile(
    rf"^i(?:\s+just|\s+have|\s+had|'ve|'d|\s+also|\s+finally)?\s+({_VERB_RE})\s+(.+?)\s+({_PREP_RE})\s+(.+)$"
)
_MOVED_FROM = re.compile(rf"^i(?:\s+just|'ve|\s+have)?\s+moved\s+(.+?)\s+from\s+(.+?)\s+(?:to|into|onto)\s+(.+)$")
_IS_AT = re.compile(
    rf"^((?:my|the|our)\s+.+?)\s+(?:is|are|'s|'re)\s+(?:now\s+|currently\s+|still\s+|always\s+)?({_PREP_RE})\s+(.+)$"
)
_TOOK_OUT = re.compile(r"^i(?:\s+just|'ve|\s+have)?\s+(?:took|removed|taken|got|pulled)\s+(.+?)\s+out of\s+(.+)$")
_GONE = re.compile(r"^i(?:\s+just|'ve|\s+have)?\s+(lost|gave away|threw away|threw out|sold|no longer have)\s+(.+)$")
_ALIAS = re.compile(r"^(?:my\s+|the\s+)?(.+?)\s+(?:is|are)\s+also\s+called\s+(?:the\s+|my\s+)?(.+)$")
_WHERE = re.compile(
    r"^(?:do you know |can you tell me |remind me )?where(?:'s|'re|\s+is|\s+are|\s+did\s+i\s+(?:last\s+)?(?:put|leave|place|store|stash|hide|keep|pack|see)"
    r"|\s+have\s+i\s+(?:put|left|stored)|\s+would\s+i\s+have\s+(?:put|left)|\s+can\s+i\s+find|\s+should\s+i\s+look\s+for)\s+(.+?)"
    r"(?:\s+(?:is|are))?(?:\s+again)?(?:\s+now)?$"
)
_VEHICLE = r"(?:my |the |our )?(car|truck|van|bike|bicycle|motorcycle|scooter)"
_PARKED = re.compile(rf"^i(?:\s+just|'ve|\s+have)?\s+parked(?:\s+{_VEHICLE})?\s+({_PREP_RE})\s+(.+)$")
_WHERE_PARKED = re.compile(rf"^where\s+(?:did\s+i|have\s+i)\s+park(?:ed)?(?:\s+{_VEHICLE})?$|^where(?:'s|\s+is)\s+{_VEHICLE}\s+parked$")
_SEEN = re.compile(r"^have you seen\s+(.+?)$")
_IN_PLACE = re.compile(
    rf"^what(?:'s|\s+is|\s+did\s+i\s+(?:put|leave|store|pack)|\s+have\s+i\s+(?:put|stored|packed)|\s+do\s+i\s+have|\s+things?\s+(?:are|did\s+i\s+put))\s+({_PREP_RE})\s+(.+)$"
)
_ELSE_THERE = re.compile(
    r"^what\s+else(?:\s+(?:did\s+i\s+(?:put|leave|store|pack)|is|was|have\s+i\s+(?:put|stored)|do\s+i\s+have))?\s+(?:there|in\s+there|in\s+it|in\s+that|in\s+there\s+too|there\s+too)$"
)
_WHEN = re.compile(r"^when\s+(?:did\s+i\s+(?:put|leave|move|tell\s+you)|was\s+that|did\s+you\s+hear\s+that)(?:\s+(?:it|them|that))?(?:\s+there)?$")
_BEFORE = re.compile(r"^where\s+(?:was|were)\s+(?:it|they)\s+before|^where\s+did\s+(?:it|they)\s+used?\s+to\s+be")
_SOURCE = re.compile(r"^(?:how do you know(?: that)?|what'?s your source|what is your source|who told you(?: that)?|are you sure|did you see (?:it|them|that))$")
_FORGET = re.compile(
    r"^(?:forget|delete|erase|remove)\s+(?:where\s+i\s+(?:put|left)\s+|(?:the\s+)?memory\s+(?:of|about)\s+|about\s+|what\s+you\s+know\s+about\s+)(.+?)$"
)
_FORGET_ALL = re.compile(r"^(?:forget|delete|erase)\s+(?:all|every)\s+(?:of\s+)?(?:my\s+)?(?:object|item|thing)\s*(?:memories|memory|locations?)?$")
_LIST = re.compile(r"^(?:what|which)\s+(?:objects|things|items)\s+(?:do\s+you\s+remember|have\s+i\s+told\s+you\s+about)|^list\s+my\s+(?:object|item)\s+memor")
_CORRECTION = re.compile(r"^(?:no|nope|actually|correction|sorry|wait|i mean|i meant|oops)\b[,.:!]?\s*(.*)$")
_CORRECTION_LEAD = re.compile(
    r"^(?:no[,.]?\s+)?(?:i said\s+|i meant\s+|make that\s+|it's\s+|it is\s+|they're\s+|they are\s+|it was\s+|they were\s+|not\s+.+?\s+but\s+)?(?:now\s+)?"
)
_PRONOUNS = {"it", "them", "that", "those", "they", "these", "this"}


def _split_objects(phrase: str) -> list[str]:
    parts = re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+(?=(?:my|the|our|a|an)\s)", phrase)
    return [p.strip() for p in parts if p.strip()]


def _valid_place(place: str) -> bool:
    text = _clean(place)
    return bool(text) and not _TIME_PLACE.match(text) and len(text) <= 160


def _physical(name: str) -> bool:
    key = object_key(name)
    return bool(key) and not (set(key.split()) & _NON_PHYSICAL)


def _focus_objects(turn: VoiceTurn) -> list[str]:
    value = get_focus("object_memory.objects", session_id=turn.session_id)
    return list(value or [])


def _remember_focus(turn: VoiceTurn, *, objects: list[str] | None = None, place: str | None = None,
                    captured: bool = False, candidates: list[dict[str, Any]] | None = None) -> None:
    sid = turn.session_id
    if objects is not None:
        set_focus("object_memory.objects", objects, session_id=sid)
    if place is not None:
        set_focus("object_memory.place", place, session_id=sid)
    set_focus("object_memory.captured_at", _now() if captured else None, session_id=sid)
    set_focus("object_memory.candidates", candidates, session_id=sid)


def _object_names_for(ids: list[str]) -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        out = []
        for object_id in ids:
            row = conn.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
            if row:
                out.append(_object_view(conn, row))
        return out


def _capture(objects: list[str], place: str, relation: str, turn: VoiceTurn, utterance: str,
             *, correction: bool = False) -> str:
    focus = _focus_objects(turn)
    names: list[str] = []
    for raw in objects:
        if _clean(raw) in _PRONOUNS:
            names.extend(v["object"] for v in _object_names_for(focus))
        else:
            names.append(raw)
    if not names:
        return "Which item do you mean?"
    if not _valid_place(place):
        return "Where is it? Tell me the place, like 'in the hall closet'."
    records = [
        record_placement(n, place, relation=relation, channel=turn.channel, session_id=turn.session_id,
                         utterance=utterance, correction=correction)
        for n in names
    ]
    _remember_focus(turn, objects=[r["object_id"] for r in records], place=place, captured=True)
    spoken_place = f"{relation} {_speak_place(place)}"
    if correction:
        return f"Corrected: {_join([r['object'] for r in records])} {spoken_place}."
    moved = [r for r in records if r["previous_place"] and _place_key(r["previous_place"]) != _place_key(place)]
    if len(records) == 1 and moved:
        return f"Got it. Your {records[0]['object']}: {spoken_place}, not {_speak_place(moved[0]['previous_place'])} anymore."
    return "Got it."


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _describe(view: dict[str, Any], *, now: datetime | None = None) -> str:
    name = view["object"]
    verb = "were" if _plural(name) else "was"
    pron = "they" if _plural(name) else "it"
    current = view["current"]
    sighting = _visual_sighting(name)
    if current is None:
        message = f"I don't have a current record of where your {name} {('are' if _plural(name) else 'is')}."
        if view["history"]:
            last = view["history"][0]
            message = f"You told me {_when(_parse_iso(last['asserted_at']), now)} that your {name} {verb} no longer at {_speak_place(last['place']) or 'the last place'}, so I don't know where {pron} {('are' if _plural(name) else 'is')} now."
            placed = next((h for h in view["history"] if h["kind"] == "placement" and h["status"] != "corrected"), None)
            if last["kind"] == "removal" and placed:
                message = (f"You told me {_when(_parse_iso(last['asserted_at']), now)} you took your {name} out of "
                           f"{_speak_place(placed['place'])}. I don't know where {pron} {('are' if _plural(name) else 'is')} now.")
        return message + _sighting_note(sighting, None)
    instant = _parse_iso(current["asserted_at"])
    if current["kind"] == "removal":
        detail = _clean(current["place"])
        be = "are" if _plural(name) else "is"
        if detail.startswith("out of "):
            return (f"You told me {_when(instant, now)} you took your {name} {_speak_place(detail)}. "
                    f"I don't know where {pron} {be} now.") + _sighting_note(sighting, instant)
        how = {"lost": "lost", "sold": "sold", "gave away": "given away", "threw away": "thrown away",
               "threw out": "thrown out", "no longer have": "gone"}.get(detail, "gone")
        return (f"You told me {_when(instant, now)} that your {name} {verb} {how}, "
                f"so I don't have a current location.") + _sighting_note(sighting, instant)
    message = f"You last told me your {name} {verb} {current['relation']} {_speak_place(current['place'])}, {_when(instant, now)}."
    age = (now or _now()) - instant
    if age > STALE_AFTER:
        weeks = max(2, int(age.days // 7))
        message += f" That was about {weeks} weeks ago, so {pron} may have moved."
    return message + _sighting_note(sighting, instant)


def _sighting_note(sighting: dict[str, Any] | None, reported_at: datetime | None) -> str:
    if not sighting:
        return ""
    try:
        seen = _parse_iso(str(sighting["seen_at"]))
    except Exception:
        return ""
    if reported_at is not None and seen <= reported_at:
        return ""
    return (f" Separately, an optional camera sighting {_when(seen)} placed something matching it at "
            f"{sighting['location']}; that is a camera observation, not your report.")


def _lookup(name: str, turn: VoiceTurn, *, definitive: bool) -> str | None:
    candidates = resolve(name)
    if not candidates:
        if not definitive:
            return None
        display = _display_object(name)
        sighting = _visual_sighting(display)
        if sighting:
            return (f"You haven't told me where your {display} {'are' if _plural(display) else 'is'}."
                    + _sighting_note(sighting, None))
        return (f"I don't have any record of where your {display} {'are' if _plural(display) else 'is'}. "
                f"If you find {'them' if _plural(display) else 'it'}, tell me where and I'll remember.")
    if len(candidates) > 1:
        located = [c for c in candidates if c["current"]]
        pool = located or candidates
        if len(pool) > 1:
            _remember_focus(turn, objects=[c["object_id"] for c in pool], candidates=pool)
            parts = []
            for c in pool[:3]:
                cur = c["current"]
                if cur and cur["kind"] == "placement":
                    parts.append(f"your {c['object']}, {cur['relation']} {_speak_place(cur['place'])}")
                else:
                    parts.append(f"your {c['object']}, location unknown")
            return f"I have {len(pool)} matches: " + "; ".join(parts) + ". Which one?"
        candidates = pool
    view = candidates[0]
    place = view["current"]["place"] if view["current"] and view["current"]["kind"] == "placement" else None
    _remember_focus(turn, objects=[view["object_id"]], place=place)
    return _describe(view)


def _list_place(place: str, turn: VoiceTurn, *, exclude: list[str], also: bool) -> str:
    items = items_at(place, exclude=exclude)
    _remember_focus(turn, place=place, objects=[i["object_id"] for i in items] or exclude)
    spoken = _speak_place(place)
    if not items:
        if also:
            return "Nothing else that you've told me about there."
        return f"You haven't told me about anything in {spoken}."
    names = [i["object"] for i in items[:6]]
    lead = "You also mentioned" if also else "You've told me about"
    extra = f", plus {len(items) - 6} more" if len(items) > 6 else ""
    return f"{lead} {_join(['your ' + n for n in names])}{extra}."


def handle(text: str, turn: VoiceTurn) -> str | None:
    raw = _clean(text)
    raw = _WAKE.sub("", raw)
    if not raw:
        return None
    n = re.sub(r"^(?:please|okay|ok|so|hey)[,]?\s+", "", raw)

    # Pending "forget everything" confirmation.
    if get_focus("object_memory.forget_all", session_id=turn.session_id):
        if n in {"yes", "yes forget them", "yes forget them all", "yes delete them", "confirm forget all", "yes, forget them all"}:
            set_focus("object_memory.forget_all", None, session_id=turn.session_id)
            return f"Done. I forgot {forget_all()} remembered items."
        if n in {"no", "never mind", "cancel", "keep them"}:
            set_focus("object_memory.forget_all", None, session_id=turn.session_id)
            return "Okay, I kept them."

    if _FORGET_ALL.match(n):
        set_focus("object_memory.forget_all", True, session_id=turn.session_id, ttl_seconds=120)
        return "That deletes every item location you've told me. Say 'yes, forget them all' to confirm."

    m = _FORGET.match(n)
    if m:
        target = m.group(1)
        ids = _focus_objects(turn) if _clean(target) in _PRONOUNS else [c["object_id"] for c in resolve(target)]
        if not ids:
            return None if _clean(target) in _PRONOUNS else f"I don't have anything remembered about {_display_object(target)}."
        if len(ids) > 1 and _clean(target) not in _PRONOUNS:
            views = _object_names_for(ids)
            return "Which one should I forget: " + _join([v["object"] for v in views]) + "?"
        names = [v["object"] for v in _object_names_for(ids)]
        for object_id in ids:
            forget(object_id)
        _remember_focus(turn, objects=[])
        return f"Forgotten. I deleted what you told me about your {_join(names)}."

    if _LIST.match(n):
        objects = list_objects(limit=50)
        if not objects:
            return "You haven't told me where anything is yet."
        names = [o["object"] for o in objects[:5]]
        more = f", and {len(objects) - 5} more" if len(objects) > 5 else ""
        return f"I remember {len(objects)} items you told me about: {_join(names)}{more}."

    m = _ALIAS.match(n)
    if m and _physical(m.group(1)):
        try:
            result = add_alias(m.group(1), m.group(2))
        except ValueError as exc:
            return str(exc)
        return f"Okay. I'll know {result['alias']} means your {result['object']}."

    # Statements: remember-prefixed or explicit first-person placement.
    body = n
    prefixed = False
    rm = _REMEMBER.match(n)
    if rm:
        body = rm.group(1)
        prefixed = True
    m = _PARKED.match(body)
    if m:
        vehicle = m.group(1) or "car"
        return _capture([vehicle], m.group(3), _relation(m.group(2)), turn, text)
    m = _MOVED_FROM.match(body)
    if m:
        objects = _split_objects(m.group(1))
        if all(_physical(o) or _clean(o) in _PRONOUNS for o in objects):
            return _capture(objects, m.group(3), "in", turn, text)
    m = _PLACED.match(body)
    if m:
        objects = _split_objects(m.group(2))
        if all(_physical(o) or _clean(o) in _PRONOUNS for o in objects) and _valid_place(m.group(4)):
            return _capture(objects, m.group(4), _relation(m.group(3)), turn, text)
    m = _IS_AT.match(body)
    if m and (prefixed or " now " in f" {body} ") and _physical(m.group(1)) and _valid_place(m.group(3)):
        return _capture(_split_objects(m.group(1)), m.group(3), _relation(m.group(2)), turn, text)
    m = _TOOK_OUT.match(body)
    if m and (_physical(m.group(1)) or _clean(m.group(1)) in _PRONOUNS):
        names = ([v["object"] for v in _object_names_for(_focus_objects(turn))]
                 if _clean(m.group(1)) in _PRONOUNS else _split_objects(m.group(1)))
        records = [record_placement(o, f"out of {m.group(2)}", channel=turn.channel, session_id=turn.session_id,
                                    utterance=text, kind="removal") for o in names]
        _remember_focus(turn, objects=[r["object_id"] for r in records], captured=True)
        return "Got it. I'll remember you took it out." if len(records) == 1 else "Got it."
    m = _GONE.match(body)
    if m and _physical(m.group(2)):
        how = m.group(1)
        records = [record_placement(o, how, channel=turn.channel, session_id=turn.session_id,
                                    utterance=text, kind="removal") for o in _split_objects(m.group(2))]
        _remember_focus(turn, objects=[r["object_id"] for r in records], captured=True)
        prior = [r for r in records if r["previous_place"]]
        if how == "lost" and prior:
            return (f"Noted. The last place you told me was {prior[0]['previous_relation']} "
                    f"{_speak_place(prior[0]['previous_place'])}.")
        return "Noted."
    if prefixed:
        # "Remember ..." that isn't an object placement belongs to another memory system.
        return None

    # Corrections right after a capture, or updates right after a lookup.
    m = _CORRECTION.match(n)
    continuing = turn.extras.get("previous_family", "object_memory") == "object_memory"
    if m and continuing and _focus_objects(turn):
        rest = m.group(1).strip()
        if rest:
            captured_at = get_focus("object_memory.captured_at", session_id=turn.session_id)
            is_correction = bool(captured_at and _now() - captured_at <= CORRECTION_WINDOW)
            pm = _PLACED.match(rest) or None
            if pm:
                return _capture(_split_objects(pm.group(2)), pm.group(4), _relation(pm.group(3)), turn, text,
                                correction=is_correction)
            place_text = _CORRECTION_LEAD.sub("", rest, count=1)
            relation = "in"
            pm2 = re.match(rf"^({_PREP_RE})\s+(.+)$", place_text)
            if pm2:
                relation, place_text = _relation(pm2.group(1)), pm2.group(2)
            place_text = re.sub(r"\s+(?:now|instead)$", "", place_text)
            if (pm2 or re.match(r"^(?:the|my|our)\s", place_text)) and _valid_place(place_text):
                return _capture(["it"], place_text, relation, turn, text, correction=is_correction)

    # Candidate selection after an ambiguous lookup.
    candidates = get_focus("object_memory.candidates", session_id=turn.session_id)
    if candidates:
        pick = _pick_candidate(n, candidates)
        if pick is not None:
            fresh = _object_names_for([pick["object_id"]])
            if fresh:
                view = fresh[0]
                place = view["current"]["place"] if view["current"] and view["current"]["kind"] == "placement" else None
                _remember_focus(turn, objects=[view["object_id"]], place=place)
                return _describe(view)

    # Lookups.
    m = _WHERE_PARKED.match(n)
    if m:
        return _lookup(m.group(1) or m.group(2) or "car", turn, definitive=True)
    m = _WHERE.match(n) or _SEEN.match(n)
    if m:
        target = m.group(1).strip()
        if _clean(target) in _PRONOUNS:
            focus = _object_names_for(_focus_objects(turn))
            if len(focus) == 1:
                return _describe(focus[0])
            return None
        if target in {"i", "we", "you", "am i", "are we"} or not _physical(target):
            return None
        definitive = bool(re.match(r"^(?:my|our)\s", target)) or " did i " in f" {n} " or " have i " in f" {n} " \
            or n.startswith("have you seen")
        reply = _lookup(target, turn, definitive=definitive)
        if reply and n.startswith("have you seen"):
            reply = "I can't see, but " + reply[0].lower() + reply[1:]
        return reply
    m = _IN_PLACE.match(n)
    if m and _valid_place(m.group(2)):
        place = m.group(2)
        if _clean(place) in {"there", "it"}:
            place = get_focus("object_memory.place", session_id=turn.session_id) or ""
            if not place:
                return None
        return _list_place(place, turn, exclude=[], also=False) if items_at(place) or _known_place(place) else None
    if _ELSE_THERE.match(n):
        place = get_focus("object_memory.place", session_id=turn.session_id)
        if not place:
            return "Where do you mean? I don't have a place in mind from what we were just discussing."
        return _list_place(place, turn, exclude=_focus_objects(turn), also=True)
    if _WHEN.match(n):
        focus = _object_names_for(_focus_objects(turn))
        if len(focus) == 1 and focus[0]["history"]:
            latest = focus[0]["history"][0]
            stamp = _parse_iso(latest["asserted_at"]).astimezone()
            return f"You told me {_when(stamp)}, at {stamp.strftime('%I:%M %p').lstrip('0')}."
        return None
    if _BEFORE.match(n):
        focus = _object_names_for(_focus_objects(turn))
        if len(focus) == 1:
            older = [h for h in focus[0]["history"][1:] if h["kind"] == "placement" and h["status"] == "superseded"]
            if not older:
                return f"That's the only place you've told me for your {focus[0]['object']}."
            prev = older[0]
            return f"Before that, you said {prev['relation']} {_speak_place(prev['place'])}, {_when(_parse_iso(prev['asserted_at']))}."
        return None
    if _SOURCE.match(n):
        focus = _object_names_for(_focus_objects(turn))
        if len(focus) == 1 and focus[0]["history"]:
            latest = focus[0]["history"][0]
            how = "by voice" if latest["source_kind"] == "user_spoken" else "in text"
            return (f"You told me {how} {_when(_parse_iso(latest['asserted_at']))}. It's your report; "
                    f"I didn't see it and I have no sensor confirming it.")
        return None
    return None


def _relation(prep: str) -> str:
    prep = prep.strip()
    return {"into": "in", "inside": "in", "inside of": "in", "onto": "on", "underneath": "under",
            "beneath": "under", "on top of": "on top of"}.get(prep, prep)


def _known_place(place: str) -> bool:
    target = set(_place_key(place).split())
    if not target:
        return False
    with _LOCK, _connect() as conn:
        for row in conn.execute("SELECT DISTINCT place_key FROM assertions WHERE kind='placement'"):
            if target <= set(str(row["place_key"]).split()):
                return True
    return False


def _pick_candidate(n: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    ordinals = {"the first one": 0, "first one": 0, "the first": 0, "the second one": 1, "second one": 1,
                "the second": 1, "the third one": 2, "third one": 2, "the last one": len(candidates) - 1}
    if n in ordinals and ordinals[n] < len(candidates):
        return candidates[ordinals[n]]
    key = object_key(re.sub(r"^(?:the|my)\s+|\s+one$", "", n))
    if not key:
        return None
    for candidate in candidates:
        if key == object_key(candidate["object"]) or set(key.split()) <= set(object_key(candidate["object"]).split()) and \
                len(key.split()) and key.split()[0] in object_key(candidate["object"]).split()[:1]:
            return candidate
    for candidate in candidates:
        if key in object_key(candidate["object"]).split() and key not in {"key", "keys"}:
            return candidate
    return None


register("object_memory", handle)
