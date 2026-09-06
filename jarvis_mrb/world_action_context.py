from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_CURRENT_EXECUTIVE_DECISION_ID: ContextVar[str] = ContextVar(
    "jarvis_current_executive_decision_id",
    default="",
)


def current_decision_id() -> str:
    return str(_CURRENT_EXECUTIVE_DECISION_ID.get() or "")


@contextmanager
def use_decision(decision_id: str | None) -> Iterator[None]:
    token = _CURRENT_EXECUTIVE_DECISION_ID.set(str(decision_id or ""))
    try:
        yield
    finally:
        _CURRENT_EXECUTIVE_DECISION_ID.reset(token)


def status() -> dict[str, object]:
    return {
        "installed": True,
        "context_local": True,
        "current_decision_id": current_decision_id(),
    }
