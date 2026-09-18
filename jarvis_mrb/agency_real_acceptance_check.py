from __future__ import annotations

import argparse
import json

from jarvis_mrb.agency_real_acceptance import (
    evaluate_session,
    finalize_session,
    list_sessions,
    start_session,
    status,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run evidence-derived REAL Agency acceptance gate sessions."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start a SHA-bound REAL gate observation session.")
    start.add_argument("gate")
    start.add_argument("--desired-state", default="")
    start.add_argument(
        "--parameters-json",
        default="{}",
        help="Gate-specific JSON parameters, e.g. A11 tool/preference_key.",
    )

    evaluate = sub.add_parser("evaluate", help="Evaluate current evidence without creating a receipt.")
    evaluate.add_argument("session_id")

    finalize = sub.add_parser("finalize", help="Create an immutable receipt only if every derived check passes.")
    finalize.add_argument("session_id")

    listing = sub.add_parser("list", help="List REAL gate sessions.")
    listing.add_argument("--status", default="")
    listing.add_argument("--limit", type=int, default=100)

    sub.add_parser("status", help="Show live acceptance harness status.")

    args = parser.parse_args()
    if args.command == "start":
        try:
            parameters = json.loads(args.parameters_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid --parameters-json: {exc}") from exc
        if not isinstance(parameters, dict):
            raise SystemExit("--parameters-json must decode to a JSON object.")
        result = start_session(
            args.gate,
            desired_state_id=args.desired_state,
            parameters=parameters,
        )
        exit_code = 0
    elif args.command == "evaluate":
        result = evaluate_session(args.session_id)
        exit_code = 0 if bool(result.get("passed")) else 1
    elif args.command == "finalize":
        result = finalize_session(args.session_id)
        exit_code = 0 if bool(result.get("passed")) else 1
    elif args.command == "list":
        result = {
            "sessions": list_sessions(
                status=args.status or None,
                limit=args.limit,
            )
        }
        exit_code = 0
    else:
        result = status()
        exit_code = 0

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
