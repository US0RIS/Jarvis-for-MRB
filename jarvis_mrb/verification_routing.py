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


def _verification_by_id(verification_id: str) -> sqlite3.Row | None:
    from jarvis_mrb.world_model import DB_PATH

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM action_verifications WHERE id=?",
            (str(verification_id),),
        ).fetchone()
    finally:
        conn.close()


def _observation_expected(row: sqlite3.Row) -> dict[str, Any]:
    """Return an observer-ready expectation without rewriting immutable provenance."""
    try:
        expected = json.loads(str(row["expected_json"] or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        expected = {}
    if not isinstance(expected, dict):
        expected = {}

    if str(row["tool"] or "") != "calendar.create":
        return expected

    try:
        from jarvis_mrb.tools.google import _normalize_calendar_datetime
    except Exception:
        return expected

    normalized_expected = dict(expected)
    for key in ("start", "end"):
        normalized, parsed = _normalize_calendar_datetime(
            normalized_expected.get(key)
        )
        if parsed is not None and normalized:
            normalized_expected[key] = normalized
    return normalized_expected


def _record_terminal_recheck(
    row: sqlite3.Row,
    *,
    outcome: str,
    evidence: str,
    error: str = "",
) -> None:
    """Audit a post-terminal user-requested observation without rewriting history."""
    from jarvis_mrb.world_model import DB_PATH, record_event

    now = datetime.now().astimezone().isoformat()
    verification_id = str(row["id"])
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        conn.execute(
            """
            UPDATE action_verifications
            SET attempts=attempts+1,last_checked_at=?,last_evidence=?,
                last_error=?,updated_at=?
            WHERE id=?
            """,
            (
                now,
                str(evidence)[:3000],
                str(error)[:2000],
                now,
                verification_id,
            ),
        )
        conn.commit()

    try:
        record_event(
            "verification.rechecked",
            (
                f"Fresh post-terminal verification recheck for "
                f"{str(row['tool'])}: {outcome}. {str(evidence)[:1200]}"
            ),
            source_kind="jarvis_verifier",
            source_ref=f"{verification_id}:recheck:{now}",
            occurred_at=now,
            payload={
                "verification_id": verification_id,
                "historical_status": str(row["status"] or ""),
                "recheck_outcome": str(outcome),
                "tool": str(row["tool"] or ""),
                "evidence": str(evidence)[:3000],
            },
            evidence=(
                "Explicit user-requested fresh observation recorded separately "
                "from the immutable terminal verification verdict."
            ),
            confidence=1.0 if outcome in {"verified", "failed"} else 0.9,
        )
    except Exception:
        pass


def _fresh_check(verification_id: str) -> dict[str, Any] | None:
    """Perform a fresh observer pass without rewriting terminal verification history."""
    from jarvis_mrb import world_verification

    row = _verification_by_id(verification_id)
    if row is None:
        return None

    status = str(row["status"] or "")
    expected = _observation_expected(row)
    verifier = str(row["verifier"] or "")

    if status == "pending":
        # Current records should already contain normalized arguments. This explicit
        # observer path also supports legacy rows whose calendar date-times were
        # serialized in older dict-string form, without mutating expected_json.
        try:
            outcome, evidence = world_verification._observe(verifier, expected)
            world_verification._record_observation(
                verification_id,
                outcome=outcome,
                evidence=evidence,
            )
            if outcome in {"verified", "failed"}:
                return world_verification._transition(row, outcome, evidence)
            return world_verification._mark_pending(row, evidence)
        except Exception as exc:
            return world_verification._mark_pending(
                row,
                str(row["last_evidence"] or ""),
                error=str(exc),
            )

    if status != "timed_out":
        return {
            "id": verification_id,
            "status": status,
            "tool": str(row["tool"] or ""),
            "evidence": str(row["last_evidence"] or "")[:1500],
        }

    # A timeout is an immutable statement about what Jarvis knew by its deadline.
    # A later explicit user query may inspect reality again, but it must not mutate
    # timed_out -> verified/failed or append to the closed observation ledger.
    try:
        outcome, evidence = world_verification._observe(verifier, expected)
        _record_terminal_recheck(
            row,
            outcome=outcome,
            evidence=evidence,
        )
        return {
            "id": verification_id,
            "status": outcome if outcome in {"verified", "failed"} else "timed_out",
            "historical_status": "timed_out",
            "late_recheck": True,
            "tool": str(row["tool"] or ""),
            "evidence": str(evidence)[:1500],
        }
    except Exception as exc:
        error = str(exc)[:2000]
        evidence = str(row["last_evidence"] or "")
        _record_terminal_recheck(
            row,
            outcome="observer_error",
            evidence=evidence,
            error=error,
        )
        return {
            "id": verification_id,
            "status": "timed_out",
            "historical_status": "timed_out",
            "late_recheck": True,
            "tool": str(row["tool"] or ""),
            "evidence": evidence[:1500],
            "error": error,
        }


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
    is invoked even when the original verification window previously timed out.
    """
    if not is_verification_query(text):
        return None

    try:
        row = _latest_verification(text)
    except sqlite3.OperationalError:
        return "I do not have a recorded action outcome to verify yet."
    if row is None:
        return "I do not have a recorded action outcome to verify yet."

    verification_id = str(row["id"])
    try:
        fresh = _fresh_check(verification_id)
    except Exception:
        fresh = None

    try:
        refreshed = _latest_verification(text)
    except Exception:
        refreshed = row
    if refreshed is None:
        refreshed = row

    if fresh is not None and bool(fresh.get("late_recheck")):
        status = str(fresh.get("status") or "timed_out")
        tool = str(fresh.get("tool") or refreshed["tool"] or "")
        evidence = str(fresh.get("evidence") or "").strip()
        late_recheck = True
    else:
        status = str(refreshed["status"] or "pending")
        tool = str(refreshed["tool"] or "")
        evidence = str(refreshed["last_evidence"] or "").strip()
        late_recheck = False
    label = _human_tool(tool)

    if status == "verified":
        detail = f" {evidence}" if evidence else ""
        prefix = (
            "Yes. A fresh independent recheck now verified"
            if late_recheck
            else "Yes. I independently verified"
        )
        return f"{prefix} the {label}.{detail}".strip()
    if status == "failed":
        detail = f" {evidence}" if evidence else ""
        prefix = (
            "No. A fresh independent recheck now shows"
            if late_recheck
            else "No."
        )
        if late_recheck:
            return f"{prefix} the {label} failed.{detail}".strip()
        return f"No. The {label} failed.{detail}".strip()
    if status == "timed_out":
        detail = f" {evidence}" if evidence else ""
        return f"I still could not independently verify the {label} after a fresh check.{detail}".strip()
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
        "late_timeout_recovery": True,
        "repeat_action_on_did_that_work": False,
    }
