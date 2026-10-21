from __future__ import annotations

"""Conversational narrowing and short spoken answers for earpiece turns.

User: "What's on my calendar tomorrow?"  Horus: "You have three events
tomorrow. The first is Standup at 9 AM, then ..."  User: "Just the
afternoon."  Horus: "Two in the afternoon: Design review at 2 PM and 1:1 at
4 PM."

The calendar read goes through the normal permission-aware ``execute_tool``
path; the follow-up only filters the events that read returned (kept in the
per-session, in-memory focus), so narrowing never invents or re-fetches data.
Spoken compaction is used for voice turns; typed turns keep the full listing.

It also catches a voice utterance that was plainly cut off ("remind me to")
and asks the user to finish it instead of guessing.
"""

import re
from datetime import datetime, time, timedelta
from typing import Any

from jarvis_mrb.voice_router import VoiceTurn, get_focus, register, set_focus

WINDOWS = {
    "morning": (time(0, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(17, 0)),
    "evening": (time(17, 0), time(23, 59, 59)),
    "tonight": (time(17, 0), time(23, 59, 59)),
}
_NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_ORDINALS = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4, "last": -1, "next": 0}
_DANGLING = {"the", "my", "a", "an", "and", "your", "our", "to"}

_NARROW = re.compile(
    r"^(?:just|only|and|what about|how about)?\s*(?:the|in the|this|for the)?\s*(morning|afternoon|evening|tonight)(?:\s+(?:ones?|events?|meetings?|please))?$"
    r"|^(?:just|only)\s+(?:the\s+)?(?:ones?|events?|meetings?)\s+in\s+the\s+(morning|afternoon|evening)$"
    r"|^(?:just|only)\s+(?:the\s+)?(morning|afternoon|evening)\s+(?:ones?|events?|meetings?)$"
)
_AFTER = re.compile(r"^(?:just|only)?\s*(?:the\s+ones?\s+)?(after|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")
_ORDINAL = re.compile(r"^(?:what(?:'s| is)|tell me (?:about|more about)|and)?\s*the\s+(first|second|third|fourth|fifth|last|next)(?:\s+(?:one|event|meeting))?$")
_DAY_SHIFT = re.compile(r"^(?:and |what about |how about )(today|tomorrow|yesterday)$")


