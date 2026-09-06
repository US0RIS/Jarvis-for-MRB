from __future__ import annotations

import difflib
import json
import re
import sqlite3
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import PurePath
from typing import Any

from jarvis_mrb.world_model import DB_PATH, record_event

_VERSION_WORDS = {
    "draft", "revised", "revision", "rev", "updated", "update", "final", "clean",
    "redline", "blackline", "markup", "marked", "execution", "executed", "signed",
    "copy", "new", "latest", "working",
}
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "shall", "will", "into", "upon",
    "such", "any", "each", "other", "agreement", "section", "party", "parties",
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
    conn.execute("PRAGMA busy_timeout=10000")
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


def _parse_time(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        try:
            value = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone()


def _event_chronology(item: dict[str, Any]) -> tuple[float, int]:
    occurred = _parse_time(str(item.get("occurred_at") or ""))
    return (occurred.timestamp() if occurred is not None else 0.0, int(item.get("event_id") or 0))


def _family_key(filename: str) -> str:
    path = PurePath(str(filename or "document"))
    stem = path.stem.lower()
    stem = re.sub(r"\([^)]*\)$", " ", stem)
    stem = re.sub(r"\b(?:v|ver|version)[-_ ]?\d+(?:\.\d+)*\b", " ", stem)
    stem = re.sub(r"\b20\d{2}[-_. ]\d{1,2}[-_. ]\d{1,2}\b", " ", stem)
    stem = re.sub(r"\b\d{1,2}[-_. ]\d{1,2}[-_. ]20\d{2}\b", " ", stem)
    tokens = [token for token in re.findall(r"[a-z0-9]+", stem) if token not in _VERSION_WORDS]
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
    seen: set[str] = set()
    for value in values:
        normalized = value.lower()
        if normalized not in seen:
            seen.add(normalized)
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
        if old is None or similarity < 0.58 or old == new:
            continue
        old_numbers = _numbers(old)
        new_numbers = _numbers(new)
        numeric_change = old_numbers != new_numbers and bool(old_numbers or new_numbers)
        if not numeric_change and similarity < 0.82:
            continue
        key = (old[:220], new[:220])
        if key in seen:
            continue
        seen.add(key)
        changes.append(
            {
                "old": old[:1400], "new": new[:1400], "similarity": round(similarity, 3),
                "numeric_change": numeric_change, "old_numbers": old_numbers, "new_numbers": new_numbers,
            }
        )
        if len(changes) >= max(1, min(int(limit), 20)):
            break
    changes.sort(key=lambda item: (not bool(item["numeric_change"]), -float(item["similarity"])))
    return changes


def _attachment_events() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM events WHERE event_type='knowledge.gmail_attachment' ORDER BY id ASC").fetchall()
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
                "event_id": int(row["id"]), "occurred_at": str(row["occurred_at"]),
                "title": title, "text": text, "metadata": metadata,
                "source_ref": str(row["source_ref"]), "family": _family_key(title),
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


def _project_ids_for_event(event_id: int) -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ee.entity_id FROM event_entities ee JOIN entities e ON e.id=ee.entity_id WHERE ee.event_id=? AND e.kind='project'",
            (int(event_id),),
        ).fetchall()
    return {str(row["entity_id"]) for row in rows}


def _participants_for_attachment(event_id: int) -> list[tuple[str, str, float]]:
    with _connect() as conn:
        rows = conn.execute("SELECT entity_id,role,confidence FROM event_entities WHERE event_id=?", (int(event_id),)).fetchall()
    result: list[tuple[str, str, float]] = []
    for row in rows:
        role = str(row["role"])
        if role in {"sender", "mentioned"}:
            result.append((str(row["entity_id"]), role, float(row["confidence"])))
    return result


def _content_tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]{3,}", str(text or "").lower()[:25_000])
        if token not in _STOP and not token.isdigit()
    }


