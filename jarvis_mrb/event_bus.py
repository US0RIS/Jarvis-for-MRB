from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
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


def emit_proactive(message: str, *, cue: str = "attention", severity: str = "info") -> None:
    companion_events.publish(
        {
            "type": "proactive_alert",
            "message": message,
            "cue": cue,
            "severity": severity,
        }
    )
