from __future__ import annotations

import hashlib
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


def is_inferred_source(source_kind: str) -> bool:
    return str(source_kind or "").strip().lower() in _INFERRED_SOURCE_KINDS


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


def approval_preference_key(tool: str) -> str:
    clean_tool = " ".join(str(tool or "").strip().lower().split())[:300]
    if not clean_tool:
        raise ValueError("Approval preference requires a tool name.")
    return f"approval_style:{clean_tool}"[:500]


def infer_approval_preference(
    tool: str,
    *,
    minimum_approvals: int = 3,
    lookback: int = 100,
) -> dict[str, Any] | None:
    """Infer a low-authority preference from repeated explicit Agency approvals.

    This never changes permission policy. It merely records that the user has
    repeatedly approved a protected tool, with the exact approval events kept as
    provenance so downstream code can distinguish inference from assertion.
    """
    clean_tool = " ".join(str(tool or "").strip().lower().split())[:300]
    if not clean_tool:
        raise ValueError("Approval-history inference requires a tool name.")
    required = max(2, min(int(minimum_approvals), 10))
    safe_lookback = max(required, min(int(lookback), 500))

    with _connect() as conn:
        try:
            rows = conn.execute(
                """
                SELECT id,payload_json,occurred_at,recorded_at
                FROM events
                WHERE event_type='agency.step.approved'
                  AND source_kind='jarvis_agency'
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_lookback,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

    approvals: list[dict[str, Any]] = []
    seen_steps: set[str] = set()
    for row in rows:
        payload = dict(_loads(str(row["payload_json"] or "{}"), {}))
        if str(payload.get("tool") or "").strip().lower() != clean_tool:
            continue
        step_id = str(payload.get("step_id") or "")
        if not step_id or step_id in seen_steps:
            continue
        seen_steps.add(step_id)
        approvals.append(
            {
                "event_id": int(row["id"]),
                "step_id": step_id,
                "desired_state_id": str(payload.get("desired_state_id") or ""),
                "occurred_at": str(row["occurred_at"] or row["recorded_at"] or ""),
            }
        )
    approvals.sort(key=lambda item: int(item["event_id"]))
    if len(approvals) < required:
        return None

    support = approvals[-min(len(approvals), 12):]
    support_ids = [int(item["event_id"]) for item in support]
    key = approval_preference_key(clean_tool)
    digest = hashlib.sha256(
        json.dumps(
            {"tool": clean_tool, "supporting_approval_event_ids": support_ids},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="replace")
    ).hexdigest()[:24]
    source_ref = f"approval-history:{digest}"
    confidence = min(0.9, 0.55 + 0.08 * len(support_ids))
    value = {
        "behavior": (
            f"routine approvals observed for {clean_tool}; "
            "may prefer fewer confirmation interruptions for routine uses"
        ),
        "tool": clean_tool,
        "supporting_approval_event_ids": support_ids,
        "authority_effect": "none",
    }
    entry = upsert(
        "preference",
        key,
        value,
        confidence=confidence,
        source_kind="inferred_behavior",
        source_ref=source_ref,
    )

    try:
        from jarvis_mrb.world_model import record_event

        record_event(
            "agency.self_model.inferred",
            (
                f"Inferred low-authority approval preference for {clean_tool} "
                f"from {len(support_ids)} explicit Agency approvals."
            ),
            source_kind="jarvis_agency",
            source_ref=source_ref,
            payload={
                "preference_key": key,
                "tool": clean_tool,
                "supporting_approval_event_ids": support_ids,
                "confidence": confidence,
                "authority_effect": "none",
            },
            evidence=(
                "Behavioral preference inference derived from explicit persisted "
                "Agency approval events; permission authority is unchanged."
            ),
            confidence=confidence,
        )
    except Exception:
        pass

    return entry


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
