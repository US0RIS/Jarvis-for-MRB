from __future__ import annotations

from typing import Any

from jarvis_mrb.world_model import (
    SELF_ID,
    assert_belief,
    ensure_entity,
    ingest_frontend_snapshot as ingest_core_snapshot,
    record_event,
)


def ingest_frontend_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Merge bounded iPhone metadata into the common PC world graph.

    The iPhone contract deliberately excludes biometric feature prints, raw camera
    frames, raw microphone buffers, incident media, clipboard contents and privacy
    zone coordinates. Advisory current-person presence may cross this bridge only as
    enrolled-person ID/name/time metadata; the biometric comparison itself stays on
    device and never becomes a durable identity belief.
    """
    data = dict(snapshot or {})
    counts: dict[str, Any] = ingest_core_snapshot(data)
    counts.setdefault("events", 0)
    counts.setdefault("receipts", 0)
    counts.setdefault("mode", 0)
    counts.setdefault("current_person_presence", 0)

    # Goal Manager, Waiting-On and Known People enrollment are authoritative full
    # collections only when each collection is present and valid. Missing/malformed
    # collections are partial snapshots and cannot retire anything.
    try:
        from jarvis_mrb.world_snapshot_reconcile import reconcile_authoritative_snapshot

        counts["reconcile"] = reconcile_authoritative_snapshot(data)
    except Exception as exc:
        counts["reconcile"] = {"error": str(exc)[:300]}

    mode = " ".join(str(data.get("mode") or "").split())[:120]
    if mode:
        event_id = record_event(
            "context.conversation_mode",
            f"iPhone Jarvis mode: {mode}",
            source_kind="iphone_mode",
            source_ref=mode.lower(),
            payload={"mode": mode},
            evidence="Explicit frontend conversation/privacy mode metadata.",
            confidence=1.0,
            participants=[(SELF_ID, "user", 1.0)],
        )
        assert_belief(
            SELF_ID,
            "conversation_mode",
            value=mode,
            confidence=1.0,
            source_event_id=event_id,
            evidence="Current iPhone Jarvis mode",
        )
        counts["mode"] = 1

    # Known People matching is closed-set and advisory. A fresh match is useful
    # situational context, but it is deliberately represented as an expiring temporal
    # observation rather than `currently_with`/identity state that could outlive the
    # camera evidence. No distance, threshold, feature print or image is accepted.
    presence = data.get("presence")
    current_person = presence.get("current_person") if isinstance(presence, dict) else None
    if isinstance(current_person, dict):
        person_id = str(current_person.get("person_id") or "").strip()[:200]
        person_name = " ".join(str(current_person.get("name") or "").split())[:300]
        matched_at = str(current_person.get("matched_at") or "").strip()[:100]
        advisory = current_person.get("advisory") is True
        forbidden = {"distance", "threshold", "feature_print", "feature_prints", "image", "raw_image"}
        if person_id and person_name and matched_at and advisory and not (forbidden & set(current_person)):
            entity_id = ensure_entity(
                "person",
                person_name,
                external_namespace="iphone_known_person",
                external_id=person_id,
                confidence=0.85,
            )
            # Bucket duplicate fresh observations to one event per minute per person.
            # The timestamp remains in the payload/evidence while the explicit event
            # key prevents a continuously visible face from generating thousands of
            # nearly identical world events.
            minute_bucket = matched_at[:16]
            record_event(
                "person.present_observed",
                f"iPhone advisory presence match: {person_name}",
                source_kind="iphone_known_person_presence",
                source_ref=f"{person_id}:{minute_bucket}",
                occurred_at=matched_at,
                payload={
                    "person_id": person_id,
                    "name": person_name,
                    "matched_at": matched_at,
                    "advisory": True,
                    "expires_after_seconds": 12,
                },
                evidence=(
                    "Fresh closed-set Known People match produced on iPhone. Advisory only; "
                    "no biometric feature data, match distance, threshold or image copied."
                ),
                confidence=0.75,
                participants=[(SELF_ID, "observer", 1.0), (entity_id, "present_person", 0.75)],
                event_key=f"iphone-known-person-presence:{person_id}:{minute_bucket}",
            )
            counts["current_person_presence"] = 1

    raw_events = data.get("events")
    for item in raw_events if isinstance(raw_events, list) else []:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("id") or "").strip()
        title = " ".join(str(item.get("title") or "").split())[:500]
        detail = " ".join(str(item.get("detail") or "").split())[:3000]
        kind = " ".join(str(item.get("kind") or "event").split())[:120]
        if not event_id or not (title or detail):
            continue
        raw_confidence = item.get("confidence")
        try:
            confidence = max(0.0, min(float(raw_confidence), 1.0)) if raw_confidence is not None else 1.0
        except (TypeError, ValueError):
            confidence = 1.0
        record_event(
            f"frontend.{kind}",
            (title + (f": {detail}" if detail else ""))[:3000],
            source_kind="iphone_power_event",
            source_ref=event_id,
            occurred_at=str(item.get("timestamp") or "") or None,
            payload={"kind": kind, "title": title, "detail": detail},
            evidence="Bounded event emitted by an iPhone-local Jarvis capability.",
            confidence=confidence,
            participants=[(SELF_ID, "related", 1.0)],
        )
        counts["events"] += 1

    raw_receipts = data.get("receipts")
    for item in raw_receipts if isinstance(raw_receipts, list) else []:
        if not isinstance(item, dict):
            continue
        receipt_id = str(item.get("id") or "").strip()
        action = " ".join(str(item.get("action") or "").split())[:500]
        detail = " ".join(str(item.get("detail") or "").split())[:1600]
        if not receipt_id or not action:
            continue
        record_event(
            "action.frontend",
            f"Frontend action: {action}" + (f" — {detail}" if detail else ""),
            source_kind="iphone_action_receipt",
            source_ref=receipt_id,
            occurred_at=str(item.get("timestamp") or "") or None,
            payload={"action": action, "detail": detail},
            evidence="Local iPhone Jarvis action receipt.",
            confidence=1.0,
            participants=[(SELF_ID, "requester", 1.0)],
        )
        counts["receipts"] += 1

    # A phone-side change such as adding a goal or Waiting-On item should become
    # traversable immediately rather than waiting for the 15-minute knowledge-index
    # refresh. The linker is incremental, so this normally processes only these new
    # events and stays cheap enough for the companion path.
    try:
        from jarvis_mrb.world_linker import refresh_links

        counts["linker"] = refresh_links(limit=500)
    except Exception as exc:
        counts["linker"] = {"error": str(exc)[:300]}

    # Explicit goal/Waiting-On mutations should also update Jarvis's persistent
    # executive state immediately. This layer derives intentions only from explicit
    # goals and evidence-backed graph links; ambient observations never silently
    # become goals.
    try:
        from jarvis_mrb.world_executive import refresh_intentions

        counts["executive"] = refresh_intentions()
    except Exception as exc:
        counts["executive"] = {"error": str(exc)[:300]}

    return counts
