from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
SANDBOX_DIR = APP_DIR / "sandbox"
DOCKER_IMAGE = os.environ.get("JARVIS_SANDBOX_IMAGE", "python:3.12-alpine")


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        completed = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def status() -> dict[str, Any]:
    return {"docker": docker_available(), "image": DOCKER_IMAGE, "network": "none"}


def run_python(code: str, *, stdin_json: Any = None, timeout_seconds: int = 8) -> SandboxResult:
    source = code.strip()
    if not source:
        return SandboxResult(False, "Sandbox code is empty.")
    if len(source) > 40_000:
        return SandboxResult(False, "Sandbox code exceeds the 40 KB limit.")
    if not docker_available():
        return SandboxResult(False, "Docker is not available, so the isolated code sandbox cannot run.")

    timeout_value = max(1, min(int(timeout_seconds), 20))
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jarvis-", dir=SANDBOX_DIR) as temp:
        work = Path(temp)
        script = work / "main.py"
        script.write_text(source, encoding="utf-8")
        if stdin_json is not None:
            (work / "input.json").write_text(json.dumps(stdin_json, ensure_ascii=False), encoding="utf-8")

        command = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "1.0",
            "--pids-limit", "64",
            "--read-only",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
            "-v", f"{work}:/work:ro",
            "-w", "/work",
            DOCKER_IMAGE,
            "python", "main.py",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_value,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(False, f"Sandbox execution exceeded {timeout_value} seconds.")
        except OSError as exc:
            return SandboxResult(False, f"Sandbox could not start: {exc}")

    stdout = completed.stdout[-8000:]
    stderr = completed.stderr[-4000:]
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit code {completed.returncode}"
        return SandboxResult(False, f"Sandbox code failed: {detail[:1200]}", stdout, stderr)
    result_text = stdout.strip()
    if not result_text:
        result_text = "Sandbox code completed successfully with no output."
    return SandboxResult(True, result_text[:4000], stdout, stderr)
