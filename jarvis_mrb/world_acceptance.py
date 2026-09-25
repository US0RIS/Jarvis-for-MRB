from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator


@contextmanager
def _isolated_world() -> Iterator[tuple[Path, dict[str, Any]]]:
    """Redirect every world-model module used by acceptance to an isolated database.

    The acceptance harness must never mutate the user's deployed world. It therefore
    patches module-level DB_PATH/APP_DIR values for the duration of the scenario and
    restores them even if a check raises.
    """
    import jarvis_mrb.runtime_health as runtime_health
    import jarvis_mrb.world_document_versions as world_document_versions
    import jarvis_mrb.world_executive as world_executive
    import jarvis_mrb.world_executive_loop as world_executive_loop
    import jarvis_mrb.world_linker as world_linker
    import jarvis_mrb.world_migrations as world_migrations
    import jarvis_mrb.world_model as world_model
    import jarvis_mrb.world_situation as world_situation
    import jarvis_mrb.world_snapshot_reconcile as world_snapshot_reconcile
    import jarvis_mrb.world_term_context as world_term_context
    import jarvis_mrb.world_terms as world_terms
    import jarvis_mrb.world_verification as world_verification

    modules = {
        "runtime_health": runtime_health,
        "document_versions": world_document_versions,
        "executive": world_executive,
        "executive_loop": world_executive_loop,
        "linker": world_linker,
        "migrations": world_migrations,
        "model": world_model,
        "situation": world_situation,
        "snapshot_reconcile": world_snapshot_reconcile,
        "term_context": world_term_context,
        "terms": world_terms,
        "verification": world_verification,
    }
    saved: list[tuple[Any, str, Any]] = []
    temp = tempfile.TemporaryDirectory()
    base = Path(temp.name)
    db = base / "world_model.sqlite3"
    try:
        saved.append((world_model, "APP_DIR", world_model.APP_DIR))
        world_model.APP_DIR = base
        for module in modules.values():
            if hasattr(module, "DB_PATH"):
                saved.append((module, "DB_PATH", getattr(module, "DB_PATH")))
                setattr(module, "DB_PATH", db)
        # Prevent the synthetic situation query from attempting a live Google refresh.
        saved.append((world_situation, "_LAST_REFRESH_MONOTONIC", world_situation._LAST_REFRESH_MONOTONIC))
        world_situation._LAST_REFRESH_MONOTONIC = time.monotonic()
        yield db, modules
    finally:
        for module, name, value in reversed(saved):
            setattr(module, name, value)
        temp.cleanup()


