from __future__ import annotations

import shutil
import subprocess
import threading
import time
from typing import Any

import psutil

from jarvis_mrb.event_bus import emit_proactive

_LOCK = threading.RLock()
_STARTED = False
_LAST_ALERT: dict[str, float] = {}
_LAST_SAMPLE: dict[str, Any] = {}


def _gpu_sample() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {}
    command = [
        executable,
        "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if completed.returncode != 0 or not completed.stdout.strip():
        return {}
    first = completed.stdout.strip().splitlines()[0]
    fields = [part.strip() for part in first.split(",")]
    if len(fields) < 5:
        return {}
    try:
        used = int(float(fields[1]))
        total = int(float(fields[2]))
        utilization = int(float(fields[3]))
        temp = int(float(fields[4]))
    except ValueError:
        return {}
    return {
        "name": fields[0],
        "memory_used_mib": used,
        "memory_total_mib": total,
        "memory_percent": round(100.0 * used / total, 1) if total else 0.0,
        "utilization_percent": utilization,
        "temperature_c": temp,
    }


def sample() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    disk = psutil.disk_usage("/")
    backlog = 0
    running = 0
    try:
        from jarvis_mrb.background_workers import list_tasks
        tasks = list_tasks(30)
        backlog = sum(1 for task in tasks if task.get("status") == "queued")
        running = sum(1 for task in tasks if task.get("status") == "running")
    except Exception:
        pass
    result = {
        "captured_at": time.time(),
        "cpu_percent": round(float(cpu), 1),
        "ram_percent": round(float(memory.percent), 1),
        "ram_used_gib": round((memory.total - memory.available) / (1024 ** 3), 1),
        "ram_total_gib": round(memory.total / (1024 ** 3), 1),
        "disk_percent": round(float(disk.percent), 1),
        "background_queued": backlog,
        "background_running": running,
        "gpu": _gpu_sample(),
    }
    with _LOCK:
        _LAST_SAMPLE.clear()
        _LAST_SAMPLE.update(result)
    return result


def describe() -> str:
    state = sample()
    gpu = state.get("gpu") or {}
    parts = [
        f"CPU {state['cpu_percent']:.0f} percent",
        f"RAM {state['ram_percent']:.0f} percent",
        f"background queue {state['background_queued']} queued and {state['background_running']} running",
    ]
    if gpu:
        parts.append(
            f"GPU {gpu.get('utilization_percent', 0)} percent, VRAM {gpu.get('memory_percent', 0):.0f} percent, {gpu.get('temperature_c', 0)} C"
        )
    return "System resources: " + "; ".join(parts) + "."


def _allowed(key: str, cooldown: float) -> bool:
    now = time.time()
    with _LOCK:
        last = _LAST_ALERT.get(key, 0.0)
        if now - last < cooldown:
            return False
        _LAST_ALERT[key] = now
    return True


def _check(state: dict[str, Any]) -> None:
    gpu = state.get("gpu") or {}
    if gpu:
        vram = float(gpu.get("memory_percent") or 0)
        temp = float(gpu.get("temperature_c") or 0)
        if vram >= 96 and _allowed("vram", 15 * 60):
            emit_proactive(
                f"GPU memory is at about {vram:.0f} percent. Heavy background work may start evicting models or increasing voice latency.",
                cue="warning",
                severity="warning",
            )
        if temp >= 86 and _allowed("gpu-temp", 15 * 60):
            emit_proactive(
                f"The GPU is unusually hot at about {temp:.0f} degrees Celsius.",
                cue="warning",
                severity="warning",
            )
    cpu = float(state.get("cpu_percent") or 0)
    ram = float(state.get("ram_percent") or 0)
    queued = int(state.get("background_queued") or 0)
    if cpu >= 97 and _allowed("cpu", 10 * 60):
        emit_proactive("PC CPU utilization is near saturation.", cue="warning", severity="warning")
    if ram >= 94 and _allowed("ram", 15 * 60):
        emit_proactive("PC system memory is above 94 percent utilization.", cue="warning", severity="warning")
    if queued >= 6 and _allowed("queue", 10 * 60):
        emit_proactive(
            f"The Jarvis background queue has grown to {queued} waiting tasks.",
            cue="attention",
            severity="info",
        )


def _loop() -> None:
    time.sleep(5)
    while True:
        try:
            _check(sample())
        except Exception:
            pass
        time.sleep(10)


def start() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    threading.Thread(target=_loop, name="jarvis-resource-monitor", daemon=True).start()
