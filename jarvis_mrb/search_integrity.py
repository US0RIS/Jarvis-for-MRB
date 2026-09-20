from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx

from jarvis_mrb.planner_model import FAST_MODEL

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
AUDIT_DB = APP_DIR / "search_integrity.sqlite3"
RECEIPT_DIR = APP_DIR / "research_receipts"
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
KEEP_ALIVE = os.environ.get("JARVIS_OLLAMA_KEEP_ALIVE", "30m")

REQUIRED_FAMILIES = (
    "precision",
    "breadth",
    "constraints",
    "authoritative",
    "independent",
    "disconfirming",
    "long_tail",
    "adversarial",
)


@dataclass(frozen=True)
class QuerySpec:
    family: str
    query: str
    rationale: str = ""


@dataclass(frozen=True)
class ResearchResult:
    ok: bool
    message: str
    receipt_id: str
    data: dict[str, Any]


SearchFn = Callable[..., Any]


def requires_audited_research(raw: str) -> bool:
    """Return True when a one-shot search would create material selection risk."""
    n = " " + re.sub(r"\s+", " ", raw.strip().lower()) + " "
    cues = (
        " best ", " best option ", " best choice ", " recommend ", " recommendation ",
        " recommendations ", " compare ", " comparison ", " alternatives ", " options ",
        " shortlist ", " exhaustive ", " comprehensively ", " rigorous ", " rigorously ",
        " thoroughly ", " all available ", " every option ", " don't miss ", " do not miss ",
        " closest match ", " top choice ", " top pick ", " rank them ", " rank the ",
    )
    return any(cue in n for cue in cues)


def audited_research(
    question: str,
    *,
    search_fn: SearchFn | None = None,
    query_specs: list[QuerySpec] | None = None,
    num_per_query: int = 10,
    synthesize: bool = True,
) -> ResearchResult:
    """Run an inspectable multi-family web search and emit a Research Receipt.

    This does not claim open-web completeness. It records the search process, measures
    saturation/overlap, and constrains recommendation language to the measured coverage.
    Tests can inject a deterministic search_fn/query_specs and disable synthesis.
    """
    original = " ".join(question.strip().split())
    if not original:
        return ResearchResult(False, "Research requires a question.", "", {})

    run_id = "R-" + uuid.uuid4().hex[:12].upper()
    created = _now()
    _ensure_store()
    _start_run(run_id, original, created)
    _append_event(run_id, "run_started", {"question": original})

    specs = query_specs or _plan_queries(original)
    specs = _normalize_plan(original, specs)
    _append_event(run_id, "plan", {"families": [s.family for s in specs], "queries": [s.query for s in specs]})

    if search_fn is None:
        from jarvis_mrb.tools.web import web_search
        search_fn = web_search

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    query_stats: list[dict[str, Any]] = []
    failures: list[str] = []
    evidence_index = 0

    for spec in specs:
        started = _now()
        _append_event(run_id, "query_started", {"family": spec.family, "query": spec.query, "rationale": spec.rationale})
        try:
            result = search_fn(spec.query, num=max(1, min(int(num_per_query), 10)), refine=False)
        except Exception as exc:  # provider isolation: one failed family must not erase the audit
            failures.append(f"{spec.family}: {exc}")
            query_stats.append({
                "family": spec.family,
                "query": spec.query,
                "ok": False,
                "results": 0,
                "new_results": 0,
                "started_at": started,
                "error": str(exc),
            })
            _append_event(run_id, "query_failed", {"family": spec.family, "query": spec.query, "error": str(exc)})
            continue

        ok = bool(getattr(result, "ok", False))
        data = getattr(result, "data", None)
        rows = data.get("evidence") if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = []

        new_count = 0
        family_total = 0
        for rank, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            normalized = _normalize_evidence(row)
            if not normalized.get("title") and not normalized.get("text"):
                continue
            family_total += 1
            fingerprint = _evidence_fingerprint(normalized)
            is_new = fingerprint not in seen
            if is_new:
                seen.add(fingerprint)
                new_count += 1
            evidence_index += 1
            item = {
                "id": f"E{evidence_index}",
                "family": spec.family,
                "query": spec.query,
                "rank": rank,
                "new": is_new,
                "fingerprint": fingerprint,
                **normalized,
            }
            evidence.append(item)
            _append_event(run_id, "result_observed", {
                "evidence_id": item["id"],
                "family": spec.family,
                "rank": rank,
                "domain": item.get("domain", ""),
                "link": item.get("link", ""),
                "fingerprint": fingerprint,
                "new": is_new,
            })

        if not ok:
            failures.append(f"{spec.family}: {getattr(result, 'message', 'search failed')}")

        stat = {
            "family": spec.family,
            "query": spec.query,
            "ok": ok,
            "results": family_total,
            "new_results": new_count,
            "started_at": started,
        }
        query_stats.append(stat)
        _append_event(run_id, "query_completed", stat)

    candidates = _extract_candidates(original, evidence)
    metrics = _coverage_metrics(specs, query_stats, evidence, candidates, failures)
    stop_reason = _stop_reason(metrics, failures)
    _append_event(run_id, "coverage_assessed", {"metrics": metrics, "stop_reason": stop_reason})

    if synthesize:
        answer = _synthesize(original, evidence, candidates, metrics, run_id)
    else:
        answer = "Audited search completed."

    if not answer:
        answer = _fallback_answer(metrics, run_id)

    certificate = _certificate_summary(run_id, metrics, query_stats, candidates, stop_reason)
    message = f"{answer}\n\n{certificate}".strip()

    receipt = {
        "schema_version": 1,
        "receipt_id": run_id,
        "question": original,
        "created_at": created,
        "completed_at": _now(),
        "status": "completed" if evidence else "incomplete",
        "search_plan": [s.__dict__ for s in specs],
        "queries": query_stats,
        "evidence": evidence,
        "candidates": candidates,
        "coverage": metrics,
        "stop_reason": stop_reason,
        "failures": failures,
        "open_web_completeness_claim": False,
        "answer": answer,
    }
    final_hash = _append_event(run_id, "run_completed", {
        "coverage_grade": metrics["grade"],
        "unique_results": metrics["unique_results"],
        "unique_domains": metrics["unique_domains"],
        "stop_reason": stop_reason,
    })
    receipt["ledger_final_hash"] = final_hash
    _finish_run(run_id, receipt, final_hash)
    _write_receipt(receipt)

    return ResearchResult(bool(evidence), message, run_id, receipt)


