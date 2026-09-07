from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis_mrb.jarvis20 import history, plan, run_preflight, save_scored_run, score_run, score_template
from jarvis_mrb.jarvis20_variants import generate_variant_bundle, validate_variant_bundle, write_variant_bundle


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _parse_anchor(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS-20 fixed behavioral evaluation suite")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser("plan", help="Show the frozen 20-test specification")
    plan_parser.add_argument("--compact", action="store_true")

    preflight_parser = sub.add_parser("preflight", help="Run source/integration prerequisites without awarding behavioral score")
    preflight_parser.add_argument("--strict", action="store_true", help="Return nonzero if any preflight check fails")

    template_parser = sub.add_parser("template", help="Generate a blank 20-test score sheet")
    template_parser.add_argument("--seed", default="")
    template_parser.add_argument("--output", type=Path)

    generate_parser = sub.add_parser("generate", help="Generate a replayable procedural JARVIS-20 scenario")
    generate_parser.add_argument("--seed", required=True, help="Non-empty deterministic variant seed")
    generate_parser.add_argument("--anchor", help="Optional ISO-8601 anchor time; omit for current UTC time")
    generate_parser.add_argument("--output", required=True, type=Path, help="Public scenario JSON")
    generate_parser.add_argument("--oracle-output", type=Path, help="Hidden oracle JSON; keep away from the system under test")
    generate_parser.add_argument("--score-output", type=Path, help="Pre-populated scoring sheet JSON")

    validate_parser = sub.add_parser("validate-variant", help="Validate a generated scenario and optional hidden oracle")
    validate_parser.add_argument("public", type=Path)
    validate_parser.add_argument("--oracle", type=Path)

    score_parser = sub.add_parser("score", help="Score a completed JARVIS-20 JSON score sheet")
    score_parser.add_argument("file", type=Path)
    score_parser.add_argument("--save", action="store_true")

    history_parser = sub.add_parser("history", help="Show prior saved JARVIS-20 runs")
    history_parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "plan":
        payload = plan()
        if args.compact:
            payload = {
                "name": payload["name"],
                "maximum_score": payload["maximum_score"],
                "north_star_ids": payload["north_star_ids"],
                "tests": [{"id": row["id"], "name": row["name"], "mode": row["mode"]} for row in payload["tests"]],
            }
        _print(payload)
        return 0

    if args.command == "preflight":
        payload = run_preflight()
        _print(payload)
        return 1 if args.strict and not payload.get("ok") else 0

    if args.command == "template":
        payload = score_template(variant_seed=args.seed)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(str(args.output))
        else:
            _print(payload)
        return 0

    if args.command == "generate":
        try:
            anchor = _parse_anchor(args.anchor)
            bundle = generate_variant_bundle(args.seed, anchor=anchor)
            written = write_variant_bundle(
                bundle,
                public_path=args.output,
                oracle_path=args.oracle_output,
                score_path=args.score_output,
            )
            validation = validate_variant_bundle(bundle.public, bundle.oracle)
        except (ValueError, OSError) as exc:
            print(f"JARVIS-20 generation failed: {exc}")
            return 2
        _print({
            "ok": validation["ok"],
            "scenario_id": bundle.public["scenario_id"],
            "seed": bundle.public["seed"],
            "anchor": bundle.public["anchor"],
            "oracle_sha256": bundle.public["oracle_sha256"],
            "written": written,
        })
        return 0 if validation["ok"] else 1

    if args.command == "validate-variant":
        try:
            public = json.loads(args.public.read_text(encoding="utf-8"))
            if not isinstance(public, dict):
                raise ValueError("public variant must contain one JSON object")
            oracle = None
            if args.oracle:
                oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
                if not isinstance(oracle, dict):
                    raise ValueError("oracle must contain one JSON object")
            result = validate_variant_bundle(public, oracle)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"JARVIS-20 variant validation failed: {exc}")
            return 2
        _print(result)
        return 0 if result["ok"] else 1

    if args.command == "score":
        try:
            source = json.loads(args.file.read_text(encoding="utf-8"))
            if not isinstance(source, dict):
                raise ValueError("score file must contain one JSON object")
            report = score_run(source)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"JARVIS-20 score failed: {exc}")
            return 2
        if args.save:
            path = save_scored_run(report)
            report = {**report, "saved_to": str(path)}
        _print(report)
        return 0

    if args.command == "history":
        _print({"suite": "JARVIS-20", "runs": history(limit=max(1, args.limit))})
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
