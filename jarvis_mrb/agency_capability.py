from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agency_capability_gaps (
            id TEXT PRIMARY KEY,
            desired_state_id TEXT NOT NULL DEFAULT '',
            capability TEXT NOT NULL,
            reason TEXT NOT NULL,
            observed_availability_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'open',
            proposed_tool_name TEXT NOT NULL DEFAULT '',
            resolution TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agency_capability_gaps
            ON agency_capability_gaps(status,desired_state_id,updated_at DESC);
        """
    )
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(agency_capability_gaps)").fetchall()}
    if "observed_availability_json" not in columns:
        conn.execute(
            "ALTER TABLE agency_capability_gaps ADD COLUMN observed_availability_json TEXT NOT NULL DEFAULT '{}'"
        )
    conn.commit()
    return conn


def available_tool(tool: str) -> dict[str, Any]:
    """Describe availability separately from authority.

    Presence in the built-in risk map means Jarvis knows the tool contract. A denied
    permission is not a missing capability; it is an authority boundary.
    """
    from jarvis_mrb.permissions import TOOL_RISK, decide
    from jarvis_mrb.workflow_engine import _ALLOWED_NODE_TOOLS

    name = str(tool or "").strip()
    if name in TOOL_RISK:
        permission = decide(name)
        agency_allowed = name in _ALLOWED_NODE_TOOLS
        permission_allowed = bool(permission.allowed)
        return {
            "tool": name,
            "known": True,
            "available": bool(agency_allowed and permission_allowed),
            "implemented_for_agency": bool(agency_allowed),
            "authority_blocked": bool(not permission_allowed),
            "agency_scope_blocked": bool(not agency_allowed),
            "risk": str(permission.risk),
            "requires_confirmation": bool(permission.needs_confirmation),
            "source": "builtin",
        }

    try:
        from jarvis_mrb.custom_tools import list_tools
        matches = [item for item in list_tools() if str(item.get("name") or "") == name]
    except Exception:
        matches = []
    if len(matches) == 1:
        item = matches[0]
        enabled = bool(item.get("enabled"))
        wrapper_permission = decide("custom.run")
        return {
            "tool": name,
            "known": True,
            "available": bool(enabled and wrapper_permission.allowed),
            "implemented_for_agency": True,
            "authority_blocked": bool((not enabled) or (not wrapper_permission.allowed)),
            "agency_scope_blocked": False,
            "risk": str(item.get("risk") or "security"),
            "requires_confirmation": bool(wrapper_permission.needs_confirmation),
            "source": "custom",
            "enabled": enabled,
            "wrapper_tool": "custom.run",
        }

    return {
        "tool": name,
        "known": False,
        "available": False,
        "implemented_for_agency": False,
        "authority_blocked": False,
        "agency_scope_blocked": False,
        "risk": "",
        "requires_confirmation": False,
        "source": "missing",
    }


def record_gap(
    desired_state_id: str,
    capability: str,
    reason: str,
) -> dict[str, Any]:
    state_id = str(desired_state_id or "").strip()
    clean_capability = " ".join(str(capability or "").split())[:500]
    clean_reason = " ".join(str(reason or "").split())[:3000]
    if not clean_capability:
        raise ValueError("Capability gap requires a capability name.")
    now = _now()

    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT * FROM agency_capability_gaps
            WHERE desired_state_id=? AND capability=? AND status IN ('open','proposed')
            ORDER BY updated_at DESC LIMIT 1
            """,
            (state_id, clean_capability),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE agency_capability_gaps SET reason=?,updated_at=? WHERE id=?",
                (clean_reason, now, str(existing["id"])),
            )
            gap_id = str(existing["id"])
        else:
            gap_id = f"cap-gap:{uuid.uuid4()}"
            observed_availability = available_tool(clean_capability)
            conn.execute(
                """
                INSERT INTO agency_capability_gaps(
                    id,desired_state_id,capability,reason,observed_availability_json,
                    status,created_at,updated_at
                ) VALUES(?,?,?,?,?,'open',?,?)
                """,
                (
                    gap_id,
                    state_id,
                    clean_capability,
                    clean_reason,
                    json.dumps(observed_availability, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        conn.commit()

    try:
        from jarvis_mrb.world_model import record_event
        record_event(
            "agency.capability_gap",
            f"Agency capability gap: {clean_capability}. {clean_reason}",
            source_kind="jarvis_agency",
            source_ref=gap_id,
            occurred_at=now,
            payload={
                "gap_id": gap_id,
                "desired_state_id": state_id,
                "capability": clean_capability,
                "reason": clean_reason,
            },
            evidence="Agency planner/runtime explicitly identified a missing capability.",
            confidence=1.0,
        )
    except Exception:
        pass

    return get_gap(gap_id) or {}


def get_gap(gap_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agency_capability_gaps WHERE id=?",
            (str(gap_id),),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    try:
        item["observed_availability"] = json.loads(str(item.pop("observed_availability_json") or "{}"))
    except (json.JSONDecodeError, TypeError):
        item["observed_availability"] = {}
    return item


def list_gaps(*, desired_state_id: str | None = None, open_only: bool = False) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if desired_state_id:
        clauses.append("desired_state_id=?")
        params.append(str(desired_state_id))
    if open_only:
        clauses.append("status IN ('open','proposed')")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM agency_capability_gaps{where} ORDER BY updated_at DESC",
            tuple(params),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["observed_availability"] = json.loads(str(item.pop("observed_availability_json") or "{}"))
        except (json.JSONDecodeError, TypeError):
            item["observed_availability"] = {}
        result.append(item)
    return result


def synthesize_adapter(
    gap_id: str,
    *,
    name: str,
    description: str,
    api_spec: str,
    allowed_hosts: list[str],
    risk: str = "read",
) -> dict[str, Any]:
    gap = get_gap(str(gap_id))
    if gap is None:
        raise ValueError(f"Unknown capability gap {gap_id!r}.")
    if str(gap.get("status") or "") not in {"open", "proposed"}:
        raise ValueError("Capability gap is already resolved.")
    hosts = [str(value).strip() for value in allowed_hosts if str(value).strip()]
    if not hosts:
        raise ValueError("Adapter synthesis requires at least one explicit allowed host.")
    if not str(api_spec or "").strip():
        raise ValueError("Adapter synthesis requires an API specification.")

    from jarvis_mrb.custom_tools import synthesize

    item = synthesize(
        name=str(name or ""),
        description=str(description or gap.get("capability") or ""),
        api_spec=str(api_spec or ""),
        allowed_hosts=hosts,
        risk=str(risk or "read"),
    )
    # custom_tools.synthesize deliberately creates disabled tools. Reassert the
    # invariant here so Agency can never turn synthesis into silent authority.
    if bool(item.get("enabled")):
        try:
            from jarvis_mrb.custom_tools import set_enabled
            item = set_enabled(str(item.get("name") or name), False)
        except Exception as exc:
            raise RuntimeError("Generated adapter unexpectedly enabled and could not be disabled.") from exc

    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE agency_capability_gaps
            SET status='proposed',proposed_tool_name=?,resolution=?,updated_at=?
            WHERE id=?
            """,
            (
                str(item.get("name") or name)[:300],
                "Sandbox-tested adapter drafted; remains disabled pending explicit enable authority.",
                now,
                str(gap_id),
            ),
        )
        conn.commit()
    return {
        "gap": get_gap(str(gap_id)),
        "tool": item,
        "enabled": bool(item.get("enabled")),
    }


def reconcile_gaps() -> dict[str, Any]:
    """Resume blocked goals when a previously missing/proposed capability becomes usable."""
    from jarvis_mrb.desired_state import get_desired_state, set_state

    resumed: list[str] = []
    resolved: list[str] = []
    gaps = list_gaps(open_only=True)
    for gap in gaps:
        capability = str(gap.get("capability") or "")
        proposed = str(gap.get("proposed_tool_name") or "")
        target = proposed or capability
        availability = available_tool(target)
        if not bool(availability.get("available")):
            continue

        gap_id = str(gap["id"])
        resolve_gap(
            gap_id,
            f"Capability {target} is now available to Agency through {availability.get('wrapper_tool') or target}.",
        )
        resolved.append(gap_id)

        state_id = str(gap.get("desired_state_id") or "")
        state = get_desired_state(state_id) if state_id else None
        if state is None or str(state.get("state") or "") != "blocked":
            continue
        blocked_reason = str(state.get("blocked_reason") or "").lower()
        if capability.lower() not in blocked_reason and proposed.lower() not in blocked_reason:
            continue

        remaining = [
            item for item in list_gaps(desired_state_id=state_id, open_only=True)
            if str(item.get("id") or "") != gap_id
        ]
        if remaining:
            continue
        set_state(state_id, "active")
        resumed.append(state_id)

    return {
        "checked": len(gaps),
        "resolved": resolved,
        "reactivated": resumed,
    }


def resolve_gap(gap_id: str, resolution: str) -> dict[str, Any]:
    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM agency_capability_gaps WHERE id=?",
            (str(gap_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown capability gap {gap_id!r}.")
        conn.execute(
            """
            UPDATE agency_capability_gaps
            SET status='resolved',resolution=?,updated_at=?
            WHERE id=?
            """,
            (str(resolution or "")[:3000], now, str(gap_id)),
        )
        conn.commit()
    return get_gap(str(gap_id)) or {}


def status() -> dict[str, Any]:
    with _connect() as conn:
        counts = {
            str(row["status"]): int(row["count"])
            for row in conn.execute(
                "SELECT status,COUNT(*) AS count FROM agency_capability_gaps GROUP BY status"
            ).fetchall()
        }
    return {"ready": True, "gaps": counts}
