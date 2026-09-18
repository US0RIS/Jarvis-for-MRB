from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import jarvis_mrb.world_model as world_model
from jarvis_mrb.agency_acceptance import REAL_GATES, SYNTHETIC_ONLY_GATES


_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$", re.IGNORECASE)
_VALIDATION_HARNESS = "agency-release-full-v1"
_VALIDATION_PROCESS_NONCE = uuid.uuid4().hex
_VALIDATION_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "jarvis_release_validation_context",
    default="",
)
_REAL_RECEIPT_PROCESS_NONCE = uuid.uuid4().hex
_REAL_RECEIPT_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "jarvis_real_receipt_context",
    default="",
)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _real_receipt_context_payload(
    *,
    gate: str,
    deployment_sha_value: str,
    environment: str,
    harness: str,
    checks: list[dict[str, Any]],
    evidence: dict[str, Any],
    trace_ref: str,
    session_id: str,
) -> dict[str, Any]:
    normalized_checks: list[dict[str, Any]] = []
    for raw in checks or []:
        if not isinstance(raw, dict):
            continue
        normalized_checks.append(
            {
                "name": " ".join(str(raw.get("name") or "").split())[:1000],
                "passed": raw.get("passed") is True,
                "evidence": raw.get("evidence"),
            }
        )
    return {
        "gate": str(gate or "").strip().upper(),
        "deployment_sha": str(deployment_sha_value or "").strip().lower(),
        "environment_fingerprint": str(environment or "").strip(),
        "harness": " ".join(str(harness or "").split())[:300],
        "checks": normalized_checks,
        "evidence": dict(evidence or {}),
        "trace_ref": str(trace_ref or "").strip()[:3000],
        "session_id": str(session_id or "").strip()[:300],
    }


