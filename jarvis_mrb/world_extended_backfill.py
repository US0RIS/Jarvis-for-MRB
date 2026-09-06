from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
_SENTINEL = APP_DIR / "world_model_extended_backfill_v1.complete"


def _rows(path: Path, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def _backfill_jobs() -> int:
    import jarvis_mrb.jobs as jobs

    rows = _rows(APP_DIR / "jobs.sqlite3", "SELECT * FROM jobs ORDER BY id")
    count = 0
    for row in rows:
        created = str(row["created_at"] or "")
        recurrence = str(row["recurrence"] or "") or None
        jobs._mirror_job(
            int(row["id"]),
            event_type="automation.created",
            kind=str(row["kind"]),
            trigger_value=str(row["trigger_value"]),
            command=str(row["command"]),
            enabled=bool(row["enabled"]),
            next_run=str(row["next_run"] or "") or None,
            recurrence=recurrence,
            occurred_at=created or None,
        )
        if row["last_run"]:
            jobs._mirror_job(
                int(row["id"]),
                event_type="automation.executed",
                kind=str(row["kind"]),
                trigger_value=str(row["trigger_value"]),
                command=str(row["command"]),
                enabled=bool(row["enabled"]),
                next_run=str(row["next_run"] or "") or None,
                recurrence=recurrence,
                occurred_at=str(row["last_run"]),
                result=str(row["last_result"] or ""),
            )
        count += 1
    return count


def _backfill_background() -> int:
    import jarvis_mrb.background_workers as workers

    rows = _rows(APP_DIR / "background_tasks.sqlite3", "SELECT * FROM background_tasks ORDER BY id")
    count = 0
    event_for_status = {
        "queued": "work.queued",
        "running": "work.started",
        "completed": "work.completed",
        "failed": "work.failed",
        "cancelled": "work.cancelled",
    }
    for row in rows:
        task = {
            "id": int(row["id"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "session_id": str(row["session_id"]),
            "prompt": str(row["prompt"]),
            "status": str(row["status"]),
            "result": str(row["result"] or ""),
            "error": str(row["error"] or ""),
        }
        workers._mirror_task(task, event_type=event_for_status.get(task["status"], "work.observed"))
        count += 1
    return count


def _backfill_expenses() -> int:
    import jarvis_mrb.expense_tracker as expenses

    rows = _rows(APP_DIR / "expenses.sqlite3", "SELECT * FROM expenses ORDER BY id")
    count = 0
    for row in rows:
        try:
            raw_items = json.loads(str(row["items_json"] or "[]"))
            items = raw_items if isinstance(raw_items, list) else []
        except json.JSONDecodeError:
            items = []
        expenses._mirror_expense(
            int(row["id"]),
            captured_at=str(row["captured_at"]),
            merchant=str(row["merchant"] or ""),
            transaction_date=str(row["transaction_date"] or ""),
            currency=str(row["currency"] or ""),
            subtotal=float(row["subtotal"]) if row["subtotal"] is not None else None,
            tax=float(row["tax"]) if row["tax"] is not None else None,
            tip=float(row["tip"]) if row["tip"] is not None else None,
            total=float(row["total"]) if row["total"] is not None else None,
            items=items,
        )
        count += 1
    return count


def _backfill_journals() -> int:
    from jarvis_mrb.world_model import record_knowledge_source

    journal_dir = APP_DIR / "journal"
    if not journal_dir.exists():
        return 0
    count = 0
    for path in sorted(journal_dir.glob("*.md")):
        try:
            markdown = path.read_text(encoding="utf-8", errors="replace")[:80000]
        except OSError:
            continue
        day = path.stem[:32]
        record_knowledge_source(
            "journal",
            day,
            title=f"Daily journal {day}",
            text=markdown,
            occurred_at=f"{day}T23:59:00" if len(day) == 10 else None,
            metadata={"path": str(path), "derived": True, "backfilled": True},
        )
        count += 1
    return count


def backfill_extended_state(*, force: bool = False) -> dict[str, Any]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if _SENTINEL.exists() and not force:
        return {"ok": True, "skipped": True, "reason": "extended world-model backfill already completed"}

    result: dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "jobs": 0,
        "background_tasks": 0,
        "expenses": 0,
        "journals": 0,
        "errors": [],
    }
    steps = (
        ("jobs", _backfill_jobs),
        ("background_tasks", _backfill_background),
        ("expenses", _backfill_expenses),
        ("journals", _backfill_journals),
    )
    for name, function in steps:
        try:
            result[name] = int(function())
        except Exception as exc:
            result["ok"] = False
            result["errors"].append(f"{name}: {exc}")

    try:
        from jarvis_mrb.world_linker import refresh_links
        from jarvis_mrb.world_model import record_event

        record_event(
            "system.world_extended_backfill",
            "Jarvis imported durable scheduler, worker, expense, and journal history into the persistent world model.",
            source_kind="system",
            source_ref="world_model_extended_backfill_v1",
            payload={key: value for key, value in result.items() if key != "errors"},
            evidence="One-time local migration over existing durable Jarvis stores.",
            confidence=1.0,
        )
        result["linker"] = refresh_links(limit=5000)
    except Exception as exc:
        result["ok"] = False
        result["errors"].append(f"linker: {exc}")

    if result["ok"]:
        _SENTINEL.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
