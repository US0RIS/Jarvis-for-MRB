from __future__ import annotations

from typing import Any

from jarvis_mrb.world_model import SELF_ID, assert_belief, ingest_frontend_snapshot as ingest_core_snapshot, record_event


def ingest_frontend_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Merge bounded iPhone metadata into the common PC world graph.

    The iPhone contract deliberately excludes biometric feature prints, raw camera
    frames, raw microphone buffers, incident media, clipboard contents and privacy
    zone coordinates. This function must not attempt to reconstruct or request those
    excluded channels.
    """
    data = dict(snapshot or {})
    counts: dict[str, Any] = ingest_core_snapshot(data)
    counts.setdefault("events", 0)
    counts.setdefault("receipts", 0)
    counts.setdefault("mode", 0)

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
