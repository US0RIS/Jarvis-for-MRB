"""Optional shared low-priority interruption budget.

Opt-in via JARVIS_ATTENTION_BUDGET_ENABLED=1. Only low-priority informational
proactive events are rate limited. Warnings, urgent signals and unknown severity
classes bypass the governor to avoid silently hiding a safety issue. No user
message text is saved in this budget ledger.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import os
import threading
from typing import Any


_LOCK=threading.RLock()
_INFO_WINDOW=timedelta(hours=1)
_INFO_LIMIT=3
_entries: deque[datetime]=deque()
_suppressed=0
_delivered=0


def enabled() -> bool:
    return os.environ.get("JARVIS_ATTENTION_BUDGET_ENABLED","0")=="1"


def may_deliver(severity: str, *, now: datetime|None=None) -> bool:
    global _suppressed, _delivered
    if not enabled() or severity.strip().lower() not in {"info","low","notice"}:
        return True
    stamp=now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError("attention timestamps must be offset-aware")
    stamp=stamp.astimezone(timezone.utc)
    with _LOCK:
        cutoff=stamp-_INFO_WINDOW
        while _entries and _entries[0]<=cutoff:
            _entries.popleft()
        if len(_entries)>=_INFO_LIMIT:
            _suppressed+=1
            return False
        _entries.append(stamp)
        _delivered+=1
        return True


def status(*, now: datetime|None=None) -> dict[str,Any]:
    stamp=now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError("attention timestamps must be offset-aware")
    with _LOCK:
        current=sum(t>stamp.astimezone(timezone.utc)-_INFO_WINDOW for t in _entries)
        return {
            "enabled":enabled(),
            "info_used_last_hour":current,
            "info_allowance_per_hour":_INFO_LIMIT,
            "low_priority_suppressed_since_process_start":_suppressed,
            "info_delivered_since_process_start":_delivered,
            "critical_alerts_rate_limited":False,
            "scope":"process_memory_only_no_message_content",
        }


def _reset_for_test() -> None:
    global _suppressed,_delivered
    with _LOCK:
        _entries.clear()
        _suppressed=0
        _delivered=0
