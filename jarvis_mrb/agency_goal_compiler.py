from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Callable

import httpx

from jarvis_mrb.planner_model import QUALITY_MODEL
import jarvis_mrb.world_model as world_model


DEFAULT_OBSERVATION_SOURCE_KINDS = [
    "jarvis_verifier",
    "calendar_enriched",
    "gmail_attachment",
    "rayban_camera",
    "meeting_notes",
    "expense_tracker",
    "iphone_inventory",
    "iphone_waiting",
    "iphone_reminders",
    "iphone_encounter",
]

_ACHIEVED_TERMS = {
    "signed", "executed", "approved", "accepted", "submitted", "sent",
    "booked", "reserved", "purchased", "delivered", "received", "completed",
    "finished", "resolved", "closed", "paid", "confirmed", "filed",
    "launched", "deployed",
}

_COMPLETION_WORDS = {
    "sign": "signed",
    "signed": "signed",
    "execute": "executed",
    "executed": "executed",
    "approve": "approved",
    "approved": "approved",
    "accept": "accepted",
    "accepted": "accepted",
    "submit": "submitted",
    "submitted": "submitted",
    "send": "sent",
    "sent": "sent",
    "book": "booked",
    "booked": "booked",
    "reserve": "reserved",
    "reserved": "reserved",
    "purchase": "purchased",
    "purchased": "purchased",
    "buy": "purchased",
    "deliver": "delivered",
    "delivered": "delivered",
    "receive": "received",
    "received": "received",
    "complete": "completed",
    "completed": "completed",
    "finish": "finished",
    "finished": "finished",
    "resolve": "resolved",
    "resolved": "resolved",
    "close": "closed",
    "closed": "closed",
    "pay": "paid",
    "paid": "paid",
    "confirm": "confirmed",
    "confirmed": "confirmed",
    "file": "filed",
    "filed": "filed",
    "launch": "launched",
    "launched": "launched",
    "deploy": "deployed",
    "deployed": "deployed",
}


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(raw[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def _max_event_id() -> int:
    conn = sqlite3.connect(world_model.DB_PATH, timeout=10.0)
    try:
        row = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _intention_context(intention_id: str) -> dict[str, Any]:
    from jarvis_mrb.world_executive import active_intentions

    for item in active_intentions(limit=30):
        if str(item.get("id") or "") == str(intention_id):
            return item
    return {}


def _model_compile(prompt: str) -> dict[str, Any]:
    from jarvis_mrb.agent import OLLAMA_URL

    system = """Compile an explicit personal goal into a conservative OBSERVABLE success contract.
Return JSON only:
{
  "confidence": 0.0,
  "criteria": [
    {
      "kind":"event_match",
      "terms_all":["specific subject","completion-state word"],
      "terms_none":["negated/unfinished phrase"],
      "event_types":[],
      "source_kinds":[]
    }
    OR
    {
      "kind":"commitment_status",
      "commitment_id":"an EXACT supplied commitment id",
      "status":"resolved"
    }
  ],
  "explanation":"short explanation of what future observation proves success"
}

Rules:
- This contract determines when an autonomous agent STOPS. False positives are worse than delayed completion.
- Criteria are ANDed. Include only conditions that are genuinely necessary to establish success.
- event_match must describe evidence of an ACHIEVED state, never merely an intention, plan, reminder, request, deadline, or discussion.
- event_match terms_all must contain a specific subject anchor and an achieved-state term such as signed, booked, delivered, received, approved, paid, filed, deployed, completed, or confirmed.
- Put common negations / incomplete formulations in terms_none, for example "not signed", "unsigned", "needs signature", "pending".
- Leave event_types/source_kinds empty unless the supplied context justifies narrowing them.
- commitment_status may use ONLY an exact commitment id supplied in context.
- Do not invent entity IDs, commitment IDs, tools, sources, or facts.
- If the goal cannot be converted into reliable observable evidence from this context, return confidence below 0.70 and criteria=[].
"""
    payload = {
        "model": QUALITY_MODEL,
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": "0",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt[:12000]},
        ],
        "options": {"temperature": 0},
    }
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=2.0)) as client:
        response = client.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    parsed = _extract_json(str((data.get("message") or {}).get("content") or ""))
    if not parsed:
        raise ValueError("Goal-contract model returned invalid JSON.")
    return parsed


