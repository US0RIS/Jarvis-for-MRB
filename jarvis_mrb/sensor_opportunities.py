from __future__ import annotations

"""Camera-independent ambient opportunity matching.

Opt-in, metadata-only iPhone microphone/motion/location signals are matched
against explicit standing user reminder goals. No microphone stream, transcript,
raw GPS trail, or biometrics are stored here. No tool may execute from a
classifier output. Weather is separately identified as MODELLED public data,
never misrepresented as temperature measured by glasses or the iPhone.
"""

from datetime import datetime, timezone
import math
import re
import threading
import time
from typing import Any

import httpx

_LOCK = threading.RLock()
# Ephemeral per-phone baselines, reset on backend restart or revocation.
_LIVE: dict[str, dict[str, Any]] = {}
_NEXT_WEATHER: dict[str, float] = {}

_HOME = re.compile(
    r"^remind me to (.{3,120}?) when i (get home|come home|arrive home|leave home)$",
    re.IGNORECASE,
)
_DOORBELL = re.compile(
    r"^remind me to (.{3,120}?) when (?:the |my )?doorbell rings$",
    re.IGNORECASE,
)
_WEATHER = re.compile(
    r"^remind me to (.{3,120}?) when (?:it's|it is) (cold|hot)(?: outside)?$",
    re.IGNORECASE,
)
_INVALID_REMINDER = re.compile(r"\b(?:and then|after that|automatically|without asking)\b", re.IGNORECASE)
_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def _parsed_time(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _fresh(value: Any, now: datetime, max_age: int) -> bool:
    stamp = _parsed_time(value)
    if stamp is None:
        return False
    age = (now - stamp).total_seconds()
    return -15 <= age <= max_age


def _number(value: Any, lower: float, upper: float) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) and lower <= number <= upper else None
    except (ValueError, TypeError, OverflowError):
        return None


def _reminders() -> list[dict[str, str]]:
    from jarvis_mrb.world_executive import active_intentions

    result: list[dict[str, str]] = []
    for item in active_intentions(limit=30):
        if not isinstance(item, dict):
            continue
        try:
            if float(item.get("confidence", 0)) < 0.7:
                continue
        except (TypeError, ValueError):
            continue
        title = " ".join(str(item.get("title") or "").split()).rstrip(".!?")
        if len(title) > 180 or not item.get("id"):
            continue
        for kind, pattern in (("home", _HOME), ("doorbell", _DOORBELL), ("weather", _WEATHER)):
            match = pattern.fullmatch(title)
            if match and not _INVALID_REMINDER.search(match.group(1)):
                result.append({
                    "id": str(item["id"]),
                    "kind": kind,
                    "task": match.group(1).strip(),
                    "condition": str(match.group(2)).lower() if match.lastindex and match.lastindex > 1 else "",
                })
                break
    return result


def _emit(goal: dict[str, str], trigger: str, message: str, *, confidence: float, severity: str = "warning") -> dict[str, Any]:
    # The only authority here is to advise. Agency Attention persists a
    # deduplicated message; it cannot execute a tool or approve a pending plan.
    from jarvis_mrb.agency_attention import consider
    return consider(
        kind="ambient_goal_opportunity",
        desired_state_id=goal["id"],
        dedup_key=f"ambient:{goal['id']}:{trigger}",
        message=message,
        benefit=95,
        urgency=38,
        confidence=min(confidence, 0.90),
        error_cost=5,
        attention_cost=10,
        threshold=55,
        severity=severity,
        dedup_seconds=6 * 3600,
    )


