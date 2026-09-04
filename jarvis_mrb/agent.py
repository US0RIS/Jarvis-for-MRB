from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from jarvis_mrb.jobs import cancel_job, create_event_job, create_time_job, list_jobs
from jarvis_mrb.permissions import decide, policy_summary, set_policy
from jarvis_mrb.tools.browser import browser_status, close_tab, focus_tab, list_tabs, open_site, tab_status
from jarvis_mrb.tools.google import (
    create_calendar_event,
    google_status,
    list_calendar_events,
    resolve_contact,
    send_email,
)
from jarvis_mrb.tools.pc import (
    app_status,
    close_app,
    launch_app,
    launch_minecraft,
    list_running_apps,
    minecraft_status,
    open_path,
    open_url,
)

OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("JARVIS_MODEL", "qwen3.8:27b")
OLLAMA_KEEP_ALIVE = os.environ.get("JARVIS_OLLAMA_KEEP_ALIVE", "30m")

_PENDING_ACTION: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentReply:
    ok: bool
    message: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _result(reply: Any) -> AgentReply:
    return AgentReply(bool(reply.ok), str(reply.message))


def _matching_tab_exists(name: str) -> bool:
    tab = tab_status(name)
    return bool(tab.ok and isinstance(tab.data, list) and tab.data)


def _smart_status(name: str) -> AgentReply:
    if browser_status().ok and _matching_tab_exists(name):
        return _result(tab_status(name))
    return _result(app_status(name))


def _smart_open(name: str) -> AgentReply:
    if browser_status().ok:
        if _matching_tab_exists(name):
            return _result(focus_tab(name))
        web = open_site(name)
        if web.ok:
            return _result(web)
    return _result(launch_app(name))


def _smart_close(name: str) -> AgentReply:
    if browser_status().ok and _matching_tab_exists(name):
        return _result(close_tab(name))
    return _result(close_app(name))


def _describe_action(tool: str, args: dict[str, Any]) -> str:
    if tool == "gmail.send":
        subject = f" subject {args.get('subject')!r}," if args.get("subject") else ""
        return f"send email to {args.get('recipient')!r},{subject} body {args.get('body')!r}"
    if tool == "calendar.create":
        return f"create calendar event {args.get('summary')!r} from {args.get('start')} to {args.get('end')}"
    if tool in {"smart.close", "pc.close_app", "browser.close_tab"}:
        return f"close {args.get('name') or args.get('query')!r}"
    if tool == "jobs.cancel":
        return f"cancel job {args.get('job_id')}"
    return f"run {tool} with {args}"


def _execute_unchecked(tool: str, args: dict[str, Any]) -> AgentReply:
    if tool == "smart.status":
        return _smart_status(str(args.get("name") or ""))
    if tool == "smart.open":
        return _smart_open(str(args.get("name") or ""))
    if tool == "smart.close":
        return _smart_close(str(args.get("name") or ""))
    if tool == "browser.status":
        return _result(browser_status())
    if tool == "browser.list_tabs":
        return _result(list_tabs())
    if tool == "browser.tab_status":
        return _result(tab_status(str(args.get("query") or "")))
    if tool == "browser.close_tab":
        return _result(close_tab(str(args.get("query") or "")))
    if tool == "browser.focus_tab":
        return _result(focus_tab(str(args.get("query") or "")))
    if tool == "browser.open_site":
        return _result(open_site(str(args.get("query") or "")))
    if tool == "pc.minecraft_status":
        return _result(minecraft_status())
    if tool == "pc.launch_minecraft":
        return _result(launch_minecraft())
    if tool == "pc.ensure_minecraft_running":
        status = minecraft_status()
        return AgentReply(True, "Minecraft is already running.") if "does not appear" not in status.message.lower() else _result(launch_minecraft())
    if tool == "pc.app_status":
        return _result(app_status(str(args.get("name") or "")))
    if tool == "pc.launch_app":
        return _result(launch_app(str(args.get("name") or "")))
    if tool == "pc.close_app":
        return _result(close_app(str(args.get("name") or "")))
    if tool == "pc.list_running_apps":
        return _result(list_running_apps(int(args.get("limit") or 30)))
    if tool == "pc.open_url":
        return _result(open_url(str(args.get("url") or "")))
    if tool == "pc.open_path":
        return _result(open_path(str(args.get("path") or "")))
    if tool == "google.status":
        return _result(google_status())
    if tool == "contacts.resolve":
        return _result(resolve_contact(str(args.get("query") or "")))
    if tool == "gmail.send":
        recipient = str(args.get("recipient") or "").strip()
        body = str(args.get("body") or "").strip()
        if not recipient or not body:
            return AgentReply(False, "Email requires a recipient and body.")
        return _result(send_email(recipient, body, str(args.get("subject") or "").strip() or None))
    if tool == "calendar.list":
        return _result(list_calendar_events(int(args.get("days") or 7), int(args.get("limit") or 10)))
    if tool == "calendar.create":
        return _result(create_calendar_event(
            str(args.get("summary") or ""),
            str(args.get("start") or ""),
            str(args.get("end") or ""),
            str(args.get("description") or "").strip() or None,
        ))
    if tool == "jobs.list":
        return _result(list_jobs())
    if tool == "jobs.create_time":
        return _result(create_time_job(str(args.get("when") or ""), str(args.get("command") or "")))
    if tool == "jobs.create_event":
        return _result(create_event_job(str(args.get("event") or ""), str(args.get("command") or "")))
    if tool == "jobs.cancel":
        return _result(cancel_job(int(args.get("job_id") or 0)))
    return AgentReply(False, f"The planner requested an unknown tool: {tool}")


