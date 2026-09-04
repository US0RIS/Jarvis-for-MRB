from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
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


def is_minecraft_running() -> bool:
    markers = (
        "minecraft",
        "minecraftlauncher",
        "javaw.exe",
    )
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
        (
            "Microsoft Store launcher",
            ["explorer.exe", "shell:AppsFolder\\Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft"],
        ),
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

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    launcher = os.path.join(
        local_app_data,
        "Packages",
        "Microsoft.4297127D64EC6_8wekyb3d8bbwe",
    )
    if launcher and os.path.exists(launcher):
        return ToolResult(
            False,
            "Minecraft is installed, but Jarvis could not locate a launchable entry point. "
            "Open Minecraft once manually, then retry.",
        )

    return ToolResult(False, "Jarvis could not find a usable Minecraft launch method on this PC.")
