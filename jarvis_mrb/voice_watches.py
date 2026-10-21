from __future__ import annotations

"""Natural-language "watch this" monitoring for the earpiece voice path.

An utterance such as "watch for new severe weather alerts near home for the
next three hours" is compiled into a typed ``external_watches`` watch (exact
kind, place, expiry, cadence). The place comes only from the shared
``saved_places.resolve_place`` rule: a fresh phone fix or a place the user
explicitly saved. Domains with no supported source are refused plainly rather
than stored as hollow watches.

When the background runner detects a *change* (never the baseline), the alert
is built here from the diff against the previous observation, carries its
source, evidence and observed time, and goes through the shared attention
ledger in ``proactive_attention`` (dedupe, cooldown, hourly budget, truthful
per-transport delivery state). Cancelled, paused and expired watches are
re-checked immediately before emission and can never alert.
"""

import hashlib
import json
import math
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import jarvis_mrb.world_model as world_model
from jarvis_mrb import external_watches as ew
from jarvis_mrb import proactive_attention as attention
from jarvis_mrb.voice_router import VoiceTurn, get_focus, register, set_focus, clear_focus
from jarvis_mrb.voice_time import (
    clock_words, local_clock, parse_duration_seconds, parse_until, span_words, when_words,
)

SCOPE = "personal"
DEFAULT_HOURS = 4
MAX_SECONDS = 168 * 3600
MIN_SECONDS = 300
FOCUS_KEY = "voice_watch_last"
_LOCK = threading.RLock()

# kind -> (spoken name, minimum cadence seconds, default cooldown seconds)
KINDS: dict[str, dict[str, Any]] = {
    "nws_alerts": {"noun": "weather", "name": "official NWS alerts", "interval": 900, "cooldown": 600},
    "usgs_earthquakes": {"noun": "earthquake", "name": "USGS earthquake reports", "interval": 900, "cooldown": 600},
    "air_quality": {"noun": "air quality", "name": "modelled air quality", "interval": 1800, "cooldown": 1800},
    "airspace_region": {"noun": "airspace", "name": "aircraft counts (OpenSky)", "interval": 1800, "cooldown": 1800},
}

CAPABILITIES = ("official NWS weather alerts", "USGS earthquakes", "modelled air quality",
                "aircraft counts in an area")


def _now() -> datetime:
    return datetime.now().astimezone()


# ------------------------------------------------------------------ store ---

@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    folder = world_model.APP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "voice_watches.sqlite3", timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS watch_meta (
            watch_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            place_label TEXT NOT NULL,
            place_provenance TEXT NOT NULL,
            rule_json TEXT NOT NULL,
            cooldown_seconds INTEGER NOT NULL,
            utterance TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            baseline_at TEXT,
            baseline_summary TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def get_meta(watch_id: str) -> dict[str, Any] | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM watch_meta WHERE watch_id=?", (watch_id,)).fetchone()
    if row is None:
        return None
    meta = {k: row[k] for k in row.keys()}
    meta["rule"] = json.loads(meta.pop("rule_json"))
    return meta


# ---------------------------------------------------------------- compile ---

def _norm(text: str) -> str:
    t = str(text or "").lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9:.' ]+", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    t = " ".join(t.split())
    t = re.sub(r"^(?:(?:hey|ok|okay) )?(?:horus|jarvis) ", "", t)
    t = re.sub(r"^(?:please |can you |could you |would you |i want you to |i'd like you to |go ahead and )+", "", t)
    return t.strip()


_CREATE_VERB = re.compile(
    r"^(?:watch|monitor|track|keep (?:an eye on|watch on|watch for|watching|tabs on|track of)|"
    r"(?:set up|start|create|begin|add) (?:a |an )?(?:new )?(?:watch|monitor|alert)\b)")
_MEDIA = re.compile(r"\b(?:video|videos|movie|movies|show|shows|youtube|netflix|tv|television|stream|game tonight|"
                    r"cpu|memory|ram|disk|battery|process|screen|clipboard|folder|file|inbox|world armor|armor)\b")
_TELL_ME = re.compile(
    r"^(?:tell|let|alert|notify|warn|ping|message) me\b.*\b(?:if|when|whenever|once|as soon as)\b|"
    r"^(?:alert|notify|warn) me (?:of|about|to)\b")

_D_NWS = re.compile(
    r"\b(?:severe weather|weather (?:alerts?|warnings?|watch(?:es)?|advisor(?:y|ies)|emergenc(?:y|ies))|"
    r"storm (?:alerts?|warnings?|watch(?:es)?)|nws|national weather service|tornado(?:es)?|flash floods?|"
    r"flood(?:ing)?(?: warnings?| watch(?:es)?)?|hurricanes?|tsunamis?|thunderstorms?|blizzards?|winter storms?|"
    r"heat (?:advisor(?:y|ies)|warnings?|wave)|red flag|ice storms?|dangerous weather|bad weather|the weather|weather)\b")
_D_USGS = re.compile(r"\b(?:earthquakes?|quakes?|seismic|tremors?|aftershocks?)\b")
_D_AIR = re.compile(r"\b(?:air quality|aqi|air pollution|smog|unhealthy air|smoke|poor air)\b")
_D_AIRSPACE = re.compile(r"\b(?:airspace|aircraft|planes?|air traffic|jets?|helicopters?|planes overhead)\b")

_UNSUPPORTED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(?:flights?|airline|airlines|gate changes?)\b|\bdelay(?:ed|s)?\b.*\b(?:flight|plane)\b"),
     "flight delays or flight status",
     "I have no flight-status source"),
    (re.compile(r"\b(?:trains?|transit|buses|bus|subway|metro|ferry|ferries|commute|delayed trains?)\b"),
     "train, bus or transit status",
     "I have no transit-status source"),
    (re.compile(r"\b(?:traffic|road closures?|road conditions|accidents?)\b"),
     "traffic or road closures", "I have no live traffic or road-closure source"),
    (re.compile(r"\b(?:prices?|stocks?|shares?|bitcoin|crypto(?:currency)?|market)\b"),
     "prices or markets", "I have no market-price source"),
    (re.compile(r"\b(?:packages?|parcels?|shipments?|deliver(?:y|ies))\b"),
     "package delivery", "I have no package-tracking source"),
    (re.compile(r"\b(?:wild ?fires?|fires?|evacuations?)\b"),
     "wildfires or evacuations",
     "I have no wildfire-perimeter or evacuation source. NWS alerts include Red Flag warnings, but that is not a fire map"),
    (re.compile(r"\b(?:rain|raining|snow|snowing|forecast|temperature|sunny|cold|hot)\b"),
     "rain, snow or forecasts",
     "I only watch official NWS alerts, not forecasts or precipitation"),
    (re.compile(r"\b(?:sec filings?|filings?|10-k|8-k)\b"),
     "company filings",
     "Filing watches need a company's SEC registrant number, which I can't resolve by voice yet"),
]
_UNSUPPORTED_TELL_ME = re.compile(
    r"\b(?:flights?|delay(?:ed|s)?|trains?|transit|subway|ferry|traffic|road closures?|prices?|stocks?|"
    r"bitcoin|crypto|packages?|parcels?|shipments?|wild ?fires?|evacuations?|rain|snow|forecast|temperature|"
    r"filings?)\b")