def research_receipt(receipt_id: str = "latest", *, detail: str = "summary") -> str:
    receipt = load_receipt(receipt_id)
    if not receipt:
        return "No Research Receipt was found."
    if detail.lower() in {"full", "json", "complete"}:
        return json.dumps(receipt, ensure_ascii=False, indent=2)
    metrics = receipt.get("coverage") or {}
    queries = receipt.get("queries") or []
    candidates = receipt.get("candidates") or []
    lines = [
        f"Research Receipt {receipt.get('receipt_id')}",
        f"Question: {receipt.get('question', '')}",
        f"Coverage: {metrics.get('grade', 'C')} ({metrics.get('coverage_label', 'incomplete')})",
        f"Queries: {metrics.get('queries_executed', 0)}/{metrics.get('queries_planned', 0)} families; unique results: {metrics.get('unique_results', 0)}; domains: {metrics.get('unique_domains', 0)}.",
    ]
    if candidates:
        lines.append("Candidates discovered: " + ", ".join(str(item.get("name") or "") for item in candidates[:12] if item.get("name")))
    lines.append("Query trace:")
    for q in queries:
        state = "ok" if q.get("ok") else "failed"
        lines.append(f"- [{q.get('family')}] {q.get('query')} — {state}; {q.get('results', 0)} results, {q.get('new_results', 0)} new")
    lines.append("Stop reason: " + str(receipt.get("stop_reason") or "unknown"))
    lines.append("Ledger hash: " + str(receipt.get("ledger_final_hash") or ""))
    return "\n".join(lines)


