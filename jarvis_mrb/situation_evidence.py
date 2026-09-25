from __future__ import annotations

"""Read-only, source-qualified evidence for the existing meeting prebrief.

This module intentionally does not enroll Guardian watches, evaluate/emit
Guardian alerts, trigger iPhone Mission Control, sense a new place, perform
Life Fabric mutations, or contact an external provider. An absent adapter is
UNKNOWN, never a finding that the real-world risk/obligation does not exist.
"""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import re

_MAX_GUARDIAN_SIGNAL_AGE = timedelta(minutes=15)
_MAX_LENS_SNAPSHOT_AGE = timedelta(hours=2)


def _now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("Evidence compiler requires timezone-aware time.")
    return value.astimezone(timezone.utc)


def _time(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _fresh(raw: Any, now: datetime, age: timedelta) -> bool:
    time = _time(raw)
    return time is not None and -timedelta(seconds=30) <= now - time <= age


def _norm(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _tokens(value: Any) -> set[str]:
    stop = {
        "what", "where", "this", "that", "with", "about", "from", "before",
        "after", "meeting", "call", "the", "and", "for", "you", "your", "our",
        "task", "please", "review", "prepare", "final", "make", "check",
    }
    return {x for x in _norm(value).split() if len(x) >= 3 and x not in stop}


def _readonly(path: Path) -> sqlite3.Connection:
    # Both Windows C:/... and POSIX paths are supported by SQLite URI syntax.
    conn = sqlite3.connect("file:" + path.resolve().as_posix() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _guardian_rows() -> tuple[list[dict[str, Any]], str]:
    from jarvis_mrb.world_model import DB_PATH
    if not Path(DB_PATH).is_file():
        return [], "no_enrolled_data"
    try:
        with closing(_readonly(Path(DB_PATH))) as conn:
            rows = conn.execute(
                """SELECT id,intention_id,goal_title,deadline_at,status,last_signal,
                          last_checked_at,snoozed_until
                   FROM guardian_objective_watches
                   WHERE status='active' ORDER BY deadline_at LIMIT 30"""
            ).fetchall()
            return [dict(row) for row in rows], "available"
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return [], "no_enrolled_data"
        return [], "unavailable"


def _life_rows() -> tuple[list[dict[str, Any]], str]:
    from jarvis_mrb.life_fabric import STORE, _state
    path = Path(STORE)
    if not path.is_file():
        return [], "no_enrolled_data"
    try:
        with closing(_readonly(path)) as conn:
            rows = conn.execute(
                """SELECT id,domain,title,data_json,deadline_at
                   FROM records WHERE kind='task' AND retired_at IS NULL
                   ORDER BY CASE WHEN deadline_at IS NULL THEN 1 ELSE 0 END,
                            deadline_at,created_at LIMIT 500"""
            ).fetchall()
            result = []
            for row in rows:
                last = conn.execute(
                    """SELECT outcome,source_kind,observed_at FROM receipts
                       WHERE record_id=? ORDER BY observed_at DESC,rowid DESC LIMIT 1""",
                    (row["id"],),
                ).fetchone()
                try:
                    data = json.loads(row["data_json"])
                except (TypeError, ValueError):
                    continue
                if not isinstance(data, dict):
                    continue
                result.append({
                    "id": row["id"], "domain": row["domain"], "title": row["title"],
                    "data": data, "deadline_at": row["deadline_at"],
                    "completion_state": _state("task", [dict(last)] if last else []),
                })
            return result, "available"
    except (sqlite3.Error, ValueError):
        return [], "unavailable"


def _lens_rows(place_key: str) -> tuple[list[dict[str, Any]], str]:
    from jarvis_mrb.reality_lens import STORE
    path = Path(STORE)
    if not path.is_file():
        return [], "no_enrolled_data"
    try:
        with closing(_readonly(path)) as conn:
            rows = conn.execute(
                """SELECT id,place_label,captured_at,metrics_json
                   FROM snapshots WHERE place_key=?
                   ORDER BY captured_at DESC,rowid DESC LIMIT 2""",
                (place_key,),
            ).fetchall()
            return [dict(row) for row in rows], "available"
    except sqlite3.Error:
        return [], "unavailable"


def _matching_task(task: dict[str, Any], event: dict[str, Any],
                   projects: list[dict[str, Any]]) -> str | None:
    """Avoid an unrelated personal task leaking into a particular meeting."""
    body = task.get("data") or {}
    if not isinstance(body, dict):
        return None
    eid = str(event.get("calendar_event_id") or event.get("source_ref") or "")
    ref = str(body.get("source_ref") or "")
    if eid and ref in {eid, "calendar:" + eid}:
        return "exact_calendar_event_reference"
    description = " ".join(str(body.get(k) or "") for k in ("description", "next_step"))
    task_text = " ".join((str(task.get("title") or ""), description))
    event_text = str(event.get("title") or "")
    overlap = _tokens(task_text) & _tokens(event_text)
    if len(overlap) >= 2:
        return "two_distinct_event_title_terms"
    normalized_task = " " + _norm(task_text) + " "
    for project in projects:
        name = _norm(project.get("name"))
        if len(name) >= 5 and " " + name + " " in normalized_task:
            return "connected_project_name"
    return None


def _guardian(event: dict[str, Any], intentions: list[dict[str, Any]],
              now: datetime) -> tuple[list[dict[str, Any]], str]:
    if not intentions:
        return [], "no_linked_intentions"
    rows, availability = _guardian_rows()
    if availability != "available":
        return [], availability
    linked = {str(x.get("id")): x for x in intentions if x.get("id")}
    result: list[dict[str, Any]] = []
    for row in rows:
        intention = linked.get(str(row.get("intention_id") or ""))
        if not intention:
            continue
        enrolled_due = _time(row.get("deadline_at"))
        current_due = _time(intention.get("due"))
        if not enrolled_due or not current_due or enrolled_due != current_due:
            continue
        if now > enrolled_due + timedelta(hours=24):
            continue
        if not _fresh(row.get("last_checked_at"), now, _MAX_GUARDIAN_SIGNAL_AGE):
            continue
        signal = str(row.get("last_signal") or "")
        if signal not in {"at_risk", "past_deadline_unverified", "monitoring"}:
            continue
        # Only a previous, timestamped Guardian evaluation can report risk.
        result.append({
            "source": "guardian_objectives", "watch_id": row["id"],
            "intention_id": row["intention_id"], "title": row["goal_title"],
            "signal": signal, "deadline_at": row["deadline_at"],
            "observed_at": row["last_checked_at"],
            "evidence_kind": "previous_enrolled_goal_evaluation",
            "qualifier": "Not a live route calculation or a completion attestation.",
        })
    return result[:4], "available" if result else "no_fresh_matching_signal"


def _life(event: dict[str, Any], projects: list[dict[str, Any]],
          now: datetime) -> tuple[list[dict[str, Any]], str]:
    rows, availability = _life_rows()
    if availability != "available":
        return [], availability
    tasks = {str(x["id"]): x for x in rows}
    completed = {"user_confirmed", "sensor_observed"}
    result: list[dict[str, Any]] = []
    for task in rows:
        state = task.get("completion_state")
        if state in completed:
            continue
        reason = _matching_task(task, event, projects)
        if not reason:
            continue
        deadline = _time(task.get("deadline_at"))
        if deadline is not None and not (-timedelta(seconds=30) <= deadline - now <= timedelta(days=7)):
            # Older overdue tasks remain relevant; include them as overdue,
            # but do not present far-future tasks as imminent.
            if deadline > now + timedelta(days=7):
                continue
        missing = [
            identifier for identifier in (task["data"].get("depends_on") or [])
            if identifier not in tasks
            or tasks[identifier]["completion_state"] not in completed
        ]
        if deadline is None and not missing and state != "outcome_unknown":
            continue
        due_state = ("overdue" if deadline < now else
                     "next_24h" if deadline <= now + timedelta(hours=24) else
                     "next_7d") if deadline else "no_deadline"
        result.append({
            "source": "life_fabric", "task_id": task["id"],
            "title": task["title"], "domain": task["domain"],
            "completion_state": state, "due_state": due_state,
            "deadline_at": task.get("deadline_at"), "blocked": bool(missing),
            "missing_dependency_ids": missing[:5], "link": reason,
            "qualifier": "Explicitly enrolled task, not external proof of completion.",
        })
    result.sort(key=lambda x: (x["deadline_at"] is None, x["deadline_at"] or ""))
    return result[:6], "available" if result else "no_relevant_enrolled_tasks"


def _mission(event: dict[str, Any], mission: dict[str, Any] | None,
             now: datetime) -> tuple[list[dict[str, Any]], str]:
    # Mission Control is in iPhone Keychain; the Windows server has no right
    # to retrieve it. Only an explicitly furnished, exact-event summary can
    # be joined. This is a future phone transport hook, not auto-sync.
    if mission is None:
        return [], "phone_local_not_shared"
    eid = str(event.get("calendar_event_id") or event.get("source_ref") or "")
    if not eid or mission.get("calendarID") != eid:
        return [], "different_event"
    if _time(event.get("start")) != _time(mission.get("startsAt")):
        return [], "event_time_mismatch"
    if _norm(event.get("location")) != _norm(mission.get("literalDestination")):
        return [], "destination_mismatch"
    if not _fresh(mission.get("checkedAt"), now, timedelta(minutes=2)):
        return [], "stale_phone_snapshot"
    phase = mission.get("phase")
    if phase not in {"active", "reviewRequired", "achievedOnTime", "arrivedLate",
                     "missedUnverified", "cancelled"}:
        return [], "invalid_phase"
    return [{
        "source": "iphone_mission_control", "calendar_event_id": eid,
        "phase": phase, "observed_at": mission["checkedAt"],
        "route_checked_at": mission.get("routeCheckedAt"),
        "qualifier": "Phone-reported phase only; arrival proximity is not attendance.",
    }], "provided_for_exact_event"


def _lens(event: dict[str, Any],
          resolved_place: dict[str, Any] | None,
          now: datetime) -> tuple[list[dict[str, Any]], str]:
    # The calendar currently has a *text* location, not MapKit-resolved
    # coordinates. Never join on label alone, approximate text, or user GPS.
    if not resolved_place:
        return [], "exact_place_not_linked"
    try:
        from jarvis_mrb.reality_lens import _coordinates
        if _norm(resolved_place.get("literal_location")) != _norm(event.get("location")):
            return [], "location_mismatch"
        key = _coordinates(resolved_place["latitude"], resolved_place["longitude"])
    except (KeyError, TypeError, ValueError):
        return [], "unverified_place"
    rows, state = _lens_rows(key)
    if state != "available":
        return [], state
    if len(rows) < 2 or not _fresh(rows[0]["captured_at"], now, _MAX_LENS_SNAPSHOT_AGE):
        return [], "no_recent_pair"
    if not _fresh(rows[1]["captured_at"], now, timedelta(days=30)):
        return [], "old_baseline"
    try:
        newer, older = (json.loads(row["metrics_json"]) for row in rows)
    except (TypeError, ValueError):
        return [], "invalid_saved_metrics"
    from jarvis_mrb.reality_lens import FIELDS
    result: list[dict[str, Any]] = []
    for fid, label in FIELDS:
        a, b = newer.get(fid), older.get(fid)
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        if a.get("source") != b.get("source"):
            continue
        if type(a.get("value")) not in (int, float) or type(b.get("value")) not in (int, float):
            continue
        if a["value"] == b["value"]:
            continue
        result.append({
            "source": "reality_lens_saved_snapshots",
            "fact_id": fid, "label": label,
            "before": b["value"], "after": a["value"],
            "provider": a["source"], "previous_at": rows[1]["captured_at"],
            "observed_at": rows[0]["captured_at"],
            "qualifier": "Historical manually saved snapshots, NOT current conditions.",
        })
    return result[:4], "historical_diff" if result else "no_saved_difference"


def compile_evidence(event: dict[str, Any],
                     intentions: list[dict[str, Any]],
                     projects: list[dict[str, Any]], *,
                     now: datetime | None = None,
                     phone_mission: dict[str, Any] | None = None,
                     resolved_place: dict[str, Any] | None = None) -> dict[str, Any]:
    instant = _now(now)
    sections: dict[str, list[dict[str, Any]]] = {}
    statuses: dict[str, str] = {}
    for name, provider in (
        ("guardian", lambda: _guardian(event, intentions, instant)),
        ("life_fabric", lambda: _life(event, projects, instant)),
        ("mission_control", lambda: _mission(event, phone_mission, instant)),
        ("reality_lens", lambda: _lens(event, resolved_place, instant)),
    ):
        try:
            rows, status = provider()
            sections[name], statuses[name] = rows, status
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            sections[name], statuses[name] = [], "unavailable"
    return {
        "schema": "jarvis.situation.evidence.v1",
        "checked_at": instant.isoformat(),
        "sections": sections, "source_status": statuses,
        "external_actions": 0, "model_calls": 0,
        "coverage": "exact_event_related_read_only_evidence",
    }
