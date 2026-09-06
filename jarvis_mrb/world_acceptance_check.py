from __future__ import annotations

import argparse
import json
import os
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed Jarvis end-to-end acceptance scenario in a temporary isolated world database. "
            "This does not contact external services or modify/read deployed user state."
        )
    )
    parser.add_argument("--compact", action="store_true", help="Print compact JSON.")
    args = parser.parse_args()

    # The acceptance process must not inherit the deployed permission file or any
    # other APPDATA-backed Jarvis state. Set APPDATA before importing world modules so
    # module-level paths (including permissions.py) are created inside this temporary
    # environment. world_acceptance adds a second, explicit temporary DB redirect.
    old_appdata = os.environ.get("APPDATA")
    with tempfile.TemporaryDirectory() as appdata:
        os.environ["APPDATA"] = appdata
        try:
            from jarvis_mrb.world_acceptance import run_synthetic_acceptance

            result = run_synthetic_acceptance()
        finally:
            if old_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old_appdata

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
