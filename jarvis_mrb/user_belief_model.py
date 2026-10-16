"""Opt-in, evidence-bounded model of potential user/world belief divergence.

The model never reads minds. An explicitly stated user belief is a recorded
statement, an exposure is only an exposure, and an acknowledged correction is
evidence of a potential update. No proactive warnings without an imminent,
user-enrolled action and independently source-verified current state.

No model inference, network calls or external writes occur here. All operations
are private SQLite transactions. The API must enforce authenticated enrollment.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import os
import re
import sqlite3
from uuid import uuid4

from jarvis_mrb import world_model

DEFAULT_PATH = Path(world_model.DB_PATH).with_name("user_belief_model.sqlite3")
_KEY = re.compile(r"^[a-z][a-z0-9_.:-]{1,95}$")
_ID = re.compile(r"^[a-zA-Z0-9_.:-]{3,160}$")
_KINDS = {"stated", "exposed", "acknowledged"}
_MAX_FACT_AGE = timedelta(hours=24)
_MAX_WARNING_HORIZON = timedelta(hours=1)


def enabled() -> bool:
    return os.getenv("JARVIS_USER_BELIEF_MODEL_ENABLED", "0") == "1"


def _require_enabled() -> None:
    if not enabled():
        raise RuntimeError("User Belief Model is disabled. Explicit opt-in is required.")


def _text(raw: Any, name: str, limit: int = 300) -> str:
    if not isinstance(raw, str) or not (1 <= len(raw.strip()) <= limit):
        raise ValueError(f"{name} must have 1-{limit} characters.")
    value = " ".join(raw.strip().split())
    if not value:
        raise ValueError(f"{name} cannot be empty.")
    return value


def _key(raw: str) -> str:
    value = _text(raw, "predicate", 96).lower()
    if not _KEY.fullmatch(value):
        raise ValueError("predicate must be a normalized identifier.")
    return value


def _stamp(raw: str | datetime | None = None) -> datetime:
    if raw is None:
        result = datetime.now(timezone.utc)
    elif isinstance(raw, datetime):
        result = raw
    elif isinstance(raw, str):
        try:
            result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Timestamp must be ISO 8601 with a timezone.") from exc
    else:
        raise ValueError("Timestamp must be ISO 8601 with a timezone.")
    if result.tzinfo is None:
        raise ValueError("Naive timestamps are not permitted.")
    return result.astimezone(timezone.utc)


def _db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA secure_delete=ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS world_statements (
          id TEXT PRIMARY KEY,
          subject TEXT NOT NULL,
          predicate TEXT NOT NULL,
          value TEXT NOT NULL,
          evidence_id TEXT NOT NULL,
          source_kind TEXT NOT NULL CHECK(source_kind IN ('attested','provider_verified')),
          observed_at TEXT NOT NULL,
          recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_world_subject
          ON world_statements(subject,predicate,observed_at);
        CREATE TABLE IF NOT EXISTS belief_exposures (
          id TEXT PRIMARY KEY,
          subject TEXT NOT NULL,
          predicate TEXT NOT NULL,
          value TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('stated','exposed','acknowledged')),
          evidence_id TEXT NOT NULL,
          observed_at TEXT NOT NULL,
          recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_belief_subject
          ON belief_exposures(subject,predicate,observed_at);
        CREATE TABLE IF NOT EXISTS pending_decisions (
          id TEXT PRIMARY KEY,
          subject TEXT NOT NULL,
          predicate TEXT NOT NULL,
          label TEXT NOT NULL,
          deadline TEXT NOT NULL,
          enrollment_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active','resolved','cancelled')),
          recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_active
          ON pending_decisions(status,deadline);
    """)
    con.commit()
    return con


