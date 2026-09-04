from __future__ import annotations

import base64
import html
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from jarvis_mrb.email_policy import blocked_recipient_message, recipient_is_allowed

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
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
        return GoogleResult(True, "Google Gmail read/send, Contacts, and Calendar authentication completed.")
    except Exception as exc:
        return GoogleResult(False, f"Google authentication failed: {exc}")


def google_status() -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if creds and creds.valid:
        return GoogleResult(True, "Google Gmail read/send, Contacts, and Calendar are connected.")
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
    email_address = str(resolved.data["email"]).strip().lower()

    if not recipient_is_allowed(email_address):
        return GoogleResult(False, blocked_recipient_message(email_address), {"email": email_address})

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


def _decode_gmail_data(data: str | None) -> str:
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _plain_text_from_payload(payload: dict[str, Any]) -> str:
    mime_type = str(payload.get("mimeType") or "").lower()
    body = _decode_gmail_data((payload.get("body") or {}).get("data"))
    if mime_type == "text/plain" and body:
        return body

    parts = payload.get("parts") or []
    for part in parts:
        if isinstance(part, dict):
            text = _plain_text_from_payload(part)
            if text:
                return text

    if mime_type == "text/html" and body:
        without_tags = re.sub(r"<[^>]+>", " ", body)
        return html.unescape(re.sub(r"\s+", " ", without_tags)).strip()
    return ""


