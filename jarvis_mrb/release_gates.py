"""Release evidence ledger for criteria.md gates C00–C22.

This module never decides that a capability works because code exists.  It
records acceptance *sessions* that are bound to one frozen candidate SHA and
installation fingerprint, derives machine checks from durable runtime stores
(Agency receipts, validation runs, the running service's own identity, client
builds actually observed, subsystem receipts), and mints an append-only,
hash-chained record containing every field required by criteria.md §4.

A PASS record can only be written when:

* a candidate was frozen from a clean tree with a passing full validation run;
* the checkout, running service and session all report that same SHA/env;
* every derived check for the gate passes; and
* every required human field (literal request, readback, failure case, and
  any physical observation the gate requires) is present.

FAIL and BLOCKED records are always accepted, are never rewritten, and remain
in the ledger after any later PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import jarvis_mrb.world_model as world_model

LEDGER_PATH = Path(world_model.DB_PATH).with_name("release_evidence.sqlite3")
EXPORT_DIR = Path(world_model.DB_PATH).with_name("release_evidence")

GATES: dict[str, str] = {
    "C00": "Candidate integrity and deployment identity",
    "C01": "Feature inventory / truth audit",
    "C02": "Ordinary Jarvis interaction path",
    "C03": "Persistent world model and identity continuity",
    "C04": "Persistent intentions across restart",
    "C05": "Executive loop / closed-loop convergence",
    "C06": "Authority, approval, denial, and resumption",
    "C07": "Independent outcome verification and failure recovery",
    "C08": "Replanning and dormant-goal wakeup",
    "C09": "Proactivity and exception-based attention",
    "C10": "Cross-source situational awareness",
    "C11": "Deliberation, counterfactuals, and capability-gap honesty",
    "C12": "Cognitive routing: deterministic, local, Groq, fallback",
    "C13": "Conductor: verified workstation action",
    "C14": "Reality Mesh: actual cross-device presence/continuity",
    "C15": "Reality Graph: live, provenance-bearing world state",
    "C16": "World Armor: general lawful public-camera path",
    "C17": "World Armor: shipped environmental/movement providers",
    "C18": "Closed-app delivery and runtime resilience",
    "C19": "Presence: real bounded physical actuation",
    "C20": "Privacy, secrets, revocation, and fail-closed boundaries",
    "C21": "Long-run reliability / recovery soak",
    "C22": "Unscripted revolutionary capstone",
}

# Agency REAL receipts (jarvis-agency-real-gate) that a C gate additionally
# requires.  They must be valid, same SHA/env, and minted during the C session.
AGENCY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "C04": ("A1",),
    "C05": ("A2",),
    "C06": ("A3", "A11"),
    "C07": ("A4",),
    "C08": ("A5", "A6"),
    "C09": ("A8",),
    "C11": ("A7", "A9"),
}

# Gates whose PASS criteria explicitly include a human physical observation.
HUMAN_OBSERVATION_GATES: dict[str, str] = {
    "C18": "the physical iPhone displayed the notification while Jarvis was not foregrounded",
    "C19": "the physical light visibly changed state",
    "C22": "the user experienced the run as one Jarvis task without orchestrating it",
}

RECORD_FIELDS = (
    "user_entry_surface",
    "literal_user_request",
    "devices",
    "real_services_or_providers",
    "preconditions",
    "expected_observable_result",
    "actual_observable_result",
    "external_readback_or_independent_evidence",
    "permission_or_grant_evidence",
    "failure_case_exercised",
    "artifacts",
    "notes",
)
# Fields that may legitimately be "not applicable" for some gates but must
# still be stated explicitly for a PASS.
_PASS_REQUIRED_FIELDS = (
    "user_entry_surface",
    "literal_user_request",
    "devices",
    "real_services_or_providers",
    "expected_observable_result",
    "actual_observable_result",
    "external_readback_or_independent_evidence",
    "permission_or_grant_evidence",
    "failure_case_exercised",
)
RESULTS = {"PASS", "FAIL", "BLOCKED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _connect(path: Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS release_candidates (
            id TEXT PRIMARY KEY,
            sha TEXT NOT NULL,
            environment_fingerprint TEXT NOT NULL,
            validation_run_id TEXT NOT NULL,
            frozen_at TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            candidate_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS release_gate_sessions (
            id TEXT PRIMARY KEY,
            gate TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            sha TEXT NOT NULL,
            environment_fingerprint TEXT NOT NULL,
            started_at TEXT NOT NULL,
            baseline_json TEXT NOT NULL,
            declared_json TEXT NOT NULL,
            session_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            record_id TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS release_gate_records (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            gate TEXT NOT NULL,
            result TEXT NOT NULL CHECK(result IN ('PASS','FAIL','BLOCKED')),
            candidate_id TEXT NOT NULL,
            sha TEXT NOT NULL,
            environment_fingerprint TEXT NOT NULL,
            session_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            checks_json TEXT NOT NULL,
            attestations_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            record_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS release_client_builds (
            device_id TEXT NOT NULL,
            build_sha TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            requests INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(device_id, build_sha)
        );

        CREATE TRIGGER IF NOT EXISTS release_candidates_append_only_u
        BEFORE UPDATE ON release_candidates
        BEGIN SELECT RAISE(ABORT, 'release candidates are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS release_candidates_append_only_d
        BEFORE DELETE ON release_candidates
        BEGIN SELECT RAISE(ABORT, 'release candidates are append-only'); END;

        CREATE TRIGGER IF NOT EXISTS release_records_append_only_u
        BEFORE UPDATE ON release_gate_records
        BEGIN SELECT RAISE(ABORT, 'release gate records are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS release_records_append_only_d
        BEFORE DELETE ON release_gate_records
        BEGIN SELECT RAISE(ABORT, 'release gate records are append-only'); END;

        CREATE TRIGGER IF NOT EXISTS release_sessions_identity_immutable
        BEFORE UPDATE ON release_gate_sessions
        WHEN NEW.id IS NOT OLD.id OR NEW.gate IS NOT OLD.gate
          OR NEW.candidate_id IS NOT OLD.candidate_id OR NEW.sha IS NOT OLD.sha
          OR NEW.environment_fingerprint IS NOT OLD.environment_fingerprint
          OR NEW.started_at IS NOT OLD.started_at OR NEW.baseline_json IS NOT OLD.baseline_json
          OR NEW.declared_json IS NOT OLD.declared_json OR NEW.session_hash IS NOT OLD.session_hash
          OR OLD.status <> 'running'
        BEGIN SELECT RAISE(ABORT, 'release sessions are immutable once started/finalized'); END;
        CREATE TRIGGER IF NOT EXISTS release_sessions_no_delete
        BEFORE DELETE ON release_gate_sessions
        BEGIN SELECT RAISE(ABORT, 'release sessions are append-only'); END;
        """
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def build_identity() -> dict[str, Any]:
    """Identity of *this* process's code and installation."""
    from jarvis_mrb.agency_release import (
        _git_worktree_clean,
        deployment_sha,
        environment_fingerprint,
        source_root,
    )

    root = source_root()
    sha = deployment_sha(root)
    clean, dirty = _git_worktree_clean(root)
    try:
        from jarvis_mrb.world_migrations import status as migration_status
        migrations = migration_status()
    except Exception as exc:  # pragma: no cover - defensive
        migrations = {"ready": False, "error": str(exc)[:300]}
    return {
        "code_sha": sha,
        "worktree_clean": bool(clean),
        "worktree_detail": "" if clean else str(dirty)[:1000],
        "environment_fingerprint": environment_fingerprint(),
        "world_schema_ready": bool(migrations.get("ready")),
        "world_schema_version": int(migrations.get("current") or 0),
        "world_schema_target": int(migrations.get("target") or 0),
        "pid": os.getpid(),
        "python": sys.version.split()[0],
    }


