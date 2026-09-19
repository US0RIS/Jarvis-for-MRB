from __future__ import annotations

import hashlib
import inspect
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from jarvis_mrb.permissions import decide as permission_decision
from jarvis_mrb.world_model import DB_PATH


PLAN_ACTIVE_STATES = {"active", "awaiting_approval", "awaiting_verification", "needs_replan", "blocked"}
PLAN_TERMINAL_STATES = {"completed", "superseded", "retired"}
STEP_SUCCESS_STATES = {"verified", "skipped"}
STEP_TERMINAL_FAILURE_STATES = {"failed", "blocked"}
STEP_OPEN_STATES = {"pending", "awaiting_approval", "executing", "executed", "awaiting_verification"}

_ACTIVE_EXECUTIONS: set[str] = set()
_ACTIVE_EXECUTIONS_LOCK = threading.RLock()


def _execution_is_active(step_id: str) -> bool:
    with _ACTIVE_EXECUTIONS_LOCK:
        return str(step_id) in _ACTIVE_EXECUTIONS


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agency_plans (
            id TEXT PRIMARY KEY,
            desired_state_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            summary TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            last_error TEXT NOT NULL DEFAULT '',
            relevance_hash TEXT NOT NULL DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agency_plan_generation
            ON agency_plans(desired_state_id,generation);
        CREATE INDEX IF NOT EXISTS idx_agency_plans_state
            ON agency_plans(status,updated_at DESC);

        CREATE TABLE IF NOT EXISTS agency_steps (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES agency_plans(id) ON DELETE CASCADE,
            step_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            tool TEXT NOT NULL,
            arguments_json TEXT NOT NULL DEFAULT '{}',
            depends_on_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            risk TEXT NOT NULL DEFAULT '',
            requires_confirmation INTEGER NOT NULL DEFAULT 0,
            approval_digest TEXT NOT NULL DEFAULT '',
            verification_id TEXT NOT NULL DEFAULT '',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            result_summary TEXT NOT NULL DEFAULT '',
            blocked_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            UNIQUE(plan_id,step_key),
            UNIQUE(plan_id,ordinal)
        );
        CREATE INDEX IF NOT EXISTS idx_agency_steps_plan
            ON agency_steps(plan_id,status,ordinal);

        CREATE TRIGGER IF NOT EXISTS agency_plans_immutable_identity
        BEFORE UPDATE ON agency_plans
        WHEN NEW.id IS NOT OLD.id
          OR NEW.desired_state_id IS NOT OLD.desired_state_id
          OR NEW.generation IS NOT OLD.generation
          OR NEW.created_at IS NOT OLD.created_at
          OR NEW.relevance_hash IS NOT OLD.relevance_hash
        BEGIN
            SELECT RAISE(ABORT, 'Agency plan identity and relevance baseline are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS agency_steps_immutable_spec
        BEFORE UPDATE ON agency_steps
        WHEN NEW.id IS NOT OLD.id
          OR NEW.plan_id IS NOT OLD.plan_id
          OR NEW.step_key IS NOT OLD.step_key
          OR NEW.ordinal IS NOT OLD.ordinal
          OR NEW.tool IS NOT OLD.tool
          OR NEW.arguments_json IS NOT OLD.arguments_json
          OR NEW.depends_on_json IS NOT OLD.depends_on_json
          OR NEW.risk IS NOT OLD.risk
          OR NEW.requires_confirmation IS NOT OLD.requires_confirmation
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'Agency step specification is immutable');
        END;
        """
    )
    plan_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(agency_plans)").fetchall()}
    if "relevance_hash" not in plan_columns:
        conn.execute("ALTER TABLE agency_plans ADD COLUMN relevance_hash TEXT NOT NULL DEFAULT ''")
    step_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(agency_steps)").fetchall()}
    if "approval_digest" not in step_columns:
        conn.execute("ALTER TABLE agency_steps ADD COLUMN approval_digest TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def _row_to_plan(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "desired_state_id": str(row["desired_state_id"]),
        "generation": int(row["generation"]),
        "summary": str(row["summary"]),
        "rationale": str(row["rationale"]),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "completed_at": str(row["completed_at"] or ""),
        "last_error": str(row["last_error"] or ""),
        "relevance_hash": str(row["relevance_hash"] or ""),
    }


def _row_to_step(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "plan_id": str(row["plan_id"]),
        "step_key": str(row["step_key"]),
        "ordinal": int(row["ordinal"]),
        "tool": str(row["tool"]),
        "arguments": dict(_loads(str(row["arguments_json"]), {})),
        "depends_on": list(_loads(str(row["depends_on_json"]), [])),
        "status": str(row["status"]),
        "risk": str(row["risk"]),
        "requires_confirmation": bool(row["requires_confirmation"]),
        "approval_digest": str(row["approval_digest"] or ""),
        "verification_id": str(row["verification_id"] or ""),
        "attempt_count": int(row["attempt_count"]),
        "result_summary": str(row["result_summary"] or ""),
        "blocked_reason": str(row["blocked_reason"] or ""),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "started_at": str(row["started_at"] or ""),
        "finished_at": str(row["finished_at"] or ""),
    }


def _relevance_hash(conn: sqlite3.Connection, desired_state_id: str) -> str:
    """Fingerprint current world facts that can materially affect one desired state."""
    try:
        state = conn.execute(
            "SELECT intention_id,criteria_json FROM desired_states WHERE id=?",
            (str(desired_state_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        state = None
    if state is None:
        return ""

    criteria = list(_loads(str(state["criteria_json"]), []))
    entity_ids: set[str] = set()
    commitment_ids: set[str] = set()
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        if criterion.get("entity_id"):
            entity_ids.add(str(criterion["entity_id"]))
        if criterion.get("commitment_id"):
            commitment_ids.add(str(criterion["commitment_id"]))

    intention_id = str(state["intention_id"] or "")
    if intention_id:
        try:
            rows = conn.execute(
                "SELECT entity_id FROM intention_entities WHERE intention_id=?",
                (intention_id,),
            ).fetchall()
            entity_ids.update(str(row["entity_id"]) for row in rows)
            rows = conn.execute(
                "SELECT commitment_id FROM intention_commitments WHERE intention_id=?",
                (intention_id,),
            ).fetchall()
            commitment_ids.update(str(row["commitment_id"]) for row in rows)
        except sqlite3.OperationalError:
            pass

    snapshot: dict[str, Any] = {"entities": {}, "commitments": {}}
    for entity_id in sorted(entity_ids):
        beliefs = conn.execute(
            """
            SELECT predicate,object_id,value_json,confidence
            FROM beliefs
            WHERE subject_id=? AND state='current'
            ORDER BY predicate,id
            """,
            (entity_id,),
        ).fetchall()
        linked_events = conn.execute(
            """
            SELECT e.id,e.event_type,e.source_kind,e.source_ref
            FROM event_entities ee
            JOIN events e ON e.id=ee.event_id
            WHERE ee.entity_id=?
              AND e.source_kind NOT IN (
                'jarvis_agency','jarvis_desired_state','proactive_monitor',
                'jarvis_jobs','background_worker','system'
              )
            ORDER BY e.id DESC
            LIMIT 25
            """,
            (entity_id,),
        ).fetchall()
        snapshot["entities"][entity_id] = {
            "beliefs": [
                {
                    "predicate": str(row["predicate"]),
                    "object_id": str(row["object_id"] or ""),
                    "value_json": str(row["value_json"] or ""),
                    "confidence": round(float(row["confidence"] or 0.0), 6),
                }
                for row in beliefs
            ],
            "linked_events": [
                {
                    "id": int(row["id"]),
                    "event_type": str(row["event_type"]),
                    "source_kind": str(row["source_kind"]),
                    "source_ref": str(row["source_ref"]),
                }
                for row in linked_events
            ],
        }

    for commitment_id in sorted(commitment_ids):
        row = conn.execute(
            """
            SELECT owner_id,action,due_at,due_text,status,confidence,updated_at
            FROM commitments WHERE id=?
            """,
            (commitment_id,),
        ).fetchone()
        snapshot["commitments"][commitment_id] = dict(row) if row else None

    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def relevance_hash(desired_state_id: str) -> str:
    with _connect() as conn:
        return _relevance_hash(conn, str(desired_state_id))


def _desired_state_exists(conn: sqlite3.Connection, desired_state_id: str) -> bool:
    try:
        return conn.execute("SELECT 1 FROM desired_states WHERE id=?", (desired_state_id,)).fetchone() is not None
    except sqlite3.OperationalError:
        return False


def _normalize_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        raise ValueError("Agency plan requires at least one step.")
    if len(steps) > 24:
        raise ValueError("Agency plan supports at most 24 steps.")

    keys: list[str] = []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError("Agency plan steps must be objects.")
        key = str(raw.get("id") or raw.get("step_key") or f"s{index}").strip()
        tool = str(raw.get("tool") or "").strip()
        args = raw.get("arguments") or {}
        deps = raw.get("depends_on") or []
        if not key or key in keys:
            raise ValueError("Agency step keys must be unique and non-empty.")
        if not tool:
            raise ValueError(f"Agency step {key!r} requires a tool.")
        if not isinstance(args, dict):
            raise ValueError(f"Agency step {key!r} arguments must be an object.")
        if not isinstance(deps, list):
            raise ValueError(f"Agency step {key!r} depends_on must be a list.")
        keys.append(key)
        normalized.append(
            {
                "step_key": key,
                "tool": tool,
                "arguments": dict(args),
                "depends_on_keys": [str(dep).strip() for dep in deps if str(dep).strip()],
            }
        )

    known = set(keys)
    for step in normalized:
        key = str(step["step_key"])
        deps = list(step["depends_on_keys"])
        if key in deps:
            raise ValueError(f"Agency step {key!r} cannot depend on itself.")
        unknown = [dep for dep in deps if dep not in known]
        if unknown:
            raise ValueError(f"Agency step {key!r} has unknown dependencies: {unknown}.")

    remaining = {str(step["step_key"]): set(step["depends_on_keys"]) for step in normalized}
    resolved: set[str] = set()
    while remaining:
        ready = [key for key, deps in remaining.items() if deps <= resolved]
        if not ready:
            raise ValueError("Agency plan dependency graph contains a cycle.")
        for key in ready:
            resolved.add(key)
            remaining.pop(key, None)

    return normalized


def create_plan(
    desired_state_id: str,
    steps: list[dict[str, Any]],
    *,
    summary: str = "",
    rationale: str = "",
) -> dict[str, Any]:
    state_id = str(desired_state_id or "").strip()
    normalized = _normalize_steps(steps)
    now = _now()
    plan_id = f"agency-plan:{uuid.uuid4()}"

    with _connect() as conn:
        if not _desired_state_exists(conn, state_id):
            raise ValueError(f"Unknown desired state {state_id!r}.")
        row = conn.execute(
            "SELECT COALESCE(MAX(generation),0) AS generation FROM agency_plans WHERE desired_state_id=?",
            (state_id,),
        ).fetchone()
        generation = int(row["generation"] or 0) + 1
        conn.execute(
            """
            UPDATE agency_plans
            SET status='superseded',updated_at=?
            WHERE desired_state_id=? AND status IN ('active','awaiting_approval','awaiting_verification','needs_replan','blocked')
            """,
            (now, state_id),
        )
        plan_relevance_hash = _relevance_hash(conn, state_id)
        conn.execute(
            """
            INSERT INTO agency_plans(
                id,desired_state_id,generation,summary,rationale,status,created_at,updated_at,relevance_hash
            ) VALUES(?,?,?,?,?,'active',?,?,?)
            """,
            (
                plan_id,
                state_id,
                generation,
                " ".join(str(summary or "").split())[:1500] or f"Plan for {state_id}",
                " ".join(str(rationale or "").split())[:3000],
                now,
                now,
                plan_relevance_hash,
            ),
        )

        step_ids = {step["step_key"]: f"agency-step:{uuid.uuid4()}" for step in normalized}
        for ordinal, step in enumerate(normalized, start=1):
            tool = str(step["tool"])
            permission = permission_decision(tool)
            dependency_ids = [step_ids[key] for key in step["depends_on_keys"]]
            conn.execute(
                """
                INSERT INTO agency_steps(
                    id,plan_id,step_key,ordinal,tool,arguments_json,depends_on_json,status,
                    risk,requires_confirmation,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,'pending',?,?,?,?)
                """,
                (
                    step_ids[str(step["step_key"])],
                    plan_id,
                    str(step["step_key"]),
                    ordinal,
                    tool,
                    json.dumps(step["arguments"], ensure_ascii=False, sort_keys=True),
                    json.dumps(dependency_ids, ensure_ascii=False, sort_keys=True),
                    str(permission.risk),
                    1 if permission.needs_confirmation else 0,
                    now,
                    now,
                ),
            )
        conn.commit()

    _record_event(
        "agency.plan.created",
        f"Agency plan generation {generation} created with {len(normalized)} steps.",
        plan_id=plan_id,
        desired_state_id=state_id,
        payload={"generation": generation, "steps": len(normalized)},
    )
    return get_plan(plan_id, include_steps=True) or {}


def create_plan_from_workflow(desired_state_id: str, workflow_plan: dict[str, Any]) -> dict[str, Any]:
    nodes = workflow_plan.get("nodes") if isinstance(workflow_plan, dict) else None
    if not isinstance(nodes, list):
        raise ValueError("Workflow plan does not contain a node list.")
    steps: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("Workflow node must be an object.")
        steps.append(
            {
                "id": str(node.get("id") or ""),
                "tool": str(node.get("tool") or ""),
                "arguments": dict(node.get("arguments") or {}),
                "depends_on": list(node.get("depends_on") or []),
            }
        )
    return create_plan(
        desired_state_id,
        steps,
        summary=str(workflow_plan.get("summary") or ""),
        rationale="Compiled from the bounded Jarvis workflow planner.",
    )


def get_plan(plan_id: str, *, include_steps: bool = False) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM agency_plans WHERE id=?", (str(plan_id),)).fetchone()
        if row is None:
            return None
        result = _row_to_plan(row)
        if include_steps:
            result["steps"] = [
                _row_to_step(item)
                for item in conn.execute(
                    "SELECT * FROM agency_steps WHERE plan_id=? ORDER BY ordinal",
                    (str(plan_id),),
                ).fetchall()
            ]
    return result


def current_plan(desired_state_id: str, *, include_steps: bool = True) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM agency_plans
            WHERE desired_state_id=? AND status!='superseded'
            ORDER BY generation DESC LIMIT 1
            """,
            (str(desired_state_id),),
        ).fetchone()
    if row is None:
        return None
    return get_plan(str(row["id"]), include_steps=include_steps)


