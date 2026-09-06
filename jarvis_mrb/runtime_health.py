from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_subsystem_health (
            subsystem TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_error TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def record_success(subsystem: str) -> None:
    name = str(subsystem or "unknown")[:160]
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO runtime_subsystem_health(
                subsystem,status,consecutive_failures,last_success_at,last_failure_at,last_error,updated_at
            ) VALUES(?,?,0,?,NULL,'',?)
            ON CONFLICT(subsystem) DO UPDATE SET
                status='ok',consecutive_failures=0,last_success_at=excluded.last_success_at,
                last_error='',updated_at=excluded.updated_at
            """,
            (name, "ok", now, now),
        )
        conn.commit()


def record_failure(subsystem: str, error: object) -> None:
    name = str(subsystem or "unknown")[:160]
    now = _now()
    message = str(error or "unknown failure")[:2000]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO runtime_subsystem_health(
                subsystem,status,consecutive_failures,last_success_at,last_failure_at,last_error,updated_at
            ) VALUES(?,?,1,NULL,?,?,?)
            ON CONFLICT(subsystem) DO UPDATE SET
                status='degraded',
                consecutive_failures=runtime_subsystem_health.consecutive_failures+1,
                last_failure_at=excluded.last_failure_at,last_error=excluded.last_error,
                updated_at=excluded.updated_at
            """,
            (name, "degraded", now, message, now),
        )
        conn.commit()


def snapshot() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runtime_subsystem_health ORDER BY subsystem"
        ).fetchall()
    return [
        {
            "subsystem": str(row["subsystem"]),
            "status": str(row["status"]),
            "consecutive_failures": int(row["consecutive_failures"]),
            "last_success_at": str(row["last_success_at"] or ""),
            "last_failure_at": str(row["last_failure_at"] or ""),
            "last_error": str(row["last_error"] or ""),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]


def status() -> dict[str, Any]:
    items = snapshot()
    degraded = [item for item in items if item["status"] != "ok"]
    return {
        "installed": True,
        "subsystems": items,
        "degraded": len(degraded),
        "healthy": len(items) - len(degraded),
    }
