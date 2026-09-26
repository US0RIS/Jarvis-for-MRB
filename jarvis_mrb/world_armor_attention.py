from __future__ import annotations

"""Evidence-based World Armor attention inbox. No push or outbound delivery.

Only opt-in watch samples from the fixed real adapters can create notices.
A publisher report is not evidence of verified physical onset, safe conditions,
an independently confirmed incident, or permission for any external action.
"""

from contextlib import closing
from datetime import datetime, timedelta
import math
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from jarvis_mrb.world_armor_phase1 import (
    STORE, _clock, _connect, _identifier, _timestamp,
    compare_recent,
)

KINDS = (
    "off", "modelled_aqi_threshold_crossed",
    "new_usgs_report", "new_nws_alert",
)
_MAX_NOTICES = 100


def validate_rule(kind: str, threshold: float | None,
                  cooldown_minutes: int) -> tuple[str, float | None, int]:
    if kind not in KINDS or not isinstance(kind, str):
        raise ValueError("Choose one supported, typed attention rule.")
    if type(cooldown_minutes) is not int or not 30 <= cooldown_minutes <= 360:
        raise ValueError("Attention cooldown must be 30–360 whole minutes.")
    if kind == "off" or kind == "new_nws_alert":
        if threshold is not None:
            raise ValueError("This attention rule has no numeric threshold.")
        return kind, None, cooldown_minutes
    if type(threshold) not in (int, float) or not math.isfinite(threshold):
        raise ValueError("A finite source-specific threshold is required.")
    if kind == "modelled_aqi_threshold_crossed" and not 50 <= threshold <= 300:
        raise ValueError("Modelled AQI threshold must be 50–300.")
    if kind == "new_usgs_report" and not 2.5 <= threshold <= 8.0:
        raise ValueError("USGS reported magnitude threshold must be 2.5–8.0.")
    return kind, round(float(threshold), 1), cooldown_minutes


def _candidate(row: sqlite3.Row, changes: dict[str, Any],
               instant: datetime, sample_id: str) -> dict[str, Any] | None:
    kind = row["attention_kind"]
    source = {
        "modelled_aqi_threshold_crossed": "openmeteo_model",
        "new_usgs_report": "usgs_earthquakes",
        "new_nws_alert": "nws_point_alerts",
    }.get(kind)
    if (source is None or changes.get("comparison") != "two_received_samples"
            or changes.get("latest_mode") != "real_adapter"
            or changes.get("previous_mode") != "real_adapter"
            or source not in changes.get("sources_with_comparable_coverage", [])):
        return None
    if changes.get("latest_received_at") is None:
        return None
    if kind == "modelled_aqi_threshold_crossed":
        movement = changes.get("modelled_air_quality_change")
        if not movement:
            return None
        threshold = row["attention_threshold"]
        if not movement["before"] < threshold <= movement["after"]:
            return None
        source_at = _timestamp(movement.get("after_model_at"))
        if (source_at is None
                or not timedelta(0) <=
                instant - datetime.fromisoformat(source_at) <= timedelta(hours=6)):
            return None
        return {
            "source": source,
            "kind": kind,
            "source_key": "aqi_crossing:" + sample_id,
            "observed_at": source_at,
            "observation_id": movement["observation_id"],
            "summary": (
                "Modelled US AQI crossed the configured "
                f"{threshold:g} threshold: {movement['before']:g} to "
                f"{movement['after']:g}. Coarse model, not a street sensor."
            ),
        }
    candidates = []
    for item in changes.get("source_record_changes", []):
        if (item["source"] != source
                or item["kind"] != "newly_received_record_not_newly_occurred_event"):
            continue
        values = item.get("after") or {}
        if kind == "new_usgs_report":
            magnitude = values.get("magnitude")
            source_at = _timestamp(item.get("observed_at"))
            if (type(magnitude) not in (int, float)
                    or not math.isfinite(magnitude)
                    or magnitude < row["attention_threshold"]
                    or source_at is None
                    or not timedelta(0) <=
                    instant - datetime.fromisoformat(source_at) <= timedelta(hours=24)):
                continue
            summary = (
                f"Newly received USGS M{magnitude:g} report. "
                "First received is not proof of earthquake onset."
            )
        else:
            source_at = None  # The source adapter lacks NWS issue time.
            event = str(values.get("event") or "weather alert")[:120]
            summary = (
                "Newly received NWS point alert: " + event +
                ". Issue time and precise alert footprint not retained."
            )
        candidates.append({
            "source": source, "kind": kind,
            "source_key": str(item["record_key"])[:300],
            "observed_at": source_at,
            "observation_id": item["observation_id"],
            "summary": summary,
            "magnitude": values.get("magnitude", 0)
                if kind == "new_usgs_report" else 0,
        })
    # At most one notice per watch collection; deterministic strongest report.
    candidates.sort(key=lambda x: (-x["magnitude"], x["source_key"]))
    return candidates[0] if candidates else None