def _parse(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.astimezone() if value.tzinfo else value


def _clock(moment: datetime) -> str:
    return moment.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")


def _count(n: int) -> str:
    return _NUMBERS[n] if n < len(_NUMBERS) else str(n)


def _spoken_events(events: list[dict[str, Any]], *, scope: str) -> str:
    timed = []
    for event in events:
        start = _parse(event.get("start") or "")
        all_day = "T" not in str(event.get("start") or "")
        timed.append((start, all_day, str(event.get("summary") or "untitled")[:60]))
    if not timed:
        return f"Nothing on your calendar {scope}."
    def item(entry: tuple[datetime | None, bool, str]) -> str:
        start, all_day, title = entry
        if all_day or start is None:
            return f"{title}, all day"
        return f"{title} at {_clock(start)}"
    noun = "event" if len(timed) == 1 else "events"
    lead = f"You have {_count(len(timed))} {noun} {scope}."
    if len(timed) == 1:
        return f"{lead} {item(timed[0])}."
    rest = [item(e) for e in timed[1:4]]
    more = f", plus {len(timed) - 4} more" if len(timed) > 4 else ""
    return f"{lead} The first is {item(timed[0])}, then " + (", ".join(rest[:-1]) + " and " + rest[-1] if len(rest) > 1 else rest[0]) + more + "."


def _scope_label(args: dict[str, Any]) -> str:
    start = _parse(str(args.get("start") or ""))
    if start is None:
        return "coming up"
    today = datetime.now().astimezone().date()
    if start.date() == today:
        return "today"
    if start.date() == today + timedelta(days=1):
        return "tomorrow"
    if start.date() == today - timedelta(days=1):
        return "yesterday"
    return "on " + start.strftime("%A")


def _run_calendar(args: dict[str, Any], turn: VoiceTurn) -> str:
    from jarvis_mrb.agent import execute_tool

    reply = execute_tool("calendar.query", dict(args))
    events = list((reply.data or {}).get("events") or []) if isinstance(reply.data, dict) else []
    if not reply.ok or not isinstance(reply.data, dict):
        return reply.message
    scope = _scope_label(args)
    set_focus("calendar.last", {"args": dict(args), "events": events, "scope": scope}, session_id=turn.session_id)
    if turn.channel in {"voice", "conversation"}:
        return _spoken_events(events, scope=scope)
    return reply.message


def _within(events: list[dict[str, Any]], lo: time, hi: time) -> list[dict[str, Any]]:
    out = []
    for event in events:
        start = _parse(event.get("start") or "")
        if start is None or "T" not in str(event.get("start") or ""):
            continue
        if lo <= start.time() < hi:
            out.append(event)
    return out


def handle(text: str, turn: VoiceTurn) -> str | None:
    n = " ".join(text.lower().replace("’", "'").split()).strip(" .!?,")
    n = re.sub(r"^(?:(?:hey|ok|okay)\s+)?(?:horus|jarvis)[,:!]?\s+", "", n)
    if not n:
        return None

    last = get_focus("calendar.last", session_id=turn.session_id)
    if last:
        m = _NARROW.match(n)
        if m:
            window = next(g for g in m.groups() if g)
            lo, hi = WINDOWS[window]
            hits = _within(last["events"], lo, hi)
            label = "tonight" if window == "tonight" else f"in the {window}"
            set_focus("calendar.last", {**last, "events": hits, "scope": f"{last['scope']} {label}"},
                      session_id=turn.session_id)
            if not hits:
                return f"Nothing {label}."
            items = [f"{str(e.get('summary') or 'untitled')[:60]} at {_clock(_parse(e['start']))}" for e in hits[:4]]
            joined = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
            return f"{_count(len(hits)).capitalize()} {label}: {joined}."
        m = _AFTER.match(n)
        if m:
            hour = int(m.group(2)) % 12 + (12 if (m.group(4) == "pm" or (not m.group(4) and int(m.group(2)) < 8)) else 0)
            pivot = time(min(hour, 23), int(m.group(3) or 0))
            hits = _within(last["events"], pivot, time(23, 59, 59)) if m.group(1) == "after" else _within(last["events"], time(0, 0), pivot)
            if not hits:
                return f"Nothing {m.group(1)} {_clock(datetime.combine(datetime.now().date(), pivot))}."
            items = [f"{str(e.get('summary') or 'untitled')[:60]} at {_clock(_parse(e['start']))}" for e in hits[:4]]
            return f"{_count(len(hits)).capitalize()}: " + ", ".join(items) + "."
        m = _ORDINAL.match(n)
        if m and last["events"]:
            index = _ORDINALS[m.group(1)]
            if index >= len(last["events"]):
                return f"There are only {_count(len(last['events']))}."
            event = last["events"][index]
            start = _parse(event.get("start") or "")
            when = _clock(start) if start and "T" in str(event.get("start")) else "all day"
            where = f", at {event['location']}" if event.get("location") else ""
            return f"{event.get('summary') or 'Untitled'}, {when}{where}."
        m = _DAY_SHIFT.match(n)
        if m:
            from jarvis_mrb.deterministic_dispatch import _calendar_day
            route = _calendar_day(m.group(1), datetime.now().astimezone())
            return _run_calendar(dict(route.args), turn)

    # A fresh calendar-day question: route exactly as the model-free dispatcher
    # would, but remember the result so follow-ups can narrow it.
    from jarvis_mrb.deterministic_dispatch import dispatch
    route = dispatch(text)
    if route is not None and route.tool == "calendar.query" and route.family in {"calendar.day", "calendar.week"}:
        return _run_calendar(dict(route.args), turn)

    if turn.channel in {"voice", "conversation"}:
        words = n.split()
        if 1 < len(words) <= 8 and words[-1] in _DANGLING:
            return "Sorry, I think you got cut off. Go ahead and finish."
    return None


register("conversation_refine", handle)
