from __future__ import annotations

import base64
import io
import re
import zipfile
from email.utils import parseaddr
from pathlib import PurePath
from typing import Any, Iterable
from xml.etree import ElementTree

from googleapiclient.discovery import build

from jarvis_mrb.world_model import ensure_entity, record_knowledge_source

_MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
_MAX_TEXT_CHARS = 80_000
_MAX_MESSAGES = 20
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".rtf", ".pptx"}


def _decode_base64url(data: str) -> bytes:
    padded = str(data or "") + "=" * (-len(str(data or "")) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _iter_parts(part: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield part
    for child in part.get("parts") or []:
        if isinstance(child, dict):
            yield from _iter_parts(child)


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in payload.get("headers") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        value = str(item.get("value") or "").strip()
        if name and value:
            result[name] = value
    return result


def _clean_text(value: str) -> str:
    text = value.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:_MAX_TEXT_CHARS]


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "windows-1252", "latin-1"):
        try:
            return _clean_text(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    return ""


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            targets = ["word/document.xml"]
            targets.extend(sorted(name for name in names if name.startswith("word/header") and name.endswith(".xml")))
            targets.extend(sorted(name for name in names if name.startswith("word/footer") and name.endswith(".xml")))
            chunks: list[str] = []
            for name in targets:
                if name not in names:
                    continue
                raw = archive.read(name)
                root = ElementTree.fromstring(raw)
                text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
                if text.strip():
                    chunks.append(text.strip())
                if sum(len(chunk) for chunk in chunks) >= _MAX_TEXT_CHARS:
                    break
            return _clean_text("\n".join(chunks))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError):
        return ""


def _extract_pptx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            slide_names = sorted(
                name for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            )[:120]
            chunks: list[str] = []
            for name in slide_names:
                root = ElementTree.fromstring(archive.read(name))
                text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
                if text.strip():
                    chunks.append(text.strip())
                if sum(len(chunk) for chunk in chunks) >= _MAX_TEXT_CHARS:
                    break
            return _clean_text("\n".join(chunks))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError):
        return ""


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=False)
        chunks: list[str] = []
        for page in list(reader.pages)[:80]:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                chunks.append(text.strip())
            if sum(len(chunk) for chunk in chunks) >= _MAX_TEXT_CHARS:
                break
        return _clean_text("\n".join(chunks))
    except Exception:
        return ""


def _extract_rtf(data: bytes) -> str:
    text = _decode_text(data)
    if not text:
        return ""
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return _clean_text(text)


