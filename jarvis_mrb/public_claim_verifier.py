"""Conservative primary-source verification for public announcement claims.

Search-engine snippets are leads, not authoritative evidence. This module
fetches a small bounded selection of *first-party* HTTPS pages and reports
what those pages support. It never infers that no post exists from missing
search results and cannot authenticate an image without its source post.
"""
from __future__ import annotations

from dataclasses import dataclass
import html
import re
from urllib.parse import urlsplit
from typing import Any

import httpx

_OFFICIAL: dict[str,tuple[str,...]] = {
    "google":("blog.google","deepmind.google","ai.google.dev","developers.googleblog.com"),
    "gemma":("blog.google","deepmind.google","ai.google.dev","developers.googleblog.com"),
    "gemini":("blog.google","deepmind.google","ai.google.dev","developers.googleblog.com"),
    "apple":("apple.com","www.apple.com","developer.apple.com"),
    "openai":("openai.com","www.openai.com"),
    "gpt":("openai.com","www.openai.com"),
    "anthropic":("anthropic.com","www.anthropic.com"),
    "claude":("anthropic.com","www.anthropic.com"),
    "microsoft":("microsoft.com","www.microsoft.com","blogs.microsoft.com"),
    "nvidia":("nvidia.com","www.nvidia.com","blogs.nvidia.com"),
    "meta":("about.fb.com","ai.meta.com"),
}
_PRODUCTS=re.compile(
    r"\b(?:gemini|gemma|gpt|claude|qwen)\s*[- ]?\d+(?:\.\d+)?(?:\s+[a-zA-Z][a-zA-Z0-9-]{1,25})?",
    re.I,
)
_TAGS=re.compile(r"<[^>]*>",re.S)
_SKIP=re.compile(r"<(?:script|style|nav|footer|svg)\b[^>]*>.*?</(?:script|style|nav|footer|svg)>",re.I|re.S)


def _domains(query: str) -> tuple[str,...]:
    words=re.findall(r"\b[a-z]+\b",query.lower())
    for word in words:
        if word in _OFFICIAL:
            return _OFFICIAL[word]
    return ()


def _target_phrase(query: str) -> str:
    found=_PRODUCTS.search(query)
    return " ".join(found.group().split()).lower() if found else ""


def _safe_source(url: str, allowed: tuple[str,...]) -> bool:
    try:
        parts=urlsplit(url)
        return bool(
            parts.scheme=="https"
            and parts.hostname in allowed
            and not parts.username and not parts.password
            and parts.port in {None,443}
            and not parts.fragment
        )
    except ValueError:
        return False


def _page_text(content: bytes) -> str:
    raw=content[:240_000].decode("utf-8",errors="replace")
    raw=_SKIP.sub(" ",raw)
    return " ".join(html.unescape(_TAGS.sub(" ",raw)).split())[:80_000]


def inspect_source(
    url: str, *, allowed: tuple[str,...],
    fetch: Any=None,
) -> dict[str,Any] | None:
    if not _safe_source(url,allowed):
        return None
    fetch=fetch or httpx.get
    try:
        response=fetch(
            url, timeout=httpx.Timeout(7.0,connect=2.0),
            follow_redirects=False,
            headers={"Accept":"text/html"},
        )
        if response.status_code!=200:
            return None
        media_type=str(response.headers.get("content-type") or "").lower()
        if "text/html" not in media_type:
            return None
        if len(response.content)>1_500_000:
            return None
        body=_page_text(response.content)
        if not body:
            return None
        return {"url":url,"text":body,"host":urlsplit(url).hostname}
    except (httpx.HTTPError,ValueError):
        return None


def verify_public_claim(query: str, *, search: Any=None, fetch: Any=None,
                        num: int=8) -> dict[str,Any]:
    """Return evidence and a carefully qualified answer, never a negative proof."""
    from jarvis_mrb.tools.web import web_search
    query=" ".join(str(query or "").split())[:400]
    allowed=_domains(query)
    if not allowed:
        return {"ok":False,"status":"unsupported_official_domain",
                "message":"I cannot identify an official source to verify this public claim. A screenshot alone is not proof either way.","sources":[]}
    result=(search or web_search)(query,num=max(1,min(num,10)),refine=False)
    if not result.ok:
        return {"ok":False,"status":"search_unavailable",
                "message":"I cannot verify this current claim because live search is unavailable. That is not evidence it is false.","sources":[]}
    payload=result.data if isinstance(result.data,dict) else {}
    candidates=payload.get("evidence") if isinstance(payload.get("evidence"),list) else []
    phrase=_target_phrase(query)
    seen=set()
    sources=[]
    for item in candidates:
        if len(sources)>=3: break
        if not isinstance(item,dict):
            continue
        url=str(item.get("link") or "")
        if url in seen or not _safe_source(url,allowed):
            continue
        seen.add(url)
        page=inspect_source(url,allowed=allowed,fetch=fetch)
        if not page: continue
        if phrase and phrase not in page["text"].lower():
            continue
        sources.append({
            "url":url,"host":page["host"],
            "phrase_confirmed":bool(phrase),
            "source_type":"first_party_page_fetched",
        })
    if not sources:
        return {
            "ok":True,"status":"unverified",
            "message":"I could not verify this from a fetched official page. That does not establish the announcement or screenshot is fake. I need the original official post or another independently confirmed primary source.",
            "sources":[],
        }
    links="; ".join(item["url"] for item in sources)
    return {
        "ok":True,"status":"primary_source_mentions_subject",
        "message":(
            f"I fetched {len(sources)} official source page(s) that mention the subject: {links}. "
            "This establishes only what those accessible pages say; it does not authenticate "
            "a particular screenshot, social-media post, date, or wording. Check the original post "
            "before claiming that it was or was not published."
        ),
        "sources":sources,
    }
