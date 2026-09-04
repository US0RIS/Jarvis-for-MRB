from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

import httpx

from jarvis_mrb.agent import (
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_URL,
    AgentReply,
    _fast_path,
    _respectful,
    execute_tool,
    handle_natural_language,
)
from jarvis_mrb.conversation import ConversationMessage


class StreamingAgentError(RuntimeError):
    pass


def _planner_system(now: str) -> str:
    return f"""You are Jarvis, a composed, highly capable personal aide and tool router. Current local date/time: {now}.
Address the user respectfully, but DO NOT write 'sir' in the conversational body because the transport prepends it. Be calm, concise, precise, and understated. Thinking is disabled because latency matters.

Use recent conversation to resolve pronouns, omitted subjects, follow-ups, names, recipients, and references such as 'it', 'him', 'that one', 'the same thing', or 'what about tomorrow'. Preserve user constraints exactly.

You MUST use this streaming protocol:
1. Your FIRST output line must be exactly one compact JSON object with keys tool and arguments, for example:
{{"tool":null,"arguments":{{}}}}
or
{{"tool":"calendar.query","arguments":{{"direction":"future","days":7,"limit":5}}}}
2. End that JSON object with a newline immediately.
3. If tool is null, continue after the newline with the natural-language answer and stream it normally.
4. If tool is not null, output NOTHING after the first newline. Jarvis will execute the tool itself.
Never wrap the first line in Markdown or code fences.

Tools:
smart.status {{name}}; smart.open {{name}}; smart.close {{name}};
browser.status {{}}; browser.list_tabs {{}}; browser.tab_status {{query}}; browser.close_tab {{query}}; browser.focus_tab {{query}}; browser.open_site {{query}};
pc.app_status {{name}}; pc.launch_app {{name}}; pc.close_app {{name}}; pc.list_running_apps {{limit}}; pc.open_url {{url}}; pc.open_path {{path}};
pc.minecraft_status {{}}; pc.launch_minecraft {{}}; pc.ensure_minecraft_running {{}};
google.status {{}}; contacts.resolve {{query}}; gmail.query {{query,limit}}; gmail.send {{recipient,body,subject}};
calendar.list {{days,limit}}; calendar.recent {{days_back}}; calendar.query {{direction,days,limit,query,start,end}}; calendar.create {{summary,start,end,description}};
jobs.list {{}}; jobs.create_time {{when,command}}; jobs.create_event {{event,command}}; jobs.cancel {{job_id}}.

Routing rules:
- Gmail read/check/find/search/review received mail -> gmail.query. Use Gmail search syntax. Latest inbox email: query='in:inbox', limit=1. Unread inbox: query='is:unread in:inbox'. Never request more than 10.
- Gmail send -> gmail.send. Resolve recipient from conversation when unambiguous. Preserve the requested body exactly in meaning. Sending is protected by confirmation and the backend allowlist.
- Calendar past -> calendar.query direction='past'; future -> direction='future'; last/most recent -> calendar.recent. Use timezone-aware ISO ranges when an exact date is inferred.
- Ordinary app/site actions -> smart.open/smart.close/smart.status.
- 'at 8pm open Spotify' -> jobs.create_time. 'when I get home ...' -> jobs.create_event event='home_arrival'.
- Never claim an action occurred unless a tool was selected.
- If no tool is required, keep the answer voice-friendly: usually 1-4 short sentences unless the user explicitly requests detail.
"""


def _parse_plan(line: str) -> dict[str, Any] | None:
    candidate = line.strip()
    if not candidate:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _lower_first_alpha(text: str) -> str:
    chars = list(text)
    for index, character in enumerate(chars):
        if character.isalpha():
            chars[index] = character.lower()
            break
    return "".join(chars)


def _fallback(text: str, history: Sequence[ConversationMessage] | None) -> Iterator[str]:
    reply = handle_natural_language(text, history=history)
    if reply.message and reply.message != "__EXIT__":
        yield reply.message


def stream_natural_language(
    text: str,
    history: Sequence[ConversationMessage] | None = None,
) -> Iterator[str]:
    """Yield response text as soon as it becomes available.

    Deterministic fast paths remain immediate. Non-trivial requests use a one-line
    tool plan followed by the conversational body in the *same* Ollama stream.
    For a no-tool turn, the body is forwarded token-by-token after the first
    newline instead of waiting for Qwen to finish the entire response.
    """
    stripped = text.strip()
    if not stripped:
        return

    normalized = " ".join(stripped.lower().split())
    if normalized in {"quit", "exit"}:
        return
    if normalized in {"model", "what model are you using", "what model are you using?"}:
        yield _respectful(AgentReply(True, f"Planner model: {OLLAMA_MODEL}; thinking off; keep-alive {OLLAMA_KEEP_ALIVE}")).message
        return

    fast = _fast_path(stripped)
    if fast is not None:
        message = _respectful(fast).message
        if message and message != "__EXIT__":
            yield message
        return

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _planner_system(datetime.now().astimezone().isoformat())}
    ]
    for item in history or ():
        if item.role in {"user", "assistant"} and item.content.strip():
            messages.append({"role": item.role, "content": item.content})
    messages.append({"role": "user", "content": stripped})

    payload = {
        "model": OLLAMA_MODEL,
        "stream": True,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "messages": messages,
        "options": {"temperature": 0},
    }

    plan_buffer = ""
    plan: dict[str, Any] | None = None
    body_started = False
    emitted_body = False
    first_body_chunk = True

    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=3.0)) as client:
            with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        packet = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    chunk = str(packet.get("message", {}).get("content", ""))
                    if not chunk:
                        continue

                    if plan is None:
                        plan_buffer += chunk
                        if "\n" not in plan_buffer:
                            if len(plan_buffer) > 4096:
                                break
                            continue
                        first_line, remainder = plan_buffer.split("\n", 1)
                        plan = _parse_plan(first_line)
                        if plan is None:
                            break

                        tool = plan.get("tool")
                        args = plan.get("arguments") or {}
                        if tool:
                            reply = _respectful(
                                execute_tool(str(tool), args if isinstance(args, dict) else {})
                            )
                            if reply.message and reply.message != "__EXIT__":
                                yield reply.message
                            return

                        # Guarantee the preferred form of address without waiting
                        # for the model to finish enough text to inspect its prose.
                        yield "Sir, "
                        body_started = True
                        if remainder:
                            emitted_body = True
                            first_body_chunk = False
                            yield _lower_first_alpha(remainder)
                        continue

                    if body_started:
                        emitted_body = True
                        if first_body_chunk:
                            first_body_chunk = False
                            yield _lower_first_alpha(chunk)
                        else:
                            yield chunk

                if plan is not None and not plan.get("tool") and body_started:
                    if not emitted_body:
                        yield "I'm listening."
                    return

    except (httpx.HTTPError, ValueError, TypeError):
        pass

    # Protocol violations or transient stream failures fall back to the proven
    # non-streaming path rather than returning a partial or malformed answer.
    yield from _fallback(stripped, history)
