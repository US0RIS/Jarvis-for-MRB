"""Read back why Jarvis emitted its latest proactive notification.

Read-only. A published companion-bus notification is not proof that an iPhone
displayed it, AirPods played it, or the user noticed it. Where the emitter did
not attach a known origin, report 'unknown' rather than inventing an explanation.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from jarvis_mrb import world_model
from jarvis_mrb.event_bus import PROACTIVE_ORIGINS


def latest_receipt(db_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else Path(world_model.DB_PATH)
    if not path.is_file():
        return {"ok": False, "message": "No persisted proactive alert history is available."}
    try:
        with sqlite3.connect(path, timeout=3.0) as conn:
            row = conn.execute(
                "SELECT summary, occurred_at, payload_json, source_kind "
                "FROM events WHERE event_type='attention.proactive' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except sqlite3.Error:
        return {"ok": False, "message": "Proactive alert history could not be read."}
    if not row:
        return {"ok": False, "message": "No proactive alert has a saved receipt."}
    summary, occurred, payload, source_kind = row
    try:
        details = json.loads(payload or "{}")
    except (TypeError, json.JSONDecodeError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    origin = str(details.get("origin") or "unknown")
    if origin not in PROACTIVE_ORIGINS:
        origin = "unknown"
    severity = str(details.get("severity") or "unknown")[:40]
    return {
        "ok": True,
        "message": str(summary or "")[:400],
        "emitted_at": str(occurred or ""),
        "severity": severity,
        "origin": origin,
        "origin_description": PROACTIVE_ORIGINS[origin],
        "provenance": str(source_kind or "unknown"),
        "scope": "last recorded event published to companion bus, not confirmed delivery",
        "has_independent_source_receipt": False,
    }


def describe_latest(db_path: Path | str | None = None) -> str:
    receipt = latest_receipt(db_path)
    if not receipt["ok"]:
        return receipt["message"]
    cause = receipt["origin_description"]
    if receipt["origin"] == "unknown":
        cause = "The triggering subsystem was not recorded"
    return (
        f"My most recent recorded proactive alert was: {receipt['message']}. "
        f"Recorded cause: {cause}. It was emitted at {receipt['emitted_at']} "
        f"with severity {receipt['severity']}. "
        "This proves only that Jarvis published an alert internally, "
        "not that you received or heard it."
    )
