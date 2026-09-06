from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

_LOCK = threading.RLock()
_INSTALLED = False
_ORIGINAL: Callable[..., Any] | None = None


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

        register_execution(
            str(tool),
            dict(args or {}),
            reply,
            action_event_id=int(action_event_id),
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
            if not _is_staged_confirmation(reply):
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
    return {
        "installed": _INSTALLED,
        "has_original": _ORIGINAL is not None,
        "confirmation_prompts_recorded_as_actions": False,
        "world_introspection_recorded": False,
        "security_result_bodies_persisted": False,
        "repeated_identical_executions_preserved": True,
        "closed_loop_verification_registered": True,
    }
