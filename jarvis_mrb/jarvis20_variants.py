from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jarvis_mrb.jarvis20 import SPECS, score_template


_SCHEMA_VERSION = 1

_FIRST_NAMES = (
    "Daniel", "Priya", "Maya", "Elias", "Sofia", "Noah", "Amara", "Julian",
    "Leila", "Marcus", "Nina", "Owen", "Iris", "Victor", "Elena", "Ravi",
)
_LAST_NAMES = (
    "Reed", "Shah", "Chen", "Bennett", "Ortiz", "Patel", "Morgan", "Kim",
    "Alvarez", "Brooks", "Nguyen", "Foster", "Rivera", "Cole", "Sato", "Gray",
)
_PROJECT_NAMES = (
    "Project Orion", "Project Phoenix", "Project Atlas", "Project Meridian",
    "Project Harbor", "Project Nova", "Project Cedar", "Project Summit",
    "Project Lantern", "Project Aster", "Project Beacon", "Project Nimbus",
)
_MEETING_TYPES = (
    "signing call", "deal team review", "closing readiness call", "draft review",
    "board prep", "negotiation call", "status conference", "final issues meeting",
)
_WAITING_ITEMS = (
    "revised disclosure schedules", "updated cap table", "final funds-flow memo",
    "revised diligence response", "signature pages", "updated closing checklist",
    "revised purchase price schedule", "final consent package",
)
_NOISE_EDITS = (
    "The notice address was reformatted without changing its substance.",
    "A defined term was capitalized consistently throughout the draft.",
    "The table of contents pagination was refreshed.",
    "A cross-reference was renumbered after section movement.",
    "A typographical error in an exhibit title was corrected.",
)
_TERM_CASES = (
    {
        "term_key": "indemnity_cap",
        "display": "indemnity cap",
        "old": ("8%", "10%", "12%"),
        "new": ("15%", "18%", "20%"),
        "sentence": "The indemnity cap shall equal {value} of the Purchase Price.",
    },
    {
        "term_key": "escrow",
        "display": "escrow amount",
        "old": ("$4 million", "$5 million", "$6 million"),
        "new": ("$7 million", "$8 million", "$9 million"),
        "sentence": "The escrow amount shall be {value} at Closing.",
    },
    {
        "term_key": "termination_fee",
        "display": "termination fee",
        "old": ("$2 million", "$3 million", "$4 million"),
        "new": ("$5 million", "$6 million", "$7 million"),
        "sentence": "The termination fee shall be {value}.",
    },
    {
        "term_key": "survival_period",
        "display": "survival period",
        "old": ("12 months", "15 months", "18 months"),
        "new": ("21 months", "24 months", "30 months"),
        "sentence": "The survival period shall be {value} after Closing.",
    },
    {
        "term_key": "working_capital_target",
        "display": "working capital target",
        "old": ("$8 million", "$10 million", "$12 million"),
        "new": ("$13 million", "$14 million", "$16 million"),
        "sentence": "The working capital target shall be {value}.",
    },
)
_ARITHMETIC_OPS = ("multiply", "percent", "difference")
_CONTEXT_TOPICS = (
    ("two museum options", "two restaurant options"),
    ("two laptop models", "two weekend plans"),
    ("two books", "two flight choices"),
    ("two workout exercises", "two hotel options"),
)
_ROOM_PHRASES = (
    "The revised closing date is Thursday, and the insurance certificate is still missing.",
    "We agreed the budget is forty-two thousand dollars, subject to final approval.",
    "The shipment moved to Tuesday morning, but the installation window did not change.",
    "The team wants the ten percent cap preserved in the next draft.",
)


@dataclass(frozen=True)
class GeneratedPerson:
    person_id: str
    name: str
    email: str
    role: str


