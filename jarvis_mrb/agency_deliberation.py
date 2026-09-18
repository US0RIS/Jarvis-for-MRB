from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable

import httpx

from jarvis_mrb.planner_model import QUALITY_MODEL
from jarvis_mrb.world_model import DB_PATH


OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

DEFAULT_ROLES = (
    "evidence",
    "skeptic",
    "feasibility",
    "risk_cost",
)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agency_deliberations (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            agency_step_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            synthesis_json TEXT NOT NULL DEFAULT '{}',
            disagreement_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            wall_ms INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_agency_deliberations
            ON agency_deliberations(status,created_at DESC);

        CREATE TABLE IF NOT EXISTS agency_deliberation_workers (
            id TEXT PRIMARY KEY,
            deliberation_id TEXT NOT NULL REFERENCES agency_deliberations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            output_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            elapsed_ms INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_agency_deliberation_workers
            ON agency_deliberation_workers(deliberation_id,role);
        """
    )
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(agency_deliberations)").fetchall()}
    if "agency_step_id" not in columns:
        conn.execute("ALTER TABLE agency_deliberations ADD COLUMN agency_step_id TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agency_deliberations_step "
        "ON agency_deliberations(agency_step_id,created_at DESC)"
    )
    conn.commit()
    return conn


def _extract_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return {"conclusion": raw[:4000], "claims": [], "risks": [], "unknowns": []}
        try:
            value = json.loads(raw[start : end + 1])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {"conclusion": raw[:4000], "claims": [], "risks": [], "unknowns": []}


def _normalize_worker_output(role: str, raw: Any, *, context: str = "") -> dict[str, Any]:
    value = dict(raw) if isinstance(raw, dict) else {"conclusion": str(raw or "")}
    claims = value.get("claims") if isinstance(value.get("claims"), list) else []
    risks = value.get("risks") if isinstance(value.get("risks"), list) else []
    unknowns = value.get("unknowns") if isinstance(value.get("unknowns"), list) else []
    context_text = str(context or "")
    context_lower = context_text.lower()

    clean_claims: list[dict[str, Any]] = []
    for item in claims[:30]:
        if not isinstance(item, dict):
            continue
        try:
            confidence = max(0.0, min(float(item.get("confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            confidence = 0.0
        source_class = str(item.get("source") or "unknown").strip().lower()
        if source_class not in {"context", "reasoning", "unknown"}:
            source_class = "unknown"
        clean_claims.append(
            {
                "claim": " ".join(str(item.get("claim") or "").split())[:2400],
                "confidence": confidence,
                "evidence": " ".join(str(item.get("evidence") or "").split())[:3000],
                "source": source_class,
            }
        )

    raw_sources = value.get("sources") if isinstance(value.get("sources"), list) else []
    clean_sources: list[str] = []
    for item in raw_sources[:30]:
        source_id = " ".join(str(item or "").split())[:1500]
        if not source_id:
            continue
        # Provenance identifiers are accepted only if they literally occur in the
        # supplied context. The model cannot mint a new source ID by assertion.
        if source_id.lower() in context_lower and source_id not in clean_sources:
            clean_sources.append(source_id)

    return {
        "role": role,
        "conclusion": str(value.get("conclusion") or "")[:5000],
        "claims": clean_claims,
        "risks": [str(item)[:1200] for item in risks[:20]],
        "unknowns": [str(item)[:1200] for item in unknowns[:20]],
        "sources": clean_sources,
    }


def _model_worker(role: str, question: str, context: str) -> dict[str, Any]:
    role_rules = {
        "evidence": "Establish the strongest evidence and distinguish observations from assumptions. Prefer primary evidence supplied in context.",
        "skeptic": "Attack the leading interpretation. Find counterexamples, missing assumptions, and reasons the obvious answer could fail.",
        "feasibility": "Focus on what can actually be executed, dependencies, technical constraints, reversibility, and the cheapest decisive test.",
        "risk_cost": "Analyze downside, opportunity cost, resource cost, failure modes, and actions that create irreversible exposure.",
    }
    system = f"""You are one independent worker in a parallel deliberation.
Your role is {role!r}. {role_rules.get(role, 'Analyze the question independently.')}
Do not try to agree with other workers; you cannot see them.
Return JSON only:
{{
  "conclusion":"...",
  "claims":[{{"claim":"...","confidence":0.0,"evidence":"...","source":"context|reasoning|unknown"}}],
  "risks":["..."],
  "unknowns":["..."],
  "sources":["explicit source identifiers from context only"]
}}
Never invent a source identifier. If evidence is unavailable, say so.
"""
    prompt = f"Question:\n{question[:6000]}\n\nContext:\n{context[:12000]}"
    payload = {
        "model": QUALITY_MODEL,
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": "0",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.2},
    }
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=2.0)) as client:
        response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    return _normalize_worker_output(
        role,
        _extract_json(str((data.get("message") or {}).get("content") or "")),
        context=context,
    )


def _deterministic_disagreement(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface material conflicts without pretending semantic disagreement is exact."""
    disagreements: list[dict[str, Any]] = []
    by_claim: list[tuple[str, str, float]] = []
    for output in outputs:
        role = str(output.get("role") or "")
        for raw in output.get("claims") or []:
            if not isinstance(raw, dict):
                continue
            claim = " ".join(str(raw.get("claim") or "").lower().split())
            if not claim:
                continue
            try:
                confidence = max(0.0, min(float(raw.get("confidence") or 0.0), 1.0))
            except (TypeError, ValueError):
                confidence = 0.0
            by_claim.append((role, claim, confidence))

    # Confidence divergence on text-identical claims is objective and cheap to detect.
    grouped: dict[str, list[tuple[str, float]]] = {}
    for role, claim, confidence in by_claim:
        grouped.setdefault(claim, []).append((role, confidence))
    for claim, values in grouped.items():
        if len(values) < 2:
            continue
        confidences = [value for _, value in values]
        if max(confidences) - min(confidences) >= 0.35:
            disagreements.append(
                {
                    "type": "confidence_divergence",
                    "claim": claim,
                    "workers": [{"role": role, "confidence": confidence} for role, confidence in values],
                }
            )

    conclusions = {
        str(output.get("role") or ""): " ".join(str(output.get("conclusion") or "").split())[:1600]
        for output in outputs
        if str(output.get("conclusion") or "").strip()
    }
    if len(set(value.lower() for value in conclusions.values())) > 1:
        disagreements.append({"type": "different_conclusions", "conclusions": conclusions})
    return disagreements[:20]


def _model_synthesizer(
    question: str,
    context: str,
    outputs: list[dict[str, Any]],
    disagreements: list[dict[str, Any]],
) -> dict[str, Any]:
    system = """Synthesize independent worker analyses without erasing disagreement.
Return JSON only:
{
  "answer":"...",
  "consensus":["..."],
  "disagreements":[{"issue":"...","positions":[{"role":"...","position":"..."}]}],
  "unknowns":["..."],
  "recommended_next_evidence":["..."],
  "confidence":0.0
}
Only use evidence present in the supplied worker outputs/context. Do not invent consensus.
"""
    prompt = (
        f"Question:\n{question[:6000]}\n\n"
        f"Context:\n{context[:8000]}\n\n"
        f"Worker outputs:\n{json.dumps(outputs, ensure_ascii=False)[:24000]}\n\n"
        f"Deterministic disagreement signals:\n{json.dumps(disagreements, ensure_ascii=False)[:8000]}"
    )
    payload = {
        "model": QUALITY_MODEL,
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": "0",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0},
    }
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=2.0)) as client:
        response = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_json(str((data.get("message") or {}).get("content") or ""))


