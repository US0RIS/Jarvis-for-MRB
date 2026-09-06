from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "spatial_memory.sqlite3"


def _connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS object_sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seen_at TEXT NOT NULL,
            object_name TEXT NOT NULL,
            location_context TEXT NOT NULL,
            scene TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.5
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_object_name ON object_sightings(object_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_object_seen ON object_sightings(id DESC)")
    conn.commit()
    return conn


def _normalize_object(name: str) -> str:
    return " ".join(name.strip().lower().split())[:120]


def remember_object(
    name: str,
    *,
    location_context: str,
    scene: str,
    confidence: float = 0.6,
) -> dict[str, Any]:
    object_name = _normalize_object(name)
    if not object_name:
        raise ValueError("Object name is empty.")
    location = " ".join(location_context.strip().split())[:300] or "unknown location"
    scene_text = " ".join(scene.strip().split())[:1400]
    score = max(0.0, min(float(confidence), 1.0))
    seen_at = datetime.now().astimezone().isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO object_sightings(seen_at,object_name,location_context,scene,confidence) VALUES(?,?,?,?,?)",
            (seen_at, object_name, location, scene_text, score),
        )
        sighting_id = int(cursor.lastrowid)
        conn.execute(
            "DELETE FROM object_sightings WHERE id NOT IN (SELECT id FROM object_sightings ORDER BY id DESC LIMIT 5000)"
        )
        conn.commit()

    # Keep the proven low-latency spatial database for direct "where are my keys?"
    # queries, while mirroring the same observation as a distinct temporal occurrence.
    # No raw image is persisted in either path.
    try:
        from jarvis_mrb.world_linker import link_event
        from jarvis_mrb.world_occurrence import record_visual_occurrence

        event_id = record_visual_occurrence(
            scene_text,
            [object_name],
            location_context=location,
            confidence=score,
            occurred_at=seen_at,
            occurrence_ref=f"spatial:{sighting_id}:{seen_at}",
        )
        link_event(event_id)
    except Exception:
        pass

    return {
        "id": sighting_id,
        "object": object_name,
        "location": location,
        "scene": scene_text,
        "confidence": score,
        "seen_at": seen_at,
    }


def find_object(name: str, limit: int = 3) -> list[dict[str, Any]]:
    target = _normalize_object(name)
    if not target:
        return []
    safe_limit = max(1, min(int(limit), 10))
    terms = [term for term in target.split() if len(term) >= 2]
    if not terms:
        terms = [target]
    clauses = " OR ".join("object_name LIKE ?" for _ in terms)
    params = [f"%{term}%" for term in terms]
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM object_sightings WHERE {clauses} ORDER BY id DESC LIMIT ?",
            (*params, safe_limit),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "object": str(row["object_name"]),
            "location": str(row["location_context"]),
            "scene": str(row["scene"]),
            "confidence": float(row["confidence"]),
            "seen_at": str(row["seen_at"]),
        }
        for row in rows
    ]


def describe_last_seen(name: str) -> str:
    matches = find_object(name, limit=1)
    if not matches:
        return f"I don't have a recorded sighting of {name.strip() or 'that object'} yet."
    item = matches[0]
    location = item["location"]
    scene = item["scene"]
    return f"I last saw {item['object']} at {location}. The scene was: {scene}"


def status() -> dict[str, Any]:
    with _connect() as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM object_sightings").fetchone()[0])
    return {"sightings": count, "database": str(DB_PATH), "world_model_mirroring": True}
