from __future__ import annotations

"""Distributed read-only World Armor observers over trusted private Mesh nodes.

Windows remains authoritative for source grants, cadence, leases, retention,
normalization and final evidence writes. Paired Macs may perform only typed
capabilities explicitly advertised at startup. Camera tasks are restricted to
already-enrolled Caltrans or explicit public-media sources and still pass
through the existing public-host/DNS/media validation on the worker.

No network discovery, private-network fetch, arbitrary RPC, remote shell,
credential delegation, person tracking or action authority is added.
"""

import argparse
from contextlib import closing
from datetime import datetime
from pathlib import Path
import time
from typing import Any

from jarvis_mrb.world_armor_movement import (
    _connect, _dbpath, _instant, _require_enabled, collect_source,
)


def _remote_capabilities(capabilities: dict[str, Any]) -> list[str]:
    advertised = capabilities.get("world_observer_capabilities")
    if isinstance(advertised, list):
        return [str(x) for x in advertised if isinstance(x, str)]
    if capabilities.get("world_observer") == "opensky_region_read_only":
        return ["opensky_region_read_only"]
    return []


def available_workers() -> dict[str, Any]:
    from jarvis_mrb import reality_mesh
    fabric = reality_mesh.nodes()
    workers = [{
        "id": "windows", "status": "online",
        "capabilities": [
            "local_all_movement_adapters",
            "local_all_camera_adapters",
        ],
    }]
    for node in fabric.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        capabilities = node.get("capabilities")
        if (node_id not in ("macbook", "macmini")
                or node.get("status") != "online"
                or not isinstance(capabilities, dict)):
            continue
        advertised = _remote_capabilities(capabilities)
        if not advertised:
            continue
        workers.append({
            "id": node_id, "status": "online",
            "capabilities": advertised,
            "observed_at": node.get("observed_at"),
        })
    return {
        "workers": workers,
        "network_discovery": False,
        "controller": "windows",
        "credential_delegation": False,
        "remote_arbitrary_rpc": False,
        "private_network_camera_fetch": False,
    }


def _choose_worker(kind: str, workers: list[dict[str, Any]],
                   index: int) -> tuple[str, int]:
    # Provider-global OpenSky and AIS stay on the controller. Regional
    # OpenSky can use an explicitly opted-in paired Mac.
    if kind != "opensky_region":
        return "windows", index
    remote = [
        item["id"] for item in workers
        if item.get("id") in ("macbook", "macmini")
        and "opensky_region_read_only" in (item.get("capabilities") or [])
    ]
    if not remote:
        return "windows", index
    node = remote[index % len(remote)]
    return node, index + 1


def _choose_camera_worker(kind: str, workers: list[dict[str, Any]],
                          index: int) -> tuple[str, int]:
    # Windy can require a provider credential; do not delegate credentials.
    # Caltrans and explicit public HTTP(S) media may be fetched/processed on
    # an opted-in Mac using the same public-network guard as Windows.
    if kind not in ("caltrans", "public_https", "public_http"):
        return "windows", index
    remote = [
        item["id"] for item in workers
        if item.get("id") in ("macbook", "macmini")
        and "camera_source_analysis_read_only"
        in (item.get("capabilities") or [])
    ]
    if not remote:
        return "windows", index
    node = remote[index % len(remote)]
    return node, index + 1


def run_due(*, db_path: Path | None = None, limit: int = 8,
            now: datetime | None = None) -> dict[str, Any]:
    """One bounded movement dispatch pass; source count itself is not capped."""
    _require_enabled()
    if type(limit) is not int or limit < 1:
        raise ValueError("Distributed dispatch batch size must be positive.")
    path = _dbpath(db_path)
    if not path.exists():
        return {
            "checks": [], "due_remaining": 0,
            "workers": available_workers()["workers"],
        }
    instant = _instant(now)
    with closing(_connect(path, create=True)) as con:
        rows = con.execute(
            "SELECT id,kind FROM movement_sources "
            "WHERE state='active' AND authorized_automated_access=1 "
            "AND cadence_seconds>0 AND next_due_at<=? "
            "AND (lease_until IS NULL OR lease_until<=?) "
            "ORDER BY next_due_at,id LIMIT ?",
            (instant.isoformat(), instant.isoformat(), limit),
        ).fetchall()
    fabric = available_workers()
    workers = fabric["workers"]
    cursor = 0
    outcomes = []
    for row in rows:
        worker, cursor = _choose_worker(row["kind"], workers, cursor)
        try:
            outcomes.append(collect_source(
                row["id"], db_path=path, scheduled=True,
                worker_id=worker, now=now,
            ))
        except (ValueError, KeyError, RuntimeError) as exc:
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
        "controller_authority": (
            "source grants, leases, cadence, normalization and persistence"
        ),
        "remote_action_authority": False,
    }


def run_camera_due(*, db_path: Path | None = None, limit: int = 4,
                   now: datetime | None = None) -> dict[str, Any]:
    """One bounded camera pass using enrolled rights-scoped source grants."""
    from jarvis_mrb import world_armor_observe as camera_runner
    from jarvis_mrb import world_armor_platform as platform

    platform._require_enabled()
    if type(limit) is not int or limit < 1:
        raise ValueError("Distributed camera batch size must be positive.")
    path = platform._dbpath(db_path)
    if not path.exists():
        return {
            "checks": [], "due_remaining": 0,
            "workers": available_workers()["workers"],
        }
    instant = platform._instant(now)
    with closing(platform._connect(path, create=True)) as con:
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
    fabric = available_workers()
    workers = fabric["workers"]
    cursor = 0
    outcomes = []
    for row in rows:
        worker, cursor = _choose_camera_worker(
            row["kind"], workers, cursor
        )
        try:
            outcomes.append(camera_runner.observe_source(
                row["id"], db_path=path, scheduled=True,
                worker_id=worker, now=now,
            ))
        except (ValueError, KeyError, RuntimeError) as exc:
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
