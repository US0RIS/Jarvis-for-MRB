from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from jarvis_mrb.tools.browser import browser_status, close_tab, focus_tab, list_tabs, open_site, tab_status
from jarvis_mrb.tools.google import google_status, resolve_contact, send_email
from jarvis_mrb.tools.pc import app_status, close_app, launch_app, launch_minecraft, list_running_apps, minecraft_status, open_path, open_url

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
    recipient = str(arguments.get("recipient") or "").strip(); body = str(arguments.get("body") or "").strip()
    subject_raw = arguments.get("subject"); subject = str(subject_raw).strip() if subject_raw else ""
    if not recipient or not body: return AgentReply(False, "An email needs both a recipient and message body.")
    resolved = resolve_contact(recipient)
    if not resolved.ok or not resolved.data: return AgentReply(False, resolved.message)
    email = str(resolved.data["email"]); name = str(resolved.data.get("name") or email)
    _PENDING_EMAIL = {"recipient": email, "body": body, "subject": subject}
    subject_line = f" Subject: {subject!r}." if subject else ""
    return AgentReply(True, f"Ready to send email to {name} <{email}>.{subject_line} Body: {body!r} Type 'confirm' to send or 'cancel'.")

def _confirm_pending() -> AgentReply:
    global _PENDING_EMAIL
    if not _PENDING_EMAIL: return AgentReply(False, "There is nothing waiting for confirmation.")
    pending = _PENDING_EMAIL; _PENDING_EMAIL = None
    result = send_email(recipient=pending["recipient"], body=pending["body"], subject=pending.get("subject") or None)
    return AgentReply(result.ok, result.message)

def _cancel_pending() -> AgentReply:
    global _PENDING_EMAIL
    if not _PENDING_EMAIL: return AgentReply(False, "There is nothing waiting for confirmation.")
    _PENDING_EMAIL = None; return AgentReply(True, "Cancelled.")

def _matching_tab_exists(name: str) -> bool:
    tab = tab_status(name)
    return bool(tab.ok and isinstance(tab.data, list) and len(tab.data) > 0)

def _smart_status(name: str) -> AgentReply:
    if browser_status().ok and _matching_tab_exists(name): return _result(tab_status(name))
    return _result(app_status(name))

def _smart_open(name: str) -> AgentReply:
    if browser_status().ok:
        if _matching_tab_exists(name): return _result(focus_tab(name))
        web = open_site(name)
        if web.ok: return _result(web)
    return _result(launch_app(name))

def _smart_close(name: str) -> AgentReply:
    if browser_status().ok and _matching_tab_exists(name): return _result(close_tab(name))
    return _result(close_app(name))

def _execute_tool(name: str, arguments: dict[str, Any]) -> AgentReply:
    mapping = {
        "smart.status": lambda: _smart_status(str(arguments.get("name") or "")),
        "smart.open": lambda: _smart_open(str(arguments.get("name") or "")),
        "smart.close": lambda: _smart_close(str(arguments.get("name") or "")),
        "browser.status": lambda: _result(browser_status()), "browser.list_tabs": lambda: _result(list_tabs()),
        "browser.tab_status": lambda: _result(tab_status(str(arguments.get("query") or ""))),
        "browser.close_tab": lambda: _result(close_tab(str(arguments.get("query") or ""))),
        "browser.focus_tab": lambda: _result(focus_tab(str(arguments.get("query") or ""))),
        "browser.open_site": lambda: _result(open_site(str(arguments.get("query") or ""))),
        "pc.minecraft_status": lambda: _result(minecraft_status()), "pc.launch_minecraft": lambda: _result(launch_minecraft()),
        "pc.app_status": lambda: _result(app_status(str(arguments.get("name") or ""))),
        "pc.launch_app": lambda: _result(launch_app(str(arguments.get("name") or ""))),
        "pc.close_app": lambda: _result(close_app(str(arguments.get("name") or ""))),
        "pc.list_running_apps": lambda: _result(list_running_apps(int(arguments.get("limit") or 30))),
        "pc.open_url": lambda: _result(open_url(str(arguments.get("url") or ""))),
        "pc.open_path": lambda: _result(open_path(str(arguments.get("path") or ""))),
    }
    if name == "pc.ensure_minecraft_running":
        status = minecraft_status(); return AgentReply(True, "Minecraft is already running.") if "does not appear" not in status.message.lower() else _result(launch_minecraft())
    if name == "google.status":
        r=google_status(); return AgentReply(r.ok,r.message)
    if name == "contacts.resolve":
        r=resolve_contact(str(arguments.get("query") or "")); return AgentReply(r.ok,r.message)
    if name == "gmail.prepare_send": return _prepare_email(arguments)
    if name in mapping: return mapping[name]()
    return AgentReply(False, f"The planner requested an unknown tool: {name}")

def _extract_json(content: str) -> dict[str, Any] | None:
    content=content.strip()
    if not content:return None
    try:
        v=json.loads(content); return v if isinstance(v,dict) else None
    except json.JSONDecodeError: pass
    m=re.search(r"\{.*\}",content,flags=re.DOTALL)
    if not m:return None
    try:
        v=json.loads(m.group(0)); return v if isinstance(v,dict) else None
    except json.JSONDecodeError:return None

