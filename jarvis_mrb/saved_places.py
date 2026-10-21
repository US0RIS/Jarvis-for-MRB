from __future__ import annotations

"""User-named places ("home", "the office") saved explicitly from a phone fix.

A place exists only because the user said "save this place as home" while the
iPhone attached a fresh, permitted location fix. Horus never infers home from
movement history. ``resolve_place`` is the single place-resolution rule for
voice features: an explicitly named saved place, else the current phone fix
for "here / near me / around me", else an honest reason why no place is known.
"""

import os
import re
import sqlite3
from contextlib import contextmanager
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis_mrb.voice_router import VoiceTurn, register

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "saved_places.sqlite3"
_LOCK = threading.RLock()
_NAME = re.compile(r"^[a-z0-9][a-z0-9 '\-]{0,39}$")


@dataclass(frozen=True)
class ResolvedPlace:
    latitude: float
    longitude: float
    label: str          # spoken form: "home", "your current location"
    provenance: str     # "saved_place" | "phone_fix"
    captured_at: str
    accuracy_m: float | None = None


@contextmanager
def _open() -> Iterator[sqlite3.Connection]:
    """Commit on success and always close: a bare ``with conn`` leaves the file open,
    which blocks deleting the database on Windows."""
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS places(
            name TEXT PRIMARY KEY,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            accuracy_m REAL,
            saved_at TEXT NOT NULL,
            source TEXT NOT NULL
        )"""
    )
    conn.commit()
    return conn


def normalize_name(name: str) -> str:
    text = " ".join(str(name or "").lower().split()).strip(" .,!?")
    text = re.sub(r"^(?:my|the|our)\s+", "", text)
    return text if _NAME.match(text) else ""


def save_place(name: str, latitude: float, longitude: float, *, accuracy_m: float | None = None,
               source: str = "phone_fix") -> dict[str, Any]:
    key = normalize_name(name)
    if not key:
        raise ValueError("Place names are short words like 'home' or 'the office'.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Location out of range.")
    saved_at = datetime.now(timezone.utc).isoformat()
    with _LOCK, _open() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO places(name,latitude,longitude,accuracy_m,saved_at,source) VALUES(?,?,?,?,?,?)",
            (key, round(float(latitude), 5), round(float(longitude), 5), accuracy_m, saved_at, source[:40]),
        )
        conn.commit()
    return {"name": key, "latitude": round(float(latitude), 5), "longitude": round(float(longitude), 5),
            "accuracy_m": accuracy_m, "saved_at": saved_at, "source": source}


def get_place(name: str) -> dict[str, Any] | None:
    key = normalize_name(name)
    if not key:
        return None
    with _LOCK, _open() as conn:
        row = conn.execute("SELECT * FROM places WHERE name=?", (key,)).fetchone()
    return dict(row) if row else None


def list_places() -> list[dict[str, Any]]:
    with _LOCK, _open() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM places ORDER BY name")]


def forget_place(name: str) -> bool:
    key = normalize_name(name)
    with _LOCK, _open() as conn:
        deleted = conn.execute("DELETE FROM places WHERE name=?", (key,)).rowcount
        conn.commit()
    return bool(deleted)


_HERE = re.compile(r"\b(?:around (?:me|here)|near (?:me|here)|nearby|here|this area|my area|where i am|my location|my current location)\b")
_NAMED = re.compile(r"\b(?:near|around|at|by|for|close to|in)\s+(?:my |the |our )?([a-z][a-z0-9'\-]*(?: [a-z][a-z0-9'\-]*)?)\b")


def resolve_place(text: str, turn: VoiceTurn) -> tuple[ResolvedPlace | None, str]:
    """Resolve the place a voice request is about, or explain why not.

    Order: an explicitly named saved place mentioned in the request, then the
    current phone fix (only if fresh; the router already rejected stale ones).
    No saved place and no fix is an honest ``None`` with a reason.
    """
    lowered = " ".join(str(text or "").lower().split())
    for match in _NAMED.finditer(lowered):
        for candidate in (match.group(1), match.group(1).split(" ")[0]):
            place = get_place(candidate)
            if place:
                return ResolvedPlace(
                    float(place["latitude"]), float(place["longitude"]), place["name"], "saved_place",
                    str(place["saved_at"]), place.get("accuracy_m"),
                ), ""
    named_home = re.search(r"\b(?:near|around|at|by)\s+(?:my |the )?(home|house|office|work)\b", lowered)
    if named_home:
        return None, (f"I don't have {named_home.group(1)} saved. When you're there, say "
                      f"'save this place as {named_home.group(1)}'.")
    if turn.location is not None:
        fix = turn.location
        return ResolvedPlace(fix.latitude, fix.longitude, "your current location", "phone_fix",
                             fix.captured_at.isoformat(), fix.accuracy_m), ""
    reason = turn.location_note or "no phone location was attached"
    return None, f"I don't know where you are: {reason}. Allow location for Horus on the iPhone, or name a saved place."


_SAVE = re.compile(
    r"^(?:(?:hey\s+)?horus[, ]+)?(?:save|remember|mark|set)\s+(?:this|my current|the current)\s+(?:place|location|spot)\s+as\s+(.+)$"
    r"|^(?:(?:hey\s+)?horus[, ]+)?(?:this is|i'm at|i am at)\s+(home|my home|work|the office|my office)$"
)
_FORGET = re.compile(r"^(?:forget|delete|remove)\s+(?:my\s+|the\s+)?(?:saved\s+)?(?:place\s+|location\s+)?(.+?)\s+(?:place|location)$")
_LIST = re.compile(r"^(?:what|which)\s+places\s+(?:have\s+you\s+saved|do\s+you\s+know)|^list\s+(?:my\s+)?saved\s+places$")


def handle(text: str, turn: VoiceTurn) -> str | None:
    n = " ".join(text.lower().replace("’", "'").split()).strip(" .!?")
    m = _SAVE.match(n)
    if m:
        name = normalize_name(m.group(1) or m.group(2) or "")
        if not name:
            return "What should I call this place? Something short, like 'home'."
        if turn.location is None:
            return (f"I can't save {name}: {turn.location_note or 'no phone location was attached'}. "
                    "Allow location for Horus and try again.")
        fix = turn.location
        save_place(name, fix.latitude, fix.longitude, accuracy_m=fix.accuracy_m)
        accuracy = f", accurate to about {int(fix.accuracy_m)} meters" if fix.accuracy_m else ""
        return f"Saved this spot as {name}{accuracy}. Say 'forget my {name} location' to remove it."
    m = _FORGET.match(n)
    if m:
        name = normalize_name(m.group(1))
        if name and forget_place(name):
            return f"Forgot the saved {name} location."
        return None if not name else f"I don't have a saved place called {name}."
    if _LIST.match(n):
        places = list_places()
        if not places:
            return "You haven't saved any places."
        return "Saved places: " + ", ".join(p["name"] for p in places) + "."
    return None


register("saved_places", handle)