def _gmail_headers(payload: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in payload.get("headers") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        value = str(item.get("value") or "").strip()
        if name and value:
            result[name] = value
    return result


def _sender_label(raw_sender: str) -> str:
    name, address = parseaddr(raw_sender)
    value = (name or address or raw_sender).strip().strip('"')
    return value or "Unknown sender"


def _human_email_date(raw_date: str) -> str:
    if not raw_date:
        return ""
    try:
        value = parsedate_to_datetime(raw_date)
        if value.tzinfo is not None:
            value = value.astimezone()
        today = datetime.now().astimezone().date()
        if value.date() == today:
            prefix = "today"
        elif value.date() == today - timedelta(days=1):
            prefix = "yesterday"
        else:
            prefix = f"{value.strftime('%A, %B')} {value.day}"
        clock = value.strftime("%I:%M %p").lstrip("0")
        return f"{prefix} at {clock}"
    except (TypeError, ValueError, OverflowError):
        return raw_date


def _strip_urls(text: str) -> str:
    value = re.sub(r"<https?://[^>]+>", " ", text, flags=re.IGNORECASE)
    value = re.sub(r"https?://\S+", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bwww\.\S+", " ", value, flags=re.IGNORECASE)
    return value


def _clean_email_text(raw_body: str, snippet: str) -> str:
    def clean(value: str) -> str:
        value = html.unescape(value or "")
        value = _strip_urls(value)
        value = re.sub(r"\(\s*\)", " ", value)
        value = re.sub(r"\[\s*\]", " ", value)
        value = re.sub(r"\b([A-Za-z][A-Za-z0-9'_-]{1,30})(?:\s+\1){2,}\b", r"\1", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value).strip(" -|•\t\r\n")
        return value

    body = clean(raw_body)
    snippet_text = clean(snippet)

    # Cut common newsletter/legal footers. Keep the full cleaned text in structured
    # data only up to a reasonable size; the spoken/display message should contain
    # the useful content, not unsubscribe boilerplate or tracking machinery.
    lower = body.lower()
    footer_positions = [
        lower.find(cue)
        for cue in (" unsubscribe", " manage preferences", " privacy policy", " view in browser")
        if lower.find(cue) >= 100
    ]
    if footer_positions:
        body = body[: min(footer_positions)].rstrip(" -|•")

    # Gmail's snippet is often a much better concise representation of newsletters
    # and long quoted threads than the raw MIME body.
    if (len(body) > 650 or raw_body.lower().count("http") >= 2) and len(snippet_text) >= 30:
        body = snippet_text
    if not body:
        body = snippet_text
    if len(body) > 520:
        body = body[:517].rsplit(" ", 1)[0].rstrip() + "..."
    return body


def query_emails(query: str | None = None, limit: int = 5) -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if not creds:
        return google_status()
    safe_limit = max(1, min(int(limit), 10))
    gmail_query = (query or "in:inbox").strip() or "in:inbox"

    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        listing = service.users().messages().list(
            userId="me",
            q=gmail_query,
            maxResults=safe_limit,
        ).execute()
        refs = listing.get("messages", [])

        emails: list[dict[str, Any]] = []
        rendered: list[str] = []
        for ref in refs:
            message_id = str(ref.get("id") or "")
            if not message_id:
                continue
            message = service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()
            payload = message.get("payload") or {}
            headers = _gmail_headers(payload)
            sender_raw = headers.get("from", "Unknown sender")
            sender = _sender_label(sender_raw)
            subject = re.sub(r"\s+", " ", headers.get("subject", "(no subject)")).strip()
            if len(subject) > 120:
                subject = subject[:117].rstrip() + "..."
            date_raw = headers.get("date", "")
            date = _human_email_date(date_raw)
            raw_body = _plain_text_from_payload(payload).strip()
            snippet = str(message.get("snippet") or "").strip()
            body = _clean_email_text(raw_body, snippet)
            unread = "UNREAD" in set(message.get("labelIds") or [])

            emails.append({
                "id": message_id,
                "from": sender_raw,
                "sender": sender,
                "subject": subject,
                "date": date_raw,
                "body": body,
                "unread": unread,
            })

        for index, email in enumerate(emails, start=1):
            excerpt = str(email["body"] or "").strip()
            if len(emails) > 1 and len(excerpt) > 190:
                excerpt = excerpt[:187].rsplit(" ", 1)[0].rstrip() + "..."
            status = "unread" if email["unread"] else "read"
            item = f"{index}) {email['sender']}, {status}, subject “{email['subject']}”"
            if excerpt:
                item += f". {excerpt}"
            rendered.append(item)
    except Exception as exc:
        return GoogleResult(False, f"Gmail read failed: {exc}")

    if not emails:
        return GoogleResult(True, "No matching emails found.", {"emails": [], "query": gmail_query})

    if len(emails) == 1:
        email = emails[0]
        when = _human_email_date(str(email["date"]))
        timing = f", received {when}" if when else ""
        message = f"The email is from {email['sender']}, subject “{email['subject']}”{timing}."
        if email["body"]:
            message += f" It says: {email['body']}"
    else:
        message = f"I found {len(emails)} matching emails. " + " ".join(rendered)

    return GoogleResult(True, message, {"emails": emails, "query": gmail_query})


def _human_event_time(value: str) -> str:
    if not value:
        return ""
    try:
        is_all_day = "T" not in value
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        today = datetime.now().astimezone().date()
        if parsed.date() == today:
            date_label = "today"
        elif parsed.date() == today + timedelta(days=1):
            date_label = "tomorrow"
        else:
            date_label = f"{parsed.strftime('%A, %B')} {parsed.day}"
        if is_all_day:
            return f"{date_label}, all day"
        clock = parsed.strftime("%I:%M %p").lstrip("0")
        return f"{date_label} at {clock}"
    except (TypeError, ValueError, OverflowError):
        return value


def _format_events(events: list[dict[str, Any]], prefix: str) -> GoogleResult:
    if not events:
        return GoogleResult(True, f"{prefix}: none found.", {"events": []})
    summaries: list[str] = []
    compact: list[dict[str, str]] = []
    for event in events:
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date") or ""
        end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date") or ""
        summary = event.get("summary") or "(untitled)"
        location = event.get("location") or ""
        summaries.append(f"{_human_event_time(start)} — {summary}" + (f" at {location}" if location else ""))
        compact.append({"id": event.get("id", ""), "summary": summary, "start": start, "end": end, "location": location})

    shown = summaries[:6]
    remaining = len(summaries) - len(shown)
    message = prefix + ": " + "; ".join(shown)
    if remaining > 0:
        message += f"; plus {remaining} more"
    return GoogleResult(True, message + ".", {"events": compact})


def query_calendar_events(
    *,
    direction: str = "future",
    days: int = 7,
    limit: int = 10,
    query: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if not creds:
        return google_status()
    now = datetime.now().astimezone()
    limit = max(1, min(int(limit), 50))
    days = max(1, min(int(days), 3650))
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        kwargs: dict[str, Any] = {
            "calendarId": "primary",
            "maxResults": limit,
            "singleEvents": True,
        }
        if query:
            kwargs["q"] = query
        if start or end:
            if start:
                kwargs["timeMin"] = start
            if end:
                kwargs["timeMax"] = end
            kwargs["orderBy"] = "startTime"
            response = service.events().list(**kwargs).execute()
            return _format_events(response.get("items", []), "Calendar events")
        if direction == "past":
            kwargs["timeMin"] = (now - timedelta(days=days)).isoformat()
            kwargs["timeMax"] = now.isoformat()
            kwargs["orderBy"] = "startTime"
            response = service.events().list(**kwargs).execute()
            events = response.get("items", [])
            events.reverse()
            return _format_events(events[:limit], "Past events")
        kwargs["timeMin"] = now.isoformat()
        kwargs["timeMax"] = (now + timedelta(days=days)).isoformat()
        kwargs["orderBy"] = "startTime"
        response = service.events().list(**kwargs).execute()
        return _format_events(response.get("items", []), "Upcoming events")
    except Exception as exc:
        return GoogleResult(False, f"Calendar read failed: {exc}")


def list_calendar_events(days: int = 7, limit: int = 10) -> GoogleResult:
    return query_calendar_events(direction="future", days=days, limit=limit)


def most_recent_calendar_event(days_back: int = 3650) -> GoogleResult:
    result = query_calendar_events(direction="past", days=days_back, limit=1)
    if result.ok and result.data and result.data.get("events"):
        event = result.data["events"][0]
        return GoogleResult(
            True,
            f"Most recent event: {_human_event_time(event['start'])} — {event['summary']}.",
            {"events": [event]},
        )
    return GoogleResult(True, f"No calendar events found in the last {days_back} day(s).", {"events": []})


def create_calendar_event(summary: str, start: str, end: str, description: str | None = None) -> GoogleResult:
    creds = _load_credentials(interactive=False)
    if not creds:
        return google_status()
    if not summary.strip() or not start.strip() or not end.strip():
        return GoogleResult(False, "Calendar event requires summary, start, and end.")
    body: dict[str, Any] = {"summary": summary.strip(), "start": {"dateTime": start.strip()}, "end": {"dateTime": end.strip()}}
    if description:
        body["description"] = description
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        event = service.events().insert(calendarId="primary", body=body).execute()
    except Exception as exc:
        return GoogleResult(False, f"Calendar create failed: {exc}")
    return GoogleResult(True, f"Created calendar event {summary!r}.", {"event_id": event.get("id", ""), "html_link": event.get("htmlLink", "")})