def _lineage_score(older: dict[str, Any], newer: dict[str, Any]) -> float:
    score = 0.0
    old_meta = older.get("metadata") if isinstance(older.get("metadata"), dict) else {}
    new_meta = newer.get("metadata") if isinstance(newer.get("metadata"), dict) else {}
    old_thread = str(old_meta.get("thread_id") or "")
    new_thread = str(new_meta.get("thread_id") or "")
    if old_thread and new_thread and old_thread == new_thread:
        score += 1.5
    if _project_ids_for_event(int(older["event_id"])) & _project_ids_for_event(int(newer["event_id"])):
        score += 1.5
    old_tokens = _content_tokens(str(older["text"]))
    new_tokens = _content_tokens(str(newer["text"]))
    if old_tokens and new_tokens:
        union = old_tokens | new_tokens
        score += min(2.0, (len(old_tokens & new_tokens) / max(1, len(union))) * 3.0)
    old_subject = re.sub(r"^(?:re|fw|fwd):\s*", "", str(old_meta.get("email_subject") or "").lower())
    new_subject = re.sub(r"^(?:re|fw|fwd):\s*", "", str(new_meta.get("email_subject") or "").lower())
    if old_subject and new_subject and old_subject == new_subject:
        score += 0.4
    return score


def _best_predecessor(members: list[dict[str, Any]], newer_index: int) -> tuple[dict[str, Any] | None, float]:
    newer = members[newer_index]
    candidates = members[max(0, newer_index - 6):newer_index]
    best: dict[str, Any] | None = None
    best_score = 0.0
    for older in reversed(candidates):
        score = _lineage_score(older, newer)
        if score > best_score:
            best, best_score = older, score
    return (best, best_score) if best is not None and best_score >= 1.15 else (None, best_score)


