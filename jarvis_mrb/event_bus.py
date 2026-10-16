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


# Machine-owned labels describe the producing subsystem, not an inference
# that a user noticed or understood the resulting notification.
PROACTIVE_ORIGINS = {
    "calendar_prebrief": "Calendar prebrief with connected context",
    "gpu_pressure": "Observed local GPU resource threshold",
    "resource_pressure": "Observed local hardware or job-queue resource threshold",
    "urgent_mail": "Unread urgent-email subject filter",
    "action_verification": "Failed or timed-out tracked action verification",
    "meeting_contradiction": "Potential discrepancy in meeting notes",
    "external_watch": "Enrolled external watch condition",
    "vision_anomaly": "Vision alert from a user-authorized camera source",
    "agency_attention": "Agency attention mechanism",
    "command_followup": "Proactive response to a command",
    "unknown": "Source was not recorded",
}


def _record_proactive_occurrence(
    message: str, cue: str, severity: str, origin: str = "unknown"
) -> None:
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
                "origin": origin if origin in PROACTIVE_ORIGINS else "unknown",
            },
            evidence="Jarvis emitted this proactive alert to the companion event channel.",
            confidence=1.0,
            participants=[(SELF_ID, "recipient", 1.0)],
            event_key=f"proactive:{occurrence}",
        )
    except Exception:
        # Alert delivery must never depend on world-model persistence.
        pass


def emit_proactive(
    message: str, *, cue: str = "attention", severity: str = "info",
    origin: str = "unknown",
) -> None:
    from jarvis_mrb.attention_budget import may_deliver
    if not may_deliver(severity):
        # Suppression must not masquerade as "alert delivered" in world history.
        return
    companion_events.publish(
        {
            "type": "proactive_alert",
            "message": message,
            "cue": cue,
            "severity": severity,
        }
    )
    # Persist only after publication was attempted. This is still not a
    # delivery/reading acknowledgement from any iPhone or headset.
    _record_proactive_occurrence(message, cue, severity, origin=origin)
