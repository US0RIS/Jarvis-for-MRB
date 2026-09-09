"""Jarvis for MRB.

Several Jarvis modules historically use ``with sqlite3.connect(...)`` as a
transaction-and-lifetime boundary. Python's standard sqlite3 connection context
manager commits or rolls back on exit, but deliberately does *not* close the file
handle. That is easy to miss on Unix because an open SQLite file can still be
unlinked; on Windows it leaves temporary databases locked and, in a long-lived
Jarvis process, can retain unnecessary handles until garbage collection.

Keep the compatibility behavior narrowly scoped to Jarvis-owned databases whose
existing callers rely on context-manager lifetime: the world model and Research
Receipt audit store. Other SQLite users in this process retain the standard library
semantics. New code should still prefer explicit connection ownership where practical.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

__version__ = "0.1.0"

_JARVIS_CONTEXT_OWNED_DATABASES = {
    "world_model.sqlite3",
    "search_integrity.sqlite3",
}


class _JarvisWorldConnection(sqlite3.Connection):
    """SQLite connection whose context-manager lifetime includes close()."""

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


if not hasattr(sqlite3, "_jarvis_original_connect"):
    setattr(sqlite3, "_jarvis_original_connect", sqlite3.connect)
_ORIGINAL_SQLITE_CONNECT = getattr(sqlite3, "_jarvis_original_connect")


def _world_model_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    """Inject closing context semantics only for explicitly owned Jarvis DB files."""
    try:
        database_name = Path(os.fspath(database)).name.lower()
    except (TypeError, ValueError):
        database_name = ""

    if database_name in _JARVIS_CONTEXT_OWNED_DATABASES and "factory" not in kwargs:
        kwargs["factory"] = _JarvisWorldConnection
    return _ORIGINAL_SQLITE_CONNECT(database, *args, **kwargs)


if not getattr(sqlite3.connect, "_jarvis_world_close_guard", False):
    setattr(_world_model_connect, "_jarvis_world_close_guard", True)
    sqlite3.connect = _world_model_connect


# Optional ForgeCAD integration. It is isolated behind a plugin so Jarvis keeps
# starting normally even if the CAD application is not installed or its bridge is
# temporarily unavailable. All actions still pass through Jarvis's permission path.
if os.environ.get("JARVIS_FORGECAD_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}:
    try:
        from jarvis_mrb.forgecad_plugin import install as _install_forgecad
        _install_forgecad()
    except Exception:
        pass