def _record_supersession(new_doc: str | None, old_doc: str | None, event_id: int, confidence: float) -> None:
    if not new_doc or not old_doc or new_doc == old_doc:
        return
    try:
        from jarvis_mrb.world_linker import status as linker_status
        linker_status()
    except Exception:
        return
    now = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id,confidence FROM entity_relations WHERE subject_id=? AND predicate='supersedes' AND object_id=?",
            (new_doc, old_doc),
        ).fetchone()
        if row:
            relation_id = int(row["id"])
            conn.execute(
                "UPDATE entity_relations SET confidence=?,state='current',last_seen_at=? WHERE id=?",
                (max(float(row["confidence"]), confidence), now, relation_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO entity_relations(subject_id,predicate,object_id,confidence,state,first_seen_at,last_seen_at,evidence_count) VALUES(?,?,?,?,?,?,?,0)",
                (new_doc, "supersedes", old_doc, confidence, "current", now, now),
            )
            relation_id = int(cursor.lastrowid)
        before = conn.total_changes
        conn.execute(
            "INSERT OR IGNORE INTO relation_evidence(relation_id,event_id,confidence,explanation) VALUES(?,?,?,?)",
            (relation_id, int(event_id), confidence, "Deterministic document-family lineage and local text comparison."),
        )
        if conn.total_changes > before:
            conn.execute("UPDATE entity_relations SET evidence_count=evidence_count+1 WHERE id=?", (relation_id,))
        conn.commit()


def repair_pair_chronology() -> dict[str, int]:
    """Remove legacy pairs whose predecessor/successor direction followed ingestion ID."""
    events = {int(item["event_id"]): item for item in _attachment_events()}
    with _connect() as conn:
        rows = conn.execute("SELECT older_event_id,newer_event_id FROM document_version_pairs").fetchall()
    repaired = 0
    for row in rows:
        older_id = int(row["older_event_id"])
        newer_id = int(row["newer_event_id"])
        older = events.get(older_id)
        newer = events.get(newer_id)
        if older is None or newer is None or _event_chronology(older) <= _event_chronology(newer):
            continue

        # The legacy pair created the opposite supersession edge: the row's `newer`
        # document (actually older in source time) superseded the row's `older` one.
        wrong_subject = _document_entity_id(str(newer["source_ref"]))
        wrong_object = _document_entity_id(str(older["source_ref"]))
        with _connect() as conn:
            conn.execute(
                "DELETE FROM document_version_pairs WHERE older_event_id=? AND newer_event_id=?",
                (older_id, newer_id),
            )
            if wrong_subject and wrong_object:
                conn.execute(
                    "UPDATE entity_relations SET state='retired',last_seen_at=? WHERE subject_id=? AND predicate='supersedes' AND object_id=? AND state='current'",
                    (datetime.now().astimezone().isoformat(), wrong_subject, wrong_object),
                )
            conn.commit()
        repaired += 1
    return {"repaired": repaired}


def refresh(limit_pairs: int = 50) -> dict[str, Any]:
    """Compare likely predecessor/successor attachments in real source chronology."""
    events = _attachment_events()
    families: dict[str, list[dict[str, Any]]] = {}
    for item in events:
        if item["family"]:
            families.setdefault(str(item["family"]), []).append(item)

    compared = changed = numeric_changes = rejected_lineage = 0
    generated_events: list[int] = []

    for family, members in families.items():
        if len(members) < 2:
            continue
        members.sort(key=_event_chronology)
        for newer_index in range(1, len(members)):
            newer = members[newer_index]
            older, lineage_score = _best_predecessor(members, newer_index)
            if older is None:
                rejected_lineage += 1
                continue
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

            if passages:
                changed += 1
                headline = next((item for item in passages if item["numeric_change"]), passages[0])
                if headline["numeric_change"]:
                    old_values = ", ".join(headline["old_numbers"][:5]) or "none"
                    new_values = ", ".join(headline["new_numbers"][:5]) or "none"
                    summary = (
                        f"New version of {newer['title']} changes numeric/date terms: "
                        f"{old_values} -> {new_values}. Changed passage: {headline['new'][:700]}"
                    )
                else:
                    summary = f"New version of {newer['title']} contains changed language: {headline['new'][:900]}"
                event_type = "document.version_changed"
                confidence = 0.93 if number_count else 0.82
            else:
                summary = f"New version of {newer['title']} appears textually equivalent in the compared passages."
                event_type = "document.version_equivalent"
                confidence = 0.78

            comparison_event_id = record_event(
                event_type,
                summary,
                source_kind="document_diff",
                source_ref=f"{older['source_ref']}->{newer['source_ref']}",
                occurred_at=str(newer["occurred_at"]),
                payload={
                    "family": family,
                    "lineage_score": round(lineage_score, 3),
                    "older": {"event_id": older["event_id"], "title": older["title"], "source_ref": older["source_ref"]},
                    "newer": {"event_id": newer["event_id"], "title": newer["title"], "source_ref": newer["source_ref"]},
                    "changes": passages,
                    "numeric_change_count": number_count,
                },
                evidence="Deterministic local lineage check and comparison of extracted Gmail attachment text. Version direction is based on source occurred_at with event ID only as a tie-breaker; numeric/date changes are prioritized.",
                confidence=confidence,
                participants=participants,
            )
            generated_events.append(comparison_event_id)
            _record_supersession(new_doc, old_doc, comparison_event_id, min(0.98, 0.82 + min(lineage_score, 2.0) * 0.06))

            with _connect() as conn:
                conn.execute(
                    "INSERT INTO document_version_pairs(older_event_id,newer_event_id,family_key,comparison_event_id,compared_at) VALUES(?,?,?,?,?)",
                    (int(older["event_id"]), int(newer["event_id"]), family, comparison_event_id, datetime.now().astimezone().isoformat()),
                )
                conn.commit()
            if compared >= max(1, min(int(limit_pairs), 200)):
                return {
                    "families": len(families), "pairs_compared": compared, "pairs_with_changes": changed,
                    "numeric_change_passages": numeric_changes, "lineage_candidates_rejected": rejected_lineage,
                    "generated_event_ids": generated_events,
                }

    return {
        "families": len(families), "pairs_compared": compared, "pairs_with_changes": changed,
        "numeric_change_passages": numeric_changes, "lineage_candidates_rejected": rejected_lineage,
        "generated_event_ids": generated_events,
    }


def status() -> dict[str, Any]:
    with _connect() as conn:
        pairs = int(conn.execute("SELECT COUNT(*) FROM document_version_pairs").fetchone()[0])
        changes = int(
            conn.execute(
                "SELECT COUNT(*) FROM document_version_pairs p JOIN events e ON e.id=p.comparison_event_id WHERE e.event_type='document.version_changed'"
            ).fetchone()[0]
        )
    return {
        "compared_version_pairs": pairs,
        "version_pairs_with_changes": changes,
        "numeric_date_change_detection": True,
        "lineage_uses_thread_project_and_text_overlap": True,
        "chronology_uses_occurred_at": True,
        "supersession_edges": True,
        "legacy_reversed_pair_repair": True,
        "deterministic_text_comparison": True,
        "executes_documents": False,
    }