def _path(db_path: Path | str | None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_PATH


def observe_world(
    subject: str, predicate: str, value: str, *,
    evidence_id: str, observed_at: str | datetime | None = None,
    db_path: Path | str | None = None,
    # Only internal independently verifying provider adapters may assert this.
    _independently_verified: bool = False,
) -> dict[str, Any]:
    """Record a source fact; externally supplied API facts remain *attested*.

    Providing a source URL/receipt is not itself proof of verification. Trusted
    adapter code may use the internal-only flag after verifying actual evidence.
    """
    _require_enabled()
    subject = _text(subject, "subject", 160)
    predicate = _key(predicate)
    value = _text(value, "value", 300)
    evidence_id = _text(evidence_id, "evidence_id", 160)
    observed = _stamp(observed_at)
    now = _stamp()
    if observed > now + timedelta(minutes=2):
        raise ValueError("World observation cannot be in the future.")
    ident = "w_" + uuid4().hex
    kind = "provider_verified" if _independently_verified else "attested"
    with closing(_db(_path(db_path))) as con, con:
        con.execute(
            "INSERT INTO world_statements VALUES(?,?,?,?,?,?,?,?)",
            (ident,subject,predicate,value,evidence_id,kind,observed.isoformat(),now.isoformat()),
        )
    return {"id":ident,"subject":subject,"predicate":predicate,"source_kind":kind,
            "observed_at":observed.isoformat(),"status":"recorded_not_independently_verified" if kind=="attested" else "verified_source_observation"}


def observe_belief(
    subject: str, predicate: str, value: str, *,
    kind: str, evidence_id: str,
    observed_at: str | datetime | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    _require_enabled()
    subject = _text(subject, "subject", 160)
    predicate = _key(predicate)
    value = _text(value, "value", 300)
    evidence_id = _text(evidence_id, "evidence_id", 160)
    if kind not in _KINDS:
        raise ValueError("kind must be stated, exposed or acknowledged.")
    observed = _stamp(observed_at)
    now = _stamp()
    if observed > now + timedelta(minutes=2):
        raise ValueError("Belief evidence cannot come from the future.")
    ident = "b_" + uuid4().hex
    with closing(_db(_path(db_path))) as con, con:
        con.execute(
            "INSERT INTO belief_exposures VALUES(?,?,?,?,?,?,?,?)",
            (ident,subject,predicate,value,kind,evidence_id,observed.isoformat(),now.isoformat()),
        )
    return {"id":ident,"kind":kind,"status":"observed_not_proof_of_current_belief"}


def enroll_decision(
    subject: str, predicate: str, label: str, *, deadline: str | datetime,
    enrollment_id: str, db_path: Path | str | None = None,
) -> dict[str, Any]:
    _require_enabled()
    subject = _text(subject, "subject", 160)
    predicate = _key(predicate)
    label = _text(label, "label", 160)
    enrollment_id = _text(enrollment_id, "enrollment_id", 160)
    deadline_dt = _stamp(deadline)
    now = _stamp()
    if deadline_dt <= now or deadline_dt > now + timedelta(days=30):
        raise ValueError("Decision deadline must be future and within 30 days.")
    ident = "d_" + uuid4().hex
    with closing(_db(_path(db_path))) as con, con:
        con.execute("INSERT INTO pending_decisions VALUES(?,?,?,?,?,?,?,?)",
                    (ident,subject,predicate,label,deadline_dt.isoformat(),enrollment_id,"active",now.isoformat()))
    return {"id":ident,"deadline":deadline_dt.isoformat(),"status":"active"}


def resolve_decision(decision_id: str, *, db_path: Path | str | None = None) -> dict[str, Any]:
    _require_enabled()
    if not _ID.fullmatch(decision_id):
        raise ValueError("Invalid decision ID.")
    with closing(_db(_path(db_path))) as con, con:
        result=con.execute("UPDATE pending_decisions SET status='resolved' WHERE id=? AND status='active'",(decision_id,))
    return {"id":decision_id, "resolved":result.rowcount == 1}


def evaluate(*, now: str | datetime | None = None,
             db_path: Path | str | None = None,
             limit: int = 20) -> dict[str, Any]:
    """Read-only conservative divergences, never an automated action.

    Exposure to a fact cannot be equated with acceptance or knowledge. A later
    acknowledgement/stated update suppresses a stale-belief warning, but does
    not prove comprehension. Alerts are never emitted on unverifiable state.
    """
    _require_enabled()
    if not isinstance(limit,int) or not 1<=limit<=100:
        raise ValueError("limit must be 1-100.")
    instant = _stamp(now)
    path=_path(db_path)
    if not path.exists():
        return {"evaluated_at":instant.isoformat(),"warnings":[],"suppressed":[]}
    warnings: list[dict[str,Any]]=[]
    suppressed: list[dict[str,Any]]=[]
    with closing(_db(path)) as con:
        decisions=con.execute(
            "SELECT * FROM pending_decisions WHERE status='active' AND deadline>? ORDER BY deadline LIMIT ?",
            (instant.isoformat(), limit),
        ).fetchall()
        for decision in decisions:
            left=( _stamp(decision["deadline"])-instant ).total_seconds()
            if left > _MAX_WARNING_HORIZON.total_seconds():
                continue
            subject,predicate=decision["subject"],decision["predicate"]
            # Include earlier observations up to the evaluation time only:
            # future-dated rows never support retrospective claims.
            world=con.execute(
                "SELECT * FROM world_statements WHERE subject=? AND predicate=? "
                "AND observed_at<=? ORDER BY observed_at DESC,recorded_at DESC LIMIT 1",
                (subject,predicate,instant.isoformat()),
            ).fetchone()
            belief=con.execute(
                "SELECT * FROM belief_exposures WHERE subject=? AND predicate=? "
                "AND kind='stated' AND observed_at<=? ORDER BY observed_at DESC,recorded_at DESC LIMIT 1",
                (subject,predicate,instant.isoformat()),
            ).fetchone()
            if not world or not belief:
                suppressed.append({"decision_id":decision["id"],"reason":"missing_world_or_stated_belief"})
                continue
            if world["source_kind"]!="provider_verified":
                suppressed.append({"decision_id":decision["id"],"reason":"world_not_independently_verified"})
                continue
            if instant-_stamp(world["observed_at"])>_MAX_FACT_AGE:
                suppressed.append({"decision_id":decision["id"],"reason":"world_evidence_expired"})
                continue
            if world["value"]==belief["value"]:
                continue
            if _stamp(belief["observed_at"])>=_stamp(world["observed_at"]):
                suppressed.append({"decision_id":decision["id"],"reason":"later_user_statement_needs_reconciliation"})
                continue
            later=con.execute(
                "SELECT * FROM belief_exposures WHERE subject=? AND predicate=? "
                "AND kind='acknowledged' AND value=? AND observed_at>? AND observed_at<=? "
                "ORDER BY observed_at DESC LIMIT 1",
                (subject,predicate,world["value"],belief["observed_at"],instant.isoformat()),
            ).fetchone()
            if later:
                suppressed.append({"decision_id":decision["id"],"reason":"user_acknowledged_new_value"})
                continue
            warnings.append({
                "decision_id":decision["id"],
                "decision":decision["label"],
                "deadline":decision["deadline"],
                "minutes_until_deadline":round(left/60,1),
                "subject":subject,"predicate":predicate,
                "last_stated_value":belief["value"],
                "latest_verified_value":world["value"],
                "belief_evidence_id":belief["evidence_id"],
                "world_evidence_id":world["evidence_id"],
                "uncertainty":"User belief may have changed without our observing it.",
                "status":"possible_decision_relevant_belief_divergence",
                "action":"inform_only_no_automatic_external_action",
            })
    return {"evaluated_at":instant.isoformat(),"warnings":warnings,"suppressed":suppressed}


def forget(*, db_path: Path | str | None = None) -> dict[str,int]:
    """Explicitly erase this model's private observations and decision enrollments."""
    _require_enabled()
    path=_path(db_path)
    if not path.exists():
        return {"world":0,"belief":0,"decisions":0}
    with closing(_db(path)) as con, con:
        counts={}
        for table,label in (("world_statements","world"),("belief_exposures","belief"),("pending_decisions","decisions")):
            counts[label]=con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            con.execute(f"DELETE FROM {table}")
        con.execute("PRAGMA secure_delete=ON")
    return counts
