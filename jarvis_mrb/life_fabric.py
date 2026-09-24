from __future__ import annotations

"""Life Fabric: a user-directed, evidence-aware ledger for everyday friction.

No account, calendar, health, payment, household or person data is inferred.
No background acquisition, email sending, booking, spending or physical action.
This module gives existing Jarvis capabilities a common life-state interface.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from jarvis_mrb.world_model import DB_PATH

STORE = Path(DB_PATH).with_name("life_fabric.sqlite3")
KINDS = frozenset({"task", "asset", "handoff", "transition"})
DOMAINS = frozenset({
    "morning", "travel", "work", "food", "home", "shopping", "moving", "money",
    "relationships", "health", "digital", "vehicle", "recovery", "maintenance",
    "uncertainty", "opportunity", "other",
})
RECEIPT_SOURCES = frozenset({
    "user_confirmation", "provider_receipt", "sensor_readback", "document_evidence",
})
OUTCOMES = frozenset({"verified", "failed", "unknown"})
MAX_RECORDS = 500
MAX_FRICTION_EVENTS = 3000
MAX_CONTEXT = 1200
# A saved transition is a concrete checklist, not an assertion that any item
# has already been done. Templates are examples and not legal/medical advice.
TRANSITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "moving": (
        ("Confirm dates, keys and exact access arrangements", "moving"),
        ("Document condition of old and new homes", "moving"),
        ("Check movers, building access and any reservations", "moving"),
        ("Arrange utilities and internet for new home", "home"),
        ("Update address at accounts you select", "money"),
        ("Prepare first-night essentials and box inventory", "home"),
        ("Confirm old service cancellation and final bills", "money"),
        ("Track deposit and move-out completion evidence", "money"),
    ),
    "travel": (
        ("Verify tickets, traveler names and travel documents", "travel"),
        ("Check destination entry requirements from official sources", "travel"),
        ("Confirm seats, lodging and local transport", "travel"),
        ("Record departure lead time and packing essentials", "travel"),
        ("Arrange care for home, pets or dependents if needed", "home"),
        ("Prepare essential offline documents and addresses", "travel"),
        ("Check schedule changes and downstream commitments", "travel"),
        ("Verify return-home arrangements", "travel"),
    ),
    "new_job": (
        ("Review and confirm offer documents", "work"),
        ("Plan the old role handoff and final responsibilities", "work"),
        ("Verify start date and onboarding requirements", "work"),
        ("Review benefits and enrollment deadlines", "money"),
        ("Arrange commute and equipment readiness", "travel"),
        ("Check payroll and tax-form submission receipts", "money"),
        ("Update relevant professional contacts", "relationships"),
        ("Reconcile first-month obligations", "work"),
    ),
    "purchase": (
        ("Record exact requirements and compatibility", "shopping"),
        ("Confirm merchant, availability, budget and return terms", "shopping"),
        ("Review and authorize exact purchase separately", "shopping"),
        ("Verify order acceptance and delivery", "shopping"),
        ("Confirm correct item and usable condition", "shopping"),
        ("Save purchase evidence and applicable warranty", "maintenance"),
        ("Record setup or installation requirements", "home"),
        ("Track return deadline and final disposition", "shopping"),
    ),
    "vehicle": (
        ("Confirm exact vehicle and maintenance issue", "vehicle"),
        ("Retrieve relevant manual and service history", "vehicle"),
        ("Check applicable coverage and recall information", "vehicle"),
        ("Review estimate and authorize service separately", "vehicle"),
        ("Arrange transportation during service", "travel"),
        ("Track service status and pickup", "vehicle"),
        ("Verify the reported repair with appropriate evidence", "vehicle"),
        ("Record work performed and next interval", "maintenance"),
    ),
    "health_followup": (
        ("Record clinician-provided follow-up instructions", "health"),
        ("Identify referral and scheduling requirements", "health"),
        ("Confirm network or coverage details independently", "health"),
        ("Schedule the clinician-approved follow-up", "health"),
        ("Prepare relevant records and questions", "health"),
        ("Track pharmacy or test receipt when applicable", "health"),
        ("Record what the clinician actually recommended", "health"),
        ("Confirm completion with the appropriate care provider", "health"),
    ),
}


def _now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("Timezone-aware time required.")
    return value.astimezone(timezone.utc)


def _stamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid ISO timestamp.") from exc
    if result.tzinfo is None:
        raise ValueError("A deadline must include a timezone.")
    return result.astimezone(timezone.utc).isoformat()


def _text(value: Any, field: str, *, limit: int = 180, required: bool = True) -> str:
    clean = " ".join(str(value or "").split())
    if (required and not clean) or len(clean) > limit or any(ord(ch) < 32 for ch in clean):
        raise ValueError(f"Invalid {field}; maximum {limit} characters.")
    return clean


def _db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA secure_delete=ON")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute(
        """CREATE TABLE IF NOT EXISTS records(
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, domain TEXT NOT NULL,
          title TEXT NOT NULL, data_json TEXT NOT NULL,
          deadline_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          version INTEGER NOT NULL, retired_at TEXT,
          client_request_id TEXT UNIQUE
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS receipts(
          id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id),
          outcome TEXT NOT NULL, source_kind TEXT NOT NULL,
          evidence_ref TEXT NOT NULL, observed_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS friction(
          id TEXT PRIMARY KEY, friction_key TEXT NOT NULL,
          label TEXT NOT NULL, occurred_at TEXT NOT NULL
        )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS life_deadlines ON records(deadline_at)")
    con.execute("CREATE INDEX IF NOT EXISTS life_receipt_record ON receipts(record_id,observed_at)")
    con.execute("CREATE INDEX IF NOT EXISTS life_friction_key ON friction(friction_key,occurred_at)")
    return con


def _path(db_path: Path | None) -> Path:
    return Path(db_path) if db_path is not None else STORE


def _body(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["data_json"])


def _get(con: sqlite3.Connection, record_id: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    if row is None or row["retired_at"]:
        raise ValueError("Active record not found.")
    return row


def _receipts(con: sqlite3.Connection, record_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(
        """SELECT id,outcome,source_kind,evidence_ref,observed_at FROM receipts
           WHERE record_id=? ORDER BY observed_at DESC,rowid DESC LIMIT 20""",
        (record_id,),
    )]


def _state(kind: str, receipts: list[dict[str, Any]]) -> str:
    if kind != "task":
        return "recorded"
    if not receipts:
        return "not_verified"
    latest = receipts[0]
    if latest["outcome"] == "unknown":
        return "outcome_unknown"
    if latest["outcome"] == "failed":
        return "reported_failure"
    return {
        "user_confirmation": "user_confirmed",
        "provider_receipt": "provider_reported",
        "sensor_readback": "sensor_observed",
        "document_evidence": "document_supported",
    }[latest["source_kind"]]


def _entry(con: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    body = _body(row)
    receipts = _receipts(con, row["id"]) if row["kind"] == "task" else []
    return {
        "id": row["id"], "kind": row["kind"], "domain": row["domain"],
        "title": row["title"], "data": body, "deadline_at": row["deadline_at"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "version": row["version"], "retired_at": row["retired_at"],
        "completion_state": _state(row["kind"], receipts),
        "receipts": receipts[:3],
    }


def _make(con: sqlite3.Connection, *, kind: str, title: str, domain: str,
          data: dict[str, Any], deadline_at: str | None, now: str,
          client_request_id: str | None = None) -> str:
    record_id = uuid4().hex
    con.execute(
        """INSERT INTO records(id,kind,domain,title,data_json,deadline_at,
                  created_at,updated_at,version,client_request_id)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (record_id, kind, domain, title,
         json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
         deadline_at, now, now, 1, client_request_id),
    )
    return record_id


def create(
    kind: str, title: str, domain: str, *, description: str = "",
    deadline_at: str | None = None, next_step: str = "",
    depends_on: list[str] | None = None, quantity: float | None = None,
    location: str = "", source_ref: str = "",
    client_request_id: str | None = None,
    db_path: Path | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    if kind not in KINDS - {"transition"}:
        raise ValueError("Invalid record kind.")
    if domain not in DOMAINS:
        raise ValueError("Unknown life domain.")
    title = _text(title, "title")
    description = _text(description, "description", limit=MAX_CONTEXT, required=False)
    next_step = _text(next_step, "next step", required=False, limit=350)
    location = _text(location, "location", required=False)
    source_ref = _text(source_ref, "source reference", required=False, limit=350)
    req = _text(client_request_id, "request id", required=False, limit=100) or None
    deps = depends_on or []
    if kind == "task":
        if not isinstance(deps, list) or len(deps) > 12 or len(set(deps)) != len(deps):
            raise ValueError("Invalid dependencies.")
    elif deps:
        raise ValueError("Only tasks can depend on tasks.")
    if kind != "asset" and quantity is not None:
        raise ValueError("Only assets can have quantity.")
    if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not 0 <= quantity <= 1_000_000):
        raise ValueError("Invalid asset quantity.")
    deadline = _stamp(deadline_at)
    stamp = _now(now).isoformat()
    data = {
        "description": description, "next_step": next_step,
        "depends_on": deps, "quantity": quantity,
        "location": location, "source_ref": source_ref,
        "created_explicitly": True,
    }
    con = _db(_path(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        if req:
            existing = con.execute(
                "SELECT * FROM records WHERE client_request_id=?", (req,)
            ).fetchone()
            if existing:
                returned = _entry(con, existing)
                if (existing["kind"], existing["domain"], existing["title"],
                    existing["deadline_at"], _body(existing)) != (kind, domain, title, deadline, data):
                    raise ValueError("Request id reused with different content.")
                con.commit()
                return returned
        if con.execute("SELECT COUNT(*) FROM records WHERE retired_at IS NULL").fetchone()[0] >= MAX_RECORDS:
            raise ValueError("Life Fabric is full; retire old records before adding more.")
        for dep in deps:
            row = _get(con, str(dep))
            if row["kind"] != "task":
                raise ValueError("Dependencies must refer to existing tasks.")
        ident = _make(con, kind=kind, title=title, domain=domain, data=data,
                      deadline_at=deadline, now=stamp, client_request_id=req)
        result = _entry(con, _get(con, ident))
        con.commit()
        return result
    finally:
        con.close()


def list_records(*, kind: str | None = None, active_only: bool = True,
                 limit: int = 100, db_path: Path | None = None) -> dict[str, Any]:
    if kind is not None and kind not in KINDS:
        raise ValueError("Invalid record kind.")
    limit = max(1, min(int(limit), 200))
    con = _db(_path(db_path))
    try:
        conditions, values = [], []
        if kind is not None:
            conditions.append("kind=?")
            values.append(kind)
        if active_only:
            conditions.append("retired_at IS NULL")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = con.execute(
            "SELECT * FROM records" + where +
            " ORDER BY created_at DESC,rowid DESC LIMIT ?",
            (*values, limit),
        ).fetchall()
        return {
            "schema": "jarvis.life_fabric.records.v1",
            "records": [_entry(con, row) for row in rows],
            "truncated": len(rows) == limit,
            "external_actions": 0,
        }
    finally:
        con.close()


def receipt(record_id: str, *, outcome: str, source_kind: str, evidence_ref: str,
            expected_version: int, db_path: Path | None = None,
            now: datetime | None = None) -> dict[str, Any]:
    if outcome not in OUTCOMES or source_kind not in RECEIPT_SOURCES:
        raise ValueError("Unsupported outcome or evidence kind.")
    evidence = _text(evidence_ref, "evidence reference", limit=350)
    stamp = _now(now).isoformat()
    con = _db(_path(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        row = _get(con, record_id)
        if row["kind"] != "task":
            raise ValueError("Receipts are only accepted for tasks.")
        if row["version"] != expected_version:
            raise ValueError("Stale record version; refresh before another write.")
        con.execute(
            "INSERT INTO receipts(id,record_id,outcome,source_kind,evidence_ref,observed_at) VALUES(?,?,?,?,?,?)",
            (uuid4().hex, record_id, outcome, source_kind, evidence, stamp),
        )
        con.execute(
            "UPDATE records SET version=version+1,updated_at=? WHERE id=?",
            (stamp, record_id),
        )
        updated = _entry(con, _get(con, record_id))
        con.commit()
        return updated
    finally:
        con.close()


def retire(record_id: str, *, expected_version: int,
           db_path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    stamp = _now(now).isoformat()
    con = _db(_path(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        row = _get(con, record_id)
        if row["version"] != expected_version:
            raise ValueError("Stale record version; refresh before retiring.")
        con.execute(
            "UPDATE records SET version=version+1,retired_at=?,updated_at=? WHERE id=?",
            (stamp, stamp, record_id),
        )
        updated = _entry(con, con.execute(
            "SELECT * FROM records WHERE id=?", (record_id,)
        ).fetchone())
        con.commit()
        return updated
    finally:
        con.close()


def transition(template: str, title: str, *, client_request_id: str,
               db_path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    if template not in TRANSITIONS:
        raise ValueError("Unknown transition template.")
    title = _text(title, "transition title")
    req = _text(client_request_id, "request id", limit=100)
    stamp = _now(now).isoformat()
    con = _db(_path(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        existing = con.execute(
            "SELECT * FROM records WHERE client_request_id=?", (req,)
        ).fetchone()
        if existing:
            if (existing["kind"] != "transition"
                or _body(existing).get("template") != template
                or existing["title"] != title):
                raise ValueError("Request id reused with different transition.")
            parent_id = existing["id"]
            task_rows = con.execute(
                "SELECT * FROM records WHERE json_extract(data_json,'$.transition_id')=? ORDER BY created_at,rowid",
                (parent_id,),
            ).fetchall()
            con.commit()
            return {"transition": _entry(con, existing),
                    "tasks": [_entry(con, row) for row in task_rows], "replayed": True}
        if con.execute("SELECT COUNT(*) FROM records WHERE retired_at IS NULL").fetchone()[0] + len(TRANSITIONS[template]) + 1 > MAX_RECORDS:
            raise ValueError("Not enough record capacity for transition.")
        parent_id = _make(
            con, kind="transition", title=title, domain="moving" if template == "moving" else
                "health" if template == "health_followup" else
                "vehicle" if template == "vehicle" else
                "travel" if template == "travel" else
                "work" if template == "new_job" else "shopping",
            data={"template": template, "created_explicitly": True},
            deadline_at=None, now=stamp, client_request_id=req,
        )
        tasks = []
        for label, domain in TRANSITIONS[template]:
            ident = _make(
                con, kind="task", title=label, domain=domain,
                data={"description": "", "next_step": "",
                      "depends_on": [], "transition_id": parent_id,
                      "created_explicitly": True},
                deadline_at=None, now=stamp,
            )
            tasks.append(_entry(con, _get(con, ident)))
        parent = _entry(con, _get(con, parent_id))
        con.commit()
        return {"transition": parent, "tasks": tasks, "replayed": False}
    finally:
        con.close()


def _date_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def readiness(*, db_path: Path | None = None,
              now: datetime | None = None) -> dict[str, Any]:
    """Evaluate ONLY user-enrolled records, never pretend an empty ledger is ready."""
    instant = _now(now)
    con = _db(_path(db_path))
    try:
        records = [
            _entry(con, row) for row in con.execute(
                "SELECT * FROM records WHERE retired_at IS NULL ORDER BY created_at,rowid"
            )
        ]
    finally:
        con.close()
    tasks = {row["id"]: row for row in records if row["kind"] == "task"}
    satisfied = {"user_confirmed", "provider_reported", "sensor_observed", "document_supported"}
    due: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in tasks.values():
        if item["completion_state"] in satisfied:
            continue
        missing = [
            dep for dep in item["data"].get("depends_on", [])
            if dep not in tasks or tasks[dep]["completion_state"] not in satisfied
        ]
        if missing:
            blocked.append({"id": item["id"], "title": item["title"],
                            "blocking_task_ids": missing})
        deadline = item["deadline_at"]
        if deadline:
            seconds = (_date_utc(deadline) - instant).total_seconds()
            if seconds <= 7 * 86400:
                due.append({
                    "id": item["id"], "title": item["title"],
                    "deadline_at": deadline,
                    "due_state": "overdue" if seconds < 0 else
                        "next_24h" if seconds <= 86400 else "next_7d",
                    "completion_state": item["completion_state"],
                    "blocked": bool(missing),
                })
    due.sort(key=lambda row: row["deadline_at"])
    return {
        "schema": "jarvis.life_fabric.readiness.v1",
        "checked_at": instant.isoformat(), "model_calls": 0,
        "external_actions": 0, "monitoring": "on_request",
        "coverage": "user_enrolled_records_only",
        "records_total": len(records), "tasks_total": len(tasks),
        "due": due[:60], "blocked": blocked[:60],
        "unknown": [x["id"] for x in tasks.values()
                    if x["completion_state"] == "outcome_unknown"][:60],
        "setup_required": not records,
        "all_clear": False if not tasks else not due and not blocked,
        "all_clear_qualifier": "Only enrolled deadlines and dependencies; not an all-life safety clearance.",
    }


def handoff(title: str, summary: str, next_step: str,
            linked_ids: list[str], *, client_request_id: str,
            db_path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(linked_ids, list) or len(linked_ids) > 12 or len(set(linked_ids)) != len(linked_ids):
        raise ValueError("Invalid handoff links.")
    title = _text(title, "title")
    summary = _text(summary, "summary", limit=MAX_CONTEXT)
    next_step = _text(next_step, "next step", limit=350)
    req = _text(client_request_id, "request id", limit=100)
    stamp = _now(now).isoformat()
    con = _db(_path(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        for linked in linked_ids:
            _get(con, linked)
        data = {
            "description": summary, "next_step": next_step,
            "linked_ids": linked_ids, "created_explicitly": True,
        }
        old = con.execute(
            "SELECT * FROM records WHERE client_request_id=?", (req,)
        ).fetchone()
        if old:
            if old["kind"] != "handoff" or old["title"] != title or _body(old) != data:
                raise ValueError("Request id reused with different handoff.")
            response = _entry(con, old)
            con.commit()
            return response
        if con.execute("SELECT COUNT(*) FROM records WHERE retired_at IS NULL").fetchone()[0] >= MAX_RECORDS:
            raise ValueError("Life Fabric is full.")
        ident = _make(con, kind="handoff", title=title, domain="work",
                      data=data, deadline_at=None, now=stamp, client_request_id=req)
        result = _entry(con, _get(con, ident))
        con.commit()
        return result
    finally:
        con.close()


def resume(handoff_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    con = _db(_path(db_path))
    try:
        record = _get(con, handoff_id)
        if record["kind"] != "handoff":
            raise ValueError("Not a handoff record.")
        handoff_row = _entry(con, record)
        linked = []
        for ident in handoff_row["data"].get("linked_ids", []):
            try:
                linked.append(_entry(con, _get(con, ident)))
            except ValueError:
                linked.append({"id": ident, "availability": "retired_or_missing"})
        return {
            "schema": "jarvis.life_fabric.handoff.v1",
            "handoff": handoff_row, "linked_records": linked,
            "external_actions": 0,
            "note": "A restore packet, not a remote app or physical action.",
        }
    finally:
        con.close()


def friction(label: str, *, occurred_at: str | None = None,
             db_path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    label = _text(label, "friction label")
    key = re.sub(r"\s+", " ", label.casefold())
    instant = _now(now)
    happened = _stamp(occurred_at) or instant.isoformat()
    if _date_utc(happened) > instant + timedelta(seconds=30):
        raise ValueError("Cannot log a future inconvenience.")
    if _date_utc(happened) < instant - timedelta(days=30):
        raise ValueError("Only the preceding 30 days are supported.")
    cutoff = (instant - timedelta(days=30)).isoformat()
    con = _db(_path(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM friction WHERE occurred_at<?", (cutoff,))
        ident = uuid4().hex
        con.execute(
            "INSERT INTO friction(id,friction_key,label,occurred_at) VALUES(?,?,?,?)",
            (ident, key, label, happened),
        )
        con.execute(
            """DELETE FROM friction WHERE id IN (
                  SELECT id FROM friction ORDER BY occurred_at DESC,rowid DESC
                  LIMIT -1 OFFSET ?)""",
            (MAX_FRICTION_EVENTS,),
        )
        counts = con.execute(
            "SELECT occurred_at FROM friction WHERE friction_key=?", (key,)
        ).fetchall()
        con.commit()
        distinct_days = len({row["occurred_at"][:10] for row in counts})
        return {
            "id": ident, "label": label, "occurrences_30d": len(counts),
            "distinct_utc_days": distinct_days,
            "candidate_repeated_friction": distinct_days >= 3,
            "suggestion": "Review this recurring inconvenience; ask before automating or changing routines."
                          if distinct_days >= 3 else None,
            "external_actions": 0,
        }
    finally:
        con.close()


def friction_candidates(*, db_path: Path | None = None,
                        now: datetime | None = None) -> dict[str, Any]:
    cutoff = (_now(now) - timedelta(days=30)).isoformat()
    con = _db(_path(db_path))
    try:
        rows = con.execute(
            """SELECT friction_key,MAX(label) AS label,COUNT(*) AS occurrences,
                      COUNT(DISTINCT substr(occurred_at,1,10)) AS days
               FROM friction WHERE occurred_at>=?
               GROUP BY friction_key HAVING days>=3 ORDER BY days DESC,occurrences DESC
               LIMIT 30""", (cutoff,),
        ).fetchall()
        return {
            "schema": "jarvis.life_fabric.friction.v1",
            "candidates": [dict(x) for x in rows],
            "basis": "explicitly logged incidents on at least three distinct UTC days within 30 days",
            "automation_authority": "none",
        }
    finally:
        con.close()


def simulate_minutes(*, activity_minutes: int, days: int,
                     daily_free_minutes: int,
                     db_path: Path | None = None) -> dict[str, Any]:
    """Bounded arithmetic what-if: user-supplied free time, NOT a calendar model."""
    if any(type(value) is not int for value in (activity_minutes, days, daily_free_minutes)):
        raise ValueError("What-if inputs must be integers.")
    if not 0 <= activity_minutes <= 10080 or not 1 <= days <= 31 or not 0 <= daily_free_minutes <= 1440:
        raise ValueError("What-if inputs outside bounded range.")
    available = days * daily_free_minutes
    return {
        "schema": "jarvis.life_fabric.what_if.v1",
        "assumptions": {
            "activity_minutes": activity_minutes, "days": days,
            "daily_free_minutes": daily_free_minutes,
            "source": "user_provided_not_calendar_verified",
        },
        "available_minutes": available,
        "remaining_minutes": available - activity_minutes,
        "fits_assumed_time_budget": activity_minutes <= available,
        "calendar_conflicts_checked": False,
        "travel_and_dependencies_checked": False,
        "forecast": False,
        "external_actions": 0,
    }


def capabilities() -> dict[str, Any]:
    """Advertise implementation levels so roadmap is never mistaken for access."""
    return {
        "schema": "jarvis.life_fabric.capabilities.v1",
        "mode": "explicit_user_entry_and_on_request_analysis",
        "implemented": [
            "timezone_aware_due_windows", "dependency_readiness",
            "source_qualified_completion_receipts", "version_guarded_updates",
            "asset_inventory_manual", "work_restore_packets", "explicit_friction_candidates",
            "bounded_time_budget_arithmetic", "six_user_enrolled_transition_checklists",
            "authenticated_read_write_api",
        ],
        "existing_separate_integrations": [
            "gated_gmail_calendar", "reality_graph", "reality_lens",
            "mission_control", "paired_device_mesh", "consented_meeting_capture",
        ],
        "not_implemented": [
            "automatic_financial_or_medical_data_ingest",
            "universal_account_access", "autonomous_purchasing",
            "automated_household_inventory", "universal_remote_input",
            "background_behavior_surveillance", "independent_physical_completion_proof",
            "universal_context_handoff_across_external_apps",
            "genuine_future_prediction", "robotic_telepresence",
        ],
        "external_actions": 0,
    }
