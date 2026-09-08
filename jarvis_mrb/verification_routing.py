from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime
from types import ModuleType
from typing import Any

_LOCK = threading.RLock()
_INSTALLED = False

_EXACT_CUES = {
    "did it work",
    "did that work",
    "did it happen",
    "did that happen",
    "was it sent",
    "was that sent",
    "was it created",
    "was that created",
    "did you verify it",
    "did you verify that",
    "is it verified",
    "is that verified",
    "has it been verified",
    "has that been verified",
    "what was the outcome",
    "what happened with that",
    "what happened with it",
    "are we still waiting",
    "still waiting",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower()).strip(" .?!")


def is_verification_query(text: str) -> bool:
    normalized = _normalize(text)
    if normalized in _EXACT_CUES:
        return True
    return (
        normalized.startswith("did you verify ")
        or normalized.startswith("was the email sent")
        or normalized.startswith("was the message sent")
        or normalized.startswith("was the event created")
        or normalized.startswith("was the calendar event created")
        or normalized.startswith("what happened with the action")
        or normalized.startswith("what is the status of that action")
        or normalized.startswith("what's the status of that action")
    )


def _preferred_tool(text: str) -> str:
    normalized = _normalize(text)
    if any(token in normalized for token in ("email", "message", "sent")):
        return "gmail.send"
    if any(token in normalized for token in ("calendar", "event", "created")):
        return "calendar.create"
    return ""


def _latest_verification(text: str) -> sqlite3.Row | None:
    from jarvis_mrb.world_model import DB_PATH

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        preferred = _preferred_tool(text)
        if preferred:
            row = conn.execute(
                "SELECT * FROM action_verifications WHERE tool=? ORDER BY created_at DESC LIMIT 1",
                (preferred,),
            ).fetchone()
            if row is not None:
                return row
        return conn.execute(
            "SELECT * FROM action_verifications ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


def _repair_calendar_expectation(row: sqlite3.Row) -> bool:
    if str(row["tool"]) != "calendar.create":
        return False
    try:
        expected = json.loads(str(row["expected_json"] or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(expected, dict):
        return False

    try:
        from jarvis_mrb.tools.google import _normalize_calendar_datetime
    except Exception:
        return False

    changed = False
    for key in ("start", "end"):
        normalized, parsed = _normalize_calendar_datetime(expected.get(key))
        if parsed is not None and normalized and normalized != expected.get(key):
            expected[key] = normalized
            changed = True
    if not changed:
        return False

    from jarvis_mrb.world_model import DB_PATH

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    try:
        conn.execute(
            "UPDATE action_verifications SET expected_json=?,updated_at=? WHERE id=?",
            (
                json.dumps(expected, ensure_ascii=False, sort_keys=True),
                datetime.now().astimezone().isoformat(),
                str(row["id"]),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return True


def _human_tool(tool: str) -> str:
    return {
        "calendar.create": "calendar event",
        "gmail.send": "email",
        "pc.launch_app": "app launch",
        "pc.close_app": "app close",
        "browser.open_site": "browser action",
        "browser.close_tab": "browser action",
        "state.update": "state change",
        "state.temp_set": "temporary state change",
    }.get(str(tool), "action")


def reply_for_query(text: str) -> str | None:
    """Return a deterministic closed-loop answer for explicit outcome questions.

    This path deliberately bypasses the planner. Asking whether an action worked must
    never cause the planner to repeat the action itself. A fresh independent observer
    is invoked when the verification is still pending.
    """
    if not is_verification_query(text):
        return None

    try:
        row = _latest_verification(text)
    except sqlite3.OperationalError:
        return "I do not have a recorded action outcome to verify yet."
    if row is None:
        return "I do not have a recorded action outcome to verify yet."

    try:
        _repair_calendar_expectation(row)
    except Exception:
        pass

    verification_id = str(row["id"])
    try:
        from jarvis_mrb.world_verification import check_one

        check_one(verification_id, force=True)
    except Exception:
        pass

    try:
        refreshed = _latest_verification(text)
    except Exception:
        refreshed = row
    if refreshed is None:
        refreshed = row

    status = str(refreshed["status"] or "pending")
    tool = str(refreshed["tool"] or "")
    label = _human_tool(tool)
    evidence = str(refreshed["last_evidence"] or "").strip()

    if status == "verified":
        detail = f" {evidence}" if evidence else ""
        return f"Yes. I independently verified the {label}.{detail}".strip()
    if status == "failed":
        detail = f" {evidence}" if evidence else ""
        return f"No. The {label} failed.{detail}".strip()
    if status == "timed_out":
        detail = f" {evidence}" if evidence else ""
        return f"I could not independently verify the {label} before the verification deadline.{detail}".strip()
    if status == "unverified":
        detail = f" {evidence}" if evidence else ""
        return f"The {label} returned success, but there is no independent observer for its effect, so I am not calling it verified.{detail}".strip()

    detail = f" {evidence}" if evidence else ""
    return f"The {label} was attempted, but I have not independently verified the outcome yet.{detail}".strip()


def install(agent_module: ModuleType, streaming_agent_module: ModuleType) -> bool:
    """Install one verification-aware fast path into both command transports."""
    global _INSTALLED
    with _LOCK:
        current = getattr(agent_module, "_fast_path", None)
        if not callable(current):
            return False
        if getattr(current, "_jarvis_verification_routing", False):
            setattr(streaming_agent_module, "_fast_path", current)
            _INSTALLED = True
            return True

        original = current

        def verification_fast_path(text: str) -> Any:
            message = reply_for_query(text)
            if message is not None:
                return agent_module.AgentReply(True, message)
            return original(text)

        setattr(verification_fast_path, "_jarvis_verification_routing", True)
        setattr(verification_fast_path, "_jarvis_original_fast_path", original)
        agent_module._fast_path = verification_fast_path
        # streaming_agent imported _fast_path by value, so update its module-global
        # reference as well. Both transports now share identical outcome semantics.
        streaming_agent_module._fast_path = verification_fast_path
        _INSTALLED = True
        return True


def status() -> dict[str, Any]:
    return {
        "installed": _INSTALLED,
        "planner_bypassed_for_outcome_queries": True,
        "calendar_legacy_expectation_repair": True,
        "fresh_independent_check_on_query": True,
        "repeat_action_on_did_that_work": False,
    }
