from __future__ import annotations

"""Opt-in local World Armor region watches, not a service-startup scheduler.

Only the existing fixed, bounded modelled-AQI/NWS/USGS adapters are eligible.
The runner must be explicitly started on the authorized Jarvis host. A watch
never grants camera, identity, aircraft, worker, messaging or physical actions.
"""

import argparse
from contextlib import closing
from datetime import datetime, timedelta
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
from uuid import uuid4

from jarvis_mrb.world_armor_phase1 import (
    STORE, ArmorDisabled, _clock, _connect, _identifier, _record,
    _require_enabled, observe_once,
)

_MAX_ACTIVE = 12
_LEASE = timedelta(seconds=120)


def _watch_enabled() -> bool:
    return os.getenv("JARVIS_WORLD_ARMOR_WATCHES_ENABLED") == "1"


def _require_watch_enabled() -> None:
    _require_enabled()
    if not _watch_enabled():
        raise ArmorDisabled(
            "Standing watches are OFF; explicitly set "
            "JARVIS_WORLD_ARMOR_WATCHES_ENABLED=1 on the Jarvis host."
        )


def _path(db_path: Path | None) -> Path:
    return Path(db_path) if db_path is not None else STORE


def _refresh(con: sqlite3.Connection, instant: datetime) -> None:
    con.execute(
        "UPDATE watches SET state='expired',lease_token=NULL,lease_until=NULL "
        "WHERE state IN ('active','paused') AND expires_at<=?",
        (instant.isoformat(),),
    )