def record_client_seen(
    *,
    device_id: str,
    build_sha: str,
    model: str = "",
    path: Path | None = None,
) -> None:
    device = str(device_id or "").strip()[:80]
    build = str(build_sha or "").strip()[:80]
    if not device or not build:
        return
    now = _now()
    with closing(_connect(path)) as conn, conn:
        conn.execute(
            """
            INSERT INTO release_client_builds(device_id,build_sha,model,first_seen,last_seen,requests)
            VALUES(?,?,?,?,?,1)
            ON CONFLICT(device_id,build_sha) DO UPDATE SET
              last_seen=excluded.last_seen, model=excluded.model, requests=requests+1
            """,
            (device, build, str(model or "")[:120], now, now),
        )


def client_builds(*, since: str = "", path: Path | None = None) -> list[dict[str, Any]]:
    with closing(_connect(path)) as conn:
        rows = conn.execute(
            "SELECT * FROM release_client_builds WHERE last_seen>=? ORDER BY last_seen DESC LIMIT 50",
            (since,),
        ).fetchall()
    return [dict(row) for row in rows]


def service_identity(timeout: float = 5.0) -> dict[str, Any]:
    """Ask the *running* Jarvis service who it is (not this CLI process)."""
    import httpx

    from jarvis_mrb.server_config import load_server_config

    config = load_server_config()
    host = config.bind_host if config.bind_host not in {"0.0.0.0", "::", ""} else "127.0.0.1"
    url = f"http://{host}:{config.port}/release/identity"
    headers = {"Authorization": f"Bearer {config.api_token}"} if config.api_token else {}
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}: {exc}"[:300], "url": url}
    if response.status_code != 200:
        return {"reachable": False, "error": f"HTTP {response.status_code}", "url": url}
    try:
        data = response.json()
    except ValueError:
        return {"reachable": False, "error": "non-JSON identity response", "url": url}
    return {"reachable": True, "url": url, **(data if isinstance(data, dict) else {})}


