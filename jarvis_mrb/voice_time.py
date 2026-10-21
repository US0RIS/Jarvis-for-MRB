from __future__ import annotations

"""Small, deterministic spoken-time helpers shared by voice watches and briefings.

Everything here takes an explicit ``now`` so behavior is testable, and returns
``None`` rather than guessing when an utterance is not understood.
"""

import re
from datetime import datetime, timedelta, timezone

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
}
_NUM = r"(?:\d+(?:\.\d+)?|" + "|".join(sorted(_ONES, key=len, reverse=True)) + r"|an?|couple of|couple|few)"
_UNIT = r"(?P<unit>minutes?|mins?|hours?|hrs?|days?)"
_DURATION = re.compile(
    r"\b(?:for\s+)?(?:the\s+)?(?:next\s+|another\s+|about\s+)?(?P<n>" + _NUM + r")\s+" + _UNIT + r"\b"
)
_HALF = re.compile(r"\b(?:half an hour|half hour|30 minutes)\b")
_HOUR_HALF = re.compile(r"\b(?:an?|one) and a half hours?\b|\bhour and a half\b")


def _quantity(token: str) -> float | None:
    token = token.strip().lower()
    if token in {"a", "an"}:
        return 1.0
    if token in {"couple", "couple of"}:
        return 2.0
    if token == "few":
        return 3.0
    if token in _ONES:
        return float(_ONES[token])
    try:
        return float(token)
    except ValueError:
        return None


def parse_duration_seconds(text: str) -> int | None:
    """'for the next three hours' -> 10800. None if no duration was spoken."""
    lowered = " ".join(str(text or "").lower().split())
    if _HOUR_HALF.search(lowered):
        return 5400
    if _HALF.search(lowered):
        return 1800
    match = _DURATION.search(lowered)
    if not match:
        return None
    amount = _quantity(match.group("n"))
    if amount is None or amount <= 0:
        return None
    unit = match.group("unit")
    per = 60 if unit.startswith("min") else 3600 if unit.startswith(("hour", "hr")) else 86400
    return int(amount * per)


_CLOCK = re.compile(
    r"\b(?:until|till|til|by)\s+(?:about\s+|around\s+)?"
    r"(?P<h>\d{1,2}|" + "|".join(k for k, v in _ONES.items() if 1 <= v <= 12) + r")"
    r"(?:[:.\s]?(?P<m>[0-5]\d))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)?(?=\s|$|[,.?!])"
)


def _hour_value(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return _ONES.get(token)


def parse_until(text: str, now: datetime) -> datetime | None:
    """'until 6', 'until 6:30 pm', 'until noon', 'tonight', 'overnight'.

    Returns an aware local datetime strictly after ``now`` or None. A bare
    hour such as "until 6" resolves to the next 6 o'clock, AM or PM."""
    lowered = " ".join(str(text or "").lower().split())
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    base = now.replace(second=0, microsecond=0)

    def at(hour: int, minute: int = 0, *, day_offset: int = 0) -> datetime:
        return base.replace(hour=hour, minute=minute) + timedelta(days=day_offset)

    if re.search(r"\b(?:until|till|til)\s+noon\b", lowered):
        c = at(12)
        return c if c > now else c + timedelta(days=1)
    if re.search(r"\b(?:until|till|til)\s+midnight\b", lowered):
        c = at(0, day_offset=1)
        return c
    m = _CLOCK.search(lowered)
    if m:
        hour = _hour_value(m.group("h"))
        if hour is None or not 0 <= hour <= 23:
            return None
        minute = int(m.group("m") or 0)
        ap = (m.group("ap") or "").replace(".", "")
        if ap:
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if ap == "pm" else 0)
            c = at(hour, minute)
            return c if c > now else c + timedelta(days=1)
        if hour >= 13 or hour == 0:
            c = at(hour, minute)
            return c if c > now else c + timedelta(days=1)
        # Ambiguous 1..12: the soonest upcoming occurrence, AM or PM.
        options = [at(hour % 12, minute), at(hour % 12 + 12, minute)]
        options += [o + timedelta(days=1) for o in options]
        return min(o for o in options if o > now)
    if re.search(r"\b(?:until|till|til)\s+(?:the\s+)?morning\b|\bovernight\b", lowered):
        c = at(7)
        return c if c > now else c + timedelta(days=1)
    if re.search(r"\btonight\b", lowered):
        c = at(6)
        return c if c > now else c + timedelta(days=1)
    if re.search(r"\b(?:for the rest of (?:the|today)|for the rest of the day|until the end of the day)\b", lowered):
        c = at(23, 59)
        return c if c > now else None
    return None


def clock_words(value: datetime) -> str:
    """'6:00 PM' (local time of the value's own tzinfo)."""
    hour12 = value.hour % 12 or 12
    return f"{hour12}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


def span_words(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return "under two minutes" if seconds >= 60 else "under a minute"
    if seconds < 5400:
        minutes = round(seconds / 60)
        return f"{minutes} minutes"
    if seconds < 172800:
        hours = seconds / 3600
        whole = round(hours)
        if abs(hours - whole) < 0.1:
            return "1 hour" if whole == 1 else f"{whole} hours"
        return f"{hours:.1f} hours"
    return f"{round(seconds / 86400)} days"


_SMALL = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
          "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
          "seventeen", "eighteen", "nineteen"]
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty"}


def number_words(n: int) -> str:
    if 0 <= n < 20:
        return _SMALL[n]
    if n in _TENS:
        return _TENS[n]
    if 20 < n < 60:
        return _TENS[n // 10 * 10] + " " + _SMALL[n % 10]
    return str(n)


def local_clock(iso: str | None) -> str:
    """Format an ISO timestamp as local clock time, or 'an unknown time'."""
    text = str(iso or "").strip()
    if not text:
        return "an unknown time"
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:  # epoch seconds (e.g. OpenSky state time)
            value = datetime.fromtimestamp(float(text), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return "an unknown time"
    if value.tzinfo is None:
        return clock_words(value)
    return clock_words(value.astimezone())


def when_words(value: datetime, now: datetime) -> str:
    """'6:00 PM', 'tomorrow at 6:00 AM' or 'Friday at 6:00 PM' in local time."""
    local, today = value.astimezone(), now.astimezone()
    clock = clock_words(local)
    days = (local.date() - today.date()).days
    if days <= 0:
        return clock
    if days == 1:
        return "tomorrow at " + clock
    return local.strftime("%A") + " at " + clock