def publish_after_watch_sample(
    con: sqlite3.Connection, watch: sqlite3.Row, *, sample_id: str,
    received_at: str, instant: datetime, changes: dict[str, Any] | None,
) -> dict[str, Any]:
    """Call inside the *same write transaction* as watch completion.

    No separate permission/runner exists: the parent watch row is checked
    under its active lease before the caller enters this function.
    """
    if watch["attention_kind"] == "off":
        return {"notices_created": 0, "attention_state": "not_enrolled"}
    # A region can already have foreground or other-watch samples. The
    # operator's first sample from THIS enrolled watch must still baseline.
    if not con.execute(
        "SELECT 1 FROM watch_receipts WHERE watch_id=? LIMIT 1",
        (watch["id"],),
    ).fetchone():
        return {"notices_created": 0, "attention_state": "watch_baseline"}
    if (changes is None
            or changes.get("latest_received_at") != received_at):
        return {"notices_created": 0, "attention_state": "no_comparable_baseline"}
    candidate = _candidate(watch, changes, instant, sample_id)
    if candidate is None:
        return {"notices_created": 0, "attention_state": "predicate_not_verified"}
    if watch["last_notice_at"]:
        last = datetime.fromisoformat(watch["last_notice_at"])
        if instant - last < timedelta(minutes=watch["attention_cooldown_minutes"]):
            return {"notices_created": 0, "attention_state": "cooldown_suppressed"}
    result = con.execute(
        "INSERT OR IGNORE INTO armor_notices"
        "(id,watch_id,investigation_id,sample_id,source,kind,source_key,"
        "observed_at,received_at,created_at,summary,observation_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (uuid4().hex, watch["id"], watch["investigation_id"], sample_id,
         candidate["source"], candidate["kind"], candidate["source_key"],
         candidate["observed_at"], received_at, instant.isoformat(),
         candidate["summary"], candidate["observation_id"]),
    )
    if result.rowcount == 0:
        return {"notices_created": 0, "attention_state": "duplicate_report"}
    con.execute(
        "UPDATE watches SET last_notice_at=? WHERE id=?",
        (instant.isoformat(), watch["id"]),
    )
    return {"notices_created": 1, "attention_state": "inbox_notice_saved"}


def inspect_sample(
    investigation_id: str, received_at: str, *,
    db_path: Path, now: datetime,
) -> dict[str, Any] | None:
    try:
        changes = compare_recent(investigation_id, db_path=db_path, now=now)
    except (KeyError, ValueError, sqlite3.Error):
        return None
    if changes.get("latest_received_at") != received_at:
        return None
    return changes


def list_notices(*, investigation_id: str | None = None,
                 watch_id: str | None = None,
                 unread_only: bool = False,
                 db_path: Path | None = None,
                 now: datetime | None = None) -> dict[str, Any]:
    """Reads stay available after feature flags OFF so history is deletable."""
    if type(unread_only) is not bool:
        raise ValueError("unread_only must be Boolean.")
    path = Path(db_path) if db_path is not None else STORE
    if not path.is_file():
        return {"notices": [], "unread_count": 0,
                "delivery": "private_inbox_only_no_remote_push"}
    if investigation_id is not None:
        _identifier(investigation_id)
    if watch_id is not None:
        _identifier(watch_id)
    instant = _clock(now)
    where = ["i.expires_at>?"]
    params: list[Any] = [instant.isoformat()]
    if investigation_id is not None:
        where.append("n.investigation_id=?")
        params.append(investigation_id)
    if watch_id is not None:
        where.append("n.watch_id=?")
        params.append(watch_id)
    scope = " AND ".join(where)
    with closing(_connect(path, create=True)) as con:
        unread = con.execute(
            "SELECT COUNT(*) FROM armor_notices n "
            "JOIN investigations i ON i.id=n.investigation_id "
            f"WHERE {scope} AND n.read_at IS NULL",
            tuple(params),
        ).fetchone()[0]
        query = (
            "SELECT n.* FROM armor_notices n "
            "JOIN investigations i ON i.id=n.investigation_id "
            f"WHERE {scope}"
        )
        if unread_only:
            query += " AND n.read_at IS NULL"
        query += " ORDER BY n.created_at DESC,n.id DESC LIMIT ?"
        rows = con.execute(query, tuple(params + [_MAX_NOTICES])).fetchall()
    return {"notices": [dict(r) for r in rows],
            "unread_count": unread,
            "delivery": "private_inbox_only_no_remote_push",
            "truncated": len(rows) >= _MAX_NOTICES}


def mark_read(notice_id: str, *, db_path: Path | None = None,
              now: datetime | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else STORE
    if not path.is_file():
        raise KeyError("Notice not found.")
    instant = _clock(now)
    with closing(_connect(path, create=True)) as con, con:
        row = con.execute(
            "SELECT n.* FROM armor_notices n "
            "JOIN investigations i ON i.id=n.investigation_id "
            "WHERE n.id=? AND i.expires_at>?",
            (_identifier(notice_id), instant.isoformat()),
        ).fetchone()
        if row is None:
            raise KeyError("Notice not found.")
        con.execute(
            "UPDATE armor_notices SET read_at=? WHERE id=? AND read_at IS NULL",
            (instant.isoformat(), notice_id),
        )
        result = con.execute(
            "SELECT * FROM armor_notices WHERE id=?", (notice_id,),
        ).fetchone()
    return dict(result)


def forget_notice(notice_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else STORE
    if not path.is_file():
        return {"deleted": 0}
    with closing(_connect(path, create=True)) as con, con:
        result = con.execute(
            "DELETE FROM armor_notices WHERE id=?", (_identifier(notice_id),),
        )
    return {"deleted": result.rowcount,
            "qualifier": "Only this local notice was forgotten; source receipts remain."}
