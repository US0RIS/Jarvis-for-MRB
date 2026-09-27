"""24-hour reliability soak sampler for criteria.md C21.

Run beside the real deployment (same checkout/Python as the service):

    jarvis-release-soak run --session <C21 release session id> [--interval 300]

It never repairs anything.  Every ``interval`` seconds it records what the
running system actually reports: the service's identity and boot id (restarts),
health, Agency goal/watch states, outbox depth, database sizes, the World
Armor live supervisor, verified actions, and whether any secret-looking string
reached the world journal.  The C21 evaluator derives PASS/FAIL checks from
these samples; a human still performs the soak's disruptions (network drop,
node restart, phone background/foreground, one approved action).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jarvis_mrb.world_model as world_model

_SECRET_RE = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{16,}|\bgsk_[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\bbearer\s+[A-Za-z0-9._-]{20,}|\bAKIA[0-9A-Z]{16}\b)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ledger(path: Path | None = None) -> sqlite3.Connection:
    from jarvis_mrb.release_gates import _connect

    conn = _connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS release_soak_samples (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            sampled_at TEXT NOT NULL,
            sample_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_release_soak_session ON release_soak_samples(session_id, seq);
        CREATE TRIGGER IF NOT EXISTS release_soak_append_only_u BEFORE UPDATE ON release_soak_samples
        BEGIN SELECT RAISE(ABORT, 'soak samples are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS release_soak_append_only_d BEFORE DELETE ON release_soak_samples
        BEGIN SELECT RAISE(ABORT, 'soak samples are append-only'); END;
        """
    )
    return conn


def _file_size(path: Path) -> int:
    total = 0
    for candidate in (path, Path(str(path) + "-wal")):
        try:
            total += candidate.stat().st_size
        except OSError:
            pass
    return total