def _present(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("lease_token", None)
    result.pop("lease_until", None)
    result["collecting"] = bool(result.get("state") == "active"
                                 and row["lease_token"])
    result["runner"] = "explicit_separate_host_process_not_automatic"
    result["notifications_enabled"] = False
    return result


def create_watch(investigation_id: str, *, interval_minutes: int,
                 max_checks: int, lifetime_hours: int,
                 db_path: Path | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
    _require_watch_enabled()
    if (type(interval_minutes) is not int or
            not 30 <= interval_minutes <= 360):
        raise ValueError("Watch interval must be 30–360 whole minutes.")
    if type(max_checks) is not int or not 1 <= max_checks <= 12:
        raise ValueError("Watch budget must be 1–12 source checks.")
    if type(lifetime_hours) is not int or not 1 <= lifetime_hours <= 72:
        raise ValueError("Watch lifetime must be 1–72 whole hours.")
    instant = _clock(now)
    path = _path(db_path)
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        region = _record(con, investigation_id, instant)
        _refresh(con, instant)
        if con.execute(
            "SELECT COUNT(*) FROM watches WHERE state IN ('active','paused')"
        ).fetchone()[0] >= _MAX_ACTIVE:
            raise ValueError("Watch cap reached; stop an existing watch.")
        if max_checks > 20 - region["sample_count"]:
            raise ValueError("Budget exceeds investigation's remaining samples.")
        expiry = min(
            instant + timedelta(hours=lifetime_hours),
            datetime.fromisoformat(region["expires_at"]),
        ).isoformat()
        key = uuid4().hex
        con.execute(
            "INSERT INTO watches(id,investigation_id,created_at,expires_at,"
            "next_due_at,interval_minutes,max_checks,state) "
            "VALUES(?,?,?,?,?,?,?,'active')",
            (key, region["id"], instant.isoformat(), expiry,
             instant.isoformat(), interval_minutes, max_checks),
        )
        record = con.execute(
            "SELECT * FROM watches WHERE id=?", (key,)
        ).fetchone()
    return _present(record)


def list_watches(*, db_path: Path | None = None,
                 investigation_id: str | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
    # Authenticated readback/revocation must remain possible when flags OFF.
    path = _path(db_path)
    if not path.is_file():
        return {"watches": [], "runner_auto_started": False}
    instant = _clock(now)
    with closing(_connect(path, create=True)) as con, con:
        _refresh(con, instant)
        if investigation_id is None:
            rows = con.execute(
                "SELECT * FROM watches ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM watches WHERE investigation_id=? "
                "ORDER BY created_at DESC LIMIT 100",
                (_identifier(investigation_id),),
            ).fetchall()
    return {
        "watches": [_present(row) for row in rows],
        "runner_auto_started": False,
        "watch_feature_enabled": _watch_enabled(),
        "collection_enabled": os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1",
    }


def stop_watch(watch_id: str, *, db_path: Path | None = None,
               now: datetime | None = None) -> dict[str, Any]:
    path = _path(db_path)
    if not path.is_file():
        raise KeyError("No enrolled watch store exists.")
    instant = _clock(now)
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        _refresh(con, instant)
        row = con.execute(
            "SELECT * FROM watches WHERE id=?", (_identifier(watch_id),)
        ).fetchone()
        if row is None:
            raise KeyError("Watch not found.")
        con.execute(
            "UPDATE watches SET state='revoked',lease_token=NULL,"
            "lease_until=NULL WHERE id=? AND state IN ('active','paused')",
            (watch_id,),
        )
        row = con.execute(
            "SELECT * FROM watches WHERE id=?", (watch_id,)
        ).fetchone()
    return {**_present(row),
            "future_collection_authorized": False,
            "past_samples_retained_until_region_forget_or_expiry": True}


def pause_watch(watch_id: str, *, db_path: Path | None = None,
                now: datetime | None = None) -> dict[str, Any]:
    path = _path(db_path)
    if not path.is_file():
        raise KeyError("No enrolled watch store exists.")
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        _refresh(con, _clock(now))
        row = con.execute(
            "SELECT * FROM watches WHERE id=?", (_identifier(watch_id),)
        ).fetchone()
        if row is None:
            raise KeyError("Watch not found.")
        if row["state"] != "active":
            raise ValueError("Only an active watch may be paused.")
        con.execute(
            "UPDATE watches SET state='paused',lease_token=NULL,"
            "lease_until=NULL WHERE id=?", (watch_id,),
        )
        row = con.execute("SELECT * FROM watches WHERE id=?",
                          (watch_id,)).fetchone()
    return _present(row)


def resume_watch(watch_id: str, *, db_path: Path | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
    _require_watch_enabled()
    path = _path(db_path)
    instant = _clock(now)
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        _refresh(con, instant)
        row = con.execute(
            "SELECT * FROM watches WHERE id=?", (_identifier(watch_id),)
        ).fetchone()
        if row is None:
            raise KeyError("Watch not found.")
        if row["state"] != "paused":
            raise ValueError("Only a paused, unexpired watch can resume.")
        con.execute(
            "UPDATE watches SET state='active',next_due_at=?,"
            "lease_token=NULL,lease_until=NULL WHERE id=?",
            (instant.isoformat(), watch_id),
        )
        row = con.execute(
            "SELECT * FROM watches WHERE id=?", (watch_id,)
        ).fetchone()
    return _present(row)


def _claim(db_path: Path, instant: datetime) -> dict[str, Any] | None:
    with closing(_connect(db_path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        _refresh(con, instant)
        row = con.execute(
            "SELECT w.* FROM watches w "
            "JOIN investigations i ON i.id=w.investigation_id "
            "WHERE w.state='active' AND w.next_due_at<=? "
            "AND (w.lease_until IS NULL OR w.lease_until<=?) "
            "AND i.expires_at>? AND i.sample_count<20 "
            "ORDER BY w.next_due_at,w.created_at LIMIT 1",
            (instant.isoformat(), instant.isoformat(), instant.isoformat()),
        ).fetchone()
        if row is None:
            return None
        token = uuid4().hex
        con.execute(
            "UPDATE watches SET lease_token=?,lease_until=?,"
            "check_count=check_count+1,next_due_at=? WHERE id=?",
            (token, (instant + _LEASE).isoformat(),
             (instant + timedelta(minutes=row["interval_minutes"])).isoformat(),
             row["id"]),
        )
        return {
            "id": row["id"], "investigation_id": row["investigation_id"],
            "lease": token, "max_checks": row["max_checks"],
            "check_count": row["check_count"] + 1,
        }


def _finish(db_path: Path, claim: dict[str, Any], *,
            instant: datetime, sample_id: str | None,
            outcome: str) -> dict[str, Any]:
    with closing(_connect(db_path, create=False)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM watches WHERE id=?", (claim["id"],)
        ).fetchone()
        if row is None or row["lease_token"] != claim["lease"]:
            return {"watch_id": claim["id"],
                    "outcome": "revoked_or_superseded_no_watch_completion"}
        if sample_id is not None:
            con.execute(
                "INSERT OR IGNORE INTO watch_receipts "
                "(watch_id,sample_id,collected_at,outcome) VALUES(?,?,?,?)",
                (claim["id"], sample_id, instant.isoformat(), outcome),
            )
        end = (row["expires_at"] <= instant.isoformat()
               or row["check_count"] >= row["max_checks"])
        con.execute(
            "UPDATE watches SET state=?,lease_token=NULL,lease_until=NULL,"
            "last_checked_at=?,last_outcome=? WHERE id=?",
            ("expired" if row["expires_at"] <= instant.isoformat() else
             "exhausted" if end else "active",
             instant.isoformat(), outcome, claim["id"]),
        )
        updated = con.execute(
            "SELECT * FROM watches WHERE id=?", (claim["id"],)
        ).fetchone()
    return {**_present(updated), "outcome": outcome, "sample_id": sample_id}


def run_due_once(*, db_path: Path | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
    """Claim one due watch. No process launches and no phantom notifications."""
    _require_watch_enabled()
    path = _path(db_path)
    if not path.is_file():
        return {"checked": False, "reason": "no_enrolled_watch_store"}
    instant = _clock(now)
    claimed = _claim(path, instant)
    if claimed is None:
        return {"checked": False, "reason": "no_due_authorized_watch"}
    try:
        receipt = observe_once(
            claimed["investigation_id"], db_path=path,
            watch_id=claimed["id"], watch_lease=claimed["lease"],
        )
    except (Exception,) as exc:
        # An exception is not an all-clear. Never publish exception messages,
        # provider URLs, account data or exact locations as watch receipts.
        return _finish(
            path, claimed, instant=_clock(now), sample_id=None,
            outcome="collection_failed_" + type(exc).__name__[:45],
        )
    outcome = ("sample_coverage_ok"
               if receipt["all_sources_available"]
               else "sample_degraded_or_partial")
    return _finish(
        path, claimed, instant=_clock(now),
        sample_id=receipt["sample_id"], outcome=outcome,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit, opt-in local World Armor watch runner."
    )
    parser.add_argument("--once", action="store_true",
                        help="Check at most one due watch and exit.")
    parser.add_argument("--loop", action="store_true",
                        help="Run locally until stopped; no remote worker.")
    args = parser.parse_args()
    if args.once == args.loop:
        parser.error("Choose exactly one of --once or --loop.")
    _require_watch_enabled()
    if args.once:
        print(run_due_once())
        return
    try:
        while True:
            result = run_due_once()
            # A due backlog is bounded. Empty queues sleep; signals stop
            # the process without a hidden service-startup scheduler.
            if not result.get("checked", True):
                time.sleep(60)
    except KeyboardInterrupt:
        print("World Armor local watch runner stopped.")


if __name__ == "__main__":
    main()
