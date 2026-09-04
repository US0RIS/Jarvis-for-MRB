from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx


CDP_URL = os.environ.get("JARVIS_BROWSER_CDP_URL", "http://127.0.0.1:9222")


@dataclass(frozen=True)
class BrowserResult:
    ok: bool
    message: str
    data: Any = None


def _cdp_get(path: str) -> httpx.Response:
    with httpx.Client(timeout=2.0) as client:
        return client.get(f"{CDP_URL}{path}")


def _short_title(title: str, url: str = "") -> str:
    value = " ".join(title.split()).strip()
    if not value:
        try:
            value = urlparse(url).hostname or "Untitled tab"
        except ValueError:
            value = "Untitled tab"
    if len(value) > 72:
        value = value[:69].rstrip() + "..."
    return value


def browser_status() -> BrowserResult:
    try:
        response = _cdp_get("/json/version")
        response.raise_for_status()
        data = response.json()
        browser = str(data.get("Browser") or "Chromium browser")
        return BrowserResult(True, f"Browser control is connected to {browser}.", data)
    except (httpx.HTTPError, ValueError):
        return BrowserResult(
            False,
            "Browser tab control is not connected yet. Opera must be started with remote debugging enabled. "
            "Run: py -3.14 -m jarvis_mrb.browser_setup",
        )


def list_tabs() -> BrowserResult:
    try:
        response = _cdp_get("/json")
        response.raise_for_status()
        raw = response.json()
    except (httpx.HTTPError, ValueError):
        return browser_status()

    tabs = [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or ""),
            "type": str(item.get("type") or ""),
        }
        for item in raw
        if str(item.get("type") or "") == "page"
    ]
    if not tabs:
        return BrowserResult(True, "No browser tabs are currently open.", [])

    # URLs stay in structured data for matching and future actions, but are not
    # dumped into the user-facing response. Reading tracking URLs aloud is both
    # useless and painfully verbose through the glasses.
    titles: list[str] = []
    seen: set[str] = set()
    for tab in tabs:
        title = _short_title(tab["title"], tab["url"])
        key = title.casefold()
        if key not in seen:
            seen.add(key)
            titles.append(title)

    shown = titles[:8]
    preview = "; ".join(shown)
    remaining = len(titles) - len(shown)
    suffix = f"; and {remaining} more" if remaining > 0 else ""
    return BrowserResult(True, f"You have {len(tabs)} open tabs: {preview}{suffix}.", tabs)


def _find_tabs(query: str) -> list[dict[str, str]]:
    result = list_tabs()
    if not result.ok or not isinstance(result.data, list):
        return []
    needle = query.strip().lower()
    if not needle:
        return []
    aliases = {
        "spotify": ("spotify", "open.spotify.com"),
        "youtube": ("youtube", "youtube.com"),
        "gmail": ("gmail", "mail.google.com"),
        "chatgpt": ("chatgpt", "chatgpt.com"),
    }
    terms = aliases.get(needle, (needle,))
    matches: list[dict[str, str]] = []
    for tab in result.data:
        haystack = f"{tab.get('title', '')} {tab.get('url', '')}".lower()
        if any(term in haystack for term in terms):
            matches.append(tab)
    return matches


def tab_status(query: str) -> BrowserResult:
    status = browser_status()
    if not status.ok:
        return status
    matches = _find_tabs(query)
    if not matches:
        return BrowserResult(True, f"No open browser tab matches {query}.")
    first = matches[0]
    return BrowserResult(True, f"{query} is open in the tab {_short_title(first['title'], first['url'])}.", matches)


def close_tab(query: str) -> BrowserResult:
    status = browser_status()
    if not status.ok:
        return status
    matches = _find_tabs(query)
    if not matches:
        return BrowserResult(False, f"No open browser tab matches {query}.")

    closed = 0
    errors = 0
    for tab in matches:
        tab_id = tab.get("id") or ""
        try:
            response = _cdp_get(f"/json/close/{quote(tab_id, safe='')}")
            if response.status_code < 400:
                closed += 1
            else:
                errors += 1
        except httpx.HTTPError:
            errors += 1

    if closed and not errors:
        return BrowserResult(True, f"Closed {closed} browser tab(s) matching {query}.")
    if closed:
        return BrowserResult(False, f"Closed {closed} matching browser tab(s), but {errors} could not be closed.")
    return BrowserResult(False, f"Jarvis found a tab matching {query}, but the browser would not close it.")


def focus_tab(query: str) -> BrowserResult:
    status = browser_status()
    if not status.ok:
        return status
    matches = _find_tabs(query)
    if not matches:
        return BrowserResult(False, f"No open browser tab matches {query}.")
    tab = matches[0]
    tab_id = tab.get("id") or ""
    try:
        response = _cdp_get(f"/json/activate/{quote(tab_id, safe='')}")
        response.raise_for_status()
        return BrowserResult(True, f"Focused {_short_title(tab['title'], tab['url'])}.")
    except httpx.HTTPError:
        return BrowserResult(False, f"Jarvis found {query}, but the browser would not focus that tab.")


def open_site(query: str) -> BrowserResult:
    matches = _find_tabs(query)
    if matches:
        return focus_tab(query)

    aliases = {
        "spotify": "https://open.spotify.com/",
        "youtube": "https://www.youtube.com/",
        "gmail": "https://mail.google.com/",
        "chatgpt": "https://chatgpt.com/",
    }
    key = query.strip().lower()
    url = aliases.get(key)
    if not url:
        if key.startswith(("http://", "https://")):
            url = query.strip()
        elif "." in query and " " not in query:
            url = "https://" + query.strip()
        else:
            return BrowserResult(False, f"Jarvis does not know which website to open for {query}.")

    if sys.platform == "win32":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            friendly = query.strip() if key in aliases else (urlparse(url).hostname or "the requested site")
            return BrowserResult(True, f"Opened {friendly} in the browser.")
        except OSError as exc:
            return BrowserResult(False, f"Could not open the requested site: {exc}")
    return BrowserResult(False, "Opening a new browser tab is currently implemented for Windows only.")


def _opera_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = [Path(os.environ.get("PROGRAMFILES", "")), Path(os.environ.get("PROGRAMFILES(X86)", ""))]
    candidates = [
        local / "Programs" / "Opera" / "opera.exe",
        local / "Programs" / "Opera GX" / "opera.exe",
    ]
    for base in program_files:
        candidates.extend([base / "Opera" / "opera.exe", base / "Opera GX" / "opera.exe"])
    return [path for path in candidates if str(path) and path.exists()]


def launch_opera_debug() -> BrowserResult:
    status = browser_status()
    if status.ok:
        return status
    candidates = _opera_candidates()
    if not candidates:
        return BrowserResult(False, "Jarvis could not locate Opera. Set JARVIS_OPERA_PATH to opera.exe if needed.")
    opera = Path(os.environ.get("JARVIS_OPERA_PATH", str(candidates[0])))
    try:
        subprocess.Popen([str(opera), "--remote-debugging-port=9222"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return BrowserResult(False, f"Could not start Opera with browser control enabled: {exc}")
    return BrowserResult(
        True,
        "Started Opera with browser control enabled. If Opera was already running, fully exit it and run this setup command again.",
    )