def list_plans(*, desired_state_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        if desired_state_id:
            rows = conn.execute(
                "SELECT * FROM agency_plans WHERE desired_state_id=? ORDER BY generation DESC LIMIT ?",
                (str(desired_state_id), safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agency_plans ORDER BY updated_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
    return [_row_to_plan(row) for row in rows]


def _record_event(
    event_type: str,
    summary: str,
    *,
    plan_id: str,
    desired_state_id: str,
    step_id: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        from jarvis_mrb.world_model import record_event

        data = {
            "plan_id": plan_id,
            "desired_state_id": desired_state_id,
            "step_id": step_id,
            **dict(payload or {}),
        }
        record_event(
            event_type,
            summary[:1500],
            source_kind="jarvis_agency",
            source_ref=f"{plan_id}:{step_id or event_type}:{uuid.uuid4()}",
            payload=data,
            evidence="Persistent Agency plan state transition.",
            confidence=1.0,
        )
    except Exception:
        pass


def _set_plan_status(
    conn: sqlite3.Connection,
    plan_id: str,
    status: str,
    *,
    error: str = "",
) -> None:
    now = _now()
    completed_at = now if status == "completed" else None
    conn.execute(
        """
        UPDATE agency_plans
        SET status=?,updated_at=?,completed_at=?,last_error=?
        WHERE id=?
        """,
        (status, now, completed_at, str(error or "")[:3000], plan_id),
    )


def _set_step_status(
    conn: sqlite3.Connection,
    step_id: str,
    status: str,
    *,
    result: str | None = None,
    blocked_reason: str | None = None,
    verification_id: str | None = None,
    increment_attempt: bool = False,
    started: bool = False,
    finished: bool = False,
) -> None:
    row = conn.execute("SELECT * FROM agency_steps WHERE id=?", (step_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown Agency step {step_id!r}.")
    now = _now()
    conn.execute(
        """
        UPDATE agency_steps
        SET status=?,updated_at=?,
            result_summary=?,
            blocked_reason=?,
            verification_id=?,
            attempt_count=?,
            started_at=?,
            finished_at=?
        WHERE id=?
        """,
        (
            status,
            now,
            str(result if result is not None else row["result_summary"])[:3000],
            str(blocked_reason if blocked_reason is not None else row["blocked_reason"])[:3000],
            str(verification_id if verification_id is not None else row["verification_id"])[:300],
            int(row["attempt_count"]) + (1 if increment_attempt else 0),
            now if started and not row["started_at"] else row["started_at"],
            now if finished else row["finished_at"],
            step_id,
        ),
    )


def _verification_for_step(conn: sqlite3.Connection, step_id: str) -> sqlite3.Row | None:
    try:
        return conn.execute(
            """
            SELECT * FROM action_verifications
            WHERE agency_step_id=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (step_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None


def _dependencies_satisfied(conn: sqlite3.Connection, step: sqlite3.Row) -> tuple[bool, str]:
    dependencies = list(_loads(str(step["depends_on_json"]), []))
    if not dependencies:
        return True, ""
    rows = conn.execute(
        f"SELECT id,status FROM agency_steps WHERE id IN ({','.join('?' for _ in dependencies)})",
        tuple(str(value) for value in dependencies),
    ).fetchall()
    by_id = {str(row["id"]): str(row["status"]) for row in rows}
    for dependency in dependencies:
        status = by_id.get(str(dependency), "")
        if status in STEP_TERMINAL_FAILURE_STATES:
            return False, f"Dependency {dependency} is {status}."
        if status not in STEP_SUCCESS_STATES:
            return False, ""
    return True, ""


def next_ready_step(plan_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        plan = conn.execute("SELECT * FROM agency_plans WHERE id=?", (str(plan_id),)).fetchone()
        if plan is None or str(plan["status"]) in PLAN_TERMINAL_STATES:
            return None
        rows = conn.execute(
            "SELECT * FROM agency_steps WHERE plan_id=? AND status='pending' ORDER BY ordinal",
            (str(plan_id),),
        ).fetchall()
        for row in rows:
            ready, dependency_error = _dependencies_satisfied(conn, row)
            if dependency_error:
                _set_step_status(conn, str(row["id"]), "blocked", blocked_reason=dependency_error, finished=True)
                _set_plan_status(conn, str(plan_id), "needs_replan", error=dependency_error)
                conn.commit()
                return None
            if ready:
                return _row_to_step(row)
    return None


def reconcile_plan(plan_id: str) -> dict[str, Any]:
    plan = get_plan(str(plan_id), include_steps=True)
    if plan is None:
        raise ValueError(f"Unknown Agency plan {plan_id!r}.")

    from jarvis_mrb.desired_state import evaluate_desired_state

    desired = evaluate_desired_state(str(plan["desired_state_id"]), persist=True)
    if desired["satisfied"]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id,status FROM agency_steps WHERE plan_id=?",
                (str(plan_id),),
            ).fetchall()
            for row in rows:
                if str(row["status"]) in STEP_OPEN_STATES:
                    _set_step_status(conn, str(row["id"]), "skipped", result="Desired state already satisfied.", finished=True)
            _set_plan_status(conn, str(plan_id), "completed")
            conn.commit()
        _record_event(
            "agency.plan.completed",
            f"Agency plan completed because desired state {plan['desired_state_id']} is satisfied.",
            plan_id=str(plan_id),
            desired_state_id=str(plan["desired_state_id"]),
        )
        return get_plan(str(plan_id), include_steps=True) or {}

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM agency_steps
            WHERE plan_id=? AND status IN ('executing','executed','awaiting_verification')
            ORDER BY ordinal
            """,
            (str(plan_id),),
        ).fetchall()
        for step in rows:
            step_id = str(step["id"])
            step_status = str(step["status"])
            verification = _verification_for_step(conn, step_id)

            if step_status == "executing":
                if _execution_is_active(step_id):
                    # Another thread in this process owns the claimed execution.
                    # A concurrent scheduler/reconcile pass must not misclassify
                    # live work as a process-death recovery case.
                    continue
                # Process death or interruption while the executor was in flight.
                # Never replay automatically: if the audited action produced a
                # durable verification record, resume verification; otherwise the
                # outcome is unknown and the step must fail closed.
                conn.execute(
                    "UPDATE agency_steps SET approval_digest='',updated_at=? WHERE id=?",
                    (_now(), step_id),
                )
                if verification is None:
                    _set_step_status(
                        conn,
                        step_id,
                        "failed",
                        result="Execution was interrupted before a durable outcome-verification record was available.",
                        blocked_reason="Interrupted execution has unknown outcome; automatic replay is forbidden.",
                        finished=True,
                    )
                    continue

            if verification is None:
                if str(step["risk"]) == "read" and step_status == "executed":
                    _set_step_status(
                        conn,
                        step_id,
                        "verified",
                        result=str(step["result_summary"] or "Read observation returned successfully."),
                        finished=True,
                    )
                continue

            verification_id = str(verification["id"])
            verification_status = str(verification["status"])
            evidence = str(verification["last_evidence"] or "")
            if verification_status == "verified":
                _set_step_status(
                    conn,
                    str(step["id"]),
                    "verified",
                    verification_id=verification_id,
                    result=evidence or str(step["result_summary"]),
                    finished=True,
                )
            elif verification_status == "pending":
                _set_step_status(
                    conn,
                    str(step["id"]),
                    "awaiting_verification",
                    verification_id=verification_id,
                    result=evidence or str(step["result_summary"]),
                )
            elif verification_status in {"failed", "timed_out", "unverified"}:
                _set_step_status(
                    conn,
                    str(step["id"]),
                    "failed",
                    verification_id=verification_id,
                    result=evidence or f"Verification {verification_status}.",
                    blocked_reason=f"Outcome verification {verification_status}.",
                    finished=True,
                )

        steps = conn.execute(
            "SELECT * FROM agency_steps WHERE plan_id=? ORDER BY ordinal",
            (str(plan_id),),
        ).fetchall()
        statuses = [str(step["status"]) for step in steps]

        if any(status in STEP_TERMINAL_FAILURE_STATES for status in statuses):
            _set_plan_status(conn, str(plan_id), "needs_replan", error="A plan step failed or became blocked.")
        elif any(status == "awaiting_approval" for status in statuses):
            _set_plan_status(conn, str(plan_id), "awaiting_approval")
        elif any(status in {"executed", "awaiting_verification"} for status in statuses):
            _set_plan_status(conn, str(plan_id), "awaiting_verification")
        elif statuses and all(status in STEP_SUCCESS_STATES for status in statuses):
            _set_plan_status(
                conn,
                str(plan_id),
                "needs_replan",
                error="Plan exhausted but desired state is not yet satisfied.",
            )
        else:
            _set_plan_status(conn, str(plan_id), "active")
        conn.commit()

    return get_plan(str(plan_id), include_steps=True) or {}


def _resolve_value(value: Any, outputs: dict[str, str]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            return str(outputs.get(match.group(1), ""))
        return re.sub(r"\$\{([A-Za-z0-9_-]+)\.message\}", replace, value)
    if isinstance(value, list):
        return [_resolve_value(item, outputs) for item in value]
    if isinstance(value, dict):
        return {str(key): _resolve_value(item, outputs) for key, item in value.items()}
    return value


def resolved_arguments(step_id: str) -> dict[str, Any]:
    with _connect() as conn:
        step = conn.execute("SELECT * FROM agency_steps WHERE id=?", (str(step_id),)).fetchone()
        if step is None:
            raise ValueError(f"Unknown Agency step {step_id!r}.")
        siblings = conn.execute(
            "SELECT step_key,result_summary FROM agency_steps WHERE plan_id=?",
            (str(step["plan_id"]),),
        ).fetchall()
    outputs = {str(row["step_key"]): str(row["result_summary"] or "") for row in siblings}
    template = dict(_loads(str(step["arguments_json"]), {}))
    return dict(_resolve_value(template, outputs))


def _approval_digest(step_id: str, tool: str, arguments: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "step_id": str(step_id),
            "tool": str(tool),
            "arguments": dict(arguments or {}),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _grant_step_approval(step_id: str, tool: str, arguments: dict[str, Any]) -> None:
    digest = _approval_digest(step_id, tool, arguments)
    with _connect() as conn:
        row = conn.execute(
            "SELECT status,tool FROM agency_steps WHERE id=?",
            (str(step_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown Agency step {step_id!r}.")
        if str(row["status"] or "") != "awaiting_approval":
            raise ValueError("Agency approval can only be granted to a step awaiting approval.")
        if str(row["tool"] or "") != str(tool):
            raise ValueError("Agency approval tool does not match the persisted step.")
        conn.execute(
            "UPDATE agency_steps SET approval_digest=?,updated_at=? WHERE id=?",
            (digest, _now(), str(step_id)),
        )
        conn.commit()


def _clear_step_approval(step_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE agency_steps SET approval_digest='',updated_at=? WHERE id=?",
            (_now(), str(step_id)),
        )
        conn.commit()


def _approval_grant_matches(
    step_id: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    required_status: str,
) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT tool,status,approval_digest FROM agency_steps WHERE id=?",
            (str(step_id),),
        ).fetchone()
    if row is None:
        return False
    if str(row["status"] or "") != str(required_status):
        return False
    if str(row["tool"] or "") != str(tool):
        return False
    digest = str(row["approval_digest"] or "")
    if not digest:
        return False
    return digest == _approval_digest(step_id, tool, arguments)


def approved_execution_matches(
    step_id: str,
    tool: str,
    arguments: dict[str, Any],
) -> bool:
    """Validate the exact protected action currently executing under approval.

    This is consulted by agent.execute_tool before honoring bypass_confirmation.
    A bare boolean is never sufficient authority.
    """
    try:
        expected = resolved_arguments(str(step_id))
    except Exception:
        return False
    if expected != dict(arguments or {}):
        return False
    return _approval_grant_matches(
        str(step_id),
        str(tool),
        expected,
        required_status="executing",
    )


def _executor_accepts_bypass(executor: Callable[..., Any]) -> bool:
    """Detect the adapter signature before execution; never retry an action after TypeError."""
    try:
        signature = inspect.signature(executor)
    except (TypeError, ValueError):
        # Unknown callables use the production signature. If that fails, fail closed
        # rather than risking a second invocation after a partial side effect.
        return True
    parameters = signature.parameters
    if "bypass_confirmation" in parameters:
        return True
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())


def _invoke_executor(
    step: dict[str, Any],
    executor: Callable[..., Any],
    *,
    bypass_confirmation: bool,
) -> Any:
    from jarvis_mrb.tool_audit import agency_step_context

    arguments = resolved_arguments(str(step["id"]))
    with agency_step_context(str(step["id"])):
        if _executor_accepts_bypass(executor):
            return executor(
                str(step["tool"]),
                arguments,
                bypass_confirmation=bypass_confirmation,
            )
        if bypass_confirmation:
            raise TypeError(
                "Approved Agency execution requires an executor that explicitly accepts bypass_confirmation."
            )
        return executor(str(step["tool"]), arguments)


def _custom_run_is_read_observation(step: dict[str, Any]) -> bool:
    if str(step.get("tool") or "") != "custom.run":
        return False
    try:
        arguments = resolved_arguments(str(step["id"]))
        name = str(arguments.get("name") or "")
        from jarvis_mrb.custom_tools import list_tools
        matches = [
            item for item in list_tools()
            if str(item.get("name") or "") == name
        ]
    except Exception:
        return False
    return bool(
        len(matches) == 1
        and matches[0].get("enabled")
        and str(matches[0].get("risk") or "") == "read"
    )


def _claim_step_for_execution(
    plan: dict[str, Any],
    step: dict[str, Any],
    arguments: dict[str, Any],
    *,
    bypass_confirmation: bool,
) -> bool:
    """Atomically claim one persisted step for exactly one executor invocation."""
    step_id = str(step["id"])
    expected_status = "awaiting_approval" if bypass_confirmation else "pending"
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status,tool,approval_digest FROM agency_steps WHERE id=? AND plan_id=?",
            (step_id, str(plan["id"])),
        ).fetchone()
        if row is None or str(row["status"] or "") != expected_status:
            conn.rollback()
            return False
        if str(row["tool"] or "") != str(step["tool"]):
            conn.rollback()
            raise PermissionError("Persisted Agency step tool changed before execution.")
        if bypass_confirmation:
            digest = str(row["approval_digest"] or "")
            expected_digest = _approval_digest(step_id, str(step["tool"]), arguments)
            if not digest or digest != expected_digest:
                conn.rollback()
                raise PermissionError(
                    "Approved Agency execution has no matching one-time approval capability."
                )

        _set_step_status(
            conn,
            step_id,
            "executing",
            increment_attempt=True,
            started=True,
        )
        _set_plan_status(conn, str(plan["id"]), "active")
        with _ACTIVE_EXECUTIONS_LOCK:
            _ACTIVE_EXECUTIONS.add(step_id)
        try:
            conn.commit()
        except Exception:
            with _ACTIVE_EXECUTIONS_LOCK:
                _ACTIVE_EXECUTIONS.discard(step_id)
            raise
    return True


def _execute_step(
    plan: dict[str, Any],
    step: dict[str, Any],
    executor: Callable[..., Any],
    *,
    bypass_confirmation: bool,
) -> dict[str, Any]:
    step_id = str(step["id"])
    arguments = resolved_arguments(step_id)
    claimed = _claim_step_for_execution(
        plan,
        step,
        arguments,
        bypass_confirmation=bypass_confirmation,
    )
    if not claimed:
        # Another worker already claimed or completed this exact step. Returning
        # the persisted plan is fail-closed and, critically, does not invoke the
        # side-effecting executor a second time.
        return get_plan(str(plan["id"]), include_steps=True) or {}

    try:
        try:
            reply = _invoke_executor(step, executor, bypass_confirmation=bypass_confirmation)
            ok = bool(getattr(reply, "ok", False))
            message = str(getattr(reply, "message", reply) or "")
        except Exception as exc:
            ok = False
            message = f"Execution raised {type(exc).__name__}: {exc}"
        finally:
            if bypass_confirmation:
                _clear_step_approval(step_id)

        with _connect() as conn:
            if not ok:
                _set_step_status(
                    conn,
                    str(step["id"]),
                    "failed",
                    result=message,
                    blocked_reason="Tool execution failed.",
                    finished=True,
                )
                _set_plan_status(conn, str(plan["id"]), "needs_replan", error=message)
                conn.commit()
            else:
                _set_step_status(conn, str(step["id"]), "executed", result=message)
                verification = _verification_for_step(conn, str(step["id"]))
                if verification is not None:
                    verification_id = str(verification["id"])
                    verification_status = str(verification["status"])
                    if verification_status == "verified":
                        _set_step_status(
                            conn,
                            str(step["id"]),
                            "verified",
                            verification_id=verification_id,
                            result=str(verification["last_evidence"] or message),
                            finished=True,
                        )
                    elif verification_status == "pending":
                        _set_step_status(
                            conn,
                            str(step["id"]),
                            "awaiting_verification",
                            verification_id=verification_id,
                            result=str(verification["last_evidence"] or message),
                        )
                    else:
                        _set_step_status(
                            conn,
                            str(step["id"]),
                            "failed",
                            verification_id=verification_id,
                            result=str(verification["last_evidence"] or message),
                            blocked_reason=f"Outcome verification {verification_status}.",
                            finished=True,
                        )
                elif str(step["risk"]) == "read" or _custom_run_is_read_observation(step):
                    _set_step_status(conn, str(step["id"]), "verified", result=message, finished=True)
                else:
                    _set_step_status(
                        conn,
                        str(step["id"]),
                        "failed",
                        result=message,
                        blocked_reason="No durable action-verification record was produced.",
                        finished=True,
                    )
                conn.commit()

        _record_event(
            "agency.step.executed",
            f"Agency step {step['step_key']} executed: {step['tool']}.",
            plan_id=str(plan["id"]),
            desired_state_id=str(plan["desired_state_id"]),
            step_id=str(step["id"]),
            payload={"tool": step["tool"], "ok": ok},
        )
        try:
            from jarvis_mrb.agency_runtime import _update_runtime
            _update_runtime(str(plan["desired_state_id"]), action=True)
        except Exception:
            # Action execution state is authoritative in the plan ledger. Fairness
            # metadata must never turn an already-attempted action into a retry.
            pass
        return reconcile_plan(str(plan["id"]))
    finally:
        with _ACTIVE_EXECUTIONS_LOCK:
            _ACTIVE_EXECUTIONS.discard(step_id)


def _invalidate_stale_plan(plan: dict[str, Any], *, pending_step_id: str = "") -> dict[str, Any] | None:
    baseline = str(plan.get("relevance_hash") or "")
    current = relevance_hash(str(plan.get("desired_state_id") or ""))
    if not baseline or not current or baseline == current:
        return None
    reason = "Relevant world state changed after this plan was compiled; replan before another consequential action."
    with _connect() as conn:
        if pending_step_id:
            row = conn.execute("SELECT status FROM agency_steps WHERE id=?", (pending_step_id,)).fetchone()
            if row is not None and str(row["status"]) == "awaiting_approval":
                _set_step_status(
                    conn,
                    pending_step_id,
                    "pending",
                    blocked_reason="",
                    result="Approval was not consumed because relevant world state changed.",
                )
        _set_plan_status(conn, str(plan["id"]), "needs_replan", error=reason)
        conn.commit()
    _record_event(
        "agency.plan.invalidated",
        reason,
        plan_id=str(plan["id"]),
        desired_state_id=str(plan["desired_state_id"]),
        step_id=str(pending_step_id or ""),
        payload={"baseline_relevance_hash": baseline, "current_relevance_hash": current},
    )
    return get_plan(str(plan["id"]), include_steps=True)


def _execution_authority_error(plan: dict[str, Any]) -> str:
    try:
        from jarvis_mrb.agency_runtime import get_mode
        mode = get_mode()
    except Exception:
        return "Agency runtime mode could not be verified."
    if mode != "active":
        return f"Agency runtime mode is {mode!r}, not 'active'."

    desired_state_id = str(plan.get("desired_state_id") or "")
    with _connect() as conn:
        row = conn.execute(
            "SELECT state,authority_json FROM desired_states WHERE id=?",
            (desired_state_id,),
        ).fetchone()
    if row is None:
        return "Agency plan has no persistent desired state."
    if str(row["state"] or "") != "active":
        return f"Desired state is {str(row['state'] or '')!r}, not 'active'."
    authority = dict(_loads(str(row["authority_json"]), {}))
    if authority.get("agency_enabled") is not True:
        return "Per-goal Agency authority is disabled."
    return ""


def execute_next(plan_id: str, executor: Callable[..., Any]) -> dict[str, Any]:
    plan = reconcile_plan(str(plan_id))
    if str(plan.get("status") or "") in PLAN_TERMINAL_STATES | {"awaiting_approval", "awaiting_verification", "needs_replan", "blocked"}:
        return plan
    authority_error = _execution_authority_error(plan)
    if authority_error:
        raise PermissionError(authority_error)

    step = next_ready_step(str(plan_id))
    if step is None:
        return reconcile_plan(str(plan_id))

    permission = permission_decision(str(step["tool"]))
    if str(permission.risk) != "read":
        stale = _invalidate_stale_plan(plan)
        if stale is not None:
            return stale
    if not permission.allowed:
        with _connect() as conn:
            reason = f"Permission policy denies {permission.risk} action {step['tool']}."
            _set_step_status(conn, str(step["id"]), "blocked", blocked_reason=reason, finished=True)
            _set_plan_status(conn, str(plan_id), "needs_replan", error=reason)
            conn.commit()
        return get_plan(str(plan_id), include_steps=True) or {}

    if permission.needs_confirmation:
        with _connect() as conn:
            _set_step_status(conn, str(step["id"]), "awaiting_approval")
            _set_plan_status(conn, str(plan_id), "awaiting_approval")
            conn.commit()
        _record_event(
            "agency.step.awaiting_approval",
            f"Agency step {step['step_key']} requires approval before {step['tool']}.",
            plan_id=str(plan_id),
            desired_state_id=str(plan["desired_state_id"]),
            step_id=str(step["id"]),
            payload={"tool": step["tool"], "risk": str(permission.risk)},
        )
        return get_plan(str(plan_id), include_steps=True) or {}

    return _execute_step(plan, step, executor, bypass_confirmation=False)


def list_pending_approvals(*, plan_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    with _connect() as conn:
        sql = """
            SELECT s.*,p.desired_state_id,p.generation,p.summary AS plan_summary,
                   COALESCE(d.title,p.desired_state_id) AS desired_state_title
            FROM agency_steps s
            JOIN agency_plans p ON p.id=s.plan_id
            LEFT JOIN desired_states d ON d.id=p.desired_state_id
            WHERE s.status='awaiting_approval' AND p.status='awaiting_approval'
        """
        params: list[Any] = []
        if plan_id:
            sql += " AND s.plan_id=?"
            params.append(str(plan_id))
        sql += " ORDER BY p.updated_at DESC,s.ordinal LIMIT ?"
        params.append(safe_limit)
        rows = conn.execute(sql, tuple(params)).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_step(row)
        item["resolved_arguments"] = resolved_arguments(str(item["id"]))
        item["desired_state_id"] = str(row["desired_state_id"])
        item["desired_state_title"] = str(row["desired_state_title"])
        item["generation"] = int(row["generation"])
        item["plan_summary"] = str(row["plan_summary"])
        result.append(item)
    return result


def _approval_display_id(step_id: str, tool: str) -> str:
    raw = json.dumps(
        {"step_id": str(step_id), "tool": str(tool)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]


def describe_pending_approval(item: dict[str, Any]) -> str:
    """Render enough detail for informed consent without leaking arbitrary payloads."""
    tool = str(item.get("tool") or "protected action")
    args = dict(item.get("resolved_arguments") or {})
    fingerprint = _approval_display_id(str(item.get("id") or ""), tool)

    if tool == "gmail.send":
        recipient = str(args.get("recipient") or "").strip() or "<unspecified recipient>"
        subject = str(args.get("subject") or "").strip()
        subject_text = f", subject {subject!r}" if subject else ""
        return (
            f"send email to {recipient!r}{subject_text}; "
            f"message body omitted from notification; action {fingerprint}"
        )

    if tool == "calendar.create":
        summary = str(args.get("summary") or "").strip() or "<untitled event>"
        start = str(args.get("start") or "").strip() or "<unspecified start>"
        end = str(args.get("end") or "").strip() or "<unspecified end>"
        return (
            f"create calendar event {summary!r} from {start} to {end}; "
            f"description omitted; action {fingerprint}"
        )

    if tool in {"smart.close", "pc.close_app", "browser.close_tab"}:
        target = str(args.get("name") or args.get("query") or "").strip() or "<unspecified target>"
        return f"{tool} target {target!r}; action {fingerprint}"

    if tool in {"smart.open", "pc.launch_app", "browser.open_site", "browser.focus_tab"}:
        target = str(args.get("name") or args.get("query") or "").strip() or "<unspecified target>"
        return f"{tool} target {target!r}; action {fingerprint}"

    if tool in {"jobs.cancel", "background.cancel"}:
        target = args.get("job_id") if tool == "jobs.cancel" else args.get("task_id")
        return f"{tool} target {target!r}; action {fingerprint}"

    if tool in {"state.update", "state.temp_set"}:
        key = str(args.get("key") or "").strip() or "<unspecified key>"
        return f"{tool} key {key!r}; value omitted; action {fingerprint}"

    if tool == "custom.run":
        name = str(args.get("name") or "").strip() or "<unspecified custom tool>"
        nested = args.get("arguments")
        argument_names = (
            sorted(str(key) for key in nested)
            if isinstance(nested, dict) else []
        )
        hosts: list[str] = []
        try:
            from jarvis_mrb.custom_tools import list_tools
            match = next(
                (
                    candidate for candidate in list_tools()
                    if str(candidate.get("name") or "") == name
                ),
                None,
            )
            if isinstance(match, dict):
                hosts = [
                    str(value)
                    for value in (match.get("allowed_hosts") or [])
                    if str(value).strip()
                ]
        except Exception:
            hosts = []
        return (
            f"custom.run {name!r} against allowed host(s) {hosts!r}; "
            f"argument names {argument_names!r}; values omitted; action {fingerprint}"
        )

    if tool == "custom.synthesize":
        name = str(args.get("name") or "").strip() or "<unspecified custom tool>"
        hosts = [
            str(value)
            for value in (args.get("allowed_hosts") or [])
            if str(value).strip()
        ]
        risk = str(args.get("risk") or "read")
        return (
            f"custom.synthesize {name!r} for risk {risk!r}, allowed host(s) {hosts!r}; "
            f"API specification omitted; action {fingerprint}"
        )

    if tool == "custom.enable":
        name = str(args.get("name") or "").strip() or "<unspecified custom tool>"
        return (
            f"custom.enable {name!r} enabled={bool(args.get('enabled', True))}; "
            f"action {fingerprint}"
        )

    if tool == "custom.apply_repair":
        name = str(args.get("name") or "").strip() or "<unspecified custom tool>"
        return f"custom.apply_repair {name!r}; repair payload omitted; action {fingerprint}"

    parameter_names = sorted(str(key) for key in args)
    rendered_names = ", ".join(parameter_names[:12]) if parameter_names else "none"
    if len(parameter_names) > 12:
        rendered_names += ", ..."
    return (
        f"{tool} with parameter names [{rendered_names}]; "
        f"values omitted; action {fingerprint}"
    )


def pending_approval(*, plan_id: str | None = None) -> dict[str, Any] | None:
    rows = list_pending_approvals(plan_id=plan_id, limit=2)
    return rows[0] if len(rows) == 1 else None


def _normalize_match(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def matching_pending_approval(query: str) -> dict[str, Any]:
    needle = _normalize_match(query)
    if not needle:
        raise ValueError("Approval query is empty.")
    candidates = list_pending_approvals(limit=200)
    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for item in candidates:
        title = _normalize_match(str(item.get("desired_state_title") or ""))
        state_id = _normalize_match(str(item.get("desired_state_id") or ""))
        if needle in {title, state_id}:
            exact.append(item)
            continue
        if needle and (needle in title or needle in state_id):
            partial.append(item)
    matches = exact if exact else partial
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("No pending Agency approval uniquely matches that description.")
    titles = ", ".join(str(item.get("desired_state_title") or item.get("tool")) for item in matches[:5])
    raise ValueError(f"That description matches multiple pending Agency approvals: {titles}.")


def approve_matching(query: str, executor: Callable[..., Any]) -> dict[str, Any]:
    step = matching_pending_approval(query)
    return approve_step(str(step["plan_id"]), str(step["id"]), executor)


def deny_matching(query: str, *, reason: str = "User denied the proposed action.") -> dict[str, Any]:
    step = matching_pending_approval(query)
    return deny_step(str(step["plan_id"]), str(step["id"]), reason=reason)


def approve_step(plan_id: str, step_id: str, executor: Callable[..., Any]) -> dict[str, Any]:
    plan = get_plan(str(plan_id), include_steps=True)
    if plan is None:
        raise ValueError(f"Unknown Agency plan {plan_id!r}.")
    step = next((item for item in plan.get("steps") or [] if str(item["id"]) == str(step_id)), None)
    if step is None:
        raise ValueError(f"Unknown Agency step {step_id!r}.")
    if str(step["status"]) != "awaiting_approval":
        raise ValueError("Agency step is not waiting for approval.")

    authority_error = _execution_authority_error(plan)
    if authority_error:
        raise PermissionError(authority_error)

    permission = permission_decision(str(step["tool"]))
    if str(permission.risk) != "read":
        stale = _invalidate_stale_plan(plan, pending_step_id=str(step_id))
        if stale is not None:
            return stale
    if not permission.allowed:
        return deny_step(str(plan_id), str(step_id), reason=f"Permission policy now denies {permission.risk}.")
    arguments = resolved_arguments(str(step_id))
    _grant_step_approval(str(step_id), str(step["tool"]), arguments)
    try:
        return _execute_step(plan, step, executor, bypass_confirmation=True)
    except Exception:
        _clear_step_approval(str(step_id))
        raise


def approve_pending(executor: Callable[..., Any]) -> dict[str, Any] | None:
    step = pending_approval()
    if step is None:
        return None
    return approve_step(str(step["plan_id"]), str(step["id"]), executor)


def deny_step(plan_id: str, step_id: str, *, reason: str = "User denied the proposed action.") -> dict[str, Any]:
    plan = get_plan(str(plan_id), include_steps=True)
    if plan is None:
        raise ValueError(f"Unknown Agency plan {plan_id!r}.")
    step = next(
        (
            item for item in plan.get("steps") or []
            if str(item.get("id") or "") == str(step_id)
        ),
        None,
    )
    if step is None:
        raise ValueError(f"Unknown Agency step {step_id!r}.")
    if str(step.get("status") or "") != "awaiting_approval":
        raise ValueError("Agency step is not waiting for approval.")
    if str(plan.get("status") or "") != "awaiting_approval":
        raise ValueError("Agency plan is not waiting for approval.")
    with _connect() as conn:
        _set_step_status(
            conn,
            str(step_id),
            "blocked",
            blocked_reason=str(reason or "Action denied."),
            result=str(reason or "Action denied."),
            finished=True,
        )
        _set_plan_status(conn, str(plan_id), "needs_replan", error=str(reason or "Action denied."))
        conn.commit()
    _record_event(
        "agency.step.denied",
        f"Agency step denied: {reason}",
        plan_id=str(plan_id),
        desired_state_id=str(plan["desired_state_id"]),
        step_id=str(step_id),
    )
    return get_plan(str(plan_id), include_steps=True) or {}


def deny_pending(*, reason: str = "User denied the proposed action.") -> dict[str, Any] | None:
    step = pending_approval()
    if step is None:
        return None
    return deny_step(str(step["plan_id"]), str(step["id"]), reason=reason)


def status() -> dict[str, Any]:
    with _connect() as conn:
        plans = {
            str(row["status"]): int(row["count"])
            for row in conn.execute("SELECT status,COUNT(*) AS count FROM agency_plans GROUP BY status").fetchall()
        }
        steps = {
            str(row["status"]): int(row["count"])
            for row in conn.execute("SELECT status,COUNT(*) AS count FROM agency_steps GROUP BY status").fetchall()
        }
    return {"ready": True, "plans": plans, "steps": steps}
