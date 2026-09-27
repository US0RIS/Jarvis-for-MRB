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
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(agency_attention_events)").fetchall()}
    if "deferred_reason" not in columns:
        conn.execute("ALTER TABLE agency_attention_events ADD COLUMN deferred_reason TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def _current_meeting(now: datetime) -> str:
    """Title of a calendar event (from the synced world model) happening now."""
    import json as _json

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT e.canonical_name,
                  (SELECT value_json FROM beliefs b WHERE b.subject_id=e.id AND b.predicate='start_at' AND b.state='current' ORDER BY b.id DESC LIMIT 1) AS start_at,
                  (SELECT value_json FROM beliefs b WHERE b.subject_id=e.id AND b.predicate='end_at' AND b.state='current' ORDER BY b.id DESC LIMIT 1) AS end_at,
                  (SELECT value_json FROM beliefs b WHERE b.subject_id=e.id AND b.predicate='calendar_status' AND b.state='current' ORDER BY b.id DESC LIMIT 1) AS status
                FROM entities e
                WHERE e.id IN (SELECT subject_id FROM beliefs WHERE predicate='start_at' AND state='current')
                ORDER BY e.last_seen_at DESC LIMIT 300
                """
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return ""
    for row in rows:
        try:
            start = _parse_time(_json.loads(row["start_at"])) if row["start_at"] else None
            end = _parse_time(_json.loads(row["end_at"])) if row["end_at"] else None
            status = str(_json.loads(row["status"]) if row["status"] else "").lower()
        except (TypeError, ValueError):
            continue
        if start and end and start <= now < end and status not in {"cancelled", "canceled", "declined"}:
            return str(row["canonical_name"])
    return ""


def attention_context(now: datetime | None = None) -> str:
    """Return why a non-urgent interruption should be deferred right now, or ''."""
    instant = now or _now_dt()
    try:
        from jarvis_mrb.sensor_opportunities import quiet_reason
        reason = quiet_reason()
        if reason:
            return reason
    except Exception:
        pass
    try:
        from jarvis_mrb.environment_state import get_state
        state = get_state()
        prefs = state.get("preferences") if isinstance(state.get("preferences"), dict) else {}
        busy_until = _parse_time(str(prefs.get("busy_until") or state.get("busy_until") or ""))
        if busy_until and busy_until > instant:
            return f"you asked not to be interrupted until {busy_until.isoformat(timespec='minutes')}"
    except Exception:
        pass
    meeting = _current_meeting(instant)
    if meeting:
        return f"you are in the calendar event {meeting!r}"
    return ""


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
    deferred_reason = ""
    if interrupt and allow_emit and str(severity or "").lower() not in {"urgent", "critical"}:
        context = attention_context()
        if context:
            allow_emit = False
            deferred_reason = context
            suppress_reason = f"deferred while {context}"
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
        conn.execute(
            "UPDATE agency_attention_events SET deferred_reason=? WHERE attention_key=? AND emitted_count=0",
            (deferred_reason[:300], key),
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
        "deferred_reason": deferred_reason,
        "rationale": rationale,
    }


def flush_deferred(*, max_age_hours: int = 12, emitter: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Deliver interruptions that were deferred for context once it has cleared.

    Each deferred item is delivered at most once and only if still recent; it is
    never delivered while the deferring context persists.
    """
    context = attention_context()
    if context:
        return {"delivered": 0, "still_deferred_because": context}
    cutoff = (_now_dt() - timedelta(hours=max_age_hours)).isoformat()
    delivered = 0
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT attention_key,message,severity FROM agency_attention_events
               WHERE deferred_reason<>'' AND emitted_count=0 AND last_seen_at>=? ORDER BY last_seen_at LIMIT 10""",
            (cutoff,),
        ).fetchall()
        now = _now()
        for row in rows:
            conn.execute(
                """UPDATE agency_attention_events SET emitted_count=1,last_emitted_at=?,deferred_reason='',
                   rationale=rationale || '; delivered after deferral' WHERE attention_key=? AND emitted_count=0""",
                (now, str(row["attention_key"])),
            )
        conn.commit()
    for row in rows:
        if emitter is not None:
            emitter(str(row["message"]))
        else:
            from jarvis_mrb.event_bus import emit_proactive
            emit_proactive(str(row["message"]), cue="attention", severity=str(row["severity"] or "info"))
        delivered += 1
    return {"delivered": delivered}


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
