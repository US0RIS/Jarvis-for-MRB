from __future__ import annotations

"""Earpiece turn router for camera-free, deterministic voice capabilities.

This is the one shared entry point the AirPods/iPhone voice path (and the
desktop text path) uses before the model planner. Each capability module
registers a handler ``(text, turn) -> str | None``; the first non-None answer
wins. Handlers must only read authorized local state or call bounded,
source-qualified providers, and they must answer "unknown" rather than invent
physical observations.

Per-turn context (session id and any phone location the iPhone chose to attach
under its own OS permission) travels in a ``contextvars`` value, so the shared
streaming and non-streaming fast paths do not need a new parameter. Follow-up
"focus" (the last object, place or topic discussed) is held in process memory
only, per session, with a short expiry. It is never persisted.
"""

import contextlib
import contextvars
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

# Phone locations older than this are treated as absent rather than current.
LOCATION_MAX_AGE_SECONDS = 15 * 60
FOCUS_TTL_SECONDS = 10 * 60


@dataclass(frozen=True)
class PhoneLocation:
    latitude: float
    longitude: float
    accuracy_m: float | None
    captured_at: datetime

    def age_seconds(self, now: datetime | None = None) -> float:
        instant = now or datetime.now(timezone.utc)
        return max(0.0, (instant - self.captured_at).total_seconds())


@dataclass
class VoiceTurn:
    session_id: str = "default"
    location: PhoneLocation | None = None
    location_note: str = ""
    channel: str = "text"
    extras: dict[str, Any] = field(default_factory=dict)


_CURRENT: contextvars.ContextVar[VoiceTurn | None] = contextvars.ContextVar(
    "horus_voice_turn", default=None
)


