from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from jarvis_mrb.cloud_cognition import route_cognition


@dataclass(frozen=True)
class BenchmarkCase:
    category: str
    prompt: str
    expected_tier: str
    force: str = "auto"
    deterministic_available: bool = False
    prior_local_failures: int = 0
    malformed_local_result: bool = False


CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase("deterministic", "Open Safari", "deterministic", deterministic_available=True),
    BenchmarkCase("ordinary conversation", "Tell me a short joke.", "local"),
    BenchmarkCase("simple reasoning", "Why does ice float?", "local"),
    BenchmarkCase(
        "difficult reasoning",
        "Prove this combinatorics identity, derive a second proof, and compare the tradeoffs.",
        "cloud",
    ),
    BenchmarkCase(
        "coding/debugging",
        "Debug this subtle race condition, identify the root cause, and design a robust architecture fix.",
        "cloud",
    ),
    BenchmarkCase(
        "ambiguous situation",
        "Synthesize the conflicting evidence; the situation is ambiguous and uncertain.",
        "cloud",
    ),
    BenchmarkCase(
        "Reality Graph synthesis",
        "Synthesize this Reality Graph across multiple constraints and conflicting evidence.",
        "cloud",
    ),
    BenchmarkCase(
        "World Armor",
        "Use World Armor evidence to investigate a causal chain and compare counterfactual explanations.",
        "cloud",
    ),
    BenchmarkCase(
        "investigation",
        "Investigate the root cause across contradictory evidence and produce a multi-step plan.",
        "cloud",
    ),
    BenchmarkCase(
        "privacy-sensitive",
        "Summarize my private notes without sending local-only context to any cloud.",
        "local",
        force="local",
    ),
    BenchmarkCase(
        "consequential",
        "Investigate this security incident with conflicting evidence and build a multi-step recovery plan.",
        "cloud",
    ),
    BenchmarkCase(
        "emergency-authoritative",
        "What is the official procedure for a gas leak?",
        "local",
    ),
    BenchmarkCase(
        "local failure",
        "Continue the analysis after repeated planner failures.",
        "cloud",
        prior_local_failures=2,
    ),
    BenchmarkCase(
        "malformed local",
        "Continue the analysis.",
        "cloud",
        malformed_local_result=True,
    ),
)


def evaluate(cases: Iterable[BenchmarkCase] = CASES) -> dict:
    rows = []
    matched = 0
    for case in cases:
        decision = route_cognition(
            case.prompt,
            force=case.force,
            deterministic_available=case.deterministic_available,
            prior_local_failures=case.prior_local_failures,
            malformed_local_result=case.malformed_local_result,
        )
        ok = decision.tier == case.expected_tier
        matched += int(ok)
        rows.append({
            "category": case.category,
            "expected": case.expected_tier,
            "actual": decision.tier,
            "reason": decision.reason,
            "reasoning_effort": decision.reasoning_effort,
            "matched": ok,
        })
    total = len(rows)
    return {
        "matched": matched,
        "total": total,
        "accuracy": matched / total if total else 1.0,
        "rows": rows,
    }


def main() -> int:
    result = evaluate()
    for row in result["rows"]:
        marker = "PASS" if row["matched"] else "FAIL"
        print(
            f'{marker:4} {row["category"]:24} '
            f'expected={row["expected"]:13} actual={row["actual"]:13} '
            f'effort={row["reasoning_effort"]:6} {row["reason"]}'
        )
    print(f'Routing benchmark: {result["matched"]}/{result["total"]} matched')
    return 0 if result["matched"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