def _rows(db: Path, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _one(db: Path, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
    rows = _rows(db, sql, params)
    return rows[0] if rows else None


def _check(checks: list[dict[str, Any]], criterion: int, name: str, condition: bool, evidence: Any = None) -> None:
    checks.append(
        {
            "criterion": int(criterion),
            "name": name,
            "passed": bool(condition),
            "evidence": evidence,
        }
    )


def run_synthetic_acceptance() -> dict[str, Any]:
    """Exercise the fixed Jarvis endpoint without external services or user data.

    This is deliberately broader than a unit test. One synthetic Apollo matter is
    observed through multiple interfaces and sources, converted into persistent world
    state, reasoned over, surfaced proactively, acted on, and independently verified.
    Additional negative/privacy checks prove that the same integration does not obtain
    its apparent coherence by over-linking or bypassing authority boundaries.
    """
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}

    with _isolated_world() as (db, modules):
        world_model = modules["model"]
        world_linker = modules["linker"]
        world_executive = modules["executive"]
        world_executive_loop = modules["executive_loop"]
        world_terms = modules["terms"]
        world_term_context = modules["term_context"]
        world_document_versions = modules["document_versions"]
        world_situation = modules["situation"]
        world_verification = modules["verification"]
        world_migrations = modules["migrations"]

        import jarvis_mrb.world_frontend_ingest as world_frontend_ingest
        import jarvis_mrb.world_intent_capture as world_intent_capture
        import jarvis_mrb.world_prebrief as world_prebrief
        from jarvis_mrb.permissions import decide as permission_decision

        migration = world_migrations.run_migrations(backup=False)
        details["migration"] = migration

        now = datetime.now().astimezone()
        overdue = (now - timedelta(hours=2)).isoformat()
        meeting_start = (now + timedelta(minutes=30)).isoformat()
        meeting_end = (now + timedelta(minutes=90)).isoformat()

        # --- iPhone/local state: explicit Known Person + Waiting-On dependency. ---
        first_snapshot = {
            "goals": [],
            "waiting": [
                {
                    "id": "apollo-schedules",
                    "person": "Daniel Reed",
                    "item": "Send revised Project Apollo disclosure schedules",
                    "created_at": (now - timedelta(days=2)).isoformat(),
                    "due_at": overdue,
                    "resolved_at": None,
                }
            ],
            "people": [
                {
                    "id": "known-daniel",
                    "name": "Daniel Reed",
                    "note": "Private face-enrollment note used only for acceptance testing.",
                    "enrolled_at": (now - timedelta(days=30)).isoformat(),
                }
            ],
            "inventory": [],
            "reminders": [],
            "encounters": [],
            "events": [],
            "receipts": [],
            "mode": "Work",
        }
        frontend_result = world_frontend_ingest.ingest_frontend_snapshot(first_snapshot)
        details["frontend_ingest"] = frontend_result
        daniel_row = _one(
            db,
            "SELECT entity_id FROM external_ids WHERE namespace='iphone_known_person' AND external_id='known-daniel'",
        )
        daniel_id = str(daniel_row["entity_id"]) if daniel_row else ""

        # Gmail identity must bridge to the explicitly enrolled person rather than
        # creating a parallel Daniel identity.
        email_daniel_id = world_model.ensure_entity(
            "person",
            "Daniel Reed",
            external_namespace="email_address",
            external_id="daniel@example.com",
            aliases=["daniel@example.com"],
            attributes={"email": "daniel@example.com"},
            confidence=1.0,
        )

        # --- Conversation: explicit persistent intention and negotiated term. ---
        goal_events = world_intent_capture.capture(
            "We're trying to get Project Apollo signed by Friday.",
            session_id="acceptance-apollo",
        )
        for event_id in goal_events:
            world_linker.link_event(event_id)

        discussion_event = world_model.record_event(
            "conversation.turn",
            "Project Apollo indemnity cap is 10% based on today's discussion.",
            source_kind="conversation",
            source_ref="acceptance:apollo-discussion",
            occurred_at=(now - timedelta(hours=3)).isoformat(),
            payload={
                "session_id": "acceptance-apollo",
                "user": "Project Apollo indemnity cap is 10% based on today's discussion.",
                "assistant": "Understood.",
            },
            evidence="Synthetic acceptance conversation evidence.",
            participants=[(world_model.SELF_ID, "speaker", 1.0)],
        )
        world_linker.link_event(discussion_event)

        # --- Gmail-style document history: v1 at 10%, revised v2 at 15%. ---
        old_attachment = world_model.record_knowledge_source(
            "gmail_attachment",
            "apollo-old:a1",
            title="Project Apollo Purchase Agreement Draft v1.docx",
            text=(
                "Project Apollo Purchase Agreement. The indemnity cap shall equal 10% "
                "of the Purchase Price. The survival period is 18 months."
            ),
            occurred_at=(now - timedelta(hours=2, minutes=30)).isoformat(),
            metadata={
                "message_id": "apollo-old",
                "thread_id": "thread-apollo",
                "filename": "Project Apollo Purchase Agreement Draft v1.docx",
                "email_subject": "Project Apollo purchase agreement",
                "sender": "Daniel Reed <daniel@example.com>",
            },
            participants=[(email_daniel_id, "sender", 1.0)],
        )
        world_linker.link_event(old_attachment)

        new_attachment = world_model.record_knowledge_source(
            "gmail_attachment",
            "apollo-new:a2",
            title="Project Apollo Purchase Agreement Revised v2.docx",
            text=(
                "Project Apollo Purchase Agreement. The indemnity cap shall equal 15% "
                "of the Purchase Price. The survival period is 18 months."
            ),
            occurred_at=(now - timedelta(hours=1)).isoformat(),
            metadata={
                "message_id": "apollo-new",
                "thread_id": "thread-apollo",
                "filename": "Project Apollo Purchase Agreement Revised v2.docx",
                "email_subject": "Re: Project Apollo purchase agreement",
                "sender": "Daniel Reed <daniel@example.com>",
            },
            participants=[(email_daniel_id, "sender", 1.0)],
        )
        world_linker.link_event(new_attachment)

        version_result = world_document_versions.refresh(limit_pairs=20)
        for event_id in version_result.get("generated_event_ids") or []:
            world_linker.link_event(int(event_id))
        details["document_versions"] = version_result

        term_result = world_terms.refresh(limit=5000)
        for event_id in term_result.get("generated_event_ids") or []:
            world_linker.link_event(int(event_id))
        details["terms"] = term_result

        # --- Calendar: imminent meeting with the same Daniel identity and Project. ---
        calendar_id = world_model.ensure_entity(
            "calendar",
            "Project Apollo signing call",
            external_namespace="calendar",
            external_id="cal-apollo-signing",
            confidence=1.0,
        )
        calendar_event = world_model.record_event(
            "calendar.context_enriched",
            "Calendar context: Project Apollo signing call — Final signing readiness review for Project Apollo.",
            source_kind="calendar_enriched",
            source_ref="cal-apollo-signing",
            occurred_at=meeting_start,
            payload={
                "calendar_event_id": "cal-apollo-signing",
                "title": "Project Apollo signing call",
                "start": meeting_start,
                "end": meeting_end,
                "location": "Conference Room A",
                "status": "confirmed",
                "description": "Final signing readiness review for Project Apollo.",
            },
            participants=[
                (calendar_id, "meeting", 1.0),
                (world_model.SELF_ID, "calendar_owner", 1.0),
                (email_daniel_id, "attendee", 1.0),
            ],
        )
        world_linker.link_event(calendar_event)
        world_linker.refresh_links(limit=5000)
        world_executive.refresh_intentions()
        world_executive_loop.refresh()

        project_row = _one(
            db,
            "SELECT id FROM entities WHERE kind='project' AND normalized_name='project apollo' ORDER BY last_seen_at DESC LIMIT 1",
        )
        project_id = str(project_row["id"]) if project_row else ""
        intention_row = _one(db, "SELECT id,title FROM intentions WHERE status='active' ORDER BY updated_at DESC LIMIT 1")
        intention_id = str(intention_row["id"]) if intention_row else ""

        # Criterion 1 — persistent world model.
        counts = {
            "entities": int(_one(db, "SELECT COUNT(*) AS n FROM entities")["n"]),
            "events": int(_one(db, "SELECT COUNT(*) AS n FROM events")["n"]),
            "beliefs": int(_one(db, "SELECT COUNT(*) AS n FROM beliefs")["n"]),
            "commitments": int(_one(db, "SELECT COUNT(*) AS n FROM commitments")["n"]),
        }
        _check(checks, 1, "persistent world stores entities/events/beliefs/commitments", all(v > 0 for v in counts.values()), counts)

        # Criterion 2 — identity continuity across iPhone, Gmail and Calendar.
        attendee_row = _one(
            db,
            "SELECT 1 FROM event_entities WHERE event_id=? AND entity_id=? AND role='attendee'",
            (calendar_event, email_daniel_id),
        )
        _check(
            checks,
            2,
            "Daniel resolves to one entity across Known People, Gmail identity and Calendar attendee",
            bool(daniel_id and daniel_id == email_daniel_id and attendee_row),
            {"known_people_entity": daniel_id, "email_entity": email_daniel_id},
        )

        # Criterion 3 — persistent intention.
        _check(
            checks,
            3,
            "explicit conversational objective becomes active persistent intention",
            bool(intention_row and "Project Apollo" in str(intention_row["title"])),
            dict(intention_row) if intention_row else None,
        )

        # Criterion 4 — situational awareness.
        situation_context = world_situation.context_for_query("Anything I need to know before I go in?")
        _check(
            checks,
            4,
            "meeting situation connects meeting, person, project and Waiting-On obligation",
            all(token in situation_context for token in ("Project Apollo signing call", "Daniel Reed", "Project Apollo", "disclosure schedules")),
            situation_context[:3000],
        )

        # Criterion 5 — cross-source reasoning and chronology.
        latest_terms = world_terms.latest_observations(project_id) if project_id else []
        latest_cap = next((item for item in latest_terms if item.get("term_key") == "indemnity_cap"), None)
        conflict_count_row = _one(db, "SELECT COUNT(*) AS n FROM term_conflicts")
        conflict_count = int(conflict_count_row["n"]) if conflict_count_row else 0
        version_change_row = _one(db, "SELECT summary FROM events WHERE event_type='document.version_changed' ORDER BY id DESC LIMIT 1")
        _check(
            checks,
            5,
            "cross-source term ledger preserves 10%/15% discrepancy and current 15% chronology",
            bool(latest_cap and str(latest_cap.get("value")) == "15%" and conflict_count >= 1),
            {"latest_cap": latest_cap, "conflicts": conflict_count},
        )
        _check(
            checks,
            5,
            "document lineage detects numeric change 10% to 15%",
            bool(version_change_row and "10%" in str(version_change_row["summary"]) and "15%" in str(version_change_row["summary"])),
            str(version_change_row["summary"]) if version_change_row else "",
        )

        # Criterion 6 — Executive Loop.
        plans = world_executive_loop.plans_for_query("What's blocking Project Apollo?", limit=1)
        plan = plans[0] if plans else {}
        blocker_kinds = {str(item.get("kind")) for item in plan.get("blockers") or []}
        decision = plan.get("decision") or {}
        _check(
            checks,
            6,
            "Executive Loop compiles at-risk objective with substantive and dependency blockers",
            bool(plan.get("state") == "at_risk" and "term_conflict" in blocker_kinds and "overdue_commitment" in blocker_kinds),
            {"state": plan.get("state"), "blockers": sorted(blocker_kinds), "next_actions": plan.get("next_actions")},
        )
        _check(
            checks,
            6,
            "Executive decision prioritizes evidence gathering through normal permission gate",
            bool(decision.get("tool") == "knowledge.search" and decision.get("requires_confirmation") is False),
            decision,
        )

        # Criterion 7 — closed-loop verification.
        decision_row = _one(
            db,
            "SELECT id FROM executive_decisions WHERE intention_id=? AND status='current' ORDER BY updated_at DESC LIMIT 1",
            (intention_id,),
        )
        decision_id = str(decision_row["id"]) if decision_row else ""
        followup_args = {
            "recipient": "daniel@example.com",
            "subject": "Project Apollo revised schedules",
            "body": "Please send the revised Project Apollo disclosure schedules.",
        }
        if decision_id:
            conn = sqlite3.connect(db)
            try:
                conn.execute(
                    "UPDATE executive_decisions SET proposed_tool='gmail.send',proposed_args_json=?,requires_confirmation=1 WHERE id=?",
                    (json.dumps(followup_args, sort_keys=True), decision_id),
                )
                conn.commit()
            finally:
                conn.close()
        action_event = world_model.record_tool_execution(
            "gmail.send",
            followup_args,
            ok=True,
            message="Provider accepted send request.",
        )
        verification_id = world_verification.register_execution(
            "gmail.send",
            followup_args,
            SimpleNamespace(
                ok=True,
                message="Sent email to daniel@example.com.",
                data={
                    "message_id": "acceptance-apollo-followup",
                    "email": "daniel@example.com",
                },
            ),
            action_event_id=action_event,
            executive_decision_id=decision_id or None,
        )
        pending_row = _one(db, "SELECT status FROM action_verifications WHERE id=?", (verification_id,))
        original_observe = world_verification._observe
        try:
            world_verification._observe = lambda verifier, expected: (
                "verified",
                "Independent Sent Mail read-back contains the causally bounded message.",
            )
            verification_outcome = world_verification.check_one(verification_id, force=True)
        finally:
            world_verification._observe = original_observe
        _check(
            checks,
            7,
            "external write remains pending after tool receipt and closes only after independent observation",
            bool(
                pending_row
                and str(pending_row["status"]) == "pending"
                and verification_outcome
                and verification_outcome.get("status") == "verified"
            ),
            {"before": str(pending_row["status"]) if pending_row else None, "after": verification_outcome},
        )

        # Criterion 8 — appropriate proactivity.
        prebrief = world_prebrief.build("cal-apollo-signing", "Project Apollo signing call")
        prebrief_text = str((prebrief or {}).get("message") or "")
        _check(
            checks,
            8,
            "proactive prebrief surfaces only actionable connected facts",
            bool(prebrief and "Term discrepancy" in prebrief_text and "Daniel Reed still owes" in prebrief_text),
            prebrief,
        )

        # Criterion 9 — privacy and authority boundaries.
        second_snapshot = dict(first_snapshot)
        second_snapshot["people"] = []
        revoke_result = world_frontend_ingest.ingest_frontend_snapshot(second_snapshot)
        iphone_identity_left = _one(
            db,
            "SELECT 1 FROM external_ids WHERE namespace='iphone_known_person' AND external_id='known-daniel'",
        )
        email_identity_left = _one(
            db,
            "SELECT 1 FROM external_ids WHERE namespace='email_address' AND external_id='daniel@example.com' AND entity_id=?",
            (email_daniel_id,),
        )
        entity_row = _one(db, "SELECT attributes_json FROM entities WHERE id=?", (email_daniel_id,))
        attrs = json.loads(str(entity_row["attributes_json"] or "{}")) if entity_row else {}
        send_policy = permission_decision("gmail.send")
        read_policy = permission_decision("knowledge.search")
        _check(
            checks,
            9,
            "Known People unenrollment revokes face identity/private note but preserves independent email identity",
            bool(
                revoke_result.get("reconcile", {}).get("revoked_known_people") == 1
                and not iphone_identity_left
                and email_identity_left
                and "note" not in attrs
            ),
            {"reconcile": revoke_result.get("reconcile"), "attributes": attrs},
        )
        _check(
            checks,
            9,
            "external writes require confirmation while read-only evidence gathering does not",
            bool(send_policy.needs_confirmation and not read_policy.needs_confirmation and send_policy.allowed and read_policy.allowed),
            {"gmail_send": send_policy.__dict__, "knowledge_search": read_policy.__dict__},
        )

        # Criterion 10 — unified interaction/state across interfaces.
        source_kinds = {
            str(row["source_kind"])
            for row in _rows(
                db,
                """
                SELECT DISTINCT e.source_kind
                FROM events e JOIN event_entities ee ON ee.event_id=e.id
                WHERE ee.entity_id=?
                """,
                (project_id,),
            )
        } if project_id else set()
        commitment_link = _one(
            db,
            "SELECT 1 FROM intention_commitments WHERE intention_id=? AND commitment_id='waiting:apollo-schedules'",
            (intention_id,),
        )
        _check(
            checks,
            10,
            "conversation, Gmail-style documents, Calendar and iPhone Waiting-On converge on one objective/world",
            bool(
                {"conversation", "gmail_attachment", "calendar_enriched"}.issubset(source_kinds)
                and commitment_link
            ),
            {"project_source_kinds": sorted(source_kinds), "waiting_linked": bool(commitment_link)},
        )

        # Negative controls: coherence must not come from indiscriminate graph linking.
        alex_id = world_model.ensure_entity(
            "person",
            "Alex Example",
            external_namespace="email_address",
            external_id="alex@example.com",
        )
        negative_event = world_model.record_event(
            "conversation.turn",
            "Alex Example is not on Project Apollo.",
            source_kind="conversation",
            source_ref="acceptance:negative-association",
            payload={"user": "Alex Example is not on Project Apollo."},
            participants=[(world_model.SELF_ID, "speaker", 1.0)],
        )
        world_linker.link_event(negative_event)
        false_relation = _one(
            db,
            "SELECT 1 FROM entity_relations WHERE subject_id=? AND predicate='associated_with_project' AND object_id=? AND state='current'",
            (alex_id, project_id),
        )
        partial_reconcile = modules["snapshot_reconcile"].reconcile_authoritative_snapshot(
            {"mode": "Work", "goals": None, "waiting": "malformed", "people": {"not": "a list"}}
        )
        unrelated = __import__("jarvis_mrb.world_relevance", fromlist=["context_for_query"]).context_for_query(
            "What should I order for dinner?"
        )
        _check(
            checks,
            10,
            "unified graph rejects negative/generic person-project co-occurrence",
            not bool(false_relation),
            {"false_relation": bool(false_relation)},
        )
        _check(
            checks,
            9,
            "partial/malformed iPhone snapshots cannot destructively reconcile authoritative collections",
            partial_reconcile == {"retired_goals": 0, "retired_waiting": 0, "revoked_known_people": 0},
            partial_reconcile,
        )
        _check(
            checks,
            8,
            "unrelated conversational queries are not contaminated by Apollo Executive state",
            unrelated == "",
            unrelated,
        )

        # Criterion 11 — operational reliability.
        # Link the final synthetic events before diagnostics so the acceptance world is
        # evaluated as a quiescent prepared deployment rather than mid-refresh.
        world_linker.refresh_links(limit=5000)
        world_executive.refresh_intentions()
        world_executive_loop.refresh()
        from jarvis_mrb.world_diagnostics import validate as validate_world
        diagnostics = validate_world()
        details["diagnostics"] = diagnostics
        _check(
            checks,
            11,
            "versioned schema, integrity, graph/privacy/verification diagnostics are clean",
            bool(diagnostics.get("ok") and migration.get("ready")),
            {"problems": diagnostics.get("problems"), "warnings": diagnostics.get("warnings")},
        )

        # Criterion 12 — the acceptance scenario itself crosses the full causal chain.
        direct_term_context = world_term_context.context_for_query("What's the indemnity cap on Project Apollo?")
        full_chain = bool(
            goal_events
            and project_id
            and intention_id
            and conflict_count >= 1
            and version_change_row
            and prebrief
            and decision
            and verification_outcome
            and verification_outcome.get("status") == "verified"
            and "15%" in direct_term_context
        )
        _check(
            checks,
            12,
            "Apollo scenario crosses intention → evidence → conflict → situation → decision → action → observed outcome",
            full_chain,
            {
                "term_context": direct_term_context[:2200],
                "prebrief": prebrief,
                "decision": decision,
                "verification": verification_outcome,
            },
        )

    criteria: dict[int, dict[str, Any]] = {}
    for number in range(1, 13):
        relevant = [item for item in checks if int(item["criterion"]) == number]
        criteria[number] = {
            "passed": bool(relevant) and all(bool(item["passed"]) for item in relevant),
            "checks": len(relevant),
            "failed": [item["name"] for item in relevant if not item["passed"]],
        }
    failed_checks = [item for item in checks if not item["passed"]]
    return {
        "ok": not failed_checks and all(item["passed"] for item in criteria.values()),
        "mode": "synthetic_isolated",
        "mutates_user_data": False,
        "uses_external_services": False,
        "criteria": criteria,
        "checks": checks,
        "failed_checks": failed_checks,
        "details": details,
    }


def status() -> dict[str, Any]:
    return {
        "fixed_endpoint_criteria": list(range(1, 13)),
        "synthetic_isolated_acceptance": True,
        "mutates_user_data": False,
        "uses_external_services": False,
        "covers_apollo_full_chain": True,
        "runtime_device_validation_still_required_after_deployment": True,
    }
