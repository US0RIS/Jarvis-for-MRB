from __future__ import annotations

import json
import sys
from typing import Any


def _truth(value: Any) -> bool:
    try:
        return bool(value)
    except Exception:
        return False


def main() -> None:
    captured: dict[str, Any] = {}

    def tracer(frame: Any, event: str, arg: Any):
        if frame.f_code.co_name == "run_synthetic_acceptance" and event == "return":
            local = frame.f_locals
            verification = local.get("verification_outcome")
            captured.update(
                {
                    "goal_events": _truth(local.get("goal_events")),
                    "goal_event_count": len(local.get("goal_events") or []),
                    "project_id": _truth(local.get("project_id")),
                    "project_id_value": str(local.get("project_id") or ""),
                    "intention_id": _truth(local.get("intention_id")),
                    "intention_id_value": str(local.get("intention_id") or ""),
                    "conflict_count_ge_1": int(local.get("conflict_count") or 0) >= 1,
                    "conflict_count": int(local.get("conflict_count") or 0),
                    "version_change_row": _truth(local.get("version_change_row")),
                    "prebrief": _truth(local.get("prebrief")),
                    "decision": _truth(local.get("decision")),
                    "verification_outcome": _truth(verification),
                    "verification_verified": bool(
                        isinstance(verification, dict)
                        and verification.get("status") == "verified"
                    ),
                    "term_context_has_15pct": "15%" in str(local.get("direct_term_context") or ""),
                    "full_chain": bool(local.get("full_chain")),
                }
            )
        return tracer

    old_trace = sys.gettrace()
    try:
        sys.settrace(tracer)
        from jarvis_mrb.world_acceptance import run_synthetic_acceptance

        result = run_synthetic_acceptance()
    finally:
        sys.settrace(old_trace)

    print(
        json.dumps(
            {
                "acceptance_ok": bool(result.get("ok")),
                "failed_checks": result.get("failed_checks") or [],
                "criterion_12_components": captured,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    raise SystemExit(0 if bool(result.get("ok")) else 1)


if __name__ == "__main__":
    main()
