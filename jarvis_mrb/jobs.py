from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

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
            last_result TEXT
        )
        """
    )
    conn.commit()
    return conn


def _now() -> datetime:
    return datetime.now().astimezone()


def create_time_job(when: str, command: str) -> JobResult:
    parsed = dateparser.parse(
        when,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "RELATIVE_BASE": _now(),
        },
    )
    if parsed is None:
        return JobResult(False, f"I couldn't understand the time {when!r}.")
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    if parsed <= _now():
        return JobResult(False, "That time is not in the future.")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs(kind, trigger_value, command, created_at, next_run) VALUES(?,?,?,?,?)",
            ("time", when, command, _now().isoformat(), parsed.isoformat()),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
    return JobResult(True, f"Created job {job_id}: at {parsed.strftime('%Y-%m-%d %I:%M %p %Z')}, {command}.")


def create_event_job(event: str, command: str) -> JobResult:
    event_key = event.strip().lower().replace(" ", "_")
    if not event_key:
        return JobResult(False, "No event trigger was provided.")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs(kind, trigger_value, command, created_at) VALUES(?,?,?,?)",
            ("event", event_key, command, _now().isoformat()),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
    return JobResult(True, f"Created job {job_id}: when event {event_key!r} occurs, {command}.")


def list_jobs() -> JobResult:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM jobs WHERE enabled=1 ORDER BY id").fetchall()
    if not rows:
        return JobResult(True, "No active jobs.")
    parts: list[str] = []
    for row in rows:
        trigger = row["next_run"] if row["kind"] == "time" else row["trigger_value"]
        parts.append(f"#{row['id']} {row['kind']} {trigger}: {row['command']}")
    return JobResult(True, "Active jobs: " + "; ".join(parts))


def cancel_job(job_id: int) -> JobResult:
    with _connect() as conn:
        cur = conn.execute("UPDATE jobs SET enabled=0 WHERE id=? AND enabled=1", (job_id,))
        conn.commit()
    if cur.rowcount:
        return JobResult(True, f"Cancelled job {job_id}.")
    return JobResult(False, f"No active job {job_id} was found.")


def _execute_row(conn: sqlite3.Connection, row: sqlite3.Row, executor: Callable[[str], str]) -> None:
    try:
        result = executor(str(row["command"]))
    except Exception as exc:
        result = f"Job failed: {exc}"
    conn.execute(
        "UPDATE jobs SET enabled=0, last_run=?, last_result=? WHERE id=?",
        (_now().isoformat(), result[:2000], row["id"]),
    )
    conn.commit()


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
