from __future__ import annotations

import argparse
import json

from jarvis_mrb.agency_release import release_status, run_full_validation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Jarvis Agency 1.0 release evidence for the exact deployed SHA."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run compileall, the full unittest suite, synthetic Agency acceptance, and strict diagnostics before evaluating release evidence.",
    )
    args = parser.parse_args()

    if args.full:
        validation = run_full_validation()
        status = validation.get("release_status") if isinstance(validation.get("release_status"), dict) else release_status()
        result = {"validation": validation, "release": status}
    else:
        status = release_status()
        result = {"release": status}

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    raise SystemExit(0 if bool(status.get("release_ready")) else 1)


if __name__ == "__main__":
    main()
