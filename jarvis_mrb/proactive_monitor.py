from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any, Callable

import httpx

from jarvis_mrb.environment_state import get_state
from jarvis_mrb.event_bus import emit_proactive
from jarvis_mrb.planner_model import FAST_MODEL
from jarvis_mrb.tools.google import query_calendar_events, query_emails

OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_LOCK = threading.RLock()
_LAST_ALERTS: dict[str, float] = {}
_STARTED = False


def _health_success(subsystem: str) -> None:
    try:
        from jarvis_mrb.runtime_health import record_success
        record_success(subsystem)
    except Exception:
        pass


def _health_failure(subsystem: str, error: object) -> None:
    try:
        from jarvis_mrb.runtime_health import record_failure
        record_failure(subsystem, error)
    except Exception:
        pass


def _run_isolated(subsystem: str, operation: Callable[[], None]) -> None:
    try:
        operation()
        _health_success(subsystem)
    except Exception as exc:
        _health_failure(subsystem, exc)


def _install_action_audit() -> bool:
    try:
        from jarvis_mrb.tool_audit import install as install_tool_audit
        return bool(install_tool_audit())
    except Exception as exc:
        _health_failure("action_audit", exc)
        return False


# service.py imports proactive_monitor before it starts scheduler/background threads.
# Bring the shared world schema to the one supported version before any runtime thread
# can observe or mutate it. Migration failure is intentionally fatal: running with a
# partially known schema is less safe than refusing to start.
from jarvis_mrb.world_migrations import run_migrations as _run_world_migrations

_MIGRATION_STATE = _run_world_migrations()
_AUDIT_READY = _install_action_audit()
if not _AUDIT_READY:
    raise RuntimeError("Jarvis action audit/verification wrapper could not be installed safely.")
_health_success("world_migrations")
_health_success("action_audit")


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
        except httpx.HTTPError as exc:
            _health_failure("meeting_prefetch_model", exc)
        else:
            _health_success("meeting_prefetch_model")
        try:
            from jarvis_mrb.knowledge_index import search
            search(summary, limit=3)
        except Exception as exc:
            _health_failure("meeting_prefetch_knowledge", exc)
        else:
            _health_success("meeting_prefetch_knowledge")

    threading.Thread(target=work, name="jarvis-meeting-prefetch", daemon=True).start()


def _contextual_prebrief(event_id: str, summary: str) -> dict[str, Any] | None:
    try:
        from jarvis_mrb.world_prebrief import build
        return build(event_id, summary)
    except Exception as exc:
        _health_failure("world_prebrief", exc)
        return None


def _check_calendar() -> None:
    now = datetime.now().astimezone()
    result = query_calendar_events(direction="future", days=1, limit=8)
    if not result.ok or not result.data:
        if not result.ok:
            raise RuntimeError(result.message)
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
        if not result.ok:
            raise RuntimeError(result.message)
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
    from jarvis_mrb.world_verification import check_due

    outcomes = check_due(limit=20)
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


def _proactive_enabled() -> bool:
    try:
        state = get_state()
        preferences = state.get("preferences") if isinstance(state.get("preferences"), dict) else {}
        _health_success("environment_state_read")
        return preferences.get("proactive_monitoring", True) is not False
    except Exception as exc:
        _health_failure("environment_state_read", exc)
        # A preference read failure must not disable verification or calendar safety
        # checks silently. Default to the documented enabled behavior.
        return True


def _check_agency_runtime() -> None:
    """Advance persistent desired states with a small action and interruption budget."""
    from jarvis_mrb.agency_attention import consider
    from jarvis_mrb.agency_runtime import tick_all
    from jarvis_mrb.desired_state import get_desired_state

    report = tick_all(max_actions=2, limit=50)
    candidates: list[dict[str, Any]] = []
    for item in report.get("results") or []:
        state_id = str(item.get("desired_state_id") or "")
        state = get_desired_state(state_id) or {}
        title = str(state.get("title") or state_id or "an Agency goal")
        status = str(item.get("status") or "")
        plan = item.get("plan") if isinstance(item.get("plan"), dict) else {}

        if status == "awaiting_approval":
            waiting = [
                step for step in (plan.get("steps") or [])
                if str(step.get("status") or "") == "awaiting_approval"
            ]
            step = waiting[0] if waiting else {}
            tool = str(step.get("tool") or "a protected action")
            candidates.append(
                {
                    "kind": "approval_required",
                    "message": f"Agency needs your approval to continue {title}: {tool}.",
                    "desired_state_id": state_id,
                    "dedup_key": f"agency-approval:{plan.get('id')}:{step.get('id')}",
                    "benefit": 90,
                    "urgency": 70,
                    "confidence": 1.0,
                    "error_cost": 0,
                    "attention_cost": 20,
                    "severity": "warning",
                    "dedup_seconds": 24 * 3600,
                }
            )
        elif status == "blocked":
            candidates.append(
                {
                    "kind": "blocked",
                    "message": f"Agency is blocked on {title}.",
                    "desired_state_id": state_id,
                    "dedup_key": f"agency-blocked:{state_id}:{state.get('blocked_reason')}",
                    "benefit": 55,
                    "urgency": 20,
                    "confidence": 1.0,
                    "error_cost": 10,
                    "attention_cost": 25,
                    "severity": "info",
                    "dedup_seconds": 24 * 3600,
                }
            )
        elif status == "satisfied":
            candidates.append(
                {
                    "kind": "satisfied",
                    "message": f"Agency satisfied {title}.",
                    "desired_state_id": state_id,
                    "dedup_key": f"agency-satisfied:{state_id}:{state.get('satisfied_at')}",
                    "benefit": 20,
                    "urgency": 0,
                    "confidence": 1.0,
                    "error_cost": 0,
                    "attention_cost": 25,
                    "severity": "info",
                    "dedup_seconds": 7 * 24 * 3600,
                }
            )

    # At most one *new* interruption per monitor cycle. A duplicate of a previously
    # emitted candidate does not consume the budget, allowing the next waiting
    # exception to surface. Deferred candidates remain queryable and eligible later.
    interruption_budget = 1
    for candidate in candidates:
        result = consider(
            **candidate,
            allow_emit=interruption_budget > 0,
            suppress_reason="one-new-Agency-interruption-per-monitor-cycle",
        )
        if result.get("emitted"):
            interruption_budget -= 1


