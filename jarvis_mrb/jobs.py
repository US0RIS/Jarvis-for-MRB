from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import dateparser

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "jobs.sqlite3"


@dataclass(frozen=True)
class JobResult:
    ok: bool
    message: str


def _connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            trigger_value TEXT NOT NULL,
            command TEXT NOT NULL,
            created_at TEXT NOT NULL,
            next_run TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run TEXT,
            last_result TEXT,
            recurrence TEXT
        )
        """
    )
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "recurrence" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN recurrence TEXT")
    conn.commit()
    return conn


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_future(when: str) -> datetime | None:
    parsed = dateparser.parse(
        when,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "RELATIVE_BASE": _now(),
        },
    )
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _mirror_job(
    job_id: int,
    *,
    event_type: str,
    kind: str,
    trigger_value: str,
    command: str,
    enabled: bool,
    next_run: str | None = None,
    recurrence: str | None = None,
    occurred_at: str | None = None,
    result: str = "",
) -> None:
    """Best-effort world representation; jobs.sqlite3 remains execution authority."""
    try:
        from jarvis_mrb.world_model import SELF_ID, assert_belief, ensure_entity, record_event

        name = f"Job {job_id}: {' '.join(command.split())[:400]}"
        entity_id = ensure_entity(
            "automation",
            name,
            external_namespace="jarvis_job",
            external_id=str(job_id),
            attributes={
                "kind": kind,
                "trigger_value": trigger_value,
                "command": command[:4000],
                "recurrence": recurrence or "",
            },
            confidence=1.0,
        )
        payload: dict[str, Any] = {
            "job_id": int(job_id),
            "kind": kind,
            "trigger_value": trigger_value,
            "command": command[:4000],
            "enabled": bool(enabled),
            "next_run": next_run,
            "recurrence": recurrence,
        }
        if result:
            payload["result"] = result[:2000]
        event_id = record_event(
            event_type,
            f"Job {job_id} {event_type.split('.')[-1]}: {' '.join(command.split())[:900]}",
            source_kind="jarvis_jobs",
            source_ref=f"job:{job_id}:{event_type}:{occurred_at or _now().isoformat()}",
            occurred_at=occurred_at,
            payload=payload,
            evidence="Jarvis scheduler state/execution record.",
            confidence=1.0,
            participants=[(SELF_ID, "requester", 1.0), (entity_id, "automation", 1.0)],
        )
        assert_belief(entity_id, "enabled", value=bool(enabled), source_event_id=event_id)
        assert_belief(entity_id, "trigger_kind", value=kind, source_event_id=event_id)
        assert_belief(entity_id, "trigger_value", value=trigger_value, source_event_id=event_id)
        if recurrence:
            assert_belief(entity_id, "recurrence", value=recurrence, source_event_id=event_id)
        if next_run:
            assert_belief(entity_id, "next_run", value=next_run, source_event_id=event_id)
    except Exception:
        pass


def create_time_job(when: str, command: str) -> JobResult:
    parsed = _parse_future(when)
    if parsed is None:
        return JobResult(False, f"I couldn't understand the time {when!r}.")
    if parsed <= _now():
        return JobResult(False, "That time is not in the future.")
    created = _now().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs(kind, trigger_value, command, created_at, next_run) VALUES(?,?,?,?,?)",
            ("time", when, command, created, parsed.isoformat()),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
    _mirror_job(
        job_id,
        event_type="automation.created",
        kind="time",
        trigger_value=when,
        command=command,
        enabled=True,
        next_run=parsed.isoformat(),
        occurred_at=created,
    )
    return JobResult(True, f"Created job {job_id}: at {parsed.strftime('%Y-%m-%d %I:%M %p %Z')}, {command}.")


def create_recurring_job(when: str, command: str, recurrence: str = "daily") -> JobResult:
    cadence = recurrence.strip().lower().replace(" ", "_")
    if cadence not in {"daily", "weekdays", "weekly"}:
        return JobResult(False, "Recurring jobs support daily, weekdays, or weekly cadence.")
    parsed = _parse_future(when)
    if parsed is None:
        return JobResult(False, f"I couldn't understand the time {when!r}.")
    while parsed <= _now():
        parsed += timedelta(days=1 if cadence in {"daily", "weekdays"} else 7)
    if cadence == "weekdays":
        while parsed.weekday() >= 5:
            parsed += timedelta(days=1)
    created = _now().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs(kind, trigger_value, command, created_at, next_run, recurrence) VALUES(?,?,?,?,?,?)",
            ("time", when, command, created, parsed.isoformat(), cadence),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
    _mirror_job(
        job_id,
        event_type="automation.created",
        kind="time",
        trigger_value=when,
        command=command,
        enabled=True,
        next_run=parsed.isoformat(),
        recurrence=cadence,
        occurred_at=created,
    )
    return JobResult(
        True,
        f"Created recurring job {job_id}: {cadence} at {parsed.strftime('%I:%M %p %Z')}, {command}.",
    )


def create_event_job(event: str, command: str) -> JobResult:
    event_key = event.strip().lower().replace(" ", "_")
    if not event_key:
        return JobResult(False, "No event trigger was provided.")
    created = _now().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs(kind, trigger_value, command, created_at) VALUES(?,?,?,?)",
            ("event", event_key, command, created),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
    _mirror_job(
        job_id,
        event_type="automation.created",
        kind="event",
        trigger_value=event_key,
        command=command,
        enabled=True,
        occurred_at=created,
    )
    return JobResult(True, f"Created job {job_id}: when event {event_key!r} occurs, {command}.")


def list_jobs() -> JobResult:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM jobs WHERE enabled=1 ORDER BY id").fetchall()
    if not rows:
        return JobResult(True, "No active jobs.")
    parts: list[str] = []
    for row in rows:
        trigger = row["next_run"] if row["kind"] == "time" else row["trigger_value"]
        recurrence = str(row["recurrence"] or "")
        cadence = f" recurring {recurrence}" if recurrence else ""
        parts.append(f"#{row['id']} {row['kind']}{cadence} {trigger}: {row['command']}")
    return JobResult(True, "Active jobs: " + "; ".join(parts))


def cancel_job(job_id: int) -> JobResult:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=? AND enabled=1", (job_id,)).fetchone()
        cur = conn.execute("UPDATE jobs SET enabled=0 WHERE id=? AND enabled=1", (job_id,))
        conn.commit()
    if cur.rowcount:
        if row is not None:
            _mirror_job(
                job_id,
                event_type="automation.cancelled",
                kind=str(row["kind"]),
                trigger_value=str(row["trigger_value"]),
                command=str(row["command"]),
                enabled=False,
                next_run=str(row["next_run"] or "") or None,
                recurrence=str(row["recurrence"] or "") or None,
            )
        return JobResult(True, f"Cancelled job {job_id}.")
    return JobResult(False, f"No active job {job_id} was found.")


def _next_recurring_time(current: datetime, recurrence: str) -> datetime:
    cadence = recurrence.strip().lower()
    if cadence == "weekly":
        return current + timedelta(days=7)
    candidate = current + timedelta(days=1)
    if cadence == "weekdays":
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
    return candidate


def _execute_row(conn: sqlite3.Connection, row: sqlite3.Row, executor: Callable[[str], str]) -> None:
    run_at = _now().isoformat()
    try:
        result = executor(str(row["command"]))
    except Exception as exc:
        result = f"Job failed: {exc}"

    recurrence = str(row["recurrence"] or "").strip()
    enabled = False
    next_run_value: str | None = None
    if recurrence and row["kind"] == "time" and row["next_run"]:
        try:
            current = datetime.fromisoformat(str(row["next_run"]))
            if current.tzinfo is None:
                current = current.astimezone()
        except ValueError:
            current = _now()
        next_run = _next_recurring_time(current, recurrence)
        while next_run <= _now():
            next_run = _next_recurring_time(next_run, recurrence)
        next_run_value = next_run.isoformat()
        enabled = True
        conn.execute(
            "UPDATE jobs SET enabled=1,next_run=?,last_run=?,last_result=? WHERE id=?",
            (next_run_value, run_at, result[:2000], row["id"]),
        )
    else:
        conn.execute(
            "UPDATE jobs SET enabled=0, last_run=?, last_result=? WHERE id=?",
            (run_at, result[:2000], row["id"]),
        )
    conn.commit()

    _mirror_job(
        int(row["id"]),
        event_type="automation.executed",
        kind=str(row["kind"]),
        trigger_value=str(row["trigger_value"]),
        command=str(row["command"]),
        enabled=enabled,
        next_run=next_run_value,
        recurrence=recurrence or None,
        occurred_at=run_at,
        result=result,
    )


def run_due_jobs(executor: Callable[[str], str]) -> int:
    now_iso = _now().isoformat()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE enabled=1 AND kind='time' AND next_run IS NOT NULL AND next_run<=? ORDER BY id",
            (now_iso,),
        ).fetchall()
        for row in rows:
            _execute_row(conn, row, executor)
    return len(rows)


def trigger_event(event: str, executor: Callable[[str], str]) -> JobResult:
    event_key = event.strip().lower().replace(" ", "_")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE enabled=1 AND kind='event' AND trigger_value=? ORDER BY id",
            (event_key,),
        ).fetchall()
        for row in rows:
            _execute_row(conn, row, executor)
    if not rows:
        return JobResult(True, f"Event {event_key!r} received; no jobs matched it.")
    return JobResult(True, f"Event {event_key!r} triggered {len(rows)} job(s).")
