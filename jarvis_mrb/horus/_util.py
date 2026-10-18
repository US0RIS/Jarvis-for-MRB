"""Small shared helpers for the HORUS primitive library.

Everything in ``jarvis_mrb.horus`` is stdlib-only and deterministic: callers pass
``now`` explicitly where time matters so behaviour is reproducible in tests and
replays.  Persistence is the caller's job; every stateful object can round-trip
through ``to_dict``/``from_dict`` (plain JSON types).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

UTC = timezone.utc

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
STOPWORDS = frozenset(
    "a an and are as at be been but by for from has have i in is it its me my of on or our "
    "so that the their them then there these this to was we were what when where which who "
    "will with you your".split()
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_dt(value: datetime | str | float | int | None, default: datetime | None = None) -> datetime:
    """Coerce ISO strings / epoch seconds / naive datetimes into aware UTC datetimes."""
    if value is None:
        if default is None:
            return utcnow()
        return default
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def iso(value: datetime | None) -> str | None:
    return None if value is None else as_dt(value).isoformat()


def minutes(n: float) -> timedelta:
    return timedelta(minutes=n)


def stable_id(*parts: object, length: int = 16) -> str:
    raw = "\n".join(json.dumps(p, sort_keys=True, default=str) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def tokens(text: str, *, drop_stopwords: bool = True) -> list[str]:
    words = _WORD.findall(str(text or "").lower())
    if drop_stopwords:
        words = [w for w in words if w not in STOPWORDS]
    return words


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("median of empty sequence")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def mad(values: list[float]) -> float:
    m = median(values)
    return median([abs(v - m) for v in values])


def plain(value: Any) -> Any:
    """Convert dataclasses/datetimes/sets into JSON-compatible structures."""
    from dataclasses import asdict, is_dataclass

    if is_dataclass(value) and not isinstance(value, type):
        return plain(asdict(value))
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(plain(v) for v in value)
    return value
