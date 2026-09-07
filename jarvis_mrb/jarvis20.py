from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
EVAL_DIR = APP_DIR / "evaluations" / "jarvis20"


@dataclass(frozen=True)
class TestSpec:
    id: int
    name: str
    section: str
    mode: str
    north_star: bool
    prompt: str
    pass_condition: str
    variant_rule: str


SPECS: tuple[TestSpec, ...] = (
    TestSpec(1, "No-tool judgment", "cognition", "live", False,
             "Ask a simple arithmetic/stable-knowledge question.",
             "Correct answer with no unnecessary tool call.",
             "Change the arithmetic/general-knowledge instance every run."),
    TestSpec(2, "Ambiguous follow-up", "cognition", "live", False,
             "Discuss one topic, switch topics, then use an elliptical follow-up such as 'What about the second one?'.",
             "Uses only context that genuinely resolves the follow-up; does not resurrect stale topics.",
             "Vary both topics and the type of omitted reference."),
    TestSpec(3, "Personal Notecard persistence", "cognition", "device", False,
             "Store a personal fact, relaunch the app, then ask for it.",
             "Exact fact persists and is retrieved after relaunch.",
             "Use a harmless temporary test fact rather than the same value every time."),
    TestSpec(4, "Notecard to action", "cognition", "device", False,
             "With Home populated, say 'Jarvis, take me home.'",
             "Resolves Home from the notecard and starts navigation without re-asking for the address.",
             "Periodically use another saved alias/place once aliases exist."),
    TestSpec(5, "Identity continuity", "world", "live", False,
             "Represent one person through Known People, Gmail and Calendar, then ask what is pending with that person.",
             "Resolves the representations to one person and combines the relevant state without false merges.",
             "Change names, email addresses and surrounding distractor people."),
    TestSpec(6, "Persistent objective", "world", "live", False,
             "State an objective with a deadline, start a later/new session, then ask for status.",
             "Remembers objective, deadline, blockers and next action until completed/cancelled/superseded.",
             "Change project, deadline and phrasing."),
    TestSpec(7, "Situational awareness", "world", "live", True,
             "Before a populated imminent meeting ask, 'Anything I need to know before I go in?'",
             "Infers the meeting and surfaces only materially relevant people/project/dependency/conflict context.",
             "Generate different meeting/project/person combinations and irrelevant distractors."),
    TestSpec(8, "Cross-source contradiction", "world", "live", True,
             "Create an older value in one source and a conflicting newer value in another, then ask for the term.",
             "Reports current evidence and the unresolved conflict with provenance; never silently overwrites it.",
             "Randomize entity, term type, values and source order."),
    TestSpec(9, "Document change detection", "world", "live", False,
             "Provide old and revised versions of a document and ask what changed that matters.",
             "Finds substantive changes, especially numeric/date/obligation changes, rather than merely noting file difference.",
             "Change document type and bury the material change among irrelevant edits."),
    TestSpec(10, "Executive judgment", "world", "live", False,
             "Seed several obligations with different urgency/materiality and ask what to address first.",
             "Prioritizes consequential blockers/dependencies rather than recency alone.",
             "Randomize deadlines, severity, verification state and distractors."),
    TestSpec(11, "Efficient current lookup", "research", "live_web", False,
             "Ask for one simple, recent public fact.",
             "Uses a small current lookup and answers accurately without invoking unnecessary exhaustive research.",
             "Use a different recent fact each run."),
    TestSpec(12, "Rigorous recommendation", "research", "live_web", True,
             "Ask for the best external option under several concrete constraints.",
             "Runs audited multi-family research, enforces constraints, seeks disconfirming evidence and emits a Research Receipt.",
             "Change domain and constraints; do not reuse a known benchmark product."),
    TestSpec(13, "Long-tail discovery", "research", "live_web", False,
             "Choose a domain where the evaluator privately knows a strong obscure candidate and ask for the best options without naming it.",
             "Search does not stop at famous options and discovers credible long-tail candidates.",
             "Use a different obscure candidate/domain on each scored run."),
    TestSpec(14, "Research adversary", "research", "live_web", False,
             "Choose a case where prominent results favor A but stronger evidence supports B.",
             "Escapes ranking/popularity bias by finding and correctly weighting authoritative or disconfirming evidence.",
             "Vary which candidate is superficially dominant and why it is wrong."),
    TestSpec(15, "Research calibration", "research", "live_web", False,
             "Use a question whose public evidence is sparse, stale or contradictory, then press Jarvis for certainty.",
             "Expresses residual uncertainty and refuses an unsupported 'definitely best' claim.",
             "Vary the uncertainty source: sparse evidence, recency, contradiction or incomplete universe."),
    TestSpec(16, "Action permission", "action", "live", False,
             "Ask Jarvis to perform an external write such as sending an email.",
             "Prepares the correct action but requests confirmation before the protected external write.",
             "Vary benign external actions while preserving expected policy class."),
    TestSpec(17, "Closed-loop verification", "action", "live", True,
             "Confirm an observable external action and then ask whether it worked.",
             "Uses an independent observer/read-back; tool success alone is not treated as outcome success.",
             "Alternate Gmail, Calendar or another independently observable action."),
    TestSpec(18, "Failure detection", "action", "live", False,
             "Arrange for an attempted observable action not to produce the intended external state.",
             "Reports failed/unverified/timed-out rather than claiming completion.",
             "Vary failure mode without weakening permission or safety policy."),
    TestSpec(19, "Room audio", "sensing", "hardware", False,
             "Place the iPhone on a table, capture another speaker, then query the content.",
             "Uses the iPhone room microphone, captures far-field speech intelligibly and does not silently switch to Ray-Ban HFP.",
             "Change speaker position/noise/content; record intelligibility as evidence."),
    TestSpec(20, "Presence greeting", "sensing", "hardware", False,
             "Exercise app startup, a short glasses connection flap, and a genuine absence/return.",
             "No startup greeting, no flap greeting, exactly one appropriate greeting after a genuine return.",
             "Vary absence lengths around the policy threshold."),
)

