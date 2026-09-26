from __future__ import annotations

"""Durable APNs transport for high-priority World Armor events.

APNs is a delivery transport only.  The World Armor live journal remains the
authoritative event record.  Device tokens are registered only through the
private Jarvis API, and provider signing material is read from local
environment/configuration at send time.  No Apple credential is stored in this
SQLite database or reflected through the API.
"""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any
from uuid import uuid4

import httpx

from jarvis_mrb import world_model

PUSH_STORE = Path(world_model.DB_PATH).with_name("world_armor_push.sqlite3")
_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64,256}$")
_MAX_OUTBOX = 2_000
_MAX_ATTEMPTS = 8
_MAX_AGE_HOURS = 24
_WORKER_INTERVAL_SECONDS = 3
_worker_lock = threading.RLock()
_worker_stop = threading.Event()
_worker_thread: threading.Thread | None = None
_jwt_lock = threading.RLock()
_cached_jwt: tuple[str, float] | None = None


def _now(value: datetime | None = None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("APNs timestamps must be offset-aware.")
    return instant.astimezone(timezone.utc)


def enabled() -> bool:
    return (
        os.getenv("JARVIS_WORLD_ARMOR_ENABLED") == "1"
        and os.getenv("JARVIS_WORLD_ARMOR_PUSH_ENABLED") == "1"
    )


def configured() -> bool:
    return bool(
        enabled()
        and os.getenv("JARVIS_APNS_TEAM_ID", "").strip()
        and os.getenv("JARVIS_APNS_KEY_ID", "").strip()
        and os.getenv("JARVIS_APNS_BUNDLE_ID", "").strip()
        and os.getenv("JARVIS_APNS_KEY_FILE", "").strip()
    )


def _connect(path: Path = PUSH_STORE) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA secure_delete=ON")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS push_devices (
          id TEXT PRIMARY KEY,
          token TEXT NOT NULL UNIQUE,
          token_hash TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_success_at TEXT,
          last_failure_at TEXT,
          last_failure_reason TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS ix_push_devices_enabled
          ON push_devices(enabled,updated_at);

        CREATE TABLE IF NOT EXISTS push_outbox (
          id TEXT PRIMARY KEY,
          device_id TEXT NOT NULL REFERENCES push_devices(id) ON DELETE CASCADE,
          event_id TEXT NOT NULL,
          event_seq INTEGER,
          priority TEXT NOT NULL,
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          created_at TEXT NOT NULL,
          next_attempt_at TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          state TEXT NOT NULL DEFAULT 'pending',
          last_error TEXT NOT NULL DEFAULT '',
          UNIQUE(device_id,event_id),
          CHECK(priority IN ('warning','urgent')),
          CHECK(state IN ('pending','sent','dead'))
        );
        CREATE INDEX IF NOT EXISTS ix_push_outbox_due
          ON push_outbox(state,next_attempt_at,created_at);
        """
    )
    con.commit()
    return con


def _token(value: str) -> str:
    token = str(value or "").strip().lower()
    if not _TOKEN_RE.fullmatch(token):
        raise ValueError("APNs device token must be 64-256 hexadecimal characters.")
    return token


def register_device(
    token: str, *, db_path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    value = _token(token)
    instant = _now(now)
    path = Path(db_path) if db_path is not None else PUSH_STORE
    digest = hashlib.sha256(value.encode("ascii")).hexdigest()
    ident = digest[:32]
    with closing(_connect(path)) as con, con:
        con.execute(
            """INSERT INTO push_devices
               (id,token,token_hash,created_at,updated_at,enabled)
               VALUES(?,?,?,?,?,1)
               ON CONFLICT(token) DO UPDATE SET
                 updated_at=excluded.updated_at,enabled=1""",
            (ident, value, digest, instant.isoformat(), instant.isoformat()),
        )
    if enabled():
        start_worker(db_path=path)
    return {
        "device_id": ident,
        "token_hash": digest,
        "enabled": True,
        "push_transport_enabled": enabled(),
        "provider_configured": configured(),
        "token_reflected": False,
    }


def unregister_device(
    token: str, *, db_path: Path | None = None
) -> dict[str, Any]:
    value = _token(token)
    path = Path(db_path) if db_path is not None else PUSH_STORE
    if not path.exists():
        return {"disabled": False}
    with closing(_connect(path)) as con, con:
        result = con.execute(
            "UPDATE push_devices SET enabled=0,updated_at=? WHERE token=?",
            (_now().isoformat(), value),
        )
    return {"disabled": result.rowcount == 1}


def _prune(con: sqlite3.Connection, instant: datetime) -> None:
    cutoff = (instant - timedelta(hours=_MAX_AGE_HOURS)).isoformat()
    con.execute(
        "UPDATE push_outbox SET state='dead',last_error='expired' "
        "WHERE state='pending' AND created_at<?",
        (cutoff,),
    )
    con.execute(
        "DELETE FROM push_outbox WHERE state IN ('sent','dead') AND created_at<?",
        ((instant - timedelta(days=7)).isoformat(),),
    )
    excess = con.execute(
        "SELECT MAX(0,COUNT(*)-?) FROM push_outbox WHERE state='pending'",
        (_MAX_OUTBOX,),
    ).fetchone()[0]
    if excess:
        con.execute(
            "UPDATE push_outbox SET state='dead',last_error='outbox_backpressure' "
            "WHERE id IN (SELECT id FROM push_outbox WHERE state='pending' "
            "ORDER BY created_at,id LIMIT ?)",
            (int(excess),),
        )


def enqueue_world_event(
    event: dict[str, Any],
    *,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not enabled():
        return {"queued": 0, "reason": "push_disabled"}
    priority = str(event.get("priority") or "").lower()
    if priority not in {"warning", "urgent"}:
        return {"queued": 0, "reason": "priority_not_pushable"}
    event_id = str(event.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("World Armor push event needs an event_id.")
    summary = str(event.get("summary") or "").strip()
    if not summary:
        raise ValueError("World Armor push event needs a summary.")
    title = "World Armor urgent" if priority == "urgent" else "World Armor"
    instant = _now(now)
    path = Path(db_path) if db_path is not None else PUSH_STORE
    queued = 0
    with closing(_connect(path)) as con, con:
        _prune(con, instant)
        devices = con.execute(
            "SELECT id FROM push_devices WHERE enabled=1 ORDER BY created_at"
        ).fetchall()
        for device in devices:
            cur = con.execute(
                """INSERT OR IGNORE INTO push_outbox
                   (id,device_id,event_id,event_seq,priority,title,body,
                    created_at,next_attempt_at,attempts,state)
                   VALUES(?,?,?,?,?,?,?,?,?,0,'pending')""",
                (
                    uuid4().hex, device["id"], event_id,
                    int(event["seq"]) if event.get("seq") is not None else None,
                    priority, title, summary[:700],
                    instant.isoformat(), instant.isoformat(),
                ),
            )
            queued += max(0, int(cur.rowcount))
    if queued:
        start_worker(db_path=path)
    return {"queued": queued, "reason": "queued" if queued else "no_enabled_devices"}


def status(*, db_path: Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else PUSH_STORE
    devices = pending = dead = sent = 0
    oldest = None
    if path.exists():
        with closing(_connect(path)) as con, con:
            _prune(con, _now())
            devices = int(con.execute(
                "SELECT count(*) FROM push_devices WHERE enabled=1"
            ).fetchone()[0])
            pending = int(con.execute(
                "SELECT count(*) FROM push_outbox WHERE state='pending'"
            ).fetchone()[0])
            dead = int(con.execute(
                "SELECT count(*) FROM push_outbox WHERE state='dead'"
            ).fetchone()[0])
            sent = int(con.execute(
                "SELECT count(*) FROM push_outbox WHERE state='sent'"
            ).fetchone()[0])
            oldest = con.execute(
                "SELECT MIN(created_at) FROM push_outbox WHERE state='pending'"
            ).fetchone()[0]
    return {
        "enabled": enabled(),
        "provider_configured": configured(),
        "registered_devices": devices,
        "pending": pending,
        "dead": dead,
        "sent_retained": sent,
        "oldest_pending_at": oldest,
        "max_pending": _MAX_OUTBOX,
        "max_attempts": _MAX_ATTEMPTS,
        "delivery_semantics": "best_effort_apns_with_durable_retry_outbox",
    }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _provider_jwt(now_epoch: float | None = None) -> str:
    global _cached_jwt
    if not configured():
        raise RuntimeError("APNs provider credentials are not configured.")
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    with _jwt_lock:
        if _cached_jwt and now_epoch - _cached_jwt[1] < 45 * 60:
            return _cached_jwt[0]
        team = os.environ["JARVIS_APNS_TEAM_ID"].strip()
        key_id = os.environ["JARVIS_APNS_KEY_ID"].strip()
        key_file = Path(os.environ["JARVIS_APNS_KEY_FILE"].strip())
        try:
            key_bytes = key_file.read_bytes()
        except OSError as exc:
            raise RuntimeError("Cannot read APNs signing key file.") from exc
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import (
                decode_dss_signature,
            )
            key = serialization.load_pem_private_key(key_bytes, password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise TypeError("not EC")
            header = _b64url(json.dumps(
                {"alg": "ES256", "kid": key_id},
                separators=(",", ":"), sort_keys=True,
            ).encode())
            claims = _b64url(json.dumps(
                {"iss": team, "iat": int(now_epoch)},
                separators=(",", ":"), sort_keys=True,
            ).encode())
            signing_input = f"{header}.{claims}".encode("ascii")
            der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
            r, s = decode_dss_signature(der)
            raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
            token = f"{header}.{claims}.{_b64url(raw_signature)}"
        except Exception as exc:
            raise RuntimeError("APNs signing key is invalid or unusable.") from exc
        _cached_jwt = (token, now_epoch)
        return token


def _endpoint(token: str) -> str:
    production = os.getenv("JARVIS_APNS_ENVIRONMENT", "development").strip().lower()
    if production not in {"development", "production"}:
        raise RuntimeError("JARVIS_APNS_ENVIRONMENT must be development or production.")
    host = (
        "https://api.push.apple.com"
        if production == "production"
        else "https://api.sandbox.push.apple.com"
    )
    return f"{host}/3/device/{token}"


def _send_one(token: str, title: str, body: str) -> tuple[bool, str]:
    jwt = _provider_jwt()
    bundle = os.environ["JARVIS_APNS_BUNDLE_ID"].strip()
    payload = {
        "aps": {
            "alert": {"title": title[:120], "body": body[:700]},
            "sound": "default",
            "thread-id": "world-armor",
        },
        "world_armor": True,
    }
    try:
        with httpx.Client(http2=True, timeout=12.0) as client:
            response = client.post(
                _endpoint(token),
                headers={
                    "authorization": "bearer " + jwt,
                    "apns-topic": bundle,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                    "content-type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        return False, type(exc).__name__
    if response.status_code == 200:
        return True, ""
    reason = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            reason = str(data.get("reason") or "")
    except ValueError:
        pass
    return False, reason[:120] or f"http_{response.status_code}"


def drain_once(
    *, db_path: Path | None = None, limit: int = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("APNs drain limit must be 1-100.")
    if not enabled():
        return {"attempted": 0, "sent": 0, "failed": 0, "reason": "push_disabled"}
    if not configured():
        return {
            "attempted": 0, "sent": 0, "failed": 0,
            "reason": "provider_not_configured",
        }
    path = Path(db_path) if db_path is not None else PUSH_STORE
    instant = _now(now)
    if not path.exists():
        return {"attempted": 0, "sent": 0, "failed": 0}
    with closing(_connect(path)) as con, con:
        _prune(con, instant)
        rows = con.execute(
            """SELECT o.*,d.token FROM push_outbox o
               JOIN push_devices d ON d.id=o.device_id
               WHERE o.state='pending' AND d.enabled=1
                 AND o.next_attempt_at<=?
               ORDER BY o.created_at,o.id LIMIT ?""",
            (instant.isoformat(), limit),
        ).fetchall()
    sent = failed = 0
    for row in rows:
        ok, reason = _send_one(row["token"], row["title"], row["body"])
        completed = _now() if now is None else instant
        with closing(_connect(path)) as con, con:
            if ok:
                con.execute(
                    "UPDATE push_outbox SET state='sent',attempts=attempts+1,"
                    "last_error='' WHERE id=? AND state='pending'",
                    (row["id"],),
                )
                con.execute(
                    "UPDATE push_devices SET last_success_at=?,last_failure_reason='' "
                    "WHERE id=?",
                    (completed.isoformat(), row["device_id"]),
                )
                sent += 1
            else:
                attempts = int(row["attempts"]) + 1
                terminal_token = reason in {
                    "BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"
                }
                dead = attempts >= _MAX_ATTEMPTS or terminal_token
                delay = min(1800, 5 * (2 ** min(attempts - 1, 8)))
                con.execute(
                    "UPDATE push_outbox SET attempts=?,state=?,last_error=?,"
                    "next_attempt_at=? WHERE id=? AND state='pending'",
                    (
                        attempts, "dead" if dead else "pending", reason,
                        (completed + timedelta(seconds=delay)).isoformat(),
                        row["id"],
                    ),
                )
                con.execute(
                    "UPDATE push_devices SET last_failure_at=?,last_failure_reason=?,"
                    "enabled=CASE WHEN ? THEN 0 ELSE enabled END WHERE id=?",
                    (
                        completed.isoformat(), reason, int(terminal_token),
                        row["device_id"],
                    ),
                )
                failed += 1
    return {
        "attempted": len(rows),
        "sent": sent,
        "failed": failed,
        "remaining": status(db_path=path)["pending"],
    }


def _worker(path: Path) -> None:
    while not _worker_stop.is_set():
        try:
            result = drain_once(db_path=path)
            pending = int(result.get("remaining") or 0)
        except Exception:
            pending = 0
        _worker_stop.wait(
            0.5 if pending else _WORKER_INTERVAL_SECONDS
        )


def start_worker(*, db_path: Path | None = None) -> bool:
    if not enabled():
        return False
    path = Path(db_path) if db_path is not None else PUSH_STORE
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return True
        _worker_stop.clear()
        _worker_thread = threading.Thread(
            target=_worker, args=(path,),
            name="world-armor-apns-outbox", daemon=True,
        )
        _worker_thread.start()
    return True


def worker_alive() -> bool:
    with _worker_lock:
        return bool(_worker_thread and _worker_thread.is_alive())


def stop_worker() -> None:
    global _worker_thread
    with _worker_lock:
        _worker_stop.set()
        thread = _worker_thread
    if thread and thread.is_alive():
        thread.join(timeout=2.0)
    with _worker_lock:
        if _worker_thread is thread:
            _worker_thread = None
