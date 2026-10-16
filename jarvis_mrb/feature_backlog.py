"""Deterministic inventory of future.md ideas.

A backlog line is not an implemented feature. This parser inventories every
bold-led idea, stores stable IDs based on its heading+title and never promotes
anything from planned to verified. It intentionally keeps research candidates
separate from executable features.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
HEADING=re.compile(r"^(#{2,4})\s+(.+?)\s*$")
BOLD_BULLET=re.compile(r"^\s*-\s+\*\*(.+?)\*\*\s*(.*)$")
# Plain bullets can also represent features. Capture them conservatively:
PLAIN_BULLET=re.compile(r"^\s*-\s+([^*#].+?)\s*$")


def _name(value: str) -> str:
    value=re.sub(r"[\s\u200b]+"," ",value).strip()
    return value.rstrip(".:-–— ")


def _id(heading: str,title: str) -> str:
    key=(heading+"\n"+title).casefold().encode("utf-8")
    return hashlib.blake2s(key,digest_size=10).hexdigest()


def inventory(content: str) -> dict[str, Any]:
    if not isinstance(content,str):
        raise ValueError("Content must be Markdown text.")
    items=[]
    current_heading=""
    parents: dict[int,str]={}
    for lineno,line in enumerate(content.splitlines(),start=1):
        hm=HEADING.match(line)
        if hm:
            level=len(hm.group(1))
            parents[level]=_name(hm.group(2))
            for depth in list(parents):
                if depth>level:
                    del parents[depth]
            current_heading=" / ".join(parents[d] for d in sorted(parents))
            continue
        bm=BOLD_BULLET.match(line)
        if not bm or not current_heading:
            continue
        title=_name(bm.group(1))
        if not title or title.lower().startswith(("http://","https://")):
            continue
        kind=(
            "repository_candidate" if any(t in current_heading.lower()
             for t in ("github survey","gitHub capability".lower(),"mechanical sweep","voice stack replacement"))
            else "feature_idea"
        )
        items.append({
            "id":"f_"+_id(current_heading,title),
            "title":title[:240],
            "section":current_heading,
            "source_line":lineno,
            "kind":kind,
            # Source file is a proposal, not a receipt. No status inference.
            "status":"not_verified_from_future_md",
        })
    unique={}
    duplicates=[]
    for item in items:
        if item["id"] in unique:
            duplicates.append({"id":item["id"],"first_line":unique[item["id"]]["source_line"],
                               "repeated_line":item["source_line"]})
        else:
            unique[item["id"]]=item
    counted=Counter(x["kind"] for x in unique.values())
    return {
        "source":"future.md",
        "source_sha256":hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "total":len(unique),
        "counts":dict(counted),
        "duplicates":duplicates,
        "items":list(unique.values()),
        "status_contract":"All ideas remain unverified until a separate acceptance ledger has passing evidence.",
    }


def load(path: Path|str=ROOT/"future.md") -> dict[str,Any]:
    return inventory(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(description="Inventory ALL bold-led ideas in future.md without making completion claims.")
    parser.add_argument("--path",type=Path,default=ROOT/"future.md")
    parser.add_argument("--summary",action="store_true",help="Emit counts instead of full manifest")
    args=parser.parse_args(argv)
    result=load(args.path)
    if args.summary:
        result={key:value for key,value in result.items() if key!="items"}
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
