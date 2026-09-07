from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import jarvis_mrb.world_model as world_model
from jarvis_mrb.world_model import record_event

_TERM_PATTERNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "indemnity_cap": ("indemnity cap", (r"\bindemn(?:ity|ification)\s+cap\b.{0,100}?({VALUE})", r"\bcap\s+on\s+indemn(?:ity|ification)\b.{0,100}?({VALUE})")),
    "indemnity_basket": ("indemnity basket", (r"\bindemn(?:ity|ification)\s+basket\b.{0,100}?({VALUE})", r"\bbasket\b.{0,70}?({VALUE})")),
    "escrow": ("escrow amount", (r"\bescrow(?:\s+amount)?\b.{0,100}?({VALUE})", r"\bholdback(?:\s+amount)?\b.{0,100}?({VALUE})")),
    "survival_period": ("survival period", (r"\bsurvival(?:\s+period)?\b.{0,100}?({DURATION})", r"\brepresentations?.{0,60}?surviv(?:e|al)\b.{0,80}?({DURATION})")),
    "termination_fee": ("termination fee", (r"\btermination\s+fee\b.{0,100}?({VALUE})", r"\bbreak[- ]?up\s+fee\b.{0,100}?({VALUE})")),
    "purchase_price": ("purchase price", (r"\bpurchase\s+price\b.{0,100}?({MONEY})",)),
    "working_capital_target": ("working capital target", (r"\bworking\s+capital\s+(?:target|peg)\b.{0,100}?({MONEY})", r"\b(?:target|peg)\s+working\s+capital\b.{0,100}?({MONEY})")),
    "earnout": ("earnout", (r"\bearn[- ]?out\b.{0,100}?({VALUE})",)),
    "interest_rate": ("interest rate", (r"\binterest\s+rate\b.{0,100}?({PERCENT})", r"\brate\s+of\s+interest\b.{0,100}?({PERCENT})")),
    "ownership_percentage": ("ownership percentage", (r"\b(?:ownership|equity|stake)\b.{0,100}?({PERCENT})", r"\b({PERCENT}).{0,60}?\b(?:ownership|equity|stake)\b")),
    "deadline": ("deadline", (r"\b(?:deadline|signing|closing)\b.{0,90}?\b(?:by|on|before)\s+({DATE})",)),
}

_MONEY = r"(?:[$€£]\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:million|billion|mm|bn|m|b))?)"
_PERCENT = r"(?:\d+(?:\.\d+)?\s*(?:%|percent|bps?))"
_DURATION = r"(?:\d+(?:\.\d+)?\s*(?:business\s+)?(?:days?|weeks?|months?|years?))"
_DATE = r"(?:(?:today|tomorrow|tonight|this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?|\d{1,2}/\d{1,2}/(?:\d{2}|\d{4}))"
_GENERIC_VALUE = rf"(?:{_MONEY}|{_PERCENT}|{_DURATION}|\d[\d,]*(?:\.\d+)?)"

_SOURCE_CONFIDENCE = {
    "gmail_attachment": 0.96,
    "meeting_notes": 0.92,
    "conversation": 0.90,
    "gmail": 0.86,
    "note": 0.85,
    "calendar_enriched": 0.70,
}

_IGNORED_EVENT_PREFIXES = (
    "term.", "document.version_", "action.", "context.", "perception.", "automation.", "background.",
)