def _fast_path(text: str) -> AgentReply | None:
    n=_normalize(text)
    if n in {"confirm","yes send it","send it","yes, send it"}:return _confirm_pending()
    if n in {"cancel","never mind","nevermind","don't send it","do not send it"}:return _cancel_pending()
    if n in {"browser status","opera status","is browser control connected","is browser control connected?"}:return _execute_tool("browser.status",{})
    if n in {"list tabs","show tabs","what tabs are open","what tabs are open?"}:return _execute_tool("browser.list_tabs",{})
    if n in {"google status","gmail status","is gmail connected","is gmail connected?"}:return _execute_tool("google.status",{})
    if n in {"what is running","what's running","list running apps","list running processes"}:return _execute_tool("pc.list_running_apps",{})
    m=re.fullmatch(r"(?:is|check if|check whether) (.+?) (?:running|open)\??",n)
    if m:return _execute_tool("smart.status",{"name":m.group(1)})
    m=re.fullmatch(r"(?:close|quit|stop|kill) (.+?)[?.!]?",n)
    if m:return _execute_tool("smart.close",{"name":m.group(1)})
    m=re.fullmatch(r"(?:open|launch|start|run) (.+?)(?: for me)?[?.!]?",n)
    if m:
        target=m.group(1).strip()
        if target.startswith(("http://","https://","www.")) or ("." in target and " " not in target):return _execute_tool("pc.open_url",{"url":target})
        if re.match(r"^[a-z]:\\",target) or target.startswith(("~",".\\","\\\\")):return _execute_tool("pc.open_path",{"path":target})
        return _execute_tool("smart.open",{"name":target})
    if n in {"minecraft status","check minecraft","make sure minecraft is running","make sure minecraft is open","ensure minecraft is running","ensure minecraft is open"}:
        return _execute_tool("pc.ensure_minecraft_running" if any(x in n for x in ("make sure","ensure")) else "pc.minecraft_status",{})
    return None

def _ollama_plan(text: str) -> tuple[dict[str, Any] | None,str]:
    system='''You are the tool router for Jarvis, a local personal assistant. Thinking is disabled because latency matters. Choose exactly one listed tool. Prefer smart.open/smart.close/smart.status for ordinary names. Tools: smart.status {name}; smart.open {name}; smart.close {name}; browser.status {}; browser.list_tabs {}; browser.tab_status {query}; browser.close_tab {query}; browser.focus_tab {query}; browser.open_site {query}; pc.app_status {name}; pc.launch_app {name}; pc.close_app {name}; pc.list_running_apps {limit}; pc.open_url {url}; pc.open_path {path}; pc.minecraft_status {}; pc.launch_minecraft {}; pc.ensure_minecraft_running {}; google.status {}; contacts.resolve {query}; gmail.prepare_send {recipient,body,subject}. Preserve message constraints exactly. Do not add emojis, facts, greetings, signatures or promises unless requested. gmail.prepare_send only prepares and asks for confirmation. Return one JSON object only with keys tool, arguments, response.'''
    payload={"model":OLLAMA_MODEL,"stream":False,"format":"json","think":False,"keep_alive":OLLAMA_KEEP_ALIVE,"messages":[{"role":"system","content":system},{"role":"user","content":text}],"options":{"temperature":0}}
    try:
        with httpx.Client(timeout=120.0) as c:r=c.post(f"{OLLAMA_URL}/api/chat",json=payload);r.raise_for_status();data=r.json()
        p=_extract_json(str(data.get("message",{}).get("content","")))
        return (p,"") if p is not None else (None,"Ollama responded, but Jarvis could not parse its tool plan.")
    except httpx.ConnectError:return None,f"Cannot connect to Ollama at {OLLAMA_URL}. Is Ollama running?"
    except httpx.TimeoutException:return None,f"Ollama model {OLLAMA_MODEL} timed out while planning."
    except (httpx.HTTPError,TypeError,ValueError) as e:return None,f"Ollama planner error: {e}"

def handle_natural_language(text: str) -> AgentReply:
    n=_normalize(text)
    if not n:return AgentReply(True,"")
    if n in {"quit","exit"}:return AgentReply(True,"__EXIT__")
    if n in {"model","what model are you using","what model are you using?"}:return AgentReply(True,f"Planner model: {OLLAMA_MODEL} via Ollama at {OLLAMA_URL}; thinking off; keep-alive {OLLAMA_KEEP_ALIVE}")
    fast=_fast_path(text)
    if fast is not None:return fast
    plan,error=_ollama_plan(text)
    if plan is None:return AgentReply(False,error)
    tool=plan.get("tool");args=plan.get("arguments") or {}
    if tool:return _execute_tool(str(tool),args if isinstance(args,dict) else {})
    return AgentReply(False,str(plan.get("response") or "I do not have a tool for that yet."))