def _completion_term(title: str) -> str:
    """Fallback only when the goal itself names an achieved state.

    The model compiler may infer a defensible future observation contract for an
    imperative such as "book dinner". The deterministic fallback may not silently
    invent what evidence "booked" would look like.
    """
    words = re.findall(r"[a-zA-Z]+", str(title or "").lower())
    for word in words:
        if word in _ACHIEVED_TERMS:
            return word
    return ""


def _fallback_anchor(title: str, intention: dict[str, Any]) -> str:
    entity_names = [
        " ".join(str(item.get("name") or "").split())
        for item in (intention.get("entities") or [])
        if str(item.get("role") or "") == "project" and str(item.get("name") or "").strip()
    ]
    if entity_names:
        return entity_names[0]

    candidates = re.findall(
        r"(?:[A-Z][A-Za-z0-9'_-]+(?:\s+[A-Z][A-Za-z0-9'_-]+)*)",
        str(title or ""),
    )
    leading = {"get", "have", "make", "ensure", "finish", "complete", "confirm", "send", "book", "buy"}
    for candidate in candidates:
        words = candidate.strip().split()
        while len(words) > 1 and words[0].lower() in leading:
            words.pop(0)
        cleaned = " ".join(words).strip()
        if len(cleaned) >= 4:
            return cleaned
    return ""


def _fallback_contract(title: str, intention: dict[str, Any]) -> dict[str, Any] | None:
    completion = _completion_term(title)
    if not completion:
        return None
    anchor = _fallback_anchor(title, intention)
    if not anchor:
        return None

    negations = [
        f"not {completion}",
        "pending",
        "not complete",
        "not completed",
    ]
    if completion == "signed":
        negations.extend(["unsigned", "needs signature", "to be signed"])
    if completion == "booked":
        negations.extend(["not booked", "needs booking", "to book"])

    return {
        "confidence": 0.76,
        "criteria": [
            {
                "kind": "event_match",
                "terms_all": [anchor, completion],
                "terms_none": list(dict.fromkeys(negations)),
                "event_types": [],
                "source_kinds": [],
            }
        ],
        "explanation": f"Fallback contract requires a future event explicitly showing {anchor} is {completion}.",
        "compiler": "deterministic_fallback",
    }


