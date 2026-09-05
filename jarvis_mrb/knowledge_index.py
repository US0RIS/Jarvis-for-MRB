from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any

from jarvis_mrb.memory import remember_text, retrieve
from jarvis_mrb.tools.google import query_calendar_events, query_emails

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "knowledge_sources.sqlite3"
NOTES_DIR = APP_DIR / "notes"


def _connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indexed_sources (
            source_key TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _index_once(source_key: str, text: str, *, kind: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    digest = _fingerprint(cleaned)
    with _connect() as conn:
        row = conn.execute(
            "SELECT content_hash FROM indexed_sources WHERE source_key=?",
            (source_key,),
        ).fetchone()
        if row and str(row[0]) == digest:
            return False
    remember_text(cleaned, session_id="knowledge", kind=kind)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO indexed_sources(source_key,content_hash) VALUES(?,?) "
            "ON CONFLICT(source_key) DO UPDATE SET content_hash=excluded.content_hash,indexed_at=CURRENT_TIMESTAMP",
            (source_key, digest),
        )
        conn.commit()
    return True


def refresh() -> dict[str, Any]:
    indexed = 0
    scanned = 0
    errors: list[str] = []

    email_result = query_emails(query="in:anywhere newer_than:30d", limit=10)
    if email_result.ok and email_result.data:
        for email in email_result.data.get("emails", []):
            if not isinstance(email, dict):
                continue
            scanned += 1
            text = (
                f"Email from {email.get('sender') or email.get('from') or 'unknown'}; "
                f"subject: {email.get('subject') or '(no subject)'}; "
                f"date: {email.get('date') or ''}. "
                f"{email.get('body') or ''}"
            )
            if _index_once(f"gmail:{email.get('id')}", text, kind="gmail"):
                indexed += 1
    elif not email_result.ok:
        errors.append(email_result.message)

    for direction, days in (("past", 60), ("future", 120)):
        calendar_result = query_calendar_events(direction=direction, days=days, limit=30)
        if calendar_result.ok and calendar_result.data:
            for event in calendar_result.data.get("events", []):
                if not isinstance(event, dict):
                    continue
                scanned += 1
                text = (
                    f"Calendar event: {event.get('summary') or '(untitled)'}; "
                    f"start: {event.get('start') or ''}; end: {event.get('end') or ''}; "
                    f"location: {event.get('location') or ''}."
                )
                if _index_once(f"calendar:{event.get('id')}", text, kind="calendar"):
                    indexed += 1
        elif not calendar_result.ok:
            errors.append(calendar_result.message)

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(NOTES_DIR.glob("**/*")):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".md", ".json", ".log"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")[:80_000]
        except OSError as exc:
            errors.append(f"Could not read {path.name}: {exc}")
            continue
        scanned += 1
        relative = path.relative_to(NOTES_DIR).as_posix()
        text = f"Local note {relative}:\n{raw}"
        if _index_once(f"note:{relative}", text, kind="note"):
            indexed += 1

    return {
        "ok": not errors,
        "scanned": scanned,
        "indexed": indexed,
        "errors": errors[:5],
        "notes_directory": str(NOTES_DIR),
    }


def search(query: str, limit: int = 5) -> list[str]:
    return retrieve(query, limit=max(1, min(int(limit), 8)))


def describe_search(query: str, limit: int = 5) -> str:
    items = search(query, limit=limit)
    if not items:
        return "I couldn't find a matching item in indexed mail, calendar, notes, or prior conversations."
    return "Relevant unified-memory matches: " + " | ".join(items)


def status() -> dict[str, Any]:
    with _connect() as conn:
        sources = int(conn.execute("SELECT COUNT(*) FROM indexed_sources").fetchone()[0])
    return {"indexed_sources": sources, "notes_directory": str(NOTES_DIR)}