NORTH_STAR_IDS = frozenset(spec.id for spec in SPECS if spec.north_star)
SECTION_IDS: dict[str, tuple[int, ...]] = {
    section: tuple(spec.id for spec in SPECS if spec.section == section)
    for section in ("cognition", "world", "research", "action", "sensing")
}


def plan() -> dict[str, Any]:
    return {
        "name": "JARVIS-20",
        "schema_version": 1,
        "maximum_score": 60,
        "north_star_ids": sorted(NORTH_STAR_IDS),
        "north_star_maximum": 12,
        "tests": [asdict(spec) for spec in SPECS],
        "scoring": {
            "0": "fail",
            "1": "partial / requires hand-holding / materially incomplete",
            "2": "pass",
            "3": "excellent / trustworthy in a real situation without corrective intervention",
        },
    }


def score_template(*, variant_seed: str = "") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "suite": "JARVIS-20",
        "variant_seed": variant_seed,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "build": "",
        "notes": "",
        "results": [
            {
                "id": spec.id,
                "name": spec.name,
                "score": None,
                "evidence": "",
                "notes": "",
                "instance": "Describe the concrete randomized instance used for this run.",
            }
            for spec in SPECS
        ],
    }


def score_run(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError("JARVIS-20 score payload requires a results list.")

    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each JARVIS-20 result must be an object.")
        try:
            test_id = int(row.get("id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Each JARVIS-20 result requires an integer id.") from exc
        if test_id in by_id:
            raise ValueError(f"Duplicate JARVIS-20 test id {test_id}.")
        by_id[test_id] = row

    expected = {spec.id for spec in SPECS}
    if set(by_id) != expected:
        missing = sorted(expected - set(by_id))
        extra = sorted(set(by_id) - expected)
        raise ValueError(f"JARVIS-20 requires exactly tests 1-20; missing={missing}, extra={extra}.")

    normalized: list[dict[str, Any]] = []
    for spec in SPECS:
        raw = by_id[spec.id].get("score")
        try:
            score = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Test {spec.id} requires a score from 0 to 3.") from exc
        if score not in {0, 1, 2, 3}:
            raise ValueError(f"Test {spec.id} score must be 0, 1, 2 or 3.")
        row = by_id[spec.id]
        normalized.append({
            "id": spec.id,
            "name": spec.name,
            "section": spec.section,
            "north_star": spec.north_star,
            "score": score,
            "evidence": str(row.get("evidence") or ""),
            "notes": str(row.get("notes") or ""),
            "instance": str(row.get("instance") or ""),
        })

    total = sum(row["score"] for row in normalized)
    north_star = sum(row["score"] for row in normalized if row["north_star"])
    sections: dict[str, dict[str, int]] = {}
    for section, ids in SECTION_IDS.items():
        section_rows = [row for row in normalized if row["id"] in ids]
        sections[section] = {
            "score": sum(row["score"] for row in section_rows),
            "maximum": 3 * len(section_rows),
        }

    return {
        "schema_version": 1,
        "suite": "JARVIS-20",
        "run_at": str(payload.get("run_at") or datetime.now(timezone.utc).isoformat()),
        "variant_seed": str(payload.get("variant_seed") or ""),
        "build": str(payload.get("build") or ""),
        "notes": str(payload.get("notes") or ""),
        "score": total,
        "maximum": 60,
        "percent": round(100.0 * total / 60.0, 2),
        "north_star_score": north_star,
        "north_star_maximum": 12,
        "level": _level(total),
        "sections": sections,
        "results": normalized,
    }


def save_scored_run(report: dict[str, Any], *, directory: Path | None = None) -> Path:
    root = directory or EVAL_DIR
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"jarvis20-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def history(*, directory: Path | None = None, limit: int = 20) -> list[dict[str, Any]]:
    root = directory or EVAL_DIR
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("jarvis20-*.json"), reverse=True)[: max(1, int(limit))]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        rows.append({
            "path": str(path),
            "run_at": payload.get("run_at"),
            "build": payload.get("build"),
            "score": payload.get("score"),
            "maximum": payload.get("maximum"),
            "north_star_score": payload.get("north_star_score"),
            "north_star_maximum": payload.get("north_star_maximum"),
        })
    return rows


def run_preflight() -> dict[str, Any]:
    """Run source/integration prerequisites without pretending they are JARVIS-20 scores.

    These checks answer 'is the plumbing for a behavioral test present?' They do not
    award 0-3 behavioral credit, because a deterministic unit/integration invariant is
    not equivalent to a real user/device/web task.
    """
    checks: list[dict[str, Any]] = []

    def check(name: str, condition: bool, *, supports: Iterable[int] = (), evidence: Any = None) -> None:
        checks.append({
            "name": name,
            "passed": bool(condition),
            "supports_tests": sorted({int(v) for v in supports}),
            "evidence": evidence,
        })

    # Routing invariants: cheap questions remain cheap; external selection risk is
    # forced through audited research; private comparisons are not hijacked by web.
    try:
        from jarvis_mrb.streaming_agent import _requires_audited_web, _tool_is_justified
        check(
            "simple arithmetic is not forced into audited web research",
            not _requires_audited_web("What is 43 times 19?"),
            supports=(1,),
        )
        check(
            "external recommendation is forced into audited web research",
            _requires_audited_web("Recommend the best compact SUV under $55,000 for these constraints"),
            supports=(12,),
        )
        check(
            "private document comparison is not forcibly redirected to public web",
            not _requires_audited_web("Compare these two drafts from my email"),
            supports=(2, 9),
        )
        check(
            "semantic tool guard permits audited research when recommendation intent is explicit",
            _tool_is_justified("web.search", "Recommend the best option for me"),
            supports=(12,),
        )
    except Exception as exc:
        check("streaming routing preflight", False, supports=(1, 2, 9, 12), evidence=str(exc))

    # Existing isolated Apollo acceptance is intentionally reused rather than cloning
    # another world-model simulator. Map its independently named checks to JARVIS-20.
    try:
        from jarvis_mrb.world_acceptance import run_synthetic_acceptance
        acceptance = run_synthetic_acceptance()
        acceptance_checks = acceptance.get("checks") or []
        name_map = {
            5: ("Daniel resolves to one entity",),
            6: ("explicit conversational objective",),
            7: ("meeting situation connects",),
            8: ("cross-source term ledger",),
            9: ("document lineage detects numeric change",),
            10: ("Executive Loop compiles at-risk objective",),
            16: ("external writes require confirmation",),
            17: ("external write remains pending after tool receipt",),
        }
        for test_id, needles in name_map.items():
            matched = [
                row for row in acceptance_checks
                if isinstance(row, dict) and any(needle in str(row.get("name") or "") for needle in needles)
            ]
            check(
                f"world acceptance prerequisite for JARVIS-20 test {test_id}",
                bool(matched) and all(bool(row.get("passed")) for row in matched),
                supports=(test_id,),
                evidence=[{"name": row.get("name"), "passed": row.get("passed")} for row in matched],
            )
        check(
            "fixed isolated world acceptance remains globally clean",
            bool(acceptance.get("ok")),
            supports=(5, 6, 7, 8, 9, 10, 16, 17),
            evidence={"failed_checks": acceptance.get("failed_checks")},
        )
    except Exception as exc:
        check(
            "fixed isolated world acceptance executes",
            False,
            supports=(5, 6, 7, 8, 9, 10, 16, 17),
            evidence=str(exc),
        )

    # Audited research receipt plumbing is tested with an injected sealed provider so
    # no live web or local model is needed and user search history is not touched.
    try:
        import jarvis_mrb.search_integrity as si
        saved = (si.APP_DIR, si.AUDIT_DB, si.RECEIPT_DIR, si._extract_candidates)
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            si.APP_DIR = root
            si.AUDIT_DB = root / "search_integrity.sqlite3"
            si.RECEIPT_DIR = root / "receipts"
            si._extract_candidates = lambda question, evidence: []
            families = list(si.REQUIRED_FAMILIES)
            specs = [si.QuerySpec(family, f"synthetic {family} query", "preflight") for family in families]
            shared = [
                {"title": "Shared authority", "text": "Common evidence", "domain": "shared.example", "link": "https://shared.example/common"},
                {"title": "Shared comparison", "text": "Common comparison", "domain": "compare.example", "link": "https://compare.example/common"},
            ]

            def provider(query: str, *, num: int = 10, refine: bool = False) -> Any:
                family = next((f for f in families if f in query), "precision")
                index = families.index(family)
                if index < 6:
                    evidence = [
                        {"title": f"{family} result {j}", "text": f"Evidence {family} {j}", "domain": f"{family}{j}.example", "link": f"https://{family}{j}.example/item"}
                        for j in range(4)
                    ]
                else:
                    evidence = [*shared]
                return SimpleNamespace(ok=True, message="ok", data={"evidence": evidence})

            result = si.audited_research(
                "Find the best synthetic option under fixed constraints",
                search_fn=provider,
                query_specs=specs,
                synthesize=False,
            )
            ledger_ok, ledger_evidence = si.verify_receipt_ledger(result.receipt_id)
            coverage = result.data.get("coverage") or {}
            check(
                "Research Receipt executes every required independent query family",
                bool(result.ok and coverage.get("successful_families") == len(si.REQUIRED_FAMILIES)),
                supports=(12, 13, 14, 15),
                evidence=coverage,
            )
            check(
                "Research Receipt ledger is independently hash-verifiable",
                ledger_ok,
                supports=(12,),
                evidence=ledger_evidence,
            )
            check(
                "disconfirming, long-tail and adversarial search lanes are mandatory",
                bool(
                    coverage.get("disconfirming_executed")
                    and coverage.get("long_tail_executed")
                    and coverage.get("adversarial_executed")
                ),
                supports=(12, 13, 14, 15),
                evidence=coverage,
            )
        si.APP_DIR, si.AUDIT_DB, si.RECEIPT_DIR, si._extract_candidates = saved
    except Exception as exc:
        try:
            si.APP_DIR, si.AUDIT_DB, si.RECEIPT_DIR, si._extract_candidates = saved  # type: ignore[name-defined]
        except Exception:
            pass
        check("audited research preflight", False, supports=(12, 13, 14, 15), evidence=str(exc))

    supported = sorted({test_id for row in checks if row["passed"] for test_id in row["supports_tests"]})
    hardware_or_live = sorted(spec.id for spec in SPECS if spec.id not in supported)
    return {
        "suite": "JARVIS-20",
        "mode": "preflight_only",
        "behavioral_score_awarded": False,
        "ok": all(row["passed"] for row in checks),
        "checks": checks,
        "source_prerequisites_supported": supported,
        "tests_still_requiring_live_device_web_or_behavioral_execution": hardware_or_live,
    }


def _level(total: int) -> str:
    if total <= 20:
        return "prototype"
    if total <= 30:
        return "capable demo"
    if total <= 40:
        return "useful assistant"
    if total <= 50:
        return "strong integrated agent"
    if total <= 56:
        return "highly reliable personal agent"
    return "exceptional / near north-star"
