from __future__ import annotations

"""Explicit user/host-run, lease-fenced public camera acquisition and notices.

A watcher is a durable source grant, not permission to expand to adjacent
cameras. A single user-defined environmental goal can run for as long as the
operator's source-specific rights, consent, host budget and cadence permit.
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

from jarvis_mrb import world_armor_perception as perception
from jarvis_mrb.world_armor_platform import (
    _bytes_budget, _connect, _dbpath, _enabled, _id, _instant,
    _require_enabled, _LEASE,
)


def _check_permission(row: sqlite3.Row, now: datetime, *, scheduled: bool) -> None:
    if row["state"] != "active":
        raise ValueError("Source grant is paused/stopped.")
    if row["consent_expires_at"] and row["consent_expires_at"] <= now.isoformat():
        raise ValueError("Source consent is expired; re-enrollment required.")
    if row["sample_budget"] is not None and row["check_count"] >= row["sample_budget"]:
        raise ValueError("Explicit source-check budget exhausted.")
    if scheduled and (not row["authorized_automated_access"]
                      or row["cadence_seconds"] <= 0):
        raise ValueError("Automated checks not authorized for this source.")


def _acquire_lease(source_id: str, *, path: Path,
                   now: datetime, scheduled: bool) -> dict[str, Any]:
    _require_enabled()
    _bytes_budget(path)
    with closing(_connect(path, create=True)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM source_grants WHERE id=?", (_id(source_id),),
        ).fetchone()
        if row is None:
            raise KeyError("Source grant absent.")
        _check_permission(row, now, scheduled=scheduled)
        if row["lease_until"] and row["lease_until"] > now.isoformat():
            raise ValueError("Source already has a running observation.")
        if scheduled and row["next_due_at"] and row["next_due_at"] > now.isoformat():
            raise ValueError("Source is not due yet.")
        # Host-budget/contract throttle applies to manually requested checks
        # as well as automated ones when configured by the source operator.
        minimum = row["automated_min_interval_seconds"]
        if row["last_checked_at"] and minimum > 0 and (
            now - datetime.fromisoformat(row["last_checked_at"])
        ).total_seconds() < minimum:
            raise ValueError("Source-specific minimum request interval has not elapsed.")
        lease = uuid4().hex
        con.execute(
            "UPDATE source_grants SET lease_token=?,lease_until=?,"
            "next_due_at=? WHERE id=?",
            (lease, (now + _LEASE).isoformat(),
             (now + timedelta(seconds=row["cadence_seconds"])).isoformat()
             if row["cadence_seconds"] else None, source_id),
        )
    return {**dict(row), "lease": lease}


def _current(con: sqlite3.Connection, row: dict[str, Any],
             now: datetime) -> bool:
    state = con.execute(
        "SELECT state,lease_token,lease_until,consent_expires_at,"
        "sample_budget,check_count FROM source_grants WHERE id=?",
        (row["id"],),
    ).fetchone()
    return bool(
        state and state["state"] == "active"
        and state["lease_token"] == row["lease"]
        and state["lease_until"] and state["lease_until"] > now.isoformat()
        and (state["consent_expires_at"] is None
             or state["consent_expires_at"] > now.isoformat())
        and (state["sample_budget"] is None
             or state["check_count"] < state["sample_budget"])
        and _enabled()
    )


def _prune(con: sqlite3.Connection, row: dict[str, Any], now: datetime) -> None:
    cutoff = (now - timedelta(days=row["retention_days"])).isoformat()
    con.execute(
        "DELETE FROM source_evidence WHERE source_id=? AND received_at<?",
        (row["id"], cutoff),
    )
    con.execute(
        "DELETE FROM source_checks WHERE source_id=? AND checked_at<?",
        (row["id"], cutoff),
    )


def _finish_error(row: dict[str, Any], *, path: Path,
                  error: Exception) -> dict[str, Any]:
    now = _instant()
    with closing(_connect(path)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        if not _current(con, row, now):
            return {"status": "revoked_or_superseded", "source_id": row["id"],
                    "data_saved": False}
        con.execute(
            "UPDATE source_grants SET lease_token=NULL,lease_until=NULL,"
            "last_checked_at=?,last_outcome=?,check_count=check_count+1 WHERE id=?",
            (now.isoformat(), "unavailable", row["id"]),
        )
        con.execute(
            "INSERT INTO source_checks(source_id,checked_at,status,error_type)"
            "VALUES(?,?,?,?)",
            (row["id"], now.isoformat(), "unavailable", type(error).__name__),
        )
        _prune(con, row, now)
    return {
        "status": "unavailable", "source_id": row["id"],
        "error_type": type(error).__name__,
        "source_status": "unknown_not_all_clear", "data_saved": False,
    }


def observe_source(source_id: str, *, db_path: Path | None = None,
                   scheduled: bool = False,
                   now: datetime | None = None) -> dict[str, Any]:
    """The sole host execution path; external bytes and model calls outside SQL locks."""
    start = _instant(now)
    path = _dbpath(db_path)
    row = _acquire_lease(source_id, path=path, now=start, scheduled=scheduled)
    frame: bytes | None = None
    try:
        received = perception.acquire_source(row["kind"], row["locator"])
        frame = received.pop("frame")
        image_hash = received["sha256"]
        if (not image_hash or len(image_hash) != 64 or not frame):
            raise ValueError("Provider yielded no normalized camera frame.")
        if row["last_image_hash"] == image_hash:
            # No model invocation and no evidence/event created for a re-served
            # identical frame. A repeated frame isn't a later verified capture.
            evaluation = None
        else:
            evaluation = perception.interpret_frame(
                frame, row["scene_goal"],
            )
    except Exception as exc:
        return _finish_error(row, path=path, error=exc)
    finally:
        # Nothing persists the model image bytes. Wipe the only local binding.
        frame = None

    finish = _instant() if now is None else _instant(now)
    with closing(_connect(path)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        if not _current(con, row, finish):
            return {"status": "revoked_or_superseded", "source_id": row["id"],
                    "data_saved": False}
        if evaluation is None:
            con.execute(
                "UPDATE source_grants SET lease_token=NULL,lease_until=NULL,"
                "last_checked_at=?,last_outcome=?,check_count=check_count+1 "
                "WHERE id=?",
                (finish.isoformat(), "unchanged_published_frame", row["id"]),
            )
            con.execute(
                "INSERT INTO source_checks(source_id,checked_at,status,error_type)"
                "VALUES(?,?,?,NULL)",
                (row["id"], finish.isoformat(), "unchanged_published_frame"),
            )
            _prune(con, row, finish)
            return {
                "status": "ok", "source_id": row["id"],
                "change_kind": "same_published_image_not_new_capture",
                "model_calls": 0, "evidence_inserted": 0,
                "capture_time_verified": False,
            }

        decision = evaluation["condition_status"]
        old_hash = row["last_image_hash"]
        if decision == "observed":
            streak = row["positive_streak"] + 1
        else:
            streak = 0
        armed = bool(row["alert_armed"])
        if decision == "not_observed":
            armed = True
        # A baseline is evidence but not a notification. Subsequent *distinct*
        # positive frames may produce one uncertainty-qualified notice.
        notice = bool(row["scene_goal"] and old_hash and decision == "observed"
                      and streak >= 2 and armed)
        if notice:
            armed = False
        evidence_id = uuid4().hex
        change = ("baseline" if not old_hash else
                  "different_published_frame_not_verified_scene_change")
        con.execute(
            """INSERT INTO source_evidence
             (id,source_id,image_sha256,description,condition_status,
              scene_goal,source_capture_at,retrieved_at,received_at,
              media_kind,model,source_display,geometry_basis,change_kind)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (evidence_id, row["id"], image_hash,
             evaluation["description"], decision, row["scene_goal"],
             None, received["retrieved_at"], finish.isoformat(),
             received["media_kind"], evaluation["model"],
             received["source_display"], row["spatial_basis"], change),
        )
        if notice:
            con.execute(
                "INSERT INTO source_notices"
                "(id,source_id,evidence_id,created_at,kind,summary)"
                "VALUES(?,?,?,?,?,?)",
                (uuid4().hex, row["id"], evidence_id, finish.isoformat(),
                 "possible_requested_visual_condition",
                 "Selected camera has two DISTINCT published frames "
                 "classified as showing: " + row["scene_goal"]
                 + ". Unconfirmed local-model observations; publisher "
                 "capture times and view footprint unknown. Inspect source."),
            )
        con.execute(
            "UPDATE source_grants SET lease_token=NULL,lease_until=NULL,"
            "last_checked_at=?,last_outcome=?,last_image_hash=?,"
            "positive_streak=?,alert_armed=?,check_count=check_count+1 "
            "WHERE id=?",
            (finish.isoformat(), "ok", image_hash, streak, int(armed),
             row["id"]),
        )
        con.execute(
            "INSERT INTO source_checks(source_id,checked_at,status,error_type)"
            "VALUES(?,?,?,NULL)",
            (row["id"], finish.isoformat(), "ok"),
        )
        _prune(con, row, finish)
    return {
        "status": "ok", "source_id": row["id"],
        "evidence_id": evidence_id, "change_kind": change,
        "condition_status": decision, "notice_created": notice,
        "model_calls": 1, "evidence_inserted": 1,
        "capture_time_verified": False,
        "source_is_current": "not_verified",
        "no_image_retained": True,
    }


