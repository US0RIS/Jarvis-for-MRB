from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the deployed Jarvis persistent world model without modifying user data."
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of indented JSON.",
    )
    args = parser.parse_args()

    from jarvis_mrb.world_diagnostics import validate

    result = validate()
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
