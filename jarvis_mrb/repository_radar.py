"""Opt-in mechanical GitHub Repository Radar for Jarvis capability discovery.

No assistant ever installs code based on the results. Every candidate is only
a review suggestion. Default command is local snapshot inspection; discovery
requires explicitly specifying `--scan` and talks ONLY to GitHub's official
search API. Untrusted titles/descriptions are treated as data, not commands.

Run: python -m jarvis_mrb.repository_radar --scan
     python -m jarvis_mrb.repository_radar --summary
Optional JARVIS_GITHUB_TOKEN increases GitHub's request budget.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import json
import os
import re
from typing import Any, Callable

import httpx

_DEFAULT_PATH = Path(os.environ.get("APPDATA") or Path.home()) / "JarvisForMRB" / "repository_radar.json"
_API = "https://api.github.com/search/repositories"
_BUCKETS = {
    "voice": ("topic:text-to-speech stars:>200", "voice cloning created:>2026-01-01 stars:>200"),
    "computer_use": ("topic:computer-use stars:>100", "desktop automation agent stars:>300"),
    "browser": ("topic:browser-automation stars:>1000", "agent browser created:>2026-01-01 stars:>300"),
    "memory": ("topic:knowledge-graph stars:>1000", "agent memory created:>2026-01-01 stars:>200"),
    "vision": ("topic:computer-vision stars:>1000", "video analysis local inference stars:>500"),
    "geospatial": ("topic:geospatial stars:>500", "open source OSINT map created:>2026-01-01"),
    "cameras": ("topic:rtsp stars:>100", "camera video rtsp local stars:>500"),
    "physical": ("topic:home-automation stars:>1000", "topic:sdr stars:>200"),
    "reactive": ("topic:workflow-automation stars:>1000", "topic:change-detection stars:>100"),
    "verification": ("topic:llm-evaluation stars:>200", "agent observability trace stars:>300"),
}
_REPO=re.compile(r"^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read(path: Path) -> dict[str,Any]:
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value,dict) and isinstance(value.get("repos"),list):
            return value
    except (OSError, ValueError):
        pass
    return {"repos":[],"scanned_at":None,"queries_executed":0}


def _write(path: Path, data: dict[str,Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    temp.replace(path)


def _clean(text: Any,limit: int=240) -> str:
    return " ".join(str(text or "").split())[:limit]


def _score(repo: dict[str,Any], *,now: datetime) -> float:
    """Transparent heuristic, not a benchmark of quality or safety."""
    stars=max(0,int(repo["stars"]))
    size=min(9.0,(stars+1).bit_length()/3.0)
    updated=repo.get("updated_at")
    freshness=0.0
    try:
        dt=datetime.fromisoformat(str(updated).replace("Z","+00:00"))
        age=max(0.0,(now-dt.astimezone(timezone.utc)).total_seconds()/86400)
        freshness=4.0 if age<=14 else (2.0 if age<=60 else (1.0 if age<=180 else 0.0))
    except (ValueError,TypeError):
        pass
    license_bonus=1.0 if repo.get("license") in {"mit","apache-2.0","bsd-3-clause","bsd-2-clause"} else 0.0
    return round(size+freshness+license_bonus,2)


def _parse(raw: Any, *, bucket: str, now: datetime) -> dict[str,Any] | None:
    if not isinstance(raw,dict):
        return None
    full=_clean(raw.get("full_name"),181)
    if not _REPO.fullmatch(full):
        return None
    if raw.get("archived") or raw.get("disabled") or raw.get("fork"):
        return None
    html_url=str(raw.get("html_url") or "")
    if html_url != "https://github.com/"+full:
        return None
    license_obj=raw.get("license")
    license_key=_clean(license_obj.get("key"),35).lower() if isinstance(license_obj,dict) else ""
    result={
        "full_name":full,
        "url":html_url,
        "description":_clean(raw.get("description"),260),
        "stars":max(0,int(raw.get("stargazers_count") or 0)),
        "updated_at":_clean(raw.get("updated_at"),40),
        "license":license_key,
        "buckets":[bucket],
        "review_status":"candidate_not_validated_or_installed",
    }
    result["discovery_score"]=_score(result,now=now)
    return result


def _request(client: httpx.Client, query: str, *,token: str="",max_results: int=10) -> list[dict[str,Any]]:
    headers={
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"jarvis-repository-radar/1.0",
    }
    if token:
        headers["Authorization"]="Bearer "+token
    response=client.get(_API,params={"q":query,"per_page":max_results,"sort":"stars","order":"desc"},
                        headers=headers,timeout=httpx.Timeout(12,connect=3))
    response.raise_for_status()
    data=response.json()
    if not isinstance(data,dict) or not isinstance(data.get("items"),list):
        raise ValueError("GitHub returned malformed repository search response")
    return data["items"][:max_results]


def scan(*, path: Path = _DEFAULT_PATH, client: httpx.Client|None=None,
         buckets: dict[str,tuple[str,...]]|None=None,
         now: datetime|None=None,
         token: str|None=None) -> dict[str,Any]:
    now=now or _now()
    if now.tzinfo is None:
        raise ValueError("Radar requires timezone-aware scan time")
    buckets=buckets or _BUCKETS
    existing=_read(path)
    old_names={x.get("full_name") for x in existing.get("repos",[]) if isinstance(x,dict)}
    seen: dict[str,dict[str,Any]]={}
    errors=[]
    executed=0
    owns=client is None
    client=client or httpx.Client(trust_env=False)
    token = os.environ.get("JARVIS_GITHUB_TOKEN","").strip() if token is None else token
    try:
        for bucket,queries in buckets.items():
            for query in queries:
                try:
                    entries=_request(client,query,token=token)
                    executed+=1
                except (httpx.HTTPError,ValueError) as exc:
                    # Preserve the last known-good snapshot when provider is
                    # unavailable; a broken scan is never a clean empty list.
                    errors.append({"bucket":bucket,"kind":type(exc).__name__})
                    continue
                for raw in entries:
                    parsed=_parse(raw,bucket=bucket,now=now)
                    if parsed is None:
                        continue
                    name=parsed["full_name"]
                    if name in seen:
                        if bucket not in seen[name]["buckets"]:
                            seen[name]["buckets"].append(bucket)
                    else:
                        seen[name]=parsed
    finally:
        if owns:client.close()

    if not executed:
        return {"ok":False,"status":"source_unavailable","previous":existing,
                "errors":errors,"queries_executed":0}
    ranked=sorted(seen.values(),key=lambda x:(-x["discovery_score"],-x["stars"],x["full_name"]))
    novel=[x for x in ranked if x["full_name"] not in old_names]
    snapshot={
        "scanned_at":now.isoformat(),
        "source":"GitHub official REST repository search",
        "queries_executed":executed,
        "partial":bool(errors),
        "errors":errors,
        "new_candidates":len(novel),
        "repos":ranked[:250],
        "criteria":"Heuristic stars/recency/license only. No source code or security audit.",
        "requires_manual_review":True,
    }
    _write(path,snapshot)
    return {"ok":True,"status":"partial" if errors else "completed",
            "new_candidates":len(novel),"total":len(ranked[:250]),
            "top_new":novel[:20],"queries_executed":executed,
            "errors":errors,"saved_to":str(path)}


def inspect(*,path: Path=_DEFAULT_PATH) -> dict[str,Any]:
    state=_read(path)
    return {
        "scanned_at":state.get("scanned_at"),
        "count":len(state["repos"]),
        "queries_executed":state.get("queries_executed",0),
        "top_candidates":state["repos"][:20],
        "status":"previous_local_snapshot_not_current_availability_or_code_verification",
    }


def main(argv: list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(description="Mechanical GitHub discovery; no installations or deployments")
    parser.add_argument("--scan",action="store_true",help="Explicitly scan GitHub now")
    parser.add_argument("--summary",action="store_true",help="Read last local snapshot")
    args=parser.parse_args(argv)
    result=scan() if args.scan else inspect()
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result.get("ok",True) else 1


if __name__=="__main__":
    raise SystemExit(main())