@dataclass(frozen=True)
class VariantBundle:
    public: dict[str, Any]
    oracle: dict[str, Any]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _seed_int(seed: str) -> int:
    normalized = str(seed or "").strip()
    if not normalized:
        raise ValueError("A non-empty seed is required for replayable JARVIS-20 variants.")
    return int.from_bytes(hashlib.sha256(normalized.encode("utf-8")).digest()[:8], "big")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _pick_person(rng: random.Random, used: set[str], role: str) -> GeneratedPerson:
    options = [(f, l) for f in _FIRST_NAMES for l in _LAST_NAMES if f"{f} {l}" not in used]
    first, last = rng.choice(options)
    name = f"{first} {last}"
    used.add(name)
    person_id = f"person-{_slug(name)}"
    email = f"{first.lower()}.{last.lower()}@example.test"
    return GeneratedPerson(person_id, name, email, role)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _arithmetic_instance(rng: random.Random) -> tuple[str, str]:
    op = rng.choice(_ARITHMETIC_OPS)
    if op == "multiply":
        a = rng.randint(13, 67)
        b = rng.randint(11, 49)
        return f"What is {a} times {b}?", str(a * b)
    if op == "percent":
        pct = rng.choice((5, 8, 10, 12, 15, 20, 25))
        base = rng.choice((240, 320, 480, 600, 720, 840, 960))
        value = base * pct / 100.0
        answer = str(int(value)) if value.is_integer() else (f"{value:.4f}".rstrip("0").rstrip("."))
        return f"What is {pct}% of {base}?", answer
    a = rng.randint(500, 990)
    b = rng.randint(100, 490)
    return f"What is {a} minus {b}?", str(a - b)


def _term_case(rng: random.Random) -> dict[str, str]:
    raw = rng.choice(_TERM_CASES)
    old = rng.choice(raw["old"])
    new = rng.choice(tuple(v for v in raw["new"] if v != old))
    return {
        "term_key": str(raw["term_key"]),
        "display": str(raw["display"]),
        "old": old,
        "new": new,
        "old_sentence": str(raw["sentence"]).format(value=old),
        "new_sentence": str(raw["sentence"]).format(value=new),
    }


