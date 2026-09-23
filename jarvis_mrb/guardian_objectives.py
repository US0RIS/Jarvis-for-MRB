from __future__ import annotations

"""Camera-free, explicitly enrolled objective rescue.

A deadline is a user-authored expectation, not evidence of inevitable failure.
Only actual, active goal status and pending linked dependencies are evidence.
This module never executes tools, drafts outbound mail, or grants authority.
Authenticated foreground iPhone heartbeats are required for interruptions.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3
import threading
from typing import Any

from jarvis_mrb.world_model import DB_PATH

_LOCK = threading.RLock()
_PRESENCE: dict[str, datetime] = {}
_MAX_WATCHES = 30
_MAX_ACTIVE_DAYS = 365


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS guardian_objective_watches (
            id TEXT PRIMARY KEY,
            intention_id TEXT NOT NULL UNIQUE,
            goal_title TEXT NOT NULL,
            deadline_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            snoozed_until TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_checked_at TEXT NOT NULL DEFAULT '',
            last_signal TEXT NOT NULL DEFAULT '',
            last_alert_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_guardian_objectives_status
            ON guardian_objective_watches(status,deadline_at);
        """
    )
    conn.commit()
    return conn


def ingest_presence(snapshot: dict[str, Any], *, now: datetime | None = None) -> None:
    """Only after authenticated companion transport; no GPS, audio or health."""
    if not isinstance(snapshot, dict):
        return
    source = str(snapshot.get("source_id") or "")[:100]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", source):
        return
    instant = now or _now()
    observed = _stamp(snapshot.get("observed_at"))
    if observed is None or not -15 <= (instant - observed).total_seconds() <= 30:
        return
    with _LOCK:
        if snapshot.get("enabled") is True:
            previous = _PRESENCE.get(source)
            if previous is None or observed > previous:
                _PRESENCE[source] = observed
        else:
            _PRESENCE.pop(source, None)
        for key, seen in list(_PRESENCE.items()):
            if (instant - seen).total_seconds() > 90:
                _PRESENCE.pop(key, None)


def _has_live_consent(now: datetime) -> bool:
    with _LOCK:
        return any(0 <= (now - seen).total_seconds() <= 90 for seen in _PRESENCE.values())


def _active_goals(limit: int = 30) -> list[dict[str, Any]]:
    from jarvis_mrb.world_executive import active_intentions
    return active_intentions(limit=limit)


def _deadline(item: dict[str, Any], now: datetime) -> datetime | None:
    if str(item.get("source_kind") or "") != "explicit_goal":
        return None
    try:
        if float(item.get("confidence") or 0) < 0.9:
            return None
    except (ValueError, TypeError):
        return None
    timestamp = _stamp(item.get("due_at"))
    if timestamp is None or timestamp > now + timedelta(days=_MAX_ACTIVE_DAYS):
        return None
    return timestamp


def eligible(*, now: datetime | None = None) -> list[dict[str, Any]]:
    instant = now or _now()
    with _connect() as conn:
        enrolled = {
            str(row["intention_id"]): (str(row["status"]), str(row["deadline_at"]))
            for row in conn.execute(
                "SELECT intention_id,status,deadline_at FROM guardian_objective_watches"
            )
        }
    result = []
    for item in _active_goals():
        due = _deadline(item, instant)
        if due is None:
            continue
        result.append({
            "intention_id": str(item["id"]),
            "title": str(item["title"])[:180],
            "deadline_at": _iso(due),
            "enrolled": enrolled.get(str(item["id"])) == ("active", _iso(due)),
            "source": "user-authored goal / structured world intention",
        })
    return result