def _connect() -> sqlite3.Connection:
    # Resolve the authoritative world DB at connection time. Importing DB_PATH by
    # value makes isolated acceptance/tests/digital-twin worlds vulnerable to stale
    # paths after another temporary world is torn down.
    conn = sqlite3.connect(world_model.DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS term_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            term_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            value_text TEXT NOT NULL,
            normalized_value TEXT NOT NULL,
            context TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            source_event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            source_kind TEXT NOT NULL,
            confidence REAL NOT NULL,
            UNIQUE(project_id,term_key,normalized_value,source_event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_term_observations_project_key
            ON term_observations(project_id,term_key,id DESC);

        CREATE TABLE IF NOT EXISTS term_conflicts (
            older_observation_id INTEGER NOT NULL REFERENCES term_observations(id) ON DELETE CASCADE,
            newer_observation_id INTEGER NOT NULL REFERENCES term_observations(id) ON DELETE CASCADE,
            conflict_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(older_observation_id,newer_observation_id)
        );

        CREATE TABLE IF NOT EXISTS world_terms_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
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


def _chronology_key(row: sqlite3.Row) -> tuple[float, int, int]:
    occurred = _parse_time(str(row["occurred_at"] or ""))
    timestamp = occurred.timestamp() if occurred is not None else 0.0
    return (timestamp, int(row["source_event_id"] or 0), int(row["id"] or 0))


def _event_text(event: sqlite3.Row) -> str:
    payload = _loads(str(event["payload_json"] or "{}"), {})
    parts = [str(event["summary"] or "")]
    if isinstance(payload, dict):
        for key in ("text", "user", "assistant", "transcript_excerpt", "description", "body"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value)
        if len(parts) == 1:
            parts.append(json.dumps(payload, ensure_ascii=False)[:30_000])
    return "\n".join(parts)[:60_000]


def _project_ids(event_id: int) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ee.entity_id FROM event_entities ee JOIN entities e ON e.id=ee.entity_id WHERE ee.event_id=? AND e.kind='project'",
            (int(event_id),),
        ).fetchall()
    return [str(row["entity_id"]) for row in rows]


def _project_name(project_id: str) -> str:
    with _connect() as conn:
        row = conn.execute("SELECT canonical_name FROM entities WHERE id=?", (project_id,)).fetchone()
    return str(row["canonical_name"]) if row else project_id


def _normalize_value(value: str) -> str:
    text = " ".join(str(value or "").lower().split()).replace(",", "")
    text = re.sub(r"\bpercent\b", "%", text)
    text = re.sub(r"\bbasis\s+points?\b", "bps", text)
    return text.strip(" .,:;()[]")[:300]


def _expanded_pattern(template: str) -> re.Pattern[str]:
    pattern = template.replace("{MONEY}", _MONEY).replace("{PERCENT}", _PERCENT)
    pattern = pattern.replace("{DURATION}", _DURATION).replace("{DATE}", _DATE).replace("{VALUE}", _GENERIC_VALUE)
    return re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)


def _context_window(text: str, start: int, end: int) -> str:
    left = max(0, start - 180)
    right = min(len(text), end + 180)
    return " ".join(text[left:right].split())[:700]


def extract_terms(text: str) -> list[dict[str, str]]:
    value = str(text or "")
    if not value.strip():
        return []
    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for term_key, (display_name, templates) in _TERM_PATTERNS.items():
        for template in templates:
            for match in _expanded_pattern(template).finditer(value):
                captured = next((group for group in reversed(match.groups()) if group), "")
                captured = " ".join(str(captured).split())[:300]
                normalized = _normalize_value(captured)
                if not normalized:
                    continue
                key = (term_key, normalized)
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "term_key": term_key,
                    "display_name": display_name,
                    "value_text": captured,
                    "normalized_value": normalized,
                    "context": _context_window(value, match.start(), match.end()),
                })
                if len(results) >= 30:
                    return results
    return results


def _source_label(observation: sqlite3.Row) -> str:
    return f"{observation['source_kind']} at {observation['occurred_at']}"


def _ordered_pair(first: sqlite3.Row, second: sqlite3.Row) -> tuple[sqlite3.Row, sqlite3.Row]:
    return (first, second) if _chronology_key(first) <= _chronology_key(second) else (second, first)


