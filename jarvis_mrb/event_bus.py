from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]


class CompanionEventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, _Subscriber] = {}

    def register(self, loop: asyncio.AbstractEventLoop) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        sid = uuid.uuid4().hex
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers[sid] = _Subscriber(loop=loop, queue=queue)
        return sid, queue

    def unregister(self, sid: str) -> None:
        with self._lock:
            self._subscribers.pop(sid, None)

    def publish(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        with self._lock:
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            def push(sub: _Subscriber = subscriber, item: dict[str, Any] = payload) -> None:
                try:
                    if sub.queue.full():
                        sub.queue.get_nowait()
                    sub.queue.put_nowait(item)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
            try:
                subscriber.loop.call_soon_threadsafe(push)
            except RuntimeError:
                pass


companion_events = CompanionEventBus()


def emit_cue(cue: str, *, message: str | None = None) -> None:
    event: dict[str, Any] = {"type": "cue", "cue": cue}
    if message:
        event["message"] = message
    companion_events.publish(event)


def emit_thinking(active: bool) -> None:
    companion_events.publish(
        {
            "type": "thinking_start" if active else "thinking_stop",
            "cue": "thinking",
        }
    )


def _record_proactive_occurrence(message: str, cue: str, severity: str) -> None:
    """Best-effort durable record of a meaningful unsolicited Jarvis alert.

    Thinking/cue traffic is deliberately not persisted. A proactive alert, however,
    changes what the user has been told and is therefore part of the assistant's
    temporal world history.
    """
    try:
        from jarvis_mrb.world_model import SELF_ID, record_event

        occurrence = uuid.uuid4().hex
        record_event(
            "attention.proactive",
            str(message)[:3000],
            source_kind="proactive_monitor",
            source_ref=occurrence,
            occurred_at=datetime.now().astimezone().isoformat(),
            payload={
                "message": str(message)[:6000],
                "cue": str(cue)[:120],
                "severity": str(severity)[:80],
                "occurrence_id": occurrence,
            },
            evidence="Jarvis emitted this proactive alert to the companion event channel.",
            confidence=1.0,
            participants=[(SELF_ID, "recipient", 1.0)],
            event_key=f"proactive:{occurrence}",
        )
    except Exception:
        # Alert delivery must never depend on world-model persistence.
        pass


def _queue_closed_app_delivery(message: str, severity: str) -> None:
    """Warning/urgent interventions must also reach a phone that is not
    foregrounded (criteria.md C09/C18). APNs is transport only; the durable
    world event above stays the record. Info-level alerts never push."""
    level = str(severity or "").lower()
    if level not in {"warning", "urgent", "critical"}:
        return
    try:
        from jarvis_mrb.world_armor_push import enabled, enqueue_alert

        if not enabled():
            return
        enqueue_alert(
            "proactive:" + " ".join(str(message).split()).lower(),
            priority="urgent" if level in {"urgent", "critical"} else "warning",
            title="Jarvis",
            body=str(message),
        )
    except Exception:
        # Transport failure must never suppress the foreground alert or journal.
        pass


def emit_proactive(message: str, *, cue: str = "attention", severity: str = "info") -> None:
    _record_proactive_occurrence(message, cue, severity)
    _queue_closed_app_delivery(message, severity)
    companion_events.publish(
        {
            "type": "proactive_alert",
            "message": message,
            "cue": cue,
            "severity": severity,
        }
    )
