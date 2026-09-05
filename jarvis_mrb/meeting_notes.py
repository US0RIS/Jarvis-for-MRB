from __future__ import annotations

import json
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from jarvis_mrb.event_bus import emit_proactive
from jarvis_mrb.fact_checker import check_claim
from jarvis_mrb.planner_model import FAST_MODEL

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "meeting_notes.sqlite3"
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_FACT_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-fact-check")


def _connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            title TEXT,
            status TEXT NOT NULL,
            transcript TEXT NOT NULL DEFAULT '',
            action_items_json TEXT
        )
        """
    )
    conn.commit()
    return conn


def start(title: str = "") -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO meetings(started_at,title,status,transcript) VALUES(?,?,?,?)",
            (now, title.strip()[:300], "recording", ""),
        )
        meeting_id = int(cursor.lastrowid)
        conn.commit()
    return {"id": meeting_id, "started_at": now, "title": title.strip(), "status": "recording"}


def _metric_claims(chunk: str) -> list[str]:
    candidates = re.split(r"(?<=[.!?])\s+|\n+", chunk)
    result: list[str] = []
    metric_cue = re.compile(
        r"(?:\d|%|\$|\beuros?\b|\bdollars?\b|\bmillion\b|\bbillion\b|\bpercent\b|\bpercentage\b)",
        flags=re.IGNORECASE,
    )
    for candidate in candidates:
        text = " ".join(candidate.split()).strip()
        if len(text.split()) < 4 or not metric_cue.search(text):
            continue
        result.append(text[:1000])
        if len(result) >= 2:
            break
    return result


def _check_metric_claims(chunk: str) -> None:
    for claim in _metric_claims(chunk):
        try:
            verdict = check_claim(claim)
        except Exception:
            continue
        if verdict.lower().startswith("possible contradiction"):
            emit_proactive(
                verdict,
                cue="attention",
                severity="info",
            )


def append_transcript(meeting_id: int, text: str) -> None:
    chunk = " ".join(text.strip().split())
    if not chunk:
        return
    with _connect() as conn:
        row = conn.execute("SELECT status,transcript FROM meetings WHERE id=?", (int(meeting_id),)).fetchone()
        if row is None:
            raise ValueError(f"Meeting {meeting_id} does not exist.")
        if str(row["status"]) != "recording":
            raise ValueError(f"Meeting {meeting_id} is not recording.")
        existing = str(row["transcript"] or "")
        combined = (existing + "\n" + chunk).strip()
        conn.execute("UPDATE meetings SET transcript=? WHERE id=?", (combined[-120000:], int(meeting_id)))
        conn.commit()

    # During an explicitly active meeting-note session, check only concrete metric
    # claims against the user's local index. This is deliberately narrow: it does
    # not score speakers, infer deception/emotion, or treat Jarvis's local records
    # as infallible truth.
    if _metric_claims(chunk):
        _FACT_POOL.submit(_check_metric_claims, chunk)


def _extract_actions(transcript: str) -> list[dict[str, str]]:
    if not transcript.strip():
        return []
    system = """Extract only concrete follow-up commitments and action items from a meeting transcript.
Do not infer hidden intentions or assign an action to a person unless the transcript explicitly supports it.
Return JSON only: {"actions":[{"owner":"speaker label/name if explicit, otherwise unspecified","task":"concise action","due":"explicit due date/time or empty","evidence":"short supporting phrase"}]}
Maximum 12 actions. If none are clear, return an empty list."""
    payload = {
        "model": FAST_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": transcript[-30000:]},
        ],
        "options": {"temperature": 0, "num_predict": 700},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(45.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        parsed = json.loads(str((data.get("message") or {}).get("content") or "{}"))
    except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
        return []
    raw = parsed.get("actions") if isinstance(parsed, dict) else []
    if not isinstance(raw, list):
        return []
    actions: list[dict[str, str]] = []
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        task = " ".join(str(item.get("task") or "").split())[:500]
        if not task:
            continue
        actions.append({
            "owner": " ".join(str(item.get("owner") or "unspecified").split())[:120],
            "task": task,
            "due": " ".join(str(item.get("due") or "").split())[:160],
            "evidence": " ".join(str(item.get("evidence") or "").split())[:300],
        })
    return actions


def finish(meeting_id: int) -> str:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id=?", (int(meeting_id),)).fetchone()
        if row is None:
            raise ValueError(f"Meeting {meeting_id} does not exist.")
        transcript = str(row["transcript"] or "")
    actions = _extract_actions(transcript)
    ended = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE meetings SET ended_at=?,status='completed',action_items_json=? WHERE id=?",
            (ended, json.dumps(actions, ensure_ascii=False), int(meeting_id)),
        )
        conn.commit()
    if not actions:
        return f"Meeting {meeting_id} ended. I did not find any clear commitments to confirm."
    rendered = []
    for index, action in enumerate(actions, start=1):
        owner = action["owner"]
        due = f" due {action['due']}" if action["due"] else ""
        rendered.append(f"{index}) {owner}: {action['task']}{due}")
    return f"Meeting {meeting_id} ended. Proposed action items for confirmation: " + "; ".join(rendered) + "."


def recent(limit: int = 5) -> str:
    safe = max(1, min(int(limit), 20))
    with _connect() as conn:
        rows = conn.execute("SELECT id,started_at,title,status,action_items_json FROM meetings ORDER BY id DESC LIMIT ?", (safe,)).fetchall()
    if not rows:
        return "No meeting-note sessions have been recorded."
    items = []
    for row in rows:
        actions = []
        try:
            actions = json.loads(str(row["action_items_json"] or "[]"))
        except json.JSONDecodeError:
            pass
        title = str(row["title"] or "untitled meeting")
        items.append(f"#{row['id']} {title}, {row['status']}, {len(actions) if isinstance(actions, list) else 0} action items")
    return "Recent meeting notes: " + "; ".join(items) + "."
