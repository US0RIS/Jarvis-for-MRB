from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable

from jarvis_mrb.world_model import DB_PATH


DEFAULT_INTERRUPT_THRESHOLD = 60.0


def _now_dt() -> datetime:
    return datetime.now().astimezone()


def _now() -> str:
    return _now_dt().isoformat()


def _parse_time(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone()


def _stable_key(*parts: object) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agency_attention_events (
            attention_key TEXT PRIMARY KEY,
            desired_state_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            benefit REAL NOT NULL,
            urgency REAL NOT NULL,
            confidence REAL NOT NULL,
            error_cost REAL NOT NULL,
            attention_cost REAL NOT NULL,
            score REAL NOT NULL,
            threshold REAL NOT NULL,
            decision TEXT NOT NULL,
            severity TEXT NOT NULL,
            rationale TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            emitted_count INTEGER NOT NULL DEFAULT 0,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_emitted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agency_attention_decision
            ON agency_attention_events(decision,last_seen_at DESC);
        CREATE INDEX IF NOT EXISTS idx_agency_attention_state
            ON agency_attention_events(desired_state_id,last_seen_at DESC);
        """
    )
    conn.commit()
    return conn


def attention_value(
    *,
    benefit: float,
    urgency: float,
    confidence: float,
    error_cost: float,
    attention_cost: float,
) -> float:
    """Expected-value-inspired interruption score on a roughly 0-100 scale.

    Benefit and urgency are positive values in [0,100]. Confidence scales benefit.
    Error cost captures harm if the inference is wrong; attention cost captures the
    cost of interrupting the user now.
    """
    bounded_confidence = max(0.0, min(float(confidence), 1.0))
    score = bounded_confidence * max(0.0, min(float(benefit), 100.0))
    score += 0.6 * max(0.0, min(float(urgency), 100.0))
    score -= max(0.0, min(float(error_cost), 100.0))
    score -= max(0.0, min(float(attention_cost), 100.0))
    return max(-100.0, min(score, 160.0))


def consider(
    *,
    kind: str,
    message: str,
    desired_state_id: str = "",
    dedup_key: str = "",
    benefit: float,
    urgency: float,
    confidence: float = 1.0,
    error_cost: float = 0.0,
    attention_cost: float = 20.0,
    threshold: float = DEFAULT_INTERRUPT_THRESHOLD,
    dedup_seconds: int = 3600,
    severity: str = "info",
    emitter: Callable[[str], None] | None = None,
    allow_emit: bool = True,
    suppress_reason: str = "",
) -> dict[str, Any]:
    clean_kind = str(kind or "agency").strip()[:120]
    clean_message = " ".join(str(message or "").split())[:3000]
    if not clean_message:
        raise ValueError("Attention candidate message is empty.")
    key = str(dedup_key or "").strip() or _stable_key(desired_state_id, clean_kind, clean_message)
    score = attention_value(
        benefit=benefit,
        urgency=urgency,
        confidence=confidence,
        error_cost=error_cost,
        attention_cost=attention_cost,
    )
    interrupt = score >= float(threshold)
    decision = "interrupt" if interrupt else "log"
    now = _now()
    duplicate = False
    should_emit = interrupt and bool(allow_emit)
    suppressed = bool(interrupt and not allow_emit)

    rationale = (
        f"score={score:.1f} = confidence({max(0.0, min(float(confidence), 1.0)):.2f})"
        f"*benefit({float(benefit):.1f}) + 0.6*urgency({float(urgency):.1f})"
        f" - error_cost({float(error_cost):.1f}) - attention_cost({float(attention_cost):.1f}); "
        f"threshold={float(threshold):.1f}"
        + (
            f"; emission_deferred={str(suppress_reason or 'attention budget').strip()[:300]}"
            if suppressed
            else ""
        )
    )

    previous_last_emitted: str | None = None
    reserved_emit_at: str | None = None
    with _connect() as conn:
        # Serialize the dedup decision and emission reservation. Without this,
        # concurrent producers can both observe last_emitted_at=NULL and interrupt.
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM agency_attention_events WHERE attention_key=?",
            (key,),
        ).fetchone()
        occurrence_count = 1
        emitted_count = 0
        first_seen = now
        last_emitted = None
        if existing is not None:
            occurrence_count = int(existing["occurrence_count"]) + 1
            emitted_count = int(existing["emitted_count"])
            first_seen = str(existing["first_seen_at"])
            last_emitted = str(existing["last_emitted_at"] or "") or None
            previous_last_emitted = last_emitted
            previous_emit = _parse_time(last_emitted)
            if previous_emit is not None and (_now_dt() - previous_emit) < timedelta(seconds=max(0, int(dedup_seconds))):
                duplicate = True
                should_emit = False

        conn.execute(
            """
            INSERT INTO agency_attention_events(
                attention_key,desired_state_id,kind,message,benefit,urgency,confidence,error_cost,
                attention_cost,score,threshold,decision,severity,rationale,occurrence_count,emitted_count,
                first_seen_at,last_seen_at,last_emitted_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(attention_key) DO UPDATE SET
                desired_state_id=excluded.desired_state_id,
                kind=excluded.kind,
                message=excluded.message,
                benefit=excluded.benefit,
                urgency=excluded.urgency,
                confidence=excluded.confidence,
                error_cost=excluded.error_cost,
                attention_cost=excluded.attention_cost,
                score=excluded.score,
                threshold=excluded.threshold,
                decision=excluded.decision,
                severity=excluded.severity,
                rationale=excluded.rationale,
                occurrence_count=excluded.occurrence_count,
                emitted_count=excluded.emitted_count,
                last_seen_at=excluded.last_seen_at,
                last_emitted_at=excluded.last_emitted_at
            """,
            (
                key,
                str(desired_state_id or "")[:300],
                clean_kind,
                clean_message,
                float(benefit),
                float(urgency),
                max(0.0, min(float(confidence), 1.0)),
                float(error_cost),
                float(attention_cost),
                score,
                float(threshold),
                decision,
                str(severity or "info")[:80],
                rationale[:2000],
                occurrence_count,
                emitted_count,
                first_seen,
                now,
                last_emitted,
            ),
        )
        if should_emit:
            reserved_emit_at = now
            conn.execute(
                """
                UPDATE agency_attention_events
                SET emitted_count=emitted_count+1,last_emitted_at=?,last_seen_at=?
                WHERE attention_key=?
                """,
                (reserved_emit_at, now, key),
            )
        conn.commit()

    emitted = False
    if should_emit:
        if emitter is None:
            from jarvis_mrb.event_bus import emit_proactive

            def emitter_fn(value: str) -> None:
                emit_proactive(value, cue="attention", severity=str(severity or "info"))
        else:
            emitter_fn = emitter
        try:
            emitter_fn(clean_message)
            emitted = True
        except Exception:
            # Release only our reservation. A later observation may retry the alert.
            if reserved_emit_at is not None:
                with _connect() as conn:
                    conn.execute(
                        """
                        UPDATE agency_attention_events
                        SET emitted_count=CASE WHEN emitted_count>0 THEN emitted_count-1 ELSE 0 END,
                            last_emitted_at=?
                        WHERE attention_key=? AND last_emitted_at=?
                        """,
                        (previous_last_emitted, key, reserved_emit_at),
                    )
                    conn.commit()
            raise

    return {
        "attention_key": key,
        "decision": decision,
        "score": score,
        "threshold": float(threshold),
        "emitted": emitted,
        "duplicate": duplicate,
        "suppressed": suppressed,
        "rationale": rationale,
    }


def list_events(*, desired_state_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        if desired_state_id:
            rows = conn.execute(
                """
                SELECT * FROM agency_attention_events
                WHERE desired_state_id=?
                ORDER BY last_seen_at DESC LIMIT ?
                """,
                (str(desired_state_id), safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agency_attention_events ORDER BY last_seen_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def status() -> dict[str, Any]:
    with _connect() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM agency_attention_events").fetchone()[0])
        interrupted = int(
            conn.execute("SELECT COUNT(*) FROM agency_attention_events WHERE emitted_count>0").fetchone()[0]
        )
    return {
        "ready": True,
        "default_interrupt_threshold": DEFAULT_INTERRUPT_THRESHOLD,
        "events": total,
        "interrupted": interrupted,
    }
