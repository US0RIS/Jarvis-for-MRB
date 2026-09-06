from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed Jarvis end-to-end acceptance scenario in a temporary isolated world database. "
            "This does not contact external services or modify deployed user data."
        )
    )
    parser.add_argument("--compact", action="store_true", help="Print compact JSON.")
    args = parser.parse_args()

    from jarvis_mrb.world_acceptance import run_synthetic_acceptance

    result = run_synthetic_acceptance()
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=True,
            default=str,
        )
    )
    raise SystemExit(0 if bool(result.get("ok")) else 1)


if __name__ == "__main__":
    main()
