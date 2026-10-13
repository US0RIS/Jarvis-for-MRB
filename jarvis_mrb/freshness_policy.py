"""Deterministic minimum freshness gate for mutable PUBLIC claims.

This does not certify that search results are true. It prevents a subset of
current-world questions and direct challenges to earlier public-post denials
from being resolved solely from a language model's training priors.

Keep this deliberately high-precision: private files, personal mail, local
device actions, mathematical questions, and historical explanations do not
belong in a public web-search request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence, Any


@dataclass(frozen=True)
class FreshnessDecision:
    kind: str  # "search" or "clarify"
    query: str = ""
    message: str = ""


_PRIVATE = re.compile(
    r"\b(?:my|our)\s+(?:(?:private|confidential|personal|work)\s+)?(?:email|inbox|calendar|notes|documents?|drafts?|"
    r"files?|conversation|messages?|account|appointments?|meetings?|"
    r"history|data|photos?|screenshots?)\b"
    r"|\b(?:attached|uploaded|private|local)\s+(?:file|document|records?)\b",
    re.I,
)
_PUBLIC = re.compile(
    r"\b(?:google|apple|microsoft|openai|anthropic|meta|nvidia|"
    r"gemma|gemini|gpt|claude|qwen|iphone|ios|airpods|"
    r"government|official|company|developer|product|software|"
    r"release|launch|announcement|announced|posted|public|"
    r"election|stock|price|availability|concert|flight|weather|"
    r"outage|sports|result|score|inventory|reservation|policy)\b",
    re.I,
)
_FRESH = re.compile(
    r"\b(?:today|tonight|yesterday|this (?:week|month|year)|"
    r"latest|recent|recently|just|newly|currently|right now|"
    r"still|breaking|as of|now available|now released)\b",
    re.I,
)
_EVENT = re.compile(
    r"\b(?:post(?:ed|ing)?|tweet(?:ed)?|announc(?:e|ed|ement)|"
    r"releas(?:e|ed)|launch(?:ed)?|availab(?:le|ility)|"
    r"discontinu(?:e|ed)|update(?:d)?|version|"
    r"price|cost|stock|sold out|scheduled|confirmed|cancelled|"
    r"elected|appointed|passed|signed|reported|is (?:it|this) fake)\b",
    re.I,
)
_DIRECT_EVENT = re.compile(
    r"\b(?:did|has|have|was|were|is|will|when|who)\b.{0,110}"
    r"\b(?:post(?:ed)?|announc(?:e|ed)|releas(?:e|ed)|"
    r"launch(?:ed)?|discontinu(?:ed|e)|available|cancelled|"
    r"released|in stock)\b",
    re.I,
)
_DISPUTED_POST = re.compile(
    r"\b(?:how do you know|what makes you (?:think|say)|prove|"
    r"are you sure|did you check)\b.{0,120}"
    r"\b(?:didn['’]t|did not|never|wasn['’]t|not)\b.{0,80}"
    r"\b(?:post|announce|release|publish|launch)\b",
    re.I,
)
_SAFE_PUBLIC_ENTITIES = re.compile(
    r"\b(?:google|apple|microsoft|openai|anthropic|meta|nvidia|"
    r"gemini(?:\s+\d+(?:\s+[a-zA-Z]{2,18})?)?|"
    r"gemma(?:\s+\d+)?|gpt(?:[-\s]+\d+(?:\.\d+)?)?|"
    r"claude|qwen(?:\s*\d+)?)\b",
    re.I,
)


def _normalize(raw: str) -> str:
    return " ".join(raw.strip().split())[:3000]


def _last_public_user_claim(history: Sequence[Any] | None) -> str:
    if not history:
        return ""
    for item in reversed(history[-8:]):
        role = item.get("role") if isinstance(item, dict) else getattr(item, "role", "")
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", "")
        if role != "user" or not isinstance(content, str):
            continue
        candidate = _normalize(content)
        if 5 <= len(candidate) <= 250 and not _PRIVATE.search(candidate):
            # Send only allowlisted public product/company identifiers. Never
            # send an arbitrary sentence from conversation history to Serper.
            entities = list(dict.fromkeys(
                match.group(0) for match in _SAFE_PUBLIC_ENTITIES.finditer(candidate)
            ))
            if entities:
                return " ".join(entities[:4]) + " official announcement post"
    return ""


def freshness_decision(
    question: str,
    history: Sequence[Any] | None = None,
) -> FreshnessDecision | None:
    """Return a deterministic web/clarification decision, or let normal routing act.

    Never treat a user's screenshot or model memory as verification. If a post
    challenge lacks an identifiable public referent, ask instead of searching
    meaningless pronouns or leaking a private conversation to the web.
    """
    if not isinstance(question, str):
        return None
    text = _normalize(question)
    if len(text) < 4 or _PRIVATE.search(text):
        return None

    if _DISPUTED_POST.search(text):
        earlier = _last_public_user_claim(history)
        if earlier:
            return FreshnessDecision("search", query=f"{earlier} {text}"[:400])
        return FreshnessDecision(
            "clarify",
            message=(
                "I cannot establish that they didn't post it from model memory. "
                "Which official account or announcement should I verify?"
            ),
        )

    public = bool(_PUBLIC.search(text))
    has_fresh_context = bool(_FRESH.search(text))
    has_event = bool(_EVENT.search(text))
    direct_event = bool(_DIRECT_EVENT.search(text))

    if (public and has_event and (has_fresh_context or direct_event)) or (
        public and has_fresh_context and re.search(r"\b(?:what|who|when|is|has|did|any)\b", text, re.I)
    ):
        return FreshnessDecision("search", query=text)
    return None
