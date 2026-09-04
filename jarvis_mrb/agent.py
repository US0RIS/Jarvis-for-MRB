from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis_mrb.tools.pc import launch_minecraft, minecraft_status


@dataclass(frozen=True)
class AgentReply:
    ok: bool
    message: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def handle_natural_language(text: str) -> AgentReply:
    """Translate a small set of ordinary-language requests into explicit tools.

    This is intentionally deterministic for milestone 2. The API boundary is the
    same one a model-based planner will call later, so adding an LLM does not
    require changing the PC execution layer.
    """
    normalized = _normalize(text)
    if not normalized:
        return AgentReply(True, "")

    if normalized in {"quit", "exit"}:
        return AgentReply(True, "__EXIT__")

    status_patterns = (
        "is minecraft running",
        "is minecraft open",
        "check minecraft",
        "check if minecraft is running",
        "check whether minecraft is running",
        "minecraft status",
    )
    if normalized in status_patterns or (
        "minecraft" in normalized
        and any(phrase in normalized for phrase in ("is running", "is open", "running?", "open?"))
    ):
        result = minecraft_status()
        return AgentReply(result.ok, result.message)

    ensure_patterns = (
        "make sure minecraft is running",
        "make sure minecraft is open",
        "ensure minecraft is running",
        "ensure minecraft is open",
    )
    if normalized in ensure_patterns:
        status = minecraft_status()
        if "does not appear" not in status.message.lower():
            return AgentReply(True, "Minecraft is already running.")
        result = launch_minecraft()
        return AgentReply(result.ok, result.message)

    launch_verbs = ("open", "launch", "start", "run")
    if "minecraft" in normalized and any(
        re.search(rf"\b{verb}\b", normalized) for verb in launch_verbs
    ):
        result = launch_minecraft()
        return AgentReply(result.ok, result.message)

    if normalized in {"help", "what can you do", "what can you do?"}:
        return AgentReply(
            True,
            "Try ordinary language such as 'Open Minecraft', 'Is Minecraft running?', "
            "or 'Make sure Minecraft is running'.",
        )

    return AgentReply(
        False,
        "I understood the request as natural language, but I do not have a matching tool yet.",
    )
