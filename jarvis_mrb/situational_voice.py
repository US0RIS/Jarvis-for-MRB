from __future__ import annotations

"""Spoken, source-qualified situational awareness without a camera.

"Anything interesting happening around me?" resolves the place only from a
named saved place or the iPhone's fresh, permitted location fix, picks the
nonvisual sources that fit the question, queries them concurrently (with a
short per-area cache so repeated questions don't re-hit providers), and
answers in one or two spoken sentences that lead with what is new or
notable, then say what was NOT covered. Every unreachable source is named;
an outage is never an all-clear.

Sources (all existing adapters): NWS point alerts + Open-Meteo modelled air
quality (``physical_conditions``), USGS earthquakes (``public_incidents``),
regional OpenSky aircraft counts (``public_airspace``), community-mapped
facilities (``public_facilities``, only when asked what's nearby), plus the
user's own calendar and active watches for "before I leave".

For "what's changed since I was here?" Horus keeps a coarse (~1 km cell)
signature of each answer it gave for 30 days: alert ids, quake ids, AQI band
and aircraft count only. "Forget my place history" deletes it.
"""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from jarvis_mrb.saved_places import ResolvedPlace, resolve_place
from jarvis_mrb.voice_router import VoiceTurn, get_focus, register, set_focus

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "situational_snapshots.sqlite3"
SNAPSHOT_RETENTION = timedelta(days=30)
CACHE_SECONDS = {"conditions": 600, "quakes": 600, "airspace": 120, "facilities": 1800}
NOTABLE_QUAKE_MAGNITUDE = 4.0
NOTABLE_AQI = 101
NOTABLE_UV = 8

_LOCK = threading.RLock()
_CACHE: dict[tuple[str, float, float], tuple[float, dict[str, Any]]] = {}


def _conditions(lat: float, lon: float) -> dict[str, Any]:
    from jarvis_mrb.physical_conditions import physical_conditions
    return physical_conditions(lat, lon)


def _quakes(lat: float, lon: float) -> dict[str, Any]:
    from jarvis_mrb.public_incidents import regional_earthquakes
    return regional_earthquakes(lat, lon)


def _airspace(lat: float, lon: float) -> dict[str, Any]:
    from jarvis_mrb.public_airspace import airspace_region
    return airspace_region(lat, lon, radius_km=20)


def _facilities(lat: float, lon: float) -> dict[str, Any]:
    from jarvis_mrb.public_facilities import nearby_mapped_facilities
    return nearby_mapped_facilities(lat, lon)


PROVIDERS: dict[str, Callable[[float, float], dict[str, Any]]] = {
    "conditions": _conditions,
    "quakes": _quakes,
    "airspace": _airspace,
    "facilities": _facilities,
}


def _has_data(source: str, result: dict[str, Any]) -> bool:
    if source == "conditions":
        return any((result.get(part) or {}).get("status") in {"ok", "partial", "stale"}
                   for part in ("air_quality", "weather_alerts"))
    return result.get("status") in {"ok", "partial", "stale", "unsupported_region"}


def _fetch(source: str, place: ResolvedPlace) -> dict[str, Any]:
    key = (source, round(place.latitude, 2), round(place.longitude, 2))
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and hit[0] > now:
            return {**hit[1], "_cached": True}
    try:
        result = PROVIDERS[source](place.latitude, place.longitude)
    except Exception as exc:
        result = {"status": "unavailable", "source_note": f"{source} failed: {type(exc).__name__}"}
    # Cache only answers that carry data; an outage is retried on the next question.
    if _has_data(source, result):
        with _LOCK:
            _CACHE[key] = (now + CACHE_SECONDS.get(source, 300), result)
    return result


