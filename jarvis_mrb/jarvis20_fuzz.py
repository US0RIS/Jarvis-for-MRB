from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jarvis_mrb.jarvis20_variants import generate_variant_bundle
from jarvis_mrb.jarvis20_worldlab import run_world_variant


def run_world_fuzz(
    seed_prefix: str,
    *,
    count: int = 20,
    anchor: datetime | None = None,
) -> dict[str, Any]:
    """Run many independent procedural worlds and aggregate tests 5-10.

    This remains preflight infrastructure and never awards the live 0-60 score.
    Every failed seed is retained so the exact world can be regenerated later.
    """
    prefix = str(seed_prefix or "").strip()
    if not prefix:
        raise ValueError("seed_prefix must be non-empty")
    count = int(count)
    if count < 1 or count > 500:
        raise ValueError("count must be between 1 and 500")

    if anchor is None:
        anchor = datetime.now(timezone.utc).replace(microsecond=0)
    elif anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    else:
        anchor = anchor.astimezone(timezone.utc)

    rows: list[dict[str, Any]] = []
    per_test: dict[str, dict[str, int]] = {
        str(test_id): {"passed": 0, "failed": 0}
        for test_id in range(5, 11)
    }

    for index in range(1, count + 1):
        seed = f"{prefix}-{index:04d}"
        bundle = generate_variant_bundle(seed, anchor=anchor)
        result = run_world_variant(bundle.public, bundle.oracle)
        failed_tests: list[int] = []
        for test_id in range(5, 11):
            passed = bool((result.get("tests") or {}).get(str(test_id), {}).get("passed"))
            key = "passed" if passed else "failed"
            per_test[str(test_id)][key] += 1
            if not passed:
                failed_tests.append(test_id)
        rows.append({
            "seed": seed,
            "scenario_id": bundle.public.get("scenario_id"),
            "ok": bool(result.get("ok")),
            "failed_tests": failed_tests,
            "failed_checks": result.get("failed_checks") or [],
            "project": bundle.public["world_fixture"]["project"],
            "term_key": bundle.oracle["world"]["expected_term"]["term_key"],
        })

    passed_worlds = sum(1 for row in rows if row["ok"])
    failing = [row for row in rows if not row["ok"]]
    return {
        "ok": not failing,
        "mode": "procedural_world_fuzz",
        "seed_prefix": prefix,
        "anchor": anchor.isoformat(),
        "worlds": count,
        "passed_worlds": passed_worlds,
        "failed_worlds": count - passed_worlds,
        "pass_rate": round(passed_worlds / count, 6),
        "tests": per_test,
        "failures": failing,
        "runs": rows,
        "mutates_user_data": False,
        "uses_external_services": False,
        "awards_behavioral_score": False,
    }