def _create_conflict(first: sqlite3.Row, second: sqlite3.Row) -> int | None:
    older, newer = _ordered_pair(first, second)
    if str(older["normalized_value"]) == str(newer["normalized_value"]):
        return None
    with _connect() as conn:
        existing = conn.execute(
            "SELECT conflict_event_id FROM term_conflicts WHERE older_observation_id=? AND newer_observation_id=?",
            (int(older["id"]), int(newer["id"])),
        ).fetchone()
    if existing:
        return int(existing["conflict_event_id"]) if existing["conflict_event_id"] else None

    project_id = str(newer["project_id"])
    project_name = _project_name(project_id)
    summary = (
        f"{project_name} term changed or conflicts across sources: {newer['display_name']} is "
        f"{newer['value_text']} in {_source_label(newer)}, versus {older['value_text']} in {_source_label(older)}."
    )
    event_id = record_event(
        "term.changed_or_conflicted",
        summary,
        source_kind="term_ledger",
        source_ref=f"{older['id']}->{newer['id']}",
        occurred_at=str(newer["occurred_at"]),
        payload={
            "project_id": project_id,
            "term_key": str(newer["term_key"]),
            "display_name": str(newer["display_name"]),
            "older": {
                "observation_id": int(older["id"]), "value": str(older["value_text"]),
                "source_event_id": int(older["source_event_id"]), "source_kind": str(older["source_kind"]),
                "occurred_at": str(older["occurred_at"]), "context": str(older["context"]),
            },
            "newer": {
                "observation_id": int(newer["id"]), "value": str(newer["value_text"]),
                "source_event_id": int(newer["source_event_id"]), "source_kind": str(newer["source_kind"]),
                "occurred_at": str(newer["occurred_at"]), "context": str(newer["context"]),
            },
        },
        evidence="Deterministic project-term extraction found different explicit values for the same named term in two provenance-bearing sources. Source chronology is based on occurred_at, not ingestion order. This is a possible change/conflict, not an assertion that either source is authoritative.",
        confidence=min(float(older["confidence"]), float(newer["confidence"])),
        participants=[(project_id, "project", 1.0)],
    )
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO term_conflicts(older_observation_id,newer_observation_id,conflict_event_id,created_at) VALUES(?,?,?,?)",
            (int(older["id"]), int(newer["id"]), event_id, datetime.now().astimezone().isoformat()),
        )
        conn.commit()
    return event_id


def _adjacent_observations(project_id: str, term_key: str, observation_id: int) -> tuple[sqlite3.Row | None, sqlite3.Row | None, sqlite3.Row | None]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM term_observations WHERE project_id=? AND term_key=?",
            (project_id, term_key),
        ).fetchall()
    ordered = sorted(rows, key=_chronology_key)
    for index, row in enumerate(ordered):
        if int(row["id"]) == int(observation_id):
            previous = ordered[index - 1] if index > 0 else None
            following = ordered[index + 1] if index + 1 < len(ordered) else None
            return previous, row, following
    return None, None, None


