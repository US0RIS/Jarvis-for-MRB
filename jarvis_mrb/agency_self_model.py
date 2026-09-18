from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


VALID_KINDS = {
    "fact",
    "preference",
    "policy",
    "objective",
    "tradeoff",
    "decision",
    "correction",
}


_EXPLICIT_SOURCE_KINDS = {
    "explicit_user",
    "user_correction",
    "explicit_policy",
}
_INFERRED_SOURCE_KINDS = {
    "inferred",
    "inferred_behavior",
    "model_inference",
    "decision_history",
}


def _source_authority(source_kind: str) -> int:
    clean = str(source_kind or "").strip().lower()
    if clean in _EXPLICIT_SOURCE_KINDS:
        return 3
    if clean in _INFERRED_SOURCE_KINDS:
        return 1
    # Imported/other attributed sources may inform planning, but cannot silently
    # outrank direct user statements.
    return 2


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(str(raw or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agency_self_model_entries (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            entry_key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'current',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agency_self_model_current
            ON agency_self_model_entries(kind,entry_key,state,updated_at DESC);
        """
    )
    conn.commit()
    return conn


def upsert(
    kind: str,
    key: str,
    value: Any,
    *,
    confidence: float = 1.0,
    source_kind: str = "explicit_user",
    source_ref: str = "",
) -> dict[str, Any]:
    clean_kind = str(kind or "").strip().lower()
    if clean_kind not in VALID_KINDS:
        raise ValueError(f"Self-model kind must be one of {sorted(VALID_KINDS)}.")
    clean_key = " ".join(str(key or "").split())[:500]
    if not clean_key:
        raise ValueError("Self-model key is empty.")
    bounded_confidence = max(0.0, min(float(confidence), 1.0))
    now = _now()
    entry_id = f"self-model:{uuid.uuid4()}"
    ref = str(source_ref or "").strip()[:1000] or entry_id

    incoming_source = str(source_kind or "explicit_user")[:120]
    with _connect() as conn:
        current = conn.execute(
            """
            SELECT * FROM agency_self_model_entries
            WHERE kind=? AND entry_key=? AND state='current'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (clean_kind, clean_key),
        ).fetchone()

        incoming_authority = _source_authority(incoming_source)
        current_authority = (
            _source_authority(str(current["source_kind"]))
            if current is not None else -1
        )
        preserve_current = bool(
            current is not None
            and (
                incoming_authority < current_authority
                or (
                    incoming_authority == current_authority == 1
                    and bounded_confidence < float(current["confidence"] or 0.0)
                )
            )
        )

        if not preserve_current:
            conn.execute(
                """
                UPDATE agency_self_model_entries
                SET state='superseded',updated_at=?
                WHERE kind=? AND entry_key=? AND state='current'
                """,
                (now, clean_kind, clean_key),
            )

        conn.execute(
            """
            INSERT INTO agency_self_model_entries(
                id,kind,entry_key,value_json,confidence,source_kind,source_ref,state,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entry_id,
                clean_kind,
                clean_key,
                json.dumps(value, ensure_ascii=False, sort_keys=True),
                bounded_confidence,
                incoming_source,
                ref,
                "superseded" if preserve_current else "current",
                now,
                now,
            ),
        )
        conn.commit()
    return get(clean_kind, clean_key) or {}


def get(kind: str, key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM agency_self_model_entries
            WHERE kind=? AND entry_key=? AND state='current'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (str(kind).strip().lower(), " ".join(str(key or "").split())[:500]),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["value"] = _loads(str(item.pop("value_json")), None)
    return item


def list_entries(
    *,
    kind: str | None = None,
    include_superseded: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if kind:
        clauses.append("kind=?")
        params.append(str(kind).strip().lower())
    if not include_superseded:
        clauses.append("state='current'")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(max(1, min(int(limit), 1000)))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM agency_self_model_entries{where} ORDER BY updated_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["value"] = _loads(str(item.pop("value_json")), None)
        result.append(item)
    return result


def record_correction(
    key: str,
    *,
    prior: Any,
    corrected: Any,
    reason: str,
    confidence: float = 1.0,
    source_ref: str = "",
) -> dict[str, Any]:
    return upsert(
        "correction",
        key,
        {
            "prior": prior,
            "corrected": corrected,
            "reason": " ".join(str(reason or "").split())[:2000],
        },
        confidence=confidence,
        source_kind="user_correction",
        source_ref=source_ref,
    )


def decision_context(*, limit_per_kind: int = 20) -> dict[str, list[dict[str, Any]]]:
    """Return explicit categories without flattening them into a personality blob."""
    result: dict[str, list[dict[str, Any]]] = {}
    for kind in ("policy", "objective", "tradeoff", "preference", "correction", "fact", "decision"):
        result[kind] = list_entries(kind=kind, limit=limit_per_kind)
    return result


def authority_for(tool: str) -> dict[str, Any]:
    """Authority always comes from permissions, never inferred preferences."""
    from jarvis_mrb.permissions import decide

    decision = decide(str(tool))
    return {
        "tool": str(tool),
        "allowed": bool(decision.allowed),
        "requires_confirmation": bool(decision.needs_confirmation),
        "risk": str(decision.risk),
        "authority_source": "permissions",
        "self_model_can_override": False,
    }


def compact_context(*, max_chars: int = 8000) -> str:
    sections: list[str] = []
    for kind in ("policy", "objective", "tradeoff", "preference", "correction"):
        entries = list_entries(kind=kind, limit=12)
        if not entries:
            continue
        lines = []
        for item in entries:
            lines.append(
                f"- {item['entry_key']}: {json.dumps(item['value'], ensure_ascii=False)} "
                f"(confidence={float(item['confidence']):.2f}, source={item['source_kind']}:{item['source_ref']})"
            )
        sections.append(kind.upper() + "\n" + "\n".join(lines))
    return "\n\n".join(sections)[:max_chars]


def status() -> dict[str, Any]:
    with _connect() as conn:
        counts = {
            str(row["kind"]): int(row["count"])
            for row in conn.execute(
                "SELECT kind,COUNT(*) AS count FROM agency_self_model_entries WHERE state='current' GROUP BY kind"
            ).fetchall()
        }
    return {
        "ready": True,
        "kinds": sorted(VALID_KINDS),
        "current_entries": counts,
        "authority_source": "permissions",
    }
