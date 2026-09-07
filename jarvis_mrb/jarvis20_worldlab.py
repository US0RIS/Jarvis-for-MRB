from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis_mrb.jarvis20_variants import validate_variant_bundle


def _check(rows: list[dict[str, Any]], test_id: int, name: str, passed: bool, evidence: Any = None) -> None:
    rows.append({
        "test_id": int(test_id),
        "name": name,
        "passed": bool(passed),
        "evidence": evidence,
    })


def _one(db: Path, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _parse_time(raw: str) -> datetime:
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _temporal_rebaser(anchor_raw: str):
    """Keep scenario chronology stable while making 'imminent/overdue' relative to now.

    A generated bundle is replayable months later. We therefore preserve every offset
    from the serialized anchor while moving the whole synthetic timeline to the moment
    of materialization. The public/oracle files themselves remain unchanged.
    """
    anchor = _parse_time(anchor_raw)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    def rebase(raw: str) -> str:
        return (now + (_parse_time(raw) - anchor)).isoformat()

    return rebase


def run_world_variant(public: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    """Materialize one procedural JARVIS-20 world in an isolated database.

    This is a digital-twin preflight for JARVIS-20 tests 5-10. It never awards the
    live 0-3 behavioral score and never touches the user's deployed world or external
    services. The hidden oracle is required so the system under test cannot derive the
    expected answer from the public fixture.
    """
    validation = validate_variant_bundle(public, oracle)
    if not validation.get("ok"):
        return {
            "ok": False,
            "mode": "procedural_world_preflight",
            "mutates_user_data": False,
            "uses_external_services": False,
            "validation": validation,
            "checks": [],
            "failed_checks": ["variant validation failed"],
        }

    from jarvis_mrb.world_acceptance import _isolated_world

    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    world = public["world_fixture"]
    hidden = oracle["world"]
    rebase = _temporal_rebaser(str(public["anchor"]))

    with _isolated_world() as (db, modules):
        world_model = modules["model"]
        world_linker = modules["linker"]
        world_executive = modules["executive"]
        world_executive_loop = modules["executive_loop"]
        world_terms = modules["terms"]
        world_document_versions = modules["document_versions"]
        world_situation = modules["situation"]
        world_migrations = modules["migrations"]

        import jarvis_mrb.world_frontend_ingest as world_frontend_ingest
        import jarvis_mrb.world_intent_capture as world_intent_capture

        migration = world_migrations.run_migrations(backup=False)
        details["migration"] = migration

        primary = world["primary_person"]
        distractors = world.get("distractor_people") or []
        waiting = world["waiting_on"]
        meeting = world["meeting"]
        sources = world["sources"]
        project = world["project"]

        # iPhone Known People + Waiting-On establishes one explicit identity lane.
        snapshot = {
            "goals": [],
            "waiting": [{
                "id": f"waiting-{public['scenario_id'].lower()}",
                "person": primary["name"],
                "item": waiting["item"],
                "created_at": rebase(public["anchor"]),
                "due_at": rebase(waiting["due_at"]),
                "resolved_at": None,
            }],
            "people": [{
                "id": primary["person_id"],
                "name": primary["name"],
                "note": "Procedural JARVIS-20 private enrollment note.",
                "enrolled_at": rebase(public["anchor"]),
            }],
            "inventory": [],
            "reminders": [],
            "encounters": [],
            "events": [],
            "receipts": [],
            "mode": "Work",
        }
        details["frontend"] = world_frontend_ingest.ingest_frontend_snapshot(snapshot)

        known_row = _one(
            db,
            "SELECT entity_id FROM external_ids WHERE namespace='iphone_known_person' AND external_id=?",
            (primary["person_id"],),
        )
        known_id = str(known_row["entity_id"]) if known_row else ""
        email_id = world_model.ensure_entity(
            "person",
            primary["name"],
            external_namespace="email_address",
            external_id=primary["email"],
            aliases=[primary["email"]],
            attributes={"email": primary["email"]},
            confidence=1.0,
        )

        # Add distractors with strong external IDs so name/co-occurrence heuristics
        # cannot make the world look coherent by incorrectly merging identities.
        distractor_ids: dict[str, str] = {}
        for person in distractors:
            distractor_ids[person["person_id"]] = world_model.ensure_entity(
                "person",
                person["name"],
                external_namespace="email_address",
                external_id=person["email"],
                aliases=[person["email"]],
                attributes={"email": person["email"]},
                confidence=1.0,
            )

        # Explicit persistent intention.
        objective_text = f"We're trying to {world['objective']['text']}."
        goal_events = world_intent_capture.capture(
            objective_text,
            session_id=f"j20:{public['scenario_id']}",
        )
        for event_id in goal_events:
            world_linker.link_event(event_id)

        # Older conversational term evidence.
        discussion = sources["older_discussion"]
        discussion_event = world_model.record_event(
            "conversation.turn",
            discussion["text"],
            source_kind="conversation",
            source_ref=f"j20:{public['scenario_id']}:discussion",
            occurred_at=rebase(discussion["occurred_at"]),
            payload={
                "session_id": f"j20:{public['scenario_id']}",
                "user": discussion["text"],
                "assistant": "Understood.",
            },
            evidence="Procedural JARVIS-20 conversation evidence.",
            participants=[(world_model.SELF_ID, "speaker", 1.0)],
        )
        world_linker.link_event(discussion_event)

        # Old/new Gmail-style attachment lineage.
        for key, source_ref in (("older_document", "old"), ("newer_document", "new")):
            document = sources[key]
            event_id = world_model.record_knowledge_source(
                "gmail_attachment",
                f"j20-{public['scenario_id']}:{source_ref}",
                title=document["filename"],
                text=document["text"],
                occurred_at=rebase(document["occurred_at"]),
                metadata={
                    "message_id": f"j20-{public['scenario_id']}-{source_ref}",
                    "thread_id": f"j20-thread-{public['scenario_id']}",
                    "filename": document["filename"],
                    "email_subject": f"{project} agreement",
                    "sender": document["sender"],
                },
                participants=[(email_id, "sender", 1.0)],
            )
            world_linker.link_event(event_id)

        version_result = world_document_versions.refresh(limit_pairs=30)
        for event_id in version_result.get("generated_event_ids") or []:
            world_linker.link_event(int(event_id))
        details["document_versions"] = version_result

        term_result = world_terms.refresh(limit=5000)
        for event_id in term_result.get("generated_event_ids") or []:
            world_linker.link_event(int(event_id))
        details["terms"] = term_result

        # Imminent Calendar meeting with same primary identity plus a distractor.
        calendar_entity = world_model.ensure_entity(
            "calendar",
            meeting["title"],
            external_namespace="calendar",
            external_id=f"j20-cal-{public['scenario_id']}",
            confidence=1.0,
        )
        participants = [
            (calendar_entity, "meeting", 1.0),
            (world_model.SELF_ID, "calendar_owner", 1.0),
            (email_id, "attendee", 1.0),
        ]
        if distractors:
            participants.append((distractor_ids[distractors[0]["person_id"]], "attendee", 1.0))
        meeting_start = rebase(meeting["start"])
        meeting_end = rebase(meeting["end"])
        calendar_event = world_model.record_event(
            "calendar.context_enriched",
            f"Calendar context: {meeting['title']} — {meeting['description']}",
            source_kind="calendar_enriched",
            source_ref=f"j20-cal-{public['scenario_id']}",
            occurred_at=meeting_start,
            payload={
                "calendar_event_id": f"j20-cal-{public['scenario_id']}",
                "title": meeting["title"],
                "start": meeting_start,
                "end": meeting_end,
                "location": "JARVIS-20 Synthetic Conference Room",
                "status": "confirmed",
                "description": meeting["description"],
            },
            participants=participants,
        )
        world_linker.link_event(calendar_event)

        # Negative association is a deliberate trap.
        negative_person_id = hidden["expected_false_association_person_id"]
        negative_entity_id = distractor_ids.get(negative_person_id, "")
        negative_event = world_model.record_event(
            "conversation.turn",
            world["negative_association_statement"],
            source_kind="conversation",
            source_ref=f"j20:{public['scenario_id']}:negative-association",
            payload={"user": world["negative_association_statement"]},
            participants=[(world_model.SELF_ID, "speaker", 1.0)],
        )
        world_linker.link_event(negative_event)

        world_linker.refresh_links(limit=5000)
        world_executive.refresh_intentions()
        world_executive_loop.refresh()

        project_row = _one(
            db,
            "SELECT id FROM entities WHERE kind='project' AND normalized_name=? ORDER BY last_seen_at DESC LIMIT 1",
            (project.lower(),),
        )
        project_id = str(project_row["id"]) if project_row else ""

        # Test 5: one cross-source identity, no false merge.
        attendee = _one(
            db,
            "SELECT 1 FROM event_entities WHERE event_id=? AND entity_id=? AND role='attendee'",
            (calendar_event, email_id),
        )
        false_merge = any(entity_id == email_id for entity_id in distractor_ids.values())
        _check(
            checks,
            5,
            "Known People, Gmail and Calendar resolve primary person to one identity without distractor merge",
            bool(known_id and known_id == email_id and attendee and not false_merge),
            {"known_id": known_id, "email_id": email_id, "distractor_ids": distractor_ids},
        )

        # Test 6: objective survived capture as active intention.
        intention = _one(
            db,
            "SELECT id,title,due_at,status FROM intentions WHERE status='active' AND lower(title) LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"%{project.lower()}%",),
        )
        _check(
            checks,
            6,
            "generated explicit objective becomes an active persistent intention",
            bool(intention),
            dict(intention) if intention else None,
        )

        # Test 7: generic pre-meeting question retrieves generated world state.
        situation = world_situation.context_for_query("Anything I need to know before I go in?")
        situation_tokens = [str(value) for value in hidden["expected_situation_tokens"]]
        _check(
            checks,
            7,
            "generic pre-meeting query surfaces generated project/person/dependency context",
            all(token.lower() in situation.lower() for token in situation_tokens),
            {"required_tokens": situation_tokens, "context": situation[:5000]},
        )

        # Test 8: source chronology determines current term while conflict remains.
        latest = world_terms.latest_observations(project_id) if project_id else []
        term_key = hidden["expected_term"]["term_key"]
        latest_term = next((row for row in latest if row.get("term_key") == term_key), None)
        conflict_row = _one(
            db,
            "SELECT COUNT(*) AS n FROM term_conflicts tc JOIN term_observations newer ON newer.id=tc.newer_observation_id WHERE newer.project_id=? AND newer.term_key=?",
            (project_id, term_key),
        ) if project_id else None
        conflicts = int(conflict_row["n"]) if conflict_row else 0
        _check(
            checks,
            8,
            "generated newer term is current while older conflicting value remains provenance-bearing",
            bool(
                latest_term
                and str(latest_term.get("value")) == str(hidden["expected_current_term_value"])
                and conflicts >= 1
            ),
            {"latest": latest_term, "conflicts": conflicts, "expected": hidden["expected_current_term_value"]},
        )

        # Test 9: document lineage captures both material values despite benign edits.
        version_row = _one(
            db,
            "SELECT summary FROM events WHERE event_type='document.version_changed' ORDER BY id DESC LIMIT 1",
        )
        version_summary = str(version_row["summary"] or "") if version_row else ""
        required_change_tokens = [str(value) for value in hidden["expected_material_change_tokens"]]
        _check(
            checks,
            9,
            "generated document revision exposes the material changed values",
            bool(version_row and all(token in version_summary for token in required_change_tokens)),
            {"required_tokens": required_change_tokens, "summary": version_summary},
        )

        # Test 10: Executive state prioritizes material conflict and overdue dependency.
        plans = world_executive_loop.plans_for_query(f"What's blocking {project}?", limit=1)
        plan = plans[0] if plans else {}
        blocker_kinds = {str(item.get("kind")) for item in plan.get("blockers") or []}
        _check(
            checks,
            10,
            "Executive plan marks generated objective at risk with conflict and overdue dependency blockers",
            bool(plan.get("state") == "at_risk" and {"term_conflict", "overdue_commitment"}.issubset(blocker_kinds)),
            {"state": plan.get("state"), "blocker_kinds": sorted(blocker_kinds), "decision": plan.get("decision")},
        )

        # Negative control tied to tests 5/7/10: explicit negation must not become a
        # current person-project relationship.
        false_relation = _one(
            db,
            "SELECT 1 FROM entity_relations WHERE subject_id=? AND predicate='associated_with_project' AND object_id=? AND state='current'",
            (negative_entity_id, project_id),
        ) if negative_entity_id and project_id else None
        _check(
            checks,
            5,
            "negative person-project statement does not create a current association",
            not bool(false_relation),
            {"negative_person_entity_id": negative_entity_id, "project_id": project_id},
        )

    failed = [row for row in checks if not row["passed"]]
    by_test: dict[str, dict[str, Any]] = {}
    for test_id in range(5, 11):
        relevant = [row for row in checks if row["test_id"] == test_id]
        by_test[str(test_id)] = {
            "passed": bool(relevant) and all(row["passed"] for row in relevant),
            "checks": len(relevant),
            "failed": [row["name"] for row in relevant if not row["passed"]],
        }

    return {
        "ok": not failed and all(row["passed"] for row in by_test.values()),
        "mode": "procedural_world_preflight",
        "scenario_id": public.get("scenario_id"),
        "seed": public.get("seed"),
        "mutates_user_data": False,
        "uses_external_services": False,
        "awards_behavioral_score": False,
        "temporal_replay_policy": "preserve_offsets_rebased_to_materialization_time",
        "tests": by_test,
        "checks": checks,
        "failed_checks": [row["name"] for row in failed],
        "details": details,
    }
