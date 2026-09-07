"""Jarvis for MRB.

The world-model modules historically use ``with sqlite3.connect(...)`` as a
transaction-and-lifetime boundary. Python's standard sqlite3 connection context
manager commits or rolls back on exit, but deliberately does *not* close the file
handle. That is easy to miss on Unix because an open SQLite file can still be
unlinked; on Windows it leaves temporary world databases locked and, in a long-lived
Jarvis process, can retain unnecessary handles until garbage collection.

Keep the compatibility behavior narrowly scoped to Jarvis's world-model database
name. Other SQLite users in this process retain the standard library semantics.
New code should still prefer explicit connection ownership where practical.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

__version__ = "0.1.0"


class _JarvisWorldConnection(sqlite3.Connection):
    """SQLite connection whose context-manager lifetime includes close()."""

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


# Preserve the true stdlib function on the sqlite3 module itself so reloading
# jarvis_mrb cannot accidentally capture our wrapper as the "original" and recurse.
if not hasattr(sqlite3, "_jarvis_original_connect"):
    setattr(sqlite3, "_jarvis_original_connect", sqlite3.connect)
_ORIGINAL_SQLITE_CONNECT = getattr(sqlite3, "_jarvis_original_connect")


def _world_model_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    """Inject closing context semantics only for Jarvis world_model.sqlite3 files."""
    try:
        database_name = Path(os.fspath(database)).name.lower()
    except (TypeError, ValueError):
        database_name = ""

    if database_name == "world_model.sqlite3" and "factory" not in kwargs:
        kwargs["factory"] = _JarvisWorldConnection
    return _ORIGINAL_SQLITE_CONNECT(database, *args, **kwargs)


# Submodules import the shared sqlite3 module object, so installing this once at
# package import fixes all existing world-model _connect() helpers without changing
# unrelated databases.
if not getattr(sqlite3.connect, "_jarvis_world_close_guard", False):
    setattr(_world_model_connect, "_jarvis_world_close_guard", True)
    sqlite3.connect = _world_model_connect
