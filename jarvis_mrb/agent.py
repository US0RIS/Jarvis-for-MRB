from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from jarvis_mrb.tools.browser import (
    browser_status,
    close_tab,
    focus_tab,
    list_tabs,
    open_site,
    tab_status,
)
from jarvis_mrb.tools.google import google_status, resolve_contact, send_email
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

_PENDING_EMAIL: dict[str, str] | None = None


@dataclass(frozen=True)
class AgentReply:
    ok: bool
    message: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _result(reply: Any) -> AgentReply:
    return AgentReply(bool(reply.ok), str(reply.message))


def _prepare_email(arguments: dict[str, Any]) -> AgentReply:
    global _PENDING_EMAIL
    recipient = str(arguments.get("recipient") or "").strip()
    body = str(arguments.get("body") or "").strip()
    subject_raw = arguments.get("subject")
    subject = str(subject_raw).strip() if subject_raw else ""
    if not recipient or not body:
        return AgentReply(False, "An email needs both a recipient and message body.")
    resolved = resolve_contact(recipient)
    if not resolved.ok or not resolved.data:
        return AgentReply(False, resolved.message)
    email = str(resolved.data["email"])
    name = str(resolved.data.get("name") or email)
    _PENDING_EMAIL = {"recipient": email, "body": body, "subject": subject}
    subject_line = f" Subject: {subject!r}." if subject else ""
    return AgentReply(True, f"Ready to send email to {name} <{email}>.{subject_line} Body: {body!r} Type 'confirm' to send or 'cancel'.")


def _confirm_pending() -> AgentReply:
    global _PENDING_EMAIL
    if not _PENDING_EMAIL:
        return AgentReply(False, "There is nothing waiting for confirmation.")
    pending = _PENDING_EMAIL
    _PENDING_EMAIL = None
    result = send_email(recipient=pending["recipient"], body=pending["body"], subject=pending.get("subject") or None)
    return AgentReply(result.ok, result.message)


def _cancel_pending() -> AgentReply:
    global _PENDING_EMAIL
    if not _PENDING_EMAIL:
        return AgentReply(False, "There is nothing waiting for confirmation.")
    _PENDING_EMAIL = None
    return AgentReply(True, "Cancelled.")


def _smart_status(name: str) -> AgentReply:
    bstatus = browser_status()
    if bstatus.ok:
        tab = tab_status(name)
        if tab.ok and "no open browser tab matches" not in tab.message.lower():
            return _result(tab)
    return _result(app_status(name))


def _smart_open(name: str) -> AgentReply:
    bstatus = browser_status()
    if bstatus.ok:
        tab = tab_status(name)
        if tab.ok and "no open browser tab matches" not in tab.message.lower():
            return _result(focus_tab(name))
        web = open_site(name)
        if web.ok:
            return _result(web)
    return _result(launch_app(name))


def _smart_close(name: str) -> AgentReply:
    bstatus = browser_status()
    if bstatus.ok:
        tab = tab_status(name)
        if tab.ok and "no open browser tab matches" not in tab.message.lower():
            return _result(close_tab(name))
    return _result(close_app(name))


def _execute_tool(name: str, arguments: dict[str, Any]) -> AgentReply:
    if name == "smart.status":
        return _smart_status(str(arguments.get("name") or ""))
    if name == "smart.open":
        return _smart_open(str(arguments.get("name") or ""))
    if name == "smart.close":
        return _smart_close(str(arguments.get("name") or ""))
    if name == "browser.status":
        return _result(browser_status())
    if name == "browser.list_tabs":
        return _result(list_tabs())
    if name == "browser.tab_status":
        return _result(tab_status(str(arguments.get("query") or "")))
    if name == "browser.close_tab":
        return _result(close_tab(str(arguments.get("query") or "")))
    if name == "browser.focus_tab":
        return _result(focus_tab(str(arguments.get("query") or "")))
    if name == "browser.open_site":
        return _result(open_site(str(arguments.get("query") or "")))
    if name == "pc.minecraft_status":
        return _result(minecraft_status())
    if name == "pc.launch_minecraft":
        return _result(launch_minecraft())
    if name == "pc.ensure_minecraft_running":
        status = minecraft_status()
        if "does not appear" not in status.message.lower():
            return AgentReply(True, "Minecraft is already running.")
        return _result(launch_minecraft())
    if name == "pc.app_status":
        return _result(app_status(str(arguments.get("name") or "")))
    if name == "pc.launch_app":
        return _result(launch_app(str(arguments.get("name") or "")))
    if name == "pc.close_app":
        return _result(close_app(str(arguments.get("name") or "")))
    if name == "pc.list_running_apps":
        return _result(list_running_apps(int(arguments.get("limit") or 30)))
    if name == "pc.open_url":
        return _result(open_url(str(arguments.get("url") or "")))
    if name == "pc.open_path":
        return _result(open_path(str(arguments.get("path") or "")))
    if name == "google.status":
        result = google_status()
        return AgentReply(result.ok, result.message)
    if name == "contacts.resolve":
        result = resolve_contact(str(arguments.get("query") or ""))
        return AgentReply(result.ok, result.message)
    if name == "gmail.prepare_send":
        return _prepare_email(arguments)
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
    normalized = _normalize(text)
    if normalized in {"confirm", "yes send it", "send it", "yes, send it"}:
        return _confirm_pending()
    if normalized in {"cancel", "never mind", "nevermind", "don't send it", "do not send it"}:
        return _cancel_pending()
    if normalized in {"browser status", "opera status", "is browser control connected", "is browser control connected?"}:
        return _execute_tool("browser.status", {})
    if normalized in {"list tabs", "show tabs", "what tabs are open", "what tabs are open?"}:
        return _execute_tool("browser.list_tabs", {})
    if normalized in {"google status", "gmail status", "is gmail connected", "is gmail connected?"}:
        return _execute_tool("google.status", {})
    if normalized in {"what is running", "what's running", "list running apps", "list running processes"}:
        return _execute_tool("pc.list_running_apps", {})

    status_match = re.fullmatch(r"(?:is|check if|check whether) (.+?) (?:running|open)\??", normalized)
    if status_match:
        return _execute_tool("smart.status", {"name": status_match.group(1)})

    close_match = re.fullmatch(r"(?:close|quit|stop|kill) (.+?)[?.!]?", normalized)
    if close_match:
        return _execute_tool("smart.close", {"name": close_match.group(1)})

    open_match = re.fullmatch(r"(?:open|launch|start|run) (.+?)(?: for me)?[?.!]?", normalized)
    if open_match:
        target = open_match.group(1).strip()
        if target.startswith(("http://", "https://", "www.")) or ("." in target and " " not in target):
            return _execute_tool("pc.open_url", {"url": target})
        if re.match(r"^[a-z]:\\", target) or target.startswith(("~", ".\\", "\\\\")):
            return _execute_tool("pc.open_path", {"path": target})
        return _execute_tool("smart.open", {"name": target})

    if normalized in {"minecraft status", "check minecraft", "make sure minecraft is running", "make sure minecraft is open", "ensure minecraft is running", "ensure minecraft is open"}:
        tool = "pc.ensure_minecraft_running" if any(x in normalized for x in ("make sure", "ensure")) else "pc.minecraft_status"
        return _execute_tool(tool, {})
    return None


