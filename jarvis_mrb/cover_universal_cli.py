from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jarvis_mrb.cover_universal import aggregate_universal_suite


def _load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("COVER-U input array is invalid.")
        return [row for row in payload if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Line {line_number} is not a JSON object.")
        rows.append(payload)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score a COVER-U benchmark run from JSON or JSONL task records."
    )
    parser.add_argument("input", type=Path, help="JSON array or JSONL file containing benchmark task records")
    parser.add_argument(
        "--profile",
        choices=("standard", "jarvis"),
        default="standard",
        help="Use the universal Standard profile or Jarvis deployment weighting.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    try:
        rows = _load_rows(args.input)
        result = aggregate_universal_suite(rows, profile=args.profile)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"COVER-U scoring failed: {exc}") from exc

    print(json.dumps(result.as_dict(), indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
