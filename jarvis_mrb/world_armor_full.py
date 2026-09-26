from __future__ import annotations

"""World Armor v8 full-scope interfaces.

This module closes the software-side Phase 5 loop without widening source or
action authority.  Reality Browser, Synthetic Senses and Causal Debugger are
read-only views over retained evidence.  Parallel Existence runs bounded,
typed analyses concurrently.  Presence can dispatch only to an exact,
short-lived actuator grant and currently exposes one concrete actuator class:
a user-selected HomeKit light executed by the iPhone's existing local HomeKit
controller with fresh accessory readback.

Nothing here discovers private sources, tracks named people, invents provider
rights, sends arbitrary RPC, or converts a model/event into physical authority.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable
from uuid import UUID, uuid4

from jarvis_mrb import world_model

FULL_STORE = Path(world_model.DB_PATH).with_name("world_armor_full.sqlite3")
_MAX_BROWSER_EVENTS = 500
_MAX_PARALLEL_TASKS = 6
_ALLOWED_ACTUATORS = {"homekit_light"}
_ALLOWED_PRESENCE_STATUSES = {
    "verified_reported_state", "unverified", "blocked", "failed",
}


def _now(value: datetime | None = None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("World Armor timestamps must be offset-aware.")
    return instant.astimezone(timezone.utc)


def enabled() -> bool:
    return (
        os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1"
        and os.getenv("JARVIS_WORLD_ARMOR_FULL_ENABLED") == "1"
    )


def _require_enabled() -> None:
    if not enabled():
        raise RuntimeError(
            "World Armor full-scope layer is off; set "
            "JARVIS_WORLD_ARMOR_FULL_ENABLED=1 after enabling World Armor."
        )


def _connect(path: Path = FULL_STORE) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA secure_delete=ON")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS presence_grants (
          id TEXT PRIMARY KEY,
          actuator_kind TEXT NOT NULL,
          target_id TEXT NOT NULL,
          target_label TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'active',
          max_uses INTEGER NOT NULL DEFAULT 1,
          use_count INTEGER NOT NULL DEFAULT 0,
          CHECK(actuator_kind IN ('homekit_light')),
          CHECK(state IN ('active','revoked','expired')),
          CHECK(max_uses>=1 AND use_count>=0)
        );
        CREATE INDEX IF NOT EXISTS ix_presence_grants_state
          ON presence_grants(state,expires_at);

        CREATE TABLE IF NOT EXISTS presence_receipts (
          id TEXT PRIMARY KEY,
          grant_id TEXT NOT NULL REFERENCES presence_grants(id) ON DELETE CASCADE,
          requested_at TEXT NOT NULL,
          completed_at TEXT,
          requested_state INTEGER NOT NULL,
          status TEXT NOT NULL,
          verification_basis TEXT NOT NULL,
          message TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_presence_receipts_grant
          ON presence_receipts(grant_id,requested_at);

        CREATE TABLE IF NOT EXISTS parallel_runs (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          completed_at TEXT NOT NULL,
          task_count INTEGER NOT NULL,
          ok_count INTEGER NOT NULL,
          degraded_count INTEGER NOT NULL,
          summary_json TEXT NOT NULL
        );
        """
    )
    con.commit()
    return con


def _parse_iso(value: str | None, *, label: str) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp.") from exc
    return _now(parsed)


def _event_in_window(
    item: dict[str, Any],
    start: datetime | None,
    end: datetime | None,
) -> bool:
    try:
        stamp = _parse_iso(str(item.get("created_at") or ""), label="event time")
    except ValueError:
        return False
    if stamp is None:
        return False
    return (start is None or stamp >= start) and (end is None or stamp <= end)


