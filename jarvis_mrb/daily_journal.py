from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from jarvis_mrb.background_workers import list_tasks
from jarvis_mrb.environment_state import get_state
from jarvis_mrb.planner_model import FAST_MODEL
from jarvis_mrb.tools.google import query_emails

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
JOURNAL_DIR = APP_DIR / "journal"
CONVERSATION_DB = APP_DIR / "conversation.sqlite3"
SPATIAL_DB = APP_DIR / "spatial_memory.sqlite3"
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_LOCK = threading.RLock()
_STARTED = False
_LAST_WRITTEN_DATE = ""


def _conversation_rows(day: date) -> list[dict[str, str]]:
    if not CONVERSATION_DB.exists():
        return []
    start = datetime.combine(day, datetime.min.time()).astimezone()
    end = start + timedelta(days=1)
    try:
        conn = sqlite3.connect(CONVERSATION_DB, timeout=5.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT role,content,created_at FROM conversation_messages WHERE created_at>=? AND created_at<? ORDER BY id ASC LIMIT 120",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [
        {"role": str(row["role"]), "content": str(row["content"])[:1200], "created_at": str(row["created_at"])}
        for row in rows
    ]


def _spatial_rows(day: date) -> list[dict[str, str]]:
    if not SPATIAL_DB.exists():
        return []
    start = datetime.combine(day, datetime.min.time()).astimezone()
    end = start + timedelta(days=1)
    try:
        conn = sqlite3.connect(SPATIAL_DB, timeout=5.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT object_name,location_context,scene,seen_at FROM object_sightings WHERE seen_at>=? AND seen_at<? ORDER BY id DESC LIMIT 40",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [
        {
            "object": str(row["object_name"]),
            "location": str(row["location_context"]),
            "scene": str(row["scene"])[:500],
            "seen_at": str(row["seen_at"]),
        }
        for row in rows
    ]


def _mail_summary() -> dict[str, Any]:
    received = query_emails(query="in:inbox newer_than:1d", limit=8)
    sent = query_emails(query="in:sent newer_than:1d", limit=8)
    return {
        "received": received.message if received.ok else "unavailable",
        "sent": sent.message if sent.ok else "unavailable",
    }


def _task_summary() -> list[dict[str, Any]]:
    try:
        tasks = list_tasks(30)
    except Exception:
        return []
    return [
        {
            "id": task.get("id"),
            "status": task.get("status"),
            "prompt": str(task.get("prompt") or "")[:500],
            "result": str(task.get("result") or "")[:700],
            "updated_at": task.get("updated_at"),
        }
        for task in tasks
        if task.get("status") in {"completed", "failed", "cancelled"}
    ][:12]


def _render_with_model(day: date, source: dict[str, Any]) -> str:
    system = """Create a concise private daily journal entry from the supplied local Jarvis activity.
Return Markdown only. Use these headings when relevant: # date, ## Highlights, ## Commitments & Follow-ups, ## Work Completed, ## Communications, ## Seen / Places, ## Notes for Tomorrow.
Do not invent events, emotions, motives, or sensitive interpretations. Prefer 5-12 useful bullets total. Omit empty sections. Do not include API credentials or raw URLs."""
    payload = {
        "model": FAST_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Date: {day.isoformat()}\nLocal activity JSON:\n{json.dumps(source, ensure_ascii=False)[:24000]}"},
        ],
        "options": {"temperature": 0, "num_predict": 900},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        text = str((data.get("message") or {}).get("content") or "").strip()
        if text:
            return text
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    lines = [f"# {day.isoformat()}", "", "## Highlights"]
    conversations = source.get("conversations") or []
    if conversations:
        lines.append(f"- Jarvis recorded {len(conversations)} conversation messages today.")
    tasks = source.get("background_tasks") or []
    if tasks:
        lines.append(f"- {len(tasks)} background task outcomes were recorded.")
    sightings = source.get("spatial_sightings") or []
    if sightings:
        lines.append(f"- {len(sightings)} recent object/location sightings were retained.")
    return "\n".join(lines) + "\n"


def _mirror_journal(target_day: date, markdown: str, path: Path) -> None:
    try:
        from jarvis_mrb.world_model import record_knowledge_source

        record_knowledge_source(
            "journal",
            target_day.isoformat(),
            title=f"Daily journal {target_day.isoformat()}",
            text=markdown,
            occurred_at=f"{target_day.isoformat()}T23:59:00",
            metadata={"path": str(path), "derived": True},
        )
    except Exception:
        pass


def generate(day: date | None = None) -> Path:
    target_day = day or datetime.now().astimezone().date()
    source = {
        "conversations": _conversation_rows(target_day),
        "background_tasks": _task_summary(),
        "spatial_sightings": _spatial_rows(target_day),
        "mail": _mail_summary(),
    }
    markdown = _render_with_model(target_day, source)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = JOURNAL_DIR / f"{target_day.isoformat()}.md"
    path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    _mirror_journal(target_day, markdown, path)
    return path


def generate_message() -> str:
    path = generate()
    return f"Today's local journal is saved at {path}."


def _enabled() -> bool:
    state = get_state()
    preferences = state.get("preferences") if isinstance(state.get("preferences"), dict) else {}
    return bool(preferences.get("daily_journal", False))


def _loop() -> None:
    global _LAST_WRITTEN_DATE
    while True:
        now = datetime.now().astimezone()
        key = now.date().isoformat()
        should_run = now.hour == 23 and now.minute >= 45
        if _enabled() and should_run and _LAST_WRITTEN_DATE != key:
            try:
                generate(now.date())
                _LAST_WRITTEN_DATE = key
            except Exception:
                pass
        time.sleep(60)


def start() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    threading.Thread(target=_loop, name="jarvis-daily-journal", daemon=True).start()
