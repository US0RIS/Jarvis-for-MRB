from __future__ import annotations

import os
from typing import Any

import httpx

from jarvis_mrb.background_workers import list_tasks
from jarvis_mrb.environment_state import get_state
from jarvis_mrb.planner_model import FAST_MODEL
from jarvis_mrb.tools.google import query_calendar_events, query_emails
from jarvis_mrb.tools.web import web_answer, web_status

OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def _location_label() -> str:
    state = get_state()
    value = str(state.get("location") or "").strip()
    if value and value.lower() not in {"unknown", "home", "away"}:
        return value
    profile = str(state.get("active_profile") or "").strip()
    if profile:
        return profile
    return "the user's current area"


def generate_briefing() -> str:
    calendar = query_calendar_events(direction="future", days=1, limit=8)
    mail = query_emails(query="is:unread in:inbox newer_than:2d", limit=5)

    weather_text = "Weather unavailable."
    news_text = "News unavailable."
    if web_status().ok:
        weather = web_answer(f"weather today in {_location_label()}", num=5)
        if weather.ok:
            weather_text = weather.message
        news = web_answer("top important US and world news today", num=6)
        if news.ok:
            news_text = news.message

    tasks = list_tasks(5)
    active_tasks = [item for item in tasks if item.get("status") in {"queued", "running"}]
    task_text = "None." if not active_tasks else "; ".join(
        f"#{item['id']} {item['status']}: {str(item['prompt'])[:120]}" for item in active_tasks
    )

    evidence = (
        f"CALENDAR:\n{calendar.message}\n\n"
        f"UNREAD EMAIL:\n{mail.message}\n\n"
        f"WEATHER:\n{weather_text}\n\n"
        f"NEWS:\n{news_text}\n\n"
        f"ACTIVE BACKGROUND WORK:\n{task_text}"
    )
    system = """Produce a concise spoken morning briefing for a personal assistant.
Use only the supplied evidence. Prioritize anything time-sensitive, then calendar, weather, important mail, and only genuinely significant news.
Keep it under about 180 words unless there is an urgent issue. Do not read URLs, IDs, or raw machine formatting. Do not invent missing facts. Address the user as sir once, naturally."""
    payload = {
        "model": FAST_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": evidence[:16000]},
        ],
        "options": {"temperature": 0},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        answer = " ".join(str((data.get("message") or {}).get("content") or "").split()).strip()
        if answer:
            return answer[:2400]
    except (httpx.HTTPError, ValueError, TypeError):
        pass

    return f"Sir, here is the briefing. {calendar.message} {weather_text} {mail.message}"