_CADENCE = re.compile(r"\bevery\s+(?:(?P<half>half an? hour)|(?P<n>\d+|one|two|three|four|five|ten|fifteen|twenty|thirty|an?)?\s*(?P<u>minutes?|mins?|hours?|hrs?))\b")
_NUMW = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10,
         "fifteen": 15, "twenty": 20, "thirty": 30}
_THRESH = re.compile(r"\b(?:above|over|exceeds?|exceeding|greater than|higher than|more than|reaches?|hits?|crosses?|past|tops?)\s+(\d{2,3})\b")
_MAG = re.compile(r"\b(?:magnitude|mag)\s*(?:of\s+)?(\d(?:\.\d)?)|\b(?:above|over|bigger than|stronger than|larger than|at least)\s+(?:a\s+)?(?:magnitude\s+)?(\d(?:\.\d)?)\b")
_RADIUS = re.compile(r"\bwithin\s+(\d+(?:\.\d+)?)\s*(miles?|mi|kilometers?|kilometres?|km)\b")
_HERE_WORDS = {"me", "here", "next", "coming", "last", "this", "my", "our", "a", "an", "morning", "evening",
               "afternoon", "night", "time", "case", "order", "clock", "area", "nearby", "the", "us"}
_NAMED_UNKNOWN = re.compile(
    r"\b(?:near|around|close to)\s+(?:the\s+|my\s+)?(?P<p>[a-z][a-z' -]{1,30}?)"
    r"(?=\s+(?:for|until|till|til|tonight|today|tomorrow|and|every|within|above|over|if|when|that|to|in|by)\b|$)")

NO_LOCATION = ("I don't have your location. Say 'near home' once you've saved home, "
               "or enable location on your iPhone.")


@dataclass
class WatchPlan:
    kind: str
    latitude: float
    longitude: float
    place_label: str
    place_provenance: str
    expires_at: datetime
    interval_seconds: int
    rule: dict[str, Any]
    cooldown_seconds: int
    notes: list[str] = field(default_factory=list)
    label: str = ""


@dataclass
class Compiled:
    status: str                     # not_watch | needs_place | unsupported | ok
    reply: str = ""
    plans: list[WatchPlan] = field(default_factory=list)
    unsupported_note: str = ""


def _is_create_intent(t: str) -> bool:
    if _CREATE_VERB.match(t):
        return not _MEDIA.search(t)
    return bool(_TELL_ME.match(t))


_NWS_STRONG = re.compile(
    r"\b(?:alerts?|warnings?|severe|advisor|watch(?:es)?|storm|tornado|flood|hurricane|tsunami|nws|"
    r"national weather|thunderstorm|blizzard|heat|red flag|dangerous)\b")
_PRECIP = re.compile(r"\b(?:rain|raining|snow|snowing|forecast|temperature)\b")


