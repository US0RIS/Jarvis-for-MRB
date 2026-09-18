from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from jarvis_mrb.world_model import DB_PATH


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(str(raw or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agency_decision_cases (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            selected_branch_id TEXT NOT NULL DEFAULT '',
            selection_rationale TEXT NOT NULL DEFAULT '',
            change_conditions_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            selected_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agency_decision_cases
            ON agency_decision_cases(status,updated_at DESC);

        CREATE TABLE IF NOT EXISTS agency_decision_branches (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES agency_decision_cases(id) ON DELETE CASCADE,
            branch_key TEXT NOT NULL,
            title TEXT NOT NULL,
            plan_json TEXT NOT NULL DEFAULT '{}',
            assumptions_json TEXT NOT NULL DEFAULT '[]',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            expected_outcomes_json TEXT NOT NULL DEFAULT '[]',
            cost_json TEXT NOT NULL DEFAULT '{}',
            reversibility REAL NOT NULL DEFAULT 0.5,
            uncertainty REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'candidate',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(case_id,branch_key)
        );
        CREATE INDEX IF NOT EXISTS idx_agency_decision_branches
            ON agency_decision_branches(case_id,status,branch_key);
        """
    )
    conn.commit()
    return conn


def _validate_branch(raw: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Counterfactual branches must be objects.")
    key = str(raw.get("id") or raw.get("key") or f"branch-{index}").strip()
    title = " ".join(str(raw.get("title") or key).split())[:1000]
    if not key or not title:
        raise ValueError("Counterfactual branch requires a key and title.")
    assumptions = raw.get("assumptions") if isinstance(raw.get("assumptions"), list) else []
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
    outcomes = raw.get("expected_outcomes") if isinstance(raw.get("expected_outcomes"), list) else []
    cost = raw.get("cost") if isinstance(raw.get("cost"), dict) else {}
    try:
        reversibility = max(0.0, min(float(raw.get("reversibility", 0.5)), 1.0))
    except (TypeError, ValueError):
        reversibility = 0.5
    try:
        uncertainty = max(0.0, min(float(raw.get("uncertainty", 0.5)), 1.0))
    except (TypeError, ValueError):
        uncertainty = 0.5
    return {
        "key": key[:200],
        "title": title,
        "plan": dict(raw.get("plan") or {}) if isinstance(raw.get("plan"), dict) else {},
        "assumptions": [str(item)[:1500] for item in assumptions[:30]],
        "evidence": [item for item in evidence[:50]],
        "expected_outcomes": [item for item in outcomes[:30]],
        "cost": cost,
        "reversibility": reversibility,
        "uncertainty": uncertainty,
    }


def create_case(
    question: str,
    branches: list[dict[str, Any]],
    *,
    context: str = "",
) -> dict[str, Any]:
    clean_question = " ".join(str(question or "").split())[:3000]
    if not clean_question:
        raise ValueError("Decision case question is empty.")
    if not isinstance(branches, list) or len(branches) < 2:
        raise ValueError("Counterfactual decision case requires at least two branches.")
    if len(branches) > 20:
        raise ValueError("Counterfactual decision case supports at most 20 branches.")

    normalized = [_validate_branch(branch, index) for index, branch in enumerate(branches, start=1)]
    keys = [branch["key"] for branch in normalized]
    if len(set(keys)) != len(keys):
        raise ValueError("Counterfactual branch keys must be unique.")

    case_id = f"decision-case:{uuid.uuid4()}"
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_decision_cases(id,question,context,status,created_at,updated_at)
            VALUES(?,?,?,'open',?,?)
            """,
            (case_id, clean_question, str(context or "")[:12000], now, now),
        )
        for branch in normalized:
            branch_id = f"decision-branch:{uuid.uuid4()}"
            conn.execute(
                """
                INSERT INTO agency_decision_branches(
                    id,case_id,branch_key,title,plan_json,assumptions_json,evidence_json,
                    expected_outcomes_json,cost_json,reversibility,uncertainty,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'candidate',?,?)
                """,
                (
                    branch_id,
                    case_id,
                    branch["key"],
                    branch["title"],
                    json.dumps(branch["plan"], ensure_ascii=False, sort_keys=True),
                    json.dumps(branch["assumptions"], ensure_ascii=False, sort_keys=True),
                    json.dumps(branch["evidence"], ensure_ascii=False, sort_keys=True),
                    json.dumps(branch["expected_outcomes"], ensure_ascii=False, sort_keys=True),
                    json.dumps(branch["cost"], ensure_ascii=False, sort_keys=True),
                    branch["reversibility"],
                    branch["uncertainty"],
                    now,
                    now,
                ),
            )
        conn.commit()

    try:
        from jarvis_mrb.world_model import record_event
        record_event(
            "agency.counterfactual.created",
            f"Counterfactual decision case created: {clean_question}",
            source_kind="jarvis_agency",
            source_ref=case_id,
            occurred_at=now,
            payload={"case_id": case_id, "branch_count": len(normalized)},
            evidence="Multiple candidate branches persisted before selection.",
            confidence=1.0,
        )
    except Exception:
        pass
    return get_case(case_id) or {}


def _branch_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "case_id": str(row["case_id"]),
        "key": str(row["branch_key"]),
        "title": str(row["title"]),
        "plan": dict(_loads(str(row["plan_json"]), {})),
        "assumptions": list(_loads(str(row["assumptions_json"]), [])),
        "evidence": list(_loads(str(row["evidence_json"]), [])),
        "expected_outcomes": list(_loads(str(row["expected_outcomes_json"]), [])),
        "cost": dict(_loads(str(row["cost_json"]), {})),
        "reversibility": float(row["reversibility"]),
        "uncertainty": float(row["uncertainty"]),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_case(case_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM agency_decision_cases WHERE id=?", (str(case_id),)).fetchone()
        if row is None:
            return None
        branches = conn.execute(
            "SELECT * FROM agency_decision_branches WHERE case_id=? ORDER BY branch_key",
            (str(case_id),),
        ).fetchall()
    return {
        "id": str(row["id"]),
        "question": str(row["question"]),
        "context": str(row["context"]),
        "status": str(row["status"]),
        "selected_branch_id": str(row["selected_branch_id"] or ""),
        "selection_rationale": str(row["selection_rationale"] or ""),
        "change_conditions": list(_loads(str(row["change_conditions_json"]), [])),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "selected_at": str(row["selected_at"] or ""),
        "branches": [_branch_from_row(branch) for branch in branches],
    }


def select_branch(
    case_id: str,
    branch: str,
    *,
    rationale: str,
    change_conditions: list[str] | None = None,
) -> dict[str, Any]:
    case = get_case(str(case_id))
    if case is None:
        raise ValueError(f"Unknown decision case {case_id!r}.")
    matches = [
        item for item in case["branches"]
        if str(item["id"]) == str(branch) or str(item["key"]) == str(branch)
    ]
    if len(matches) != 1:
        raise ValueError("Decision branch could not be uniquely identified.")
    selected = matches[0]
    clean_rationale = " ".join(str(rationale or "").split())[:4000]
    if not clean_rationale:
        raise ValueError("Selecting a counterfactual branch requires an explicit rationale.")
    conditions = [
        " ".join(str(item or "").split())[:1500]
        for item in (change_conditions or [])[:30]
        if " ".join(str(item or "").split())
    ]
    if not conditions:
        raise ValueError(
            "Selecting a counterfactual branch requires at least one explicit condition "
            "that would change or reopen the choice."
        )
    now = _now()

    with _connect() as conn:
        conn.execute(
            "UPDATE agency_decision_branches SET status='candidate',updated_at=? WHERE case_id=?",
            (now, str(case_id)),
        )
        conn.execute(
            "UPDATE agency_decision_branches SET status='selected',updated_at=? WHERE id=?",
            (now, str(selected["id"])),
        )
        conn.execute(
            """
            UPDATE agency_decision_cases
            SET status='selected',selected_branch_id=?,selection_rationale=?,
                change_conditions_json=?,selected_at=?,updated_at=?
            WHERE id=?
            """,
            (
                str(selected["id"]),
                clean_rationale,
                json.dumps(conditions, ensure_ascii=False, sort_keys=True),
                now,
                now,
                str(case_id),
            ),
        )
        conn.commit()

    try:
        from jarvis_mrb.world_model import record_event
        record_event(
            "agency.counterfactual.selected",
            f"Selected counterfactual branch {selected['title']}: {clean_rationale[:1000]}",
            source_kind="jarvis_agency",
            source_ref=f"{case_id}:{selected['id']}",
            occurred_at=now,
            payload={
                "case_id": str(case_id),
                "selected_branch_id": str(selected["id"]),
                "selected_branch_key": str(selected["key"]),
                "change_conditions": conditions,
            },
            evidence="Selection preserved all non-selected branches and explicit change conditions.",
            confidence=1.0,
        )
    except Exception:
        pass
    return get_case(str(case_id)) or {}


def comparison(case_id: str) -> dict[str, Any]:
    case = get_case(str(case_id))
    if case is None:
        raise ValueError(f"Unknown decision case {case_id!r}.")
    return {
        "question": case["question"],
        "status": case["status"],
        "selected_branch_id": case["selected_branch_id"],
        "selection_rationale": case["selection_rationale"],
        "change_conditions": case["change_conditions"],
        "branches": [
            {
                "id": branch["id"],
                "key": branch["key"],
                "title": branch["title"],
                "assumptions": branch["assumptions"],
                "evidence": branch["evidence"],
                "expected_outcomes": branch["expected_outcomes"],
                "cost": branch["cost"],
                "reversibility": branch["reversibility"],
                "uncertainty": branch["uncertainty"],
                "status": branch["status"],
            }
            for branch in case["branches"]
        ],
    }


def status() -> dict[str, Any]:
    with _connect() as conn:
        counts = {
            str(row["status"]): int(row["count"])
            for row in conn.execute(
                "SELECT status,COUNT(*) AS count FROM agency_decision_cases GROUP BY status"
            ).fetchall()
        }
    return {"ready": True, "cases": counts}
