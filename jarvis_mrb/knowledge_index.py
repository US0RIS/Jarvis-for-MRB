from __future__ import annotations

import hashlib
import os
import sqlite3
from email.utils import parseaddr
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
        row = conn.execute("SELECT content_hash FROM indexed_sources WHERE source_key=?", (source_key,)).fetchone()
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


def _record_world_email(email: dict[str, Any], text: str) -> None:
    try:
        from jarvis_mrb.world_model import ensure_entity, record_knowledge_source

        raw_sender = str(email.get("sender") or email.get("from") or "").strip()
        display_name, address = parseaddr(raw_sender)
        person_name = " ".join((display_name or address or raw_sender or "Unknown sender").split())[:300]
        participants: list[tuple[str, str, float]] = []
        if person_name and person_name.lower() != "unknown sender":
            person_id = ensure_entity(
                "person",
                person_name,
                external_namespace="email_address" if address else None,
                external_id=address.lower() if address else None,
                aliases=[address] if address else [],
                attributes={"email": address.lower()} if address else {},
                confidence=1.0,
            )
            participants.append((person_id, "sender", 1.0))

        record_knowledge_source(
            "gmail",
            str(email.get("id") or ""),
            title=str(email.get("subject") or "(no subject)"),
            text=text,
            occurred_at=str(email.get("date") or "") or None,
            metadata={
                "sender": raw_sender,
                "email_address": address.lower() if address else "",
                "thread_id": str(email.get("threadId") or email.get("thread_id") or ""),
            },
            participants=participants,
        )
    except Exception:
        pass


def _record_world_calendar(event: dict[str, Any], text: str) -> None:
    try:
        from jarvis_mrb.world_model import ensure_entity, record_knowledge_source

        participants: list[tuple[str, str, float]] = []
        location = " ".join(str(event.get("location") or "").split())[:500]
        if location:
            place_id = ensure_entity("place", location, confidence=0.9)
            participants.append((place_id, "location", 0.9))

        record_knowledge_source(
            "calendar",
            str(event.get("id") or ""),
            title=str(event.get("summary") or "(untitled event)"),
            text=text,
            occurred_at=str(event.get("start") or "") or None,
            metadata={"start": event.get("start"), "end": event.get("end"), "location": location},
            participants=participants,
        )
    except Exception:
        pass


def _record_world_note(relative: str, raw: str) -> None:
    try:
        from jarvis_mrb.world_model import record_knowledge_source

        record_knowledge_source("note", relative, title=relative, text=raw, metadata={"path": relative})
    except Exception:
        pass


def refresh() -> dict[str, Any]:
    indexed = 0
    scanned = 0
    errors: list[str] = []
    backfill: dict[str, Any] | None = None
    extended_backfill: dict[str, Any] | None = None
    attachment_sync: dict[str, Any] | None = None
    calendar_enrichment: dict[str, Any] | None = None
    linker: dict[str, Any] | None = None
    document_versions: dict[str, Any] | None = None
    terms: dict[str, Any] | None = None
    executive: dict[str, Any] | None = None
    executive_loop: dict[str, Any] | None = None

    try:
        from jarvis_mrb.world_backfill import backfill_existing_state
        backfill = backfill_existing_state()
    except Exception as exc:
        backfill = {"ok": False, "error": str(exc)[:500]}

    try:
        from jarvis_mrb.world_extended_backfill import backfill_extended_state
        extended_backfill = backfill_extended_state()
    except Exception as exc:
        extended_backfill = {"ok": False, "error": str(exc)[:500]}

    email_result = query_emails(query="in:anywhere newer_than:30d", limit=10)
    if email_result.ok and email_result.data:
        for email in email_result.data.get("emails", []):
            if not isinstance(email, dict):
                continue
            scanned += 1
            text = (
                f"Email from {email.get('sender') or email.get('from') or 'unknown'}; "
                f"subject: {email.get('subject') or '(no subject)'}; "
                f"date: {email.get('date') or ''}. {email.get('body') or ''}"
            )
            _record_world_email(email, text)
            if _index_once(f"gmail:{email.get('id')}", text, kind="gmail"):
                indexed += 1
    elif not email_result.ok:
        errors.append(email_result.message)

    try:
        from jarvis_mrb.world_gmail_attachments import sync as sync_gmail_attachments
        attachment_sync = sync_gmail_attachments(limit=20)
    except Exception as exc:
        attachment_sync = {"ok": False, "messages": 0, "indexed": 0, "error": str(exc)[:500]}

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
                _record_world_calendar(event, text)
                if _index_once(f"calendar:{event.get('id')}", text, kind="calendar"):
                    indexed += 1
        elif not calendar_result.ok:
            errors.append(calendar_result.message)

    try:
        from jarvis_mrb.world_calendar_sync import sync as sync_world_calendar
        calendar_enrichment = sync_world_calendar(days_past=30, days_future=120, limit=100)
    except Exception as exc:
        calendar_enrichment = {"ok": False, "synced": 0, "error": str(exc)[:500]}

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
        _record_world_note(relative, raw)
        if _index_once(f"note:{relative}", text, kind="note"):
            indexed += 1

    try:
        from jarvis_mrb.world_linker import refresh_links
        linker = refresh_links(limit=3000)
    except Exception as exc:
        linker = {"error": str(exc)[:500]}

    try:
        from jarvis_mrb.world_document_versions import refresh as refresh_document_versions
        from jarvis_mrb.world_linker import link_event

        document_versions = refresh_document_versions(limit_pairs=80)
        for event_id in document_versions.get("generated_event_ids") or []:
            try:
                link_event(int(event_id))
            except Exception:
                pass
    except Exception as exc:
        document_versions = {"error": str(exc)[:500]}

    try:
        from jarvis_mrb.world_linker import link_event
        from jarvis_mrb.world_terms import refresh as refresh_terms

        terms = refresh_terms(limit=4000)
        for event_id in terms.get("generated_event_ids") or []:
            try:
                link_event(int(event_id))
            except Exception:
                pass
    except Exception as exc:
        terms = {"error": str(exc)[:500]}

    try:
        from jarvis_mrb.world_executive import refresh_intentions
        executive = refresh_intentions()
    except Exception as exc:
        executive = {"error": str(exc)[:500]}

    # Knowledge ingestion is a major world-state transition. Recompute persistent
    # attention and the current decision only after source linking, document-version
    # analysis, term reconciliation, and intention materialization all finish. This
    # keeps the Executive Loop current without waiting for a later user query.
    try:
        from jarvis_mrb.world_executive_loop import refresh as refresh_executive_loop
        executive_loop = refresh_executive_loop()
    except Exception as exc:
        executive_loop = {"error": str(exc)[:500]}

    return {
        "ok": not errors,
        "scanned": scanned,
        "indexed": indexed,
        "errors": errors[:5],
        "notes_directory": str(NOTES_DIR),
        "world_model_mirroring": True,
        "world_backfill": backfill,
        "world_extended_backfill": extended_backfill,
        "world_gmail_attachments": attachment_sync,
        "world_calendar_enrichment": calendar_enrichment,
        "world_linker": linker,
        "world_document_versions": document_versions,
        "world_terms": terms,
        "world_executive": executive,
        "world_executive_loop": executive_loop,
    }