def load_receipt(receipt_id: str = "latest") -> dict[str, Any] | None:
    _ensure_store()
    with sqlite3.connect(AUDIT_DB) as con:
        if receipt_id.lower() == "latest":
            row = con.execute(
                "SELECT receipt_json FROM research_runs WHERE receipt_json IS NOT NULL ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        else:
            row = con.execute(
                "SELECT receipt_json FROM research_runs WHERE id = ?",
                (receipt_id,),
            ).fetchone()
    if not row or not row[0]:
        return None
    try:
        value = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def verify_receipt_ledger(receipt_id: str) -> tuple[bool, str]:
    _ensure_store()
    with sqlite3.connect(AUDIT_DB) as con:
        rows = con.execute(
            "SELECT seq, occurred_at, kind, payload_json, prev_hash, event_hash FROM research_events WHERE run_id = ? ORDER BY seq",
            (receipt_id,),
        ).fetchall()
    previous = ""
    if not rows:
        return False, "no ledger events"
    for seq, occurred_at, kind, payload_json, prev_hash, event_hash in rows:
        if str(prev_hash or "") != previous:
            return False, f"broken previous-hash link at event {seq}"
        canonical = _canonical_event(seq, occurred_at, kind, payload_json, previous)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if expected != event_hash:
            return False, f"hash mismatch at event {seq}"
        previous = expected
    return True, previous


def _plan_queries(question: str) -> list[QuerySpec]:
    # The eight-family audit protocol is a deterministic coverage contract.
    # A small model must not silently drop requirements while inventing search
    # families or paraphrasing product identifiers. Semantic expansion remains
    # opt-in; the default plan preserves the supplied question in each family.
    if os.environ.get("JARVIS_RESEARCH_PLAN_USE_QWEN", "").strip().lower() not in {"1", "true", "yes"}:
        return _fallback_plan(question)
    system = """Create an auditable web-search plan for a high-stakes comparison/discovery request.
Return JSON only as {"queries":[{"family":"...","query":"...","rationale":"..."}]}.
Use exactly these eight families once each: precision, breadth, constraints, authoritative, independent, disconfirming, long_tail, adversarial.
Each query must be self-contained and preserve concrete user constraints. The families mean:
precision = direct literal request; breadth = synonyms/categories/alternatives; constraints = must-haves/budget/location/date; authoritative = primary/official/specification sources; independent = reviews/comparisons not controlled by candidates; disconfirming = drawbacks/failures/exclusions; long_tail = overlooked/niche/less prominent candidates; adversarial = query explicitly trying to find a superior candidate that the obvious shortlist missed.
Do not answer the request. Do not invent facts. Maximum 220 characters per query."""
    payload = {
        "model": FAST_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Current date: {datetime.now().astimezone().date().isoformat()}\nRequest: {question[:5000]}"},
        ],
        "options": {"temperature": 0, "num_predict": 900},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        parsed = json.loads(str((data.get("message") or {}).get("content") or "{}"))
        rows = parsed.get("queries") if isinstance(parsed, dict) else None
        if isinstance(rows, list):
            specs = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                family = str(row.get("family") or "").strip().lower()
                query = " ".join(str(row.get("query") or "").split())[:220]
                rationale = " ".join(str(row.get("rationale") or "").split())[:240]
                if family in REQUIRED_FAMILIES and query:
                    specs.append(QuerySpec(family, query, rationale))
            if specs:
                return specs
    except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return _fallback_plan(question)


def _fallback_plan(question: str) -> list[QuerySpec]:
    q = " ".join(question.split())[:180]
    suffixes = {
        "precision": "",
        "breadth": " alternatives options comparison",
        "constraints": " requirements constraints eligibility",
        "authoritative": " official specifications documentation",
        "independent": " independent review comparison",
        "disconfirming": " drawbacks problems complaints exclusions",
        "long_tail": " overlooked lesser known niche alternatives",
        "adversarial": " better alternative missed by common recommendations",
    }
    return [QuerySpec(family, (q + suffixes[family]).strip(), "deterministic fallback") for family in REQUIRED_FAMILIES]


def _normalize_plan(question: str, specs: Iterable[QuerySpec]) -> list[QuerySpec]:
    by_family: dict[str, QuerySpec] = {}
    used_queries: set[str] = set()
    for spec in specs:
        family = str(spec.family).strip().lower()
        query = " ".join(str(spec.query).split())[:220]
        key = query.lower()
        if family not in REQUIRED_FAMILIES or not query or key in used_queries or family in by_family:
            continue
        by_family[family] = QuerySpec(family, query, str(spec.rationale)[:240])
        used_queries.add(key)
    fallback = {item.family: item for item in _fallback_plan(question)}
    return [by_family.get(family, fallback[family]) for family in REQUIRED_FAMILIES]


def _extract_candidates(question: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not evidence:
        return []
    prompt_rows = _evidence_for_model(evidence, max_items=42, max_chars=22000)
    system = """Extract concrete candidate options from web search evidence for the user's comparison/discovery request.
Return JSON only: {"candidates":[{"name":"canonical name","eligibility":"eligible|excluded|uncertain","reason":"short reason","evidence_ids":["E1"]}]}.
Candidate means a specific option the user could plausibly select: product/model, business, hotel, service, route, provider, paper, policy option, etc. Do not invent candidates. Merge duplicate names. Evidence IDs must exist in the supplied evidence. If the task does not involve candidates, return an empty array."""
    payload = {
        "model": FAST_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Request: {question[:4000]}\n\nEvidence:\n{prompt_rows}"},
        ],
        "options": {"temperature": 0, "num_predict": 1400},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(35.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        parsed = json.loads(str((data.get("message") or {}).get("content") or "{}"))
    except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
        return []
    rows = parsed.get("candidates") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return []
    valid_ids = {item["id"] for item in evidence}
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = " ".join(str(row.get("name") or "").split())[:220]
        if not name:
            continue
        key = _name_key(name)
        ids = [str(v) for v in row.get("evidence_ids", []) if str(v) in valid_ids][:12]
        eligibility = str(row.get("eligibility") or "uncertain").lower()
        if eligibility not in {"eligible", "excluded", "uncertain"}:
            eligibility = "uncertain"
        item = merged.setdefault(key, {
            "name": name,
            "eligibility": eligibility,
            "reason": " ".join(str(row.get("reason") or "").split())[:400],
            "evidence_ids": [],
        })
        for evidence_id in ids:
            if evidence_id not in item["evidence_ids"]:
                item["evidence_ids"].append(evidence_id)
        if item["eligibility"] == "uncertain" and eligibility != "uncertain":
            item["eligibility"] = eligibility
    return list(merged.values())[:80]


def _coverage_metrics(
    specs: list[QuerySpec],
    query_stats: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    failures: list[str],
) -> dict[str, Any]:
    successful = [q for q in query_stats if q.get("ok")]
    unique_fingerprints = {item.get("fingerprint") for item in evidence if item.get("fingerprint")}
    domains = {str(item.get("domain") or "") for item in evidence if item.get("domain")}
    late = query_stats[-2:] if len(query_stats) >= 2 else query_stats
    late_total = sum(int(q.get("results") or 0) for q in late)
    late_new = sum(int(q.get("new_results") or 0) for q in late)
    late_novelty = late_new / late_total if late_total else 1.0

    candidate_estimate = _candidate_capture_recall(candidates, evidence)
    required_ok = len({q.get("family") for q in successful})
    domain_count = len(domains)

    if (
        required_ok == len(REQUIRED_FAMILIES)
        and not failures
        and domain_count >= 8
        and len(unique_fingerprints) >= 20
        and late_novelty <= 0.30
        and (candidate_estimate is None or candidate_estimate >= 0.85)
    ):
        grade = "A"
        label = "high-coverage audited search"
    elif (
        required_ok >= 6
        and domain_count >= 5
        and len(unique_fingerprints) >= 12
        and late_novelty <= 0.50
        and (candidate_estimate is None or candidate_estimate >= 0.65)
    ):
        grade = "B"
        label = "moderate-coverage audited search"
    else:
        grade = "C"
        label = "incomplete or weakly saturated search"

    return {
        "grade": grade,
        "coverage_label": label,
        "queries_planned": len(specs),
        "queries_executed": len(query_stats),
        "successful_families": required_ok,
        "unique_results": len(unique_fingerprints),
        "unique_domains": domain_count,
        "late_query_novelty": round(late_novelty, 4),
        "candidate_count": len(candidates),
        "candidate_capture_recall_estimate": None if candidate_estimate is None else round(candidate_estimate, 4),
        "provider_failures": len(failures),
        "disconfirming_executed": any(q.get("family") == "disconfirming" and q.get("ok") for q in query_stats),
        "long_tail_executed": any(q.get("family") == "long_tail" and q.get("ok") for q in query_stats),
        "adversarial_executed": any(q.get("family") == "adversarial" and q.get("ok") for q in query_stats),
        "open_web_completeness_known": False,
    }


def _candidate_capture_recall(candidates: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> float | None:
    if len(candidates) < 2:
        return None
    id_to_family = {str(item.get("id")): str(item.get("family")) for item in evidence}
    first_group = {"precision", "breadth", "constraints", "authoritative"}
    second_group = {"independent", "disconfirming", "long_tail", "adversarial"}
    a: set[str] = set()
    b: set[str] = set()
    for candidate in candidates:
        key = _name_key(str(candidate.get("name") or ""))
        families = {id_to_family.get(str(eid), "") for eid in candidate.get("evidence_ids", [])}
        if families & first_group:
            a.add(key)
        if families & second_group:
            b.add(key)
    if not a or not b:
        return None
    overlap = len(a & b)
    if overlap == 0:
        return 0.0
    # Chapman capture-recapture estimator; used as a calibration signal, never as
    # proof that the open web has been exhaustively enumerated.
    estimated_total = ((len(a) + 1) * (len(b) + 1) / (overlap + 1)) - 1
    discovered = len(a | b)
    if estimated_total <= 0:
        return None
    return max(0.0, min(1.0, discovered / estimated_total))


def _stop_reason(metrics: dict[str, Any], failures: list[str]) -> str:
    if failures:
        return "Search budget completed with one or more provider/query-family failures; result is explicitly uncertified as exhaustive."
    novelty = float(metrics.get("late_query_novelty") or 0)
    if metrics.get("grade") == "A":
        return f"All independent query families completed and late-query novelty fell to {novelty:.0%}; additional search had diminishing returns."
    if metrics.get("grade") == "B":
        return f"All/most planned query families completed; late-query novelty was {novelty:.0%}. Coverage is useful but residual candidates may remain."
    return f"Planned query budget was reached while coverage/saturation remained weak (late-query novelty {novelty:.0%}); more search could materially change the answer."


def _synthesize(
    question: str,
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    metrics: dict[str, Any],
    run_id: str,
) -> str:
    if not evidence:
        return ""
    evidence_text = _evidence_for_model(evidence, max_items=48, max_chars=28000)
    candidates_text = json.dumps(candidates[:50], ensure_ascii=False)
    system = """You are Jarvis's audited-research synthesis stage. Use ONLY the supplied search evidence.
The user cares about whether the search was genuinely rigorous. Do not claim the open web was exhaustively searched.
Rules:
- Answer the user's actual question directly.
- Preserve all user constraints.
- If recommending a 'best' option, say 'best found in this audited search' unless the evidence itself establishes a closed finite universe.
- Do not promote a candidate merely because it appeared in more search results.
- Prefer primary/authoritative evidence for objective specs and independent evidence for comparative judgments.
- Surface material contradictions and unknowns.
- If coverage grade is C, explicitly say the search is not sufficiently saturated to call any option the best.
- Do not fabricate sources, candidates, prices, claims, or search steps.
- Keep the spoken answer concise (normally <=180 words); the Research Receipt follows separately."""
    user = (
        f"Request: {question}\n"
        f"Research receipt: {run_id}\n"
        f"Coverage metrics: {json.dumps(metrics, ensure_ascii=False)}\n"
        f"Candidate extraction: {candidates_text}\n\n"
        f"Evidence:\n{evidence_text}"
    )
    payload = {
        "model": FAST_MODEL,
        "stream": False,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user[:36000]},
        ],
        "options": {"temperature": 0, "num_predict": 900},
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(50.0, connect=2.0)) as client:
            response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        answer = " ".join(str((data.get("message") or {}).get("content") or "").split()).strip()
        return answer[:2200]
    except (httpx.HTTPError, ValueError, TypeError):
        return ""


def _fallback_answer(metrics: dict[str, Any], run_id: str) -> str:
    if metrics.get("grade") == "C":
        return f"I completed an audited search, but it did not saturate enough to support a reliable 'best' claim. See Research Receipt {run_id}."
    return f"I completed an audited search. See Research Receipt {run_id} for the verifiable query/source trace."


def _certificate_summary(
    run_id: str,
    metrics: dict[str, Any],
    query_stats: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    stop_reason: str,
) -> str:
    return (
        f"Research Receipt {run_id} — coverage {metrics['grade']}: {metrics['coverage_label']}. "
        f"Executed {metrics['successful_families']}/{len(REQUIRED_FAMILIES)} independent query families; "
        f"observed {metrics['unique_results']} unique results across {metrics['unique_domains']} domains; "
        f"late-query novelty {metrics['late_query_novelty']:.0%}; candidates extracted {len(candidates)}. "
        f"Open-web completeness is not knowable. Stop reason: {stop_reason}"
    )


def _evidence_for_model(evidence: list[dict[str, Any]], *, max_items: int, max_chars: int) -> str:
    # Round-robin families prevents the top precision query from consuming the entire
    # synthesis context and makes long-tail/disconfirming evidence actually visible.
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        buckets[str(item.get("family") or "other")].append(item)
    ordered: list[dict[str, Any]] = []
    while len(ordered) < max_items:
        added = False
        for family in REQUIRED_FAMILIES:
            bucket = buckets.get(family) or []
            if bucket:
                ordered.append(bucket.pop(0))
                added = True
                if len(ordered) >= max_items:
                    break
        if not added:
            break
    lines: list[str] = []
    used = 0
    for item in ordered:
        line = (
            f"[{item.get('id')}] family={item.get('family')} rank={item.get('rank')} "
            f"title={item.get('title')} | domain={item.get('domain')} | date={item.get('date')}\n"
            f"{item.get('text')}\nlink={item.get('link')}"
        )
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n\n".join(lines)


def _normalize_evidence(row: dict[str, Any]) -> dict[str, str]:
    return {
        "kind": _clean(row.get("kind"), 40),
        "title": _clean(row.get("title"), 200),
        "text": _clean(row.get("text"), 900),
        "domain": _clean(row.get("domain"), 160).lower(),
        "date": _clean(row.get("date"), 100),
        "link": _clean(row.get("link"), 1200),
    }


def _clean(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _evidence_fingerprint(item: dict[str, Any]) -> str:
    link = str(item.get("link") or "").strip().lower()
    if link:
        raw = re.sub(r"[#?].*$", "", link).rstrip("/")
    else:
        raw = "|".join((str(item.get("domain") or ""), str(item.get("title") or ""), str(item.get("text") or "")[:220])).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _name_key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _ensure_store() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(AUDIT_DB) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS research_runs (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                receipt_json TEXT,
                final_hash TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS research_events (
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                occurred_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                PRIMARY KEY (run_id, seq)
            )
            """
        )
        con.commit()


def _start_run(run_id: str, question: str, created_at: str) -> None:
    with sqlite3.connect(AUDIT_DB) as con:
        con.execute(
            "INSERT INTO research_runs(id, question, created_at, status) VALUES (?, ?, ?, 'running')",
            (run_id, question, created_at),
        )
        con.commit()


def _append_event(run_id: str, kind: str, payload: dict[str, Any]) -> str:
    occurred = _now()
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with sqlite3.connect(AUDIT_DB) as con:
        row = con.execute(
            "SELECT seq, event_hash FROM research_events WHERE run_id = ? ORDER BY seq DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        seq = int(row[0]) + 1 if row else 1
        previous = str(row[1]) if row else ""
        canonical = _canonical_event(seq, occurred, kind, payload_json, previous)
        event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        con.execute(
            "INSERT INTO research_events(run_id, seq, occurred_at, kind, payload_json, prev_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, seq, occurred, kind, payload_json, previous, event_hash),
        )
        con.commit()
    return event_hash


def _canonical_event(seq: int, occurred_at: str, kind: str, payload_json: str, previous: str) -> str:
    return json.dumps(
        {"seq": int(seq), "occurred_at": occurred_at, "kind": kind, "payload": payload_json, "prev_hash": previous},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _finish_run(run_id: str, receipt: dict[str, Any], final_hash: str) -> None:
    with sqlite3.connect(AUDIT_DB) as con:
        con.execute(
            "UPDATE research_runs SET completed_at = ?, status = ?, receipt_json = ?, final_hash = ? WHERE id = ?",
            (
                str(receipt.get("completed_at") or _now()),
                str(receipt.get("status") or "completed"),
                json.dumps(receipt, ensure_ascii=False, sort_keys=True),
                final_hash,
                run_id,
            ),
        )
        con.commit()


def _write_receipt(receipt: dict[str, Any]) -> None:
    path = RECEIPT_DIR / f"{receipt['receipt_id']}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
