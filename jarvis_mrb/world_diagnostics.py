from __future__ import annotations

import sqlite3
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from jarvis_mrb.world_model import DB_PATH, status as world_status

_AGENCY_REQUIRED_TABLES = {
    "desired_states", "desired_state_evaluations", "desired_state_watches",
    "agency_plans", "agency_steps", "agency_runtime_state", "agency_settings", "agency_runtime_boots",
    "agency_deliberations", "agency_deliberation_workers", "agency_attention_events",
    "agency_capability_gaps", "agency_decision_cases", "agency_decision_branches",
    "agency_self_model_entries", "agency_real_gate_sessions",
    "agency_real_gate_receipts", "agency_release_validation_runs", "agency_installation_identity",
}
_REQUIRED_TABLES = {
    "entities", "external_ids", "aliases", "events", "event_entities", "beliefs", "commitments",
    "entity_relations", "relation_evidence", "intentions", "intention_entities", "intention_commitments",
    "term_observations", "term_conflicts", "document_version_pairs",
    "executive_attention", "executive_decisions", "action_verifications", "verification_observations",
    "runtime_subsystem_health", "gmail_attachment_sync_state", "world_schema_meta", "world_schema_history",
}
_STRONG_PERSON_PROJECT_ROLES = {
    "sender", "recipient", "attendee", "organizer", "owner", "assignee",
    "participant", "meeting_participant", "speaker", "requester", "beneficiary",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    return {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _parse_time(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        try:
            value = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone()


def validate(*, require_agency: bool = False) -> dict[str, Any]:
    from jarvis_mrb.runtime_health import status as runtime_status
    from jarvis_mrb.world_document_versions import status as document_status
    from jarvis_mrb.world_executive import status as executive_status
    from jarvis_mrb.world_executive_loop import status as executive_loop_status
    from jarvis_mrb.world_gmail_attachments import status as attachment_status
    from jarvis_mrb.world_linker import status as linker_status
    from jarvis_mrb.world_migrations import status as migration_status
    from jarvis_mrb.world_prebrief import status as prebrief_status
    from jarvis_mrb.world_relevance import status as relevance_status
    from jarvis_mrb.world_situation import status as situation_status
    from jarvis_mrb.world_terms import status as terms_status
    from jarvis_mrb.world_verification import status as verification_status

    core = world_status()
    linker = linker_status()
    executive = executive_status()
    executive_loop = executive_loop_status()
    relevance = relevance_status()
    situation = situation_status()
    prebrief = prebrief_status()
    terms = terms_status()
    documents = document_status()
    verification = verification_status()
    migrations = migration_status()
    runtime = runtime_status()
    attachments = attachment_status()
    problems: list[str] = []
    warnings: list[str] = []

    target_version = int(migrations.get("target") or 0)
    migration_history = [int(item.get("version") or 0) for item in migrations.get("history", [])]
    expected_history = list(range(1, target_version + 1)) if target_version else []
    if not bool(migrations.get("ready")):
        problems.append(
            f"World schema is v{migrations.get('current', 0)}; this build requires v{target_version} (run jarvis-world-migrate)."
        )
    elif migration_history != expected_history:
        problems.append(
            f"World schema reports v{target_version} but migration history is not contiguous: {migration_history}."
        )

    if bool(attachments.get("backlog_remaining")):
        warnings.append("Gmail attachment ingestion has a resumable backlog; subsequent knowledge refreshes must continue draining it.")
    attachment_state = str(attachments.get("last_status") or "never")
    attachment_error = str(attachments.get("last_error") or "").strip()
    if attachment_state in {"error", "partial"} and attachment_error:
        warnings.append(f"Gmail attachment ingestion last reported {attachment_state}: {attachment_error}")

    with _connect() as conn:
        integrity_row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = str(integrity_row[0]) if integrity_row else "unknown"
        if integrity.lower() != "ok":
            problems.append(f"SQLite integrity_check: {integrity}")

        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            problems.append(f"Foreign-key violations: {len(fk_rows)}")

        journal_row = conn.execute("PRAGMA journal_mode").fetchone()
        journal_mode = str(journal_row[0]).lower() if journal_row else "unknown"
        if bool(migrations.get("ready")) and journal_mode != "wal":
            warnings.append(f"World database journal_mode is {journal_mode}, expected WAL after migration.")

        tables = _existing_tables(conn)
        required_tables = _REQUIRED_TABLES | (_AGENCY_REQUIRED_TABLES if require_agency else set())
        missing_tables = sorted(required_tables - tables)
        if missing_tables:
            problems.append("Missing required world tables: " + ", ".join(missing_tables))

        agency_metrics: dict[str, Any] = {
            "invalid_desired_states": 0,
            "invalid_plan_states": 0,
            "invalid_step_states": 0,
            "multiple_current_plans": 0,
            "orphan_plans": 0,
            "orphan_verification_links": 0,
            "awaiting_verification_without_id": 0,
            "approval_plan_without_step": 0,
            "invalid_real_session_states": 0,
            "real_sessions_without_integrity_hash": 0,
            "completed_real_sessions_without_receipt": 0,
            "completed_real_session_receipt_mismatch": 0,
            "orphan_real_gate_receipts": 0,
            "running_real_sessions_with_receipt": 0,
        }
        if require_agency and _AGENCY_REQUIRED_TABLES <= tables:
            valid_desired = ("active", "satisfied", "blocked", "paused", "retired")
            desired_ph = ",".join("?" for _ in valid_desired)
            agency_metrics["invalid_desired_states"] = int(conn.execute(
                f"SELECT COUNT(*) FROM desired_states WHERE state NOT IN ({desired_ph})",
                valid_desired,
            ).fetchone()[0])

            valid_plans = (
                "active", "awaiting_approval", "awaiting_verification", "needs_replan",
                "blocked", "completed", "superseded", "retired",
            )
            plan_ph = ",".join("?" for _ in valid_plans)
            agency_metrics["invalid_plan_states"] = int(conn.execute(
                f"SELECT COUNT(*) FROM agency_plans WHERE status NOT IN ({plan_ph})",
                valid_plans,
            ).fetchone()[0])

            valid_steps = (
                "pending", "awaiting_approval", "executing", "executed",
                "awaiting_verification", "verified", "skipped", "failed", "blocked",
            )
            step_ph = ",".join("?" for _ in valid_steps)
            agency_metrics["invalid_step_states"] = int(conn.execute(
                f"SELECT COUNT(*) FROM agency_steps WHERE status NOT IN ({step_ph})",
                valid_steps,
            ).fetchone()[0])

            current_plan_states = ("active", "awaiting_approval", "awaiting_verification", "needs_replan", "blocked")
            current_ph = ",".join("?" for _ in current_plan_states)
            agency_metrics["multiple_current_plans"] = len(conn.execute(
                f"""
                SELECT desired_state_id
                FROM agency_plans
                WHERE status IN ({current_ph})
                GROUP BY desired_state_id
                HAVING COUNT(*)>1
                """,
                current_plan_states,
            ).fetchall())
            agency_metrics["orphan_plans"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM agency_plans p
                LEFT JOIN desired_states d ON d.id=p.desired_state_id
                WHERE d.id IS NULL
                """
            ).fetchone()[0])
            agency_metrics["orphan_verification_links"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM action_verifications v
                LEFT JOIN agency_steps s ON s.id=v.agency_step_id
                WHERE v.agency_step_id!='' AND s.id IS NULL
                """
            ).fetchone()[0])
            agency_metrics["awaiting_verification_without_id"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM agency_steps
                WHERE status='awaiting_verification' AND verification_id=''
                """
            ).fetchone()[0])
            agency_metrics["approval_plan_without_step"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM agency_plans p
                WHERE p.status='awaiting_approval'
                  AND NOT EXISTS (
                    SELECT 1 FROM agency_steps s
                    WHERE s.plan_id=p.id AND s.status='awaiting_approval'
                  )
                """
            ).fetchone()[0])
            agency_metrics["invalid_real_session_states"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM agency_real_gate_sessions
                WHERE status NOT IN ('running','completed')
                """
            ).fetchone()[0])
            agency_metrics["real_sessions_without_integrity_hash"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM agency_real_gate_sessions
                WHERE session_hash=''
                """
            ).fetchone()[0])
            agency_metrics["completed_real_sessions_without_receipt"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM agency_real_gate_sessions
                WHERE status='completed' AND receipt_id=''
                """
            ).fetchone()[0])
            agency_metrics["completed_real_session_receipt_mismatch"] = int(conn.execute(
                """
                SELECT COUNT(*)
                FROM agency_real_gate_sessions s
                LEFT JOIN agency_real_gate_receipts r ON r.id=s.receipt_id
                WHERE s.status='completed'
                  AND s.receipt_id!=''
                  AND (
                    r.id IS NULL
                    OR r.session_id!=s.id
                    OR r.gate!=s.gate
                    OR r.deployment_sha!=s.deployment_sha
                    OR r.environment_fingerprint!=s.environment_fingerprint
                  )
                """
            ).fetchone()[0])
            agency_metrics["orphan_real_gate_receipts"] = int(conn.execute(
                """
                SELECT COUNT(*)
                FROM agency_real_gate_receipts r
                LEFT JOIN agency_real_gate_sessions s ON s.id=r.session_id
                WHERE r.session_id='' OR s.id IS NULL
                """
            ).fetchone()[0])
            agency_metrics["running_real_sessions_with_receipt"] = int(conn.execute(
                """
                SELECT COUNT(*) FROM agency_real_gate_sessions
                WHERE status='running' AND receipt_id!=''
                """
            ).fetchone()[0])

            for key, label in (
                ("invalid_desired_states", "Agency desired states with invalid lifecycle states"),
                ("invalid_plan_states", "Agency plans with invalid lifecycle states"),
                ("invalid_step_states", "Agency steps with invalid lifecycle states"),
                ("multiple_current_plans", "Desired states with multiple current Agency plans"),
                ("orphan_plans", "Agency plans without desired states"),
                ("orphan_verification_links", "Action verifications pointing at missing Agency steps"),
                ("awaiting_verification_without_id", "Agency steps awaiting verification without verification IDs"),
                ("approval_plan_without_step", "Agency plans awaiting approval without an approval step"),
                ("invalid_real_session_states", "REAL Agency sessions with invalid lifecycle states"),
                ("real_sessions_without_integrity_hash", "REAL Agency sessions without integrity hashes"),
                ("completed_real_sessions_without_receipt", "Completed REAL Agency sessions without receipts"),
                ("completed_real_session_receipt_mismatch", "Completed REAL Agency sessions with mismatched receipts"),
                ("orphan_real_gate_receipts", "REAL Agency receipts without matching sessions"),
            ):
                value = int(agency_metrics[key])
                if value:
                    problems.append(f"{label}: {value}")

            running_with_receipt = int(agency_metrics["running_real_sessions_with_receipt"])
            if running_with_receipt:
                warnings.append(
                    "REAL Agency sessions with receipts still marked running "
                    f"(recoverable incomplete finalization): {running_with_receipt}"
                )

        max_event = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0])
        linked_event = int(linker.get("last_linked_event_id") or 0)
        linker_lag = max(0, max_event - linked_event)
        if linker_lag > 500:
            warnings.append(f"World linker is {linker_lag} events behind.")

        mismatch_rows = conn.execute(
            """
            SELECT e.id,e.canonical_name,b.value_json,i.status
            FROM entities e
            JOIN beliefs b ON b.subject_id=e.id AND b.predicate='status' AND b.state='current'
            LEFT JOIN intentions i ON i.source_kind='explicit_goal' AND i.source_ref=e.id
            WHERE e.kind='goal'
            """
        ).fetchall()
        goal_mismatches = 0
        for row in mismatch_rows:
            raw = str(row["value_json"] or "\"active\"").strip('"').lower()
            expected = "completed" if raw in {"completed", "done", "resolved"} else (
                "retired" if raw in {"retired", "deleted", "removed", "cancelled", "canceled", "inactive"} else "active"
            )
            if expected != str(row["status"] or "missing"):
                goal_mismatches += 1
        if goal_mismatches:
            problems.append(f"Goal/intention status mismatches: {goal_mismatches}")

        stale_links = int(conn.execute(
            """
            SELECT COUNT(*) FROM intention_commitments ic
            JOIN intentions i ON i.id=ic.intention_id
            JOIN commitments c ON c.id=ic.commitment_id
            WHERE i.status!='active' OR c.status!='pending'
            """
        ).fetchone()[0])
        if stale_links:
            problems.append(f"Stale current intention/commitment links: {stale_links}")

        relation_without_evidence = len(conn.execute(
            """
            SELECT r.id FROM entity_relations r
            LEFT JOIN relation_evidence re ON re.relation_id=r.id
            WHERE r.state='current' GROUP BY r.id HAVING COUNT(re.event_id)=0
            """
        ).fetchall())
        if relation_without_evidence:
            problems.append(f"Current derived relations without evidence: {relation_without_evidence}")

        relation_count_mismatches = int(conn.execute(
            "SELECT COUNT(*) FROM entity_relations r WHERE r.evidence_count != (SELECT COUNT(*) FROM relation_evidence re WHERE re.relation_id=r.id)"
        ).fetchone()[0])
        if relation_count_mismatches:
            problems.append(f"Derived relations with incorrect evidence_count: {relation_count_mismatches}")

        strong_placeholders = ",".join("?" for _ in _STRONG_PERSON_PROJECT_ROLES)
        weak_person_project = int(conn.execute(
            f"""
            SELECT COUNT(*) FROM entity_relations r
            JOIN entities p ON p.id=r.subject_id AND p.kind='person'
            JOIN entities pr ON pr.id=r.object_id AND pr.kind='project'
            WHERE r.state='current' AND r.predicate='associated_with_project'
              AND NOT EXISTS (
                SELECT 1 FROM relation_evidence re
                JOIN event_entities ee ON ee.event_id=re.event_id AND ee.entity_id=r.subject_id
                WHERE re.relation_id=r.id AND (
                    lower(replace(ee.role,' ','_')) IN ({strong_placeholders})
                    OR lower(ee.role) LIKE '%attendee%' OR lower(ee.role) LIKE '%organizer%'
                    OR lower(ee.role) LIKE '%sender%' OR lower(ee.role) LIKE '%recipient%'
                    OR lower(ee.role) LIKE '%assignee%' OR lower(ee.role) LIKE '%participant%'
                )
              )
            """,
            tuple(sorted(_STRONG_PERSON_PROJECT_ROLES)),
        ).fetchone()[0])
        if weak_person_project:
            problems.append(f"Current person/project associations without structured participant evidence: {weak_person_project}")

        privacy_terms = (
            "feature_prints", "featureprints", "raw_image", "raw camera frame", "rolling_audio",
            "raw microphone", "clipboard_contents", "privacy_zone_coordinates",
        )
        clauses = " OR ".join(["lower(payload_json) LIKE ?"] * len(privacy_terms))
        privacy_hits = int(conn.execute(
            f"SELECT COUNT(*) FROM events WHERE source_kind LIKE 'iphone%' AND ({clauses})",
            tuple(f"%{term}%" for term in privacy_terms),
        ).fetchone()[0])
        if privacy_hits:
            problems.append(f"Potential prohibited raw iPhone payloads in world events: {privacy_hits}")

        stale_revoked_identity = int(conn.execute(
            """
            SELECT COUNT(DISTINCT b.subject_id) FROM beliefs b
            JOIN external_ids x ON x.entity_id=b.subject_id AND x.namespace='iphone_known_person'
            WHERE b.predicate='known_person_enrollment' AND b.state='current' AND b.value_json='\"revoked\"'
            """
        ).fetchone()[0])
        if stale_revoked_identity:
            problems.append(f"Revoked Known People entities still bound to iPhone enrollment IDs: {stale_revoked_identity}")

        revoked_alias_leaks = int(conn.execute(
            """
            SELECT COUNT(DISTINCT b.subject_id) FROM beliefs b
            JOIN aliases a ON a.entity_id=b.subject_id AND a.source='iphone_known_person'
            WHERE b.predicate='known_person_enrollment' AND b.state='current' AND b.value_json='\"revoked\"'
            """
        ).fetchone()[0])
        if revoked_alias_leaks:
            problems.append(f"Revoked Known People entities still expose enrollment aliases: {revoked_alias_leaks}")

        tombstone_relation_leaks = int(conn.execute(
            """
            SELECT COUNT(*) FROM entity_relations r
            JOIN entities e ON (e.id=r.subject_id OR e.id=r.object_id)
            WHERE r.state='current' AND e.normalized_name LIKE 'former enrolled person %'
            """
        ).fetchone()[0])
        if tombstone_relation_leaks:
            problems.append(f"Current graph relations still reference tombstoned Known People identities: {tombstone_relation_leaks}")

        duplicate_current_decisions = len(conn.execute(
            "SELECT intention_id FROM executive_decisions WHERE status='current' GROUP BY intention_id HAVING COUNT(*)>1"
        ).fetchall())
        if duplicate_current_decisions:
            problems.append(f"Intentions with multiple current Executive decisions: {duplicate_current_decisions}")

        term_same_value_conflicts = int(conn.execute(
            """
            SELECT COUNT(*) FROM term_conflicts c
            JOIN term_observations a ON a.id=c.older_observation_id
            JOIN term_observations b ON b.id=c.newer_observation_id
            WHERE a.normalized_value=b.normalized_value
            """
        ).fetchone()[0])
        if term_same_value_conflicts:
            problems.append(f"Term conflicts whose normalized values are identical: {term_same_value_conflicts}")

        term_conflicts_without_event = int(conn.execute(
            """
            SELECT COUNT(*) FROM term_conflicts c LEFT JOIN events e ON e.id=c.conflict_event_id
            WHERE c.conflict_event_id IS NULL OR e.event_type!='term.changed_or_conflicted'
            """
        ).fetchone()[0])
        if term_conflicts_without_event:
            problems.append(f"Term conflicts without term.changed_or_conflicted evidence events: {term_conflicts_without_event}")

        reversed_term_conflicts = 0
        term_time_rows = conn.execute(
            """
            SELECT older.occurred_at AS older_at,newer.occurred_at AS newer_at
            FROM term_conflicts c
            JOIN term_observations older ON older.id=c.older_observation_id
            JOIN term_observations newer ON newer.id=c.newer_observation_id
            """
        ).fetchall()
        for row in term_time_rows:
            older_at = _parse_time(str(row["older_at"] or ""))
            newer_at = _parse_time(str(row["newer_at"] or ""))
            if older_at is not None and newer_at is not None and older_at > newer_at:
                reversed_term_conflicts += 1
        if reversed_term_conflicts:
            problems.append(f"Term conflict pairs reversed relative to source chronology: {reversed_term_conflicts}")

        document_pairs_without_event = int(conn.execute(
            """
            SELECT COUNT(*) FROM document_version_pairs p LEFT JOIN events e ON e.id=p.comparison_event_id
            WHERE p.comparison_event_id IS NULL OR e.event_type NOT IN ('document.version_changed','document.version_equivalent')
            """
        ).fetchone()[0])
        if document_pairs_without_event:
            problems.append(f"Document version pairs without valid comparison events: {document_pairs_without_event}")

        reversed_document_pairs = 0
        document_time_rows = conn.execute(
            """
            SELECT older.occurred_at AS older_at,newer.occurred_at AS newer_at
            FROM document_version_pairs p
            JOIN events older ON older.id=p.older_event_id
            JOIN events newer ON newer.id=p.newer_event_id
            """
        ).fetchall()
        for row in document_time_rows:
            older_at = _parse_time(str(row["older_at"] or ""))
            newer_at = _parse_time(str(row["newer_at"] or ""))
            if older_at is not None and newer_at is not None and older_at > newer_at:
                reversed_document_pairs += 1
        if reversed_document_pairs:
            problems.append(f"Document version pairs reversed relative to source chronology: {reversed_document_pairs}")

        disputed = int(conn.execute("SELECT COUNT(*) FROM beliefs WHERE state='disputed'").fetchone()[0])
        if disputed:
            warnings.append(f"There are {disputed} disputed belief(s); this is allowed but should remain visible to reasoning.")

        valid_verification_states = ("pending", "verified", "failed", "timed_out", "unverified", "superseded")
        placeholders = ",".join("?" for _ in valid_verification_states)
        invalid_verification_states = int(conn.execute(
            f"SELECT COUNT(*) FROM action_verifications WHERE status NOT IN ({placeholders})",
            valid_verification_states,
        ).fetchone()[0])
        if invalid_verification_states:
            problems.append(f"Action verifications with invalid states: {invalid_verification_states}")

        verified_without_event = int(conn.execute(
            """
            SELECT COUNT(*) FROM action_verifications v LEFT JOIN events e ON e.id=v.resolved_event_id
            WHERE v.status='verified' AND (v.resolved_event_id IS NULL OR e.event_type!='verification.verified')
            """
        ).fetchone()[0])
        if verified_without_event:
            problems.append(f"Verified action outcomes without verification.verified evidence events: {verified_without_event}")

        now_iso = datetime.now().astimezone().isoformat()
        overdue_verifications = int(conn.execute(
            "SELECT COUNT(*) FROM action_verifications WHERE status='pending' AND deadline_at IS NOT NULL AND deadline_at<=?",
            (now_iso,),
        ).fetchone()[0])
        if overdue_verifications:
            warnings.append(f"There are {overdue_verifications} pending action verification(s) past deadline; the verifier loop should resolve them on its next pass.")

        unverifiable = int(conn.execute("SELECT COUNT(*) FROM action_verifications WHERE status='unverified'").fetchone()[0])
        if unverifiable:
            warnings.append(f"There are {unverifiable} action outcome(s) explicitly marked unverified; Jarvis must not infer success for them.")

    try:
        from jarvis_mrb.tool_audit import status as audit_status
        audit: dict[str, Any] = audit_status()
        if not bool(audit.get("installed")):
            warnings.append("Backend tool audit wrapper is not installed in this diagnostic process.")
    except Exception as exc:
        audit = {"installed": False, "error": str(exc)[:300]}
        warnings.append("Backend tool audit status could not be read.")

    degraded_subsystems = [
        item for item in runtime.get("subsystems", [])
        if str(item.get("status")) != "ok" and int(item.get("consecutive_failures") or 0) > 0
    ]
    for item in degraded_subsystems:
        warnings.append(
            f"Runtime subsystem {item.get('subsystem')} has {item.get('consecutive_failures')} consecutive failure(s): {item.get('last_error')}"
        )

    path = Path(DB_PATH)
    database_bytes = path.stat().st_size if path.exists() else 0
    if database_bytes > 500 * 1024 * 1024:
        warnings.append(f"World database is {database_bytes / (1024 * 1024):.1f} MiB; review retention/content storage before it grows further.")

    return {
        "ok": not problems,
        "integrity": integrity,
        "journal_mode": journal_mode,
        "foreign_key_violations": len(fk_rows),
        "database_bytes": database_bytes,
        "schema_migrations": migrations,
        "migration_history_contiguous": migration_history == expected_history,
        "missing_required_tables": missing_tables,
        "agency_required": bool(require_agency),
        "core": core,
        "linker": linker,
        "executive": executive,
        "executive_loop": executive_loop,
        "relevance": relevance,
        "situation": situation,
        "prebrief": prebrief,
        "terms": terms,
        "documents": documents,
        "verification": verification,
        "gmail_attachments": attachments,
        "runtime_health": runtime,
        "tool_audit": audit,
        "linker_lag_events": linker_lag,
        "goal_intention_mismatches": goal_mismatches,
        "stale_intention_commitment_links": stale_links,
        "relations_without_evidence": relation_without_evidence,
        "relation_evidence_count_mismatches": relation_count_mismatches,
        "weak_person_project_relations": weak_person_project,
        "privacy_boundary_hits": privacy_hits,
        "revoked_known_people_with_stale_ids": stale_revoked_identity,
        "revoked_known_people_with_alias_leaks": revoked_alias_leaks,
        "tombstone_relation_leaks": tombstone_relation_leaks,
        "duplicate_current_executive_decisions": duplicate_current_decisions,
        "same_value_term_conflicts": term_same_value_conflicts,
        "term_conflicts_without_events": term_conflicts_without_event,
        "reversed_term_conflicts": reversed_term_conflicts,
        "document_pairs_without_comparison_events": document_pairs_without_event,
        "reversed_document_pairs": reversed_document_pairs,
        "invalid_verification_states": invalid_verification_states,
        "verified_outcomes_without_evidence_events": verified_without_event,
        "pending_verifications_past_deadline": overdue_verifications,
        "unverified_outcomes": unverifiable,
        "agency": agency_metrics,
        "attachment_backlog_remaining": bool(attachments.get("backlog_remaining")),
        "attachment_last_status": attachment_state,
        "degraded_subsystems": len(degraded_subsystems),
        "problems": problems,
        "warnings": warnings,
    }