def gather(place: ResolvedPlace, sources: list[str]) -> dict[str, dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        futures = {s: pool.submit(_fetch, s, place) for s in sources}
        return {s: f.result() for s, f in futures.items()}


# --------------------------------------------------------------------------
# Snapshots for "what's changed since I was here?"

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
        """CREATE TABLE IF NOT EXISTS snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cell TEXT NOT NULL,
            label TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            signature_json TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snap_cell ON snapshots(cell, id DESC)")
    conn.commit()
    return conn


def _cell(place: ResolvedPlace) -> str:
    return f"{round(place.latitude, 2):.2f},{round(place.longitude, 2):.2f}"


def _signature(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sig: dict[str, Any] = {}
    cond = results.get("conditions")
    if cond:
        alerts = cond.get("weather_alerts") or {}
        if alerts.get("status") in {"ok", "partial"}:
            sig["alerts"] = {a["id"]: a.get("event", "") for a in alerts.get("alerts") or [] if a.get("id")}
        air = cond.get("air_quality") or {}
        if air.get("status") == "ok" and air.get("us_aqi") is not None:
            sig["aqi"] = round(float(air["us_aqi"]))
    quakes = results.get("quakes")
    if quakes and quakes.get("status") in {"ok", "partial"}:
        sig["quakes"] = {q["id"]: q.get("magnitude") for q in quakes.get("events") or []}
    air = results.get("airspace")
    if air and air.get("status") == "ok":
        sig["aircraft"] = air.get("aircraft_count")
    return sig


def _previous_snapshot(place: ResolvedPlace, *, before: datetime | None = None) -> dict[str, Any] | None:
    cutoff = (before or datetime.now(timezone.utc)) - timedelta(minutes=30)
    with _LOCK, _open() as conn:
        row = conn.execute(
            "SELECT * FROM snapshots WHERE cell=? AND checked_at<=? ORDER BY id DESC LIMIT 1",
            (_cell(place), cutoff.isoformat()),
        ).fetchone()
    if not row:
        return None
    return {"checked_at": row["checked_at"], "signature": json.loads(row["signature_json"])}


def _latest_snapshot(place: ResolvedPlace) -> dict[str, Any] | None:
    with _LOCK, _open() as conn:
        row = conn.execute(
            "SELECT * FROM snapshots WHERE cell=? ORDER BY id DESC LIMIT 1", (_cell(place),)
        ).fetchone()
    return {"checked_at": row["checked_at"], "signature": json.loads(row["signature_json"])} if row else None


def _store_snapshot(place: ResolvedPlace, signature: dict[str, Any]) -> None:
    if not signature:
        return
    now = datetime.now(timezone.utc)
    with _LOCK, _open() as conn:
        conn.execute(
            "INSERT INTO snapshots(cell,label,checked_at,signature_json) VALUES(?,?,?,?)",
            (_cell(place), place.label[:40], now.isoformat(), json.dumps(signature, sort_keys=True)),
        )
        conn.execute("DELETE FROM snapshots WHERE checked_at<?", ((now - SNAPSHOT_RETENTION).isoformat(),))
        conn.commit()


def forget_history() -> int:
    with _LOCK, _open() as conn:
        count = conn.execute("DELETE FROM snapshots").rowcount
        conn.commit()
    return int(count)


# --------------------------------------------------------------------------
# Composition

def _ago(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    minutes = int((datetime.now(timezone.utc) - moment).total_seconds() // 60)
    if minutes < 2:
        return "just now"
    if minutes < 90:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 36:
        return f"{hours} hours ago"
    return f"{hours // 24} days ago"


def _where(place: ResolvedPlace) -> str:
    return "near home" if place.label == "home" else (
        "around you" if place.provenance == "phone_fix" else f"near {place.label}")


def _findings(results: dict[str, dict[str, Any]], previous: dict[str, Any] | None,
              *, include_airspace: bool) -> tuple[list[tuple[int, str]], list[str], list[str], list[dict[str, Any]]]:
    """Return (scored findings, quiet facts, gaps, evidence)."""
    findings: list[tuple[int, str]] = []
    quiet: list[str] = []
    gaps: list[str] = []
    evidence: list[dict[str, Any]] = []
    old = (previous or {}).get("signature") or {}

    cond = results.get("conditions")
    if cond is not None:
        alerts = cond.get("weather_alerts") or {}
        status = alerts.get("status")
        if status in {"ok", "partial"}:
            items = list(alerts.get("alerts") or [])
            evidence.append({"source": "NWS point alerts", "url": alerts.get("source_url"),
                             "checked_at": alerts.get("checked_at"), "count": len(items)})
            seen_before = set((old.get("alerts") or {}).keys())
            for alert in items[:3]:
                new = previous is not None and alert.get("id") not in seen_before
                severity = str(alert.get("severity") or "")
                score = {"Extreme": 100, "Severe": 90, "Moderate": 70}.get(severity, 55) + (10 if new else 0)
                label = alert.get("event") or "weather alert"
                findings.append((score, ("New: " if new else "") + f"the National Weather Service has a {label} in effect"))
            if not items:
                quiet.append("no NWS weather alerts")
            if status == "partial":
                gaps.append("the NWS alert list may be incomplete")
        elif status == "unsupported_region":
            gaps.append("official weather alerts aren't integrated for this region")
        else:
            gaps.append("I couldn't reach the National Weather Service")
        air = cond.get("air_quality") or {}
        if air.get("status") == "ok" and air.get("us_aqi") is not None:
            aqi = round(float(air["us_aqi"]))
            evidence.append({"source": "Open-Meteo/CAMS modelled air quality", "url": air.get("source_url"),
                             "model_time": air.get("model_time_utc"), "us_aqi": aqi})
            if aqi >= NOTABLE_AQI:
                findings.append((75 if aqi >= 151 else 60, f"modelled air quality is poor, AQI {aqi}"))
            else:
                quiet.append(f"air quality {'good' if aqi <= 50 else 'moderate'} at AQI {aqi}")
            uv = air.get("uv_index")
            if uv is not None and float(uv) >= NOTABLE_UV:
                findings.append((40, f"UV index is {round(float(uv))}"))
        elif air.get("status") == "stale":
            gaps.append("the air-quality model is stale")
        else:
            gaps.append("air quality is unavailable")

    quakes = results.get("quakes")
    if quakes is not None:
        if quakes.get("status") in {"ok", "partial"}:
            events = list(quakes.get("events") or [])
            evidence.append({"source": "USGS earthquakes (100 km, 24 h, M2.5+)", "url": quakes.get("source_url"),
                             "checked_at": quakes.get("checked_at"), "count": len(events)})
            seen_before = set((old.get("quakes") or {}).keys())
            notable = sorted(events, key=lambda e: -(e.get("magnitude") or 0))
            if notable and (notable[0].get("magnitude") or 0) >= NOTABLE_QUAKE_MAGNITUDE:
                q = notable[0]
                new = previous is not None and q["id"] not in seen_before
                findings.append((80 + (10 if new else 0),
                                 ("New: " if new else "") + f"a magnitude {q['magnitude']} earthquake, {q.get('place')}, {_ago(q.get('occurred_at'))}"))
            elif events:
                findings.append((20, f"{len(events)} small earthquake{'s' if len(events) != 1 else ''} within 100 kilometers today, none above magnitude {NOTABLE_QUAKE_MAGNITUDE:g}"))
            else:
                quiet.append("no earthquakes nearby in the last day")
        else:
            gaps.append("I couldn't reach USGS")

    airspace = results.get("airspace")
    if airspace is not None:
        if airspace.get("status") == "ok" and airspace.get("aircraft_count") is not None:
            count = int(airspace["aircraft_count"])
            evidence.append({"source": "OpenSky regional state vectors (20 km)", "url": airspace.get("source_url"),
                             "states_at": airspace.get("states_at"), "aircraft_count": count})
            before = old.get("aircraft")
            change = ""
            if previous is not None and isinstance(before, int):
                change = f", compared with {before} when you last asked"
            if include_airspace:
                findings.append((50, f"OpenSky reports {count} airborne aircraft within about 20 kilometers{change}. "
                                     "Coverage is incomplete and I don't identify flights"))
        elif airspace.get("status") == "stale":
            gaps.append("OpenSky's aircraft data is stale")
        else:
            gaps.append("I couldn't reach OpenSky for aircraft")

    facilities = results.get("facilities")
    if facilities is not None:
        if facilities.get("status") == "ok":
            listed = facilities.get("facilities") or []
            kinds: dict[str, int] = {}
            for item in listed:
                kind = str(item.get("category") or item.get("kind") or "place").replace("_", " ")
                kinds[kind] = kinds.get(kind, 0) + 1
            top = sorted(kinds.items(), key=lambda kv: -kv[1])[:3]
            evidence.append({"source": "OpenStreetMap community mapping", "url": facilities.get("source_url"),
                             "count": len(listed)})
            if top:
                findings.append((30, "mapped nearby: " + ", ".join(f"{n} {k}" for k, n in top)))
        else:
            gaps.append("public mapping is unavailable")
    return findings, quiet, gaps, evidence


def _sentence(items: list[str]) -> str:
    if not items:
        return ""
    joined = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    return joined[0].upper() + joined[1:] + "."


def compose(place: ResolvedPlace, results: dict[str, dict[str, Any]], *, intent: str,
            previous: dict[str, Any] | None, personal: list[str] | None = None) -> dict[str, Any]:
    findings, quiet, gaps, evidence = _findings(results, previous, include_airspace=(intent == "airspace"))
    reachable = [e for e in evidence]
    where = _where(place)
    if not reachable and not personal:
        spoken = (f"I couldn't reach any of my sources {where}, so I can't tell you what's happening. "
                  "That's not an all-clear.")
        return {"spoken": spoken, "evidence": evidence, "gaps": gaps, "findings": []}
    findings.sort(key=lambda f: -f[0])
    parts: list[str] = []
    if personal:
        parts.extend(personal)
    if intent == "general":
        top = [f for f in findings if f[0] >= 30][:2]
    else:
        top = findings[:3]
    if top:
        parts.append(_sentence([t for _, t in top]))
    elif intent != "airspace":
        lead = "Nothing notable " + where + " from what I checked: "
        parts.append(lead + (", ".join(quiet[:3]) if quiet else "no alerts") + ".")
    if gaps:
        parts.append(_sentence(gaps[:2]))
    if top and intent != "airspace":
        parts.append("Say 'tell me more' for details.")
    spoken = " ".join(p for p in parts if p)
    return {"spoken": spoken, "evidence": evidence, "gaps": gaps,
            "findings": [t for _, t in findings], "quiet": quiet}


def _changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if previous is None:
        return []
    old = previous["signature"]
    out: list[str] = []
    new_alerts = [v for k, v in (current.get("alerts") or {}).items() if k not in (old.get("alerts") or {})]
    ended = [v for k, v in (old.get("alerts") or {}).items() if k not in (current.get("alerts") or {})]
    if "alerts" in current and "alerts" in old:
        if new_alerts:
            out.append("new weather alert" + ("s" if len(new_alerts) > 1 else "") + ": " + ", ".join(new_alerts[:2]))
        if ended:
            out.append(", ".join(ended[:2]) + " no longer active")
    if "quakes" in current and "quakes" in old:
        fresh = [m for k, m in (current.get("quakes") or {}).items() if k not in (old.get("quakes") or {})]
        if fresh:
            out.append(f"{len(fresh)} new earthquake{'s' if len(fresh) > 1 else ''} recorded, largest magnitude {max(fresh)}")
    if "aqi" in current and "aqi" in old and abs(int(current["aqi"]) - int(old["aqi"])) >= 25:
        out.append(f"air quality went from AQI {old['aqi']} to {current['aqi']}")
    return out


def _personal_before_leaving(now: datetime | None = None) -> list[str]:
    notes: list[str] = []
    instant = now or datetime.now(timezone.utc)
    try:
        from jarvis_mrb.world_situation import _latest_calendar_events
        upcoming = []
        for item in _latest_calendar_events(limit=80):
            try:
                start = datetime.fromisoformat(str(item.get("start") or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if start.tzinfo is None:
                continue
            if instant <= start <= instant + timedelta(hours=6) and item.get("status") != "cancelled":
                upcoming.append((start, item))
        if upcoming:
            start, item = sorted(upcoming, key=lambda x: x[0])[0]
            minutes = int((start - instant).total_seconds() // 60)
            when = f"in {minutes} minutes" if minutes < 90 else "at " + start.astimezone().strftime("%I:%M %p").lstrip("0")
            where = f" at {item['location']}" if item.get("location") else ""
            notes.append(f"Your next event, {str(item.get('title') or 'untitled')[:60]}, is {when}{where} (from your synced calendar).")
    except Exception:
        pass
    try:
        from jarvis_mrb.external_watches import list_watches
        active = [w for w in list_watches("personal") if w.get("enabled")]
        if active:
            notes.append(f"You have {len(active)} active watch{'es' if len(active) > 1 else ''} running.")
    except Exception:
        pass
    return notes


# --------------------------------------------------------------------------
# Spoken interface

_AIRSPACE = re.compile(r"\b(?:airspace|aircraft|planes?|helicopters?|flights?)\b.*\b(?:around|near|over|above|overhead|here)\b|\bairspace\b")
_CHANGED = re.compile(r"\bwhat(?:'s| has| is)? (?:changed|new|different) since (?:i was|i was last|the last time i was|last time i was|i last was|my last visit)\b")
_BEFORE_LEAVING = re.compile(r"\bwhat (?:should|do) i (?:know|need to know) before (?:i )?(?:leav(?:e|ing)|head(?:ing)? out|go(?:ing)? out|i go|step(?:ping)? out)\b")
_UNUSUAL = re.compile(r"\b(?:anything|something) (?:unusual|weird|wrong|strange|going on|dangerous|i should know about)\b.*\b(?:near|around|at|by|here|nearby)\b|\bis it safe (?:to go )?(?:out|outside)\b")
_GENERAL = re.compile(
    r"\b(?:anything|what'?s|what is) (?:interesting |notable |new )?(?:happening|going on)\b.*\b(?:around|near|nearby|here|in my area)\b"
    r"|\banything interesting\b.*\b(?:around|near|nearby|here)\b|\bsituational (?:update|awareness|brief)\b"
)
_NEARBY = re.compile(r"^what'?s (?:around me|nearby|near me|around here)$")
_MORE = re.compile(r"^(?:tell me more|more detail|more details|go on|what are (?:your|the) sources|which sources|how fresh is that|where is that from|what did you check)$")
# Standing requests ("watch the airspace for two hours") belong to watches.
_DELEGATED = re.compile(r"^(?:please )?(?:watch|monitor|keep (?:an )?eye|tell me (?:if|when)|alert me|notify me|let me know (?:if|when)|warn me|cancel|stop|pause|resume)\b")
_FORGET = re.compile(r"^(?:forget|delete|clear) (?:my )?(?:place|situational|location) (?:history|snapshots)$")


def _classify(n: str) -> str | None:
    if _CHANGED.search(n):
        return "changed"
    if _BEFORE_LEAVING.search(n):
        return "before_leaving"
    if _AIRSPACE.search(n) and ("airspace" in n or re.search(r"\b(?:around|over|above|overhead|near)\b", n)):
        return "airspace"
    if _NEARBY.match(n):
        return "nearby"
    if _UNUSUAL.search(n):
        return "unusual"
    if _GENERAL.search(n):
        return "general"
    return None


SOURCES_BY_INTENT = {
    "general": ["conditions", "quakes"],
    "unusual": ["conditions", "quakes"],
    "before_leaving": ["conditions"],
    "airspace": ["airspace"],
    "changed": ["conditions", "quakes", "airspace"],
    "nearby": ["facilities", "conditions"],
}


def answer(text: str, turn: VoiceTurn) -> dict[str, Any] | None:
    n = " ".join(text.lower().replace("’", "'").split()).strip(" .!?")
    n = re.sub(r"^(?:(?:hey|ok|okay)\s+)?(?:horus|jarvis)[,:!]?\s+", "", n)
    if _DELEGATED.match(n):
        return None
    intent = _classify(n)
    if intent is None:
        return None
    place, reason = resolve_place(n, turn)
    if place is None:
        return {"spoken": reason, "evidence": [], "gaps": ["no permitted place"], "intent": intent}
    previous = _previous_snapshot(place) if intent != "changed" else _latest_snapshot(place)
    results = gather(place, SOURCES_BY_INTENT[intent])
    signature = _signature(results)
    personal = _personal_before_leaving() if intent == "before_leaving" else None
    if intent == "changed":
        if previous is None:
            composed = compose(place, results, intent="general", previous=None)
            composed["spoken"] = ("I don't have an earlier check from this area to compare with. "
                                  "Here's now: " + composed["spoken"])
        else:
            diffs = _changes(previous, signature)
            composed = compose(place, results, intent="general", previous=previous)
            since = _ago(previous["checked_at"])
            if diffs:
                composed["spoken"] = f"Since you last asked here, {since}: " + "; ".join(diffs) + "."
            elif composed["evidence"]:
                composed["spoken"] = (f"Nothing changed in the sources I can compare since {since}: "
                                      "weather alerts, earthquakes, air quality and aircraft count. "
                                      "I can't tell about anything those don't cover.")
    else:
        composed = compose(place, results, intent=intent, previous=previous, personal=personal)
    if composed["evidence"]:
        _store_snapshot(place, signature)
    composed["intent"] = intent
    composed["place"] = {"label": place.label, "provenance": place.provenance, "captured_at": place.captured_at,
                         "accuracy_m": place.accuracy_m}
    set_focus("situational.last", composed, session_id=turn.session_id)
    return composed


def _detail(last: dict[str, Any]) -> str:
    parts = []
    findings = last.get("findings") or []
    if findings:
        parts.append(_sentence(findings[:4]))
    sources = []
    for item in last.get("evidence") or []:
        when = item.get("checked_at") or item.get("model_time") or ""
        if item.get("states_at"):
            try:
                when = datetime.fromtimestamp(float(item["states_at"]), timezone.utc).isoformat()
            except (TypeError, ValueError):
                when = ""
        sources.append(item["source"] + (f", {_ago(when)}" if when else ""))
    if sources:
        parts.append("Sources: " + "; ".join(sources) + ".")
    if last.get("gaps"):
        parts.append("Not covered: " + "; ".join(last["gaps"]) + ".")
    place = last.get("place") or {}
    if place.get("provenance") == "phone_fix":
        acc = f", accurate to about {int(place['accuracy_m'])} meters" if place.get("accuracy_m") else ""
        parts.append(f"Location came from your iPhone{acc}.")
    elif place.get("provenance") == "saved_place":
        parts.append(f"Location is your saved place '{place.get('label')}'.")
    parts.append("None of this is a camera view or a safety guarantee.")
    return " ".join(parts)


def handle(text: str, turn: VoiceTurn) -> str | None:
    n = " ".join(text.lower().replace("’", "'").split()).strip(" .!?")
    if _FORGET.match(n):
        return f"Deleted {forget_history()} saved area checks."
    if _MORE.match(n):
        last = get_focus("situational.last", session_id=turn.session_id)
        return _detail(last) if last else None
    result = answer(text, turn)
    return result["spoken"] if result else None


register("situational", handle)
