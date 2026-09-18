from __future__ import annotations

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


def _now() -> str:
    return datetime.now().astimezone().isoformat()


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
            deployment_sha TEXT NOT NULL,
            environment_fingerprint TEXT NOT NULL,
            source_root TEXT NOT NULL,
            compile_ok INTEGER NOT NULL,
            regression_ok INTEGER NOT NULL,
            synthetic_ok INTEGER NOT NULL,
            diagnostics_ok INTEGER NOT NULL,
            regression_summary TEXT NOT NULL DEFAULT '',
            synthetic_summary TEXT NOT NULL DEFAULT '',
            diagnostics_summary TEXT NOT NULL DEFAULT '',
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
        """
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


def environment_fingerprint() -> str:
    raw = json.dumps(
        {
            "installation_id": _installation_id(),
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
        _require_true(evidence, "goal_recovered_without_restatement", gate)
    elif gate == "A2":
        _require_int_at_least(evidence, "action_observation_cycles", 2, gate)
        _require_true(evidence, "desired_state_satisfied", gate)
        _require_true(evidence, "automatic_stop_observed", gate)
    elif gate == "A3":
        _require_true(evidence, "protected_external_write_observed", gate)
        _require_true(evidence, "approval_resumed_same_plan", gate)
        _require_true(evidence, "denial_case_observed", gate)
    elif gate == "A4":
        _require_true(evidence, "verified_real_write_observed", gate)
        _require_true(evidence, "failure_timeout_or_unverified_observed", gate)
        _require_true(evidence, "independent_readback_observed", gate)
    elif gate == "A5":
        _require_true(evidence, "external_change_observed", gate)
        _require_true(evidence, "stale_path_invalidated", gate)
        _require_true(evidence, "replanned_without_goal_restatement", gate)
    elif gate == "A6":
        _require_true(evidence, "dormant_state_observed", gate)
        _require_true(evidence, "wake_condition_changed", gate)
        _require_true(evidence, "reactivated_without_goal_restatement", gate)
    elif gate == "A7":
        _require_int_at_least(evidence, "parallel_workers", 2, gate)
        _require_true(evidence, "parallel_overlap_observed", gate)
        _require_true(evidence, "provenance_structurally_bounded", gate)
        _require_true(evidence, "material_disagreement_preserved", gate)
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
            "independent_outcome_verification",
            "replan_after_injected_change",
            "final_desired_state_satisfied",
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

    receipt_id = f"agency-real:{uuid.uuid4()}"
    recorded_at = _now()
    clean_trace_ref = str(trace_ref or "").strip()[:3000]
    trace_sha256 = _file_sha256(clean_trace_ref) if clean_gate == "A12" else ""
    if clean_gate == "A12" and not trace_sha256:
        raise ValueError("A12 real receipt trace file could not be hashed.")
    clean_session_id = str(session_id or "").strip()[:300]
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
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_release_validation_runs(
                id,deployment_sha,environment_fingerprint,source_root,compile_ok,regression_ok,
                synthetic_ok,diagnostics_ok,regression_summary,synthetic_summary,
                diagnostics_summary,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                clean_sha,
                env,
                str(source_root_value or "")[:2000],
                1 if compile_ok else 0,
                1 if regression_ok else 0,
                1 if synthetic_ok else 0,
                1 if diagnostics_ok else 0,
                str(regression_summary or "")[-5000:],
                str(synthetic_summary or "")[-5000:],
                str(diagnostics_summary or "")[-5000:],
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
        reason = ""
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
            reason = "receipt content hash mismatch"
        elif gate == "A12" and _file_sha256(str(item.get("trace_ref") or "")) != str(item.get("trace_sha256") or ""):
            reason = "human-readable A12 trace content hash mismatch"
        elif not item.get("checks") or not all(
            isinstance(check, dict) and check.get("passed") is True
            for check in (item.get("checks") or [])
        ):
            reason = "receipt contains missing or non-passing checks"
        else:
            try:
                _validate_gate_evidence(
                    gate,
                    dict(item.get("evidence") or {}),
                    str(item.get("trace_ref") or ""),
                )
            except ValueError as exc:
                reason = str(exc)
        if reason:
            invalid_receipts.setdefault(gate, []).append(
                {"receipt_id": str(item.get("id") or ""), "reason": reason[:1000]}
            )
            continue
        by_gate[gate] = item
    missing_real = sorted(REAL_GATES - set(by_gate))

    validation = latest_validation_run(sha, environment=env) if valid_sha else None
    validation_ok = bool(
        validation
        and int(validation.get("compile_ok") or 0) == 1
        and int(validation.get("regression_ok") or 0) == 1
        and int(validation.get("synthetic_ok") or 0) == 1
        and int(validation.get("diagnostics_ok") or 0) == 1
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

    run = record_validation_run(
        deployment_sha_value=sha,
        source_root_value=str(source),
        compile_ok=compile_ok,
        regression_ok=regression_ok,
        synthetic_ok=synthetic_ok,
        diagnostics_ok=diagnostics_ok,
        regression_summary=("compile:\n" + compile_output + "\n\nunittest:\n" + regression_output),
        synthetic_summary=synthetic_output,
        diagnostics_summary=json.dumps(diagnostics, ensure_ascii=False, sort_keys=True, default=str),
    )
    return {
        "ok": bool(compile_ok and regression_ok and synthetic_ok and diagnostics_ok),
        "recorded": True,
        "deployment_sha": sha,
        "environment_fingerprint": environment_fingerprint(),
        "compile_ok": compile_ok,
        "regression_ok": regression_ok,
        "synthetic_ok": synthetic_ok,
        "diagnostics_ok": diagnostics_ok,
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
