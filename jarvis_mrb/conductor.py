from __future__ import annotations

"""Conductor v1: one exact workstation, bounded user-approved app actions.

A prepared mission is NOT execution authority. The caller must supply the
short-lived random one-use grant returned once at planning. The backend
reserves that grant BEFORE touching a device; uncertain effects never retry.
No model-generated tool names, arbitrary files/commands, screen pixels,
email, microphone, smart-lock, purchases, or irreversible physical actions.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid
from typing import Any

from jarvis_mrb import reality_mesh
from jarvis_mrb.world_model import APP_DIR

_LOCK = threading.RLock()
_MAC = ("Safari", "Notes", "Calendar", "Preview", "Finder")
_WINDOWS = ("Notepad", "Calculator", "File Explorer", "Paint")
_EXPIRY_SECONDS = 120
_MAX_APPS = 3


class MissionBlocked(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat()


def enabled() -> bool:
    return os.getenv("JARVIS_CONDUCTOR_ENABLED") == "1"


@contextmanager
def _database():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(APP_DIR / "conductor.sqlite3", timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS workstation_missions (
        id TEXT PRIMARY KEY,
        node_id TEXT NOT NULL,
        apps_json TEXT NOT NULL,
        screen_requested INTEGER NOT NULL,
        grant_digest TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        steps_json TEXT NOT NULL DEFAULT '[]',
        error TEXT NOT NULL DEFAULT ''
    )""")
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _validate_target(node_id: str, apps: list[str], screen: bool) -> None:
    from jarvis_mrb import mesh_windows_apps
    from jarvis_mrb.permissions import decide

    if not enabled():
        raise MissionBlocked("Operator has not enabled Conductor on the Windows backend.")
    if node_id not in {"windows", "macbook", "macmini"}:
        raise ValueError("Choose one exact paired workstation.")
    if type(apps) is not list or not 1 <= len(apps) <= _MAX_APPS:
        raise ValueError("Choose 1–3 exact registered app names.")
    if any(type(app) is not str for app in apps) or len(apps) != len(set(apps)):
        raise ValueError("Each exact application may appear only once.")
    if type(screen) is not bool:
        raise ValueError("Screen choice must be a boolean.")
    allowed = _WINDOWS if node_id == "windows" else _MAC
    if any(app not in allowed for app in apps):
        raise ValueError("Unsupported exact app on the selected device.")
    if node_id == "windows":
        if not mesh_windows_apps.enabled():
            raise MissionBlocked("Windows app-launch opt-in is off.")
        if not decide("pc.launch_app").allowed:
            raise MissionBlocked("Windows PC launch permissions deny local writes.")
        from jarvis_mrb import mesh_windows_screen
        if screen and not mesh_windows_screen.enabled():
            raise MissionBlocked("Windows screen opt-in is off. Uncheck desktop viewing.")
        return
    state = reality_mesh.probe(node_id)
    if state.get("status") != "online":
        raise MissionBlocked("Exact Mac is offline or identity unverified.")
    capabilities = state.get("capabilities", {})
    if capabilities.get("app_launch") != "exact_user_tap_only":
        raise MissionBlocked("Mac exact-app startup opt-in is off.")
    if screen and capabilities.get("screen") != "session_opt_in":
        raise MissionBlocked("Mac screen startup opt-in is off. Uncheck desktop viewing.")


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "kind": "prepare_workstation",
        "node_id": row["node_id"],
        "apps": json.loads(row["apps_json"]),
        "screen_requested": bool(row["screen_requested"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "updated_at": row["updated_at"],
        "steps": json.loads(row["steps_json"]),
        "error": row["error"],
        "screen_shown_on_phone_verified": False,
        "one_use_grant_redeemable": row["status"] == "planned"
            and row["expires_at"] > _iso(),
    }


def plan(node_id: str, apps: list[str], *, screen: bool = False) -> dict[str, Any]:
    _validate_target(node_id, apps, screen)
    token = secrets.token_urlsafe(32)
    now = _now()
    mission_id = uuid.uuid4().hex
    with _LOCK:
        with _database() as conn:
            # Hard bound outstanding exact mission grants per backend.
            pending = conn.execute(
                "SELECT COUNT(*) FROM workstation_missions "
                "WHERE status='planned' AND expires_at>?",
                (now.isoformat(),)
            ).fetchone()[0]
            if pending >= 10:
                raise MissionBlocked("Too many live workstation drafts; revoke one first.")
            conn.execute(
                "INSERT INTO workstation_missions "
                "(id,node_id,apps_json,screen_requested,grant_digest,status,"
                "created_at,expires_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    mission_id, node_id, json.dumps(apps), int(screen),
                    hashlib.sha256(token.encode()).hexdigest(),
                    "planned", now.isoformat(),
                    (now + timedelta(seconds=_EXPIRY_SECONDS)).isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM workstation_missions WHERE id=?", (mission_id,)
            ).fetchone()
    return {
        **_public(row),
        "one_use_grant": token,  # returned once; never stored plaintext
        "authorization_note": (
            "Inspect exact device, app list and optional view; an explicit "
            "phone confirmation is required before redeeming this one-use grant."
        ),
    }


def get(mission_id: str) -> dict[str, Any]:
    if not isinstance(mission_id, str) or len(mission_id) != 32:
        raise ValueError("Invalid exact Conductor mission ID.")
    with _database() as conn:
        row = conn.execute(
            "SELECT * FROM workstation_missions WHERE id=?", (mission_id,)
        ).fetchone()
    if row is None:
        raise ValueError("Unknown Conductor mission.")
    return _public(row)


def recent(*, limit: int = 15) -> dict[str, Any]:
    """No grant tokens; receipts survive phone restart and network failures."""
    count = max(1, min(int(limit), 30))
    with _database() as conn:
        rows = conn.execute(
            "SELECT * FROM workstation_missions ORDER BY created_at DESC LIMIT ?",
            (count,),
        ).fetchall()
    return {
        "checked_at": _iso(),
        "missions": [_public(row) for row in rows],
        "one_use_grants_returned": False,
    }


def revoke(mission_id: str) -> dict[str, Any]:
    # Revocation is checked before every step; in-flight external calls cannot
    # be rolled back, and that uncertainty is retained in the step evidence.
    with _LOCK:
        with _database() as conn:
            row = conn.execute(
                "SELECT * FROM workstation_missions WHERE id=?", (mission_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Unknown Conductor mission.")
            if row["status"] in {"planned", "running"}:
                conn.execute(
                    "UPDATE workstation_missions SET status='revoked',updated_at=? "
                    "WHERE id=?", (_iso(), mission_id)
                )
                conn.commit()
    return get(mission_id)


def _save(mission_id: str, status: str, steps: list[dict[str, Any]],
          error: str = "") -> dict[str, Any]:
    with _LOCK:
        with _database() as conn:
            row = conn.execute(
                "SELECT status FROM workstation_missions WHERE id=?", (mission_id,)
            ).fetchone()
            if row is None:
                raise MissionBlocked("Workstation mission has disappeared.")
            if row["status"] == "revoked":
                status = "revoked"
            conn.execute(
                "UPDATE workstation_missions SET status=?,steps_json=?,error=?,"
                "updated_at=? WHERE id=?",
                (status, json.dumps(steps), error[:250], _iso(), mission_id),
            )
            conn.commit()
    return get(mission_id)


def _require_fresh_evidence(snapshot: dict[str, Any], node_id: str) -> datetime:
    if snapshot.get("node_id") != node_id or not isinstance(snapshot.get("apps"), dict):
        raise reality_mesh.NodeUnavailable("Independent process observation target mismatched.")
    try:
        stamp = datetime.fromisoformat(str(snapshot["observed_at"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None or abs((_now() - stamp).total_seconds()) > 30:
            raise ValueError("stale source timestamp")
    except (ValueError, TypeError, KeyError) as exc:
        raise reality_mesh.NodeUnavailable("Independent process timestamp missing/stale.") from exc
    if not str(snapshot.get("source") or ""):
        raise reality_mesh.NodeUnavailable("Independent process source attribution absent.")
    return stamp


def execute(mission_id: str, grant: str, node_id: str,
            apps: list[str]) -> dict[str, Any]:
    if not enabled():
        raise MissionBlocked("Conductor operator opt-in is now disabled.")
    if not isinstance(grant, str) or len(grant) < 32:
        raise MissionBlocked("Missing one-use mission grant.")
    with _LOCK:
        with _database() as conn:
            row = conn.execute(
                "SELECT * FROM workstation_missions WHERE id=?", (mission_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Unknown exact workstation mission.")
            valid = (
                row["status"] == "planned"
                and row["expires_at"] > _iso()
                and row["node_id"] == node_id
                and json.loads(row["apps_json"]) == apps
                and hmac.compare_digest(
                    str(row["grant_digest"]),
                    hashlib.sha256(grant.encode()).hexdigest()
                )
            )
            if not valid:
                raise MissionBlocked(
                    "Mission was revoked, expired, changed or its one-use grant was spent."
                )
            # Reserve ALL potential app side effects BEFORE remote or OS IO.
            # After service restart, a running record remains 'running/unknown'
            # rather than being replayed.
            conn.execute(
                "UPDATE workstation_missions SET status='running',"
                "grant_digest='',updated_at=? WHERE id=?",
                (_iso(), mission_id),
            )
            conn.commit()
    steps: list[dict[str, Any]] = []
    try:
        _validate_target(node_id, apps, bool(row["screen_requested"]))
        pre = reality_mesh.exact_app_observations(node_id)
        pre_time = _require_fresh_evidence(pre, node_id)
        last_action_at = 0.0
        for app in apps:
            if get(mission_id)["status"] != "running":
                return _save(mission_id, "revoked", steps,
                             "Revoked; an in-flight host side effect cannot be undone.")
            before = pre["apps"].get(app, "unknown")
            step: dict[str, Any] = {
                "node_id": node_id, "app_name": app,
                "before_state": before,
                "before_observed_at": pre["observed_at"],
                "source": pre["source"],
                "attempted_at": "",
                "receipt": "",
                "after_state": "unknown",
                "after_observed_at": "",
                "result": "blocked",
            }
            if before == "unknown":
                step["receipt"] = "Initial process evidence unavailable; no launch attempted."
                steps.append(step)
                _save(mission_id, "running", steps)
                continue
            if before == "not_running":
                if last_action_at > 0:
                    time.sleep(max(0, 3.05 - (time.monotonic() - last_action_at)))
                if get(mission_id)["status"] != "running":
                    return _save(mission_id, "revoked", steps,
                                 "Revoked before next host action.")
                step["attempted_at"] = _iso()
                # Reserve this exact step in durable ledger *before* OS/HTTP IO.
                step["result"] = "attempt_reserved"
                steps.append(step)
                reservation = _save(mission_id, "running", steps)
                if reservation["status"] != "running":
                    return reservation
                last_action_at = time.monotonic()
                try:
                    receipt = (
                        reality_mesh.launch_exact_windows_app(app)
                        if node_id == "windows"
                        else reality_mesh.launch_exact_mac_app(node_id, app)
                    )
                    step["receipt"] = str(receipt.get("status") or "unknown")[:100]
                except (reality_mesh.NodeUnavailable, ValueError) as exc:
                    step["receipt"] = (
                        "Launch response unavailable: " + type(exc).__name__
                        + "; action MAY have occurred. Never retry automatically."
                    )
            else:
                steps.append(step)
                step["receipt"] = "Process observed running BEFORE mission; no launch attempted."
            if get(mission_id)["status"] != "running":
                step["result"] = "unverified"
                _save(mission_id, "revoked", steps,
                      "Revoked while an external action may have been in progress.")
                return get(mission_id)
            try:
                after = reality_mesh.exact_app_observations(node_id)
                # Require an independently observed, newer source timestamp.
                post_time = _require_fresh_evidence(after, node_id)
                if post_time <= pre_time:
                    raise reality_mesh.NodeUnavailable("Verifier timestamp not newer.")
                step["after_state"] = after["apps"].get(app, "unknown")
                step["after_observed_at"] = after["observed_at"]
                step["source"] = after["source"]
                step["result"] = (
                    "already_running" if before == "running"
                    and step["after_state"] == "running"
                    else "verified_running" if step["after_state"] == "running"
                    else "unverified"
                )
            except (reality_mesh.NodeUnavailable, ValueError, KeyError, TypeError):
                step["result"] = "unverified"
                step["receipt"] += "; independent follow-up unavailable"
            _save(mission_id, "running", steps)
        status = (
            "verified_apps" if len(steps) == len(apps) and
            all(s["result"] in {"already_running", "verified_running"} for s in steps)
            else "partial_or_unverified"
        )
        return _save(mission_id, status, steps)
    except (reality_mesh.NodeUnavailable, MissionBlocked, ValueError) as exc:
        return _save(mission_id, "blocked", steps,
                     type(exc).__name__ + ": fresh exact-device evidence unavailable")
