from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_EXECUTIVE_CUES = (
    "what should i do",
    "what do i need to do",
    "what am i working on",
    "what are we working on",
    "what are my goals",
    "what are our goals",
    "what am i waiting on",
    "what are we waiting on",
    "what are my priorities",
    "what are our priorities",
    "anything i need to know",
    "anything i should know",
    "before i go in",
    "before the meeting",
    "give me a briefing",
    "my briefing",
    "brief me",
    "my agenda",
    "what's next",
    "what is next",
    "next action",
    "follow up",
    "follow-up",
    "commitments",
    "obligations",
    "deadlines",
)

_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "what", "when", "where", "who", "why", "how",
    "did", "does", "have", "has", "was", "were", "are", "from", "about", "into", "your", "you",
    "my", "our", "jarvis", "please", "tell", "show", "find", "search", "me", "need", "know",
    "before", "after", "anything", "should", "would", "could", "there", "their", "they", "them",
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_.@'-]+", _normalize(value))
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def is_executive_query(query: str) -> bool:
    normalized = _normalize(query)
    return any(cue in normalized for cue in _EXECUTIVE_CUES)


def _due_score(raw: str) -> tuple[float, str]:
    text = str(raw or "").strip()
    if not text:
        return (0.0, "")
    try:
        due = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.astimezone()
        now = datetime.now().astimezone()
        days = (due - now).total_seconds() / 86400.0
        if days < 0:
            return (6.0, "overdue")
        if days <= 2:
            return (5.0, "due within 2 days")
        if days <= 7:
            return (3.0, "due within 7 days")
        if days <= 30:
            return (1.0, "due within 30 days")
    except (TypeError, ValueError, OverflowError):
        pass
    return (0.0, "")


def _expanded_entity_ids(query: str) -> set[str]:
    ids: set[str] = set()
    try:
        from jarvis_mrb.world_linker import related_entities
        from jarvis_mrb.world_model import search as world_search

        seeds = [item for item in world_search(query, limit=8) if item.get("type") == "entity"]
        for seed in seeds[:5]:
            entity_id = str(seed.get("id") or "")
            if not entity_id:
                continue
            ids.add(entity_id)
            for related in related_entities(entity_id, limit=8):
                confidence = float(related.get("confidence") or 0.0)
                if confidence >= 0.72:
                    related_id = str(related.get("entity_id") or "")
                    if related_id:
                        ids.add(related_id)
    except Exception:
        pass
    return ids


def _score_intention(
    item: dict[str, Any],
    *,
    query: str,
    query_tokens: set[str],
    entity_ids: set[str],
    executive: bool,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    title = str(item.get("title") or "")
    next_action = str(item.get("next_action") or "")
    title_tokens = _tokens(title)
    next_tokens = _tokens(next_action)

    title_overlap = len(query_tokens & title_tokens)
    if title_overlap:
        score += 3.0 * title_overlap
        reasons.append("query overlaps goal")
    next_overlap = len(query_tokens & next_tokens)
    if next_overlap:
        score += 2.0 * next_overlap
        reasons.append("query overlaps next action")

    for entity in item.get("entities") or []:
        entity_id = str(entity.get("entity_id") or "")
        name = str(entity.get("name") or "")
        if entity_id and entity_id in entity_ids:
            score += 8.0
            reasons.append(f"connected to {name or entity.get('role') or 'queried entity'}")
        elif len(_tokens(name) & query_tokens) >= 1 and len(_normalize(name)) >= 4:
            score += 4.0
            reasons.append(f"mentions {name}")

    for commitment in item.get("commitments") or []:
        action = str(commitment.get("action") or "")
        owner = str(commitment.get("owner") or "")
        action_overlap = len(query_tokens & _tokens(action))
        if action_overlap:
            score += min(6.0, 2.0 * action_overlap)
            reasons.append("query overlaps linked commitment")
        owner_tokens = _tokens(owner)
        if owner_tokens and query_tokens & owner_tokens:
            score += 6.0
            reasons.append(f"linked commitment owned by {owner}")
        if executive:
            urgency, label = _due_score(str(commitment.get("due_at") or ""))
            if urgency:
                score += urgency
                reasons.append(f"commitment {label}")

    if executive:
        score += 1.0
        urgency, label = _due_score(str(item.get("due_at") or ""))
        if urgency:
            score += urgency
            reasons.append(label)

    # Exact phrase/name matches should dominate loose lexical overlap.
    normalized_query = _normalize(query)
    normalized_title = _normalize(title)
    if normalized_title and len(normalized_title) >= 5 and normalized_title in normalized_query:
        score += 8.0
        reasons.append("explicit goal name")

    # Preserve order while deduplicating human-readable reasons.
    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return (score, deduped)


def relevant_intentions(query: str, limit: int = 4) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 10))
    try:
        from jarvis_mrb.world_executive import active_intentions, refresh_intentions

        refresh_intentions()
        items = active_intentions(limit=30)
    except Exception:
        return []

    if not items:
        return []

    executive = is_executive_query(query)
    query_tokens = _tokens(query)
    entity_ids = _expanded_entity_ids(query)
    ranked: list[tuple[float, dict[str, Any], list[str]]] = []

    for item in items:
        score, reasons = _score_intention(
            item,
            query=query,
            query_tokens=query_tokens,
            entity_ids=entity_ids,
            executive=executive,
        )
        # Non-executive turns require a concrete relation/name/lexical match. General
        # executive questions may rank active goals by urgency even without nouns.
        threshold = 0.5 if executive else 3.0
        if score >= threshold:
            ranked.append((score, item, reasons))

    ranked.sort(
        key=lambda entry: (
            entry[0],
            str(entry[1].get("due_at") or "9999"),
            str(entry[1].get("title") or ""),
        ),
        reverse=True,
    )

    result: list[dict[str, Any]] = []
    for score, item, reasons in ranked[:safe_limit]:
        enriched = dict(item)
        enriched["relevance_score"] = round(score, 2)
        enriched["relevance_reasons"] = reasons[:4]
        result.append(enriched)
    return result


def context_for_query(query: str, limit: int = 4) -> str:
    items = relevant_intentions(query, limit=limit)
    if not items:
        return ""

    lines = ["RELEVANT PERSISTENT INTENTIONS (explicit goals; selected for this query):"]
    for item in items:
        detail = f"- {item.get('title')}"
        if item.get("next_action"):
            detail += f"; next: {item.get('next_action')}"
        if item.get("due_at"):
            detail += f"; due: {item.get('due_at')}"
        projects = [
            str(entity.get("name") or "")
            for entity in item.get("entities") or []
            if str(entity.get("role") or "") == "project" and entity.get("name")
        ]
        if projects:
            detail += "; project: " + ", ".join(projects[:3])
        reasons = item.get("relevance_reasons") or []
        if reasons:
            detail += "; selected because: " + ", ".join(str(reason) for reason in reasons[:3])
        lines.append(detail)
        for commitment in (item.get("commitments") or [])[:3]:
            owner = f"{commitment.get('owner')}: " if commitment.get("owner") else ""
            due = f" (due {commitment.get('due_at')})" if commitment.get("due_at") else ""
            lines.append(f"  linked commitment: {owner}{commitment.get('action')}{due}")
    return "\n".join(lines)[:7000]


def status() -> dict[str, Any]:
    return {
        "strategy": "query-aware executive relevance",
        "unrelated_intentions_injected": False,
        "executive_queries_rank_by_urgency": True,
        "entity_graph_expansion": True,
    }