def _check_desired_states() -> None:
    """Continuously reconcile declarative desired states against the world model.

    This is intentionally observation-only. It may close or reopen a desired state
    based on explicit machine-evaluable criteria, but it never grants action authority.
    Planning/execution remains behind the normal Executive and permission layers.
    """
    from jarvis_mrb.desired_state import (
        check_wake_watches,
        evaluate_desired_state,
        list_desired_states,
        sync_from_intentions,
    )

    sync_from_intentions()
    try:
        from jarvis_mrb.agency_capability import reconcile_gaps
        reconcile_gaps()
    except Exception as exc:
        _health_failure("agency_capability_reconcile", exc)
    check_wake_watches()
    for item in list_desired_states(limit=200):
        if str(item.get("state") or "") in {"blocked", "paused", "retired"}:
            continue
        evaluate_desired_state(str(item["id"]), persist=True)


def check_once() -> None:
    proactive = _proactive_enabled()
    if proactive:
        _run_isolated("proactive_calendar", _check_calendar)
        _run_isolated("proactive_urgent_mail", _check_urgent_mail)

    # Verification and persistent desired-state control are correctness/safety
    # loops, not optional notification features. Disabling general proactive
    # suggestions must not strand an already-approved action or active Agency goal.
    _run_isolated("action_verification", _check_action_verifications)
    _run_isolated("desired_state_evaluation", _check_desired_states)
    _run_isolated("agency_runtime", _check_agency_runtime)


def _loop() -> None:
    time.sleep(8)
    cycle = 0
    while True:
        proactive = _proactive_enabled()
        if proactive:
            _run_isolated("proactive_calendar", _check_calendar)
            if cycle % 3 == 0:
                _run_isolated("proactive_urgent_mail", _check_urgent_mail)

        # Always keep outcome verification and the persistent Agency control loop
        # alive. Agency's own mode/permissions determine whether any action occurs.
        _run_isolated("action_verification", _check_action_verifications)
        _run_isolated("desired_state_evaluation", _check_desired_states)
        _run_isolated("agency_runtime", _check_agency_runtime)

        cycle += 1
        time.sleep(60)


def _start_optional(subsystem: str, starter: Callable[[], None]) -> None:
    try:
        starter()
        _health_success(subsystem)
    except Exception as exc:
        _health_failure(subsystem, exc)


def start() -> None:
    global _STARTED, _AUDIT_READY
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True

    if not _AUDIT_READY:
        _AUDIT_READY = _install_action_audit()
        if not _AUDIT_READY:
            raise RuntimeError("Jarvis action audit/verification wrapper is unavailable.")

    try:
        from jarvis_mrb.pc_context import start as start_pc_context
        _start_optional("pc_context", start_pc_context)
    except Exception as exc:
        _health_failure("pc_context", exc)
    try:
        from jarvis_mrb.resource_monitor import start as start_resource_monitor
        _start_optional("resource_monitor", start_resource_monitor)
    except Exception as exc:
        _health_failure("resource_monitor", exc)
    try:
        from jarvis_mrb.audio_damping import start as start_audio_damping
        _start_optional("audio_damping", start_audio_damping)
    except Exception as exc:
        _health_failure("audio_damping", exc)
    try:
        from jarvis_mrb.daily_journal import start as start_daily_journal
        _start_optional("daily_journal", start_daily_journal)
    except Exception as exc:
        _health_failure("daily_journal", exc)

    threading.Thread(target=_loop, name="jarvis-proactive", daemon=True).start()
    _health_success("proactive_loop")
