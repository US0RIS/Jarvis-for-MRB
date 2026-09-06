from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def prepare(*, backup: bool = True, force_backfill: bool = False) -> dict[str, Any]:
    """Run the one-time deployment preparation sequence in a deterministic order."""
    from jarvis_mrb.world_migrations import run_migrations

    result: dict[str, Any] = {
        "ok": True,
        "migrations": {},
        "backfill": {},
        "extended_backfill": {},
        "refresh": {},
        "diagnostics": {},
        "errors": [],
    }

    # Schema must be known before any historical data is replayed into it.
    result["migrations"] = run_migrations(backup=backup)

    from jarvis_mrb.world_backfill import backfill_existing_state
    from jarvis_mrb.world_extended_backfill import backfill_extended_state

    result["backfill"] = backfill_existing_state(force=force_backfill)
    result["extended_backfill"] = backfill_extended_state(force=force_backfill)
    if not bool(result["backfill"].get("ok", True)):
        result["ok"] = False
        result["errors"].extend(str(item) for item in result["backfill"].get("errors", []))
    if not bool(result["extended_backfill"].get("ok", True)):
        result["ok"] = False
        result["errors"].extend(str(item) for item in result["extended_backfill"].get("errors", []))

    # Derived indexes are rebuilt after source replay so the final state is coherent
    # before diagnostics. Each provider is isolated and reported individually.
    refresh_steps = (
        ("links", "jarvis_mrb.world_linker", "refresh_links"),
        ("terms", "jarvis_mrb.world_terms", "refresh"),
        ("document_versions", "jarvis_mrb.world_document_versions", "refresh"),
        ("intentions", "jarvis_mrb.world_executive", "refresh_intentions"),
        ("executive_loop", "jarvis_mrb.world_executive_loop", "refresh"),
    )
    for label, module_name, function_name in refresh_steps:
        try:
            module = __import__(module_name, fromlist=[function_name])
            function = getattr(module, function_name)
            result["refresh"][label] = function()
        except Exception as exc:
            result["ok"] = False
            message = f"{label}: {exc}"
            result["refresh"][label] = {"error": str(exc)[:1000]}
            result["errors"].append(message)

    try:
        from jarvis_mrb.world_diagnostics import validate
        result["diagnostics"] = validate()
        if not bool(result["diagnostics"].get("ok")):
            result["ok"] = False
            result["errors"].extend(str(item) for item in result["diagnostics"].get("problems", []))
    except Exception as exc:
        result["ok"] = False
        result["diagnostics"] = {"error": str(exc)[:1000]}
        result["errors"].append(f"diagnostics: {exc}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a Jarvis installation after pulling a world-model upgrade."
    )
    parser.add_argument("--no-backup", action="store_true", help="Skip the pre-upgrade world SQLite backup.")
    parser.add_argument(
        "--force-backfill",
        action="store_true",
        help="Replay historical source stores even if their one-time completion sentinels exist.",
    )
    args = parser.parse_args()
    result = prepare(backup=not args.no_backup, force_backfill=args.force_backfill)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, default=str))
    raise SystemExit(0 if bool(result.get("ok")) else 1)


if __name__ == "__main__":
    main()
