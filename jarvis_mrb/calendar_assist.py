from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from jarvis_mrb.tools.google import query_calendar_events


def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.astimezone()
        return parsed.astimezone()
    except (TypeError, ValueError):
        return None


def _event_interval(event: dict[str, Any]) -> tuple[datetime, datetime] | None:
    start = _parse(str(event.get("start") or ""))
    end = _parse(str(event.get("end") or ""))
    if not start or not end or end <= start:
        return None
    return start, end


def find_conflicts(days: int = 7) -> str:
    result = query_calendar_events(direction="future", days=max(1, min(int(days), 30)), limit=50)
    if not result.ok or not result.data:
        return result.message
    events = [event for event in result.data.get("events", []) if isinstance(event, dict)]
    timed: list[tuple[datetime, datetime, dict[str, Any]]] = []
    for event in events:
        interval = _event_interval(event)
        if interval:
            timed.append((interval[0], interval[1], event))
    timed.sort(key=lambda item: item[0])

    conflicts: list[str] = []
    for index, (start, end, event) in enumerate(timed):
        for other_start, other_end, other in timed[index + 1 :]:
            if other_start >= end:
                break
            if other_end > start:
                left = str(event.get("summary") or "Untitled event")
                right = str(other.get("summary") or "Untitled event")
                conflicts.append(
                    f"{left} overlaps {right} on {start.strftime('%A')} around {other_start.strftime('%-I:%M %p') if hasattr(start, 'strftime') else other_start.isoformat()}"
                )
    if not conflicts:
        return f"I found no overlapping timed calendar events in the next {days} day(s)."

    suggestions = _alternative_slots(timed, limit=min(3, len(conflicts)))
    message = "Calendar conflicts: " + "; ".join(conflicts[:5]) + "."
    if suggestions:
        message += " Possible open alternatives: " + "; ".join(suggestions) + "."
    message += " These are proposals only; Jarvis will not move or decline meetings without confirmation."
    return message


def _alternative_slots(
    timed: list[tuple[datetime, datetime, dict[str, Any]]],
    *,
    limit: int = 3,
) -> list[str]:
    now = datetime.now().astimezone()
    occupied = [(start, end) for start, end, _ in timed]
    results: list[str] = []
    for day_offset in range(0, 8):
        day = (now + timedelta(days=day_offset)).date()
        cursor = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=9)
        end_of_day = cursor.replace(hour=17)
        if day_offset == 0 and cursor < now:
            minutes = ((now.minute // 30) + 1) * 30
            cursor = now.replace(second=0, microsecond=0)
            if minutes >= 60:
                cursor = cursor.replace(minute=0) + timedelta(hours=1)
            else:
                cursor = cursor.replace(minute=minutes)
        while cursor + timedelta(minutes=60) <= end_of_day:
            slot_end = cursor + timedelta(minutes=60)
            if all(slot_end <= start or cursor >= end for start, end in occupied):
                results.append(f"{cursor.strftime('%A')} at {cursor.strftime('%I:%M %p').lstrip('0')}")
                if len(results) >= limit:
                    return results
            cursor += timedelta(minutes=30)
    return results