def _ollama_plan(text: str) -> tuple[dict[str, Any] | None, str]:
    system = """You are the tool router for Jarvis, a local personal assistant. Thinking is disabled because latency matters.
Choose exactly one listed tool when a tool can satisfy the user's request. Do not invent tools. Preserve user constraints exactly, especially wording/style constraints in messages. Never claim an action happened unless a tool is selected.

Prefer smart.open/smart.close/smart.status for ordinary names because Jarvis will check browser tabs first and then native apps.

Tools:
- smart.status {name}: check browser tabs first, then native app/process status
- smart.open {name}: focus an existing matching browser tab, otherwise open a known website, otherwise launch a native app
- smart.close {name}: close a matching browser tab first, otherwise close the native app
- browser.status {}: check whether Opera/Chromium DevTools control is connected
- browser.list_tabs {}: list open browser tabs
- browser.tab_status {query}: find a browser tab by title or URL
- browser.close_tab {query}: close matching browser tabs only
- browser.focus_tab {query}: focus a matching browser tab
- browser.open_site {query}: focus/open a known site such as Spotify, YouTube, Gmail, or ChatGPT
- pc.app_status {name}: check only native app/process status
- pc.launch_app {name}: launch only a native application
- pc.close_app {name}: close only a native application
- pc.list_running_apps {limit}: list running processes
- pc.open_url {url}: open a web URL
- pc.open_path {path}: open a local file or folder
- pc.minecraft_status {}: check Minecraft
- pc.launch_minecraft {}: launch Minecraft
- pc.ensure_minecraft_running {}: ensure Minecraft is running
- google.status {}: check Gmail/Contacts connection
- contacts.resolve {query}: resolve a person's name to an email address
- gmail.prepare_send {recipient, body, subject}: prepare an email for user confirmation. subject may be null when the user did not specify one.

Email rules:
- Do not add emojis unless the user asks for them.
- Do not add facts, promises, greetings, signatures, or extra content the user did not request.
- For 'email X saying Y', put the requested meaning in body and leave subject null unless a subject was requested or clearly necessary.
- gmail.prepare_send NEVER sends immediately; Jarvis will ask the user to confirm.

Examples:
User: Close Spotify.
Assistant: {"tool":"smart.close","arguments":{"name":"Spotify"},"response":""}
User: Is YouTube open?
Assistant: {"tool":"smart.status","arguments":{"name":"YouTube"},"response":""}
User: Open Spotify.
Assistant: {"tool":"smart.open","arguments":{"name":"Spotify"},"response":""}
User: Email alex@example.com saying that I can talk later and make sure not to use emojis.
Assistant: {"tool":"gmail.prepare_send","arguments":{"recipient":"alex@example.com","body":"I can talk later.","subject":null},"response":""}

Return one JSON object only with keys tool, arguments, response. Never wrap it in markdown."""

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


def handle_natural_language(text: str) -> AgentReply:
    normalized = _normalize(text)
    if not normalized:
        return AgentReply(True, "")
    if normalized in {"quit", "exit"}:
        return AgentReply(True, "__EXIT__")
    if normalized in {"model", "what model are you using", "what model are you using?"}:
        return AgentReply(True, f"Planner model: {OLLAMA_MODEL} via Ollama at {OLLAMA_URL}; thinking off; keep-alive {OLLAMA_KEEP_ALIVE}")
    fast = _fast_path(text)
    if fast is not None:
        return fast
    plan, error = _ollama_plan(text)
    if plan is None:
        return AgentReply(False, error)
    tool = plan.get("tool")
    arguments = plan.get("arguments") or {}
    if tool:
        if not isinstance(arguments, dict):
            arguments = {}
        return _execute_tool(str(tool), arguments)
    return AgentReply(False, str(plan.get("response") or "I do not have a tool for that yet."))
