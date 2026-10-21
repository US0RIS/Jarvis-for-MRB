from __future__ import annotations

"""One attention budget, dedupe table and delivery ledger for proactive items.

Both voice watches (Feature 7) and meeting briefings (Feature 8) submit
``ProactiveItem`` objects here instead of calling ``emit_proactive`` directly,
so they share one interruption budget, one duplicate guard, one set of
personal preferences and one truthful delivery record.

Truthfulness rules enforced here:

* An item is only *emitted* after authorization, preferences, cooldown and the
  hourly budget all pass; everything else is stored as ``suppressed`` with the
  reason so it can be inspected ("what did you hold back?").
* Delivery states are per transport and never over-claim. ``live_published``
  means the item was handed to N connected companion sessions (not that anyone
  heard it); ``queued`` means rows wait in the durable APNs outbox.

APNs push states, from least to most specific:

* ``queued`` - waiting in the outbox; APNs has not answered yet.
* ``accepted_by_apns`` - APNs answered HTTP 200. This means Apple's service
  accepted the request. It does NOT mean the iPhone received, displayed,
  heard or acted on it.
* ``rejected_by_apns`` - APNs answered with an error reason (for example a
  bad or unregistered device token).
* ``delivery_unknown`` - retries ended without APNs ever answering (network
  or transport failure), or the outbox record disappeared.
* ``device_acknowledged`` - reserved for an explicit device receipt. No device
  acknowledgement channel exists for pushes yet, so no code path sets it.
* ``failed`` - Horus could not enqueue the push at all.
* ``not_configured`` - push disabled, credentials missing or no device.

``confirmed_delivery`` (kept for API compatibility) is true only for
``device_acknowledged``, so it is always false today. ``accepted_by_apns``
is exposed as its own boolean.
"""


import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

import jarvis_mrb.world_model as world_model

_LOCK = threading.RLock()

BUDGET_WINDOW_SECONDS = 3600
RETENTION_DAYS = 30

DEFAULT_PREFS: dict[str, str] = {
    "briefings_enabled": "1",
    "snooze_until": "",
    "quiet_start": "",       # "HH:MM" local; blank = no quiet hours
    "quiet_end": "",
    "hourly_budget": "4",    # max emitted proactive items per rolling hour
    "briefing_threshold": "40",
    "briefing_lead_minutes": "15",
}

# Preferences (disable / snooze / quiet hours) apply to unsolicited briefings.
# A watch the user explicitly asked for is not silenced by them, but still
# counts against the shared hourly budget.
PREF_GATED_KINDS = {"briefing"}