# ---------------------------------------------------------------------------
# Candidate freeze
# ---------------------------------------------------------------------------

def _decode(row: sqlite3.Row | None, *json_fields: str) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row)
    for field in json_fields:
        try:
            value[field.removesuffix("_json")] = json.loads(value.pop(field) or "null")
        except (TypeError, ValueError):
            value[field.removesuffix("_json")] = None
    return value


def current_candidate(path: Path | None = None) -> dict[str, Any] | None:
    with closing(_connect(path)) as conn:
        row = conn.execute(
            "SELECT * FROM release_candidates ORDER BY frozen_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    return _decode(row, "detail_json")


def freeze(*, path: Path | None = None) -> dict[str, Any]:
    """Freeze the current clean checkout as the release candidate.

    Requires a passing `jarvis-agency-release-check --full`-style validation
    run (compileall, full regression, Agency synthetic A1–A12, strict world
    diagnostics, clean tree before/after) for exactly this SHA/environment.
    """
    from jarvis_mrb.agency_release import latest_validation_run

    identity = build_identity()
    sha = str(identity["code_sha"] or "")
    if not sha:
        raise ValueError("Cannot freeze: no exact Git SHA for this checkout.")
    if not identity["worktree_clean"]:
        raise ValueError("Cannot freeze a dirty working tree:\n" + identity["worktree_detail"])
    run = latest_validation_run(sha, environment=identity["environment_fingerprint"])
    required = ("compile_ok", "regression_ok", "synthetic_ok", "diagnostics_ok",
                "tree_clean_before", "tree_clean_after")
    if run is None or not all(bool(run.get(key)) for key in required):
        raise ValueError(
            "Cannot freeze: no passing full validation run for this SHA/environment. "
            "Run `jarvis-release-gate validate` first."
        )
    existing = current_candidate(path)
    if existing and existing["sha"] == sha and existing["environment_fingerprint"] == identity["environment_fingerprint"]:
        return {**existing, "already_frozen": True}
    frozen_at = _now()
    detail = {
        "identity": identity,
        "validation_run": {key: run.get(key) for key in ("id", "recorded_at", *required)},
        "supersedes": (existing or {}).get("id", ""),
    }
    candidate_id = "candidate:" + uuid.uuid4().hex
    digest = _sha256(_canonical([candidate_id, sha, identity["environment_fingerprint"], frozen_at, detail]))
    with closing(_connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO release_candidates VALUES(?,?,?,?,?,?,?)",
            (candidate_id, sha, identity["environment_fingerprint"], str(run.get("id") or ""),
             frozen_at, _canonical(detail), digest),
        )
    return current_candidate(path) or {}


# ---------------------------------------------------------------------------
# Derived checks
# ---------------------------------------------------------------------------

def _check(name: str, passed: bool, evidence: Any = None) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def _common_checks(session: dict[str, Any]) -> list[dict[str, Any]]:
    candidate = current_candidate()
    identity = build_identity()
    service = service_identity()
    checks = [
        _check(
            "session belongs to the current frozen candidate",
            bool(candidate) and candidate["id"] == session["candidate_id"] and candidate["sha"] == session["sha"],
            {"candidate": (candidate or {}).get("id"), "session_candidate": session["candidate_id"]},
        ),
        _check(
            "checkout is still the frozen SHA with a clean tree",
            identity["code_sha"] == session["sha"] and identity["worktree_clean"],
            {"code_sha": identity["code_sha"], "clean": identity["worktree_clean"]},
        ),
        _check(
            "installation fingerprint unchanged",
            identity["environment_fingerprint"] == session["environment_fingerprint"],
            identity["environment_fingerprint"],
        ),
        _check(
            "running Jarvis service reports the frozen SHA, clean tree and same installation",
            bool(service.get("reachable"))
            and service.get("code_sha") == session["sha"]
            and service.get("worktree_clean") is True
            and service.get("environment_fingerprint") == session["environment_fingerprint"],
            {k: service.get(k) for k in ("reachable", "code_sha", "worktree_clean", "environment_fingerprint", "error", "boot_id")},
        ),
    ]
    boot = (session.get("baseline") or {}).get("service_boot_id")
    if boot is not None:
        checks.append(_check(
            "service process recorded for this session",
            bool(service.get("boot_id")),
            {"baseline_boot": boot, "current_boot": service.get("boot_id")},
        ))
    return checks


def _agency_checks(session: dict[str, Any], gates: tuple[str, ...]) -> list[dict[str, Any]]:
    from jarvis_mrb.agency_release import list_real_gate_receipts, validate_real_gate_receipt

    receipts = list_real_gate_receipts(
        deployment_sha_value=session["sha"], environment=session["environment_fingerprint"]
    )
    checks = []
    for gate in gates:
        matching = [
            item for item in receipts
            if str(item.get("gate")) == gate and str(item.get("recorded_at") or "") >= session["started_at_local"]
        ]
        valid = [item for item in matching if validate_real_gate_receipt(str(item["id"])).get("valid")]
        checks.append(_check(
            f"valid Agency REAL receipt {gate} minted during this session at the same SHA/env",
            bool(valid),
            {"receipt_ids": [item["id"] for item in valid], "candidates": len(matching)},
        ))
    return checks


def _c00_checks(session: dict[str, Any]) -> list[dict[str, Any]]:
    from jarvis_mrb.agency_release import latest_validation_run

    checks: list[dict[str, Any]] = []
    run = latest_validation_run(session["sha"], environment=session["environment_fingerprint"])
    fields = ("compile_ok", "regression_ok", "synthetic_ok", "diagnostics_ok", "tree_clean_before", "tree_clean_after")
    checks.append(_check(
        "full regression + Agency synthetic + world diagnostics passed at this SHA/env",
        run is not None and all(bool(run.get(key)) for key in fields),
        {key: (run or {}).get(key) for key in ("id", "recorded_at", *fields)},
    ))
    service = service_identity()
    checks.append(_check(
        "running service world schema is current",
        service.get("world_schema_ready") is True
        and service.get("world_schema_version") == service.get("world_schema_target"),
        {k: service.get(k) for k in ("world_schema_ready", "world_schema_version", "world_schema_target")},
    ))
    phones = [
        item for item in client_builds(since=session["started_at"])
        if item["build_sha"] == session["sha"]
    ]
    checks.append(_check(
        "physical iPhone app stamped with the frozen SHA contacted the backend during this session",
        bool(phones),
        {"matching": phones, "all_recent": client_builds(since=session["started_at"])},
    ))
    try:
        from jarvis_mrb.reality_mesh import nodes
        mesh = nodes().get("nodes") or []
    except Exception as exc:
        mesh = [{"id": "?", "status": "error", "error": str(exc)[:200]}]
    remote = [item for item in mesh if str(item.get("id")) != "windows"]
    checks.append(_check(
        "every configured paired node identifies itself and is reachable",
        bool(remote) and all(str(item.get("status")) == "online" for item in remote),
        [{k: item.get(k) for k in ("id", "label", "status", "platform", "checked_at", "error")} for item in mesh],
    ))
    return checks


# Gate-specific evaluators.  Gates without an evaluator still get the common
# identity checks; their PASS then rests on the §4 human fields and artifacts,
# which the finalize step requires to be explicit.
EVALUATORS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "C00": _c00_checks,
}


