from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable

_LOCK = threading.RLock()
_INSTALLED = False
_ORIGINAL: Callable[..., Any] | None = None
_STAGED_EXECUTIVE: dict[str, tuple[str, float]] = {}
_STAGED_TTL_SECONDS = 10 * 60


def _is_staged_confirmation(reply: Any) -> bool:
    message = str(getattr(reply, "message", "") or "").strip().lower()
    return message.startswith("ready to ") or message.startswith("certainly, sir. ready to ")


def _safe_result_message(tool: str, reply: Any) -> str:
    raw = str(getattr(reply, "message", "") or "")
    try:
        from jarvis_mrb.permissions import decide

        if decide(str(tool)).risk == "security":
            return "Security-class tool completed; result body omitted from persistent world-model receipt."
    except Exception:
        if str(tool).startswith(("sandbox.", "custom.")):
            return "Security-class tool completed; result body omitted from persistent world-model receipt."
    return raw[:1500]


def _action_key(tool: str, args: dict[str, Any]) -> str:
    return f"{tool}\n{json.dumps(dict(args or {}), ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"


def _executive_decision_id(tool: str, args: dict[str, Any], *, include_superseded: bool = False) -> str:
    """Return one exact persisted Executive decision for this tool+arguments.

    Current decisions are used for ordinary correlation. A staged confirmation may
    later refer to a decision that has since been superseded, so callers validating a
    staged cache may opt into superseded rows. No lexical/fuzzy attribution is used.
    """
    try:
        from jarvis_mrb.world_model import DB_PATH

        rendered_args = json.dumps(dict(args or {}), ensure_ascii=False, sort_keys=True)
        state_clause = "status IN ('current','superseded')" if include_superseded else "status='current'"
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"""
                SELECT id FROM executive_decisions
                WHERE {state_clause} AND proposed_tool=? AND proposed_args_json=?
                ORDER BY CASE status WHEN 'current' THEN 0 ELSE 1 END, updated_at DESC
                LIMIT 2
                """,
                (str(tool), rendered_args),
            ).fetchall()
        finally:
            conn.close()
        if len(rows) == 1:
            return str(rows[0]["id"])
    except Exception:
        pass
    return ""


def _prune_staged(now: float | None = None) -> None:
    current = float(now if now is not None else time.monotonic())
    for key, (_, staged_at) in list(_STAGED_EXECUTIVE.items()):
        if current - staged_at > _STAGED_TTL_SECONDS:
            _STAGED_EXECUTIVE.pop(key, None)


def _stage_executive_decision(tool: str, args: dict[str, Any]) -> None:
    decision_id = _executive_decision_id(tool, args)
    if not decision_id:
        return
    with _LOCK:
        _prune_staged()
        _STAGED_EXECUTIVE[_action_key(tool, args)] = (decision_id, time.monotonic())


def _consume_staged_decision(tool: str, args: dict[str, Any]) -> str:
    key = _action_key(tool, args)
    with _LOCK:
        _prune_staged()
        cached = _STAGED_EXECUTIVE.pop(key, None)
    if not cached:
        return ""
    decision_id, _ = cached
    # Validate that the exact decision/action pair still exists. It may legitimately
    # be superseded while the user is considering a confirmation, but it must never
    # be rebound to different arguments.
    try:
        from jarvis_mrb.world_model import DB_PATH

        rendered_args = json.dumps(dict(args or {}), ensure_ascii=False, sort_keys=True)
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        try:
            row = conn.execute(
                "SELECT 1 FROM executive_decisions WHERE id=? AND proposed_tool=? AND proposed_args_json=?",
                (decision_id, str(tool), rendered_args),
            ).fetchone()
        finally:
            conn.close()
        return decision_id if row else ""
    except Exception:
        return ""


def _record(tool: str, args: dict[str, Any], reply: Any) -> None:
    if str(tool).startswith("world."):
        return
    try:
        from jarvis_mrb.world_model import record_tool_execution

        occurrence_args = dict(args or {})
        # record_tool_execution's event identity includes its sanitized arguments.
        # A private occurrence nonce therefore preserves two identical executions as
        # separate temporal events without changing the executed tool arguments.
        occurrence_args["_world_occurrence_id"] = str(uuid.uuid4())
        action_event_id = record_tool_execution(
            str(tool),
            occurrence_args,
            ok=bool(getattr(reply, "ok", False)),
            message=_safe_result_message(tool, reply),
        )
    except Exception:
        return

    # A successful tool call is only an execution receipt. The verification layer
    # separately records whether the intended state was independently observed.
    try:
        from jarvis_mrb.world_verification import register_execution

        executive_decision_id = _consume_staged_decision(tool, args) or _executive_decision_id(tool, args)
        register_execution(
            str(tool),
            dict(args or {}),
            reply,
            action_event_id=int(action_event_id),
            executive_decision_id=executive_decision_id,
        )
    except Exception:
        pass


def install() -> bool:
    """Install one process-wide audit wrapper around the canonical tool executor."""
    global _INSTALLED, _ORIGINAL
    with _LOCK:
        if _INSTALLED:
            return True
        try:
            import jarvis_mrb.agent as agent_module
            import jarvis_mrb.streaming_agent as streaming_agent_module
        except Exception:
            return False

        original = getattr(agent_module, "execute_tool", None)
        if not callable(original):
            return False
        if getattr(original, "_jarvis_world_audited", False):
            _INSTALLED = True
            _ORIGINAL = original
            return True

        def audited_execute_tool(
            tool: str,
            args: dict[str, Any],
            *,
            bypass_confirmation: bool = False,
        ) -> Any:
            reply = original(tool, args, bypass_confirmation=bypass_confirmation)
            if _is_staged_confirmation(reply):
                _stage_executive_decision(tool, args)
            else:
                _record(tool, args, reply)
            return reply

        setattr(audited_execute_tool, "_jarvis_world_audited", True)
        setattr(audited_execute_tool, "_jarvis_original_execute_tool", original)
        agent_module.execute_tool = audited_execute_tool
        streaming_agent_module.execute_tool = audited_execute_tool
        _ORIGINAL = original
        _INSTALLED = True
        return True


def status() -> dict[str, Any]:
    with _LOCK:
        _prune_staged()
        staged = len(_STAGED_EXECUTIVE)
    return {
        "installed": _INSTALLED,
        "has_original": _ORIGINAL is not None,
        "confirmation_prompts_recorded_as_actions": False,
        "world_introspection_recorded": False,
        "security_result_bodies_persisted": False,
        "repeated_identical_executions_preserved": True,
        "closed_loop_verification_registered": True,
        "executive_decision_correlation": "exact persisted tool+arguments; one-shot staged confirmation cache",
        "staged_executive_confirmations": staged,
        "staged_confirmation_ttl_seconds": _STAGED_TTL_SECONDS,
    }