def _utc(value: datetime | None = None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Proactive attention timestamps must be timezone-aware.")
    return instant.astimezone(timezone.utc)


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    folder = world_model.APP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "proactive_attention.sqlite3", timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            dedupe_key TEXT NOT NULL,
            cooldown_key TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            seen_count INTEGER NOT NULL DEFAULT 1,
            decision TEXT NOT NULL,
            suppress_reason TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'info',
            critical INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            rule TEXT NOT NULL DEFAULT '',
            score REAL,
            threshold REAL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL DEFAULT '',
            live_state TEXT NOT NULL DEFAULT '',
            live_clients INTEGER NOT NULL DEFAULT 0,
            live_detail TEXT NOT NULL DEFAULT '',
            push_state TEXT NOT NULL DEFAULT '',
            push_detail TEXT NOT NULL DEFAULT '',
            push_event_id TEXT NOT NULL DEFAULT '',
            push_updated_at TEXT,
            acknowledged_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_items_created ON items(created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_items_suppressed
          ON items(dedupe_key, suppress_reason) WHERE decision='suppressed';
        CREATE TABLE IF NOT EXISTS emitted_keys (
            key TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prefs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    # Earlier builds called an APNs HTTP 200 "sent", which read as delivery.
    conn.execute(
        "UPDATE items SET push_state='accepted_by_apns' WHERE push_state='sent'")
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


# ----------------------------------------------------------------- prefs ---

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def get_prefs(*, now: datetime | None = None) -> dict[str, Any]:
    with _db() as conn:
        stored = {str(r["key"]): str(r["value"]) for r in conn.execute("SELECT key,value FROM prefs")}
    raw = {**DEFAULT_PREFS, **stored}
    instant = _utc(now)
    snooze_until = raw["snooze_until"]
    snoozed = bool(snooze_until) and snooze_until > instant.isoformat()
    return {
        "briefings_enabled": raw["briefings_enabled"] == "1",
        "snooze_until": snooze_until if snoozed else "",
        "snoozed": snoozed,
        "quiet_start": raw["quiet_start"],
        "quiet_end": raw["quiet_end"],
        "hourly_budget": int(raw["hourly_budget"]),
        "briefing_threshold": float(raw["briefing_threshold"]),
        "briefing_lead_minutes": int(raw["briefing_lead_minutes"]),
    }


def set_prefs(**updates: Any) -> dict[str, Any]:
    clean: dict[str, str] = {}
    for key, value in updates.items():
        if key not in DEFAULT_PREFS:
            raise ValueError("Unknown proactive preference: " + key)
        if key == "briefings_enabled":
            clean[key] = "1" if bool(value) else "0"
        elif key == "snooze_until":
            text = "" if value in (None, "") else (
                value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else str(value))
            if text:
                datetime.fromisoformat(text)  # raises on garbage
            clean[key] = text
        elif key in {"quiet_start", "quiet_end"}:
            text = "" if value in (None, "") else str(value)
            if text and not _HHMM.fullmatch(text):
                raise ValueError(key + " must be HH:MM (24-hour).")
            clean[key] = text
        elif key == "hourly_budget":
            number = int(value)
            if not 1 <= number <= 60:
                raise ValueError("hourly_budget must be 1-60.")
            clean[key] = str(number)
        elif key == "briefing_threshold":
            number = float(value)
            if not 0 <= number <= 100:
                raise ValueError("briefing_threshold must be 0-100.")
            clean[key] = str(number)
        elif key == "briefing_lead_minutes":
            number = int(value)
            if not 5 <= number <= 60:
                raise ValueError("briefing_lead_minutes must be 5-60.")
            clean[key] = str(number)
    if ("quiet_start" in clean) != ("quiet_end" in clean):
        raise ValueError("Set quiet_start and quiet_end together.")
    with _LOCK, _db() as conn:
        for key, value in clean.items():
            conn.execute(
                "INSERT INTO prefs(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    return get_prefs()


def in_quiet_hours(prefs: dict[str, Any], now: datetime) -> bool:
    start, end = prefs.get("quiet_start") or "", prefs.get("quiet_end") or ""
    if not start or not end or start == end:
        return False
    local = now.astimezone()
    minute = local.hour * 60 + local.minute
    s = int(start[:2]) * 60 + int(start[3:])
    e = int(end[:2]) * 60 + int(end[3:])
    return s <= minute < e if s < e else (minute >= s or minute < e)


# ------------------------------------------------------------------ items ---

@dataclass
class ProactiveItem:
    kind: str                      # "watch_alert" | "briefing"
    subject: str                   # watch id or calendar event id
    dedupe_key: str
    text: str                      # concise spoken text (AirPods)
    title: str = "Horus"
    severity: str = "info"         # info | warning | critical
    rule: str = ""                 # human-readable trigger rule
    score: float | None = None
    threshold: float | None = None
    evidence_lines: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    source_url: str = ""
    observed_at: str = ""
    critical: bool = False         # bypasses cooldown and budget (never dedupe)
    cooldown_key: str = ""
    cooldown_seconds: int = 0
    extra_keys: tuple[str, ...] = ()
    push_body: str = ""


def _row(row: sqlite3.Row) -> dict[str, Any]:
    out = {k: row[k] for k in row.keys()}
    out["critical"] = bool(out["critical"])
    try:
        out["evidence"] = json.loads(out.pop("evidence_json") or "{}")
    except ValueError:
        out["evidence"] = {}
    # Device receipt is the only thing that counts as confirmed delivery. APNs
    # HTTP 200 is exposed separately so it can never be mistaken for it.
    out["accepted_by_apns"] = out.get("push_state") == "accepted_by_apns"
    out["confirmed_delivery"] = out.get("push_state") == "device_acknowledged"
    return out


def budget_status(*, now: datetime | None = None) -> dict[str, Any]:
    instant = _utc(now)
    limit = get_prefs(now=instant)["hourly_budget"]
    since = (instant - timedelta(seconds=BUDGET_WINDOW_SECONDS)).isoformat()
    with _db() as conn:
        used = conn.execute(
            "SELECT count(*) FROM items WHERE decision='emitted' AND created_at>=?", (since,)
        ).fetchone()[0]
    return {"max_per_hour": limit, "used": int(used), "remaining": max(0, limit - int(used)),
            "window_seconds": BUDGET_WINDOW_SECONDS}


def is_emitted(key: str) -> bool:
    with _db() as conn:
        return conn.execute("SELECT 1 FROM emitted_keys WHERE key=?", (key,)).fetchone() is not None


def _record_suppressed(conn: sqlite3.Connection, item: ProactiveItem, reason: str, instant: datetime) -> str:
    existing = conn.execute(
        "SELECT id FROM items WHERE decision='suppressed' AND dedupe_key=? AND suppress_reason=?",
        (item.dedupe_key, reason)).fetchone()
    if existing:
        conn.execute(
            "UPDATE items SET seen_count=seen_count+1,last_seen_at=?,score=?,text=? WHERE id=?",
            (instant.isoformat(), item.score, item.text[:1500], existing["id"]))
        return str(existing["id"])
    item_id = uuid.uuid4().hex
    conn.execute(_INSERT, _values(item_id, item, "suppressed", reason, instant))
    return item_id


_INSERT = """INSERT INTO items
  (id,kind,subject,dedupe_key,cooldown_key,created_at,last_seen_at,decision,suppress_reason,
   severity,critical,title,text,rule,score,threshold,evidence_json,source,source_url,observed_at)
  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def _values(item_id: str, item: ProactiveItem, decision: str, reason: str, instant: datetime) -> tuple[Any, ...]:
    evidence = {"lines": item.evidence_lines[:12], "data": item.evidence}
    return (
        item_id, item.kind, item.subject[:200], item.dedupe_key[:300], item.cooldown_key[:200],
        instant.isoformat(), instant.isoformat(), decision, reason, item.severity[:20],
        int(item.critical), item.title[:120], item.text[:1500], item.rule[:500], item.score,
        item.threshold, json.dumps(evidence, ensure_ascii=False, default=str)[:20000],
        item.source[:200], item.source_url[:1000], item.observed_at[:100],
    )


def submit(
    item: ProactiveItem,
    *,
    now: datetime | None = None,
    authorize: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Decide and (if allowed) deliver one proactive item.

    ``authorize`` is re-evaluated under the attention lock immediately before
    emission and returns "" when allowed or a reason (e.g. "cancelled",
    "paused", "expired"); a non-empty reason records a suppression and sends
    nothing.
    """
    instant = _utc(now)
    with _LOCK:
        with _db() as conn:
            dup = conn.execute(
                "SELECT item_id FROM emitted_keys WHERE key=?", (item.dedupe_key,)).fetchone()
            if dup:
                conn.execute("UPDATE items SET seen_count=seen_count+1,last_seen_at=? WHERE id=?",
                             (instant.isoformat(), dup["item_id"]))
                return {"decision": "duplicate", "reason": "duplicate", "item_id": dup["item_id"]}
            reason = ""
            if authorize is not None:
                reason = str(authorize() or "")
            prefs = get_prefs(now=instant)
            if not reason and item.kind in PREF_GATED_KINDS:
                if not prefs["briefings_enabled"]:
                    reason = "disabled"
                elif prefs["snoozed"]:
                    reason = "snoozed"
                elif in_quiet_hours(prefs, instant):
                    reason = "quiet_hours"
            if not reason and item.cooldown_key and item.cooldown_seconds > 0 and not item.critical:
                last = conn.execute(
                    "SELECT created_at FROM items WHERE decision='emitted' AND cooldown_key=? "
                    "ORDER BY created_at DESC LIMIT 1", (item.cooldown_key,)).fetchone()
                if last and last["created_at"] > (instant - timedelta(seconds=item.cooldown_seconds)).isoformat():
                    reason = "cooldown"
            if not reason and not item.critical:
                since = (instant - timedelta(seconds=BUDGET_WINDOW_SECONDS)).isoformat()
                used = conn.execute(
                    "SELECT count(*) FROM items WHERE decision='emitted' AND created_at>=?", (since,)
                ).fetchone()[0]
                if used >= prefs["hourly_budget"]:
                    reason = "budget"
            if reason:
                item_id = _record_suppressed(conn, item, reason, instant)
                return {"decision": "suppressed", "reason": reason, "item_id": item_id}
            item_id = uuid.uuid4().hex
            conn.execute(_INSERT, _values(item_id, item, "emitted", "", instant))
            for key in (item.dedupe_key, *item.extra_keys):
                conn.execute("INSERT OR IGNORE INTO emitted_keys(key,item_id,created_at) VALUES(?,?,?)",
                             (key[:300], item_id, instant.isoformat()))
            conn.execute("DELETE FROM items WHERE created_at<?",
                         ((instant - timedelta(days=RETENTION_DAYS)).isoformat(),))
        delivery = _deliver(item_id, item, instant)
    return {"decision": "emitted", "reason": "", "item_id": item_id, "delivery": delivery}


def record_suppressed(item: ProactiveItem, reason: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Store an item the caller judged not worth an interruption (for inspection).

    Used for relevance decisions made before submission (e.g. weak briefing
    evidence). Nothing is delivered. Repeats of the same item and reason are
    collapsed into one row with a seen counter."""
    instant = _utc(now)
    with _LOCK, _db() as conn:
        item_id = _record_suppressed(conn, item, reason, instant)
    return {"decision": "suppressed", "reason": reason, "item_id": item_id}


# --------------------------------------------------------------- delivery ---

def _publish_live(item: ProactiveItem) -> tuple[str, int, str]:
    clients = 0
    try:
        from jarvis_mrb import event_bus
        clients = int(event_bus.companion_events.subscriber_count())
        event_bus.emit_proactive(
            item.text, cue="attention",
            severity="warning" if item.severity in {"warning", "critical"} else "info")
    except Exception as exc:
        return "failed", clients, type(exc).__name__
    if clients > 0:
        return "live_published", clients, f"handed to {clients} connected companion session(s); receipt is not confirmed"
    return "no_live_client", 0, "no companion app was connected; this was not spoken live"


def _publish_push(item_id: str, item: ProactiveItem, instant: datetime) -> tuple[str, str, str]:
    event_id = "horus-" + item_id
    try:
        from jarvis_mrb import world_armor_push as push
        if not push.enabled():
            return "not_configured", "", "APNs push is not enabled on this server"
        if not push.configured():
            return "not_configured", "", "APNs credentials are not configured"
        body = item.push_body or item.text
        if item.source_url and item.source_url not in body:
            body = (body.rstrip() + " " + item.source_url)
        category = "briefing" if item.kind == "briefing" else "watch"
        result = push.enqueue_notification(
            event_id, item.title or "Horus", body, category=category,
            thread_id="horus-" + category,
            priority="urgent" if item.critical else "warning", now=instant)
    except Exception as exc:
        return "failed", "", type(exc).__name__
    if int(result.get("queued") or 0) > 0:
        return "queued", event_id, f"queued for {result['queued']} device(s); not yet accepted by APNs"
    if result.get("reason") == "no_enabled_devices":
        return "not_configured", "", "no iPhone is registered for push"
    return "failed", "", str(result.get("reason") or "not_queued")


def _deliver(item_id: str, item: ProactiveItem, instant: datetime) -> dict[str, Any]:
    live_state, clients, live_detail = _publish_live(item)
    push_state, event_id, push_detail = _publish_push(item_id, item, instant)
    with _db() as conn:
        conn.execute(
            """UPDATE items SET live_state=?,live_clients=?,live_detail=?,push_state=?,
               push_detail=?,push_event_id=?,push_updated_at=? WHERE id=?""",
            (live_state, clients, live_detail, push_state, push_detail, event_id,
             instant.isoformat(), item_id))
    return {"live": live_state, "live_clients": clients, "push": push_state,
            "push_detail": push_detail, "accepted_by_apns": False,
            "confirmed_delivery": False}


_APNS_REASONS = {
    "BadCollapseId", "BadDeviceToken", "BadExpirationDate", "BadMessageId", "BadPriority",
    "BadTopic", "DeviceTokenNotForTopic", "DuplicateHeaders", "ExpiredProviderToken",
    "ExpiredToken", "Forbidden", "InvalidProviderToken", "InternalServerError", "MethodNotAllowed",
    "MissingDeviceToken", "MissingTopic", "PayloadEmpty", "PayloadTooLarge", "ServiceUnavailable",
    "Shutdown", "TooManyProviderTokenUpdates", "TooManyRequests", "TopicDisallowed", "Unregistered",
    "BadCertificate", "BadCertificateEnvironment", "MissingProviderToken",
}


def _apns_answered(reason: str) -> bool:
    """True when APNs itself replied (a documented reason or an HTTP status).

    Transport exceptions (for example ``ConnectError``) mean APNs was never
    reached, so the outcome is unknown rather than a rejection."""
    return reason in _APNS_REASONS or reason.startswith("http_")


def reconcile_push() -> int:
    """Settle ``queued`` pushes against the APNs outbox. Returns rows changed."""
    changed = 0
    with _LOCK, _db() as conn:
        rows = conn.execute(
            "SELECT id,push_event_id,created_at FROM items WHERE push_state='queued' AND push_event_id!=''"
        ).fetchall()
        if not rows:
            return 0
        from jarvis_mrb import world_armor_push as push
        for row in rows:
            state = push.delivery_state(str(row["push_event_id"]))
            new_state, detail = "queued", ""
            if state["pending"] > 0:
                continue
            if state["sent"] > 0:
                new_state = "accepted_by_apns"
                detail = (f"APNs accepted the push for {state['sent']} of {state['total']} device(s); "
                          "device receipt is not confirmed")
            elif state["dead"] > 0:
                reason = str(state["last_error"] or "")
                if _apns_answered(reason):
                    new_state = "rejected_by_apns"
                    detail = "APNs rejected the push" + (": " + reason if reason else "")
                else:
                    new_state = "delivery_unknown"
                    detail = "APNs was never reached" + (": " + reason if reason else "")
            else:
                created = datetime.fromisoformat(str(row["created_at"]))
                if (datetime.now(timezone.utc) - created).total_seconds() > 3600:
                    new_state, detail = "delivery_unknown", "outbox record is gone; delivery cannot be determined"
                else:
                    continue
            conn.execute("UPDATE items SET push_state=?,push_detail=?,push_updated_at=? WHERE id=?",
                         (new_state, detail, datetime.now(timezone.utc).isoformat(), row["id"]))
            changed += 1
    return changed


# ------------------------------------------------------------------ reads ---

def ledger(*, limit: int = 50, kind: str | None = None, decision: str | None = None) -> list[dict[str, Any]]:
    try:
        reconcile_push()
    except Exception:
        pass
    sql, args = "SELECT * FROM items WHERE 1=1", []
    if kind:
        sql += " AND kind=?"; args.append(kind)
    if decision:
        sql += " AND decision=?"; args.append(decision)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))
    with _db() as conn:
        return [_row(r) for r in conn.execute(sql, args)]


def get_item(item_id: str) -> dict[str, Any] | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return _row(row) if row else None


def recent_emitted(*, kind: str | None = None, within_seconds: float = 6 * 3600,
                   now: datetime | None = None, limit: int = 10) -> list[dict[str, Any]]:
    since = (_utc(now) - timedelta(seconds=within_seconds)).isoformat()
    sql, args = "SELECT * FROM items WHERE decision='emitted' AND created_at>=?", [since]
    if kind:
        sql += " AND kind=?"; args.append(kind)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    args.append(limit)
    with _db() as conn:
        return [_row(r) for r in conn.execute(sql, args)]


HELD_BACK_REASONS = ("budget", "cooldown", "quiet_hours", "snoozed")


def held_back(*, now: datetime | None = None, within_seconds: float = 24 * 3600,
              acknowledge: bool = False) -> list[dict[str, Any]]:
    """Real items that were suppressed only by attention policy (not for being weak)."""
    since = (_utc(now) - timedelta(seconds=within_seconds)).isoformat()
    marks = ",".join("?" for _ in HELD_BACK_REASONS)
    with _db() as conn:
        rows = conn.execute(
            f"SELECT * FROM items WHERE decision='suppressed' AND acknowledged_at IS NULL "
            f"AND suppress_reason IN ({marks}) AND created_at>=? ORDER BY created_at DESC LIMIT 20",
            (*HELD_BACK_REASONS, since)).fetchall()
        if acknowledge and rows:
            conn.execute(
                f"UPDATE items SET acknowledged_at=? WHERE id IN ({','.join('?' for _ in rows)})",
                (_utc(now).isoformat(), *[r["id"] for r in rows]))
    return [_row(r) for r in rows]


# ---------------------------------------------------------------- explain ---

def delivery_summary(item: dict[str, Any]) -> str:
    live = {
        "live_published": "published to " + str(item.get("live_clients")) + " connected companion session(s) (receipt not confirmed)",
        "no_live_client": "no companion app was connected, so it was not spoken live",
        "failed": "live publish failed",
    }.get(str(item.get("live_state")), "live delivery not attempted")
    push = {
        "accepted_by_apns": "iPhone push accepted by Apple's service (device receipt not confirmed)",
        "rejected_by_apns": "iPhone push rejected by Apple's service",
        "delivery_unknown": "iPhone push outcome unknown (Apple's service was not reached)",
        "device_acknowledged": "iPhone confirmed receipt",
        "queued": "iPhone push queued, not yet answered by Apple's service",
        "failed": "iPhone push could not be queued",
        "not_configured": "iPhone push not configured (" + str(item.get("push_detail") or "no detail") + ")",
    }.get(str(item.get("push_state")), "iPhone push not attempted")
    return live + "; " + push


def explain(item: dict[str, Any]) -> str:
    from jarvis_mrb.voice_time import local_clock
    when = local_clock(item.get("created_at"))
    if item["kind"] == "briefing":
        lead = f"I briefed you at {when} because"
    else:
        lead = f"I alerted you at {when} because"
    parts = [f"{lead} {item.get('rule') or 'a rule you enabled fired'}."]
    if item.get("score") is not None and item.get("threshold") is not None:
        parts.append(f"It scored {item['score']:g} against a threshold of {item['threshold']:g}.")
    lines = (item.get("evidence") or {}).get("lines") or []
    if lines:
        parts.append("Evidence: " + "; ".join(str(x) for x in lines[:3]) + ".")
    source = item.get("source") or "no external source"
    seen = local_clock(item.get("observed_at")) if item.get("observed_at") else "an unknown time"
    parts.append(f"Source: {source}, observed {seen}.")
    return " ".join(parts)


# ---------------------------------------------------------- voice handler ---

_WHY_EXPLICIT = re.compile(
    r"^(?:(?:hey |ok |okay )?(?:horus|jarvis),? )?(?:why (?:did you|have you|were you) (?:just )?(?:alert|notify|interrupt|ping|warn|brief) me"
    r"|why was i (?:just )?(?:alerted|notified|interrupted|pinged|warned|briefed)"
    r"|what (?:was|is) that (?:alert|notification|briefing|interruption))(?: (?:about that|about it|for|just now))?$"
)
_WHY_GENERIC = re.compile(
    r"^(?:(?:hey |ok |okay )?(?:horus|jarvis),? )?(?:why did you (?:just )?(?:tell|say that to|message) me (?:that|this|about that)"
    r"|why (?:are|am) you (?:telling|alerting) me (?:that|this)|why that alert)$"
)
_HELD = re.compile(
    r"^(?:what|which) (?:alerts |alert |items |notifications )?(?:did you|have you) (?:hold back|held back|suppress|suppressed|skip|skipped)"
    r"|^(?:what did i miss|did you hold anything back|anything you held back|what are you holding back)$"
)
_BUDGET = re.compile(
    r"^(?:what(?:'s| is) )?(?:my )?(?:interruption|alert|notification) (?:budget|limit)(?: status)?$|"
    r"^how many (?:alerts|interruptions|notifications) (?:have you|did you) (?:sent|send|made|given)(?: me)?(?: this hour)?$"
)


def _norm(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9' ]+", " ", str(text or "").lower())
    return " ".join(cleaned.split())


def handle(text: str, turn: Any) -> str | None:
    n = _norm(text)
    if _WHY_EXPLICIT.match(n) or _WHY_GENERIC.match(n):
        window = 12 * 3600 if _WHY_EXPLICIT.match(n) else 20 * 60
        items = recent_emitted(within_seconds=window, limit=1)
        if not items:
            return None  # not about a proactive item; let other handlers answer
        return explain(items[0])
    if _HELD.match(n):
        items = held_back(acknowledge=True)
        if not items:
            return "Nothing is being held back. Every proactive item I recorded was either spoken or judged too weak, and I have none waiting."
        names = {"budget": "your hourly interruption limit", "cooldown": "a watch cooldown",
                 "quiet_hours": "quiet hours", "snoozed": "your snooze"}
        first = items[0]
        extra = f" and {len(items) - 1} more" if len(items) > 1 else ""
        return (f"I held back {len(items)} item{'s' if len(items) != 1 else ''} because of "
                f"{names.get(first['suppress_reason'], 'a policy')}. The newest{extra}: {first['text'][:260]}")
    if _BUDGET.match(n):
        b = budget_status()
        return (f"I have used {b['used']} of {b['max_per_hour']} proactive interruptions this hour; "
                f"{b['remaining']} remain. Critical weather alerts can still go through.")
    return None


try:
    from jarvis_mrb.voice_router import register as _register
    _register("proactive_attention", handle)
except Exception:  # pragma: no cover - router import must never break the module
    pass
