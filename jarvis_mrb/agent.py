from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from jarvis_mrb.tools.pc import launch_minecraft, minecraft_status


OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("JARVIS_MODEL", "qwen3.8:27b")


@dataclass(frozen=True)
class AgentReply:
    ok: bool
    message: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _execute_tool(name: str, arguments: dict[str, Any]) -> AgentReply:
    if name == "pc.minecraft_status":
        result = minecraft_status()
        return AgentReply(result.ok, result.message)

    if name == "pc.launch_minecraft":
        result = launch_minecraft()
        return AgentReply(result.ok, result.message)

    if name == "pc.ensure_minecraft_running":
        status = minecraft_status()
        if "does not appear" not in status.message.lower():
            return AgentReply(True, "Minecraft is already running.")
        result = launch_minecraft()
        return AgentReply(result.ok, result.message)

    return AgentReply(False, f"The planner requested an unknown tool: {name}")


def _ollama_plan(text: str) -> dict[str, Any] | None:
    system = """You are Jarvis, a local personal computer assistant.
Choose exactly one of the available tools when a tool can satisfy the user's request.
Do not invent tools. Do not claim an action happened unless a tool is selected.

Available tools:
- pc.minecraft_status: Check whether Minecraft is currently running.
- pc.launch_minecraft: Launch Minecraft if it is not already running.
- pc.ensure_minecraft_running: Ensure Minecraft is running, launching it if necessary.

Return ONLY valid JSON in this exact shape:
{"tool": "tool.name or null", "arguments": {}, "response": "brief response if no tool is needed"}

If the request cannot be completed with the listed tools, set tool to null and explain that briefly in response.
"""

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "options": {"temperature": 0},
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("message", {}).get("content", "")
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def _deterministic_fallback(text: str) -> AgentReply:
    normalized = _normalize(text)
    if not normalized:
        return AgentReply(True, "")

    if normalized in {"quit", "exit"}:
        return AgentReply(True, "__EXIT__")

    if "minecraft" in normalized and any(
        phrase in normalized
        for phrase in ("is running", "is open", "running?", "open?", "status")
    ):
        return _execute_tool("pc.minecraft_status", {})

    if "minecraft" in normalized and any(
        phrase in normalized
        for phrase in ("make sure", "ensure")
    ):
        return _execute_tool("pc.ensure_minecraft_running", {})

    if "minecraft" in normalized and any(
        re.search(rf"\b{verb}\b", normalized)
        for verb in ("open", "launch", "start", "run")
    ):
        return _execute_tool("pc.launch_minecraft", {})

    return AgentReply(
        False,
        "The local model is unavailable or returned an invalid plan, and no deterministic fallback matched.",
    )


def handle_natural_language(text: str) -> AgentReply:
    normalized = _normalize(text)
    if not normalized:
        return AgentReply(True, "")

    if normalized in {"quit", "exit"}:
        return AgentReply(True, "__EXIT__")

    plan = _ollama_plan(text)
    if plan is None:
        return _deterministic_fallback(text)

    tool = plan.get("tool")
    arguments = plan.get("arguments") or {}
    if tool:
        if not isinstance(arguments, dict):
            arguments = {}
        return _execute_tool(str(tool), arguments)

    response = str(plan.get("response") or "I do not have a tool for that yet.")
    return AgentReply(False, response)