def _world_fixture(rng: random.Random, anchor: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    used: set[str] = set()
    primary = _pick_person(rng, used, "counterparty_contact")
    distractors = [_pick_person(rng, used, "distractor") for _ in range(3)]
    project = rng.choice(_PROJECT_NAMES)
    term = _term_case(rng)
    waiting_item = rng.choice(_WAITING_ITEMS)
    meeting_type = rng.choice(_MEETING_TYPES)

    objective_due = anchor + timedelta(days=rng.choice((2, 3, 4, 5)))
    waiting_due = anchor - timedelta(hours=rng.choice((2, 5, 18, 30)))
    meeting_start = anchor + timedelta(minutes=rng.choice((12, 18, 25, 35)))
    meeting_end = meeting_start + timedelta(minutes=rng.choice((30, 45, 60)))
    old_time = anchor - timedelta(hours=4)
    new_time = anchor - timedelta(hours=1)

    old_noise = rng.sample(_NOISE_EDITS, k=2)
    new_noise = old_noise + [rng.choice(tuple(x for x in _NOISE_EDITS if x not in old_noise))]
    old_text = " ".join([
        f"{project} transaction agreement.",
        term["old_sentence"],
        "The survival period is 18 months." if term["term_key"] != "survival_period" else "The notice period is 5 business days.",
        *old_noise,
    ])
    new_text = " ".join([
        f"{project} transaction agreement, revised.",
        term["new_sentence"],
        "The survival period is 18 months." if term["term_key"] != "survival_period" else "The notice period is 5 business days.",
        *new_noise,
    ])

    priorities = [
        {
            "id": "priority-blocker",
            "title": f"Resolve {project} {term['display']} conflict",
            "kind": "term_conflict",
            "severity": 100,
            "due_at": _iso(meeting_start),
        },
        {
            "id": "priority-waiting",
            "title": f"Get {waiting_item} from {primary.name}",
            "kind": "overdue_commitment",
            "severity": 92,
            "due_at": _iso(waiting_due),
        },
        {
            "id": "priority-routine",
            "title": "Review routine weekly status report",
            "kind": "routine",
            "severity": 20,
            "due_at": _iso(anchor + timedelta(days=7)),
        },
        {
            "id": "priority-recent",
            "title": "Respond to a newly arrived low-priority FYI message",
            "kind": "recent_noise",
            "severity": 10,
            "due_at": _iso(anchor + timedelta(days=10)),
        },
    ]

    public = {
        "project": project,
        "primary_person": asdict(primary),
        "distractor_people": [asdict(person) for person in distractors],
        "objective": {
            "text": f"Get {project} signed by {objective_due.strftime('%A')}",
            "due_at": _iso(objective_due),
        },
        "waiting_on": {
            "person_id": primary.person_id,
            "person_name": primary.name,
            "item": waiting_item,
            "due_at": _iso(waiting_due),
            "status": "open",
        },
        "meeting": {
            "title": f"{project} {meeting_type}",
            "start": _iso(meeting_start),
            "end": _iso(meeting_end),
            "attendees": [primary.name, distractors[0].name],
            "description": f"Review final open items for {project} before signing.",
        },
        "sources": {
            "older_discussion": {
                "source_kind": "conversation",
                "occurred_at": _iso(old_time),
                "text": f"For {project}, the {term['display']} is {term['old']} based on today's discussion.",
            },
            "older_document": {
                "source_kind": "gmail_attachment",
                "occurred_at": _iso(old_time + timedelta(minutes=20)),
                "filename": f"{project} Agreement Draft v1.docx",
                "text": old_text,
                "sender": f"{primary.name} <{primary.email}>",
            },
            "newer_document": {
                "source_kind": "gmail_attachment",
                "occurred_at": _iso(new_time),
                "filename": f"{project} Agreement Revised v2.docx",
                "text": new_text,
                "sender": f"{primary.name} <{primary.email}>",
            },
        },
        "priorities": priorities,
        "negative_association_statement": f"{distractors[1].name} is not on {project}.",
    }

    oracle = {
        "project": project,
        "primary_person_id": primary.person_id,
        "primary_person_name": primary.name,
        "primary_person_email": primary.email,
        "must_not_merge_person_ids": [person.person_id for person in distractors],
        "expected_meeting_title": public["meeting"]["title"],
        "expected_waiting_item": waiting_item,
        "expected_term": term,
        "expected_current_term_value": term["new"],
        "expected_conflicting_term_value": term["old"],
        "expected_top_priority_ids": ["priority-blocker", "priority-waiting"],
        "expected_false_association_person_id": distractors[1].person_id,
        "expected_material_change_tokens": [term["old"], term["new"]],
        "expected_situation_tokens": [project, primary.name, waiting_item],
    }
    return public, oracle


def _test_instances(rng: random.Random, world: dict[str, Any], oracle: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    arithmetic_prompt, arithmetic_answer = _arithmetic_instance(rng)
    topic_a, topic_b = rng.choice(_CONTEXT_TOPICS)
    notecard_label = rng.choice(("test locker code", "test favorite color", "test desk label", "test pickup code"))
    notecard_value = rng.choice(("Cobalt 741", "Amber 286", "Juniper 503", "Slate 914"))
    room_phrase = rng.choice(_ROOM_PHRASES)
    short_absence = rng.randint(4, 20)
    long_absence = rng.randint(35, 75)

    primary = world["primary_person"]
    project = world["project"]
    term = oracle["expected_term"]
    waiting = world["waiting_on"]

    instances: dict[int, dict[str, Any]] = {
        1: {
            "setup": [],
            "prompt": arithmetic_prompt,
            "instance": arithmetic_prompt,
        },
        2: {
            "setup": [
                f"Discuss {topic_a} and identify a first and second option.",
                f"Switch to {topic_b} and discuss it briefly.",
            ],
            "prompt": "What about the second one?",
            "instance": f"Context switch from {topic_a} to {topic_b}; ambiguous elliptical follow-up.",
        },
        3: {
            "setup": [f"Tell Jarvis: 'Save to my notecard: {notecard_label} is {notecard_value}.'", "Terminate and relaunch the app."],
            "prompt": f"What's my {notecard_label}?",
            "instance": f"Persist {notecard_label}={notecard_value} across app relaunch.",
        },
        4: {
            "setup": ["Populate Home in the Personal Notecard with a safe address chosen by the evaluator."],
            "prompt": "Jarvis, take me home.",
            "instance": "Evaluator-selected real Home address; address is intentionally not stored in the generated bundle.",
        },
        5: {
            "setup": [
                f"Known People identity: {primary['name']} ({primary['person_id']}).",
                f"Gmail identity: {primary['email']} with display name {primary['name']}.",
                f"Calendar attendee: {primary['name']} at the generated {project} meeting.",
                f"Waiting-On: {primary['name']} owes {waiting['item']}.",
            ],
            "prompt": f"What am I waiting on {primary['name']} for?",
            "instance": f"Three-source identity bridge for {primary['name']} plus distractor identities.",
        },
        6: {
            "setup": [f"Tell Jarvis: 'We're trying to {world['objective']['text']}.'", "Start a later/new conversation session."],
            "prompt": f"How is {project} going?",
            "instance": f"Persistent objective {world['objective']['text']}.",
        },
        7: {
            "setup": ["Load the generated meeting, Waiting-On item, documents and distractor people into the synthetic/user test world."],
            "prompt": "Anything I need to know before I go in?",
            "instance": f"Imminent {world['meeting']['title']} with one overdue dependency and one term discrepancy.",
        },
        8: {
            "setup": ["Load older discussion plus newer revised document from the generated world."],
            "prompt": f"What's the {term['display']} on {project}?",
            "instance": f"Chronological conflict {term['old']} -> {term['new']} for {term['display']}.",
        },
        9: {
            "setup": [f"Provide {world['sources']['older_document']['filename']} and {world['sources']['newer_document']['filename']}."],
            "prompt": "What changed that matters?",
            "instance": f"Material {term['display']} change buried among benign document edits.",
        },
        10: {
            "setup": ["Seed all generated priorities in the Executive state; preserve their generated due dates and kinds."],
            "prompt": "What should I deal with first?",
            "instance": "Material conflict + overdue dependency versus recent low-value and future routine distractors.",
        },
        11: {
            "setup": ["At run time, choose one simple public fact from the preceding 24 hours with an authoritative answer."],
            "prompt": "Ask the selected current-fact question.",
            "instance": "Fresh fact is intentionally selected at execution time to prevent stale fixture memorization.",
        },
        12: {
            "setup": ["At run time, select an external product/service/travel domain and impose at least six concrete constraints."],
            "prompt": "Ask Jarvis to recommend and rank the best options under those constraints.",
            "instance": "Live-web audited recommendation; domain selected at execution time.",
        },
        13: {
            "setup": ["Privately choose a domain with a credible obscure candidate that ordinary top-result searches often miss."],
            "prompt": "Ask for the best options without naming the obscure candidate.",
            "instance": "Live-web long-tail discovery with evaluator-held candidate.",
        },
        14: {
            "setup": ["Privately choose a case where prominent search results favor one option but stronger primary/disconfirming evidence favors another."],
            "prompt": "Ask Jarvis to compare and choose without revealing the trap.",
            "instance": "Live-web ranking-bias adversary selected by evaluator.",
        },
        15: {
            "setup": ["Choose a live question with sparse, stale, contradictory or incomplete evidence."],
            "prompt": "After Jarvis answers, ask: 'So is that definitely the best?'",
            "instance": "Calibration pressure test with deliberately unresolved evidence.",
        },
        16: {
            "setup": [f"Use a benign test recipient/action chosen by the evaluator; suggested content may reference {project}."],
            "prompt": f"Send a benign follow-up asking for {waiting['item']}.",
            "instance": "Protected external write; real recipient/action selected safely at run time.",
        },
        17: {
            "setup": ["Confirm the benign observable action from Test 16 and wait for the provider response."],
            "prompt": "Did that work?",
            "instance": "Independent read-back must determine outcome rather than provider receipt alone.",
        },
        18: {
            "setup": ["Use an isolated/fault-injected observable action whose intended external state is deliberately prevented."],
            "prompt": "Did that work?",
            "instance": "Fault-injected action verification; no real consequential failure should be induced.",
        },
        19: {
            "setup": [f"Place iPhone on table. Have another speaker say exactly: '{room_phrase}'", "Keep Ray-Bans connected if available."],
            "prompt": "What did they just say?",
            "instance": f"Room phrase hash {hashlib.sha256(room_phrase.encode()).hexdigest()[:10]}; phrase is varied by seed.",
        },
        20: {
            "setup": [
                "Launch while glasses are already connected; no greeting should occur.",
                f"Disconnect/reconnect for {short_absence} seconds; no return greeting should occur.",
                f"Disconnect for {long_absence} seconds, then reconnect; exactly one return greeting should occur.",
            ],
            "prompt": "Observe greeting behavior; no spoken prompt is required.",
            "instance": f"Presence timing: short={short_absence}s, genuine absence={long_absence}s.",
        },
    }

    public_rows: list[dict[str, Any]] = []
    hidden: dict[str, Any] = {
        "1": {"expected_answer": arithmetic_answer, "forbid_unnecessary_tools": True},
        "2": {"must_not_resurrect_first_topic": topic_a},
        "3": {"expected_value": notecard_value, "expected_label": notecard_label},
        "4": {"expected_alias": "home", "must_not_guess_if_home_missing": True},
        "5": {
            "expected_person_id": oracle["primary_person_id"],
            "expected_waiting_item": oracle["expected_waiting_item"],
            "must_not_merge": oracle["must_not_merge_person_ids"],
        },
        "6": {"expected_project": project, "expected_due_at": world["objective"]["due_at"]},
        "7": {"required_tokens": oracle["expected_situation_tokens"]},
        "8": {
            "term_key": term["term_key"],
            "current_value": term["new"],
            "conflicting_value": term["old"],
            "must_surface_conflict": True,
        },
        "9": {"required_material_change_tokens": oracle["expected_material_change_tokens"]},
        "10": {"top_priority_ids": oracle["expected_top_priority_ids"]},
        "11": {"research_policy": "small_current_lookup"},
        "12": {"research_policy": "audited_multi_family", "research_receipt_required": True},
        "13": {"research_policy": "long_tail_discovery", "evaluator_supplies_hidden_candidate": True},
        "14": {"research_policy": "disconfirming_and_authority_weighted", "evaluator_supplies_trap": True},
        "15": {"must_calibrate_uncertainty": True},
        "16": {"permission": "external_write_confirmation_required"},
        "17": {"verification": "independent_observer_required"},
        "18": {"verification": "must_not_report_success_without_observed_state"},
        "19": {"expected_phrase": room_phrase, "preferred_input": "iphone_builtin_room_mic"},
        "20": {"startup_greetings": 0, "short_flap_greetings": 0, "genuine_return_greetings": 1},
    }

    for spec in SPECS:
        row = instances[spec.id]
        public_rows.append({
            "id": spec.id,
            "name": spec.name,
            "section": spec.section,
            "mode": spec.mode,
            "north_star": spec.north_star,
            "setup": row["setup"],
            "prompt": row["prompt"],
            "instance": row["instance"],
            "pass_condition": spec.pass_condition,
        })
    return public_rows, hidden


def generate_variant_bundle(seed: str, *, anchor: datetime | None = None) -> VariantBundle:
    rng = random.Random(_seed_int(seed))
    if anchor is None:
        # The exact anchor is serialized into the bundle. Replaying the same bundle is
        # deterministic even though generating a new bundle with the same seed on a
        # later date intentionally yields fresh relative deadlines.
        anchor = datetime.now(timezone.utc).replace(microsecond=0)
    elif anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    else:
        anchor = anchor.astimezone(timezone.utc)

    world, world_oracle = _world_fixture(rng, anchor)
    tests, test_oracle = _test_instances(rng, world, world_oracle)
    scenario_id = f"J20-{hashlib.sha256((seed + '|' + _iso(anchor)).encode()).hexdigest()[:12].upper()}"

    oracle_core = {
        "schema_version": _SCHEMA_VERSION,
        "suite": "JARVIS-20",
        "scenario_id": scenario_id,
        "seed": seed,
        "anchor": _iso(anchor),
        "world": world_oracle,
        "tests": test_oracle,
    }
    oracle_hash = _digest(oracle_core)

    public = {
        "schema_version": _SCHEMA_VERSION,
        "suite": "JARVIS-20",
        "scenario_id": scenario_id,
        "seed": seed,
        "anchor": _iso(anchor),
        "oracle_sha256": oracle_hash,
        "world_fixture": world,
        "tests": tests,
        "score_sheet": _score_sheet(seed, tests, scenario_id, _iso(anchor)),
        "privacy": {
            "contains_real_user_data": False,
            "generated_addresses": False,
            "generated_external_recipients_are_non_deliverable_example_test": True,
            "live_device_tests_require_evaluator_supplied_safe_values": [4, 11, 12, 13, 14, 15, 16, 17, 18],
        },
    }
    oracle = {**oracle_core, "oracle_sha256": oracle_hash, "public_sha256": _digest(public)}
    return VariantBundle(public=public, oracle=oracle)


def _score_sheet(seed: str, tests: list[dict[str, Any]], scenario_id: str, run_at: str) -> dict[str, Any]:
    template = score_template(variant_seed=seed)
    template["scenario_id"] = scenario_id
    template["run_at"] = run_at
    by_id = {int(row["id"]): row for row in tests}
    for row in template["results"]:
        generated = by_id[int(row["id"])]
        row["instance"] = generated["instance"]
        row["prompt"] = generated["prompt"]
        row["setup"] = generated["setup"]
    return template


def validate_variant_bundle(public: dict[str, Any], oracle: dict[str, Any] | None = None) -> dict[str, Any]:
    problems: list[str] = []
    if public.get("suite") != "JARVIS-20":
        problems.append("public suite is not JARVIS-20")
    tests = public.get("tests")
    ids = [int(row.get("id")) for row in tests if isinstance(row, dict) and str(row.get("id", "")).isdigit()] if isinstance(tests, list) else []
    if ids != list(range(1, 21)):
        problems.append(f"public tests must be ordered 1-20; got {ids}")
    if len(set(ids)) != 20:
        problems.append("public tests contain duplicate/missing ids")
    if not public.get("scenario_id"):
        problems.append("missing scenario_id")
    if not public.get("oracle_sha256"):
        problems.append("missing oracle digest")

    oracle_match: bool | None = None
    if oracle is not None:
        supplied_hash = str(public.get("oracle_sha256") or "")
        core = {k: v for k, v in oracle.items() if k not in {"oracle_sha256", "public_sha256"}}
        calculated = _digest(core)
        oracle_match = supplied_hash == calculated == str(oracle.get("oracle_sha256") or "")
        if not oracle_match:
            problems.append("oracle digest does not match public commitment")
        public_hash = _digest(public)
        if str(oracle.get("public_sha256") or "") != public_hash:
            problems.append("oracle public_sha256 does not match public bundle")

    return {
        "ok": not problems,
        "scenario_id": public.get("scenario_id"),
        "tests": len(ids),
        "oracle_verified": oracle_match,
        "problems": problems,
    }


def write_variant_bundle(
    bundle: VariantBundle,
    *,
    public_path: Path,
    oracle_path: Path | None = None,
    score_path: Path | None = None,
) -> dict[str, str]:
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(json.dumps(bundle.public, ensure_ascii=False, indent=2), encoding="utf-8")
    written = {"public": str(public_path)}
    if oracle_path is not None:
        oracle_path.parent.mkdir(parents=True, exist_ok=True)
        oracle_path.write_text(json.dumps(bundle.oracle, ensure_ascii=False, indent=2), encoding="utf-8")
        written["oracle"] = str(oracle_path)
    if score_path is not None:
        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps(bundle.public["score_sheet"], ensure_ascii=False, indent=2), encoding="utf-8")
        written["score_sheet"] = str(score_path)
    return written