def _detect_kinds(t: str) -> list[str]:
    kinds = []
    if _D_USGS.search(t):
        kinds.append("usgs_earthquakes")
    if _D_AIR.search(t):
        kinds.append("air_quality")
    if _D_AIRSPACE.search(t):
        kinds.append("airspace_region")
    m = _D_NWS.search(t)
    if m:
        # "watch the weather for rain" is a forecast request, not an alert watch.
        generic = m.group(0) in {"weather", "the weather"} and not _NWS_STRONG.search(t)
        if not (generic and _PRECIP.search(t)):
            kinds.append("nws_alerts")
    return kinds


def _unsupported(t: str, *, tell_me: bool) -> tuple[str, str] | None:
    if tell_me and not _UNSUPPORTED_TELL_ME.search(t):
        return None
    for pattern, what, why in _UNSUPPORTED:
        if pattern.search(t):
            return what, why
    return None


def _cadence(t: str) -> tuple[int | None, str]:
    m = _CADENCE.search(t)
    if not m:
        return None, t
    if m.group("half"):
        seconds = 1800
    else:
        raw = (m.group("n") or "1").strip()
        n = int(raw) if raw.isdigit() else _NUMW.get(raw, 1)
        unit = m.group("u")
        seconds = n * (60 if unit.startswith("min") else 3600)
    return seconds, t[:m.start()] + " " + t[m.end():]


def _named_unknown_place(t: str) -> str:
    for m in _NAMED_UNKNOWN.finditer(t):
        words = m.group("p").split()
        if words and words[0] not in _HERE_WORDS:
            return m.group("p")
    return ""


def compile_utterance(text: str, turn: VoiceTurn, *, now: datetime | None = None) -> Compiled:
    """Turn a spoken watch request into typed plans, or an honest reply."""
    t = _norm(text)
    if not _is_create_intent(t):
        return Compiled("not_watch")
    tell_me = not _CREATE_VERB.match(t)
    kinds = _detect_kinds(t)
    bad = _unsupported(t.replace("air traffic", " "), tell_me=tell_me)
    if not kinds:
        if bad is None:
            return Compiled("not_watch")
        what, why = bad
        return Compiled("unsupported", (
            f"{why}, so I can't watch {what}, and I haven't stored a watch. "
            f"I can watch {', '.join(CAPABILITIES[:-1])} or {CAPABILITIES[-1]}."))
    instant = now or _now()

    # Place: only a saved place the user named, or the fresh phone fix.
    from jarvis_mrb.saved_places import resolve_place
    place, reason = resolve_place(t, turn)
    unknown = _named_unknown_place(t)
    if place is None or (unknown and place.provenance != "saved_place"):
        if place is not None and unknown:
            return Compiled("needs_place", (
                f"I can't look up '{unknown}'. I can watch around your phone's location or a place you've "
                f"saved, like home. Say 'near me', or save it by saying 'save this place as {unknown}' when you're there."))
        if "i don't have" in (reason or "").lower() and "saved" in reason.lower():
            return Compiled("needs_place", reason + " Or enable location and say 'near me'.")
        return Compiled("needs_place", NO_LOCATION + (f" ({turn.location_note})" if turn.location_note and
                                                       turn.location_note != "no phone location was attached" else ""))

    cadence_request, t_no_cadence = _cadence(t)
    seconds = None
    exact_until = None
    until = parse_until(t_no_cadence, instant)
    notes: list[str] = []
    if until is not None:
        seconds = (until - instant).total_seconds()
        exact_until = until
    else:
        seconds = parse_duration_seconds(t_no_cadence)
    if seconds is None:
        seconds = DEFAULT_HOURS * 3600
        notes.append(f"You didn't say how long, so I chose {DEFAULT_HOURS} hours.")
    if seconds > MAX_SECONDS:
        seconds = MAX_SECONDS
        notes.append("That's longer than I can watch, so I capped it at 7 days.")
    if seconds < MIN_SECONDS:
        seconds = MIN_SECONDS
        notes.append("The shortest watch is 5 minutes.")
    if exact_until is not None and MIN_SECONDS <= seconds <= MAX_SECONDS:
        expires = exact_until
    else:
        expires = instant + timedelta(seconds=int(seconds))

    plans: list[WatchPlan] = []
    for kind in kinds:
        spec = KINDS[kind]
        plan_notes = list(notes) if not plans else []
        interval = spec["interval"]
        if cadence_request is not None:
            if cadence_request < interval:
                plan_notes.append(f"I can't check {spec['noun']} more often than every {span_words(interval)}.")
            elif cadence_request <= 86400:
                interval = cadence_request
        rule: dict[str, Any] = {}
        if kind == "usgs_earthquakes":
            m = _MAG.search(t)
            mag = float(next(g for g in m.groups() if g)) if m else 2.5
            rule["min_magnitude"] = max(2.5, min(mag, 9.0))
            if m and mag < 2.5:
                plan_notes.append("USGS reports here start at magnitude 2.5.")
        elif kind == "air_quality":
            m = _THRESH.search(t)
            thr = float(m.group(1)) if m else 100.0
            rule["us_aqi_threshold"] = max(1.0, min(thr, 500.0))
        elif kind == "airspace_region":
            m = _RADIUS.search(t)
            radius = 20.0
            if m:
                radius = float(m.group(1)) * (1.609344 if m.group(2).startswith(("mi",)) else 1.0)
            rule["radius_km"] = max(1.0, min(round(radius, 1), 80.0))
        if kind == "nws_alerts":
            try:
                from jarvis_mrb.physical_conditions import _in_nws_approximate_region
                if not _in_nws_approximate_region(place.latitude, place.longitude):
                    return Compiled("unsupported", (
                        "The National Weather Service only covers the United States and its territories, "
                        "and I have no weather-alert source for this place, so I haven't stored a watch."))
            except Exception:
                pass
        label = f"Voice: {spec['name']} near {place.label}"[:120]
        plans.append(WatchPlan(
            kind=kind, latitude=round(place.latitude, 4), longitude=round(place.longitude, 4),
            place_label=place.label, place_provenance=place.provenance, expires_at=expires,
            interval_seconds=int(interval), rule=rule, cooldown_seconds=spec["cooldown"],
            notes=plan_notes, label=label))
    note = ""
    if bad is not None and not (bad[0].startswith("rain") and "nws_alerts" in kinds):
        note = f"I have no supported source for {bad[0]}, so I skipped that part."
    return Compiled("ok", plans=plans, unsupported_note=note)


