"""Measured bake-offs and regression harnesses (Kant).

future.md ideas implemented here: Voice replacement acceptance test (repeatable
TTS bake-off scoring measured cold start, time-to-first-audio, RTF, VRAM,
intelligibility/naming, identity consistency, streaming, barge-in release,
long-run reliability, local-only operation and API-contract fit; Kokoro stays the
baseline until beaten), the Gemma 4 / local-model acceptance harness and
promotion rule (beat the incumbent on the Jarvis suite, not generic benchmarks),
the vision bake-off scaffold, promptfoo-style eval matrices across models x
prompts, and a langfuse-style trace/capability evidence ledger.

This module runs no models.  Callers execute candidates on the actual Jarvis PC
and feed measurements in; the harness enforces the decision rules.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, plain, stable_id

# =========================================================================== TTS bake-off

TTS_CORPUS = {
    "short": ["Done.", "Lights are on.", "Leaving in five minutes.", "No new mail.", "Meeting moved to three."],
    "medium": [
        "Your eleven o'clock with Dana was moved to two thirty at the Ventura office on Main Street.",
        "Caltrans reports a closure on Highway 33 north of Ojai until six PM tonight.",
    ],
    "long": [
        "Here is the summary. The lease auto-renews on March thirty-first unless you give sixty days written notice, "
        "which means the deadline is January thirtieth. I've added a reminder two weeks before that date and attached "
        "the clause so you can review it.",
    ],
    "names": ["HORUS", "Mnemosyne", "Cerberus", "NOAA", "Ojai", "Camarillo", "SQL", "Wi-Fi", "1Z999AA1"],
}

TTS_CANDIDATES = [
    "kokoro-82m/bm_george (baseline)", "VoiceStudio:OmniVoice", "VoiceStudio:CosyVoice3", "VoiceStudio:IndexTTS2.5",
    "MOSS-TTS-Nano", "VoiceStudio:PocketTTS", "chatterbox", "F5-TTS", "fish-speech", "qwentts.cpp", "FireRedTTS3",
    "k2-fsa/OmniVoice",
]


@dataclass
class TTSMeasurement:
    candidate: str
    cold_start_s: float
    ttfa_ms: dict[str, float]  # bucket (5/15/40 words) -> warm time-to-first-audio
    rtf: float  # real-time factor (synthesis time / audio duration)
    vram_gb: float
    mos_naturalness: float  # 1..5 listener score
    intelligibility: float  # 0..1 (e.g. ASR round-trip word accuracy)
    name_accuracy: float  # 0..1 pronunciation of names/acronyms
    long_stability: float  # 0..1
    identity_consistency: float  # 0..1 same voice across 100+ generations
    streaming: bool
    cancel_latency_ms: float
    releases_work_on_cancel: bool
    sequential_failures: int  # out of 100+
    recovers_after_restart: bool
    local_only: bool
    license_ok: bool
    api_contract_fit: bool


TTS_HARD_GATES = ("local_only", "license_ok", "api_contract_fit", "releases_work_on_cancel", "recovers_after_restart")


def score_tts(m: TTSMeasurement) -> dict[str, Any]:
    gates = {g: bool(getattr(m, g)) for g in TTS_HARD_GATES}
    gates["reliable"] = m.sequential_failures <= 1
    gates["realtime"] = m.rtf < 1.0
    latency = statistics.mean(m.ttfa_ms.values()) if m.ttfa_ms else 1e9
    score = (
        25 * (m.mos_naturalness - 1) / 4
        + 15 * m.intelligibility
        + 10 * m.name_accuracy
        + 10 * m.long_stability
        + 10 * m.identity_consistency
        + 15 * max(0.0, 1 - latency / 1000)
        + 5 * max(0.0, 1 - m.cancel_latency_ms / 500)
        + 5 * (1.0 if m.streaming else 0.0)
        + 5 * max(0.0, 1 - m.vram_gb / 16)
    )
    return {"candidate": m.candidate, "score": round(score, 2), "gates": gates, "eligible": all(gates.values()),
            "mean_ttfa_ms": round(latency, 1)}


def tts_decision(measurements: list[TTSMeasurement], *, baseline: str, min_margin: float = 5.0,
                 max_latency_regression_ms: float = 100.0) -> dict[str, Any]:
    """Keep the baseline until another stack is *demonstrably* better on the
    dimensions that matter in conversation."""
    scored = {m.candidate: score_tts(m) for m in measurements}
    if baseline not in scored:
        raise ValueError("baseline must be measured on the same corpus and hardware")
    base = scored[baseline]
    better = [s for c, s in scored.items() if c != baseline and s["eligible"]
              and s["score"] >= base["score"] + min_margin
              and s["mean_ttfa_ms"] <= base["mean_ttfa_ms"] + max_latency_regression_ms]
    better.sort(key=lambda s: -s["score"])
    return {"decision": better[0]["candidate"] if better else baseline,
            "replace": bool(better), "ranking": sorted(scored.values(), key=lambda s: -s["score"])}


def measure_ttfa(synthesize_stream: Callable[[str], Iterable[bytes]], text: str) -> dict[str, float]:
    """Helper: time-to-first-audio-chunk and total time for a streaming synthesizer."""
    t0 = time.perf_counter()
    first = None
    total_bytes = 0
    for chunk in synthesize_stream(text):
        if first is None:
            first = time.perf_counter() - t0
        total_bytes += len(chunk)
    return {"ttfa_ms": round((first or 0) * 1000, 2), "total_ms": round((time.perf_counter() - t0) * 1000, 2),
            "bytes": total_bytes}


# =========================================================================== model acceptance harness


@dataclass
class ModelRun:
    model: str
    task_id: str
    success: bool
    tool_call_valid: bool
    hallucinated: bool
    ttft_ms: float
    tokens_per_s: float
    vram_gb: float
    category: str = "general"


MODEL_CANDIDATES = ["current fast planner (Qwen 8B)", "current quality planner (Qwen 27B)", "Gemma 4 12B Unified",
                    "Moondream (vision)"]


def summarize_runs(runs: list[ModelRun]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    by: dict[str, list[ModelRun]] = {}
    for r in runs:
        by.setdefault(r.model, []).append(r)
    for m, rs in by.items():
        out[m] = {
            "n": len(rs),
            "success": sum(r.success for r in rs) / len(rs),
            "tool_valid": sum(r.tool_call_valid for r in rs) / len(rs),
            "hallucination": sum(r.hallucinated for r in rs) / len(rs),
            "ttft_ms_p50": statistics.median(r.ttft_ms for r in rs),
            "tok_s": statistics.mean(r.tokens_per_s for r in rs),
            "vram_gb_max": max(r.vram_gb for r in rs),
        }
    return out


def promotion_decision(runs: list[ModelRun], *, incumbent: str, candidate: str, vram_budget_gb: float = 16.0,
                       max_ttft_ms: float | None = None, min_tasks: int = 30) -> dict[str, Any]:
    """Promotion rule: the candidate becomes a default lane only after beating the
    incumbent on the *same* Jarvis task corpus, within VRAM/latency budgets."""
    s = summarize_runs(runs)
    if incumbent not in s or candidate not in s:
        return {"promote": False, "reason": "both models must run the same suite"}
    inc, cand = s[incumbent], s[candidate]
    shared = {r.task_id for r in runs if r.model == incumbent} & {r.task_id for r in runs if r.model == candidate}
    reasons = []
    if len(shared) < min_tasks:
        reasons.append(f"only {len(shared)} shared tasks (< {min_tasks})")
    if cand["vram_gb_max"] > vram_budget_gb:
        reasons.append("exceeds VRAM budget")
    if max_ttft_ms is not None and cand["ttft_ms_p50"] > max_ttft_ms:
        reasons.append("too slow for intended cadence")
    if cand["success"] <= inc["success"]:
        reasons.append("does not beat incumbent task success")
    if cand["hallucination"] > inc["hallucination"]:
        reasons.append("hallucinates more than incumbent")
    if cand["tool_valid"] < inc["tool_valid"]:
        reasons.append("worse tool-call validity")
    return {"promote": not reasons, "reasons": reasons or ["beats incumbent on the Jarvis suite"],
            "incumbent": inc, "candidate": cand}


# =========================================================================== eval matrix / traces


def eval_matrix(models: dict[str, Callable[[str], str]], prompts: dict[str, str],
                assertions: dict[str, Callable[[str], bool]]) -> dict[str, Any]:
    """promptfoo-style matrix: every model x prompt, each graded by its assertion."""
    rows = []
    for mname, fn in models.items():
        for pid, prompt in prompts.items():
            try:
                out = fn(prompt)
                ok = bool(assertions[pid](out))
                err = None
            except Exception as exc:  # noqa: BLE001
                out, ok, err = None, False, repr(exc)
            rows.append({"model": mname, "prompt": pid, "pass": ok, "output": out, "error": err})
    totals = {m: sum(r["pass"] for r in rows if r["model"] == m) for m in models}
    return {"rows": rows, "pass_counts": totals}


class TraceLedger:
    """Capture full model/tool traces so a failed 'Jarvis did X' claim can be
    reconstructed rather than guessed at."""

    def __init__(self) -> None:
        self.traces: dict[str, list[dict[str, Any]]] = {}

    def start(self, request: str, at: datetime) -> str:
        tid = stable_id(request, at, length=12)
        self.traces[tid] = [{"type": "request", "text": request, "at": as_dt(at).isoformat()}]
        return tid

    def span(self, tid: str, kind: str, at: datetime, **data: Any) -> None:
        self.traces[tid].append({"type": kind, "at": as_dt(at).isoformat(), **plain(data)})

    def claim_supported(self, tid: str, claim: str) -> dict[str, Any]:
        """Does the trace contain a verified receipt backing the user-visible claim?"""
        receipts = [s for s in self.traces.get(tid, []) if s["type"] == "receipt" and s.get("verified")]
        tools = [s for s in self.traces.get(tid, []) if s["type"] == "tool"]
        return {"claim": claim, "supported": bool(receipts), "tool_calls": len(tools), "receipts": receipts}


@dataclass
class VisionCase:
    id: str
    image_ref: str
    question: str
    expected: str
    kind: str  # scene | ocr | change | multi_frame


def score_vision(cases: list[VisionCase], answers: dict[str, dict[str, Any]], *, latency_budget_ms: float) -> dict[str, Any]:
    """Vision bake-off: accuracy, calibration of stated confidence, latency vs cadence."""
    correct, within, calib = 0, 0, []
    for c in cases:
        a = answers.get(c.id, {})
        ok = c.expected.lower() in str(a.get("text", "")).lower()
        correct += ok
        within += a.get("latency_ms", 1e9) <= latency_budget_ms
        if "confidence" in a:
            calib.append((float(a["confidence"]) - (1.0 if ok else 0.0)) ** 2)
    n = len(cases) or 1
    return {"accuracy": correct / n, "within_cadence": within / n,
            "brier": (sum(calib) / len(calib)) if calib else None}

