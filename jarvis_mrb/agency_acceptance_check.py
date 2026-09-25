from __future__ import annotations

import json
import sys

from jarvis_mrb.agency_acceptance import run_synthetic_acceptance


def main() -> None:
    result = run_synthetic_acceptance()
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
