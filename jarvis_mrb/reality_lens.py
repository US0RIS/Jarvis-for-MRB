from __future__ import annotations

"""Reality Lens v1: an opt-in, source-qualified memory of real-world observations.

A user explicitly resolves a place on iPhone, senses integrated public sources,
and may choose to remember a small numeric snapshot. Subsequent observations
compare like-for-like, still-fresh provider values without an LLM or raw media.
This is NOT a persistent camera archive or a background location tracker.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from jarvis_mrb.reality_graph import build_place_graph
from jarvis_mrb.world_model import DB_PATH

STORE = Path(DB_PATH).with_name("reality_lens.sqlite3")
RETENTION_DAYS = 30
MAX_SNAPSHOTS = 120
# Limit reality comparison to explicitly understood scalar provider fields.
FIELDS = (
    ("fact:air_quality", "Modelled US AQI"),
    ("fact:active_weather_alert_count", "NWS point alert count"),
    ("fact:regional_earthquake_count", "USGS regional event count"),
    ("fact:nearby_facility_count", "Mapped public facility count"),
)


def _clock(now: datetime | None = None) -> datetime:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Reality Lens needs an aware timestamp.")
    return instant.astimezone(timezone.utc)


def _coordinates(latitude: float, longitude: float) -> str:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid place coordinates.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Place coordinates are outside valid bounds.")
    # Coordinates are never stored: matching uses a local, deterministic digest.
    text = f"{lat:.5f},{lon:.5f}".encode("ascii")
    return hashlib.sha256(text).hexdigest()


def _label(value: str) -> str:
    label = " ".join(str(value or "").split())
    if not 1 <= len(label) <= 120 or any(ord(ch) < 32 for ch in label):
        raise ValueError("An explicit place label (1-120 characters) is required.")
    return label


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=8.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=8000")
    con.execute("PRAGMA secure_delete=ON")
    con.execute(
        """CREATE TABLE IF NOT EXISTS snapshots (
             id TEXT PRIMARY KEY, place_key TEXT NOT NULL,
             place_label TEXT NOT NULL, captured_at TEXT NOT NULL,
             metrics_json TEXT NOT NULL
           )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS lens_place_time ON snapshots(place_key,captured_at)")
    return con