def _extract(filename: str, mime_type: str, data: bytes) -> str:
    extension = PurePath(filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        return ""
    if len(data) > _MAX_ATTACHMENT_BYTES:
        return ""
    if extension == ".pdf":
        return _extract_pdf(data)
    if extension == ".docx":
        return _extract_docx(data)
    if extension == ".pptx":
        return _extract_pptx(data)
    if extension == ".rtf":
        return _extract_rtf(data)
    return _decode_text(data)


def _already_indexed(message_id: str, attachment_ref: str) -> bool:
    try:
        import sqlite3
        from jarvis_mrb.world_model import DB_PATH

        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        row = conn.execute(
            "SELECT 1 FROM external_ids WHERE namespace='gmail_attachment' AND external_id=? LIMIT 1",
            (f"{message_id}:{attachment_ref}",),
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def sync(*, query: str = "in:anywhere newer_than:30d has:attachment", limit: int = _MAX_MESSAGES) -> dict[str, Any]:
    """Extract safe text from recent Gmail attachments into the private world graph.

    No attachment is executed or opened through an OS application. Only an explicit
    allowlist of passive text/document formats is parsed in memory. Macro-enabled,
    executable, archive, image and unknown attachment types are ignored.
    """
    try:
        from jarvis_mrb.tools.google import _load_credentials

        creds = _load_credentials(interactive=False)
    except Exception as exc:
        return {"ok": False, "messages": 0, "indexed": 0, "error": str(exc)[:500]}
    if not creds:
        return {"ok": False, "messages": 0, "indexed": 0, "error": "Google is not connected."}

    safe_limit = max(1, min(int(limit), 50))
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        listing = service.users().messages().list(userId="me", q=query, maxResults=safe_limit).execute()
    except Exception as exc:
        return {"ok": False, "messages": 0, "indexed": 0, "error": f"Gmail attachment listing failed: {exc}"[:500]}

    messages = 0
    indexed = 0
    skipped_type = 0
    skipped_size = 0
    failed_extract = 0

    for ref in listing.get("messages", []):
        message_id = str(ref.get("id") or "").strip()
        if not message_id:
            continue
        try:
            message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        except Exception:
            continue
        messages += 1
        thread_id = str(message.get("threadId") or "").strip()[:500]
        payload = message.get("payload") or {}
        headers = _headers(payload)
        raw_sender = headers.get("from", "")
        display_name, address = parseaddr(raw_sender)
        person_name = " ".join((display_name or address or raw_sender or "Unknown sender").split())[:300]
        subject = " ".join(headers.get("subject", "(no subject)").split())[:500]
        date_raw = str(headers.get("date") or "")[:200]

        sender_id: str | None = None
        if person_name and person_name.lower() != "unknown sender":
            sender_id = ensure_entity(
                "person",
                person_name,
                external_namespace="email_address" if address else None,
                external_id=address.lower() if address else None,
                aliases=[address] if address else [],
                attributes={"email": address.lower()} if address else {},
                confidence=1.0,
            )
        parent_email_id = ensure_entity(
            "document",
            subject,
            external_namespace="gmail",
            external_id=message_id,
            attributes={"source_kind": "gmail", "sender": raw_sender, "thread_id": thread_id},
            confidence=1.0,
        )

        for part in _iter_parts(payload):
            filename = " ".join(str(part.get("filename") or "").split())[:500]
            if not filename:
                continue
            extension = PurePath(filename).suffix.lower()
            if extension not in _ALLOWED_EXTENSIONS:
                skipped_type += 1
                continue
            body = part.get("body") or {}
            attachment_id = str(body.get("attachmentId") or "").strip()
            part_id = str(part.get("partId") or filename).strip()[:300]
            attachment_ref = attachment_id or part_id
            if _already_indexed(message_id, attachment_ref):
                continue
            declared_size = int(body.get("size") or 0)
            if declared_size > _MAX_ATTACHMENT_BYTES:
                skipped_size += 1
                continue

            try:
                if attachment_id:
                    response = service.users().messages().attachments().get(
                        userId="me", messageId=message_id, id=attachment_id
                    ).execute()
                    encoded = str(response.get("data") or "")
                else:
                    encoded = str(body.get("data") or "")
                data = _decode_base64url(encoded) if encoded else b""
            except Exception:
                failed_extract += 1
                continue
            if not data or len(data) > _MAX_ATTACHMENT_BYTES:
                skipped_size += 1
                continue

            text = _extract(filename, str(part.get("mimeType") or ""), data)
            if not text:
                failed_extract += 1
                continue

            participants: list[tuple[str, str, float]] = [(parent_email_id, "parent_email", 1.0)]
            if sender_id:
                participants.append((sender_id, "sender", 1.0))
            record_knowledge_source(
                "gmail_attachment",
                f"{message_id}:{attachment_ref}",
                title=filename,
                text=text,
                occurred_at=date_raw or None,
                metadata={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "attachment_ref": attachment_ref,
                    "filename": filename,
                    "mime_type": str(part.get("mimeType") or "")[:200],
                    "email_subject": subject,
                    "sender": raw_sender,
                    "bytes": len(data),
                    "text_chars": len(text),
                },
                participants=participants,
            )
            indexed += 1

    return {
        "ok": True,
        "messages": messages,
        "indexed": indexed,
        "skipped_unsupported_type": skipped_type,
        "skipped_oversize": skipped_size,
        "failed_or_no_text": failed_extract,
        "max_attachment_bytes": _MAX_ATTACHMENT_BYTES,
        "allowed_extensions": sorted(_ALLOWED_EXTENSIONS),
    }


def status() -> dict[str, Any]:
    return {
        "enabled": True,
        "read_only": True,
        "executes_attachments": False,
        "allowed_extensions": sorted(_ALLOWED_EXTENSIONS),
        "max_attachment_bytes": _MAX_ATTACHMENT_BYTES,
        "max_text_chars": _MAX_TEXT_CHARS,
        "preserves_thread_identity": True,
    }
