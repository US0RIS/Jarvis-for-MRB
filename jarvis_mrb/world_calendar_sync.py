from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from googleapiclient.discovery import build

from jarvis_mrb.world_model import SELF_ID, assert_belief, ensure_entity, record_event


def _iso_value(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("dateTime") or value.get("date") or "").strip()


def _person_from_attendee(attendee: dict[str, Any]) -> tuple[str, str, float] | None:
    if bool(attendee.get("self")):
        return (SELF_ID, "attendee", 1.0)
    email = str(attendee.get("email") or "").strip().lower()
    display = " ".join(str(attendee.get("displayName") or "").split())
    name = display or email
    if not name:
        return None
    entity_id = ensure_entity(
        "person",
        name,
        external_namespace="email_address" if email else None,
        external_id=email if email else None,
        aliases=[email] if email else [],
        attributes={"email": email} if email else {},
        confidence=1.0,
    )
    response = str(attendee.get("responseStatus") or "").strip().lower()
    confidence = 1.0 if response in {"accepted", "tentative"} else 0.9
    return (entity_id, "attendee", confidence)


def _organizer(event: dict[str, Any]) -> tuple[str, str, float] | None:
    organizer = event.get("organizer")
    if not isinstance(organizer, dict):
        return None
    if bool(organizer.get("self")):
        return (SELF_ID, "organizer", 1.0)
    email = str(organizer.get("email") or "").strip().lower()
    display = " ".join(str(organizer.get("displayName") or "").split())
    name = display or email
    if not name:
        return None
    entity_id = ensure_entity(
        "person",
        name,
        external_namespace="email_address" if email else None,
        external_id=email if email else None,
        aliases=[email] if email else [],
        attributes={"email": email} if email else {},
        confidence=1.0,
    )
    return (entity_id, "organizer", 1.0)


def sync(*, days_past: int = 30, days_future: int = 120, limit: int = 100) -> dict[str, Any]:
    """Mirror private calendar context that the conversational adapter omits.

    The ordinary Calendar tool intentionally returns a compact spoken structure. The
    world model needs richer private context—attendees, organizer and description—to
    connect a meeting to people/projects/commitments. This uses the same local Google
    OAuth token and never changes or sends calendar data.
    """
    try:
        from jarvis_mrb.tools.google import _load_credentials

        creds = _load_credentials(interactive=False)
    except Exception as exc:
        return {"ok": False, "synced": 0, "error": f"Google credentials unavailable: {exc}"[:500]}
    if not creds:
        return {"ok": False, "synced": 0, "error": "Google is not connected."}

    now = datetime.now().astimezone()
    safe_limit = max(1, min(int(limit), 250))
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        response = service.events().list(
            calendarId="primary",
            timeMin=(now - timedelta(days=max(1, min(days_past, 3650)))).isoformat(),
            timeMax=(now + timedelta(days=max(1, min(days_future, 3650)))).isoformat(),
            maxResults=safe_limit,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception as exc:
        return {"ok": False, "synced": 0, "error": f"Calendar enrichment failed: {exc}"[:500]}

    synced = 0
    for raw in response.get("items", []):
        if not isinstance(raw, dict):
            continue
        event_id = str(raw.get("id") or "").strip()
        if not event_id:
            continue
        summary = " ".join(str(raw.get("summary") or "(untitled event)").split())[:500]
        description = str(raw.get("description") or "").strip()[:12000]
        location = " ".join(str(raw.get("location") or "").split())[:500]
        start = _iso_value(raw.get("start"))
        end = _iso_value(raw.get("end"))
        status = str(raw.get("status") or "confirmed").strip().lower()

        calendar_id = ensure_entity(
            "calendar",
            summary,
            external_namespace="calendar",
            external_id=event_id,
            attributes={
                "start": start,
                "end": end,
                "location": location,
                "calendar_status": status,
                "description_present": bool(description),
            },
            confidence=1.0,
        )
        participants: list[tuple[str, str, float]] = [(calendar_id, "meeting", 1.0), (SELF_ID, "calendar_owner", 1.0)]

        organizer = _organizer(raw)
        if organizer:
            participants.append(organizer)
        attendees: list[dict[str, str]] = []
        for attendee in raw.get("attendees") or []:
            if not isinstance(attendee, dict):
                continue
            person = _person_from_attendee(attendee)
            if person:
                participants.append(person)
            attendees.append(
                {
                    "email": str(attendee.get("email") or "")[:320],
                    "display_name": str(attendee.get("displayName") or "")[:300],
                    "response": str(attendee.get("responseStatus") or "")[:80],
                    "self": "true" if attendee.get("self") else "false",
                }
            )

        if location:
            place_id = ensure_entity("place", location, confidence=0.95)
            participants.append((place_id, "location", 0.95))

        event = record_event(
            "calendar.context_enriched",
            f"Calendar context: {summary}" + (f" — {description[:1200]}" if description else ""),
            source_kind="calendar_enriched",
            source_ref=event_id,
            occurred_at=start or None,
            payload={
                "calendar_event_id": event_id,
                "title": summary,
                "start": start,
                "end": end,
                "location": location,
                "status": status,
                "description": description,
                "attendees": attendees[:100],
            },
            evidence="Private Google Calendar event metadata synchronized locally for world-model relationship context.",
            confidence=1.0,
            participants=participants,
        )
        assert_belief(calendar_id, "calendar_status", value=status, source_event_id=event)
        if start:
            assert_belief(calendar_id, "start_at", value=start, source_event_id=event)
        if end:
            assert_belief(calendar_id, "end_at", value=end, source_event_id=event)
        if location:
            assert_belief(calendar_id, "location_name", value=location, source_event_id=event)
        synced += 1

    return {"ok": True, "synced": synced, "window_days_past": days_past, "window_days_future": days_future}
