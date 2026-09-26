from __future__ import annotations

"""Capability/load-aware World Armor orchestration over explicit Mesh observers.

Windows is the authority for source grants, cadence, leases, retention,
normalization and final evidence. Remote workers are explicitly configured,
identity-verified, capability-scoped and privately transported. The scheduler
uses authenticated worker load plus controller-owned failure/cooldown history;
it never discovers hosts, supplies arbitrary network targets or grants action
authority.
"""

import argparse
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import time
from typing import Any

from jarvis_mrb.world_armor_movement import (
    _connect, _dbpath, _instant, _require_enabled, collect_source,
)

_COOLDOWN_BASE_SECONDS = 15
_COOLDOWN_MAX_SECONDS = 300


def _remote_capabilities(capabilities: dict[str, Any]) -> list[str]:
    advertised = capabilities.get("world_observer_capabilities")
    if isinstance(advertised, list):
        return [str(x) for x in advertised if isinstance(x, str)]
    if capabilities.get("world_observer") == "opensky_region_read_only":
        return ["opensky_region_read_only"]
    return []


def _orchestration_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS world_worker_dispatch_health (
      worker_id TEXT PRIMARY KEY,
      success_count INTEGER NOT NULL DEFAULT 0,
      failure_count INTEGER NOT NULL DEFAULT 0,
      consecutive_failures INTEGER NOT NULL DEFAULT 0,
      last_success_at TEXT,
      last_failure_at TEXT,
      cooldown_until TEXT
    );
    """)


def _health_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        with closing(_connect(path)) as con:
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='world_worker_dispatch_health'"
            ).fetchone()
            if not exists:
                return {}
            rows = con.execute(
                "SELECT * FROM world_worker_dispatch_health"
            ).fetchall()
            return {str(row["worker_id"]): dict(row) for row in rows}
    except (sqlite3.Error, KeyError):
        return {}


def _record_worker_result(
    path: Path, worker_id: str, *, success: bool, now: datetime,
) -> None:
    if worker_id == "windows":
        return
    with closing(_connect(path, create=True)) as con, con:
        _orchestration_schema(con)
        current = con.execute(
            "SELECT * FROM world_worker_dispatch_health WHERE worker_id=?",
            (worker_id,),
        ).fetchone()
        successes = int(current["success_count"]) if current else 0
        failures = int(current["failure_count"]) if current else 0
        consecutive = int(current["consecutive_failures"]) if current else 0
        if success:
            con.execute(
                """INSERT INTO world_worker_dispatch_health
                   (worker_id,success_count,failure_count,consecutive_failures,
                    last_success_at,last_failure_at,cooldown_until)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(worker_id) DO UPDATE SET
                     success_count=excluded.success_count,
                     failure_count=excluded.failure_count,
                     consecutive_failures=0,
                     last_success_at=excluded.last_success_at,
                     cooldown_until=NULL""",
                (
                    worker_id, successes + 1, failures, 0,
                    now.isoformat(),
                    current["last_failure_at"] if current else None,
                    None,
                ),
            )
            return
        consecutive += 1
        delay = min(
            _COOLDOWN_MAX_SECONDS,
            _COOLDOWN_BASE_SECONDS * (2 ** min(consecutive - 1, 5)),
        )
        cooldown = (now + timedelta(seconds=delay)).isoformat()
        con.execute(
            """INSERT INTO world_worker_dispatch_health
               (worker_id,success_count,failure_count,consecutive_failures,
                last_success_at,last_failure_at,cooldown_until)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(worker_id) DO UPDATE SET
                 success_count=excluded.success_count,
                 failure_count=excluded.failure_count,
                 consecutive_failures=excluded.consecutive_failures,
                 last_failure_at=excluded.last_failure_at,
                 cooldown_until=excluded.cooldown_until""",
            (
                worker_id, successes, failures + 1, consecutive,
                current["last_success_at"] if current else None,
                now.isoformat(), cooldown,
            ),
        )


def _metrics(value: Any) -> dict[str, float | int]:
    data = value if isinstance(value, dict) else {}
    try:
        active = max(0, int(data.get("active_requests", 0)))
        capacity = max(1, min(16, int(data.get("capacity", 1))))
        load = max(0.0, float(data.get("normalized_load", 0.0)))
    except (TypeError, ValueError):
        active, capacity, load = 0, 1, 0.0
    return {
        "active_requests": active,
        "capacity": capacity,
        "normalized_load": round(load, 4),
    }


def available_workers(*, db_path: Path | None = None) -> dict[str, Any]:
    from jarvis_mrb import reality_mesh
    fabric = reality_mesh.nodes()
    health = _health_snapshot(_dbpath(db_path))
    workers = [{
        "id": "windows", "status": "online",
        "capabilities": [
            "local_all_movement_adapters",
            "local_all_camera_adapters",
            "aisstream_pooled_controller",
        ],
        "worker_metrics": {
            "active_requests": 0, "capacity": 1, "normalized_load": 0.0,
        },
        "dispatch_health": {},
    }]
    for node in fabric.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        capabilities = node.get("capabilities")
        if (node_id == "windows" or node.get("status") != "online"
                or not isinstance(capabilities, dict)):
            continue
        advertised = _remote_capabilities(capabilities)
        if not advertised:
            continue
        workers.append({
            "id": node_id, "status": "online",
            "capabilities": advertised,
            "observed_at": node.get("observed_at"),
            "worker_metrics": _metrics(node.get("worker_metrics")),
            "dispatch_health": health.get(node_id, {}),
        })
    return {
        "workers": workers,
        "network_discovery": False,
        "controller": "windows",
        "credential_delegation": False,
        "remote_arbitrary_rpc": False,
        "private_network_camera_fetch": False,
        "worker_registry": "explicit_environment_configuration",
        "worker_count_cap": None,
    }


def _cooling(worker: dict[str, Any], now: datetime) -> bool:
    until = (worker.get("dispatch_health") or {}).get("cooldown_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(str(until)) > now
    except (TypeError, ValueError):
        return True


def _select_remote(
    capability: str, workers: list[dict[str, Any]],
    assignments: dict[str, int], now: datetime,
) -> str | None:
    candidates: list[tuple[float, str]] = []
    for item in workers:
        worker_id = str(item.get("id") or "")
        if worker_id == "windows" or item.get("status") != "online":
            continue
        if capability not in (item.get("capabilities") or []):
            continue
        if _cooling(item, now):
            continue
        metrics = _metrics(item.get("worker_metrics"))
        active = int(metrics["active_requests"])
        capacity = int(metrics["capacity"])
        virtual = assignments.get(worker_id, 0)
        if active + virtual >= capacity:
            continue
        health = item.get("dispatch_health") or {}
        failures = max(0, int(health.get("consecutive_failures") or 0))
        score = (
            float(metrics["normalized_load"])
            + (active + virtual) / capacity
            + min(failures, 3) * 0.35
        )
        candidates.append((score, worker_id))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: (pair[0], pair[1]))
    chosen = candidates[0][1]
    assignments[chosen] = assignments.get(chosen, 0) + 1
    return chosen


def _movement_worker(
    kind: str, workers: list[dict[str, Any]],
    assignments: dict[str, int], now: datetime,
) -> str:
    if kind != "opensky_region":
        return "windows"
    return (
        _select_remote(
            "opensky_region_read_only", workers, assignments, now
        )
        or "windows"
    )


def _camera_worker(
    kind: str, workers: list[dict[str, Any]],
    assignments: dict[str, int], now: datetime,
) -> str:
    # Windy may require a provider credential, which stays on Windows.
    if kind not in ("caltrans", "public_https", "public_http"):
        return "windows"
    return (
        _select_remote(
            "camera_source_analysis_read_only", workers, assignments, now
        )
        or "windows"
    )


def _mark_in_memory(
    workers: list[dict[str, Any]], worker_id: str,
    *, success: bool, now: datetime,
) -> None:
    if worker_id == "windows":
        return
    for worker in workers:
        if worker.get("id") != worker_id:
            continue
        health = dict(worker.get("dispatch_health") or {})
        if success:
            health["consecutive_failures"] = 0
            health["cooldown_until"] = None
        else:
            count = max(0, int(health.get("consecutive_failures") or 0)) + 1
            delay = min(
                _COOLDOWN_MAX_SECONDS,
                _COOLDOWN_BASE_SECONDS * (2 ** min(count - 1, 5)),
            )
            health["consecutive_failures"] = count
            health["cooldown_until"] = (
                now + timedelta(seconds=delay)
            ).isoformat()
        worker["dispatch_health"] = health
        return


def run_due(*, db_path: Path | None = None, limit: int = 8,
            now: datetime | None = None) -> dict[str, Any]:
    """One capability/load-aware movement dispatch pass."""
    _require_enabled()
    if type(limit) is not int or limit < 1:
        raise ValueError("Distributed dispatch batch size must be positive.")
    path = _dbpath(db_path)
    if not path.exists():
        return {
            "checks": [], "due_remaining": 0,
            "workers": available_workers(db_path=path)["workers"],
        }
    instant = _instant(now)
    with closing(_connect(path, create=True)) as con, con:
        _orchestration_schema(con)
        rows = con.execute(
            "SELECT id,kind FROM movement_sources "
            "WHERE state='active' AND authorized_automated_access=1 "
            "AND cadence_seconds>0 AND next_due_at<=? "
            "AND (lease_until IS NULL OR lease_until<=?) "
            "ORDER BY next_due_at,id LIMIT ?",
            (instant.isoformat(), instant.isoformat(), limit),
        ).fetchall()
    fabric = available_workers(db_path=path)
    workers = fabric["workers"]
    assignments: dict[str, int] = {}
    outcomes = []
    for row in rows:
        worker = _movement_worker(
            row["kind"], workers, assignments, instant
        )
        try:
            result = collect_source(
                row["id"], db_path=path, scheduled=True,
                worker_id=worker, now=now,
            )
            outcomes.append(result)
            success = result.get("status") not in {
                "unavailable", "not_collected"
            }
            _record_worker_result(
                path, worker, success=success, now=instant
            )
            _mark_in_memory(
                workers, worker, success=success, now=instant
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            _record_worker_result(
                path, worker, success=False, now=instant
            )
            _mark_in_memory(
                workers, worker, success=False, now=instant
            )
            outcomes.append({
                "source_id": row["id"], "status": "not_collected",
                "worker_id": worker, "error_type": type(exc).__name__,
                "fallback_attempted": False,
            })
    with closing(_connect(path, create=True)) as con:
        remaining = con.execute(
            "SELECT count(*) FROM movement_sources "
            "WHERE state='active' AND authorized_automated_access=1 "
            "AND cadence_seconds>0 AND next_due_at<=? "
            "AND (lease_until IS NULL OR lease_until<=?)",
            (instant.isoformat(), instant.isoformat()),
        ).fetchone()[0]
    return {
        "checks": outcomes,
        "due_remaining": remaining,
        "workers": workers,
        "scheduler": "capability_load_health_aware",
        "controller_authority": (
            "source grants, leases, cadence, normalization and persistence"
        ),
        "remote_action_authority": False,
    }


def run_camera_due(*, db_path: Path | None = None, limit: int = 4,
                   now: datetime | None = None) -> dict[str, Any]:
    """One capability/load-aware camera pass over enrolled source grants."""
    from jarvis_mrb import world_armor_observe as camera_runner
    from jarvis_mrb import world_armor_platform as platform

    platform._require_enabled()
    if type(limit) is not int or limit < 1:
        raise ValueError("Distributed camera batch size must be positive.")
    path = platform._dbpath(db_path)
    if not path.exists():
        return {
            "checks": [], "due_remaining": 0,
            "workers": available_workers(db_path=path)["workers"],
        }
    instant = platform._instant(now)
    with closing(platform._connect(path, create=True)) as con, con:
        _orchestration_schema(con)
        rows = con.execute(
            "SELECT id,kind FROM source_grants WHERE state='active' "
            "AND cadence_seconds>0 AND authorized_automated_access=1 "
            "AND next_due_at<=? "
            "AND (lease_until IS NULL OR lease_until<=?) "
            "AND (consent_expires_at IS NULL OR consent_expires_at>?) "
            "AND (sample_budget IS NULL OR check_count<sample_budget) "
            "ORDER BY next_due_at,id LIMIT ?",
            (instant.isoformat(), instant.isoformat(),
             instant.isoformat(), limit),
        ).fetchall()
    fabric = available_workers(db_path=path)
    workers = fabric["workers"]
    assignments: dict[str, int] = {}
    outcomes = []
    for row in rows:
        worker = _camera_worker(
            row["kind"], workers, assignments, instant
        )
        try:
            result = camera_runner.observe_source(
                row["id"], db_path=path, scheduled=True,
                worker_id=worker, now=now,
            )
            outcomes.append(result)
            success = result.get("status") == "ok"
            _record_worker_result(
                path, worker, success=success, now=instant
            )
            _mark_in_memory(
                workers, worker, success=success, now=instant
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            _record_worker_result(
                path, worker, success=False, now=instant
            )
            _mark_in_memory(
                workers, worker, success=False, now=instant
            )
            outcomes.append({
                "source_id": row["id"], "status": "not_collected",
                "worker_id": worker, "error_type": type(exc).__name__,
                "fallback_attempted": False,
            })
    with closing(platform._connect(path, create=True)) as con:
        remaining = con.execute(
            "SELECT count(*) FROM source_grants WHERE state='active' "
            "AND cadence_seconds>0 AND authorized_automated_access=1 "
            "AND next_due_at<=? "
            "AND (lease_until IS NULL OR lease_until<=?) "
            "AND (consent_expires_at IS NULL OR consent_expires_at>?) "
            "AND (sample_budget IS NULL OR check_count<sample_budget)",
            (instant.isoformat(), instant.isoformat(), instant.isoformat()),
        ).fetchone()[0]
    return {
        "checks": outcomes,
        "due_remaining": remaining,
        "workers": workers,
        "scheduler": "capability_load_health_aware",
        "controller_authority": (
            "source grants, terms, leases, cadence, revocation and persistence"
        ),
        "raw_camera_frames_persisted": False,
        "remote_action_authority": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit World Armor distributed public-world dispatcher"
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--include-cameras", action="store_true",
                        help="Also dispatch due enrolled public-camera sources")
    parser.add_argument("--camera-limit", type=int, default=4)
    parser.add_argument("--interval-seconds", type=int, default=10)
    args = parser.parse_args()
    if (args.limit < 1 or args.camera_limit < 1
            or args.interval_seconds < 1):
        parser.error("Positive runner settings required.")
    _require_enabled()
    while True:
        result: dict[str, Any] = {
            "movement": run_due(limit=args.limit),
        }
        if args.include_cameras:
            result["cameras"] = run_camera_due(limit=args.camera_limit)
        print(result, flush=True)
        if args.once:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