def register_evaluator(gate: str, fn: Callable[[dict[str, Any]], list[dict[str, Any]]]) -> None:
    if gate not in GATES:
        raise ValueError(f"Unknown gate {gate}")
    EVALUATORS[gate] = fn


def _load_optional_evaluators() -> None:
    """Import subsystem evaluators lazily so this module stays import-light."""
    try:
        import jarvis_mrb.release_gate_evaluators  # noqa: F401  (registers on import)
    except ModuleNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _session_digest(values: list[Any]) -> str:
    return _sha256(_canonical(values))


def start_session(
    gate: str,
    *,
    declared: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    gate = str(gate or "").upper().strip()
    if gate not in GATES:
        raise ValueError(f"Unknown gate {gate!r}; expected one of C00–C22.")
    candidate = current_candidate(path)
    if not candidate:
        raise ValueError("No frozen release candidate. Run `jarvis-release-gate freeze` first.")
    identity = build_identity()
    if identity["code_sha"] != candidate["sha"] or not identity["worktree_clean"]:
        raise ValueError(
            f"Checkout {identity['code_sha'] or '?'} (clean={identity['worktree_clean']}) is not the "
            f"frozen candidate {candidate['sha']}. Re-freeze or check out the candidate."
        )
    if identity["environment_fingerprint"] != candidate["environment_fingerprint"]:
        raise ValueError("Installation fingerprint differs from the frozen candidate.")
    service = service_identity()
    baseline: dict[str, Any] = {
        "service": {k: service.get(k) for k in ("reachable", "code_sha", "boot_id", "error")},
        "service_boot_id": service.get("boot_id"),
    }
    try:
        from jarvis_mrb.agency_real_acceptance import _connect as agency_connect, _max_event_id
        with closing(agency_connect()) as conn:
            baseline["world_event_id"] = _max_event_id(conn)
    except Exception as exc:
        baseline["world_event_id_error"] = str(exc)[:200]
    session_id = "release-session:" + uuid.uuid4().hex
    started_at = _now()
    clean_declared = {
        key: str(value)[:4000]
        for key, value in (declared or {}).items()
        if key in RECORD_FIELDS and value not in (None, "")
    }
    digest = _session_digest([session_id, gate, candidate["id"], candidate["sha"],
                              candidate["environment_fingerprint"], started_at,
                              baseline, clean_declared])
    with closing(_connect(path)) as conn, conn:
        conn.execute(
            """INSERT INTO release_gate_sessions
               (id,gate,candidate_id,sha,environment_fingerprint,started_at,baseline_json,declared_json,session_hash)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (session_id, gate, candidate["id"], candidate["sha"], candidate["environment_fingerprint"],
             started_at, _canonical(baseline), _canonical(clean_declared), digest),
        )
    return get_session(session_id, path=path) or {}


def get_session(session_id: str, *, path: Path | None = None) -> dict[str, Any] | None:
    with closing(_connect(path)) as conn:
        row = conn.execute("SELECT * FROM release_gate_sessions WHERE id=?", (session_id,)).fetchone()
    session = _decode(row, "baseline_json", "declared_json")
    if session is None:
        return None
    expected = _session_digest([session["id"], session["gate"], session["candidate_id"], session["sha"],
                                session["environment_fingerprint"], session["started_at"],
                                session["baseline"], session["declared"]])
    session["integrity_ok"] = expected == session["session_hash"]
    # Agency receipts store local-offset timestamps; compare in the same form.
    started = datetime.fromisoformat(session["started_at"])
    session["started_at_local"] = started.astimezone().isoformat()
    return session


def evaluate_session(session_id: str, *, path: Path | None = None) -> dict[str, Any]:
    session = get_session(session_id, path=path)
    if session is None:
        raise KeyError(f"Unknown release session {session_id}")
    _load_optional_evaluators()
    checks = [_check("session record integrity", session["integrity_ok"], session["session_hash"])]
    checks.extend(_common_checks(session))
    gates = AGENCY_REQUIREMENTS.get(session["gate"], ())
    if gates:
        checks.extend(_agency_checks(session, gates))
    evaluator = EVALUATORS.get(session["gate"])
    if evaluator is not None:
        try:
            checks.extend(evaluator(session))
        except Exception as exc:
            checks.append(_check(f"{session['gate']} evaluator ran", False, f"{type(exc).__name__}: {exc}"[:500]))
    return {
        "session_id": session_id,
        "gate": session["gate"],
        "sha": session["sha"],
        "has_gate_evaluator": evaluator is not None,
        "all_checks_passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def _record_hash(record: dict[str, Any]) -> str:
    body = {key: record[key] for key in (
        "id", "gate", "result", "candidate_id", "sha", "environment_fingerprint", "session_id",
        "started_at", "finished_at", "fields", "checks", "attestations", "prev_hash",
    )}
    return _sha256(_canonical(body))


def finalize_session(
    session_id: str,
    *,
    result: str,
    fields: dict[str, Any],
    attestations: list[dict[str, Any]] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    result = str(result or "").upper().strip()
    if result not in RESULTS:
        raise ValueError("Result must be PASS, FAIL or BLOCKED.")
    session = get_session(session_id, path=path)
    if session is None:
        raise KeyError(f"Unknown release session {session_id}")
    if session["status"] != "running":
        raise ValueError("Session already finalized; start a new session to retest.")
    merged = {**session["declared"], **{k: v for k, v in fields.items() if v not in (None, "")}}
    clean_fields = {key: str(merged.get(key, "") or "")[:8000] for key in RECORD_FIELDS}
    clean_attest = [
        {
            "statement": str(item.get("statement") or "")[:1000],
            "observer": str(item.get("observer") or "")[:200],
            "observed_at": str(item.get("observed_at") or _now())[:64],
        }
        for item in (attestations or [])
        if str(item.get("statement") or "").strip()
    ]
    evaluation = evaluate_session(session_id, path=path)
    if result == "PASS":
        problems: list[str] = []
        if not evaluation["all_checks_passed"]:
            failed = [item["name"] for item in evaluation["checks"] if not item["passed"]]
            problems.append("derived checks failed: " + "; ".join(failed))
        missing = [key for key in _PASS_REQUIRED_FIELDS if not clean_fields[key].strip()]
        if missing:
            problems.append("missing §4 fields: " + ", ".join(missing))
        required_observation = HUMAN_OBSERVATION_GATES.get(session["gate"])
        if required_observation and not clean_attest:
            problems.append(f"human attestation required: {required_observation}")
        if not evaluation["has_gate_evaluator"] and not session["gate"] in AGENCY_REQUIREMENTS:
            if not clean_fields["artifacts"].strip():
                problems.append("gate has no machine evaluator; PASS requires explicit artifacts")
        if problems:
            raise ValueError("PASS refused: " + " | ".join(problems))

    finished_at = _now()
    with closing(_connect(path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        last = conn.execute("SELECT record_hash FROM release_gate_records ORDER BY seq DESC LIMIT 1").fetchone()
        record = {
            "id": "release-record:" + uuid.uuid4().hex,
            "gate": session["gate"],
            "result": result,
            "candidate_id": session["candidate_id"],
            "sha": session["sha"],
            "environment_fingerprint": session["environment_fingerprint"],
            "session_id": session_id,
            "started_at": session["started_at"],
            "finished_at": finished_at,
            "fields": clean_fields,
            "checks": evaluation["checks"],
            "attestations": clean_attest,
            "prev_hash": str(last["record_hash"]) if last else "genesis",
        }
        record["record_hash"] = _record_hash(record)
        conn.execute(
            """INSERT INTO release_gate_records
               (id,gate,result,candidate_id,sha,environment_fingerprint,session_id,started_at,finished_at,
                fields_json,checks_json,attestations_json,prev_hash,record_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record["id"], record["gate"], result, record["candidate_id"], record["sha"],
             record["environment_fingerprint"], session_id, record["started_at"], finished_at,
             _canonical(clean_fields), _canonical(record["checks"]), _canonical(clean_attest),
             record["prev_hash"], record["record_hash"]),
        )
        conn.execute(
            "UPDATE release_gate_sessions SET status='finalized', record_id=? WHERE id=?",
            (record["id"], session_id),
        )
    _export(record)
    return record


def _export(record: dict[str, Any]) -> None:
    try:
        folder = EXPORT_DIR / record["sha"][:12]
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{record['gate']}-{record['result']}-{record['id'].split(':')[-1][:12]}.json"
        (folder / name).write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    except OSError:
        pass  # the SQLite ledger remains authoritative


def records(*, sha: str = "", gate: str = "", path: Path | None = None) -> list[dict[str, Any]]:
    clauses, params = [], []
    if sha:
        clauses.append("sha=?")
        params.append(sha)
    if gate:
        clauses.append("gate=?")
        params.append(gate.upper())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with closing(_connect(path)) as conn:
        rows = conn.execute(f"SELECT * FROM release_gate_records{where} ORDER BY seq", tuple(params)).fetchall()
    return [_decode(row, "fields_json", "checks_json", "attestations_json") or {} for row in rows]


def verify_chain(path: Path | None = None) -> dict[str, Any]:
    previous = "genesis"
    for item in records(path=path):
        if item["prev_hash"] != previous or _record_hash(item) != item["record_hash"]:
            return {"ok": False, "broken_at": item["id"]}
        previous = item["record_hash"]
    return {"ok": True, "head": previous}


def release_status(path: Path | None = None) -> dict[str, Any]:
    candidate = current_candidate(path)
    chain = verify_chain(path)
    gates: dict[str, dict[str, Any]] = {}
    for gate, title in GATES.items():
        latest = None
        if candidate:
            items = [
                item for item in records(sha=candidate["sha"], gate=gate, path=path)
                if item["candidate_id"] == candidate["id"]
            ]
            latest = items[-1] if items else None
        gates[gate] = {
            "title": title,
            "state": (latest or {}).get("result") or "UNPROVEN",
            "record_id": (latest or {}).get("id", ""),
            "finished_at": (latest or {}).get("finished_at", ""),
        }
    all_pass = bool(candidate) and chain["ok"] and all(item["state"] == "PASS" for item in gates.values())
    return {
        "candidate": {k: (candidate or {}).get(k) for k in ("id", "sha", "environment_fingerprint", "frozen_at")},
        "ledger_chain": chain,
        "gates": gates,
        "release_complete": all_pass,
        "statement": (
            "All C00–C22 gates PASS on the frozen candidate."
            if all_pass else "RELEASE NOT COMPLETE: at least one gate is not PASS on the frozen candidate."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-release-gate",
        description="criteria.md C00–C22 release evidence ledger",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("identity", help="show this checkout's and the running service's identity")
    sub.add_parser("validate", help="run the full validation (tests, Agency synthetic, world diagnostics)")
    sub.add_parser("freeze", help="freeze the current clean, validated checkout as the candidate")
    start = sub.add_parser("start", help="start an acceptance session for a gate")
    start.add_argument("gate")
    for field in RECORD_FIELDS:
        start.add_argument("--" + field.replace("_", "-"), dest=field, default="")
    evaluate = sub.add_parser("evaluate", help="derive checks for a running session (no record)")
    evaluate.add_argument("session_id")
    finalize = sub.add_parser("finalize", help="write the immutable record for a session")
    finalize.add_argument("session_id")
    finalize.add_argument("--result", required=True, choices=sorted(RESULTS))
    finalize.add_argument("--attest", action="append", default=[],
                          help="human physical observation, e.g. 'the light turned on'")
    finalize.add_argument("--observer", default="user")
    for field in RECORD_FIELDS:
        finalize.add_argument("--" + field.replace("_", "-"), dest=field, default="")
    sub.add_parser("status", help="C00–C22 matrix for the frozen candidate")
    show = sub.add_parser("records", help="list records")
    show.add_argument("--gate", default="")
    args = parser.parse_args(argv)

    try:
        if args.command == "identity":
            _print({"this_process": build_identity(), "running_service": service_identity(),
                    "candidate": current_candidate(),
                    "recent_clients": client_builds()})
        elif args.command == "validate":
            from jarvis_mrb.agency_release import run_full_validation
            outcome = run_full_validation()
            _print({k: outcome.get(k) for k in (
                "ok", "deployment_sha", "environment_fingerprint", "compile_ok", "regression_ok",
                "synthetic_ok", "diagnostics_ok", "tree_clean_before", "tree_clean_after", "error")})
            return 0 if outcome.get("ok") else 1
        elif args.command == "freeze":
            _print(freeze())
        elif args.command == "start":
            declared = {field: getattr(args, field) for field in RECORD_FIELDS}
            _print(start_session(args.gate, declared=declared))
        elif args.command == "evaluate":
            _print(evaluate_session(args.session_id))
        elif args.command == "finalize":
            fields = {field: getattr(args, field) for field in RECORD_FIELDS}
            attest = [{"statement": text, "observer": args.observer} for text in args.attest]
            _print(finalize_session(args.session_id, result=args.result, fields=fields, attestations=attest))
        elif args.command == "status":
            outcome = release_status()
            _print(outcome)
            return 0 if outcome["release_complete"] else 2
        elif args.command == "records":
            _print(records(gate=args.gate))
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
