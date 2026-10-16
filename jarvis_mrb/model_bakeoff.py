"""Non-destructive local planner bake-off for candidate Jarvis models.

Run with: python -m jarvis_mrb.model_bakeoff --models qwen3:8b gemma4:12b
Optional --models qwen3.8:27b. Requires locally installed Ollama models.
The synthetic fixture tests routing syntax/latency; it is NOT a verified
real-world Jarvis task, speech, vision, or deployment acceptance result.

No tools are executed. No personal data leaves the local Ollama endpoint.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
from urllib.parse import urlsplit
from typing import Any

import httpx

DEFAULT_MODELS = ("qwen3:8b", "gemma4:12b")
CORPUS = (
    {"id":"arith", "prompt":"What is 13 times 7?", "tool":None},
    {"id":"definition", "prompt":"What is a prime number?", "tool":None},
    {"id":"current_release", "prompt":"Did Google release a new model today?", "tool":"web.search"},
    {"id":"public_post", "prompt":"Did Google post an announcement of Gemini 4 Argon today?", "tool":"web.search"},
    {"id":"local_private", "prompt":"Search my notes for the mortgage renewal date.", "tool":"knowledge.search"},
    {"id":"calendar", "prompt":"What meetings are on my calendar tomorrow?", "tool":"calendar.query"},
    {"id":"device_status", "prompt":"Show my PC's current CPU and RAM usage.", "tool":"system.resources"},
    {"id":"correction", "prompt":"Explain why a screenshot alone is not proof an official product was announced.", "tool":None},
    {"id":"action_no_unverified", "prompt":"Write a short polite sentence asking for a meeting reschedule.", "tool":None},
)

SYSTEM = """You are a local Jarvis planner in a controlled synthetic test.
Respond in a single JSON object with keys "tool" and "arguments".
Use tool=null for explanations, math and text creation.
For current public announcements use web.search; for private user notes
use knowledge.search; for the user's Calendar use calendar.query; for
the PC's live resource state use system.resources.
Never claim an action was performed. Never add text outside the JSON.
Available tools: web.search, knowledge.search, calendar.query,
system.resources. Do not invent other tools."""


def _assert_loopback(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http","https"} or parts.hostname not in {
        "127.0.0.1", "localhost", "::1"
    } or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Benchmark only accepts a loopback Ollama API endpoint.")
    return url.rstrip("/")


def _extract_plan(reply: str) -> dict[str, Any] | None:
    try:
        value=json.loads(reply.strip())
    except (ValueError, TypeError):
        return None
    if not isinstance(value,dict) or "tool" not in value:
        return None
    tool=value["tool"]
    if tool is not None and not isinstance(tool,str):
        return None
    if not isinstance(value.get("arguments"),dict):
        return None
    return value


def _probe(client: httpx.Client, url: str, model: str, prompt: str, *,
           timeout: float = 90.0) -> dict[str, Any]:
    start=time.perf_counter()
    chunks=[]
    first_token=None
    evaluation_count=0
    evaluation_duration=0
    try:
        with client.stream(
            "POST", f"{url}/api/chat",
            json={
                "model":model,
                "stream":True,
                "think":False,
                "options":{"temperature":0,"num_predict":350},
                "messages":[
                    {"role":"system","content":SYSTEM},
                    {"role":"user","content":prompt},
                ],
            },
            timeout=httpx.Timeout(timeout,connect=min(4.0,timeout)),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                event=json.loads(line)
                piece=(event.get("message") or {}).get("content") or ""
                if piece:
                    if first_token is None:
                        first_token=time.perf_counter()
                    chunks.append(piece)
                if event.get("done"):
                    evaluation_count=int(event.get("eval_count") or 0)
                    evaluation_duration=int(event.get("eval_duration") or 0)
                    break
        elapsed=time.perf_counter()-start
        return {
            "ok":True,
            "response":"".join(chunks),
            "wall_seconds":round(elapsed,3),
            "time_to_first_text_seconds":round(first_token-start,3) if first_token is not None else None,
            "eval_tokens":evaluation_count,
            "generation_tokens_per_second":round(evaluation_count/(evaluation_duration/1e9),2) if evaluation_duration else None,
        }
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        return {"ok":False,"error":f"{type(exc).__name__}: {str(exc)[:180]}",
                "time_to_first_text_seconds":None,"wall_seconds":round(time.perf_counter()-start,3)}


def evaluate_model(model: str, *, url: str = "http://127.0.0.1:11434",
                   client: httpx.Client | None = None,
                   corpus: tuple[dict[str,Any], ...] = CORPUS) -> dict[str,Any]:
    if not model or len(model)>120 or any(ord(c)<32 for c in model):
        raise ValueError("Invalid model name.")
    url=_assert_loopback(url)
    owns=client is None
    client=client or httpx.Client(trust_env=False)
    rows=[]
    try:
        for item in corpus:
            outcome=_probe(client,url,model,item["prompt"])
            plan=_extract_plan(outcome.get("response") or "") if outcome["ok"] else None
            expected=item["tool"]
            actual=plan.get("tool") if plan is not None else "__unparseable__"
            rows.append({
                "id":item["id"],"expected_tool":expected,"actual_tool":actual,
                "correct":actual==expected,"parseable":plan is not None,
                "ok":outcome["ok"],"ttft_seconds":outcome.get("time_to_first_text_seconds"),
                "wall_seconds":outcome.get("wall_seconds"),
                "generation_tokens_per_second":outcome.get("generation_tokens_per_second"),
                "error":outcome.get("error"),
            })
    finally:
        if owns: client.close()
    ttft=[r["ttft_seconds"] for r in rows if r["ttft_seconds"] is not None]
    return {
        "model":model,
        "total":len(rows),
        "routing_correct":sum(r["correct"] for r in rows),
        "parseable":sum(r["parseable"] for r in rows),
        "median_ttft_seconds":round(statistics.median(ttft),3) if ttft else None,
        "cases":rows,
        "scope":"synthetic_read_only_routing_probe_not_hardware_or_end_to_end_acceptance",
        "eligible_for_automatic_promotion":False,
    }


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Local model bake-off; never changes the default planner.")
    parser.add_argument("--models",nargs="+",default=list(DEFAULT_MODELS))
    parser.add_argument("--url",default="http://127.0.0.1:11434")
    parser.add_argument("--output",type=Path,default=None)
    args=parser.parse_args(argv)
    url=_assert_loopback(args.url)
    results=[evaluate_model(model,url=url) for model in args.models]
    result={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "models":results,
        "note":"Model selection remains unchanged. No real Jarvis tools were executed.",
    }
    encoded=json.dumps(result,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(encoded+"\n",encoding="utf-8")
    print(encoded)
    return 0 if all(r["routing_correct"]==r["total"] for r in results) else 1


if __name__=="__main__":
    raise SystemExit(main())