def _validate_compiled(
    desired_state_id: str,
    raw: dict[str, Any],
    intention: dict[str, Any],
) -> tuple[list[dict[str, Any]], float, str]:
    try:
        confidence = max(0.0, min(float(raw.get("confidence") or 0.0), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    criteria = raw.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("No observable success criteria were produced.")
    if confidence < 0.70:
        raise ValueError(f"Observable success contract confidence is too low ({confidence:.2f}).")

    allowed_commitments = {
        str(item.get("id") or "")
        for item in (intention.get("commitments") or [])
        if str(item.get("id") or "")
    }
    min_event_id = _max_event_id()
    clean: list[dict[str, Any]] = []
    for criterion in criteria[:8]:
        if not isinstance(criterion, dict):
            raise ValueError("Compiled criterion is not an object.")
        kind = str(criterion.get("kind") or "")
        if kind == "commitment_status":
            commitment_id = str(criterion.get("commitment_id") or "")
            if commitment_id not in allowed_commitments:
                raise ValueError(f"Compiler referenced unknown commitment {commitment_id!r}.")
            clean.append(
                {
                    "kind": "commitment_status",
                    "commitment_id": commitment_id,
                    "status": "resolved",
                }
            )
            continue
        if kind != "event_match":
            raise ValueError(f"Compiler requested unsupported success criterion {kind!r}.")

        terms_all = [" ".join(str(item).split()) for item in (criterion.get("terms_all") or []) if str(item).strip()]
        terms_none = [" ".join(str(item).split()) for item in (criterion.get("terms_none") or []) if str(item).strip()]
        if len(terms_all) < 2:
            raise ValueError("event_match requires at least a subject anchor and completion term.")
        observed_completion = any(
            completion in " ".join(terms_all).lower()
            for completion in set(_COMPLETION_WORDS.values())
        )
        if not observed_completion:
            raise ValueError("event_match lacks an achieved-state completion term.")
        if not any(len(term) >= 4 and term.lower() not in set(_COMPLETION_WORDS.values()) for term in terms_all):
            raise ValueError("event_match lacks a specific subject anchor.")

        requested_sources = [
            str(item).strip()
            for item in (criterion.get("source_kinds") or [])[:12]
            if str(item).strip()
        ]
        disallowed_sources = [
            source for source in requested_sources
            if source not in DEFAULT_OBSERVATION_SOURCE_KINDS
        ]
        if disallowed_sources:
            raise ValueError(
                "event_match requested non-observation source kinds: "
                + ", ".join(disallowed_sources)
            )

        clean.append(
            {
                "kind": "event_match",
                "terms_all": terms_all[:8],
                "terms_none": terms_none[:12],
                "event_types": [str(item) for item in (criterion.get("event_types") or [])[:12] if str(item).strip()],
                "source_kinds": requested_sources or list(DEFAULT_OBSERVATION_SOURCE_KINDS),
                "min_event_id": min_event_id,
            }
        )

    explanation = " ".join(str(raw.get("explanation") or "").split())[:3000]
    return clean, confidence, explanation


def compile_observable_contract(
    desired_state_id: str,
    *,
    compiler: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from jarvis_mrb.desired_state import (
        get_desired_state,
        replace_criteria,
        set_state,
        update_authority,
    )

    state = get_desired_state(str(desired_state_id))
    if state is None:
        raise ValueError(f"Unknown desired state {desired_state_id!r}.")
    intention_id = str(state.get("intention_id") or "")
    intention = _intention_context(intention_id) if intention_id else {}
    prompt = (
        f"Goal: {state.get('title')}\n"
        f"Intention: {json.dumps(intention, ensure_ascii=False, sort_keys=True)}\n"
        "Compile only the minimum future observable evidence that proves this goal has actually been achieved."
    )

    raw: dict[str, Any] | None = None
    model_error = ""
    if compiler is not None:
        raw = compiler(prompt)
    else:
        try:
            raw = _model_compile(prompt)
        except Exception as exc:
            model_error = str(exc)
            raw = _fallback_contract(str(state.get("title") or ""), intention)

    if not raw:
        reason = "Jarvis could not derive an observable success contract for this goal."
        if model_error:
            reason += f" Model compiler failed: {model_error[:500]}"
        set_state(str(desired_state_id), "blocked", reason=reason)
        update_authority(
            str(desired_state_id),
            {
                "agency_enabled": False,
                "contract_compiled": False,
                "contract_error": reason,
            },
        )
        raise ValueError(reason)

    try:
        criteria, confidence, explanation = _validate_compiled(
            str(desired_state_id),
            raw,
            intention,
        )
    except ValueError as exc:
        reason = f"Observable success contract rejected: {exc}"
        set_state(str(desired_state_id), "blocked", reason=reason)
        update_authority(
            str(desired_state_id),
            {
                "agency_enabled": False,
                "contract_compiled": False,
                "contract_error": reason,
            },
        )
        raise

    updated = replace_criteria(str(desired_state_id), criteria)
    updated = update_authority(
        str(desired_state_id),
        {
            "contract_compiled": True,
            "contract_confidence": confidence,
            "contract_explanation": explanation,
            "contract_compiled_at_event_id": _max_event_id(),
        },
    )
    return updated


def is_circular_legacy_contract(state: dict[str, Any]) -> bool:
    authority = dict(state.get("authority") or {})
    if str(authority.get("origin") or "") != "legacy_goal":
        return False
    criteria = list(state.get("criteria") or [])
    if len(criteria) != 1 or not isinstance(criteria[0], dict):
        return False
    criterion = criteria[0]
    return (
        str(criterion.get("kind") or "") == "belief_in"
        and str(criterion.get("predicate") or "") == "status"
        and {"completed", "done", "resolved"} <= set(str(item) for item in (criterion.get("values") or []))
    )


def ensure_observable_contract(
    desired_state_id: str,
    *,
    compiler: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from jarvis_mrb.desired_state import get_desired_state

    state = get_desired_state(str(desired_state_id))
    if state is None:
        raise ValueError(f"Unknown desired state {desired_state_id!r}.")
    authority = dict(state.get("authority") or {})
    if bool(authority.get("contract_compiled")):
        return state
    if not is_circular_legacy_contract(state):
        return state
    return compile_observable_contract(str(desired_state_id), compiler=compiler)