# ---------------------------------------------------------------- speaking ---

def _place_phrase(label: str, provenance: str) -> str:
    """Use after "near"/"of": 'this area' or 'home'."""
    return "this area" if provenance == "phone_fix" else label


def _place_for(label: str, provenance: str) -> str:
    """Use after "for": 'this area' or 'the area near home'."""
    return "this area" if provenance == "phone_fix" else f"the area near {label}"


def _cadence_words(seconds: int) -> str:
    if seconds == 3600:
        return "hour"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} hours"
    return f"{seconds // 60} minutes"


def _runner_caveat() -> str:
    if ew.runner_status()["active"]:
        return ""
    return (" Note: Horus's background watch runner has not checked in, so nothing is being checked "
            "until the Horus service is running.")


def _confirmation(plan: WatchPlan, now: datetime) -> str:
    until = when_words(plan.expires_at, now)
    place = _place_for(plan.place_label, plan.place_provenance)
    place_of = _place_phrase(plan.place_label, plan.place_provenance)
    every = _cadence_words(plan.interval_seconds)
    noun = KINDS[plan.kind]["noun"]
    if plan.kind == "nws_alerts":
        body = (f"I'll watch official NWS alerts for {place} until {until}, every {every}. "
                "I'll only announce new alerts, not ones already active.")
    elif plan.kind == "usgs_earthquakes":
        body = (f"I'll watch USGS earthquake reports of magnitude {plan.rule['min_magnitude']:g} or higher "
                f"within 100 kilometers of {place_of} until {until}, every {every}.")
    elif plan.kind == "air_quality":
        body = (f"I'll watch modelled US air quality for {place} until {until}, every {every}, and tell you "
                f"if it goes above {plan.rule['us_aqi_threshold']:g}.")
    else:
        body = (f"I'll watch aircraft counts within {plan.rule['radius_km']:g} kilometers of {place_of} until "
                f"{until}, every {every}, and tell you about large changes. That's an OpenSky count with "
                "incomplete coverage, not who or what is flying.")
    cancel_word = {"weather": "the weather", "earthquake": "the earthquake", "air quality": "the air quality",
                   "airspace": "the airspace"}[noun]
    tail = f" Say 'cancel {cancel_word} watch' anytime."
    notes = (" " + " ".join(plan.notes)) if plan.notes else ""
    return body + notes + tail


def _identity(kind: str, lat: float, lon: float, rule: dict[str, Any]) -> tuple:
    return (kind, round(lat, 2), round(lon, 2), rule.get("us_aqi_threshold"), rule.get("radius_km"))


def _watch_rows() -> list[dict[str, Any]]:
    rows = ew.list_watches(SCOPE)
    with _db() as conn:
        metas = {r["watch_id"]: r for r in conn.execute("SELECT * FROM watch_meta")}
    out = []
    for w in rows:
        meta = metas.get(w["id"])
        w = dict(w)
        w["voice"] = None
        if meta is not None:
            w["voice"] = {k: meta[k] for k in meta.keys() if k != "rule_json"}
            w["voice"]["rule"] = json.loads(meta["rule_json"])
        out.append(w)
    return out