def enroll(intention_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    instant = now or _now()
    identifier = str(intention_id or "").strip()
    match = next((i for i in _active_goals() if str(i.get("id")) == identifier), None)
    if match is None:
        raise ValueError("The exact goal is no longer active. Refresh before enrolling.")
    due = _deadline(match, instant)
    if due is None or due < instant - timedelta(hours=1):
        raise ValueError("Only explicit active goals with a precise timezone-aware deadline are eligible.")
    with _connect() as conn:
        count = conn.execute(
            "SELECT count(*) FROM guardian_objective_watches WHERE status='active'"
        ).fetchone()[0]
        old = conn.execute(
            "SELECT id,status FROM guardian_objective_watches WHERE intention_id=?",
            (identifier,)
        ).fetchone()
        if count >= _MAX_WATCHES and (old is None or str(old["status"]) != "active"):
            raise ValueError("Guardian has reached its explicit goal-watch limit.")
        watch_id = "guardian:" + hashlib.sha256(identifier.encode()).hexdigest()[:26]
        conn.execute(
            """
            INSERT INTO guardian_objective_watches
                (id,intention_id,goal_title,deadline_at,status,snoozed_until,created_at,
                 last_checked_at,last_signal,last_alert_at)
            VALUES (?, ?, ?, ?, 'active', '', ?, '', '', '')
            ON CONFLICT(intention_id) DO UPDATE SET
                goal_title=excluded.goal_title,deadline_at=excluded.deadline_at,
                status='active',snoozed_until='',last_checked_at='',
                last_signal='',last_alert_at=''
            """,
            (watch_id, identifier, str(match["title"])[:300], _iso(due), _iso(instant)),
        )
        conn.commit()
    return {"id": watch_id, "intention_id": identifier, "status": "active",
            "deadline_at": _iso(due), "enrolled_with_explicit_consent": True}


def revoke(watch_id: str) -> dict[str, Any]:
    with _connect() as conn:
        result = conn.execute(
            "UPDATE guardian_objective_watches SET status='revoked',snoozed_until='' WHERE id=?",
            (str(watch_id or ""),)
        )
        conn.commit()
        if result.rowcount != 1:
            raise ValueError("Unknown Guardian objective watch.")
    return {"id": watch_id, "status": "revoked"}


def snooze(watch_id: str, *, hours: int = 1, now: datetime | None = None) -> dict[str, Any]:
    instant = now or _now()
    duration = int(hours)
    if not 1 <= duration <= 24:
        raise ValueError("Snooze must be between 1 and 24 hours.")
    until = _iso(instant + timedelta(hours=duration))
    with _connect() as conn:
        result = conn.execute(
            """
            UPDATE guardian_objective_watches SET snoozed_until=?
            WHERE id=? AND status='active'
            """,
            (until, str(watch_id or ""))
        )
        conn.commit()
        if result.rowcount != 1:
            raise ValueError("Unknown or inactive Guardian objective watch.")
    return {"id": watch_id, "snoozed_until": until}


def _preflight(item: dict[str, Any], deadline: datetime, now: datetime) -> dict[str, Any]:
    remaining = (deadline - now).total_seconds()
    pending: list[dict[str, Any]] = []
    for raw in item.get("commitments") or []:
        if not isinstance(raw, dict):
            continue
        # The executive only returns currently pending linked commitments.
        pending.append({
            "id": str(raw.get("id") or "")[:120],
            "action": str(raw.get("action") or "")[:240],
            "owner": str(raw.get("owner") or "")[:120],
            "link_confidence": float(raw.get("confidence") or 0),
        })
    next_action = str(item.get("next_action") or "").strip()[:200]
    options: list[dict[str, Any]] = [
        {
            "kind": "review_evidence",
            "label": "Review the goal and latest evidence",
            "effect": "read_only",
            "requires_confirmation": False,
        }
    ]
    if next_action:
        options.append({
            "kind": "prepare_next_step",
            "label": "Review the explicitly recorded next action: " + next_action,
            "effect": "read_only",
            "requires_confirmation": False,
        })
    if pending:
        options.append({
            "kind": "prepare_followup",
            "label": "Prepare a follow-up about a recorded pending dependency (no message sent)",
            "effect": "local_draft_only",
            "requires_confirmation": True,
        })
    if remaining <= 0:
        phase = "deadline_passed"
    elif pending:
        phase = "dependency_at_risk"
    else:
        phase = "deadline_approaching"
    return {
        "phase": phase,
        "remaining_seconds": int(remaining),
        "pending_dependencies": pending[:5],
        "next_action": next_action,
        "options": options,
        "evidence": "Goal is still active in Jarvis's structured world; "
                    + ("linked dependency is still recorded as pending."
                       if pending else "completion is not recorded."),
        "confidence": 0.95,
    }


def _record(row_id: str, checked: datetime, signal: str, *, alerted: bool) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE guardian_objective_watches
            SET last_checked_at=?,last_signal=?,
                last_alert_at=CASE WHEN ? THEN ? ELSE last_alert_at END
            WHERE id=? AND status='active'
            """,
            (_iso(checked), signal, 1 if alerted else 0, _iso(checked), row_id)
        )
        conn.commit()


def evaluate_once(*, now: datetime | None = None, emit: bool = True) -> list[dict[str, Any]]:
    """Reconcile an explicitly enrolled deadline, never dispatch a tool.

    Current goal status is queried on each iteration, so completion, retirement
    and user-edited deadlines veto stale watches. The exact enrolled deadline is
    immutable: a changed source date requires re-enrollment.
    """
    instant = now or _now()
    with _connect() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM guardian_objective_watches WHERE status='active' "
            "ORDER BY deadline_at LIMIT 30"
        )]
    if not rows:
        return []
    all_goals = {str(g["id"]): g for g in _active_goals()}
    live = _has_live_consent(instant)
    if emit:
        from jarvis_mrb.environment_state import get_state
        preferences = get_state().get("preferences") or {}
        if isinstance(preferences, dict) and preferences.get("proactive_monitoring") is False:
            live = False
    reports = []
    for row in rows:
        watch_id = row["id"]
        enrolled_deadline = _stamp(row["deadline_at"])
        if enrolled_deadline is not None and instant > enrolled_deadline + timedelta(hours=24):
            with _connect() as conn:
                conn.execute(
                    "UPDATE guardian_objective_watches SET status='expired' "
                    "WHERE id=? AND status='active'",
                    (watch_id,)
                )
                conn.commit()
            continue
        goal = all_goals.get(str(row["intention_id"]))
        deadline = _stamp(row["deadline_at"])
        current_deadline = _deadline(goal, instant) if goal else None
        if goal is None or deadline is None:
            with _connect() as conn:
                conn.execute(
                    "UPDATE guardian_objective_watches SET status='inactive',"
                    "last_checked_at=?,last_signal='goal_no_longer_active' "
                    "WHERE id=? AND status='active'",
                    (_iso(instant), watch_id)
                )
                conn.commit()
            reports.append({
                "id": watch_id, "status": "no_longer_active",
                "title": row["goal_title"], "message": "Goal no longer active; no intervention.",
                "options": [], "evidence": "No current active goal was found.",
            })
            continue
        if current_deadline != deadline:
            _record(watch_id, instant, "deadline_changed", alerted=False)
            reports.append({
                "id": watch_id, "status": "needs_reconfirmation",
                "title": row["goal_title"],
                "message": "The goal deadline changed; confirm the updated date before Guardian resumes.",
                "options": [], "evidence": "The original enrolled deadline no longer matches.",
            })
            continue
        remaining = (deadline - instant).total_seconds()
        if remaining > 24 * 3600:
            continue
        evidence = _preflight(goal, deadline, instant)
        minutes = max(0, int(remaining / 60))
        if remaining > 3600:
            status = "monitoring"
            message = f"{goal['title']}: goal still active, due in about {max(1, minutes // 60)} hours."
        elif remaining <= 0:
            status = "past_deadline_unverified"
            message = f"{goal['title']}: the enrolled deadline has passed and completion is not recorded."
        else:
            status = "at_risk"
            message = (
                f"{goal['title']}: still active with {minutes} minutes until the enrolled deadline."
                + (f" {len(evidence['pending_dependencies'])} linked dependency item(s) are still pending."
                   if evidence["pending_dependencies"] else "")
            )
        report = {
            "id": watch_id,
            "intention_id": str(goal["id"]),
            "title": str(goal["title"])[:300],
            "deadline_at": _iso(deadline),
            "status": status,
            "message": message,
            "evidence": evidence["evidence"],
            "next_action": evidence["next_action"],
            "pending_dependencies": evidence["pending_dependencies"],
            "options": evidence["options"],
            "source": "explicit goal / current world intention",
            "can_actuate": False,
            "phone_consent_live": live,
            "snoozed_until": row["snoozed_until"],
        }
        reports.append(report)
        snoozed = _stamp(row["snoozed_until"])
        has_alert = bool(emit and live and status in {"at_risk", "past_deadline_unverified"}
                         and (snoozed is None or instant >= snoozed))
        if has_alert:
            from jarvis_mrb.agency_attention import consider
            result = consider(
                kind="guardian_objective_deadline",
                message=message + " " + evidence["evidence"],
                desired_state_id=str(goal["id"]),
                dedup_key=f"guardian-deadline:{watch_id}:{_iso(deadline)}:{status}",
                benefit=88, urgency=75 if remaining <= 1200 else 55,
                confidence=0.95, error_cost=8, attention_cost=15,
                threshold=60, dedup_seconds=4 * 3600,
                severity="warning",
            )
            has_alert = bool(result.get("emitted"))
        _record(watch_id, instant, status, alerted=has_alert)
    return reports


def overview(*, now: datetime | None = None) -> dict[str, Any]:
    instant = now or _now()
    with _connect() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM guardian_objective_watches ORDER BY created_at DESC LIMIT 100"
        )]
    return {
        "checked_at": _iso(instant),
        "phone_consent_live": _has_live_consent(instant),
        "camera_required": False,
        "can_actuate": False,
        "enrollable": eligible(now=instant),
        "watches": [
            {
                "id": row["id"], "intention_id": row["intention_id"],
                "title": row["goal_title"], "deadline_at": row["deadline_at"],
                "status": row["status"], "last_signal": row["last_signal"],
                "last_checked_at": row["last_checked_at"],
                "snoozed_until": row["snoozed_until"],
            }
            for row in rows
        ],
    }
