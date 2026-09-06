from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any

import httpx

from jarvis_mrb.environment_state import get_state
from jarvis_mrb.event_bus import emit_proactive
from jarvis_mrb.planner_model import FAST_MODEL
from jarvis_mrb.tools.google import query_calendar_events, query_emails

OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_LOCK = threading.RLock()
_LAST_ALERTS: dict[str, float] = {}
_STARTED = False


def _install_action_audit() -> bool:
    try:
        from jarvis_mrb.tool_audit import install as install_tool_audit

        return bool(install_tool_audit())
    except Exception:
        return False


# service.py imports proactive_monitor before it starts scheduler/background threads.
# Install the action-ingestion wrapper at import time so even startup-due jobs are
# tracked. start() retries if module initialization happened in an unusual order.
_AUDIT_READY = _install_action_audit()


def _dedup(key: str, seconds: int = 3600) -> bool:
    now = time.time()
    with _LOCK:
        last = _LAST_ALERTS.get(key, 0.0)
        if now - last < seconds:
            return False
        _LAST_ALERTS[key] = now
        for old_key, value in list(_LAST_ALERTS.items()):
            if now - value > 24 * 3600:
                _LAST_ALERTS.pop(old_key, None)
    return True


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone() if parsed.tzinfo is not None else parsed.astimezone()
    except (TypeError, ValueError):
        return None


def _prefetch_for_event(event_id: str, summary: str) -> None:
    if not _dedup(f"prefetch:{event_id}", 4 * 3600):
        return

    def work() -> None:
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0, connect=2.0)) as client:
                client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": FAST_MODEL, "prompt": "", "keep_alive": "30m"},
                )
        except httpx.HTTPError:
            pass
        try:
            from jarvis_mrb.knowledge_index import search
            search(summary, limit=3)
        except Exception:
            pass

    threading.Thread(target=work, name="jarvis-meeting-prefetch", daemon=True).start()


def _contextual_prebrief(event_id: str, summary: str) -> dict[str, Any] | None:
    try:
        from jarvis_mrb.world_prebrief import build

        return build(event_id, summary)
    except Exception:
        return None


def _check_calendar() -> None:
    now = datetime.now().astimezone()
    result = query_calendar_events(direction="future", days=1, limit=8)
    if not result.ok or not result.data:
        return
    for event in result.data.get("events", []):
        if not isinstance(event, dict):
            continue
        start_raw = str(event.get("start") or "")
        if "T" not in start_raw:
            continue
        start = _parse_time(start_raw)
        if not start:
            continue
        minutes = (start - now).total_seconds() / 60.0
        if minutes < 0 or minutes > 60:
            continue
        event_id = str(event.get("id") or event.get("summary") or start_raw)
        summary = str(event.get("summary") or "your next event")
        location = str(event.get("location") or "").strip()

        if 3 <= minutes <= 8:
            _prefetch_for_event(event_id, summary)

        if 12 < minutes <= 35:
            prebrief = _contextual_prebrief(event_id, summary)
            if prebrief:
                if _dedup(f"calendar-context:{event_id}", 4 * 3600):
                    emit_proactive(
                        str(prebrief.get("message") or ""),
                        cue="attention",
                        severity=str(prebrief.get("severity") or "info"),
                    )
                continue

        if minutes <= 12:
            if not _dedup(f"calendar-urgent:{event_id}", 45 * 60):
                continue
            rounded = max(1, int(round(minutes)))
            suffix = f" at {location}" if location else ""
            emit_proactive(
                f"You have {summary} in about {rounded} minutes{suffix}.",
                cue="attention",
                severity="warning",
            )
        elif minutes <= 45:
            if not _dedup(f"calendar-soon:{event_id}", 2 * 3600):
                continue
            rounded = int(round(minutes / 5.0) * 5)
            emit_proactive(
                f"Your next event, {summary}, starts in about {rounded} minutes.",
                cue="attention",
                severity="info",
            )


def _check_urgent_mail() -> None:
    result = query_emails(
        query='is:unread in:inbox newer_than:1d {subject:"urgent" subject:"action required" subject:"deadline"}',
        limit=3,
    )
    if not result.ok or not result.data:
        return
    for email in result.data.get("emails", []):
        if not isinstance(email, dict) or not email.get("unread"):
            continue
        message_id = str(email.get("id") or "")
        if not message_id or not _dedup(f"urgent-email:{message_id}", 6 * 3600):
            continue
        sender = str(email.get("sender") or "someone")
        subject = str(email.get("subject") or "(no subject)")
        emit_proactive(
            f"There is an unread message from {sender} with the subject {subject}.",
            cue="attention",
            severity="warning",
        )


def _check_action_verifications() -> None:
    try:
        from jarvis_mrb.world_verification import check_due

        outcomes = check_due(limit=20)
    except Exception:
        return
    for item in outcomes:
        status = str(item.get("status") or "")
        if status not in {"failed", "timed_out"}:
            continue
        verification_id = str(item.get("id") or "")
        if not verification_id or not _dedup(f"verification:{verification_id}:{status}", 24 * 3600):
            continue
        tool = str(item.get("tool") or "action")
        evidence = " ".join(str(item.get("evidence") or "").split())[:480]
        if status == "failed":
            message = f"A tracked action did not achieve its verified outcome: {tool}."
        else:
            message = f"I could not verify the outcome of a tracked action before its deadline: {tool}."
        if evidence:
            message += f" {evidence}"
        emit_proactive(message, cue="error", severity="warning")


def check_once() -> None:
    state = get_state()
    preferences = state.get("preferences") if isinstance(state.get("preferences"), dict) else {}
    if preferences.get("proactive_monitoring", True) is False:
        return
    _check_calendar()
    _check_urgent_mail()
    _check_action_verifications()


def _loop() -> None:
    time.sleep(8)
    cycle = 0
    while True:
        try:
            _check_calendar()
            _check_action_verifications()
            if cycle % 3 == 0:
                _check_urgent_mail()
        except Exception:
            pass
        cycle += 1
        time.sleep(60)


def start() -> None:
    global _STARTED, _AUDIT_READY
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True

    if not _AUDIT_READY:
        _AUDIT_READY = _install_action_audit()

    try:
        from jarvis_mrb.pc_context import start as start_pc_context
        start_pc_context()
    except Exception:
        pass
    try:
        from jarvis_mrb.resource_monitor import start as start_resource_monitor
        start_resource_monitor()
    except Exception:
        pass
    try:
        from jarvis_mrb.audio_damping import start as start_audio_damping
        start_audio_damping()
    except Exception:
        pass
    try:
        from jarvis_mrb.daily_journal import start as start_daily_journal
        start_daily_journal()
    except Exception:
        pass

    threading.Thread(target=_loop, name="jarvis-proactive", daemon=True).start()