def search(query: str, limit: int = 5) -> list[str]:
    safe_limit = max(1, min(int(limit), 8))
    result: list[str] = []
    try:
        from jarvis_mrb.world_model import search as world_search
        for item in world_search(query, limit=safe_limit):
            source = f" | source {item.get('source')}" if item.get("source") else ""
            result.append(f"[world {item.get('type')} | {item.get('time')}{source}] {item.get('text') or item.get('name') or ''}")
    except Exception:
        pass
    for item in retrieve(query, limit=safe_limit):
        if item not in result:
            result.append(item)
        if len(result) >= safe_limit:
            break
    return result[:safe_limit]


def describe_search(query: str, limit: int = 5) -> str:
    items = search(query, limit=limit)
    if not items:
        return "I couldn't find a matching entity, event, commitment, email, calendar item, attachment, document change, project term, note, or prior conversation in unified local knowledge."
    return "Relevant unified-knowledge matches: " + " | ".join(items)


def status() -> dict[str, Any]:
    with _connect() as conn:
        sources = int(conn.execute("SELECT COUNT(*) FROM indexed_sources").fetchone()[0])
    linker: dict[str, Any] = {}
    executive: dict[str, Any] = {}
    executive_loop: dict[str, Any] = {}
    relevance: dict[str, Any] = {}
    attachments: dict[str, Any] = {}
    document_versions: dict[str, Any] = {}
    terms: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    try:
        from jarvis_mrb.world_linker import status as world_linker_status
        linker = world_linker_status()
    except Exception:
        pass
    try:
        from jarvis_mrb.world_executive import status as world_executive_status
        executive = world_executive_status()
    except Exception:
        pass
    try:
        from jarvis_mrb.world_executive_loop import status as world_executive_loop_status
        executive_loop = world_executive_loop_status()
    except Exception:
        pass
    try:
        from jarvis_mrb.world_relevance import status as world_relevance_status
        relevance = world_relevance_status()
    except Exception:
        pass
    try:
        from jarvis_mrb.world_gmail_attachments import status as attachment_status
        attachments = attachment_status()
    except Exception:
        pass
    try:
        from jarvis_mrb.world_document_versions import status as version_status
        document_versions = version_status()
    except Exception:
        pass
    try:
        from jarvis_mrb.world_terms import status as term_status
        terms = term_status()
    except Exception:
        pass
    try:
        from jarvis_mrb.world_diagnostics import validate as validate_world
        diagnostics = validate_world()
    except Exception as exc:
        diagnostics = {"ok": False, "error": str(exc)[:500]}
    return {
        "indexed_sources": sources,
        "notes_directory": str(NOTES_DIR),
        "world_model_mirroring": True,
        "world_linker": linker,
        "world_executive": executive,
        "world_executive_loop": executive_loop,
        "world_relevance": relevance,
        "world_gmail_attachments": attachments,
        "world_document_versions": document_versions,
        "world_terms": terms,
        "world_diagnostics": diagnostics,
    }