def repair_conflict_chronology() -> dict[str, int]:
    """Canonicalize legacy conflict pairs that were ordered by ingestion ID."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT older_observation_id,newer_observation_id FROM term_conflicts"
        ).fetchall()
    repaired = 0
    for pair in rows:
        with _connect() as conn:
            first = conn.execute("SELECT * FROM term_observations WHERE id=?", (int(pair["older_observation_id"]),)).fetchone()
            second = conn.execute("SELECT * FROM term_observations WHERE id=?", (int(pair["newer_observation_id"]),)).fetchone()
        if first is None or second is None:
            continue
        older, newer = _ordered_pair(first, second)
        if int(older["id"]) == int(pair["older_observation_id"]):
            continue
        with _connect() as conn:
            conn.execute(
                "DELETE FROM term_conflicts WHERE older_observation_id=? AND newer_observation_id=?",
                (int(pair["older_observation_id"]), int(pair["newer_observation_id"])),
            )
            conn.commit()
        _create_conflict(older, newer)
        repaired += 1
    return {"repaired": repaired}


def observe_event(event_id: int) -> dict[str, Any]:
    with _connect() as conn:
        event = conn.execute("SELECT * FROM events WHERE id=?", (int(event_id),)).fetchone()
    if event is None:
        return {"observations": 0, "conflicts": 0, "generated_event_ids": []}
    event_type = str(event["event_type"])
    if any(event_type.startswith(prefix) for prefix in _IGNORED_EVENT_PREFIXES):
        return {"observations": 0, "conflicts": 0, "generated_event_ids": []}

    projects = _project_ids(int(event_id))
    if not projects:
        return {"observations": 0, "conflicts": 0, "generated_event_ids": []}
    terms = extract_terms(_event_text(event))
    if not terms:
        return {"observations": 0, "conflicts": 0, "generated_event_ids": []}

    source_kind = str(event["source_kind"])
    confidence = float(_SOURCE_CONFIDENCE.get(source_kind, min(0.80, float(event["confidence"]))))
    generated: list[int] = []
    inserted = 0

    for project_id in projects[:5]:
        for term in terms:
            with _connect() as conn:
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO term_observations(
                        project_id,term_key,display_name,value_text,normalized_value,context,
                        occurred_at,source_event_id,source_kind,confidence
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id, term["term_key"], term["display_name"], term["value_text"],
                        term["normalized_value"], term["context"], str(event["occurred_at"]),
                        int(event_id), source_kind, confidence,
                    ),
                )
                did_insert = conn.total_changes > before
                conn.commit()
                if not did_insert:
                    continue
                new_row = conn.execute(
                    "SELECT * FROM term_observations WHERE project_id=? AND term_key=? AND normalized_value=? AND source_event_id=? ORDER BY id DESC LIMIT 1",
                    (project_id, term["term_key"], term["normalized_value"], int(event_id)),
                ).fetchone()
            if new_row is None:
                continue
            inserted += 1
            previous, current, following = _adjacent_observations(project_id, term["term_key"], int(new_row["id"]))
            for neighbor in (previous, following):
                if current is None or neighbor is None:
                    continue
                if str(current["normalized_value"]) == str(neighbor["normalized_value"]):
                    continue
                conflict_id = _create_conflict(current, neighbor)
                if conflict_id is not None and conflict_id not in generated:
                    generated.append(conflict_id)

    return {"observations": inserted, "conflicts": len(generated), "generated_event_ids": generated}


def refresh(limit: int = 2500) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 10_000))
    with _connect() as conn:
        row = conn.execute("SELECT value FROM world_terms_state WHERE key='last_event_id'").fetchone()
        last_id = int(row["value"]) if row and str(row["value"]).isdigit() else 0
        events = conn.execute("SELECT id FROM events WHERE id>? ORDER BY id ASC LIMIT ?", (last_id, safe_limit)).fetchall()

    processed = observations = conflicts = 0
    generated: list[int] = []
    newest = last_id
    for row in events:
        event_id = int(row["id"])
        result = observe_event(event_id)
        processed += 1
        observations += int(result.get("observations", 0))
        conflicts += int(result.get("conflicts", 0))
        generated.extend(int(value) for value in result.get("generated_event_ids") or [])
        newest = max(newest, event_id)

    if newest != last_id:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO world_terms_state(key,value) VALUES('last_event_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(newest),),
            )
            conn.commit()
    return {
        "processed_events": processed,
        "observations_added": observations,
        "conflicts_added": conflicts,
        "generated_event_ids": generated,
        "last_event_id": newest,
    }


def latest_observations(project_id: str, term_keys: set[str] | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        if term_keys:
            placeholders = ",".join("?" for _ in term_keys)
            rows = conn.execute(
                f"SELECT * FROM term_observations WHERE project_id=? AND term_key IN ({placeholders})",
                (project_id, *tuple(sorted(term_keys))),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM term_observations WHERE project_id=?", (project_id,)).fetchall()
    by_term: dict[str, sqlite3.Row] = {}
    for row in rows:
        key = str(row["term_key"])
        current = by_term.get(key)
        if current is None or _chronology_key(row) > _chronology_key(current):
            by_term[key] = row
    return [
        {
            "id": int(row["id"]),
            "project_id": str(row["project_id"]),
            "term_key": str(row["term_key"]),
            "display_name": str(row["display_name"]),
            "value": str(row["value_text"]),
            "normalized_value": str(row["normalized_value"]),
            "occurred_at": str(row["occurred_at"]),
            "source_kind": str(row["source_kind"]),
            "source_event_id": int(row["source_event_id"]),
            "confidence": float(row["confidence"]),
        }
        for row in sorted(by_term.values(), key=lambda item: str(item["term_key"]))
    ]


def project_terms(project_id: str) -> list[dict[str, Any]]:
    return [
        {
            "term_key": item["term_key"],
            "display_name": item["display_name"],
            "value": item["value"],
            "occurred_at": item["occurred_at"],
            "source_kind": item["source_kind"],
            "source_event_id": item["source_event_id"],
            "confidence": item["confidence"],
        }
        for item in latest_observations(project_id)
    ]


def status() -> dict[str, Any]:
    with _connect() as conn:
        observations = int(conn.execute("SELECT COUNT(*) FROM term_observations").fetchone()[0])
        conflicts = int(conn.execute("SELECT COUNT(*) FROM term_conflicts").fetchone()[0])
        row = conn.execute("SELECT value FROM world_terms_state WHERE key='last_event_id'").fetchone()
    return {
        "term_observations": observations,
        "term_conflicts": conflicts,
        "last_processed_event_id": int(row["value"]) if row and str(row["value"]).isdigit() else 0,
        "deterministic": True,
        "cross_source_conflicts": True,
        "source_provenance_retained": True,
        "chronology_uses_occurred_at": True,
        "dynamic_world_db_binding": True,
        "claims_authoritative_truth": False,
        "supported_terms": sorted(_TERM_PATTERNS),
    }
