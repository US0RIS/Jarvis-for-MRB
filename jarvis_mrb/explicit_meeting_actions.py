from __future__ import annotations

"""Only machine-readable, explicitly supplied meeting action records.

Not a substitute for Qwen when a real meeting transcript contains prose,
ambiguous speaker turns or inferred obligations.
"""
import re


def extract_structured_actions(transcript: str) -> list[dict[str, str]] | None:
    """All lines must be ACTION: owner | task | explicit due date or '-'.

    If any non-empty line is not structured, return None and let the existing
    semantic transcript extractor decide. Never invent an owner or deadline.
    """
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    if not lines or len(lines) > 12:
        return None
    actions: list[dict[str, str]] = []
    for line in lines:
        matched = re.fullmatch(
            r"(?:action|action item|todo):\s*([^|]{2,120})\s*\|\s*"
            r"([^|]{2,500})\s*\|\s*([^|]{1,160})",
            line,
            flags=re.IGNORECASE,
        )
        if not matched:
            return None
        owner, task, due = (" ".join(value.split()) for value in matched.groups())
        if (
            not owner or not task or not due
            or owner.lower() in {"unknown", "them", "someone", "he", "she", "they"}
        ):
            return None
        if due.lower() in {"-", "none", "no deadline", "not specified"}:
            due = ""
        actions.append({
            "owner": owner[:120],
            "task": task[:500],
            "due": due[:160],
            "evidence": line[:300],
        })
    return actions