def execute_tool(tool: str, args: dict[str, Any], *, bypass_confirmation: bool = False) -> AgentReply:
    global _PENDING_ACTION
    decision = decide(tool)
    if not decision.allowed:
        return AgentReply(False, f"Permission policy denies {decision.risk} actions such as {tool}.")
    if decision.needs_confirmation and not bypass_confirmation:
        _PENDING_ACTION = {"tool": tool, "args": args}
        return AgentReply(True, f"Ready to {_describe_action(tool, args)}. Say 'confirm' to proceed or 'cancel'.")
    return _execute_unchecked(tool, args)


def _confirm_pending() -> AgentReply:
    global _PENDING_ACTION
    if not _PENDING_ACTION:
        return AgentReply(False, "There is nothing waiting for confirmation.")
    pending = _PENDING_ACTION
    _PENDING_ACTION = None
    return execute_tool(str(pending["tool"]), dict(pending["args"]), bypass_confirmation=True)


def _cancel_pending() -> AgentReply:
    global _PENDING_ACTION
    if not _PENDING_ACTION:
        return AgentReply(False, "There is nothing waiting for confirmation.")
    _PENDING_ACTION = None
    return AgentReply(True, "Cancelled.")


def _extract_json(content: str) -> dict[str, Any] | None:
    content = content.strip()
    if not content:
        return None
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def _fast_path(text: str) -> AgentReply | None:
    n = _normalize(text)
    if n in {"confirm", "yes send it", "send it", "yes, send it", "yes do it", "do it"}:
        return _confirm_pending()
    if n in {"cancel", "never mind", "nevermind", "don't do it", "do not do it", "don't send it"}:
        return _cancel_pending()
    if n in {"permissions", "permission status", "permissions status"}:
        return AgentReply(True, "Permission policy: " + policy_summary())
    policy_match = re.fullmatch(r"set (read|local_write|external_write|destructive|security) (?:actions )?to (auto|confirm|deny)", n)
    if policy_match:
        return AgentReply(True, set_policy(policy_match.group(1), policy_match.group(2)))
    if n in {"browser status", "opera status", "is browser control connected", "is browser control connected?"}:
        return execute_tool("browser.status", {})
    if n in {"list tabs", "show tabs", "what tabs are open", "what tabs are open?"}:
        return execute_tool("browser.list_tabs", {})
    if n in {"google status", "gmail status", "calendar status", "is gmail connected", "is gmail connected?"}:
        return execute_tool("google.status", {})
    if n in {"what is running", "what's running", "list running apps", "list running processes"}:
        return execute_tool("pc.list_running_apps", {})
    if n in {"list jobs", "show jobs", "what jobs are scheduled", "what jobs are scheduled?"}:
        return execute_tool("jobs.list", {})
    cancel_match = re.fullmatch(r"cancel job (\d+)", n)
    if cancel_match:
        return execute_tool("jobs.cancel", {"job_id": int(cancel_match.group(1))})

    event_match = re.fullmatch(r"when i (?:get|arrive) home,? (.+)", n)
    if event_match:
        return execute_tool("jobs.create_event", {"event": "home_arrival", "command": event_match.group(1)})

    status_match = re.fullmatch(r"(?:is|check if|check whether) (.+?) (?:running|open)\??", n)
    if status_match:
        return execute_tool("smart.status", {"name": status_match.group(1)})
    close_match = re.fullmatch(r"(?:close|quit|stop|kill) (.+?)[?.!]?", n)
    if close_match:
        return execute_tool("smart.close", {"name": close_match.group(1)})
    open_match = re.fullmatch(r"(?:open|launch|start|run) (.+?)(?: for me)?[?.!]?", n)
    if open_match:
        target = open_match.group(1).strip()
        if target.startswith(("http://", "https://", "www.")) or ("." in target and " " not in target):
            return execute_tool("pc.open_url", {"url": target})
        if re.match(r"^[a-z]:\\", target) or target.startswith(("~", ".\\", "\\\\")):
            return execute_tool("pc.open_path", {"path": target})
        return execute_tool("smart.open", {"name": target})
    return None