def _parse_location(context: dict[str, Any] | None,
                    now: datetime | None = None) -> tuple[PhoneLocation | None, str]:
    """Accept a phone fix only when it is complete, finite and recent."""
    if not context:
        return None, "no phone location was attached"
    lat, lon = context.get("latitude"), context.get("longitude")
    if lat is None or lon is None:
        return None, "no phone location was attached"
    try:
        latitude, longitude = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, "the attached phone location was malformed"
    if not (math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, "the attached phone location was out of range"
    raw_time = str(context.get("location_captured_at") or "").strip()
    if not raw_time:
        return None, "the attached phone location had no capture time"
    try:
        captured = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except ValueError:
        return None, "the attached phone location had an invalid capture time"
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    accuracy = context.get("location_accuracy_m")
    try:
        accuracy_m = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        accuracy_m = None
    if accuracy_m is not None and (not math.isfinite(accuracy_m) or accuracy_m < 0):
        accuracy_m = None
    fix = PhoneLocation(latitude, longitude, accuracy_m, captured)
    age = fix.age_seconds(now)
    if age > LOCATION_MAX_AGE_SECONDS:
        return None, f"the phone location was {int(age // 60)} minutes old"
    return fix, ""


def _make_turn(session_id: str | None, context: dict[str, Any] | None) -> VoiceTurn:
    location, note = _parse_location(context)
    channel = str((context or {}).get("channel") or "text")[:20]
    return VoiceTurn(
        session_id=(session_id or "default")[:120],
        location=location,
        location_note=note,
        channel=channel if channel in {"text", "voice", "conversation"} else "text",
    )


@contextlib.contextmanager
def turn_context(session_id: str | None, context: dict[str, Any] | None = None) -> Iterator[VoiceTurn]:
    turn = _make_turn(session_id, context)
    token = _CURRENT.set(turn)
    try:
        yield turn
    finally:
        _CURRENT.reset(token)


def current_turn() -> VoiceTurn:
    return _CURRENT.get() or VoiceTurn()


# --------------------------------------------------------------------------
# Follow-up focus: in-memory, per session, expiring.

_FOCUS: dict[tuple[str, str], tuple[float, Any]] = {}
_FOCUS_LOCK = threading.Lock()


def set_focus(key: str, value: Any, *, session_id: str | None = None,
              ttl_seconds: int = FOCUS_TTL_SECONDS) -> None:
    sid = session_id or current_turn().session_id
    with _FOCUS_LOCK:
        _FOCUS[(sid, key)] = (time.monotonic() + max(1, ttl_seconds), value)
        if len(_FOCUS) > 2000:
            now = time.monotonic()
            for stale in [k for k, (exp, _) in _FOCUS.items() if exp <= now]:
                _FOCUS.pop(stale, None)


def get_focus(key: str, *, session_id: str | None = None) -> Any:
    sid = session_id or current_turn().session_id
    with _FOCUS_LOCK:
        item = _FOCUS.get((sid, key))
        if item is None:
            return None
        if item[0] <= time.monotonic():
            _FOCUS.pop((sid, key), None)
            return None
        return item[1]


def clear_focus(*, session_id: str | None = None) -> None:
    sid = session_id or current_turn().session_id
    with _FOCUS_LOCK:
        for key in [k for k in _FOCUS if k[0] == sid]:
            _FOCUS.pop(key, None)


# --------------------------------------------------------------------------
# Handler registry.

Handler = Callable[[str, VoiceTurn], "str | None"]
_HANDLERS: list[tuple[str, Handler]] = []


def register(family: str, handler: Handler) -> None:
    if any(name == family for name, _ in _HANDLERS):
        return
    _HANDLERS.append((family, handler))


def _load_handlers() -> None:
    # Imports register their handlers. A failed optional module must never
    # break ordinary voice commands, so each import is isolated.
    for module in (
        "jarvis_mrb.object_memory",
        "jarvis_mrb.saved_places",
        "jarvis_mrb.situational_voice",
        "jarvis_mrb.voice_watches",
        "jarvis_mrb.proactive_briefing",
        "jarvis_mrb.conversation_refine",
        "jarvis_mrb.belief_gap",
    ):
        try:
            __import__(module)
        except Exception:
            continue


_LOADED = False
_OBSERVERS: list[tuple[str, Handler]] = []


def register_observer(family: str, observer: Handler) -> None:
    """An observer may add a short spoken preface to *any* turn (e.g. a
    belief-gap warning) without taking over the user's actual request."""
    if any(name == family for name, _ in _OBSERVERS):
        return
    _OBSERVERS.append((family, observer))


def _ensure_loaded() -> None:
    global _LOADED
    if not _LOADED:
        _load_handlers()
        _LOADED = True


def observe(text: str) -> str:
    _ensure_loaded()
    stripped = " ".join(str(text or "").split())
    if not stripped:
        return ""
    turn = current_turn()
    prefaces = []
    for _family, observer in list(_OBSERVERS):
        try:
            preface = observer(stripped, turn)
        except Exception:
            continue
        if preface:
            prefaces.append(preface)
    return " ".join(prefaces)


def route(text: str) -> tuple[str, str] | None:
    _ensure_loaded()
    stripped = " ".join(str(text or "").split())
    if not stripped:
        return None
    turn = current_turn()
    for family, handler in list(_HANDLERS):
        try:
            answer = handler(stripped, turn)
        except Exception as exc:
            return family, f"That {family.replace('_', ' ')} request failed: {type(exc).__name__}."
        if answer is not None:
            return family, answer
    return None


def bound_stream(session_id: str | None, context: dict[str, Any] | None,
                 factory: Callable[[], Iterator[str]]) -> Iterator[str]:
    """Run a streaming generator with the turn context bound on every step.

    Starlette may advance a sync generator from different worker threads, each
    with a fresh copy of the request context, so a value set on one step would
    not reliably survive to the next. A dedicated Context keeps it stable.
    """
    ctx = contextvars.copy_context()
    ctx.run(_CURRENT.set, _make_turn(session_id, context))
    inner = ctx.run(factory)
    while True:
        try:
            piece = ctx.run(next, inner)
        except StopIteration:
            return
        yield piece
