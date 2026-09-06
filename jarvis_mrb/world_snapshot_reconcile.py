from __future__ import annotations

import json
import re
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


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:500]


def _safe_attributes(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _revoke_known_person_enrollment(current_people_ids: set[str]) -> int:
    """Revoke iPhone face enrollment without guessing a global erasure request.

    Absence from the full Known People snapshot means the closed-set face enrollment
    no longer exists. We therefore remove the iPhone enrollment identity and copied
    private profile metadata. Independent identities/evidence (for example Gmail or a
    calendar participant) remain untouched. If the entity had no independent identity,
    it is tombstoned so the old enrolled name cannot keep creating future graph links.

    Historical events are retained as provenance. A future explicit "forget this
    person everywhere" action would be a separate destructive privacy operation.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT x.external_id,e.id,e.canonical_name,e.attributes_json
            FROM external_ids x
            JOIN entities e ON e.id=x.entity_id
            WHERE x.namespace='iphone_known_person'
            """
        ).fetchall()

    revoked = 0
    for row in rows:
        external_id = str(row["external_id"])
        if external_id in current_people_ids:
            continue

        entity_id = str(row["id"])
        old_name = str(row["canonical_name"])
        event_id = record_event(
            "person.enrollment_revoked",
            f"Known People enrollment revoked for {old_name}",
            source_kind="iphone_snapshot_reconcile",
            source_ref=f"known_person:{external_id}",
            payload={"known_person_id": external_id, "status": "revoked"},
            evidence="The enrollment was absent from a later authoritative full iPhone Known People snapshot.",
            confidence=1.0,
            participants=[(entity_id, "former_enrollment", 1.0)],
        )
        assert_belief(
            entity_id,
            "known_person_enrollment",
            value="revoked",
            confidence=1.0,
            source_event_id=event_id,
            evidence="Removed from authoritative iPhone Known People snapshot",
        )

        with _connect() as conn:
            other_ids = conn.execute(
                "SELECT namespace,external_id FROM external_ids WHERE entity_id=? AND NOT (namespace='iphone_known_person' AND external_id=?)",
                (entity_id, external_id),
            ).fetchall()
            attributes = _safe_attributes(str(row["attributes_json"] or "{}"))
            # These fields originated in the explicit Known People profile and should
            # not survive unenrollment merely because the graph retains history.
            attributes.pop("note", None)
            attributes.pop("contact_id", None)
            attributes["known_people_enrollment"] = "revoked"

            conn.execute(
                "DELETE FROM external_ids WHERE namespace='iphone_known_person' AND external_id=?",
                (external_id,),
            )
            conn.execute(
                "DELETE FROM aliases WHERE entity_id=? AND source='iphone_known_person'",
                (entity_id,),
            )

            if not other_ids:
                # With no independent identity source, keeping the old enrolled name
                # as an active entity would allow future text to relink to a person the
                # user explicitly unenrolled. Tombstone the live identity instead.
                tombstone = f"Former enrolled person {external_id[:8]}"
                conn.execute(
                    "UPDATE entities SET canonical_name=?,normalized_name=?,attributes_json=? WHERE id=?",
                    (tombstone, _normalized(tombstone), json.dumps(attributes, ensure_ascii=False, sort_keys=True), entity_id),
                )
                # Derived current relations are disposable inference; source events
                # remain. Removing them prevents a revoked local identity from
                # continuing to influence current person/project context.
                conn.execute(
                    "DELETE FROM entity_relations WHERE subject_id=? OR object_id=?",
                    (entity_id, entity_id),
                )
            else:
                # The person still exists through independent evidence. Preserve that
                # identity while removing only Known People-specific private metadata.
                conn.execute(
                    "UPDATE entities SET attributes_json=? WHERE id=?",
                    (json.dumps(attributes, ensure_ascii=False, sort_keys=True), entity_id),
                )
            conn.commit()
        revoked += 1
    return revoked


def reconcile_authoritative_snapshot(snapshot: dict[str, Any]) -> dict[str, int]:
    """Reconcile current iPhone-owned lists against the persistent world model.

    Goals and Waiting-On rows are operational state: omission retires the current row
    while preserving history. Known People is an enrollment/privacy state: omission
    revokes the iPhone enrollment identity and copied private profile metadata, but it
    does not silently erase independent mail/calendar/history about the same person.

    Inventory, encounters and reminders still use source-specific historical semantics
    and are not inferred deleted merely because a bounded snapshot omits a row.
    """
    data = dict(snapshot or {})
    current_goal_ids = _ids(data.get("goals"))
    current_waiting_ids = _ids(data.get("waiting"))
    current_people_ids = _ids(data.get("people"))
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
        metadata = _safe_attributes(str(row["metadata_json"] or "{}"))
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

    revoked_people = _revoke_known_person_enrollment(current_people_ids)

    return {
        "retired_goals": retired_goals,
        "retired_waiting": retired_waiting,
        "revoked_known_people": revoked_people,
    }
