from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
SERPER_CONFIG_PATH = APP_DIR / "serper.json"
SERPER_URL = os.environ.get("JARVIS_SERPER_URL", "https://google.serper.dev/search")


@dataclass(frozen=True)
class WebResult:
    ok: bool
    message: str
    data: Any = None


def _api_key() -> str:
    configured = os.environ.get("JARVIS_SERPER_API_KEY", "").strip()
    if configured:
        return configured
    try:
        payload = json.loads(SERPER_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return str(payload.get("api_key") or "").strip()
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def web_status() -> WebResult:
    if _api_key():
        return WebResult(True, "Serper web search is configured.")
    return WebResult(
        False,
        "Serper web search is not configured. Run 'py -3.14 -m jarvis_mrb.serper_setup' on the Jarvis PC.",
    )


def _domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host.removeprefix("www.")


def _clean(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def web_search(query: str, *, num: int = 5) -> WebResult:
    q = " ".join(query.strip().split())
    if not q:
        return WebResult(False, "Web search requires a query.")

    key = _api_key()
    if not key:
        return web_status()

    safe_num = max(1, min(int(num), 10))
    payload = {
        "q": q,
        "num": safe_num,
        "gl": os.environ.get("JARVIS_SERPER_GL", "us"),
        "hl": os.environ.get("JARVIS_SERPER_HL", "en"),
    }
    headers = {
        "X-API-KEY": key,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(12.0, connect=3.0)) as client:
            response = client.post(SERPER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            return WebResult(False, "Serper rejected the configured API key.")
        if exc.response.status_code == 429:
            return WebResult(False, "Serper rate-limited the search request.")
        return WebResult(False, f"Serper search failed with HTTP {exc.response.status_code}.")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return WebResult(False, f"Serper web search is unavailable: {exc}")

    if not isinstance(data, dict):
        return WebResult(False, "Serper returned an invalid search response.")

    pieces: list[str] = []

    answer_box = data.get("answerBox")
    if isinstance(answer_box, dict):
        answer = _clean(answer_box.get("answer") or answer_box.get("snippet"), 520)
        if answer:
            source = _clean(answer_box.get("title"), 100)
            source_domain = _domain(str(answer_box.get("link") or ""))
            attribution = source or source_domain
            pieces.append(answer + (f" Source: {attribution}." if attribution else ""))

    if not pieces:
        graph = data.get("knowledgeGraph")
        if isinstance(graph, dict):
            description = _clean(graph.get("description"), 520)
            if description:
                title = _clean(graph.get("title"), 100)
                source = _clean(graph.get("descriptionSource"), 100)
                attribution = source or title
                pieces.append(description + (f" Source: {attribution}." if attribution else ""))

    organic = data.get("organic")
    normalized: list[dict[str, str]] = []
    if isinstance(organic, list):
        for item in organic[:safe_num]:
            if not isinstance(item, dict):
                continue
            title = _clean(item.get("title"), 140)
            snippet = _clean(item.get("snippet"), 380)
            link = str(item.get("link") or "")
            date = _clean(item.get("date"), 80)
            if not title and not snippet:
                continue
            normalized.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "link": link,
                    "domain": _domain(link),
                    "date": date,
                }
            )

    # If Serper supplied a direct answer, add only a couple corroborating results.
    # Otherwise return the top three results. This is deliberately concise because
    # Jarvis may read the tool result aloud through the glasses.
    result_limit = 2 if pieces else 3
    for item in normalized[:result_limit]:
        label = item["title"] or item["domain"] or "Search result"
        detail = item["snippet"]
        suffix_parts = [value for value in (item["domain"], item["date"]) if value]
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        if detail:
            pieces.append(f"{label}{suffix}: {detail}")
        else:
            pieces.append(f"{label}{suffix}.")

    if not pieces:
        return WebResult(True, f"I found no useful web results for {q!r}.", data)

    message = "Web results: " + " ".join(pieces)
    return WebResult(True, message, {"query": q, "results": normalized, "raw": data})