def ingest(snapshot: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Consume an already-authenticated companion snapshot.

    A current observation establishes a baseline; only a subsequent state
    transition fires a home reminder. Replayed sound timestamps do not refire.
    Nothing is persisted from the input payload, and a disabled snapshot
    revokes the phone's in-memory baseline.
    """
    if not isinstance(snapshot, dict):
        return []
    source = str(snapshot.get("source_id") or "iphone")[:100]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", source):
        return []
    with _LOCK:
        if snapshot.get("enabled") is not True:
            _LIVE.pop(source, None)
            _NEXT_WEATHER.pop(source, None)
            return []
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None or not _fresh(snapshot.get("observed_at"), instant, 90):
        return []

    motion = snapshot.get("motion") if isinstance(snapshot.get("motion"), dict) else {}
    activity = str(motion.get("activity") or "").lower()
    audio = snapshot.get("audio") if isinstance(snapshot.get("audio"), dict) else {}
    if activity == "driving" or audio.get("conversation_active") is True:
        # Still update the baseline, but do not speak over the user/driving.
        quiet = True
    else:
        quiet = False

    geo = snapshot.get("location") if isinstance(snapshot.get("location"), dict) else {}
    coordinates = None
    lat = _number(geo.get("latitude"), -90, 90)
    lon = _number(geo.get("longitude"), -180, 180)
    if lat is not None and lon is not None and _fresh(geo.get("observed_at"), instant, 120):
        coordinates = (round(lat, 3), round(lon, 3))

    home = str(geo.get("home_state") or "")
    if home not in {"home", "away"} or not _fresh(geo.get("home_observed_at"), instant, 300):
        home = ""
    sound = snapshot.get("sound") if isinstance(snapshot.get("sound"), dict) else {}
    sound_id = str(sound.get("identifier") or "").lower().replace("-", "_").replace(" ", "_")
    is_bell = sound_id in {"doorbell", "door_bell"} and _fresh(sound.get("observed_at"), instant, 12)
    sound_confidence = _number(sound.get("confidence"), 0, 1) or 0.0
    sound_timestamp = str(sound.get("observed_at") or "") if is_bell and sound_confidence >= 0.85 else ""

    with _LOCK:
        previous = _LIVE.get(source, {})
        previous_home = previous.get("home_state")
        previous_sound = previous.get("last_sound")
        if not home:
            # Never infer an arrival/departure from missing or stale GPS.
            previous_home = None
        _LIVE[source] = {
            "updated_at": instant,
            "home_state": home or None,
            "last_sound": sound_timestamp or previous_sound,
            "coordinates": coordinates,
            "weather_opt_in": snapshot.get("weather_opt_in") is True,
            "quiet": quiet,
        }
        # Inactive/disconnected phones must not retain GPS in RAM indefinitely.
        for key, value in list(_LIVE.items()):
            if (instant - value["updated_at"]).total_seconds() > 300:
                _LIVE.pop(key, None)
                _NEXT_WEATHER.pop(key, None)

    if quiet:
        return []

    results: list[dict[str, Any]] = []
    for goal in _reminders():
        if goal["kind"] == "home" and previous_home and home and previous_home != home:
            condition = goal["condition"]
            arriving = condition in {"get home", "come home", "arrive home"}
            if (home == "home") == arriving:
                message = f"You asked me to remind you to {goal['task']} when you {'get' if arriving else 'leave'} home. The phone's geofence has just changed."
                results.append(_emit(goal, f"home:{home}", message, confidence=0.95))
        elif goal["kind"] == "doorbell" and sound_timestamp and sound_timestamp != previous_sound:
            message = f"The iPhone sound classifier may have heard a doorbell. You asked me to remind you to {goal['task']} when it rings."
            results.append(_emit(goal, f"doorbell:{goal['task']}", message, confidence=sound_confidence))
    return results


def check_weather(*, now: datetime | None = None, client: Any = None) -> list[dict[str, Any]]:
    """Bounded, source-attributed weather observation from a current opt-in GPS fix.

    Runs in the existing monitor, not the iPhone WebSocket receive path.
    Does not persist location, infer ambient temperature from device heat,
    or silently treat a provider outage as benign.
    """
    instant = now or datetime.now(timezone.utc)
    with _LOCK:
        sources = [
            (key, value["coordinates"]) for key, value in _LIVE.items()
            if value.get("weather_opt_in") and value.get("coordinates")
            and not value.get("quiet")
            and (instant - value["updated_at"]).total_seconds() <= 120
            and time.monotonic() >= _NEXT_WEATHER.get(key, 0)
        ]
        for key, _ in sources:
            _NEXT_WEATHER[key] = time.monotonic() + 900
    goals = [g for g in _reminders() if g["kind"] == "weather"]
    if not goals:
        return []
    result: list[dict[str, Any]] = []
    for _source, (lat, lon) in sources[:2]:
        try:
            if client is None:
                with httpx.Client(timeout=httpx.Timeout(7.0), follow_redirects=False) as session:
                    response = session.get(
                        _WEATHER_URL,
                        params={"latitude": lat, "longitude": lon,
                                "current": "temperature_2m", "timezone": "GMT",
                                "forecast_days": 1},
                    )
            else:
                response = client.get(
                    _WEATHER_URL,
                    params={"latitude": lat, "longitude": lon,
                            "current": "temperature_2m", "timezone": "GMT",
                            "forecast_days": 1},
                )
            response.raise_for_status()
            data = response.json()
            current = data.get("current") if isinstance(data, dict) else None
            if not isinstance(current, dict):
                continue
            temp = _number(current.get("temperature_2m"), -90, 65)
            source_time = str(current.get("time") or "")
            if temp is None or not _fresh(source_time + "+00:00", instant, 3600):
                continue
            for goal in goals:
                cold = goal["condition"] == "cold"
                if (cold and temp > 12.0) or (not cold and temp < 30.0):
                    continue
                message = (
                    f"You asked me to remind you to {goal['task']} when it's {goal['condition']}. "
                    f"Open-Meteo's current modelled outdoor temperature is {temp:.1f}°C "
                    f"(model time {source_time} UTC), not a measurement from your glasses."
                )
                result.append(_emit(goal, f"weather:{goal['condition']}", message, confidence=0.8))
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            # Never act as if modelled weather exists when the provider failed.
            continue
    return result


def status() -> dict[str, Any]:
    with _LOCK:
        return {
            "camera_required": False,
            "signal_sources": ["iPhone microphone sound classification (only while capture is active)",
                               "iPhone motion and GPS/geofence", "opt-in Open-Meteo modelled outdoor temperature"],
            "active_opt_in_sources": len(_LIVE),
            "can_actuate": False,
            "transcripts_or_raw_audio_persisted": False,
            "gps_trails_persisted": False,
        }