def _real_receipt_context_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        {"nonce": _REAL_RECEIPT_PROCESS_NONCE, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


@contextlib.contextmanager
def _real_receipt_recording_context(payload: dict[str, Any]):
    token = _REAL_RECEIPT_CONTEXT.set(_real_receipt_context_key(dict(payload)))
    try:
        yield
    finally:
        _REAL_RECEIPT_CONTEXT.reset(token)


def _receipt_digest(
    *,
    gate: str,
    deployment_sha_value: str,
    environment: str,
    harness: str,
    checks_json: str,
    evidence_json: str,
    trace_ref: str,
    trace_sha256: str,
    session_id: str,
    recorded_at: str,
) -> str:
    payload = {
        "gate": str(gate),
        "deployment_sha": str(deployment_sha_value),
        "environment_fingerprint": str(environment),
        "harness": str(harness),
        "checks_json": str(checks_json),
        "evidence_json": str(evidence_json),
        "trace_ref": str(trace_ref),
        "trace_sha256": str(trace_sha256),
        "session_id": str(session_id),
        "recorded_at": str(recorded_at),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _live_session_digest(
    *,
    session_id: str,
    gate: str,
    deployment_sha_value: str,
    environment: str,
    desired_state_id: str,
    parameters_json: str,
    baseline_json: str,
    started_at: str,
) -> str:
    payload = {
        "id": str(session_id),
        "gate": str(gate),
        "deployment_sha": str(deployment_sha_value),
        "environment_fingerprint": str(environment),
        "desired_state_id": str(desired_state_id),
        "parameters_json": str(parameters_json),
        "baseline_json": str(baseline_json),
        "started_at": str(started_at),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _validation_digest(
    *,
    harness: str,
    deployment_sha_value: str,
    environment: str,
    source_root_value: str,
    compile_ok: bool,
    regression_ok: bool,
    synthetic_ok: bool,
    diagnostics_ok: bool,
    tree_clean_before: bool,
    tree_clean_after: bool,
    regression_summary: str,
    synthetic_summary: str,
    diagnostics_summary: str,
    recorded_at: str,
) -> str:
    payload = {
        "harness": str(harness),
        "deployment_sha": str(deployment_sha_value),
        "environment_fingerprint": str(environment),
        "source_root": str(source_root_value),
        "compile_ok": bool(compile_ok),
        "regression_ok": bool(regression_ok),
        "synthetic_ok": bool(synthetic_ok),
        "diagnostics_ok": bool(diagnostics_ok),
        "tree_clean_before": bool(tree_clean_before),
        "tree_clean_after": bool(tree_clean_after),
        "regression_summary": str(regression_summary),
        "synthetic_summary": str(synthetic_summary),
        "diagnostics_summary": str(diagnostics_summary),
        "recorded_at": str(recorded_at),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _validation_context_payload(
    *,
    deployment_sha_value: str,
    environment: str,
    source_root_value: str,
    compile_ok: bool,
    regression_ok: bool,
    synthetic_ok: bool,
    diagnostics_ok: bool,
    tree_clean_before: bool,
    tree_clean_after: bool,
    regression_summary: str,
    synthetic_summary: str,
    diagnostics_summary: str,
) -> dict[str, Any]:
    return {
        "harness": _VALIDATION_HARNESS,
        "deployment_sha": str(deployment_sha_value),
        "environment_fingerprint": str(environment),
        "source_root": str(source_root_value),
        "compile_ok": bool(compile_ok),
        "regression_ok": bool(regression_ok),
        "synthetic_ok": bool(synthetic_ok),
        "diagnostics_ok": bool(diagnostics_ok),
        "tree_clean_before": bool(tree_clean_before),
        "tree_clean_after": bool(tree_clean_after),
        "regression_summary": str(regression_summary),
        "synthetic_summary": str(synthetic_summary),
        "diagnostics_summary": str(diagnostics_summary),
    }


def _validation_context_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        {"nonce": _VALIDATION_PROCESS_NONCE, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


@contextlib.contextmanager
def _validation_recording_context(payload: dict[str, Any]):
    token = _VALIDATION_CONTEXT.set(_validation_context_key(dict(payload)))
    try:
        yield
    finally:
        _VALIDATION_CONTEXT.reset(token)


def _file_sha256(path: str) -> str:
    target = Path(str(path or "")).expanduser()
    if not target.is_file():
        return ""
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _migrate_receipt_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='agency_real_gate_receipts'"
    ).fetchone()
    if row is None:
        return
    sql = " ".join(str(row["sql"] or "").lower().split())
    columns = {
        str(item["name"])
        for item in conn.execute("PRAGMA table_info(agency_real_gate_receipts)").fetchall()
    }
    needs_rebuild = (
        "unique(gate,deployment_sha,environment_fingerprint)" in sql.replace(" ", "")
        or "session_id" not in columns
        or "receipt_hash" not in columns
        or "trace_sha256" not in columns
    )
    if not needs_rebuild:
        return

    legacy_rows = conn.execute(
        "SELECT * FROM agency_real_gate_receipts ORDER BY recorded_at,id"
    ).fetchall()
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS agency_real_gate_receipts_immutable_update;
        DROP TRIGGER IF EXISTS agency_real_gate_receipts_immutable_delete;
        DROP INDEX IF EXISTS idx_agency_real_gate_receipts_release;
        DROP INDEX IF EXISTS idx_agency_real_gate_receipts_session;
        ALTER TABLE agency_real_gate_receipts RENAME TO agency_real_gate_receipts_legacy;
        CREATE TABLE agency_real_gate_receipts (
            id TEXT PRIMARY KEY,
            gate TEXT NOT NULL,
            deployment_sha TEXT NOT NULL,
            environment_fingerprint TEXT NOT NULL,
            harness TEXT NOT NULL,
            checks_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            trace_ref TEXT NOT NULL DEFAULT '',
            trace_sha256 TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            receipt_hash TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        """
    )
    for legacy in legacy_rows:
        keys = set(legacy.keys())
        gate = str(legacy["gate"])
        sha = str(legacy["deployment_sha"])
        env = str(legacy["environment_fingerprint"])
        harness = str(legacy["harness"])
        checks_json = str(legacy["checks_json"])
        evidence_json = str(legacy["evidence_json"])
        trace_ref = str(legacy["trace_ref"] or "")
        trace_sha256 = (
            str(legacy["trace_sha256"] or "")
            if "trace_sha256" in keys
            else _file_sha256(trace_ref)
        )
        session_id = str(legacy["session_id"] or "") if "session_id" in keys else ""
        recorded_at = str(legacy["recorded_at"])
        digest = _receipt_digest(
            gate=gate,
            deployment_sha_value=sha,
            environment=env,
            harness=harness,
            checks_json=checks_json,
            evidence_json=evidence_json,
            trace_ref=trace_ref,
            trace_sha256=trace_sha256,
            session_id=session_id,
            recorded_at=recorded_at,
        )
        conn.execute(
            """
            INSERT INTO agency_real_gate_receipts(
                id,gate,deployment_sha,environment_fingerprint,harness,checks_json,
                evidence_json,trace_ref,trace_sha256,session_id,receipt_hash,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(legacy["id"]), gate, sha, env, harness, checks_json,
                evidence_json, trace_ref, trace_sha256, session_id, digest, recorded_at,
            ),
        )
    conn.execute("DROP TABLE agency_real_gate_receipts_legacy")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(world_model.DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    _migrate_receipt_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agency_real_gate_receipts (
            id TEXT PRIMARY KEY,
            gate TEXT NOT NULL,
            deployment_sha TEXT NOT NULL,
            environment_fingerprint TEXT NOT NULL,
            harness TEXT NOT NULL,
            checks_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            trace_ref TEXT NOT NULL DEFAULT '',
            trace_sha256 TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            receipt_hash TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agency_real_gate_receipts_release
            ON agency_real_gate_receipts(deployment_sha,environment_fingerprint,gate,recorded_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agency_real_gate_receipts_session
            ON agency_real_gate_receipts(session_id) WHERE session_id<>'';

        CREATE TABLE IF NOT EXISTS agency_release_validation_runs (
            id TEXT PRIMARY KEY,
            harness TEXT NOT NULL DEFAULT '',
            deployment_sha TEXT NOT NULL,
            environment_fingerprint TEXT NOT NULL,
            source_root TEXT NOT NULL,
            compile_ok INTEGER NOT NULL,
            regression_ok INTEGER NOT NULL,
            synthetic_ok INTEGER NOT NULL,
            diagnostics_ok INTEGER NOT NULL,
            tree_clean_before INTEGER NOT NULL DEFAULT 0,
            tree_clean_after INTEGER NOT NULL DEFAULT 0,
            regression_summary TEXT NOT NULL DEFAULT '',
            synthetic_summary TEXT NOT NULL DEFAULT '',
            diagnostics_summary TEXT NOT NULL DEFAULT '',
            validation_hash TEXT NOT NULL DEFAULT '',
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agency_release_validation_runs
            ON agency_release_validation_runs(deployment_sha,environment_fingerprint,recorded_at DESC);

        CREATE TABLE IF NOT EXISTS agency_installation_identity (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            installation_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TRIGGER IF NOT EXISTS agency_real_gate_receipts_immutable_update
        BEFORE UPDATE ON agency_real_gate_receipts
        BEGIN
            SELECT RAISE(ABORT, 'Agency real-gate receipts are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS agency_real_gate_receipts_immutable_delete
        BEFORE DELETE ON agency_real_gate_receipts
        BEGIN
            SELECT RAISE(ABORT, 'Agency real-gate receipts are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS agency_release_validation_runs_immutable_update
        BEFORE UPDATE ON agency_release_validation_runs
        BEGIN
            SELECT RAISE(ABORT, 'Agency release validation runs are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS agency_release_validation_runs_immutable_delete
        BEFORE DELETE ON agency_release_validation_runs
        BEGIN
            SELECT RAISE(ABORT, 'Agency release validation runs are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS agency_installation_identity_immutable_update
        BEFORE UPDATE ON agency_installation_identity
        BEGIN
            SELECT RAISE(ABORT, 'Agency installation identity is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS agency_installation_identity_immutable_delete
        BEFORE DELETE ON agency_installation_identity
        BEGIN
            SELECT RAISE(ABORT, 'Agency installation identity is immutable');
        END;
        """
    )
    validation_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(agency_release_validation_runs)").fetchall()
    }
    if "harness" not in validation_columns:
        conn.execute(
            "ALTER TABLE agency_release_validation_runs ADD COLUMN harness TEXT NOT NULL DEFAULT ''"
        )
    if "tree_clean_before" not in validation_columns:
        conn.execute(
            "ALTER TABLE agency_release_validation_runs ADD COLUMN tree_clean_before INTEGER NOT NULL DEFAULT 0"
        )
    if "tree_clean_after" not in validation_columns:
        conn.execute(
            "ALTER TABLE agency_release_validation_runs ADD COLUMN tree_clean_after INTEGER NOT NULL DEFAULT 0"
        )
    if "validation_hash" not in validation_columns:
        conn.execute(
            "ALTER TABLE agency_release_validation_runs ADD COLUMN validation_hash TEXT NOT NULL DEFAULT ''"
        )
    conn.commit()
    return conn


def _installation_id() -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT installation_id FROM agency_installation_identity WHERE singleton=1"
        ).fetchone()
        if row is not None:
            return str(row["installation_id"])
        installation_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO agency_installation_identity(singleton,installation_id,created_at)
            VALUES(1,?,?)
            """,
            (installation_id, _now()),
        )
        conn.commit()
        return installation_id


def _host_machine_identity() -> str:
    system = platform.system().lower()

    if system == "windows":
        try:
            import winreg  # type: ignore[import-not-found]

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
            text = str(value or "").strip()
            if text:
                return "windows-machine-guid:" + text
        except Exception:
            pass

    if system == "darwin":
        try:
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', str(result.stdout or ""))
                if match:
                    return "mac-platform-uuid:" + match.group(1)
        except (OSError, subprocess.SubprocessError):
            pass

    for candidate in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            text = ""
        if text:
            return f"machine-id:{text}"

    node = str(platform.node() or "").strip()
    return "node:" + (node or "unknown-host")


def environment_fingerprint() -> str:
    try:
        db_path = str(Path(world_model.DB_PATH).expanduser().resolve())
    except OSError:
        db_path = str(Path(world_model.DB_PATH).expanduser().absolute())
    try:
        root_path = str(source_root().expanduser().resolve())
    except OSError:
        root_path = str(source_root().expanduser().absolute())

    try:
        from jarvis_mrb.permissions import _load as load_permission_policy
        permission_policy = dict(load_permission_policy())
    except Exception:
        permission_policy = {"error": "permission-policy-unavailable"}

    raw = json.dumps(
        {
            "installation_id": _installation_id(),
            "host_machine_identity": _host_machine_identity(),
            "database_path": db_path,
            "source_root": root_path,
            "permission_policy": permission_policy,
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:24]


def source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def deployment_sha(root: Path | None = None) -> str:
    env_sha = str(os.environ.get("JARVIS_BUILD_SHA") or "").strip().lower()
    if _SHA_RE.fullmatch(env_sha):
        return env_sha
    candidate = root or source_root()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(candidate),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    sha = str(result.stdout or "").strip().lower()
    return sha if result.returncode == 0 and _SHA_RE.fullmatch(sha) else ""


def _git_worktree_clean(root: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        detail = (str(result.stdout or "") + "\n" + str(result.stderr or "")).strip()
        return False, detail[-2000:] or f"git status exited {result.returncode}"
    dirty = str(result.stdout or "").strip()
    return (not dirty, dirty[-5000:])


def _require_true(evidence: dict[str, Any], key: str, gate: str) -> None:
    if evidence.get(key) is not True:
        raise ValueError(f"{gate} real receipt requires evidence.{key}=true.")


def _require_false(evidence: dict[str, Any], key: str, gate: str) -> None:
    if evidence.get(key) is not False:
        raise ValueError(f"{gate} real receipt requires evidence.{key}=false.")


def _require_int_at_least(evidence: dict[str, Any], key: str, minimum: int, gate: str) -> None:
    try:
        value = int(evidence.get(key))
    except (TypeError, ValueError):
        value = -1
    if value < minimum:
        raise ValueError(f"{gate} real receipt requires evidence.{key}>={minimum}.")


def _validate_gate_evidence(gate: str, evidence: dict[str, Any], trace_ref: str) -> None:
    _require_true(evidence, "real_services", gate)
    _require_false(evidence, "synthetic", gate)
    _require_false(evidence, "manual_orchestration", gate)

    if gate == "A1":
        _require_true(evidence, "restart_observed", gate)
        _require_true(evidence, "completed_work_preserved", gate)
        _require_true(evidence, "evidence_preserved", gate)
        _require_true(evidence, "pending_approval_preserved", gate)
        _require_true(evidence, "next_evaluation_preserved", gate)
        _require_true(evidence, "goal_recovered_without_restatement", gate)
    elif gate == "A2":
        _require_int_at_least(evidence, "action_observation_cycles", 2, gate)
        _require_int_at_least(evidence, "independent_observation_cycles", 2, gate)
        _require_true(evidence, "second_action_followed_first_observation", gate)
        _require_true(evidence, "intermediate_unsatisfied_observed", gate)
        _require_true(evidence, "desired_state_satisfied", gate)
        _require_true(evidence, "automatic_stop_observed", gate)
        _require_true(evidence, "goal_not_repeated", gate)
    elif gate == "A3":
        _require_true(evidence, "safe_read_auto_proceeded", gate)
        _require_true(evidence, "protected_external_write_observed", gate)
        _require_true(evidence, "approval_resumed_same_plan", gate)
        _require_true(evidence, "permission_boundary_not_bypassed", gate)
        _require_true(evidence, "denial_case_observed", gate)
        _require_true(evidence, "denial_forced_replan_or_blocked", gate)
    elif gate == "A4":
        _require_true(evidence, "action_attempt_persisted", gate)
        _require_true(evidence, "expected_outcome_persisted", gate)
        _require_true(evidence, "verified_real_write_observed", gate)
        _require_true(evidence, "failure_timeout_or_unverified_observed", gate)
        _require_true(evidence, "independent_readback_observed", gate)
        _require_true(evidence, "verification_feedback_observed", gate)
    elif gate == "A5":
        _require_true(evidence, "external_change_observed", gate)
        _require_true(evidence, "stale_path_invalidated", gate)
        _require_true(evidence, "replanned_without_goal_restatement", gate)
        _require_true(evidence, "already_valid_work_preserved", gate)
    elif gate == "A6":
        _require_true(evidence, "dormant_state_observed", gate)
        _require_true(evidence, "wake_condition_changed", gate)
        _require_true(evidence, "reactivated_without_goal_restatement", gate)
        _require_true(evidence, "next_step_surfaced_or_executed", gate)
    elif gate == "A7":
        _require_int_at_least(evidence, "parallel_workers", 4, gate)
        _require_true(evidence, "parallel_overlap_observed", gate)
        _require_true(evidence, "required_epistemic_roles_present", gate)
        _require_true(evidence, "provenance_structurally_bounded", gate)
        _require_true(evidence, "material_disagreement_preserved", gate)
        _require_true(evidence, "synthesis_after_workers", gate)
    elif gate == "A8":
        _require_int_at_least(evidence, "low_value_changes", 5, gate)
        if int(evidence.get("bounded_interruptions", -1)) != 1:
            raise ValueError("A8 real receipt requires evidence.bounded_interruptions=1.")
        if int(evidence.get("duplicate_interruptions", -1)) != 0:
            raise ValueError("A8 real receipt requires evidence.duplicate_interruptions=0.")
        _require_true(evidence, "interruption_reason_inspectable", gate)
    elif gate == "A9":
        _require_true(evidence, "missing_capability_observed", gate)
        _require_false(evidence, "fabricated_tool_availability", gate)
        _require_true(evidence, "blocked_or_disabled_adapter_observed", gate)
        _require_true(evidence, "adapter_synthesized_disabled", gate)
        _require_true(evidence, "explicit_enablement_observed", gate)
        _require_true(evidence, "capability_resolved_after_enable", gate)
        _require_true(evidence, "goal_reactivated_after_capability", gate)
        _require_true(evidence, "adapter_execution_still_confirmed", gate)
    elif gate == "A11":
        _require_true(evidence, "preference_authority_conflict_observed", gate)
        _require_true(evidence, "protected_action_waited_for_approval", gate)
        _require_true(evidence, "permission_policy_remained_authoritative", gate)
    elif gate == "A12":
        for key in (
            "private_information_retrieval",
            "public_research",
            "parallel_analysis",
            "protected_external_action",
            "protected_action_approval_boundary",
            "independent_outcome_verification",
            "replan_after_injected_change",
            "final_desired_state_satisfied",
            "final_satisfaction_followed_verified_action",
            "final_satisfaction_derived_from_verified_action",
        ):
            _require_true(evidence, key, gate)
        clean_trace = str(trace_ref or "").strip()
        if not clean_trace:
            raise ValueError("A12 real receipt requires a non-empty human-readable trace_ref.")
        trace_path = Path(clean_trace).expanduser()
        if not trace_path.is_file():
            raise ValueError("A12 real receipt trace_ref must point to an existing trace file.")
        try:
            if not trace_path.read_text(encoding="utf-8", errors="replace").strip():
                raise ValueError("A12 real receipt trace file is empty.")
        except OSError as exc:
            raise ValueError(f"A12 real receipt trace file is unreadable: {exc}") from exc


def _validated_live_session(
    session_id: str,
    *,
    gate: str,
    deployment_sha_value: str,
    environment: str,
    checks: list[dict[str, Any]],
    evidence: dict[str, Any],
    require_completed: bool,
    receipt_id: str = "",
) -> tuple[bool, str]:
    clean_session_id = str(session_id or "").strip()
    if not clean_session_id:
        return False, "REAL receipt is not bound to a live acceptance session."
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM agency_real_gate_sessions WHERE id=?",
                (clean_session_id,),
            ).fetchone()
    except sqlite3.OperationalError:
        return False, "REAL acceptance session ledger is unavailable."
    if row is None:
        return False, "REAL acceptance session does not exist."
    keys = set(row.keys())
    if "session_hash" not in keys:
        return False, "REAL acceptance session has no integrity hash."
    expected_session_hash = _live_session_digest(
        session_id=str(row["id"] or ""),
        gate=str(row["gate"] or ""),
        deployment_sha_value=str(row["deployment_sha"] or ""),
        environment=str(row["environment_fingerprint"] or ""),
        desired_state_id=str(row["desired_state_id"] or ""),
        parameters_json=str(row["parameters_json"] or "{}"),
        baseline_json=str(row["baseline_json"] or "{}"),
        started_at=str(row["started_at"] or ""),
    )
    if str(row["session_hash"] or "") != expected_session_hash:
        return False, "REAL acceptance session integrity hash mismatch."
    if str(row["gate"] or "") != str(gate):
        return False, "REAL acceptance session gate does not match receipt."
    if str(row["deployment_sha"] or "") != str(deployment_sha_value):
        return False, "REAL acceptance session SHA does not match receipt."
    if str(row["environment_fingerprint"] or "") != str(environment):
        return False, "REAL acceptance session environment does not match receipt."
    status = str(row["status"] or "")
    if require_completed:
        if status != "completed":
            return False, "REAL acceptance session is not completed."
        if receipt_id and str(row["receipt_id"] or "") != str(receipt_id):
            return False, "REAL acceptance session points to a different receipt."
    elif status != "running":
        return False, "REAL receipt can only be minted while its acceptance session is running."

    try:
        evaluation = json.loads(str(row["last_evaluation_json"] or "{}"))
    except (json.JSONDecodeError, TypeError):
        evaluation = {}
    if not isinstance(evaluation, dict) or evaluation.get("passed") is not True:
        return False, "REAL acceptance session has no persisted passing evaluation."

    stored_checks = evaluation.get("checks")
    stored_evidence = evaluation.get("evidence")
    if stored_checks != checks:
        return False, "REAL receipt checks do not exactly match the session evaluation."
    if stored_evidence != evidence:
        return False, "REAL receipt evidence does not exactly match the session evaluation."
    return True, ""


def record_real_gate_receipt(
    gate: str,
    *,
    deployment_sha_value: str,
    harness: str,
    checks: list[dict[str, Any]],
    evidence: dict[str, Any],
    trace_ref: str = "",
    environment: str | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    clean_gate = str(gate or "").strip().upper()
    if clean_gate not in REAL_GATES:
        if clean_gate in SYNTHETIC_ONLY_GATES:
            raise ValueError(f"{clean_gate} is synthetic-only and must not have a REAL gate receipt.")
        raise ValueError(f"Unknown REAL Agency gate {clean_gate!r}.")
    clean_sha = str(deployment_sha_value or "").strip().lower()
    if not _SHA_RE.fullmatch(clean_sha):
        raise ValueError("REAL gate receipt requires an exact 40-64 character hexadecimal deployment SHA.")
    clean_harness = " ".join(str(harness or "").split())[:300]
    if not clean_harness or "synthetic" in clean_harness.lower():
        raise ValueError("REAL gate receipt requires a named non-synthetic harness.")
    if not isinstance(checks, list) or not checks:
        raise ValueError("REAL gate receipt requires non-empty structured checks.")
    normalized_checks: list[dict[str, Any]] = []
    for raw in checks:
        if not isinstance(raw, dict):
            raise ValueError("REAL gate checks must be objects.")
        name = " ".join(str(raw.get("name") or "").split())[:1000]
        if not name or raw.get("passed") is not True:
            raise ValueError("Every REAL gate check must have a name and passed=true.")
        normalized_checks.append(
            {
                "name": name,
                "passed": True,
                "evidence": raw.get("evidence"),
            }
        )
    clean_evidence = dict(evidence or {})
    _validate_gate_evidence(clean_gate, clean_evidence, trace_ref)
    env = str(environment or environment_fingerprint()).strip()
    if not env:
        raise ValueError("REAL gate receipt requires an environment fingerprint.")

    clean_session_id = str(session_id or "").strip()[:300]
    session_ok, session_error = _validated_live_session(
        clean_session_id,
        gate=clean_gate,
        deployment_sha_value=clean_sha,
        environment=env,
        checks=normalized_checks,
        evidence=clean_evidence,
        require_completed=False,
    )
    if not session_ok:
        raise ValueError(session_error)
    if clean_harness != "agency-real-gate-session-v1":
        raise ValueError("REAL gate receipts must be minted by the live Agency gate harness.")
    context_payload = _real_receipt_context_payload(
        gate=clean_gate,
        deployment_sha_value=clean_sha,
        environment=env,
        harness=clean_harness,
        checks=normalized_checks,
        evidence=clean_evidence,
        trace_ref=trace_ref,
        session_id=clean_session_id,
    )
    if _REAL_RECEIPT_CONTEXT.get() != _real_receipt_context_key(context_payload):
        raise ValueError(
            "REAL gate receipts may only be minted by finalize_session()."
        )

    receipt_id = f"agency-real:{uuid.uuid4()}"
    recorded_at = _now()
    clean_trace_ref = str(trace_ref or "").strip()[:3000]
    trace_sha256 = _file_sha256(clean_trace_ref) if clean_gate == "A12" else ""
    if clean_gate == "A12" and not trace_sha256:
        raise ValueError("A12 real receipt trace file could not be hashed.")
    checks_json = json.dumps(normalized_checks, ensure_ascii=False, sort_keys=True)
    evidence_json = json.dumps(clean_evidence, ensure_ascii=False, sort_keys=True)
    receipt_hash = _receipt_digest(
        gate=clean_gate,
        deployment_sha_value=clean_sha,
        environment=env,
        harness=clean_harness,
        checks_json=checks_json,
        evidence_json=evidence_json,
        trace_ref=clean_trace_ref,
        trace_sha256=trace_sha256,
        session_id=clean_session_id,
        recorded_at=recorded_at,
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_real_gate_receipts(
                id,gate,deployment_sha,environment_fingerprint,harness,checks_json,
                evidence_json,trace_ref,trace_sha256,session_id,receipt_hash,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                receipt_id,
                clean_gate,
                clean_sha,
                env,
                clean_harness,
                checks_json,
                evidence_json,
                clean_trace_ref,
                trace_sha256,
                clean_session_id,
                receipt_hash,
                recorded_at,
            ),
        )
        conn.commit()
    return get_receipt(receipt_id) or {}


def _decode_receipt(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["checks"] = json.loads(str(item.pop("checks_json")))
    except (json.JSONDecodeError, TypeError):
        item["checks"] = []
    try:
        item["evidence"] = json.loads(str(item.pop("evidence_json")))
    except (json.JSONDecodeError, TypeError):
        item["evidence"] = {}
    return item


def get_receipt(receipt_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agency_real_gate_receipts WHERE id=?",
            (str(receipt_id),),
        ).fetchone()
    return _decode_receipt(row) if row else None


def get_receipt_for_session(session_id: str) -> dict[str, Any] | None:
    clean = str(session_id or "").strip()
    if not clean:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agency_real_gate_receipts WHERE session_id=? ORDER BY recorded_at DESC LIMIT 1",
            (clean,),
        ).fetchone()
    return _decode_receipt(row) if row else None


def validate_real_gate_receipt(receipt_id: str) -> dict[str, Any]:
    item = get_receipt(str(receipt_id))
    if item is None:
        return {"valid": False, "reason": "REAL gate receipt does not exist.", "receipt": None}

    gate = str(item.get("gate") or "")
    expected_hash = _receipt_digest(
        gate=gate,
        deployment_sha_value=str(item.get("deployment_sha") or ""),
        environment=str(item.get("environment_fingerprint") or ""),
        harness=str(item.get("harness") or ""),
        checks_json=json.dumps(item.get("checks") or [], ensure_ascii=False, sort_keys=True),
        evidence_json=json.dumps(item.get("evidence") or {}, ensure_ascii=False, sort_keys=True),
        trace_ref=str(item.get("trace_ref") or ""),
        trace_sha256=str(item.get("trace_sha256") or ""),
        session_id=str(item.get("session_id") or ""),
        recorded_at=str(item.get("recorded_at") or ""),
    )
    if str(item.get("receipt_hash") or "") != expected_hash:
        return {"valid": False, "reason": "receipt content hash mismatch", "receipt": item}

    session_ok, session_error = _validated_live_session(
        str(item.get("session_id") or ""),
        gate=gate,
        deployment_sha_value=str(item.get("deployment_sha") or ""),
        environment=str(item.get("environment_fingerprint") or ""),
        checks=list(item.get("checks") or []),
        evidence=dict(item.get("evidence") or {}),
        require_completed=True,
        receipt_id=str(item.get("id") or ""),
    )
    if not session_ok:
        return {"valid": False, "reason": session_error, "receipt": item}

    if gate == "A12":
        actual_trace_hash = _file_sha256(str(item.get("trace_ref") or ""))
        if actual_trace_hash != str(item.get("trace_sha256") or ""):
            return {
                "valid": False,
                "reason": "human-readable A12 trace content hash mismatch",
                "receipt": item,
            }

    checks = item.get("checks") or []
    if not checks or not all(
        isinstance(check, dict) and check.get("passed") is True
        for check in checks
    ):
        return {
            "valid": False,
            "reason": "receipt contains missing or non-passing checks",
            "receipt": item,
        }

    try:
        _validate_gate_evidence(
            gate,
            dict(item.get("evidence") or {}),
            str(item.get("trace_ref") or ""),
        )
    except ValueError as exc:
        return {"valid": False, "reason": str(exc), "receipt": item}

    return {"valid": True, "reason": "", "receipt": item}


def list_real_gate_receipts(
    *,
    deployment_sha_value: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if deployment_sha_value:
        clauses.append("deployment_sha=?")
        params.append(str(deployment_sha_value).strip().lower())
    if environment:
        clauses.append("environment_fingerprint=?")
        params.append(str(environment))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM agency_real_gate_receipts{where} ORDER BY recorded_at,gate",
            tuple(params),
        ).fetchall()
    return [_decode_receipt(row) for row in rows]


def record_validation_run(
    *,
    deployment_sha_value: str,
    source_root_value: str,
    compile_ok: bool,
    regression_ok: bool,
    synthetic_ok: bool,
    diagnostics_ok: bool,
    tree_clean_before: bool,
    tree_clean_after: bool,
    regression_summary: str = "",
    synthetic_summary: str = "",
    diagnostics_summary: str = "",
    environment: str | None = None,
) -> dict[str, Any]:
    clean_sha = str(deployment_sha_value or "").strip().lower()
    if not _SHA_RE.fullmatch(clean_sha):
        raise ValueError("Release validation run requires an exact deployment SHA.")
    run_id = f"agency-validation:{uuid.uuid4()}"
    env = str(environment or environment_fingerprint())
    recorded_at = _now()
    clean_source_root = str(source_root_value or "")[:2000]
    clean_regression_summary = str(regression_summary or "")[-5000:]
    clean_synthetic_summary = str(synthetic_summary or "")[-5000:]
    clean_diagnostics_summary = str(diagnostics_summary or "")[-5000:]
    context_payload = _validation_context_payload(
        deployment_sha_value=clean_sha,
        environment=env,
        source_root_value=clean_source_root,
        compile_ok=bool(compile_ok),
        regression_ok=bool(regression_ok),
        synthetic_ok=bool(synthetic_ok),
        diagnostics_ok=bool(diagnostics_ok),
        tree_clean_before=bool(tree_clean_before),
        tree_clean_after=bool(tree_clean_after),
        regression_summary=clean_regression_summary,
        synthetic_summary=clean_synthetic_summary,
        diagnostics_summary=clean_diagnostics_summary,
    )
    if _VALIDATION_CONTEXT.get() != _validation_context_key(context_payload):
        raise ValueError(
            "Release validation records may only be minted by run_full_validation()."
        )
    validation_hash = _validation_digest(
        harness=_VALIDATION_HARNESS,
        deployment_sha_value=clean_sha,
        environment=env,
        source_root_value=clean_source_root,
        compile_ok=bool(compile_ok),
        regression_ok=bool(regression_ok),
        synthetic_ok=bool(synthetic_ok),
        diagnostics_ok=bool(diagnostics_ok),
        tree_clean_before=bool(tree_clean_before),
        tree_clean_after=bool(tree_clean_after),
        regression_summary=clean_regression_summary,
        synthetic_summary=clean_synthetic_summary,
        diagnostics_summary=clean_diagnostics_summary,
        recorded_at=recorded_at,
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_release_validation_runs(
                id,harness,deployment_sha,environment_fingerprint,source_root,compile_ok,regression_ok,
                synthetic_ok,diagnostics_ok,tree_clean_before,tree_clean_after,
                regression_summary,synthetic_summary,diagnostics_summary,validation_hash,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                _VALIDATION_HARNESS,
                clean_sha,
                env,
                str(source_root_value or "")[:2000],
                1 if compile_ok else 0,
                1 if regression_ok else 0,
                1 if synthetic_ok else 0,
                1 if diagnostics_ok else 0,
                1 if tree_clean_before else 0,
                1 if tree_clean_after else 0,
                clean_regression_summary,
                clean_synthetic_summary,
                clean_diagnostics_summary,
                validation_hash,
                recorded_at,
            ),
        )
        conn.commit()
    return latest_validation_run(clean_sha, environment=env) or {}


def latest_validation_run(
    deployment_sha_value: str,
    *,
    environment: str | None = None,
) -> dict[str, Any] | None:
    env = str(environment or environment_fingerprint())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM agency_release_validation_runs
            WHERE deployment_sha=? AND environment_fingerprint=?
            ORDER BY recorded_at DESC LIMIT 1
            """,
            (str(deployment_sha_value).strip().lower(), env),
        ).fetchone()
    return dict(row) if row else None


def release_status(
    *,
    deployment_sha_value: str | None = None,
    environment: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sha = str(deployment_sha_value or deployment_sha()).strip().lower()
    env = str(environment or environment_fingerprint())
    valid_sha = bool(_SHA_RE.fullmatch(sha))
    receipts = (
        list_real_gate_receipts(deployment_sha_value=sha, environment=env)
        if valid_sha
        else []
    )
    by_gate: dict[str, dict[str, Any]] = {}
    invalid_receipts: dict[str, list[dict[str, str]]] = {}
    for item in reversed(receipts):
        gate = str(item.get("gate") or "")
        if gate in by_gate:
            continue
        validation = validate_real_gate_receipt(str(item.get("id") or ""))
        reason = "" if validation.get("valid") else str(validation.get("reason") or "invalid REAL receipt")
        if reason:
            invalid_receipts.setdefault(gate, []).append(
                {"receipt_id": str(item.get("id") or ""), "reason": reason[:1000]}
            )
            continue
        by_gate[gate] = item
    missing_real = sorted(REAL_GATES - set(by_gate))

    validation = latest_validation_run(sha, environment=env) if valid_sha else None
    validation_hash_ok = False
    if validation:
        expected_validation_hash = _validation_digest(
            harness=str(validation.get("harness") or ""),
            deployment_sha_value=str(validation.get("deployment_sha") or ""),
            environment=str(validation.get("environment_fingerprint") or ""),
            source_root_value=str(validation.get("source_root") or ""),
            compile_ok=int(validation.get("compile_ok") or 0) == 1,
            regression_ok=int(validation.get("regression_ok") or 0) == 1,
            synthetic_ok=int(validation.get("synthetic_ok") or 0) == 1,
            diagnostics_ok=int(validation.get("diagnostics_ok") or 0) == 1,
            tree_clean_before=int(validation.get("tree_clean_before") or 0) == 1,
            tree_clean_after=int(validation.get("tree_clean_after") or 0) == 1,
            regression_summary=str(validation.get("regression_summary") or ""),
            synthetic_summary=str(validation.get("synthetic_summary") or ""),
            diagnostics_summary=str(validation.get("diagnostics_summary") or ""),
            recorded_at=str(validation.get("recorded_at") or ""),
        )
        validation_hash_ok = str(validation.get("validation_hash") or "") == expected_validation_hash

    validation_after_real_gates = False
    if validation and by_gate:
        try:
            validation_time = datetime.fromisoformat(
                str(validation.get("recorded_at") or "").replace("Z", "+00:00")
            )
            receipt_times = [
                datetime.fromisoformat(
                    str(item.get("recorded_at") or "").replace("Z", "+00:00")
                )
                for item in by_gate.values()
            ]
            validation_after_real_gates = bool(
                receipt_times and validation_time >= max(receipt_times)
            )
        except (TypeError, ValueError):
            validation_after_real_gates = False

    validation_ok = bool(
        validation
        and str(validation.get("harness") or "") == _VALIDATION_HARNESS
        and validation_hash_ok
        and validation_after_real_gates
        and int(validation.get("compile_ok") or 0) == 1
        and int(validation.get("regression_ok") or 0) == 1
        and int(validation.get("synthetic_ok") or 0) == 1
        and int(validation.get("diagnostics_ok") or 0) == 1
        and int(validation.get("tree_clean_before") or 0) == 1
        and int(validation.get("tree_clean_after") or 0) == 1
    )

    if diagnostics is None:
        try:
            from jarvis_mrb.world_diagnostics import validate
            diagnostics = validate(require_agency=True)
        except Exception as exc:
            diagnostics = {"ok": False, "error": str(exc)[:1000]}
    diagnostics_ok = bool(diagnostics.get("ok"))

    ready = bool(valid_sha and validation_ok and diagnostics_ok and not missing_real)
    reasons: list[str] = []
    if not valid_sha:
        reasons.append("Exact deployment Git SHA is unavailable.")
    if not validation_ok:
        if validation and validation_hash_ok and not validation_after_real_gates and by_gate:
            reasons.append(
                "The latest validation run predates one or more selected REAL gate receipts; "
                "run full validation again after REAL acceptance."
            )
        else:
            reasons.append("No fully passing validation run exists for this exact SHA/environment.")
    if not diagnostics_ok:
        reasons.append("Current strict world/Agency diagnostics are not clean.")
    if missing_real:
        reasons.append("Missing REAL gate receipts: " + ", ".join(missing_real) + ".")

    return {
        "release_ready": ready,
        "deployment_sha": sha,
        "deployment_sha_valid": valid_sha,
        "environment_fingerprint": env,
        "validation_run": validation,
        "validation_hash_ok": validation_hash_ok,
        "validation_after_real_gates": validation_after_real_gates,
        "current_diagnostics_ok": diagnostics_ok,
        "real_gate_receipts": {gate: by_gate[gate]["id"] for gate in sorted(by_gate)},
        "invalid_real_gate_receipts": invalid_receipts,
        "missing_real_gates": missing_real,
        "synthetic_only_gates": sorted(SYNTHETIC_ONLY_GATES),
        "reasons": reasons,
    }


def _run_command(command: list[str], *, cwd: Path, timeout: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "JARVIS_AGENCY_MODE": "monitor"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    combined = (str(result.stdout or "") + "\n" + str(result.stderr or "")).strip()
    return result.returncode == 0, combined[-12000:]


def run_full_validation(*, root: Path | None = None) -> dict[str, Any]:
    source = root or source_root()
    sha = deployment_sha(source)
    if not _SHA_RE.fullmatch(sha):
        return {
            "ok": False,
            "recorded": False,
            "error": "Cannot run release validation without an exact deployment Git SHA.",
            "source_root": str(source),
        }
    if not (source / "jarvis_mrb").is_dir() or not (source / "tests").is_dir():
        return {
            "ok": False,
            "recorded": False,
            "error": "Release validation requires the Jarvis source tree and tests directory.",
            "source_root": str(source),
            "deployment_sha": sha,
        }

    tree_clean_before, tree_before_detail = _git_worktree_clean(source)
    if not tree_clean_before:
        return {
            "ok": False,
            "recorded": False,
            "error": "Release validation refuses to certify a dirty or unverifiable Git working tree.",
            "source_root": str(source),
            "deployment_sha": sha,
            "git_status": tree_before_detail,
        }

    compile_ok, compile_output = _run_command(
        [sys.executable, "-m", "compileall", "-q", "jarvis_mrb", "tests"],
        cwd=source,
        timeout=180,
    )
    regression_ok, regression_output = _run_command(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=source,
        timeout=1800,
    )
    synthetic_ok, synthetic_output = _run_command(
        [sys.executable, "-m", "jarvis_mrb.agency_acceptance_check"],
        cwd=source,
        timeout=600,
    )

    try:
        from jarvis_mrb.world_diagnostics import validate
        diagnostics = validate(require_agency=True)
    except Exception as exc:
        diagnostics = {"ok": False, "error": str(exc)[:2000]}
    diagnostics_ok = bool(diagnostics.get("ok"))
    tree_clean_after, tree_after_detail = _git_worktree_clean(source)
    env = environment_fingerprint()
    regression_summary = (
        "compile:\n" + compile_output
        + "\n\nunittest:\n" + regression_output
        + ("\n\npost-test git status:\n" + tree_after_detail if tree_after_detail else "")
    )[-5000:]
    synthetic_summary = str(synthetic_output or "")[-5000:]
    diagnostics_summary = json.dumps(
        diagnostics,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )[-5000:]
    context_payload = _validation_context_payload(
        deployment_sha_value=sha,
        environment=env,
        source_root_value=str(source)[:2000],
        compile_ok=compile_ok,
        regression_ok=regression_ok,
        synthetic_ok=synthetic_ok,
        diagnostics_ok=diagnostics_ok,
        tree_clean_before=tree_clean_before,
        tree_clean_after=tree_clean_after,
        regression_summary=regression_summary,
        synthetic_summary=synthetic_summary,
        diagnostics_summary=diagnostics_summary,
    )
    with _validation_recording_context(context_payload):
        run = record_validation_run(
            deployment_sha_value=sha,
            source_root_value=str(source),
            compile_ok=compile_ok,
            regression_ok=regression_ok,
            synthetic_ok=synthetic_ok,
            diagnostics_ok=diagnostics_ok,
            tree_clean_before=tree_clean_before,
            tree_clean_after=tree_clean_after,
            regression_summary=regression_summary,
            synthetic_summary=synthetic_summary,
            diagnostics_summary=diagnostics_summary,
            environment=env,
        )
    return {
        "ok": bool(
            compile_ok
            and regression_ok
            and synthetic_ok
            and diagnostics_ok
            and tree_clean_before
            and tree_clean_after
        ),
        "recorded": True,
        "deployment_sha": sha,
        "environment_fingerprint": env,
        "compile_ok": compile_ok,
        "regression_ok": regression_ok,
        "synthetic_ok": synthetic_ok,
        "diagnostics_ok": diagnostics_ok,
        "tree_clean_before": tree_clean_before,
        "tree_clean_after": tree_clean_after,
        "validation_run": run,
        "release_status": release_status(
            deployment_sha_value=sha,
            diagnostics=diagnostics,
        ),
    }


def status() -> dict[str, Any]:
    with _connect() as conn:
        receipts = int(conn.execute("SELECT COUNT(*) FROM agency_real_gate_receipts").fetchone()[0])
        validations = int(conn.execute("SELECT COUNT(*) FROM agency_release_validation_runs").fetchone()[0])
    return {
        "ready": True,
        "immutable_receipts": True,
        "real_gate_receipts": receipts,
        "validation_runs": validations,
        "current": release_status(),
    }
