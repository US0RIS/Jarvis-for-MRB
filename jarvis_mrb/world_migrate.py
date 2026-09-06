from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upgrade the Jarvis persistent world-model schema safely and idempotently."
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the pre-upgrade SQLite backup. Use only when another verified backup already exists.",
    )
    args = parser.parse_args()

    from jarvis_mrb.world_migrations import run_migrations

    result = run_migrations(backup=not args.no_backup)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