def run_due(*, db_path: Path | None = None,
            limit: int = 4, now: datetime | None = None) -> dict[str, Any]:
    _require_enabled()
    if type(limit) is not int or limit < 1:
        raise ValueError("Runner throughput limit must be positive.")
    path = _dbpath(db_path)
    if not path.exists():
        return {"checks": [], "due_remaining": 0}
    instant = _instant(now)
    with closing(_connect(path)) as con:
        rows = con.execute(
            "SELECT id FROM source_grants WHERE state='active' "
            "AND cadence_seconds>0 AND authorized_automated_access=1 "
            "AND next_due_at<=? AND "
            "(lease_until IS NULL OR lease_until<=?) "
            "AND (consent_expires_at IS NULL OR consent_expires_at>?) "
            "AND (sample_budget IS NULL OR check_count<sample_budget) "
            "ORDER BY next_due_at,id LIMIT ?",
            (instant.isoformat(), instant.isoformat(),
             instant.isoformat(), limit),
        ).fetchall()
    receipts = []
    for entry in rows:
        try:
            receipts.append(observe_source(entry["id"], db_path=path,
                                           scheduled=True, now=now))
        except (ValueError, KeyError, RuntimeError) as exc:
            receipts.append({
                "source_id": entry["id"], "status": "not_collected",
                "error_type": type(exc).__name__,
            })
    with closing(_connect(path)) as con:
        left = con.execute(
            "SELECT count(*) FROM source_grants WHERE state='active' "
            "AND cadence_seconds>0 AND authorized_automated_access=1 "
            "AND next_due_at<=? AND "
            "(lease_until IS NULL OR lease_until<=?) "
            "AND (consent_expires_at IS NULL OR consent_expires_at>?) "
            "AND (sample_budget IS NULL OR check_count<sample_budget)",
            (instant.isoformat(), instant.isoformat(), instant.isoformat()),
        ).fetchone()[0]
    return {
        "checks": receipts, "due_remaining": left,
        "scheduler": "explicit_authorized_host_only",
        "remote_workers": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit operator-run World Armor source collector"
    )
    parser.add_argument("--once", action="store_true",
                        help="Collect one bounded batch then exit")
    parser.add_argument("--limit", type=int, default=4,
                        help="Max due source requests per pass")
    parser.add_argument("--interval-seconds", type=int, default=10,
                        help="Host runner wake interval; NOT source polling cadence")
    args = parser.parse_args()
    if args.interval_seconds < 1:
        parser.error("Runner wake interval must be positive.")
    _require_enabled()
    while True:
        print(run_due(limit=args.limit), flush=True)
        if args.once:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
