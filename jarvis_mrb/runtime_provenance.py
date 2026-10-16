"""Runtime provenance for the *actually executing* Jarvis backend.

A GitHub commit or passing CI proves source state, not the code loaded by the
user's PC. Expose a stable process nonce, start timestamp, executable source
hashes and the checkout revision so the iPhone can detect stale deployments.

No user documents, hostname, machine identifier or secrets are reported.
A Python import may remain resident after its source file changes; hashes are
on-disk measurements, explicitly not proof of bytecode currently in memory.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
STARTED_AT=datetime.now(timezone.utc).isoformat()
RUNTIME_NONCE=uuid4().hex
FILES=(
    "jarvis_mrb/agent.py",
    "jarvis_mrb/streaming_agent.py",
    "jarvis_mrb/service.py",
    "jarvis_mrb/tts_client.py",
    "jarvis_mrb/freshness_policy.py",
    "jarvis_mrb/user_belief_model.py",
    "jarvis_mrb/proactive_explain.py",
)


def _git(args: list[str]) -> tuple[bool,str]:
    try:
        result=subprocess.run(
            ["git","-C",str(ROOT),*args],
            capture_output=True,text=True,timeout=3,check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError,subprocess.SubprocessError):
        return False,""
    return (result.returncode==0,result.stdout.strip())


def inspect(*, root: Path=ROOT,
            started_at: str=STARTED_AT,
            runtime_nonce: str=RUNTIME_NONCE) -> dict[str,Any]:
    """Measure current filesystem content, not claims in README/future.md."""
    sources={}
    for name in FILES:
        path=root/name
        try:
            content=path.read_bytes()
        except OSError:
            sources[name]={"present":False}
            continue
        sources[name]={"present":True,"sha256":hashlib.sha256(content).hexdigest(),
                       "size_bytes":len(content)}
    if root==ROOT:
        commit_ok,commit=_git(["rev-parse","HEAD"])
        dirty_ok,dirty=_git(["status","--porcelain","--untracked-files=no"])
    else:
        commit_ok,commit=False,""
        dirty_ok,dirty=False,""
    good_commit=bool(commit_ok and re.fullmatch(r"[0-9a-fA-F]{40}",commit))
    return {
        "process_started_at":started_at,
        "runtime_instance":runtime_nonce,
        "checkout_commit":commit if good_commit else None,
        "checkout_state":("dirty" if dirty else "clean") if dirty_ok else "unknown",
        "filesystem_sources":sources,
        "server_python":f"{sys.version_info.major}.{sys.version_info.minor}",
        "scope":"server process identity and live disk hashes only",
        "limitations":[
            "A checked-out commit does not prove an installed iPhone binary matches.",
            "Disk hashes may change after Python modules were loaded into memory.",
            "Only tests performed on a real deployment establish working device integrations.",
        ],
    }