def deliberate(
    question: str,
    *,
    context: str = "",
    roles: list[str] | tuple[str, ...] | None = None,
    worker: Callable[[str, str, str], dict[str, Any]] | None = None,
    synthesizer: Callable[[str, str, list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    clean_question = " ".join(str(question or "").split())
    if not clean_question:
        raise ValueError("Deliberation question is empty.")
    selected_roles = [str(role).strip() for role in (roles or DEFAULT_ROLES) if str(role).strip()]
    if not selected_roles or len(selected_roles) > 12 or len(set(selected_roles)) != len(selected_roles):
        raise ValueError("Deliberation requires 1-12 unique worker roles.")

    deliberation_id = f"deliberation:{uuid.uuid4()}"
    created = _now()
    try:
        from jarvis_mrb.tool_audit import current_agency_step_id
        agency_step_id = current_agency_step_id()
    except Exception:
        agency_step_id = ""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agency_deliberations(id,question,context,agency_step_id,status,created_at)
            VALUES(?,?,?,?,'running',?)
            """,
            (
                deliberation_id,
                clean_question[:8000],
                str(context or "")[:20000],
                str(agency_step_id or ""),
                created,
            ),
        )
        worker_ids: dict[str, str] = {}
        for role in selected_roles:
            worker_id = f"worker:{uuid.uuid4()}"
            worker_ids[role] = worker_id
            conn.execute(
                """
                INSERT INTO agency_deliberation_workers(
                    id,deliberation_id,role,status,started_at
                ) VALUES(?,?,?,'queued',?)
                """,
                (worker_id, deliberation_id, role, created),
            )
        conn.commit()

    worker_fn = worker or _model_worker
    synth_fn = synthesizer or _model_synthesizer
    started = time.monotonic()
    outputs: list[dict[str, Any]] = []
    errors: list[str] = []

    def run_one(role: str) -> tuple[str, dict[str, Any] | None, str, int]:
        worker_started = time.monotonic()
        started_at = _now()
        with _connect() as conn:
            conn.execute(
                "UPDATE agency_deliberation_workers SET status='running',started_at=? WHERE id=?",
                (started_at, worker_ids[role]),
            )
            conn.commit()
        try:
            raw = worker_fn(role, clean_question, str(context or ""))
            output = _normalize_worker_output(role, raw, context=str(context or ""))
            elapsed = int((time.monotonic() - worker_started) * 1000)
            return role, output, "", elapsed
        except Exception as exc:
            elapsed = int((time.monotonic() - worker_started) * 1000)
            return role, None, f"{type(exc).__name__}: {exc}", elapsed

    with ThreadPoolExecutor(
        max_workers=min(len(selected_roles), 8),
        thread_name_prefix="jarvis-deliberation",
    ) as pool:
        futures = {pool.submit(run_one, role): role for role in selected_roles}
        for future in as_completed(futures):
            role, output, error, elapsed = future.result()
            completed = _now()
            with _connect() as conn:
                conn.execute(
                    """
                    UPDATE agency_deliberation_workers
                    SET status=?,output_json=?,completed_at=?,elapsed_ms=?,error=?
                    WHERE id=?
                    """,
                    (
                        "completed" if output is not None else "failed",
                        json.dumps(output or {}, ensure_ascii=False, sort_keys=True),
                        completed,
                        elapsed,
                        error[:3000],
                        worker_ids[role],
                    ),
                )
                conn.commit()
            if output is not None:
                outputs.append(output)
            else:
                errors.append(f"{role}: {error}")

    outputs.sort(key=lambda item: selected_roles.index(str(item.get("role") or "")))
    disagreements = _deterministic_disagreement(outputs)

    synthesis: dict[str, Any]
    if not outputs:
        synthesis = {
            "answer": "",
            "consensus": [],
            "disagreements": disagreements,
            "unknowns": ["All deliberation workers failed."],
            "recommended_next_evidence": [],
            "confidence": 0.0,
        }
        status = "failed"
    else:
        try:
            synthesis = dict(synth_fn(clean_question, str(context or ""), outputs, disagreements))
            status = "completed" if len(outputs) == len(selected_roles) else "partial"
        except Exception as exc:
            errors.append(f"synthesis: {type(exc).__name__}: {exc}")
            synthesis = {
                "answer": outputs[0].get("conclusion") or "",
                "consensus": [],
                "disagreements": disagreements,
                "unknowns": ["Synthesis failed; raw worker outputs are preserved."],
                "recommended_next_evidence": [],
                "confidence": 0.0,
            }
            status = "partial"

    wall_ms = int((time.monotonic() - started) * 1000)
    completed_at = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE agency_deliberations
            SET status=?,synthesis_json=?,disagreement_json=?,completed_at=?,wall_ms=?,error=?
            WHERE id=?
            """,
            (
                status,
                json.dumps(synthesis, ensure_ascii=False, sort_keys=True),
                json.dumps(disagreements, ensure_ascii=False, sort_keys=True),
                completed_at,
                wall_ms,
                "; ".join(errors)[:5000],
                deliberation_id,
            ),
        )
        conn.commit()

    try:
        from jarvis_mrb.world_model import record_event
        record_event(
            "agency.deliberation.completed",
            f"Parallel deliberation {status}: {clean_question[:900]}",
            source_kind="jarvis_agency",
            source_ref=deliberation_id,
            occurred_at=completed_at,
            payload={
                "deliberation_id": deliberation_id,
                "roles": selected_roles,
                "workers_completed": len(outputs),
                "workers_requested": len(selected_roles),
                "disagreement_count": len(disagreements),
                "wall_ms": wall_ms,
            },
            evidence="Independent worker outputs persisted before synthesis.",
            confidence=1.0 if status == "completed" else 0.8,
        )
    except Exception:
        pass

    return {
        "id": deliberation_id,
        "status": status,
        "question": clean_question,
        "agency_step_id": str(agency_step_id or ""),
        "roles": selected_roles,
        "outputs": outputs,
        "disagreements": disagreements,
        "synthesis": synthesis,
        "wall_ms": wall_ms,
        "errors": errors,
    }


def get(deliberation_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agency_deliberations WHERE id=?",
            (str(deliberation_id),),
        ).fetchone()
        if row is None:
            return None
        workers = conn.execute(
            "SELECT * FROM agency_deliberation_workers WHERE deliberation_id=? ORDER BY started_at,role",
            (str(deliberation_id),),
        ).fetchall()
    result = dict(row)
    result["synthesis"] = _extract_json(str(result.pop("synthesis_json")))
    raw_disagreement = result.pop("disagreement_json")
    try:
        result["disagreements"] = json.loads(str(raw_disagreement or "[]"))
    except json.JSONDecodeError:
        result["disagreements"] = []
    result["workers"] = []
    for worker_row in workers:
        item = dict(worker_row)
        item["output"] = _extract_json(str(item.pop("output_json")))
        result["workers"].append(item)
    return result


def status() -> dict[str, Any]:
    with _connect() as conn:
        counts = {
            str(row["status"]): int(row["count"])
            for row in conn.execute(
                "SELECT status,COUNT(*) AS count FROM agency_deliberations GROUP BY status"
            ).fetchall()
        }
    return {"ready": True, "roles": list(DEFAULT_ROLES), "deliberations": counts}
