from __future__ import annotations

from datetime import datetime

from jarvis_mrb.background_workers import list_tasks
from jarvis_mrb.environment_state import get_state
from jarvis_mrb.tools.google import query_calendar_events, query_emails
from jarvis_mrb.tools.web import web_search, web_status


def _location_label() -> str:
    state = get_state()
    value = str(state.get("location") or "").strip()
    if value and value.lower() not in {"unknown", "home", "away"}:
        return value
    profile = str(state.get("active_profile") or "").strip()
    if profile:
        return profile
    return "the user's current area"


def _source_preview(result: object, *, limit: int = 2) -> str:
    """Render *attributed snippets*; do not turn search snippets into facts."""
    if not bool(getattr(result, "ok", False)):
        return "Unavailable."
    data = getattr(result, "data", None)
    evidence = data.get("evidence") if isinstance(data, dict) else None
    if not isinstance(evidence, list):
        return "No structured source information was returned."
    parts: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        snippet = " ".join(str(item.get("text") or "").split())[:180]
        if not snippet:
            continue
        source = str(item.get("domain") or item.get("title") or "web result")[:90]
        date = str(item.get("date") or "").strip()[:35]
        label = source + (" (" + date + ")" if date else "")
        parts.append(label + " reports: " + snippet)
        if len(parts) >= limit:
            break
    return "; ".join(parts) if parts else "No useful source excerpts were returned."


def generate_briefing() -> str:
    """Model-free briefing: facts remain attributed to their actual sources."""
    calendar = query_calendar_events(direction="future", days=1, limit=8)
    mail = query_emails(query="is:unread in:inbox newer_than:2d", limit=5)

    weather_text = "Unavailable."
    news_text = "Unavailable."
    if web_status().ok:
        weather = web_search(f"weather today in {_location_label()}", num=4, refine=False)
        weather_text = _source_preview(weather, limit=1)
        news = web_search("top important US and world news today", num=6, refine=False)
        news_text = _source_preview(news, limit=3)

    tasks = list_tasks(5)
    active = [task for task in tasks if task.get("status") in {"queued", "running"}]
    task_text = ("None." if not active else "; ".join(
        f"#{task['id']} {task['status']}: {str(task['prompt'])[:90]}"
        for task in active[:5]
    ))
    date = datetime.now().astimezone().strftime("%A, %B %d")
    lines = [
        "Sir, here is your source-backed briefing for " + date + ".",
        "Calendar: " + ((str(calendar.message)[:850]) if calendar.ok else "Unavailable."),
        "Unread inbox: " + ((str(mail.message)[:850]) if mail.ok else "Unavailable."),
        "Weather search excerpt, not a verified observation: " + weather_text,
        "News search excerpts, not independently verified by Jarvis: " + news_text,
        "Background work: " + task_text,
    ]
    return "\n".join(lines)
