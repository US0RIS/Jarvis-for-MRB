from __future__ import annotations

import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis_mrb.event_bus import companion_events, emit_cue
from jarvis_mrb.planner_model import QUALITY_MODEL

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "background_tasks.sqlite3"
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="jarvis-worker")
_LOCK = threading.RLock()
_CANCELLED: set[int] = set()


def _connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS background_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            session_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            error TEXT
        )
        """
    )
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "session_id": str(row["session_id"]),
        "prompt": str(row["prompt"]),
        "status": str(row["status"]),
        "result": str(row["result"] or ""),
        "error": str(row["error"] or ""),
    }


def _mirror_task(task: dict[str, Any], *, event_type: str) -> None:
    """Best-effort world mirror; background_tasks.sqlite3 remains queue authority."""
    try:
        from jarvis_mrb.world_model import SELF_ID, assert_belief, ensure_entity, record_event

        task_id = int(task["id"])
        prompt = " ".join(str(task.get("prompt") or "").split())[:5000]
        status = str(task.get("status") or "unknown")[:80]
        entity_id = ensure_entity(
            "work_item",
            f"Background task {task_id}: {prompt[:400]}",
            external_namespace="background_task",
            external_id=str(task_id),
            attributes={"prompt": prompt, "session_id": str(task.get("session_id") or "")[:128]},
            confidence=1.0,
        )
        payload: dict[str, Any] = {
            "task_id": task_id,
            "prompt": prompt,
            "session_id": str(task.get("session_id") or "")[:128],
            "status": status,
        }
        if task.get("result"):
            payload["result"] = str(task.get("result"))[:12000]
        if task.get("error"):
            payload["error"] = str(task.get("error"))[:4000]
        event_id = record_event(
            event_type,
            f"Background task {task_id} {status}: {prompt[:1000]}",
            source_kind="background_worker",
            source_ref=f"task:{task_id}:{event_type}:{task.get('updated_at') or ''}",
            occurred_at=str(task.get("updated_at") or task.get("created_at") or "") or None,
            payload=payload,
            evidence="Jarvis background-worker lifecycle record.",
            confidence=1.0,
            participants=[(SELF_ID, "requester", 1.0), (entity_id, "work_item", 1.0)],
        )
        assert_belief(entity_id, "status", value=status, source_event_id=event_id)
    except Exception:
        pass


def submit(prompt: str, session_id: str = "default") -> dict[str, Any]:
    text = prompt.strip()
    if not text:
        raise ValueError("Background task is empty.")
    now = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO background_tasks(created_at,updated_at,session_id,prompt,status) VALUES(?,?,?,?,?)",
            (now, now, session_id[:128] or "default", text[:12000], "queued"),
        )
        task_id = int(cursor.lastrowid)
        conn.commit()
    task = get_task(task_id)
    _mirror_task(task, event_type="work.queued")
    _POOL.submit(_run, task_id)
    emit_cue("task_started")
    return task


def _cancelled(task_id: int) -> bool:
    with _LOCK:
        if task_id in _CANCELLED:
            return True
    with _connect() as conn:
        row = conn.execute("SELECT status FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    return row is None or str(row["status"]) == "cancelled"


def _run(task_id: int) -> None:
    now = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM background_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None or str(row["status"]) == "cancelled":
            return
        conn.execute(
            "UPDATE background_tasks SET status='running',updated_at=? WHERE id=?",
            (now, task_id),
        )
        conn.commit()
        prompt = str(row["prompt"])
        session_id = str(row["session_id"])
    _mirror_task(get_task(task_id), event_type="work.started")

    try:
        from jarvis_mrb.conversation import recent_messages
        from jarvis_mrb.memory import memory_context
        from jarvis_mrb.streaming_agent import stream_natural_language

        history = recent_messages(session_id, limit=20)
        memory = memory_context(prompt, limit=3)
        if memory:
            from jarvis_mrb.conversation import ConversationMessage
            history = [ConversationMessage(role="assistant", content=memory), *history]

        pieces: list[str] = []
        for piece in stream_natural_language(
            prompt,
            history=history,
            model_override=QUALITY_MODEL,
            allow_background=False,
            announce_analysis=False,
        ):
            if _cancelled(task_id):
                return
            pieces.append(piece)

        if _cancelled(task_id):
            return

        result = "".join(pieces).strip() or "Background task completed without a textual result."
        with _connect() as conn:
            conn.execute(
                "UPDATE background_tasks SET status='completed',result=?,error=NULL,updated_at=? WHERE id=? AND status!='cancelled'",
                (result[:20000], datetime.now().astimezone().isoformat(), task_id),
            )
            conn.commit()
        if _cancelled(task_id):
            return
        completed = get_task(task_id)
        _mirror_task(completed, event_type="work.completed")

        concise = result.replace("\n", " ").strip()
        if len(concise) > 360:
            concise = concise[:357].rsplit(" ", 1)[0] + "..."
        companion_events.publish(
            {
                "type": "background_complete",
                "task_id": task_id,
                "message": f"Background task {task_id} is complete. {concise}",
                "cue": "task_complete",
            }
        )
    except Exception as exc:
        if _cancelled(task_id):
            return
        message = str(exc)[:4000]
        with _connect() as conn:
            conn.execute(
                "UPDATE background_tasks SET status='failed',error=?,updated_at=? WHERE id=? AND status!='cancelled'",
                (message, datetime.now().astimezone().isoformat(), task_id),
            )
            conn.commit()
        _mirror_task(get_task(task_id), event_type="work.failed")
        companion_events.publish(
            {
                "type": "background_failed",
                "task_id": task_id,
                "message": f"Background task {task_id} failed: {message[:500]}",
                "cue": "error",
            }
        )


def get_task(task_id: int) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM background_tasks WHERE id=?", (int(task_id),)).fetchone()
    if row is None:
        raise ValueError(f"Background task {task_id} does not exist.")
    return _row_to_dict(row)


def list_tasks(limit: int = 10) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 50))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM background_tasks ORDER BY id DESC LIMIT ?", (safe_limit,)
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def cancel(task_id: int) -> dict[str, Any]:
    task_id = int(task_id)
    with _LOCK:
        _CANCELLED.add(task_id)
    with _connect() as conn:
        row = conn.execute("SELECT status FROM background_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            with _LOCK:
                _CANCELLED.discard(task_id)
            raise ValueError(f"Background task {task_id} does not exist.")
        if str(row["status"]) not in {"completed", "failed", "cancelled"}:
            conn.execute(
                "UPDATE background_tasks SET status='cancelled',updated_at=? WHERE id=?",
                (datetime.now().astimezone().isoformat(), task_id),
            )
            conn.commit()
    task = get_task(task_id)
    if task["status"] == "cancelled":
        _mirror_task(task, event_type="work.cancelled")
    return task
