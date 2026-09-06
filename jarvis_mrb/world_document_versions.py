from __future__ import annotations

import difflib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import PurePath
from typing import Any

from jarvis_mrb.world_model import DB_PATH, record_event

_VERSION_WORDS = {
    "draft", "revised", "revision", "rev", "updated", "update", "final", "clean",
    "redline", "blackline", "markup", "marked", "execution", "executed", "signed",
    "copy", "new", "latest", "working",
}
_NUMBER_RE = re.compile(
    r"(?<!\w)(?:[$€£]\s*)?\d[\d,]*(?:\.\d+)?\s*(?:%|percent|bps?|x|days?|months?|years?)?(?!\w)",
    flags=re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b",
    flags=re.IGNORECASE,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS document_version_pairs (
            older_event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            newer_event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            family_key TEXT NOT NULL,
            comparison_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
            compared_at TEXT NOT NULL,
            PRIMARY KEY(older_event_id,newer_event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_document_version_family
            ON document_version_pairs(family_key,newer_event_id DESC);
        """
    )
    conn.commit()
    return conn


def _loads(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _family_key(filename: str) -> str:
    path = PurePath(str(filename or "document"))
    stem = path.stem.lower()
    stem = re.sub(r"\([^)]*\)$", " ", stem)
    stem = re.sub(r"\b(?:v|ver|version)[-_ ]?\d+(?:\.\d+)*\b", " ", stem)
    stem = re.sub(r"\b20\d{2}[-_. ]\d{1,2}[-_. ]\d{1,2}\b", " ", stem)
    stem = re.sub(r"\b\d{1,2}[-_. ]\d{1,2}[-_. ]20\d{2}\b", " ", stem)
    tokens = [token for token in re.findall(r"[a-z0-9]+", stem) if token not in _VERSION_WORDS]
    # Do not let an over-aggressive normalizer collapse unrelated generic files.
    if len(tokens) < 2:
        tokens = re.findall(r"[a-z0-9]+", path.stem.lower())
    return " ".join(tokens[:20])[:300]


def _segments(text: str) -> list[str]:
    cleaned = str(text or "").replace("\r", "\n")
    raw_parts = re.split(r"\n+|(?<=[.;:!?])\s+(?=[A-Z0-9(])", cleaned)
    segments: list[str] = []
    for part in raw_parts:
        value = " ".join(part.split()).strip()
        if len(value) < 20:
            continue
        if len(value) <= 900:
            segments.append(value)
            continue
        # Long extracted paragraphs are chunked on semicolons/numbered clauses while
        # preserving enough local text for high-overlap version matching.
        subparts = re.split(r"(?<=;)\s+|(?=\(\w{1,3}\)\s)|(?=\d+\.\s)", value)
        buffer = ""
        for sub in subparts:
            candidate = (buffer + " " + sub).strip()
            if len(candidate) <= 700:
                buffer = candidate
            else:
                if len(buffer) >= 20:
                    segments.append(buffer)
                buffer = sub[:900]
        if len(buffer) >= 20:
            segments.append(buffer)
    return segments[:1000]


def _numbers(text: str) -> list[str]:
    values = [" ".join(match.group(0).split()) for match in _NUMBER_RE.finditer(text)]
    values.extend(" ".join(match.group(0).split()) for match in _DATE_RE.finditer(text))
    result: list[str] = []
    for value in values:
        normalized = value.lower()
        if normalized not in {item.lower() for item in result}:
            result.append(value)
    return result[:20]


def _normalized_for_similarity(text: str) -> str:
    value = _NUMBER_RE.sub(" <NUM> ", text.lower())
    value = _DATE_RE.sub(" <DATE> ", value)
    value = re.sub(r"[^a-z0-9<>]+", " ", value)
    return " ".join(value.split())


def _best_old_segment(new_segment: str, old_segments: list[str]) -> tuple[str | None, float]:
    target = _normalized_for_similarity(new_segment)
    if len(target) < 15:
        return (None, 0.0)
    best: str | None = None
    best_score = 0.0
    new_words = set(target.split())
    for old in old_segments:
        old_norm = _normalized_for_similarity(old)
        if not old_norm:
            continue
        old_words = set(old_norm.split())
        if len(new_words & old_words) < 3:
            continue
        ratio = difflib.SequenceMatcher(None, old_norm, target, autojunk=False).ratio()
        if ratio > best_score:
            best_score = ratio
            best = old
    return (best, best_score)


def _changed_passages(old_text: str, new_text: str, limit: int = 8) -> list[dict[str, Any]]:
    old_segments = _segments(old_text)
    new_segments = _segments(new_text)
    changes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for new in new_segments:
        old, similarity = _best_old_segment(new, old_segments)
        if old is None or similarity < 0.58:
            continue
        if old == new:
            continue
        old_numbers = _numbers(old)
        new_numbers = _numbers(new)
        numeric_change = old_numbers != new_numbers and bool(old_numbers or new_numbers)
        # For non-numeric edits require very high structural similarity so this does
        # not mislabel merely related clauses as versions of the same clause.
        if not numeric_change and similarity < 0.82:
            continue
        key = (old[:220], new[:220])
        if key in seen:
            continue
        seen.add(key)
        changes.append(
            {
                "old": old[:1400],
                "new": new[:1400],
                "similarity": round(similarity, 3),
                "numeric_change": numeric_change,
                "old_numbers": old_numbers,
                "new_numbers": new_numbers,
            }
        )
        if len(changes) >= max(1, min(int(limit), 20)):
            break
    changes.sort(key=lambda item: (not bool(item["numeric_change"]), -float(item["similarity"])))
    return changes


def _attachment_events() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE event_type='knowledge.gmail_attachment' ORDER BY id ASC"
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads(str(row["payload_json"] or "{}"), {})
        if not isinstance(payload, dict):
            continue
        title = str(payload.get("title") or "")
        text = str(payload.get("text") or "")
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if not title or not text:
            continue
        result.append(
            {
                "event_id": int(row["id"]),
                "occurred_at": str(row["occurred_at"]),
                "title": title,
                "text": text,
                "metadata": metadata,
                "source_ref": str(row["source_ref"]),
                "family": _family_key(title),
            }
        )
    return result


def _document_entity_id(source_ref: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT entity_id FROM external_ids WHERE namespace='gmail_attachment' AND external_id=?",
            (source_ref,),
        ).fetchone()
    return str(row["entity_id"]) if row else None


def _participants_for_attachment(event_id: int) -> list[tuple[str, str, float]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT entity_id,role,confidence FROM event_entities WHERE event_id=?",
            (int(event_id),),
        ).fetchall()
    result: list[tuple[str, str, float]] = []
    for row in rows:
        role = str(row["role"])
        if role in {"sender", "mentioned"}:
            result.append((str(row["entity_id"]), role, float(row["confidence"])))
    return result


def refresh(limit_pairs: int = 50) -> dict[str, Any]:
    """Compare consecutive Gmail attachments that look like versions of one file."""
    events = _attachment_events()
    families: dict[str, list[dict[str, Any]]] = {}
    for item in events:
        if item["family"]:
            families.setdefault(str(item["family"]), []).append(item)

    compared = 0
    changed = 0
    numeric_changes = 0
    generated_events: list[int] = []

    for family, members in families.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda item: int(item["event_id"]))
        for older, newer in zip(members, members[1:]):
            with _connect() as conn:
                existing = conn.execute(
                    "SELECT comparison_event_id FROM document_version_pairs WHERE older_event_id=? AND newer_event_id=?",
                    (int(older["event_id"]), int(newer["event_id"])),
                ).fetchone()
            if existing:
                continue
            compared += 1
            passages = _changed_passages(str(older["text"]), str(newer["text"]), limit=8)
            number_count = sum(1 for item in passages if item["numeric_change"])
            numeric_changes += number_count

            old_doc = _document_entity_id(str(older["source_ref"]))
            new_doc = _document_entity_id(str(newer["source_ref"]))
            participants: list[tuple[str, str, float]] = []
            if old_doc:
                participants.append((old_doc, "previous_version", 1.0))
            if new_doc:
                participants.append((new_doc, "new_version", 1.0))
            participants.extend(_participants_for_attachment(int(newer["event_id"])))

            comparison_event_id: int | None = None
            if passages:
                changed += 1
                headline = next((item for item in passages if item["numeric_change"]), passages[0])
                if headline["numeric_change"]:
                    old_values = ", ".join(headline["old_numbers"][:5]) or "none"
                    new_values = ", ".join(headline["new_numbers"][:5]) or "none"
                    summary = (
                        f"New version of {newer['title']} changes numeric/date terms: "
                        f"{old_values} -> {new_values}. "
                        f"Changed passage: {headline['new'][:700]}"
                    )
                else:
                    summary = f"New version of {newer['title']} contains changed language: {headline['new'][:900]}"

                comparison_event_id = record_event(
                    "document.version_changed",
                    summary,
                    source_kind="document_diff",
                    source_ref=f"{older['source_ref']}->{newer['source_ref']}",
                    occurred_at=str(newer["occurred_at"]),
                    payload={
                        "family": family,
                        "older": {
                            "event_id": older["event_id"],
                            "title": older["title"],
                            "source_ref": older["source_ref"],
                        },
                        "newer": {
                            "event_id": newer["event_id"],
                            "title": newer["title"],
                            "source_ref": newer["source_ref"],
                        },
                        "changes": passages,
                        "numeric_change_count": number_count,
                    },
                    evidence="Deterministic local comparison of extracted text from two Gmail attachment versions; numeric/date changes are prioritized.",
                    confidence=0.9 if number_count else 0.78,
                    participants=participants,
                )
                generated_events.append(comparison_event_id)

            with _connect() as conn:
                conn.execute(
                    "INSERT INTO document_version_pairs(older_event_id,newer_event_id,family_key,comparison_event_id,compared_at) VALUES(?,?,?,?,?)",
                    (
                        int(older["event_id"]),
                        int(newer["event_id"]),
                        family,
                        comparison_event_id,
                        datetime.now().astimezone().isoformat(),
                    ),
                )
                conn.commit()
            if compared >= max(1, min(int(limit_pairs), 200)):
                return {
                    "families": len(families),
                    "pairs_compared": compared,
                    "pairs_with_changes": changed,
                    "numeric_change_passages": numeric_changes,
                    "generated_event_ids": generated_events,
                }

    return {
        "families": len(families),
        "pairs_compared": compared,
        "pairs_with_changes": changed,
        "numeric_change_passages": numeric_changes,
        "generated_event_ids": generated_events,
    }


def status() -> dict[str, Any]:
    with _connect() as conn:
        pairs = int(conn.execute("SELECT COUNT(*) FROM document_version_pairs").fetchone()[0])
        changes = int(conn.execute("SELECT COUNT(*) FROM document_version_pairs WHERE comparison_event_id IS NOT NULL").fetchone()[0])
    return {
        "compared_version_pairs": pairs,
        "version_pairs_with_changes": changes,
        "numeric_date_change_detection": True,
        "deterministic_text_comparison": True,
        "executes_documents": False,
    }