def _current_facts(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = {
        str(row.get("id")): row
        for row in graph.get("evidence", [])
        if isinstance(row, dict)
    }
    facts = {
        str(row.get("id")): row
        for row in graph.get("derived_facts", [])
        if isinstance(row, dict)
    }
    output: dict[str, dict[str, Any]] = {}
    for fact_id, label in FIELDS:
        row = facts.get(fact_id)
        if not row or isinstance(row.get("value"), bool) or not isinstance(row.get("value"), (int, float)):
            continue
        value = row["value"]
        if not math.isfinite(value) or value < 0:
            continue
        ids = row.get("evidence_ids")
        if not isinstance(ids, (list, tuple)) or not ids or not all(
            i in evidence and evidence[i].get("freshness") == "fresh" for i in ids
        ):
            continue
        providers = {str(evidence[i].get("source") or "") for i in ids}
        if len(providers) != 1:
            continue
        ev = evidence[ids[0]]
        output[fact_id] = {
            "id": fact_id, "label": label, "value": value,
            "source": providers.pop(), "observed_at": str(ev.get("observed_at") or ""),
            "qualifier": "Model output, not a local sensor." if fact_id == "fact:air_quality"
                         else "Provider-bounded count, not a safety clearance.",
        }
    return output


def _baseline(path: Path, key: str, cutoff: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    con = _connect(path)
    try:
        con.execute("DELETE FROM snapshots WHERE captured_at<?", (cutoff,))
        con.commit()
        row = con.execute(
            """SELECT id,place_label,captured_at,metrics_json FROM snapshots
               WHERE place_key=? AND captured_at>=?
               ORDER BY captured_at DESC,rowid DESC LIMIT 1""",
            (key, cutoff),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "label": row["place_label"],
            "captured_at": row["captured_at"],
            "metrics": json.loads(row["metrics_json"]),
        }
    finally:
        con.close()


def _remember(path: Path, key: str, label: str, stamp: str,
              metrics: dict[str, dict[str, Any]], cutoff: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM snapshots WHERE captured_at<?", (cutoff,))
        ident = uuid4().hex
        con.execute(
            "INSERT INTO snapshots(id,place_key,place_label,captured_at,metrics_json) VALUES(?,?,?,?,?)",
            (ident, key, label, stamp, json.dumps(metrics, sort_keys=True, separators=(",", ":"))),
        )
        con.execute(
            """DELETE FROM snapshots WHERE id IN (
                 SELECT id FROM snapshots ORDER BY captured_at DESC,rowid DESC
                 LIMIT -1 OFFSET ?)""",
            (MAX_SNAPSHOTS,),
        )
        con.commit()
        return ident
    finally:
        con.close()


def sense_place(
    latitude: float, longitude: float, label: str, *,
    remember: bool = False,
    observation: dict[str, Any] | None = None,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One intentional observation; only `remember=True` persists selected facts.

    A former snapshot's values are historical, not "still fresh" at query time.
    A new value is compared only if it has fresh supporting evidence NOW and
    originates from the same supported provider. Unknown values never become 0.
    """
    key = _coordinates(latitude, longitude)
    name = _label(label)
    clock = _clock(now)
    path = Path(db_path) if db_path is not None else STORE
    cutoff = (clock - timedelta(days=RETENTION_DAYS)).isoformat()
    before = _baseline(path, key, cutoff)
    graph = build_place_graph(latitude, longitude, observation)
    current = _current_facts(graph)
    changes: list[dict[str, Any]] = []
    if before:
        for fact_id, new in current.items():
            old = before["metrics"].get(fact_id)
            if not isinstance(old, dict) or old.get("source") != new["source"]:
                continue
            old_value = old.get("value")
            if type(old_value) not in (int, float) or not math.isfinite(old_value):
                continue
            if old_value != new["value"]:
                changes.append({
                    "id": fact_id, "label": new["label"], "before": old_value,
                    "after": new["value"], "source": new["source"],
                    "previous_observed_at": old.get("observed_at", ""),
                    "observed_at": new["observed_at"],
                    "qualifier": new["qualifier"],
                })
    changes.sort(key=lambda row: row["id"])
    stored_id = (
        _remember(path, key, name, clock.isoformat(), current, cutoff)
        if remember else None
    )
    return {
        "schema": "jarvis.reality_lens.v1",
        "place_label": name,
        "checked_at": clock.isoformat(),
        "model_calls": 0,
        "action_authority": "none",
        "remembered": stored_id is not None,
        "memory_id": stored_id,
        "baseline_at": before["captured_at"] if before else None,
        "baseline_available": before is not None,
        "observations": list(current.values()),
        "changes": changes,
        "unknown_metrics": [label for fid, label in FIELDS if fid not in current],
        "provider_states": graph.get("provider_states", {}),
        # Haptics are ONLY requested by a conscious tap in the foreground app.
        # Neither counts nor AQI alone authorize autonomous safety alerts.
        "suggested_haptic_pulses": min(3, 1 + len(changes)) if changes else 0,
        "retention_days": RETENTION_DAYS,
    }


def list_memories(*, db_path: Path | None = None,
                  now: datetime | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else STORE
    cutoff = (_clock(now) - timedelta(days=RETENTION_DAYS)).isoformat()
    rows: list[dict[str, Any]] = []
    if path.is_file():
        con = _connect(path)
        try:
            con.execute("DELETE FROM snapshots WHERE captured_at<?", (cutoff,))
            con.commit()
            result = con.execute(
                """SELECT id,place_label,captured_at,metrics_json FROM snapshots
                   WHERE captured_at>=? ORDER BY captured_at DESC,rowid DESC LIMIT 30""",
                (cutoff,),
            ).fetchall()
            rows = [
                {
                    "id": row["id"], "label": row["place_label"],
                    "captured_at": row["captured_at"],
                    "fact_count": len(json.loads(row["metrics_json"])),
                }
                for row in result
            ]
        finally:
            con.close()
    return {"schema": "jarvis.reality_lens.memory.v1",
            "memories": rows, "retention_days": RETENTION_DAYS}


def forget_place(latitude: float, longitude: float, *,
                 db_path: Path | None = None) -> dict[str, Any]:
    key = _coordinates(latitude, longitude)
    path = Path(db_path) if db_path is not None else STORE
    if not path.is_file():
        return {"deleted": 0}
    con = _connect(path)
    try:
        cursor = con.execute("DELETE FROM snapshots WHERE place_key=?", (key,))
        con.commit()
        return {"deleted": cursor.rowcount}
    finally:
        con.close()
