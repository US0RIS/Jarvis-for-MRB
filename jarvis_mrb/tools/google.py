from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
TOKEN_PATH = APP_DIR / "google_token.json"
DEFAULT_CREDENTIALS_PATH = APP_DIR / "google_credentials.json"


@dataclass(frozen=True)
class GoogleResult:
    ok: bool
    message: str
    data: dict[str, Any] | None = None


def credentials_path() -> Path:
    override = os.environ.get("JARVIS_GOOGLE_CREDENTIALS")
    return Path(override).expanduser() if override else DEFAULT_CREDENTIALS_PATH


def _has_required_scopes(creds: Credentials | None) -> bool:
    return bool(creds and creds.valid and creds.has_scopes(SCOPES))


def _load_credentials(interactive: bool = False) -> Credentials | None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            creds = None

    if _has_required_scopes(creds):
        return creds
    if not interactive:
        return None

    path = credentials_path()
    if not path.exists():
        return None
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def authenticate_google() -> GoogleResult:
    path = credentials_path()
    if not path.exists():
        return GoogleResult(False, f"Google OAuth credentials are missing. Put a Desktop OAuth client JSON at {path} or set JARVIS_GOOGLE_CREDENTIALS.")
    try:
        # Force a fresh consent when an older token lacks newly-added Calendar scopes.
        if TOKEN_PATH.exists():
            try:
                old = Credentials.from_authorized_user_file(str(TOKEN_PATH))
                if not old.has_scopes(SCOPES):
                    TOKEN_PATH.unlink(missing_ok=True)
            except Exception:
                TOKEN_PATH.unlink(missing_ok=True)
        creds = _load_credentials(interactive=True)
        if not creds:
            return GoogleResult(False, "Google authentication did not complete.")
        return GoogleResult(True, "Google Gmail, Contacts, and Calendar authentication completed.")
    except Exception as exc:
        return GoogleResult(False, f"Google authentication failed: {exc}")


def google_status() -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if creds and creds.valid:
        return GoogleResult(True, "Google Gmail, Contacts, and Calendar are connected.")
    return GoogleResult(False, "Google is not connected with all required scopes. Run: py -3.14 -m jarvis_mrb.google_auth")


def resolve_contact(query: str) -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if not creds:
        return google_status()
    query = query.strip()
    if not query:
        return GoogleResult(False, "No contact name was provided.")
    if "@" in query and " " not in query:
        return GoogleResult(True, f"Using {query}.", {"email": query, "name": query})
    try:
        service = build("people", "v1", credentials=creds, cache_discovery=False)
        response = service.people().searchContacts(query=query, readMask="names,emailAddresses", pageSize=10).execute()
    except Exception as exc:
        return GoogleResult(False, f"Could not search Google Contacts: {exc}")
    candidates: list[dict[str, str]] = []
    for result in response.get("results", []):
        person = result.get("person", {})
        emails = person.get("emailAddresses", [])
        if not emails:
            continue
        names = person.get("names", [])
        display = names[0].get("displayName") if names else query
        email = emails[0].get("value")
        if email:
            candidates.append({"name": display or query, "email": email})
    if not candidates:
        return GoogleResult(False, f"I could not find a Google contact matching {query}.")
    if len(candidates) == 1:
        chosen = candidates[0]
        return GoogleResult(True, f"Found {chosen['name']} <{chosen['email']}>.", chosen)
    exact = [c for c in candidates if c["name"].strip().lower() == query.lower()]
    if len(exact) == 1:
        chosen = exact[0]
        return GoogleResult(True, f"Found {chosen['name']} <{chosen['email']}>.", chosen)
    choices = "; ".join(f"{c['name']} <{c['email']}>" for c in candidates[:5])
    return GoogleResult(False, f"I found multiple contacts for {query}: {choices}")


def send_email(recipient: str, body: str, subject: str | None = None) -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if not creds:
        return google_status()
    resolved = resolve_contact(recipient)
    if not resolved.ok or not resolved.data:
        return resolved
    email_address = str(resolved.data["email"])
    message = EmailMessage()
    message["To"] = email_address
    if subject:
        message["Subject"] = subject
    message.set_content(body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        sent = service.users().messages().send(userId="me", body={"raw": encoded}).execute()
    except Exception as exc:
        return GoogleResult(False, f"Gmail send failed: {exc}")
    return GoogleResult(True, f"Sent email to {email_address}.", {"message_id": sent.get("id", ""), "email": email_address})


def list_calendar_events(days: int = 7, limit: int = 10) -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if not creds:
        return google_status()
    now = datetime.now().astimezone()
    end = now + timedelta(days=max(1, min(days, 90)))
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        response = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=max(1, min(limit, 50)),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception as exc:
        return GoogleResult(False, f"Calendar read failed: {exc}")
    events = response.get("items", [])
    if not events:
        return GoogleResult(True, f"No calendar events in the next {days} day(s).", {"events": []})
    summaries: list[str] = []
    compact: list[dict[str, str]] = []
    for event in events:
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date") or ""
        summary = event.get("summary") or "(untitled)"
        summaries.append(f"{start}: {summary}")
        compact.append({"id": event.get("id", ""), "summary": summary, "start": start})
    return GoogleResult(True, "Upcoming events: " + "; ".join(summaries), {"events": compact})


def create_calendar_event(summary: str, start: str, end: str, description: str | None = None) -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if not creds:
        return google_status()
    if not summary.strip() or not start.strip() or not end.strip():
        return GoogleResult(False, "Calendar event requires summary, start, and end.")
    body: dict[str, Any] = {
        "summary": summary.strip(),
        "start": {"dateTime": start.strip()},
        "end": {"dateTime": end.strip()},
    }
    if description:
        body["description"] = description
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        event = service.events().insert(calendarId="primary", body=body).execute()
    except Exception as exc:
        return GoogleResult(False, f"Calendar create failed: {exc}")
    return GoogleResult(True, f"Created calendar event {summary!r}.", {"event_id": event.get("id", ""), "html_link": event.get("htmlLink", "")})
