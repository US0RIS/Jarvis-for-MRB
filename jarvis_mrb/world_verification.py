from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any

from jarvis_mrb.permissions import decide as permission_decision
from jarvis_mrb.world_model import DB_PATH

_TERMINAL = {"verified", "failed", "timed_out", "unverified", "superseded"}
_SENSITIVE_ARG_KEYS = {"body", "code", "command", "input", "api_spec", "arguments"}


def _now_dt() -> datetime:
    return datetime.now().astimezone()


def _now() -> str:
    return _now_dt().isoformat()


def _parse_time(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.astimezone()
        return value.astimezone()
    except (TypeError, ValueError, OverflowError):
        return None


def _loads(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in dict(args or {}).items():
        lowered = str(key).lower()
        if lowered.startswith("_world_"):
            continue
        if lowered in _SENSITIVE_ARG_KEYS:
            safe[str(key)] = "<redacted>"
        elif isinstance(value, str):
            safe[str(key)] = value[:1000]
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[str(key)] = value
        elif isinstance(value, list):
            safe[str(key)] = [str(item)[:300] for item in value[:20]]
        else:
            safe[str(key)] = str(value)[:1000]
    return safe


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS action_verifications (
            id TEXT PRIMARY KEY,
            action_event_id INTEGER NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
            executive_decision_id TEXT NOT NULL DEFAULT '',
            agency_step_id TEXT NOT NULL DEFAULT '',
            tool TEXT NOT NULL,
            arguments_json TEXT NOT NULL,
            verifier TEXT NOT NULL,
            expected_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_check_at TEXT,
            deadline_at TEXT,
            last_checked_at TEXT,
            last_evidence TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_action_verifications_due
            ON action_verifications(status,next_check_at,deadline_at);
        CREATE INDEX IF NOT EXISTS idx_action_verifications_decision
            ON action_verifications(executive_decision_id,status,updated_at DESC);

        CREATE TABLE IF NOT EXISTS verification_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verification_id TEXT NOT NULL REFERENCES action_verifications(id) ON DELETE CASCADE,
            observed_at TEXT NOT NULL,
            outcome TEXT NOT NULL,
            evidence TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_verification_observations_verification
            ON verification_observations(verification_id,id DESC);
        """
    )
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(action_verifications)").fetchall()}
    if "agency_step_id" not in columns:
        conn.execute("ALTER TABLE action_verifications ADD COLUMN agency_step_id TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_verifications_agency_step "
        "ON action_verifications(agency_step_id,status,updated_at DESC)"
    )
    conn.commit()
    return conn


def _reply_data(reply: Any) -> dict[str, Any]:
    value = getattr(reply, "data", None)
    return dict(value) if isinstance(value, dict) else {}


def _extract_int(message: str, pattern: str) -> int | None:
    match = re.search(pattern, str(message or ""), flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _plan(tool: str, args: dict[str, Any], reply: Any) -> dict[str, Any]:
    ok = bool(getattr(reply, "ok", False))
    message = str(getattr(reply, "message", "") or "")
    data = _reply_data(reply)
    now = _now_dt()

    if not ok:
        return {
            "verifier": "tool_return",
            "expected": {"tool_ok": True},
            "status": "failed",
            "next_check_at": None,
            "deadline_at": now.isoformat(),
            "evidence": f"Tool returned failure: {message[:1200]}",
        }

    risk = str(permission_decision(tool).risk)
    if risk == "read":
        return {
            "verifier": "return_value",
            "expected": {"observation_returned": True},
            "status": "verified",
            "next_check_at": None,
            "deadline_at": now.isoformat(),
            "evidence": "Read-only action returned successfully; its return value is the requested observation.",
        }

    if tool == "gmail.send":
        # AgentReply currently may not preserve GoogleResult.data. The causal Gmail
        # search boundary prevents an earlier message to the same recipient/subject
        # from falsely verifying this send; exact message ID wins when available.
        expected = {
            "message_id": str(data.get("message_id") or ""),
            "recipient": str(data.get("email") or args.get("recipient") or "").strip().lower(),
            "subject": str(args.get("subject") or "").strip(),
            "not_before_unix": int((now - timedelta(seconds=10)).timestamp()),
        }
        return {
            "verifier": "gmail_sent_message",
            "expected": expected,
            "status": "pending",
            "next_check_at": (now + timedelta(seconds=5)).isoformat(),
            "deadline_at": (now + timedelta(minutes=10)).isoformat(),
            "evidence": "Gmail send API accepted the message; waiting for causally bounded Sent Mail read-back.",
        }

    if tool == "calendar.create":
        expected = {
            "event_id": str(data.get("event_id") or ""),
            "summary": str(args.get("summary") or "").strip(),
            "start": str(args.get("start") or "").strip(),
            "end": str(args.get("end") or "").strip(),
        }
        return {
            "verifier": "calendar_event_exists",
            "expected": expected,
            "status": "pending",
            "next_check_at": (now + timedelta(seconds=5)).isoformat(),
            "deadline_at": (now + timedelta(minutes=10)).isoformat(),
            "evidence": "Calendar create API accepted the event; waiting for independent calendar read-back.",
        }

    if tool in {"pc.launch_app", "smart.open"}:
        return {
            "verifier": "app_or_tab_present" if tool == "smart.open" else "app_present",
            "expected": {"name": str(args.get("name") or "").strip()},
            "status": "pending",
            "next_check_at": (now + timedelta(seconds=2)).isoformat(),
            "deadline_at": (now + timedelta(minutes=2)).isoformat(),
            "evidence": "Launch request completed; waiting for observed running/open state.",
        }

    if tool in {"pc.close_app", "smart.close"}:
        return {
            "verifier": "app_or_tab_absent" if tool == "smart.close" else "app_absent",
            "expected": {"name": str(args.get("name") or "").strip()},
            "status": "pending",
            "next_check_at": (now + timedelta(seconds=2)).isoformat(),
            "deadline_at": (now + timedelta(minutes=2)).isoformat(),
            "evidence": "Close request completed; waiting for observed closed state.",
        }

    if tool in {"pc.launch_minecraft", "pc.ensure_minecraft_running"}:
        return {
            "verifier": "minecraft_running",
            "expected": {"running": True},
            "status": "pending",
            "next_check_at": (now + timedelta(seconds=3)).isoformat(),
            "deadline_at": (now + timedelta(minutes=3)).isoformat(),
            "evidence": "Minecraft launch request completed; waiting for process observation.",
        }

    if tool in {"browser.open_site", "browser.focus_tab"}:
        return {
            "verifier": "browser_tab_present",
            "expected": {"query": str(args.get("query") or "").strip()},
            "status": "pending",
            "next_check_at": (now + timedelta(seconds=2)).isoformat(),
            "deadline_at": (now + timedelta(minutes=2)).isoformat(),
            "evidence": "Browser action completed; waiting for matching tab observation.",
        }

    if tool == "browser.close_tab":
        return {
            "verifier": "browser_tab_absent",
            "expected": {"query": str(args.get("query") or "").strip()},
            "status": "pending",
            "next_check_at": (now + timedelta(seconds=2)).isoformat(),
            "deadline_at": (now + timedelta(minutes=2)).isoformat(),
            "evidence": "Browser close request completed; waiting for matching tab to disappear.",
        }

    if tool == "state.update":
        return {
            "verifier": "persistent_state_value",
            "expected": {"key": str(args.get("key") or ""), "value": args.get("value")},
            "status": "pending",
            "next_check_at": now.isoformat(),
            "deadline_at": (now + timedelta(minutes=1)).isoformat(),
            "evidence": "Persistent-state write returned successfully; waiting for independent read-back.",
        }

    if tool == "state.temp_set":
        return {
            "verifier": "temporary_state_value",
            "expected": {"key": str(args.get("key") or ""), "value": args.get("value")},
            "status": "pending",
            "next_check_at": now.isoformat(),
            "deadline_at": (now + timedelta(minutes=1)).isoformat(),
            "evidence": "Temporary-state write returned successfully; waiting for independent read-back.",
        }

    if tool in {"jobs.create_time", "jobs.create_recurring", "jobs.create_event"}:
        job_id = _extract_int(message, r"created(?: recurring)? job\s+(\d+)")
        return {
            "verifier": "job_active" if job_id is not None else "no_independent_verifier",
            "expected": {"job_id": job_id},
            "status": "pending" if job_id is not None else "unverified",
            "next_check_at": now.isoformat() if job_id is not None else None,
            "deadline_at": (now + timedelta(minutes=1)).isoformat(),
            "evidence": "Scheduler accepted the job; waiting for active-job read-back." if job_id is not None else "Scheduler returned success but no stable job identifier was available for read-back.",
        }

    if tool == "jobs.cancel":
        return {
            "verifier": "job_inactive",
            "expected": {"job_id": int(args.get("job_id") or 0)},
            "status": "pending",
            "next_check_at": now.isoformat(),
            "deadline_at": (now + timedelta(minutes=1)).isoformat(),
            "evidence": "Scheduler accepted cancellation; waiting for active-job read-back.",
        }

    if tool == "background.submit":
        task_id = _extract_int(message, r"background task\s+(\d+)\s+started")
        return {
            "verifier": "background_terminal" if task_id is not None else "no_independent_verifier",
            "expected": {"task_id": task_id},
            "status": "pending" if task_id is not None else "unverified",
            "next_check_at": (now + timedelta(seconds=10)).isoformat() if task_id is not None else None,
            "deadline_at": (now + timedelta(hours=2)).isoformat(),
            "evidence": "Background task was accepted; completion, failure, or cancellation remains unresolved." if task_id is not None else "Background task returned success but no stable task identifier was available for verification.",
        }

    return {
        "verifier": "no_independent_verifier",
        "expected": {"tool": tool},
        "status": "unverified",
        "next_check_at": None,
        "deadline_at": now.isoformat(),
        "evidence": "Tool returned success, but Jarvis has no independent observer for this effect. Success is not inferred from the tool receipt.",
    }


def _decision_context(decision_id: str) -> tuple[str, list[str]]:
    if not decision_id:
        return ("", [])
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT intention_id FROM executive_decisions WHERE id=?",
                (decision_id,),
            ).fetchone()
            if row is None:
                return ("", [])
            intention_id = str(row["intention_id"])
            title_row = conn.execute("SELECT title FROM intentions WHERE id=?", (intention_id,)).fetchone()
            title = str(title_row["title"] or "") if title_row else ""
            project_rows = conn.execute(
                """
                SELECT e.canonical_name
                FROM intention_entities ie JOIN entities e ON e.id=ie.entity_id
                WHERE ie.intention_id=? AND ie.role='project'
                ORDER BY ie.confidence DESC
                """,
                (intention_id,),
            ).fetchall()
            projects = [str(item["canonical_name"]) for item in project_rows]
            return (title, projects[:5])
    except sqlite3.OperationalError:
        return ("", [])


def _record_world_transition(
    verification_id: str,
    *,
    status: str,
    tool: str,
    evidence: str,
    action_event_id: int,
    executive_decision_id: str,
) -> int | None:
    try:
        from jarvis_mrb.world_model import record_event

        objective, projects = _decision_context(executive_decision_id)
        context = f" for {objective}" if objective else ""
        project_text = f" ({', '.join(projects)})" if projects else ""
        event_id = record_event(
            f"verification.{status}",
            f"Action verification {status}: {tool}{context}{project_text}. {evidence[:1200]}",
            source_kind="jarvis_verifier",
            source_ref=verification_id,
            payload={
                "verification_id": verification_id,
                "action_event_id": int(action_event_id),
                "executive_decision_id": executive_decision_id,
                "tool": tool,
                "status": status,
                "objective": objective,
                "projects": projects,
            },
            evidence="Closed-loop verification state derived from an independent observer when available.",
            confidence=1.0 if status in {"verified", "failed"} else 0.9,
        )
        try:
            from jarvis_mrb.world_linker import link_event

            link_event(event_id)
        except Exception:
            pass
        return int(event_id)
    except Exception:
        return None


def register_execution(
    tool: str,
    args: dict[str, Any],
    reply: Any,
    *,
    action_event_id: int,
    executive_decision_id: str = "",
    agency_step_id: str = "",
) -> str:
    plan = _plan(str(tool), dict(args or {}), reply)
    verification_id = f"verification:{uuid.uuid4()}"
    now = _now()
    safe_args = _safe_args(args)
    status = str(plan["status"])
    evidence = str(plan.get("evidence") or "")[:3000]

    with _connect() as conn:
        if executive_decision_id:
            conn.execute(
                """
                UPDATE action_verifications
                SET status='superseded',updated_at=?
                WHERE executive_decision_id=? AND tool=?
                  AND status IN ('pending','failed','timed_out','unverified')
                """,
                (now, executive_decision_id, str(tool)),
            )
        conn.execute(
            """
            INSERT INTO action_verifications(
                id,action_event_id,executive_decision_id,agency_step_id,tool,arguments_json,verifier,expected_json,
                status,attempts,next_check_at,deadline_at,last_checked_at,last_evidence,last_error,
                created_at,updated_at,resolved_event_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
            """,
            (
                verification_id,
                int(action_event_id),
                str(executive_decision_id or ""),
                str(agency_step_id or ""),
                str(tool),
                json.dumps(safe_args, ensure_ascii=False, sort_keys=True),
                str(plan["verifier"]),
                json.dumps(plan["expected"], ensure_ascii=False, sort_keys=True),
                status,
                0,
                plan.get("next_check_at"),
                plan.get("deadline_at"),
                now if status in _TERMINAL else None,
                evidence,
                "",
                now,
                now,
            ),
        )
        conn.commit()

    event_id = _record_world_transition(
        verification_id,
        status=status,
        tool=str(tool),
        evidence=evidence,
        action_event_id=int(action_event_id),
        executive_decision_id=str(executive_decision_id or ""),
    )
    if event_id is not None:
        with _connect() as conn:
            conn.execute(
                "UPDATE action_verifications SET resolved_event_id=? WHERE id=?",
                (event_id, verification_id),
            )
            conn.commit()
    return verification_id


def _gmail_observation(expected: dict[str, Any]) -> tuple[str, str]:
    from jarvis_mrb.tools.google import query_emails

    recipient = str(expected.get("recipient") or "").strip().lower()
    subject = str(expected.get("subject") or "").strip()
    message_id = str(expected.get("message_id") or "").strip()
    try:
        not_before_unix = int(expected.get("not_before_unix") or 0)
    except (TypeError, ValueError):
        not_before_unix = 0

    query = "in:sent"
    if not_before_unix > 0:
        query += f" after:{not_before_unix}"
    else:
        # Older rows created before causal-boundary support remain conservative.
        query += " newer_than:1d"
    if recipient:
        query += f" to:{recipient}"
    if subject:
        escaped = subject.replace('"', "")[:160]
        query += f' subject:"{escaped}"'

    result = query_emails(query=query, limit=10)
    if not result.ok:
        raise RuntimeError(result.message)
    emails = list((result.data or {}).get("emails") or [])
    if message_id:
        if any(str(item.get("id") or "") == message_id for item in emails if isinstance(item, dict)):
            return ("verified", f"Sent Mail contains Gmail message {message_id} inside the causal verification window.")
        return ("pending", f"Gmail message {message_id} is not visible in the causally bounded Sent Mail query yet.")
    if emails:
        return ("verified", "Sent Mail contains a recipient/subject match created after this action was attempted.")
    return ("pending", "No causally valid Sent Mail match is visible yet.")


def _calendar_observation(expected: dict[str, Any]) -> tuple[str, str]:
    from jarvis_mrb.tools.google import query_calendar_events

    summary = str(expected.get("summary") or "").strip()
    start = str(expected.get("start") or "").strip()
    end = str(expected.get("end") or "").strip()
    event_id = str(expected.get("event_id") or "").strip()
    start_dt = _parse_time(start)
    end_dt = _parse_time(end)
    time_min = (start_dt - timedelta(hours=1)).isoformat() if start_dt else None
    time_max = (end_dt + timedelta(hours=1)).isoformat() if end_dt else None
    result = query_calendar_events(
        direction="future",
        days=365,
        limit=20,
        query=summary or None,
        start=time_min,
        end=time_max,
    )
    if not result.ok:
        raise RuntimeError(result.message)
    events = list((result.data or {}).get("events") or [])
    if event_id and any(str(item.get("id") or "") == event_id for item in events if isinstance(item, dict)):
        return ("verified", f"Calendar read-back contains event {event_id}.")
    for item in events:
        if not isinstance(item, dict):
            continue
        if summary and str(item.get("summary") or "").strip() != summary:
            continue
        if start and str(item.get("start") or "").strip() != start:
            continue
        if end and str(item.get("end") or "").strip() != end:
            continue
        return ("verified", "Calendar read-back contains the created event with matching title/start/end.")
    return ("pending", "Created calendar event is not independently visible yet.")


def _app_running(name: str) -> tuple[bool, str]:
    from jarvis_mrb.tools.pc import app_status

    result = app_status(name)
    running = bool(result.ok and "does not appear to be running" not in result.message.lower())
    return (running, result.message)


def _tab_present(query: str) -> tuple[bool, str]:
    from jarvis_mrb.tools.browser import tab_status

    result = tab_status(query)
    data = getattr(result, "data", None)
    present = bool(result.ok and isinstance(data, list) and len(data) > 0)
    return (present, result.message)


def _observe(verifier: str, expected: dict[str, Any]) -> tuple[str, str]:
    if verifier == "gmail_sent_message":
        return _gmail_observation(expected)
    if verifier == "calendar_event_exists":
        return _calendar_observation(expected)
    if verifier == "app_present":
        running, evidence = _app_running(str(expected.get("name") or ""))
        return ("verified" if running else "pending", evidence)
    if verifier == "app_absent":
        running, evidence = _app_running(str(expected.get("name") or ""))
        return ("pending" if running else "verified", evidence)
    if verifier == "app_or_tab_present":
        name = str(expected.get("name") or "")
        present, tab_evidence = _tab_present(name)
        if present:
            return ("verified", tab_evidence)
        running, app_evidence = _app_running(name)
        return ("verified" if running else "pending", f"{tab_evidence} {app_evidence}".strip())
    if verifier == "app_or_tab_absent":
        name = str(expected.get("name") or "")
        present, tab_evidence = _tab_present(name)
        running, app_evidence = _app_running(name)
        return ("verified" if not present and not running else "pending", f"{tab_evidence} {app_evidence}".strip())
    if verifier == "minecraft_running":
        from jarvis_mrb.tools.pc import minecraft_status

        result = minecraft_status()
        running = bool(result.ok and "does not appear" not in result.message.lower())
        return ("verified" if running else "pending", result.message)
    if verifier == "browser_tab_present":
        present, evidence = _tab_present(str(expected.get("query") or ""))
        return ("verified" if present else "pending", evidence)
    if verifier == "browser_tab_absent":
        present, evidence = _tab_present(str(expected.get("query") or ""))
        return ("pending" if present else "verified", evidence)
    if verifier == "persistent_state_value":
        from jarvis_mrb.environment_state import get_state

        key = str(expected.get("key") or "")
        observed = get_state().get(key)
        matches = observed == expected.get("value")
        return ("verified" if matches else "pending", f"Persistent state {key!r} read back as {observed!r}.")
    if verifier == "temporary_state_value":
        from jarvis_mrb.ephemeral_state import get_all

        key = str(expected.get("key") or "")
        item = get_all().get(key)
        observed = item.get("value") if isinstance(item, dict) else None
        matches = observed == expected.get("value")
        return ("verified" if matches else "pending", f"Temporary state {key!r} read back as {observed!r}.")
    if verifier in {"job_active", "job_inactive"}:
        from jarvis_mrb.jobs import list_jobs

        job_id = int(expected.get("job_id") or 0)
        result = list_jobs()
        if not result.ok:
            raise RuntimeError(result.message)
        present = f"#{job_id} " in result.message
        wanted = verifier == "job_active"
        return ("verified" if present == wanted else "pending", result.message[:1400])
    if verifier == "background_terminal":
        from jarvis_mrb.background_workers import get_task

        task_id = int(expected.get("task_id") or 0)
        task = get_task(task_id)
        status = str(task.get("status") or "")
        if status == "completed":
            return ("verified", f"Background task {task_id} completed.")
        if status in {"failed", "cancelled"}:
            detail = str(task.get("error") or task.get("result") or "")[:1200]
            return ("failed", f"Background task {task_id} ended {status}. {detail}".strip())
        return ("pending", f"Background task {task_id} is {status}.")
    raise RuntimeError(f"Unknown verifier {verifier}")


def _record_observation(
    verification_id: str,
    *,
    outcome: str,
    evidence: str,
    error: str = "",
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO verification_observations(verification_id,observed_at,outcome,evidence,error) VALUES(?,?,?,?,?)",
            (verification_id, _now(), outcome, evidence[:3000], error[:2000]),
        )
        conn.commit()


def _transition(row: sqlite3.Row, status: str, evidence: str, *, error: str = "") -> dict[str, Any]:
    verification_id = str(row["id"])
    now = _now()
    event_id = _record_world_transition(
        verification_id,
        status=status,
        tool=str(row["tool"]),
        evidence=evidence,
        action_event_id=int(row["action_event_id"]),
        executive_decision_id=str(row["executive_decision_id"] or ""),
    )
    with _connect() as conn:
        conn.execute(
            """
            UPDATE action_verifications
            SET status=?,last_checked_at=?,last_evidence=?,last_error=?,updated_at=?,
                next_check_at=NULL,resolved_event_id=COALESCE(?,resolved_event_id)
            WHERE id=?
            """,
            (status, now, evidence[:3000], error[:2000], now, event_id, verification_id),
        )
        conn.commit()
    return {
        "id": verification_id,
        "status": status,
        "tool": str(row["tool"]),
        "evidence": evidence[:1500],
        "executive_decision_id": str(row["executive_decision_id"] or ""),
    }


def _mark_pending(row: sqlite3.Row, evidence: str, *, error: str = "") -> dict[str, Any]:
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE action_verifications
            SET attempts=attempts+1,last_checked_at=?,last_evidence=?,last_error=?,updated_at=?,next_check_at=?
            WHERE id=?
            """,
            (
                now,
                evidence[:3000],
                error[:2000],
                now,
                (_now_dt() + timedelta(seconds=45)).isoformat(),
                str(row["id"]),
            ),
        )
        conn.commit()
    result = {
        "id": str(row["id"]),
        "status": "pending",
        "tool": str(row["tool"]),
        "evidence": evidence[:1500],
    }
    if error:
        result["error"] = error[:1500]
    return result


def check_one(verification_id: str, *, force: bool = False) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM action_verifications WHERE id=?", (verification_id,)).fetchone()
    if row is None:
        return None
    status = str(row["status"])
    if status in _TERMINAL:
        return {
            "id": str(row["id"]),
            "status": status,
            "tool": str(row["tool"]),
            "evidence": str(row["last_evidence"]),
        }

    now = _now_dt()
    next_check = _parse_time(str(row["next_check_at"] or ""))
    if not force and next_check is not None and next_check > now:
        return None
    deadline = _parse_time(str(row["deadline_at"] or ""))
    expired = deadline is not None and now >= deadline

    verifier = str(row["verifier"])
    expected = _loads(str(row["expected_json"]), {})
    try:
        outcome, evidence = _observe(verifier, expected if isinstance(expected, dict) else {})
        _record_observation(str(row["id"]), outcome=outcome, evidence=evidence)
        if outcome in {"verified", "failed"}:
            return _transition(row, outcome, evidence)
        if expired:
            timeout_evidence = (
                f"Verification deadline elapsed after a final independent observation remained inconclusive. {evidence}"
            )
            _record_observation(str(row["id"]), outcome="timed_out", evidence=timeout_evidence)
            return _transition(row, "timed_out", timeout_evidence)
        return _mark_pending(row, evidence)
    except Exception as exc:
        error = str(exc)[:2000]
        previous = str(row["last_evidence"] or "")
        _record_observation(
            str(row["id"]),
            outcome="observer_error",
            evidence=previous,
            error=error,
        )
        if expired:
            timeout_evidence = (
                "Verification deadline elapsed and the final independent observer was unavailable or errored. "
                + error
            )
            _record_observation(
                str(row["id"]),
                outcome="timed_out",
                evidence=timeout_evidence,
                error=error,
            )
            return _transition(row, "timed_out", timeout_evidence, error=error)
        return _mark_pending(row, previous, error=error)


def check_due(limit: int = 20, *, force: bool = False) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 100))
    now = _now()
    with _connect() as conn:
        if force:
            rows = conn.execute(
                "SELECT id FROM action_verifications WHERE status='pending' ORDER BY created_at LIMIT ?",
                (safe_limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id FROM action_verifications
                WHERE status='pending' AND (next_check_at IS NULL OR next_check_at<=? OR deadline_at<=?)
                ORDER BY COALESCE(next_check_at,deadline_at),created_at
                LIMIT ?
                """,
                (now, now, safe_limit),
            ).fetchall()
    result: list[dict[str, Any]] = []
    for item in rows:
        checked = check_one(str(item["id"]), force=force)
        if checked is not None:
            result.append(checked)
    try:
        from jarvis_mrb.world_executive_loop import refresh as refresh_executive

        refresh_executive()
    except Exception:
        pass
    return result


def pending_for_intention(intention_id: str, limit: int = 12) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 50))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT v.*
            FROM action_verifications v
            JOIN executive_decisions d ON d.id=v.executive_decision_id
            WHERE d.intention_id=? AND v.status IN ('pending','failed','timed_out','unverified')
            ORDER BY
                CASE v.status WHEN 'failed' THEN 0 WHEN 'timed_out' THEN 1 WHEN 'unverified' THEN 2 ELSE 3 END,
                v.updated_at DESC
            LIMIT ?
            """,
            (intention_id, safe_limit),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "action_event_id": int(row["action_event_id"]),
            "executive_decision_id": str(row["executive_decision_id"]),
            "tool": str(row["tool"]),
            "status": str(row["status"]),
            "verifier": str(row["verifier"]),
            "expected": _loads(str(row["expected_json"]), {}),
            "attempts": int(row["attempts"]),
            "deadline_at": str(row["deadline_at"] or ""),
            "last_evidence": str(row["last_evidence"]),
            "last_error": str(row["last_error"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]


def _is_verification_query(query: str) -> bool:
    normalized = " ".join(str(query or "").lower().split())
    cues = (
        "did it work",
        "did that work",
        "did it happen",
        "did that happen",
        "was it sent",
        "was that sent",
        "was it created",
        "did you verify",
        "verified",
        "verification",
        "still waiting",
        "what happened with",
        "outcome",
    )
    return any(cue in normalized for cue in cues)


def context_for_query(query: str, limit: int = 6) -> str:
    if not _is_verification_query(query):
        return ""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM action_verifications ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 20)),),
        ).fetchall()
    if not rows:
        return ""
    lines = ["ACTION OUTCOME VERIFICATION (tool success is not treated as real-world success unless indicated):"]
    for row in rows:
        lines.append(
            f"- {row['tool']}: status={row['status']}; verifier={row['verifier']}; "
            f"evidence={str(row['last_evidence'])[:900]}"
        )
    return "\n".join(lines)[:7000]


def status() -> dict[str, Any]:
    with _connect() as conn:
        counts = {
            str(row["status"]): int(row["count"])
            for row in conn.execute(
                "SELECT status,COUNT(*) AS count FROM action_verifications GROUP BY status"
            ).fetchall()
        }
        row = conn.execute(
            "SELECT updated_at FROM action_verifications ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return {
        "installed": True,
        "tool_receipt_is_outcome": False,
        "independent_readback": True,
        "causal_readback_window": True,
        "deadline_final_observation": True,
        "persistent_pending_state": True,
        "timeout_state": True,
        "unverifiable_effects_marked_unverified": True,
        "statuses": counts,
        "last_update": str(row["updated_at"]) if row else "",
    }