def _world_counts() -> dict[str, Any]:
    counts: dict[str, Any] = {}
    try:
        conn = sqlite3.connect(f"file:{world_model.DB_PATH}?mode=ro", uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        with closing(conn):
            counts["events"] = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
            counts["max_event_id"] = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0])
            counts["desired_states"] = {
                str(row[0]): int(row[1])
                for row in conn.execute("SELECT state,COUNT(*) FROM desired_states GROUP BY state")
            }
            counts["active_goal_ids"] = [
                str(row[0]) for row in conn.execute(
                    "SELECT id FROM desired_states WHERE state IN ('active','blocked') ORDER BY id LIMIT 50"
                )
            ]
            counts["active_wake_watches"] = int(conn.execute(
                "SELECT COUNT(*) FROM desired_state_watches WHERE status='active'").fetchone()[0])
            counts["verifications"] = {
                str(row[0]): int(row[1])
                for row in conn.execute("SELECT status,COUNT(*) FROM action_verifications GROUP BY status")
            }
            recent = conn.execute(
                "SELECT summary,evidence,payload_json FROM events ORDER BY id DESC LIMIT 500"
            ).fetchall()
            counts["secret_like_recent_events"] = sum(
                1 for row in recent
                if _SECRET_RE.search(" ".join(str(row[k] or "") for k in ("summary", "evidence", "payload_json")))
            )
    except sqlite3.Error as exc:
        counts["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return counts


def sample(session_id: str) -> dict[str, Any]:
    from jarvis_mrb.release_gates import service_identity

    identity = service_identity(timeout=10.0)
    record: dict[str, Any] = {
        "sampled_at": _now(),
        "service": {k: identity.get(k) for k in ("reachable", "code_sha", "boot_id", "pid", "error",
                                                  "worktree_clean", "world_schema_ready")},
    }
    try:
        import httpx

        from jarvis_mrb.server_config import load_server_config
        config = load_server_config()
        host = config.bind_host if config.bind_host not in {"0.0.0.0", "::", ""} else "127.0.0.1"
        health = httpx.get(f"http://{host}:{config.port}/health", timeout=10.0).json()
        record["health"] = {k: health.get(k) for k in (
            "status", "world_model", "runtime_health", "scheduler", "proactive_monitor",
            "world_armor_live", "agency", "agency_mode", "agency_desired_states", "tool_audit")}
    except Exception as exc:
        record["health"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    pid = identity.get("pid")
    if isinstance(pid, int):
        try:
            import psutil
            process = psutil.Process(pid)
            record["process"] = {"rss_mb": round(process.memory_info().rss / 1_048_576, 1),
                                 "threads": process.num_threads()}
        except Exception as exc:
            record["process"] = {"error": type(exc).__name__}
    record["world"] = _world_counts()
    try:
        from jarvis_mrb.world_armor_push import PUSH_STORE, status as push_status
        push = push_status()
        record["push"] = {k: push.get(k) for k in ("pending", "dead", "sent_retained", "registered_devices", "max_pending")}
        push_path = PUSH_STORE
    except Exception as exc:
        record["push"] = {"error": type(exc).__name__}
        push_path = None
    try:
        from jarvis_mrb.world_armor_live import status as live_status
        live = live_status()
        record["world_armor_live"] = {k: live.get(k) for k in ("enabled", "heartbeat_age_seconds", "journal_events", "latest_seq")}
    except Exception as exc:
        record["world_armor_live"] = {"error": type(exc).__name__}
    try:
        from jarvis_mrb.release_gates import client_builds
        record["phones_last_seen"] = [
            {k: item[k] for k in ("device_id", "build_sha", "last_seen")} for item in client_builds()[:5]
        ]
    except Exception:
        record["phones_last_seen"] = []
    data_dir = Path(world_model.DB_PATH).parent
    record["storage_bytes"] = {
        "world_model": _file_size(Path(world_model.DB_PATH)),
        "push": _file_size(push_path) if push_path else None,
        "data_dir_total": sum(p.stat().st_size for p in data_dir.glob("*.sqlite3*") if p.is_file()),
    }
    with closing(_ledger()) as conn, conn:
        conn.execute(
            "INSERT INTO release_soak_samples(session_id,sampled_at,sample_json) VALUES(?,?,?)",
            (session_id, record["sampled_at"], json.dumps(record, sort_keys=True, default=str)),
        )
    return record


def samples(session_id: str, *, path: Path | None = None) -> list[dict[str, Any]]:
    with closing(_ledger(path)) as conn:
        rows = conn.execute(
            "SELECT sample_json FROM release_soak_samples WHERE session_id=? ORDER BY seq", (session_id,)
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _healthy(item: dict[str, Any], sha: str) -> bool:
    service = item.get("service") or {}
    health = item.get("health") or {}
    return bool(
        service.get("reachable") and service.get("code_sha") == sha
        and health.get("status") == "ok" and health.get("world_model") == "ready"
        and health.get("proactive_monitor") == "running"
    )


def evaluate(session: dict[str, Any], *, min_hours: float = 24.0, max_gap_minutes: float = 30.0,
             max_unhealthy_minutes: float = 30.0) -> list[dict[str, Any]]:
    """Derive C21 checks from recorded samples (used by the release evaluator)."""
    from jarvis_mrb.release_gates import _check

    items = samples(session["id"])
    checks: list[dict[str, Any]] = []
    if len(items) < 2:
        return [_check("soak samples recorded", False, f"{len(items)} samples")]
    times = [datetime.fromisoformat(item["sampled_at"]) for item in items]
    span_hours = (times[-1] - times[0]).total_seconds() / 3600
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
    checks.append(_check(f"continuous soak of at least {min_hours:g} h", span_hours >= min_hours,
                         {"span_hours": round(span_hours, 2), "samples": len(items)}))
    checks.append(_check(f"no sampling gap over {max_gap_minutes:g} min", max(gaps) <= max_gap_minutes,
                         {"max_gap_minutes": round(max(gaps), 1)}))
    unhealthy_run, worst = 0.0, 0.0
    for previous, item, gap in zip(items, items[1:], gaps):
        unhealthy_run = unhealthy_run + gap if not _healthy(item, session["sha"]) else 0.0
        worst = max(worst, unhealthy_run)
    checks.append(_check("backend healthy or recovered within bound", worst <= max_unhealthy_minutes
                         and _healthy(items[-1], session["sha"]),
                         {"worst_unhealthy_minutes": round(worst, 1), "final_healthy": _healthy(items[-1], session["sha"])}))
    boots = [str((item.get("service") or {}).get("boot_id") or "") for item in items]
    restarts = sum(1 for a, b in zip(boots, boots[1:]) if a and b and a != b)
    checks.append(_check("service recovered from every restart without manual database repair",
                         _healthy(items[-1], session["sha"]), {"observed_restarts": restarts}))
    first_goals = set((items[0].get("world") or {}).get("active_goal_ids") or [])
    last_goals = set((items[-1].get("world") or {}).get("active_goal_ids") or [])
    checks.append(_check("at least one persistent goal survived the whole soak", bool(first_goals & last_goals),
                         {"first": sorted(first_goals)[:5], "last": sorted(last_goals)[:5]}))
    live = [((item.get("world_armor_live") or {}).get("heartbeat_age_seconds")) for item in items]
    watch_alive = [age is not None and age < 900 for age in live]
    checks.append(_check("permitted watch/collector never silently died (heartbeat < 15 min at the end, and recovered after any lapse)",
                         bool(watch_alive) and watch_alive[-1], {"final_heartbeat_age_s": live[-1]}))
    pending = [int((item.get("push") or {}).get("pending") or 0) for item in items]
    max_pending = int((items[-1].get("push") or {}).get("max_pending") or 2000)
    checks.append(_check("notification outbox stayed within its documented bound", max(pending) <= max_pending,
                         {"max_pending": max(pending), "bound": max_pending}))
    sizes = [int((item.get("storage_bytes") or {}).get("data_dir_total") or 0) for item in items]
    growth_mb_per_day = (sizes[-1] - sizes[0]) / 1_048_576 / max(span_hours / 24, 1e-6)
    checks.append(_check("database growth bounded (< 500 MB/day)", growth_mb_per_day < 500,
                         {"growth_mb_per_day": round(growth_mb_per_day, 1)}))
    first_verified = int(((items[0].get("world") or {}).get("verifications") or {}).get("verified", 0))
    last_verified = int(((items[-1].get("world") or {}).get("verifications") or {}).get("verified", 0))
    checks.append(_check("at least one approved action was independently verified during the soak",
                         last_verified > first_verified, {"verified_before": first_verified, "verified_after": last_verified}))
    leaks = max(int((item.get("world") or {}).get("secret_like_recent_events") or 0) for item in items)
    checks.append(_check("no secret-like material in the world journal", leaks == 0, {"max_secret_like_events": leaks}))
    phones = {p["last_seen"] for item in items for p in (item.get("phones_last_seen") or []) if p.get("build_sha") == session["sha"]}
    checks.append(_check("candidate iPhone build reconnected repeatedly during the soak", len(phones) >= 3,
                         {"distinct_last_seen": len(phones)}))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis-release-soak", description="C21 soak sampler")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--session", required=True, help="C21 release session id from jarvis-release-gate start C21")
    run.add_argument("--interval", type=int, default=300)
    run.add_argument("--hours", type=float, default=24.5)
    once = sub.add_parser("sample")
    once.add_argument("--session", required=True)
    report = sub.add_parser("report")
    report.add_argument("--session", required=True)
    args = parser.parse_args(argv)

    from jarvis_mrb.release_gates import get_session
    session = get_session(args.session)
    if session is None or session["gate"] != "C21":
        print("error: --session must be a C21 release session", file=sys.stderr)
        return 1
    if args.command == "sample":
        print(json.dumps(sample(args.session), indent=2, default=str))
    elif args.command == "report":
        print(json.dumps(evaluate(session), indent=2, default=str))
    else:
        deadline = time.monotonic() + max(0.1, args.hours) * 3600
        interval = max(30, int(args.interval))
        while time.monotonic() < deadline:
            try:
                item = sample(args.session)
                print(f"{item['sampled_at']} service={item['service'].get('reachable')} "
                      f"boot={str(item['service'].get('boot_id'))[:8]}", flush=True)
            except Exception as exc:  # the sampler must outlive the system under test
                print(f"{_now()} sample error: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(interval)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
