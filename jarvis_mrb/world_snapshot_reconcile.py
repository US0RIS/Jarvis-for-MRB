from __future__ import annotations

import json
import sqlite3
from typing import Any

from jarvis_mrb.world_model import DB_PATH, SELF_ID, assert_belief, record_event


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ids(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {
        str(item.get("id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def reconcile_authoritative_snapshot(snapshot: dict[str, Any]) -> dict[str, int]:
    """Retire operational records omitted from a full iPhone metadata snapshot.

    The frontend snapshot is authoritative for Goal Manager and Waiting-On membership.
    A missing row means it was deleted locally. We preserve provenance/history but
    must not keep treating the removed row as a current goal or pending obligation.

    This intentionally does not infer deletion for Known People, inventory, encounters,
    or reminders yet. Those stores have different privacy/history semantics and need
    explicit deletion contracts rather than silently treating every absent bounded row
    as a deletion.
    """
    data = dict(snapshot or {})
    current_goal_ids = _ids(data.get("goals"))
    current_waiting_ids = _ids(data.get("waiting"))
    retired_goals = 0
    retired_waiting = 0

    with _connect() as conn:
        goal_rows = conn.execute(
            """
            SELECT x.external_id,e.id,e.canonical_name
            FROM external_ids x
            JOIN entities e ON e.id=x.entity_id
            WHERE x.namespace='iphone_goal'
            """
        ).fetchall()

    for row in goal_rows:
        external_id = str(row["external_id"])
        if external_id in current_goal_ids:
            continue
        entity_id = str(row["id"])
        event_id = record_event(
            "goal.removed",
            f"Goal removed from iPhone Goal Manager: {row['canonical_name']}",
            source_kind="iphone_snapshot_reconcile",
            source_ref=f"goal:{external_id}",
            payload={"goal_id": external_id, "status": "retired"},
            evidence="The goal was absent from a later authoritative full iPhone Goal Manager snapshot.",
            confidence=1.0,
            participants=[(SELF_ID, "owner", 1.0), (entity_id, "goal", 1.0)],
        )
        assert_belief(
            entity_id,
            "status",
            value="retired",
            confidence=1.0,
            source_event_id=event_id,
            evidence="Removed from authoritative iPhone Goal Manager snapshot",
        )
        retired_goals += 1

    with _connect() as conn:
        waiting_rows = conn.execute(
            "SELECT id,action,status,metadata_json FROM commitments WHERE id LIKE 'waiting:%'"
        ).fetchall()

    for row in waiting_rows:
        commitment_id = str(row["id"])
        external_id = commitment_id.split(":", 1)[1] if ":" in commitment_id else commitment_id
        if external_id in current_waiting_ids or str(row["status"]) != "pending":
            continue
        metadata: dict[str, Any]
        try:
            parsed = json.loads(str(row["metadata_json"] or "{}"))
            metadata = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            metadata = {}
        if metadata.get("origin") != "iphone_waiting":
            continue

        event_id = record_event(
            "commitment.waiting_removed",
            f"Waiting-On item removed from iPhone tracker: {row['action']}",
            source_kind="iphone_snapshot_reconcile",
            source_ref=commitment_id,
            payload={"commitment_id": commitment_id, "status": "retired"},
            evidence="The Waiting-On row was absent from a later authoritative full iPhone snapshot.",
            confidence=1.0,
            participants=[(SELF_ID, "beneficiary", 1.0)],
        )
        with _connect() as conn:
            metadata["retired_by"] = "authoritative_iphone_snapshot"
            metadata["retirement_event_id"] = event_id
            conn.execute(
                "UPDATE commitments SET status='retired',updated_at=CURRENT_TIMESTAMP,metadata_json=? WHERE id=? AND status='pending'",
                (json.dumps(metadata, ensure_ascii=False, sort_keys=True), commitment_id),
            )
            changed = conn.total_changes
            conn.commit()
        if changed:
            retired_waiting += 1

    return {
        "retired_goals": retired_goals,
        "retired_waiting": retired_waiting,
    }
