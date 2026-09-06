from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis_mrb.world_model import DB_PATH

TARGET_SCHEMA_VERSION = 4
_BACKUP_RETAIN = 3


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def current_version() -> int:
    if not Path(DB_PATH).exists():
        return 0
    try:
        with _connect() as conn:
            if not _table_exists(conn, "world_schema_meta"):
                return 0
            row = conn.execute(
                "SELECT value FROM world_schema_meta WHERE key='schema_version'"
            ).fetchone()
        return int(row["value"]) if row and str(row["value"]).isdigit() else 0
    except sqlite3.Error:
        return 0


def _has_user_world_data() -> bool:
    path = Path(DB_PATH)
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with _connect() as conn:
            if not _table_exists(conn, "events"):
                return False
            return bool(conn.execute("SELECT 1 FROM events LIMIT 1").fetchone()) or bool(
                conn.execute("SELECT 1 FROM entities LIMIT 1").fetchone()
            )
    except sqlite3.Error:
        return True


def _backup_before_upgrade(from_version: int) -> str:
    path = Path(DB_PATH)
    if not _has_user_world_data():
        return ""
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"world_model.pre-v{TARGET_SCHEMA_VERSION}.from-v{from_version}.{stamp}.sqlite3"
    source = sqlite3.connect(path, timeout=20.0)
    target = sqlite3.connect(destination, timeout=20.0)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()

    backups = sorted(
        backup_dir.glob("world_model.pre-v*.sqlite3"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in backups[_BACKUP_RETAIN:]:
        try:
            old.unlink()
        except OSError:
            pass
    return str(destination)


def _ensure_meta() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS world_schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS world_schema_history (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT NOT NULL
            );
            """
        )
        conn.commit()


def _record_version(version: int, description: str) -> None:
    now = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO world_schema_meta(key,value) VALUES('schema_version',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(version),),
        )
        conn.execute(
            "INSERT OR REPLACE INTO world_schema_history(version,applied_at,description) VALUES(?,?,?)",
            (int(version), now, description[:1000]),
        )
        conn.commit()


def _migration_1_core() -> None:
    from jarvis_mrb.world_model import status as world_status

    world_status()


def _migration_2_relations_and_intentions() -> None:
    from jarvis_mrb.world_executive import status as executive_status
    from jarvis_mrb.world_linker import repair_person_project_relations, status as linker_status

    linker_status()
    executive_status()
    repair_person_project_relations()


def _migration_3_terms_and_document_lineage() -> None:
    from jarvis_mrb.world_document_versions import _connect as document_connect
    from jarvis_mrb.world_terms import status as terms_status

    terms_status()
    conn = document_connect()
    conn.close()


def _migration_4_executive_and_verification() -> None:
    from jarvis_mrb.world_executive_loop import status as executive_loop_status
    from jarvis_mrb.world_verification import status as verification_status

    executive_loop_status()
    verification_status()


_MIGRATIONS: tuple[tuple[int, str, Callable[[], None]], ...] = (
    (1, "Core world entities/events/beliefs/commitments", _migration_1_core),
    (2, "Evidence relations, intentions, and strong person/project semantics", _migration_2_relations_and_intentions),
    (3, "Cross-source term ledger and document lineage", _migration_3_terms_and_document_lineage),
    (4, "Persistent Executive Loop and closed-loop action verification", _migration_4_executive_and_verification),
)


def run_migrations(*, backup: bool = True) -> dict[str, Any]:
    """Bring the additive world-model schema to the single supported target version.

    Migrations are idempotent. Version is advanced only after a step returns without
    error. Existing user data is backed up once before an upgrade when requested.
    SQLite WAL mode is enabled for the shared world database so background readers and
    writers do not unnecessarily block each other.
    """
    before = current_version()
    if before > TARGET_SCHEMA_VERSION:
        raise RuntimeError(
            f"World schema v{before} is newer than this Jarvis build supports (target v{TARGET_SCHEMA_VERSION})."
        )

    backup_path = ""
    if before < TARGET_SCHEMA_VERSION and backup:
        backup_path = _backup_before_upgrade(before)

    _ensure_meta()
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.commit()

    applied: list[int] = []
    version = before
    for target, description, operation in _MIGRATIONS:
        if target <= version:
            continue
        operation()
        _record_version(target, description)
        version = target
        applied.append(target)

    if version != TARGET_SCHEMA_VERSION:
        raise RuntimeError(
            f"World migration stopped at v{version}; expected v{TARGET_SCHEMA_VERSION}."
        )

    return {
        "before": before,
        "after": version,
        "target": TARGET_SCHEMA_VERSION,
        "applied": applied,
        "backup": backup_path,
        "ready": True,
    }


def status() -> dict[str, Any]:
    version = current_version()
    history: list[dict[str, Any]] = []
    try:
        with _connect() as conn:
            if _table_exists(conn, "world_schema_history"):
                rows = conn.execute(
                    "SELECT version,applied_at,description FROM world_schema_history ORDER BY version"
                ).fetchall()
                history = [
                    {
                        "version": int(row["version"]),
                        "applied_at": str(row["applied_at"]),
                        "description": str(row["description"]),
                    }
                    for row in rows
                ]
    except sqlite3.Error:
        pass
    return {
        "current": version,
        "target": TARGET_SCHEMA_VERSION,
        "ready": version == TARGET_SCHEMA_VERSION,
        "history": history,
        "backup_retention": _BACKUP_RETAIN,
    }