def _ollama_plan(text: str) -> tuple[dict[str, Any] | None, str]:
    now = datetime.now().astimezone().isoformat()
    system = f"""You are the tool router for Jarvis, a local personal assistant. Current local date/time: {now}.
Thinking is disabled because latency matters. Choose exactly one listed tool. Do not invent tools. Preserve user constraints exactly.
Prefer smart.open/smart.close/smart.status for ordinary app/site names.

Tools:
smart.status {{name}}; smart.open {{name}}; smart.close {{name}};
browser.status {{}}; browser.list_tabs {{}}; browser.tab_status {{query}}; browser.close_tab {{query}}; browser.focus_tab {{query}}; browser.open_site {{query}};
pc.app_status {{name}}; pc.launch_app {{name}}; pc.close_app {{name}}; pc.list_running_apps {{limit}}; pc.open_url {{url}}; pc.open_path {{path}};
pc.minecraft_status {{}}; pc.launch_minecraft {{}}; pc.ensure_minecraft_running {{}};
google.status {{}}; contacts.resolve {{query}}; gmail.send {{recipient,body,subject}};
calendar.list {{days,limit}}; calendar.create {{summary,start,end,description}};
jobs.list {{}}; jobs.create_time {{when,command}}; jobs.create_event {{event,command}}; jobs.cancel {{job_id}}.

Rules:
- gmail.send: body should contain only the requested meaning; no emoji/greeting/signature unless requested. subject may be null.
- calendar.create: start/end must be timezone-aware ISO 8601 strings. Infer a reasonable one-hour duration only if user gives a start but no duration/end.
- For future commands like 'at 8pm open Spotify', use jobs.create_time and preserve the action as a short natural-language command.
- For 'when I get home ...', use jobs.create_event with event='home_arrival'.
- Never claim an action happened unless a tool is selected.
Return one JSON object only: {{"tool":"name or null","arguments":{{}},"response":"..."}}.
"""
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
        "options": {"temperature": 0},
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        parsed = _extract_json(str(data.get("message", {}).get("content", "")))
        return (parsed, "") if parsed is not None else (None, "Ollama responded, but Jarvis could not parse its tool plan.")
    except httpx.ConnectError:
        return None, f"Cannot connect to Ollama at {OLLAMA_URL}. Is Ollama running?"
    except httpx.TimeoutException:
        return None, f"Ollama model {OLLAMA_MODEL} timed out while planning."
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        return None, f"Ollama planner error: {exc}"


def handle_natural_language(text: str) -> AgentReply:
    n = _normalize(text)
    if not n:
        return AgentReply(True, "")
    if n in {"quit", "exit"}:
        return AgentReply(True, "__EXIT__")
    if n in {"model", "what model are you using", "what model are you using?"}:
        return AgentReply(True, f"Planner model: {OLLAMA_MODEL} via Ollama at {OLLAMA_URL}; thinking off; keep-alive {OLLAMA_KEEP_ALIVE}")
    fast = _fast_path(text)
    if fast is not None:
        return fast
    plan, error = _ollama_plan(text)
    if plan is None:
        return AgentReply(False, error)
    tool = plan.get("tool")
    args = plan.get("arguments") or {}
    if tool:
        return execute_tool(str(tool), args if isinstance(args, dict) else {})
    return AgentReply(False, str(plan.get("response") or "I do not have a tool for that yet."))