def full_status(*, db_path: Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else FULL_STORE
    live: dict[str, Any]
    try:
        from jarvis_mrb.world_armor_live import status as live_status
        live = live_status()
    except Exception as exc:
        live = {
            "running": False,
            "last_error": type(exc).__name__,
            "heartbeat_age_seconds": None,
        }
    try:
        from jarvis_mrb.world_armor_distributed import available_workers
        workers = available_workers().get("workers") or []
    except Exception:
        workers = []
    grants = 0
    pending = 0
    if path.exists():
        with closing(_connect(path)) as con:
            grants = int(con.execute(
                "SELECT count(*) FROM presence_grants WHERE state='active'"
            ).fetchone()[0])
            pending = int(con.execute(
                "SELECT count(*) FROM presence_receipts "
                "WHERE status='dispatched_unverified'"
            ).fetchone()[0])
    return {
        "schema": "jarvis.world_armor.full_scope.v1",
        "enabled": enabled(),
        "layers": {
            "reality_browser": "implemented_read_only",
            "synthetic_senses": "implemented_derived_only",
            "causal_debugger": "implemented_noncausal_mechanism_testing",
            "parallel_existence": "implemented_bounded_parallel_analysis",
            "presence": "implemented_exact_grant_homekit_bridge",
        },
        "live_fabric": live,
        "registered_workers": len(workers),
        "active_presence_grants": grants,
        "pending_presence_receipts": pending,
        "source_authority_expansion": False,
        "arbitrary_rpc": False,
        "person_tracking": False,
        "physical_effect_claim_without_readback": False,
        "qualifier": (
            "Software interfaces are present. Live-source entitlement, APNs "
            "credentials, installed-device operation and physical effects still "
            "require environment-specific acceptance."
        ),
    }


def reality_browser(
    *,
    after_seq: int = 0,
    limit: int = 200,
    start_at: str | None = None,
    end_at: str | None = None,
    investigation_id: str | None = None,
    as_known_at: str | None = None,
) -> dict[str, Any]:
    """Return a navigable, provenance-preserving timeline.

    The browser never interpolates missing frames or converts gaps into
    negative evidence.  Investigation evidence is included only when a bounded
    interval is explicitly provided.
    """
    _require_enabled()
    if type(after_seq) is not int or after_seq < 0:
        raise ValueError("after_seq must be a non-negative integer.")
    if type(limit) is not int or not 1 <= limit <= _MAX_BROWSER_EVENTS:
        raise ValueError(f"limit must be 1-{_MAX_BROWSER_EVENTS}.")
    start = _parse_iso(start_at, label="start_at")
    end = _parse_iso(end_at, label="end_at")
    if start and end and start > end:
        raise ValueError("start_at must not be after end_at.")

    from jarvis_mrb.world_armor_live import events as live_events
    page = live_events(after_seq=after_seq, limit=limit)
    raw_events = [
        item for item in (page.get("events") or [])
        if _event_in_window(item, start, end)
    ]

    timeline: list[dict[str, Any]] = []
    for item in raw_events:
        timeline.append({
            "id": f"live:{item['seq']}",
            "time": item.get("created_at"),
            "time_basis": "controller_received_at",
            "kind": item.get("kind"),
            "subsystem": item.get("subsystem"),
            "source_id": item.get("source_id"),
            "status": item.get("status"),
            "priority": item.get("priority"),
            "summary": item.get("summary"),
            "provenance": {
                "live_event_seq": item.get("seq"),
                "payload": item.get("payload") or {},
            },
            "synthetic": False,
        })

    evidence_graph = None
    if investigation_id is not None:
        if start is None or end is None:
            raise ValueError(
                "Investigation browsing requires explicit start_at and end_at."
            )
        from jarvis_mrb.world_armor_hypotheses import build_evidence_graph
        evidence_graph = build_evidence_graph(
            investigation_id,
            start_at=start.isoformat(),
            end_at=end.isoformat(),
            as_known_at=as_known_at,
        )
        for node in evidence_graph.get("nodes") or []:
            timeline.append({
                "id": "evidence:" + str(node.get("id")),
                "time": node.get("observed_at") or node.get("received_at"),
                "time_basis": (
                    "source_observed_at"
                    if node.get("observed_at") else "controller_received_at"
                ),
                "kind": node.get("kind"),
                "subsystem": "investigation_evidence",
                "source_id": node.get("source"),
                "status": node.get("sample_coverage_status") or "unknown",
                "priority": "info",
                "summary": (
                    f"{node.get('source','unknown')} evidence · "
                    f"{node.get('kind','observation')}"
                ),
                "provenance": {
                    "observation_id": node.get("id"),
                    "lineage": node.get("lineage"),
                    "revision": node.get("revision"),
                    "geometry_basis": node.get("geometry_basis"),
                    "values": node.get("values") or {},
                },
                "synthetic": False,
            })

    timeline.sort(key=lambda row: (str(row.get("time") or ""), row["id"]))
    graph_coverage = (
        evidence_graph.get("source_coverage") if evidence_graph else None
    )
    return {
        "schema": "jarvis.world_armor.reality_browser.v1",
        "timeline": timeline,
        "next_seq": page.get("next_seq", after_seq),
        "latest_seq": page.get("latest_seq", 0),
        "replay_gap": bool(page.get("replay_gap")),
        "source_coverage": graph_coverage,
        "hypotheses": (evidence_graph or {}).get("hypotheses") or [],
        "missing_time_is_unknown": True,
        "interpolation_performed": False,
        "model_calls": 0,
        "external_actions": 0,
    }


def synthetic_senses(
    *,
    after_seq: int = 0,
    limit: int = 300,
    start_at: str | None = None,
    end_at: str | None = None,
) -> dict[str, Any]:
    """Derive explicitly synthetic operational signals from retained live events."""
    _require_enabled()
    browser = reality_browser(
        after_seq=after_seq, limit=limit,
        start_at=start_at, end_at=end_at,
    )
    rows = [
        item for item in browser["timeline"]
        if item.get("id", "").startswith("live:")
    ]
    basis = [
        int(item["provenance"]["live_event_seq"])
        for item in rows
        if item.get("provenance", {}).get("live_event_seq") is not None
    ]
    warning_count = sum(
        1 for item in rows if item.get("priority") in {"warning", "urgent"}
    )
    movement_positions = 0
    camera_changes = 0
    attention = 0
    source_ids: set[str] = set()
    for item in rows:
        if item.get("source_id"):
            source_ids.add(str(item["source_id"]))
        payload = item.get("provenance", {}).get("payload") or {}
        if item.get("subsystem") == "movement":
            try:
                movement_positions += max(
                    0, int(payload.get("observations_saved") or 0)
                )
            except (TypeError, ValueError):
                pass
        if item.get("subsystem") == "camera" and (
            payload.get("observation_saved")
            or payload.get("evidence_saved")
            or payload.get("evidence_inserted")
        ):
            camera_changes += 1
        if item.get("kind") == "attention_notice":
            attention += 1

    total = len(rows)
    health = 1.0 if total == 0 else max(0.0, 1.0 - warning_count / total)
    signals = [
        {
            "id": "synthetic:fabric_health_ratio",
            "label": "Fabric health ratio",
            "value": round(health, 4),
            "unit": "ratio",
            "basis_event_seqs": basis[-100:],
            "derived": True,
            "world_fact": False,
            "interpretation": (
                "Fraction of retained live receipts not marked warning/urgent; "
                "not a measure of world safety or source completeness."
            ),
        },
        {
            "id": "synthetic:movement_positions",
            "label": "New movement positions",
            "value": movement_positions,
            "unit": "retained_positions",
            "basis_event_seqs": basis[-100:],
            "derived": True,
            "world_fact": False,
            "interpretation": (
                "Count reported by retained movement collector receipts in the "
                "selected window; unknown coverage remains unknown."
            ),
        },
        {
            "id": "synthetic:camera_changes",
            "label": "Camera evidence changes",
            "value": camera_changes,
            "unit": "derived_evidence_events",
            "basis_event_seqs": basis[-100:],
            "derived": True,
            "world_fact": False,
            "interpretation": (
                "Number of camera receipts reporting newly retained derived "
                "evidence; not incident confirmation."
            ),
        },
        {
            "id": "synthetic:attention",
            "label": "Attention notices",
            "value": attention,
            "unit": "notices",
            "basis_event_seqs": basis[-100:],
            "derived": True,
            "world_fact": False,
            "interpretation": (
                "Typed World Armor notice count, subject to watch and cooldown rules."
            ),
        },
        {
            "id": "synthetic:source_diversity",
            "label": "Observed source diversity",
            "value": len(source_ids),
            "unit": "source_ids",
            "basis_event_seqs": basis[-100:],
            "derived": True,
            "world_fact": False,
            "interpretation": (
                "Distinct source IDs represented in retained live receipts; "
                "does not imply independent lineage."
            ),
        },
    ]
    return {
        "schema": "jarvis.world_armor.synthetic_senses.v1",
        "signals": signals,
        "event_count": total,
        "replay_gap": browser["replay_gap"],
        "derived_only": True,
        "raw_sensor_claims": 0,
        "external_actions": 0,
    }


def causal_debugger(
    investigation_id: str,
    *,
    start_at: str,
    end_at: str,
    hypothesis_id: str | None = None,
    as_known_at: str | None = None,
) -> dict[str, Any]:
    """Inspect whether retained evidence supports a mechanism test.

    This debugger never upgrades temporal association to causality.  It reports
    what would need to be observed to distinguish mechanisms and alternatives.
    """
    _require_enabled()
    from jarvis_mrb.world_armor_hypotheses import build_evidence_graph
    graph = build_evidence_graph(
        investigation_id,
        start_at=start_at,
        end_at=end_at,
        as_known_at=as_known_at,
    )
    hypotheses = graph.get("hypotheses") or []
    if hypothesis_id is not None:
        hypotheses = [
            item for item in hypotheses if item.get("id") == hypothesis_id
        ]
        if not hypotheses:
            raise KeyError("Hypothesis is not present in this bounded evidence graph.")

    reports = []
    for hyp in hypotheses:
        missing = list(hyp.get("missing_evidence") or [])
        alternatives = list(hyp.get("alternative_explanations") or [])
        reports.append({
            "hypothesis_id": hyp.get("id"),
            "claim_under_test": hyp.get("claim"),
            "status": "mechanism_unverified",
            "supporting_observation_ids": (
                hyp.get("supporting_observation_ids") or []
            ),
            "contradicting_observation_ids": (
                hyp.get("contradicting_observation_ids") or []
            ),
            "independent_lineage_count": (
                hyp.get("independent_lineage_count") or 0
            ),
            "missing_evidence": missing,
            "alternative_explanations": alternatives,
            "observational_tests": [
                {
                    "kind": "seek_independent_mechanism_evidence",
                    "question": (
                        "Is there a separately sourced observation of a "
                        "mechanism/dependency connecting the two phenomena?"
                    ),
                    "action_authority": False,
                },
                {
                    "kind": "seek_repetition_or_third_source",
                    "question": (
                        "Does the relationship recur or appear in a third "
                        "independent source family under adequate coverage?"
                    ),
                    "action_authority": False,
                },
                {
                    "kind": "test_alternatives",
                    "question": (
                        "Which retained observations discriminate the candidate "
                        "mechanism from chance, latency, footprint mismatch, or "
                        "a shared upstream condition?"
                    ),
                    "action_authority": False,
                },
            ],
            "causal_conclusion": False,
            "intervention_performed": False,
        })
    return {
        "schema": "jarvis.world_armor.causal_debugger.v1",
        "investigation_id": investigation_id,
        "query_id": graph.get("query_id"),
        "reports": reports,
        "source_coverage": graph.get("source_coverage") or {},
        "unavailable_or_unchecked_sources": (
            graph.get("unavailable_or_unchecked_sources") or []
        ),
        "causal_claims": 0,
        "external_actions": 0,
        "qualifier": (
            "Mechanism tests organize falsifiable observational checks. "
            "No causal conclusion is emitted without independently validated "
            "mechanism evidence."
        ),
    }


def _safe_task(
    name: str, func: Callable[[], dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    try:
        return name, {"status": "ok", "result": func()}
    except Exception as exc:
        return name, {
            "status": "degraded",
            "error_type": type(exc).__name__,
            "error": str(exc)[:240],
        }


def parallel_existence(
    *,
    after_seq: int = 0,
    start_at: str | None = None,
    end_at: str | None = None,
    investigation_id: str | None = None,
    hypothesis_id: str | None = None,
    as_known_at: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Run independent read-only World Armor analyses concurrently."""
    _require_enabled()
    path = Path(db_path) if db_path is not None else FULL_STORE
    tasks: dict[str, Callable[[], dict[str, Any]]] = {
        "reality_browser": lambda: reality_browser(
            after_seq=after_seq, limit=250,
            start_at=start_at, end_at=end_at,
            investigation_id=investigation_id,
            as_known_at=as_known_at,
        ),
        "synthetic_senses": lambda: synthetic_senses(
            after_seq=after_seq, limit=300,
            start_at=start_at, end_at=end_at,
        ),
        "worker_fabric": lambda: _worker_fabric_snapshot(),
        "live_status": lambda: _live_status_snapshot(),
    }
    if investigation_id is not None:
        if not start_at or not end_at:
            raise ValueError(
                "Parallel investigation analysis requires start_at and end_at."
            )
        tasks["causal_debugger"] = lambda: causal_debugger(
            investigation_id,
            start_at=start_at,
            end_at=end_at,
            hypothesis_id=hypothesis_id,
            as_known_at=as_known_at,
        )
    if len(tasks) > _MAX_PARALLEL_TASKS:
        raise RuntimeError("Parallel task ceiling exceeded.")

    started = _now()
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(
        max_workers=min(4, len(tasks)),
        thread_name_prefix="world-armor-parallel",
    ) as pool:
        futures = {
            pool.submit(_safe_task, name, func): name
            for name, func in tasks.items()
        }
        for future in as_completed(futures):
            name, value = future.result()
            results[name] = value
    finished = _now()
    ok_count = sum(1 for item in results.values() if item["status"] == "ok")
    degraded = len(results) - ok_count
    run_id = uuid4().hex
    summary = {
        key: value["status"] for key, value in sorted(results.items())
    }
    with closing(_connect(path)) as con, con:
        con.execute(
            "INSERT INTO parallel_runs"
            "(id,created_at,completed_at,task_count,ok_count,degraded_count,summary_json)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                run_id, started.isoformat(), finished.isoformat(),
                len(results), ok_count, degraded,
                json.dumps(summary, separators=(",", ":")),
            ),
        )
    return {
        "schema": "jarvis.world_armor.parallel_existence.v1",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": finished.isoformat(),
        "duration_ms": max(
            0, int((finished - started).total_seconds() * 1000)
        ),
        "results": results,
        "parallel_task_count": len(results),
        "ok_count": ok_count,
        "degraded_count": degraded,
        "remote_authority_expansion": False,
        "external_actions": 0,
    }


def _worker_fabric_snapshot() -> dict[str, Any]:
    from jarvis_mrb.world_armor_distributed import available_workers
    value = available_workers()
    return {
        "workers": value.get("workers") or [],
        "selection_policy": value.get("selection_policy"),
        "arbitrary_jobs": False,
    }


def _live_status_snapshot() -> dict[str, Any]:
    from jarvis_mrb.world_armor_live import status
    return status()


def _uuid_text(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Presence target must be an exact UUID.") from exc


def _expire_grants(con: sqlite3.Connection, instant: datetime) -> None:
    con.execute(
        "UPDATE presence_grants SET state='expired' "
        "WHERE state='active' AND expires_at<=?",
        (instant.isoformat(),),
    )


def create_presence_grant(
    *,
    actuator_kind: str,
    target_id: str,
    target_label: str,
    lifetime_seconds: int = 120,
    max_uses: int = 1,
    now: datetime | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Create a short-lived exact actuator grant; this performs no action."""
    _require_enabled()
    if actuator_kind not in _ALLOWED_ACTUATORS:
        raise ValueError("Unsupported Presence actuator.")
    target = _uuid_text(target_id)
    if (
        not isinstance(target_label, str)
        or not 1 <= len(target_label.strip()) <= 200
    ):
        raise ValueError("Presence target label required (1-200 characters).")
    if type(lifetime_seconds) is not int or not 15 <= lifetime_seconds <= 3600:
        raise ValueError("Presence grant lifetime must be 15-3600 seconds.")
    if type(max_uses) is not int or not 1 <= max_uses <= 20:
        raise ValueError("Presence grant use count must be 1-20.")
    instant = _now(now)
    ident = uuid4().hex
    expiry = instant + timedelta(seconds=lifetime_seconds)
    path = Path(db_path) if db_path is not None else FULL_STORE
    with closing(_connect(path)) as con, con:
        _expire_grants(con, instant)
        con.execute(
            "INSERT INTO presence_grants"
            "(id,actuator_kind,target_id,target_label,created_at,expires_at,"
            "state,max_uses,use_count) VALUES(?,?,?,?,?,?,'active',?,0)",
            (
                ident, actuator_kind, target, target_label.strip(),
                instant.isoformat(), expiry.isoformat(), max_uses,
            ),
        )
    return get_presence_grant(ident, db_path=path, now=instant)


def _grant_dict(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["remaining_uses"] = max(
        0, int(value["max_uses"]) - int(value["use_count"])
    )
    value["physical_effect_verified"] = False
    return value


def get_presence_grant(
    grant_id: str,
    *,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(grant_id, str) or not re.fullmatch(r"[0-9a-f]{32}", grant_id):
        raise ValueError("Invalid Presence grant ID.")
    path = Path(db_path) if db_path is not None else FULL_STORE
    instant = _now(now)
    with closing(_connect(path)) as con, con:
        _expire_grants(con, instant)
        row = con.execute(
            "SELECT * FROM presence_grants WHERE id=?", (grant_id,)
        ).fetchone()
    if row is None:
        raise KeyError("Presence grant does not exist.")
    return _grant_dict(row)


def list_presence_grants(
    *,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else FULL_STORE
    instant = _now(now)
    if not path.exists():
        return {"grants": [], "receipts": []}
    with closing(_connect(path)) as con, con:
        _expire_grants(con, instant)
        grants = con.execute(
            "SELECT * FROM presence_grants ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        receipts = con.execute(
            "SELECT * FROM presence_receipts "
            "ORDER BY requested_at DESC LIMIT 100"
        ).fetchall()
    return {
        "grants": [_grant_dict(row) for row in grants],
        "receipts": [dict(row) for row in receipts],
        "arbitrary_targets": False,
    }


def revoke_presence_grant(
    grant_id: str, *, db_path: Path | None = None
) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else FULL_STORE
    with closing(_connect(path)) as con, con:
        result = con.execute(
            "UPDATE presence_grants SET state='revoked' "
            "WHERE id=? AND state='active'",
            (grant_id,),
        )
    return {"grant_id": grant_id, "revoked": result.rowcount == 1}


def dispatch_presence(
    grant_id: str,
    *,
    desired_on: bool,
    now: datetime | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Dispatch one exact HomeKit light request to the authenticated companion.

    A dispatch receipt is deliberately *unverified*.  The iPhone must perform
    its local HomeKit write and fresh accessory readback, then post a separate
    completion receipt.
    """
    _require_enabled()
    if type(desired_on) is not bool:
        raise ValueError("Presence desired_on must be boolean.")
    path = Path(db_path) if db_path is not None else FULL_STORE
    instant = _now(now)
    request_id = uuid4().hex
    with closing(_connect(path)) as con, con:
        con.execute("BEGIN IMMEDIATE")
        _expire_grants(con, instant)
        row = con.execute(
            "SELECT * FROM presence_grants WHERE id=?", (grant_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Presence grant does not exist.")
        if row["state"] != "active":
            raise ValueError("Presence grant is not active.")
        if int(row["use_count"]) >= int(row["max_uses"]):
            raise ValueError("Presence grant use budget exhausted.")
        con.execute(
            "UPDATE presence_grants SET use_count=use_count+1 WHERE id=?",
            (grant_id,),
        )
        con.execute(
            "INSERT INTO presence_receipts"
            "(id,grant_id,requested_at,completed_at,requested_state,status,"
            "verification_basis,message) VALUES(?,?,?,NULL,?,'dispatched_unverified',"
            "'none','Request emitted to authenticated iPhone companion; no physical "
            "effect is yet verified.')",
            (request_id, grant_id, instant.isoformat(), int(desired_on)),
        )

    event = {
        "type": "world_armor_presence_request",
        "request_id": request_id,
        "grant_id": grant_id,
        "actuator_kind": row["actuator_kind"],
        "target_id": row["target_id"],
        "target_label": row["target_label"],
        "action": "set_light",
        "desired_on": desired_on,
        "expires_at": row["expires_at"],
    }
    try:
        from jarvis_mrb.event_bus import companion_events
        companion_events.publish(event)
    except Exception as exc:
        with closing(_connect(path)) as con, con:
            con.execute(
                "UPDATE presence_receipts SET completed_at=?,status='failed',"
                "message=? WHERE id=?",
                (
                    instant.isoformat(),
                    "Companion event delivery failed: " + type(exc).__name__,
                    request_id,
                ),
            )
        raise RuntimeError("Presence companion delivery failed.") from exc
    return {
        "request_id": request_id,
        "grant_id": grant_id,
        "status": "dispatched_unverified",
        "verification_basis": "none",
        "physical_effect_verified": False,
        "requested_state": desired_on,
    }


def record_presence_receipt(
    request_id: str,
    *,
    status: str,
    message: str,
    now: datetime | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise ValueError("Invalid Presence request ID.")
    if status not in _ALLOWED_PRESENCE_STATUSES:
        raise ValueError("Invalid Presence receipt status.")
    if not isinstance(message, str) or len(message) > 800:
        raise ValueError("Presence receipt message is too long.")
    path = Path(db_path) if db_path is not None else FULL_STORE
    instant = _now(now)
    verification = (
        "iphone_homekit_fresh_accessory_readback"
        if status == "verified_reported_state" else "none"
    )
    with closing(_connect(path)) as con, con:
        row = con.execute(
            "SELECT * FROM presence_receipts WHERE id=?", (request_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Presence request does not exist.")
        if row["status"] != "dispatched_unverified":
            return {
                **dict(row),
                "physical_effect_verified": (
                    row["status"] == "verified_reported_state"
                ),
            }
        con.execute(
            "UPDATE presence_receipts SET completed_at=?,status=?,"
            "verification_basis=?,message=? WHERE id=?",
            (
                instant.isoformat(), status, verification,
                message.strip(), request_id,
            ),
        )
        final = con.execute(
            "SELECT * FROM presence_receipts WHERE id=?", (request_id,)
        ).fetchone()
    value = dict(final)
    value["physical_effect_verified"] = (
        value["status"] == "verified_reported_state"
    )
    value["verification_qualifier"] = (
        "HomeKit accessory state readback is stronger than command acceptance "
        "but is not an independent sensor proving photons/mechanical state."
    )
    return value
