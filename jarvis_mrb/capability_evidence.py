"""Local capability evidence ledger: never equate source code with deployment.

Registered capabilities state *what is required*, not what is working. Only
locally executed tests create unit-test receipts; they cannot satisfy an
independent real-device or external-service acceptance requirement.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import hashlib
from typing import Any
from uuid import uuid4

_DIR = Path(os.environ.get("APPDATA") or Path.home())/"JarvisForMRB"
LEDGER_PATH = _DIR/"capability_evidence.json"
_SOURCE_ROOT = Path(__file__).resolve().parents[1]

# Non-unit hardware/deployment scopes require independent observational proof.
# A local process may run unit tests but cannot attest its own AirPods route,
# real user-world facts or real provider data.
CATALOG: dict[str, dict[str, Any]] = {
    "airpods_voice":{
        "title":"AirPods microphone and spoken responses",
        "required":("unit", "ios_simulator", "physical_airpods"),
        "unit_pattern":"test_freshness_policy.py",
    },
    "epistemic_freshness":{
        "title":"Mandatory fresh public verification",
        "required":("unit", "live_official_source"),
        "unit_pattern":"test_freshness_policy.py",
    },
    "user_belief_model":{
        "title":"Decision-relevant belief divergence",
        "required":("unit", "real_verified_fact_adapter"),
        "unit_pattern":"test_user_belief_model.py",
    },
    "voice_studio":{
        "title":"Local VoiceStudio alternate TTS",
        "required":("unit", "actual_voicestudio_audio"),
        "unit_pattern":"test_voicestudio_tts.py",
    },
    "gemma4_planner":{
        "title":"Gemma 4 as production planner",
        "required":("unit", "rtx5080_benchmark", "end_to_end_jarvis_tasks"),
        "unit_pattern":"test_model_bakeoff.py",
    },
    "public_claim_verifier":{
        "title":"Official-source announcement verification",
        "required":("unit", "live_official_source"),
        "unit_pattern":"test_public_claim_verifier.py",
    },
    "attention_budget":{
        "title":"Proactive interruption budget",
        "required":("unit", "real_notification_acceptance"),
        "unit_pattern":"test_attention_budget.py",
    },
    "proactive_explanation":{
        "title":"Why-did-you-alert-me provenance receipt",
        "required":("unit", "real_notification_acceptance"),
        "unit_pattern":"test_proactive_explain.py",
    },
    "runtime_provenance":{
        "title":"Actually responding backend process fingerprint",
        "required":("unit", "real_deployment_readback"),
        "unit_pattern":"test_runtime_provenance.py",
    },
}
_ALLOWED_SCOPES = {"unit","ios_simulator","physical_airpods","live_official_source",
                   "real_verified_fact_adapter","actual_voicestudio_audio",
                   "rtx5080_benchmark","end_to_end_jarvis_tasks","real_notification_acceptance","real_deployment_readback"}
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _git_commit() -> str:
    try:
        result=subprocess.run(
            ["git","-C",str(_SOURCE_ROOT),"rev-parse","HEAD"],
            capture_output=True,text=True,timeout=5,check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    value=result.stdout.strip().lower()
    return value if result.returncode==0 and _COMMIT.fullmatch(value) else ""


def _read(path: Path=LEDGER_PATH) -> list[dict[str,Any]]:
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload,list):
            return [x for x in payload if isinstance(x,dict)][-500:]
    except (OSError, ValueError):
        pass
    return []


def _write(entries: list[dict[str,Any]], path: Path=LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(entries[-500:],indent=2)+"\n",encoding="utf-8")
    temporary.replace(path)


def run_unit_acceptance(
    capability_id: str, *, path: Path=LEDGER_PATH,
    timeout: float=300,
) -> dict[str,Any]:
    """Actually run a fixed existing unit suite. No shell, arbitrary CLI or URL.

    This verifies *only* the Python test fixture; it cannot produce a hardware
    or deployment receipt. Failing tests are recorded, never called verified.
    """
    if capability_id not in CATALOG:
        raise ValueError("Unknown capability.")
    if not isinstance(timeout,(int,float)) or not 10<=timeout<=600:
        raise ValueError("timeout must be 10-600 seconds.")
    pattern=CATALOG[capability_id]["unit_pattern"]
    suite=_SOURCE_ROOT/"tests"/pattern
    if not suite.is_file():
        raise RuntimeError(f"Test suite is missing: {pattern}")
    commit=_git_commit()
    proc=subprocess.run(
        [sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-v"],
        cwd=_SOURCE_ROOT,capture_output=True,text=True,check=False,timeout=timeout,
    )
    # Unit discovery returning 0 tests is not evidence of anything passing.
    observed_output=proc.stdout+"\n"+proc.stderr
    discovered=re.search(r"Ran\s+([1-9][0-9]*)\s+tests?",observed_output)
    passed=proc.returncode==0 and discovered is not None
    # Content hash proves *which fixture* was exercised, not that acceptance
    # against physical hardware occurred.
    fixture_sha=hashlib.sha256(suite.read_bytes()).hexdigest()
    entry={
        "id":"r_"+uuid4().hex,
        "capability_id":capability_id,
        "scope":"unit",
        "result":"passed" if passed else "failed",
        "commit":commit,
        "fixture_sha256":fixture_sha,
        "observed_at":_utc().isoformat(),
        "runner":"local_python_unittest",
        "details":(proc.stdout+"\n"+proc.stderr)[-1200:],
    }
    entries=_read(path)
    entries.append(entry)
    _write(entries,path)
    return entry


def inspect(*, path: Path=LEDGER_PATH,
            at: datetime | None=None,
            commit: str | None=None) -> dict[str,Any]:
    now=at or _utc()
    if now.tzinfo is None:
        raise ValueError("Inspection timestamp requires a timezone.")
    commit=_git_commit() if commit is None else commit
    entries=_read(path)
    capabilities={}
    for ident,config in CATALOG.items():
        valid=[]
        for rec in entries:
            if rec.get("capability_id")!=ident or rec.get("result")!="passed":
                continue
            if rec.get("scope") not in _ALLOWED_SCOPES or rec.get("commit")!=commit or not commit:
                continue
            try: observed=datetime.fromisoformat(str(rec["observed_at"]))
            except (ValueError,TypeError,KeyError): continue
            if observed.tzinfo is None or observed>now or now-observed>timedelta(days=7):
                continue
            if rec["scope"]=="unit":
                suite=_SOURCE_ROOT/"tests"/config["unit_pattern"]
                if not suite.is_file():
                    continue
                actual=hashlib.sha256(suite.read_bytes()).hexdigest()
                if rec.get("fixture_sha256")!=actual:
                    continue
            # There is deliberately no ingestion channel for hardware or live
            # scopes until trusted real acceptance adapters exist. Manually
            # inserting a JSON receipt must not grant those scopes.
            if rec["scope"]!="unit" or rec.get("runner")!="local_python_unittest":
                continue
            valid.append(rec)
        passed_scopes={r["scope"] for r in valid}
        missing=[scope for scope in config["required"] if scope not in passed_scopes]
        capabilities[ident]={
            "title":config["title"],
            "status":"verified" if not missing else "implemented_but_unverified",
            "verified_scopes":sorted(passed_scopes),
            "missing_scopes":missing,
            "last_local_unit_receipt":next((r["id"] for r in reversed(valid) if r["scope"]=="unit"),None),
        }
    return {"checked_at":now.isoformat(),"commit":commit,
            "capabilities":capabilities,
            "warning":"Simulator, local unit tests and README claims never establish real hardware or production deployment."}


def main(argv: list[str]|None=None) -> int:
    import argparse
    parser=argparse.ArgumentParser(description="Inspect local Jarvis evidence; no deployment claims without receipts.")
    parser.add_argument("--run-unit",choices=sorted(CATALOG))
    args=parser.parse_args(argv)
    if args.run_unit:
        result=run_unit_acceptance(args.run_unit)
        print(json.dumps(result,indent=2))
    print(json.dumps(inspect(),indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
