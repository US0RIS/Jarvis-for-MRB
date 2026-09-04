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
OLLAMA_KEEP_ALIVE = os.environ.get("JARVIS_OLLAMA_KEEP_ALIVE", "30m")


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


def _extract_json(content: str) -> dict[str, Any] | None:
    content = content.strip()
    if not content:
        return None
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _fast_path(text: str) -> AgentReply | None:
    """Handle obvious, low-risk commands without invoking the LLM.

    Jarvis should not spend seconds asking a 27B model to decide that
    'is Minecraft running?' maps to the Minecraft status tool. Ambiguous
    requests still go to the model.
    """
    normalized = _normalize(text)

    status_exact = {
        "is minecraft running",
        "is minecraft running?",
        "is minecraft open",
        "is minecraft open?",
        "minecraft status",
        "check minecraft",
        "check if minecraft is running",
        "check whether minecraft is running",
    }
    if normalized in status_exact:
        return _execute_tool("pc.minecraft_status", {})

    launch_exact = {
        "open minecraft",
        "launch minecraft",
        "start minecraft",
        "run minecraft",
        "can you open minecraft for me?",
        "can you open minecraft for me",
    }
    if normalized in launch_exact:
        return _execute_tool("pc.launch_minecraft", {})

    ensure_exact = {
        "make sure minecraft is running",
        "make sure minecraft is open",
        "ensure minecraft is running",
        "ensure minecraft is open",
    }
    if normalized in ensure_exact:
        return _execute_tool("pc.ensure_minecraft_running", {})

    return None


def _ollama_plan(text: str) -> tuple[dict[str, Any] | None, str]:
    system = """You are the tool router for Jarvis, a local personal computer assistant.
Choose exactly one listed tool when it can satisfy the user's request. Do not invent tools.

Tools:
- pc.minecraft_status: check whether Minecraft is running
- pc.launch_minecraft: launch Minecraft if it is not running
- pc.ensure_minecraft_running: make sure Minecraft is running, launching it if needed

Examples:
User: Could you check whether I forgot to leave Minecraft running?
Assistant: {\"tool\":\"pc.minecraft_status\",\"arguments\":{},\"response\":\"\"}
User: Get Minecraft ready for me.
Assistant: {\"tool\":\"pc.ensure_minecraft_running\",\"arguments\":{},\"response\":\"\"}
User: Close Minecraft.
Assistant: {\"tool\":null,\"arguments\":{},\"response\":\"I don't have a tool to close Minecraft yet.\"}

Return one JSON object only, with keys tool, arguments, response. Never wrap it in markdown."""
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "options": {"temperature": 0},
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = str(data.get("message", {}).get("content", ""))
        parsed = _extract_json(content)
        if parsed is None:
            return None, "Ollama responded, but Jarvis could not parse its tool plan."
        return parsed, ""
    except httpx.ConnectError:
        return None, f"Cannot connect to Ollama at {OLLAMA_URL}. Is Ollama running?"
    except httpx.TimeoutException:
        return None, f"Ollama model {OLLAMA_MODEL} timed out while planning."
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        return None, f"Ollama planner error: {exc}"


def _deterministic_fallback(text: str) -> AgentReply | None:
    normalized = _normalize(text)
    if "minecraft" in normalized and any(
        phrase in normalized for phrase in ("is running", "is open", "running?", "open?", "status")
    ):
        return _execute_tool("pc.minecraft_status", {})
    if "minecraft" in normalized and any(phrase in normalized for phrase in ("make sure", "ensure")):
        return _execute_tool("pc.ensure_minecraft_running", {})
    if "minecraft" in normalized and any(
        re.search(rf"\b{verb}\b", normalized) for verb in ("open", "launch", "start", "run")
    ):
        return _execute_tool("pc.launch_minecraft", {})
    return None


def handle_natural_language(text: str) -> AgentReply:
    normalized = _normalize(text)
    if not normalized:
        return AgentReply(True, "")
    if normalized in {"quit", "exit"}:
        return AgentReply(True, "__EXIT__")
    if normalized in {"model", "what model are you using", "what model are you using?"}:
        return AgentReply(
            True,
            f"Planner model: {OLLAMA_MODEL} via Ollama at {OLLAMA_URL}; thinking off; keep-alive {OLLAMA_KEEP_ALIVE}",
        )

    fast = _fast_path(text)
    if fast is not None:
        return fast

    plan, error = _ollama_plan(text)
    if plan is not None:
        tool = plan.get("tool")
        arguments = plan.get("arguments") or {}
        if tool:
            if not isinstance(arguments, dict):
                arguments = {}
            return _execute_tool(str(tool), arguments)
        return AgentReply(False, str(plan.get("response") or "I do not have a tool for that yet."))

    fallback = _deterministic_fallback(text)
    if fallback is not None:
        return AgentReply(fallback.ok, f"{fallback.message} [planner fallback: {error}]")
    return AgentReply(False, error)