def create_from_plan(plan: WatchPlan, turn: VoiceTurn, utterance: str, *, now: datetime | None = None) -> tuple[dict[str, Any], bool]:
    """Create (or find the identical active) watch. Returns (watch, created)."""
    instant = now or _now()
    ident = _identity(plan.kind, plan.latitude, plan.longitude, plan.rule)
    with _LOCK:
        for w in _watch_rows():
            v = w.get("voice")
            if v and w["state"] in {"active", "paused"}:
                cfg = w["config"]
                if _identity(w["kind"], cfg["latitude"], cfg["longitude"], v["rule"]) == ident:
                    return w, False
        config: dict[str, Any] = {"latitude": plan.latitude, "longitude": plan.longitude}
        if plan.kind == "air_quality":
            config["us_aqi_threshold"] = plan.rule["us_aqi_threshold"]
        if plan.kind == "airspace_region":
            config["radius_km"] = plan.rule["radius_km"]
        watch = ew.create_watch(SCOPE, plan.kind, plan.label, config,
                                interval_seconds=plan.interval_seconds, expires_at=plan.expires_at)
        with _db() as conn:
            conn.execute(
                """INSERT INTO watch_meta(watch_id,kind,place_label,place_provenance,rule_json,
                   cooldown_seconds,utterance,session_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (watch["id"], plan.kind, plan.place_label, plan.place_provenance, json.dumps(plan.rule),
                 plan.cooldown_seconds, utterance[:300], turn.session_id, instant.astimezone(timezone.utc).isoformat()))
    return ew.get_watch(watch["id"], SCOPE), True


def _create(text: str, turn: VoiceTurn, now: datetime | None = None) -> str | None:
    instant = now or _now()
    result = compile_utterance(text, turn, now=instant)
    if result.status == "not_watch":
        return None
    if result.status in {"needs_place", "unsupported"}:
        return result.reply
    parts: list[str] = []
    for plan in result.plans:
        try:
            watch, created = create_from_plan(plan, turn, text, now=instant)
        except (ValueError, TypeError) as exc:
            parts.append(f"I couldn't set up the {KINDS[plan.kind]['noun']} watch: {str(exc)[:160]}")
            continue
        set_focus(FOCUS_KEY, {"watch_id": watch["id"]}, session_id=turn.session_id)
        if created:
            parts.append(_confirmation(plan, instant))
        else:
            until = when_words(datetime.fromisoformat(watch["expires_at"]), instant)
            parts.append(f"I'm already watching that until {until}. Say 'cancel the "
                         f"{KINDS[plan.kind]['noun']} watch' to stop it.")
    if result.unsupported_note:
        parts.append(result.unsupported_note)
    caveat = _runner_caveat()
    return " ".join(parts) + caveat if parts else None


# ------------------------------------------------------------- list / manage ---

_STOP = {"the", "my", "a", "an", "this", "that", "please", "watch", "watches", "watching", "monitor",
         "monitors", "monitoring", "for", "on", "of", "alerts", "alert", "warnings", "again", "now", "it"}
_SEL: dict[str, re.Pattern[str]] = {
    "nws_alerts": re.compile(r"\b(?:weather|storms?|nws|severe|tornado(?:es)?|floods?|hurricanes?)\b"),
    "usgs_earthquakes": re.compile(r"\b(?:earthquakes?|quakes?|seismic)\b"),
    "air_quality": re.compile(r"\b(?:air|aqi|quality|smog|smoke)\b"),
    "airspace_region": re.compile(r"\b(?:airspace|aircraft|planes?|air traffic|flights?)\b"),
}
_ALL = re.compile(r"\b(?:all|every|everything|both)\b")
_LIST = re.compile(
    r"^(?:what|which)(?: things| watches| monitors)? (?:are|am) (?:you|we|i) (?:watching|monitoring|tracking)(?: for me| right now| now)?$|"
    r"^what(?:'s| is) being (?:watched|monitored)$|"
    r"^(?:list|show|tell me|read)(?: me)?(?: my| all| the| active)* (?:watches|monitors)$|"
    r"^what (?:watches|monitors) (?:do i have|are (?:active|running|set|on))$|"
    r"^(?:are you|is horus) (?:watching|monitoring) (?:anything|something)(?: for me| right now)?$|"
    r"^what are you keeping an eye on$|^what (?:am i|are we) watching$")
_MANAGE = re.compile(
    r"^(?P<verb>pause|resume|unpause|cancel|stop|end|delete|remove|continue|restart)\s+(?P<rest>.+)$")
_CANCEL_THAT = re.compile(r"^(?:cancel|stop|end|undo|remove|delete) (?:that|it|this)(?: watch)?$|^never mind (?:that|the) watch$")


def _ago(iso: str | None, now: datetime) -> str:
    if not iso:
        return "not checked yet"
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return "check time unknown"
    return span_words((now.astimezone(timezone.utc) - then).total_seconds()) + " ago"


def describe_watch(w: dict[str, Any], now: datetime) -> str:
    v = w.get("voice")
    expires = when_words(datetime.fromisoformat(w["expires_at"]), now)
    every = _cadence_words(int(w["interval_seconds"]))
    if v:
        spec = KINDS.get(w["kind"], {"name": w["kind"]})
        head = f"{spec['name']} for {_place_for(v['place_label'], v['place_provenance'])}"
        if w["kind"] == "air_quality":
            head += f" above {v['rule'].get('us_aqi_threshold', 100):g}"
    else:
        head = str(w["label"])
    status = f"until {expires}, every {every}"
    if w["state"] == "paused":
        status = f"paused (still expires {expires})"
    if w["last_checked_at"] is None:
        check = "not checked yet"
    elif w["last_status"] not in {"ok", "partial"}:
        check = f"last check {_ago(w['last_checked_at'], now)} did not succeed ({w['last_status']}), so its state is unknown"
    else:
        check = f"last checked {_ago(w['last_checked_at'], now)}"
    base = ""
    if v and v.get("baseline_summary"):
        base = f"; at start: {v['baseline_summary']}"
    return f"{head}, {status}, {check}{base}"


def list_answer(now: datetime | None = None) -> str:
    instant = now or _now()
    rows = [w for w in _watch_rows() if w["state"] in {"active", "paused"}]
    if not rows:
        return "I'm not watching anything for you right now." + (
            "" if ew.runner_status()["active"] else " The background watch runner is not running either.")
    items = [describe_watch(w, instant) for w in rows]
    head = f"I have {len(rows)} watch{'es' if len(rows) != 1 else ''}. " if len(rows) > 1 else "I have one watch. "
    return head + ". ".join(item[0].upper() + item[1:] for item in items) + "." + _runner_caveat()


def _select(rest: str, rows: list[dict[str, Any]], turn: VoiceTurn) -> tuple[list[dict[str, Any]], str]:
    """Pick target watches from words, or explain why that is ambiguous."""
    leftover = [w for w in re.findall(r"[a-z0-9']+", rest) if w not in _STOP]
    kinds = [k for k, p in _SEL.items() if p.search(rest)]
    covered = set()
    for k in kinds:
        covered.update(w for w in leftover if _SEL[k].fullmatch(w))
    if _ALL.search(rest):
        return rows, ""
    unexplained = [w for w in leftover if w not in covered and not _ALL.fullmatch(w)]
    if unexplained:
        return [], "not_ours"
    if kinds:
        chosen = [w for w in rows if w["kind"] in kinds]
        return chosen, "" if chosen else "none"
    focus = get_focus(FOCUS_KEY, session_id=turn.session_id)
    if focus:
        chosen = [w for w in rows if w["id"] == focus["watch_id"]]
        if chosen:
            return chosen, ""
    if len(rows) == 1:
        return rows, ""
    if not rows:
        return [], "none"
    nouns = sorted({KINDS[w["kind"]]["noun"] for w in rows if w["kind"] in KINDS})
    return [], "ambiguous:" + " or ".join(nouns)


def _manage(verb: str, rest: str, turn: VoiceTurn, now: datetime) -> str | None:
    if "armor" in rest or not re.search(r"\b(?:watch|watches|watching|monitor|monitors|monitoring)\b", rest):
        return None
    all_rows = _watch_rows()
    resume_like = verb in {"resume", "unpause", "continue", "restart"}
    live = [w for w in all_rows if w["state"] in {"active", "paused"}]
    chosen, problem = _select(rest, live, turn)
    if problem == "none":
        # Nothing live matches: look at ended watches so we can say why.
        chosen, problem2 = _select(rest, all_rows, turn)
        problem = problem2 if not chosen else ""
    if problem == "not_ours":
        return None
    if problem.startswith("ambiguous:"):
        return f"Which watch: {problem.split(':', 1)[1]}? Or say 'all watches'."
    if not chosen:
        return "I have no matching watch to " + ("resume" if resume_like else "pause" if verb == "pause" else "cancel") + "."
    done: list[str] = []
    for w in chosen:
        name = KINDS.get(w["kind"], {"noun": "external"})["noun"]
        try:
            if verb == "pause":
                if w["state"] != "active":
                    done.append(f"the {name} watch is already {w['state']}")
                    continue
                ew.pause_watch(w["id"], SCOPE)
                done.append(f"Paused the {name} watch. It still expires at {when_words(datetime.fromisoformat(w['expires_at']), now)}; "
                            "nothing is checked or announced while it's paused")
            elif resume_like:
                if w["state"] != "paused":
                    done.append(f"the {name} watch is {w['state']} and can't be resumed" if w["state"] != "active"
                                else f"the {name} watch isn't paused")
                    continue
                ew.resume_watch(w["id"], SCOPE)
                done.append(f"Resumed the {name} watch. The next check sets a fresh baseline, so changes during the pause won't be reported")
            else:
                if w["state"] in {"cancelled", "expired"}:
                    done.append(f"the {name} watch is already {w['state']}")
                    continue
                ew.stop_watch(w["id"], SCOPE)
                done.append(f"Cancelled the {name} watch. It won't check or alert anymore")
        except ValueError as exc:
            done.append(str(exc)[:120])
    if verb != "pause" and not resume_like:
        clear_focus_key(turn)
    reply = ". ".join(d[0].upper() + d[1:] if not d[0].isupper() else d for d in done) + "."
    return reply


def clear_focus_key(turn: VoiceTurn) -> None:
    set_focus(FOCUS_KEY, None, session_id=turn.session_id, ttl_seconds=1)


def handle(text: str, turn: VoiceTurn) -> str | None:
    t = _norm(text)
    if not t:
        return None
    instant = _now()
    if _LIST.match(t):
        return list_answer(instant)
    if _CANCEL_THAT.match(t):
        focus = get_focus(FOCUS_KEY, session_id=turn.session_id)
        if not focus:
            return None  # a bare "cancel" belongs to pending-action handling
        return _manage("cancel", "that watch", turn, instant)
    m = _MANAGE.match(t)
    if m:
        return _manage(m.group("verb"), m.group("rest"), turn, instant)
    return _create(text, turn, instant)


# ------------------------------------------------------------------ alerts ---

def _inactive_reason(watch_id: str) -> str:
    try:
        w = ew.get_watch(watch_id, SCOPE)
    except ValueError:
        return "cancelled"
    return "" if w["state"] == "active" else w["state"]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _baseline_summary(kind: str, payload: dict[str, Any]) -> str:
    if kind == "nws_alerts":
        alerts = payload.get("alerts") or []
        if not alerts:
            return "no NWS alerts were active at the point (not an all-clear for other hazards)"
        return f"{len(alerts)} NWS alert(s) already active ({', '.join(sorted({a['event'] for a in alerts})[:3])}); I only announce new ones"
    if kind == "usgs_earthquakes":
        return f"{len(payload.get('events') or [])} earthquake(s) already on record in the last 24 hours; I only announce new ones"
    if kind == "air_quality":
        aqi = (payload.get("air_quality") or {}).get("us_aqi")
        return "US AQI unknown" if aqi is None else f"US AQI was {aqi:g} (model estimate)"
    if kind == "airspace_region":
        count = payload.get("aircraft_count")
        return "aircraft count unknown" if count is None else f"{count} aircraft reported"
    return ""


def _compose(meta: dict[str, Any], watch: dict[str, Any], evidence: dict[str, Any],
             previous: dict[str, Any] | None, checked_at: str) -> attention.ProactiveItem | None:
    kind, wid = watch["kind"], watch["id"]
    payload = evidence.get("payload") or {}
    place = _place_phrase(meta["place_label"], meta["place_provenance"])
    place_for = _place_for(meta["place_label"], meta["place_provenance"])
    rule = meta["rule"]
    source_url = str(evidence.get("source_url") or "")
    observed = str(evidence.get("observed_at") or checked_at)
    common = dict(kind="watch_alert", subject=wid, title="Horus watch", source_url=source_url,
                  observed_at=observed, cooldown_key=wid, cooldown_seconds=int(meta["cooldown_seconds"]))
    when = local_clock(checked_at)

    if kind == "nws_alerts":
        prev_ids = {a["id"] for a in (previous or {}).get("alerts", [])} if previous else set()
        new = [a for a in payload.get("alerts", [])
               if a["id"] not in prev_ids and not attention.is_emitted(f"nws:{wid}:{a['id']}")]
        if not new:
            return None
        events = sorted({a["event"] or "alert" for a in new})
        critical = any(a["severity"] == "Extreme" or (a["severity"] == "Severe" and a["urgency"] == "Immediate")
                       for a in new)
        severity = "critical" if critical else "warning" if any(a["severity"] in {"Severe", "Moderate"} for a in new) else "info"
        head = new[0]["headline"] or new[0]["event"]
        text = (f"New National Weather Service alert for {place_for}: {', '.join(events[:3])}. "
                f"{_short(head, 170)} Source: NWS, checked {when}.")
        ids_hash = hashlib.sha256("|".join(sorted(a["id"] for a in new)).encode()).hexdigest()[:16]
        return attention.ProactiveItem(
            **common, dedupe_key=f"nws:{wid}:{ids_hash}", text=text, severity=severity, critical=critical,
            rule=f"your voice watch for new official NWS alerts for {place_for} found an alert id it had not seen",
            evidence_lines=[f"{a['event']} ({a['severity']}, {a['urgency']}): {_short(a['headline'], 160)}; "
                            f"expires {local_clock(a['expires'])}; id {a['id'][-28:]}" for a in new[:5]],
            evidence={"new_alert_ids": [a["id"] for a in new], "alerts": new[:5]},
            source="National Weather Service (api.weather.gov)",
            extra_keys=tuple(f"nws:{wid}:{a['id']}" for a in new))

    if kind == "usgs_earthquakes":
        prev_ids = {e["id"] for e in (previous or {}).get("events", [])} if previous else set()
        minimum = float(rule.get("min_magnitude", 2.5))
        new = [e for e in payload.get("events", [])
               if e["id"] not in prev_ids and e["magnitude"] >= minimum
               and not attention.is_emitted(f"usgs:{wid}:{e['id']}")]
        if not new:
            return None
        top = max(new, key=lambda e: e["magnitude"])
        distance = ""
        if top.get("latitude") is not None and top.get("longitude") is not None:
            d = _haversine_km(watch["config"]["latitude"], watch["config"]["longitude"],
                              top["latitude"], top["longitude"])
            distance = f" about {d:.0f} kilometers from the watched point,"
        status = "reviewed by USGS" if top.get("reviewed") else "automatic and preliminary, may be revised"
        more = f" {len(new) - 1} other new report{'s' if len(new) > 2 else ''}." if len(new) > 1 else ""
        text = (f"Earthquake reported near {place}: magnitude {top['magnitude']:g}, {top['place']},{distance} "
                f"at {local_clock(top['occurred_at'])}. {status.capitalize()}.{more} Source: USGS, checked {when}.")
        critical = top["magnitude"] >= 6.0
        return attention.ProactiveItem(
            **{**common, "source_url": top.get("source_url") or source_url},
            dedupe_key=f"usgs:{wid}:" + hashlib.sha256("|".join(sorted(e["id"] for e in new)).encode()).hexdigest()[:16],
            text=text, severity="critical" if critical else "warning" if top["magnitude"] >= 4.5 else "info",
            critical=critical,
            rule=f"your voice watch for earthquakes of magnitude {minimum:g} or higher within 100 km of {place} found a new USGS event",
            evidence_lines=[f"M{e['magnitude']:g} {e['place']} at {local_clock(e['occurred_at'])} (USGS id {e['id']}, "
                            f"{'reviewed' if e.get('reviewed') else 'preliminary'})" for e in new[:5]],
            evidence={"new_event_ids": [e["id"] for e in new], "events": new[:5]},
            source="USGS Earthquake Hazards Program", extra_keys=tuple(f"usgs:{wid}:{e['id']}" for e in new))

    if kind == "air_quality":
        air = payload.get("air_quality") or {}
        aqi = air.get("us_aqi")
        threshold = float(watch["config"].get("us_aqi_threshold", 100))
        if aqi is None or aqi < threshold:
            return None
        prev_aqi = ((previous or {}).get("air_quality") or {}).get("us_aqi")
        if prev_aqi is not None and prev_aqi >= threshold:
            return None
        model_time = air.get("model_time_utc") or checked_at
        text = (f"Air quality for {place_for} is now US AQI {aqi:g}, above your threshold of {threshold:g}. "
                f"This is a model estimate, not a sensor reading. Source: Open-Meteo air-quality model, "
                f"model time {local_clock(model_time)}, checked {when}.")
        return attention.ProactiveItem(
            **{**common, "observed_at": str(model_time)}, dedupe_key=f"aqi:{wid}:{model_time}", text=text,
            severity="warning" if aqi >= 151 else "info",
            rule=f"your voice watch for US AQI above {threshold:g} for {place_for} saw it cross the threshold",
            evidence_lines=[f"US AQI {aqi:g} at model time {local_clock(model_time)}; "
                            + (f"previous reading {prev_aqi:g}" if prev_aqi is not None else "previous reading unknown")],
            evidence={"us_aqi": aqi, "previous_us_aqi": prev_aqi, "threshold": threshold},
            source="Open-Meteo air-quality model (modelled, not measured)")

    if kind == "airspace_region":
        new_count = payload.get("aircraft_count")
        old_count = (previous or {}).get("aircraft_count") if previous else None
        if new_count is None or old_count is None:
            return None
        delta = abs(new_count - old_count)
        if delta < 5 or delta < 0.5 * max(old_count, 1):
            return None
        radius = float(watch["config"].get("radius_km", 20))
        text = (f"Aircraft count within {radius:g} kilometers of {place} changed from {old_count} to {new_count}. "
                f"That's an OpenSky count with incomplete coverage, not identification of any aircraft. "
                f"Source: OpenSky Network, data time {local_clock(evidence.get('observed_at'))}, checked {when}.")
        return attention.ProactiveItem(
            **common, dedupe_key=f"airspace:{wid}:{old_count}>{new_count}:{observed}", text=text, severity="info",
            rule=f"your voice watch on aircraft within {radius:g} km of {place} saw a change of at least 5 and 50 percent",
            evidence_lines=[f"count {old_count} -> {new_count} (change {delta})"],
            evidence={"previous": old_count, "current": new_count},
            source="OpenSky Network (state vectors, incomplete coverage)")
    return None


def on_watch_change(watch: dict[str, Any], evidence: dict[str, Any], change_kind: str,
                    previous_payload: dict[str, Any] | None, checked_at: str) -> bool:
    """Called by external_watches after a baseline/changed observation.

    Returns True if this module owns the watch (so the generic notice is skipped)."""
    meta = get_meta(watch["id"])
    if meta is None:
        return False
    payload = evidence.get("payload") or {}
    if change_kind == "baseline":
        with _db() as conn:
            conn.execute("UPDATE watch_meta SET baseline_at=?,baseline_summary=? WHERE watch_id=?",
                         (checked_at, _baseline_summary(watch["kind"], payload), watch["id"]))
        return True
    item = _compose(meta, watch, evidence, previous_payload, checked_at)
    if item is None:
        return True
    attention.submit(item, authorize=lambda: _inactive_reason(watch["id"]))
    return True


# ------------------------------------------------------------- API helpers ---

def watches_view(now: datetime | None = None) -> dict[str, Any]:
    instant = now or _now()
    rows = _watch_rows()
    for w in rows:
        w["description"] = describe_watch(w, instant)
    return {"watches": rows, "runner": ew.runner_status()}


register("voice_watches", handle)
