from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    message: str


def _process_names() -> Iterable[str]:
    for process in psutil.process_iter(["name"]):
        try:
            name = process.info.get("name")
            if name:
                yield name.lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def _normalize_app_name(name: str) -> str:
    return name.strip().lower().removesuffix(".exe")


def _matching_processes(name: str) -> list[psutil.Process]:
    needle = _normalize_app_name(name)
    matches: list[psutil.Process] = []
    for process in psutil.process_iter(["pid", "name"]):
        try:
            process_name = str(process.info.get("name") or "").lower().removesuffix(".exe")
            if needle and (needle == process_name or needle in process_name or process_name in needle):
                matches.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def app_status(name: str) -> ToolResult:
    matches = _matching_processes(name)
    if matches:
        names = sorted({str(p.info.get("name") or name) for p in matches})
        return ToolResult(True, f"{name} appears to be running ({', '.join(names[:5])}).")
    return ToolResult(True, f"{name} does not appear to be running.")


def list_running_apps(limit: int = 30) -> ToolResult:
    names = sorted({name for name in _process_names() if name and name not in {"system", "registry"}})
    shown = names[: max(1, min(limit, 100))]
    return ToolResult(True, "Running processes: " + ", ".join(shown))


def _start_app_via_start_menu(name: str) -> bool:
    if sys.platform != "win32":
        return False
    escaped = name.replace("'", "''")
    script = (
        "$a = Get-StartApps | Where-Object { $_.Name -like '*" + escaped + "*' } | Select-Object -First 1; "
        "if ($a) { Start-Process ('shell:AppsFolder\\' + $a.AppID); exit 0 } else { exit 2 }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def launch_app(name: str) -> ToolResult:
    if not name.strip():
        return ToolResult(False, "No application name was provided.")

    if _matching_processes(name):
        return ToolResult(True, f"{name} is already running.")

    if _normalize_app_name(name) == "minecraft":
        return launch_minecraft()

    executable = shutil.which(name) or shutil.which(name + ".exe")
    if executable:
        try:
            subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ToolResult(True, f"Opened {name}.")
        except OSError:
            pass

    if sys.platform == "win32":
        if _start_app_via_start_menu(name):
            return ToolResult(True, f"Opened {name} from the Windows Start menu.")

        try:
            result = subprocess.run(
                ["cmd.exe", "/c", "start", "", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return ToolResult(True, f"Launch request sent for {name}.")
        except (OSError, subprocess.TimeoutExpired):
            pass

    return ToolResult(False, f"Jarvis could not find an application named {name}.")


def close_app(name: str) -> ToolResult:
    matches = _matching_processes(name)
    if not matches:
        return ToolResult(True, f"{name} does not appear to be running.")

    terminated: list[psutil.Process] = []
    denied = 0
    for process in matches:
        try:
            process.terminate()
            terminated.append(process)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            denied += 1
            continue

    # Never pass inaccessible processes to wait_procs: on Windows, wait() itself
    # can raise AccessDenied and previously crashed the entire Jarvis request.
    alive: list[psutil.Process] = []
    if terminated:
        try:
            _, alive = psutil.wait_procs(terminated, timeout=2)
        except (psutil.AccessDenied, OSError):
            alive = terminated

    killed = 0
    for process in alive:
        try:
            process.kill()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Give Windows a moment, then verify by re-querying rather than relying on
    # wait() return codes from protected/sandboxed processes.
    remaining = _matching_processes(name)
    if not remaining:
        return ToolResult(True, f"Closed {name}.")

    if terminated or killed:
        return ToolResult(
            False,
            f"Jarvis asked {name} to close, but {len(remaining)} matching process(es) are still running. "
            "Windows may be protecting one of them.",
        )

    if denied:
        return ToolResult(
            False,
            f"Jarvis found {name}, but Windows denied permission to close the matching process(es).",
        )

    return ToolResult(False, f"Jarvis could not close {name}.")


def open_url(url: str) -> ToolResult:
    if not url.strip():
        return ToolResult(False, "No URL was provided.")
    target = url.strip()
    if not target.lower().startswith(("http://", "https://")):
        target = "https://" + target
    if webbrowser.open(target):
        return ToolResult(True, f"Opened {target}.")
    return ToolResult(False, f"Could not open {target}.")


def open_path(path: str) -> ToolResult:
    if not path.strip():
        return ToolResult(False, "No path was provided.")
    expanded = Path(os.path.expandvars(os.path.expanduser(path.strip()))).resolve()
    if not expanded.exists():
        return ToolResult(False, f"That path does not exist: {expanded}")
    try:
        if sys.platform == "win32":
            os.startfile(str(expanded))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(expanded)])
        else:
            subprocess.Popen(["xdg-open", str(expanded)])
        return ToolResult(True, f"Opened {expanded}.")
    except OSError as exc:
        return ToolResult(False, f"Could not open {expanded}: {exc}")


def is_minecraft_running() -> bool:
    markers = ("minecraft", "minecraftlauncher", "javaw.exe")
    return any(any(marker in name for marker in markers) for name in _process_names())


def minecraft_status() -> ToolResult:
    if is_minecraft_running():
        return ToolResult(True, "Minecraft appears to be running.")
    return ToolResult(True, "Minecraft does not appear to be running.")


def launch_minecraft() -> ToolResult:
    if sys.platform != "win32":
        return ToolResult(False, "Minecraft launching is currently implemented for Windows only.")
    if is_minecraft_running():
        return ToolResult(True, "Minecraft is already running.")

    attempts: list[tuple[str, list[str] | str]] = [
        ("minecraft URI", "start minecraft:"),
        ("Microsoft Store launcher", ["explorer.exe", "shell:AppsFolder\\Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft"]),
    ]
    for label, command in attempts:
        try:
            if isinstance(command, str):
                subprocess.Popen(command, shell=True)
            else:
                subprocess.Popen(command)
            return ToolResult(True, f"Launch request sent using {label}.")
        except OSError:
            continue

    return ToolResult(False, "Jarvis could not find a usable Minecraft launch method on this PC.")
