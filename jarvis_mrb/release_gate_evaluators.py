"""Machine-derived checks for criteria.md gates, registered with release_gates.

Each evaluator reads only durable runtime stores written by the *running*
system during the acceptance session window (session.started_at → now).  They
never call providers, never write, and never accept a caller-supplied claim as
evidence.  Checks that need a human observation (a light visibly changing, a
banner on the phone) are enforced separately as attestations.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jarvis_mrb.world_model as world_model
from jarvis_mrb.release_gates import _check, register_evaluator


def _ro(path: Path) -> sqlite3.Connection | None:
    if not Path(path).exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _world() -> sqlite3.Connection | None:
    return _ro(Path(world_model.DB_PATH))


def _since(session: dict[str, Any]) -> str:
    return str(session["started_at"])


def _local_since(session: dict[str, Any]) -> str:
    return str(session.get("started_at_local") or session["started_at"])


def _events(session: dict[str, Any], *, source_kinds: tuple[str, ...] = (), event_types: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    conn = _world()
    if conn is None:
        return []
    baseline = int((session.get("baseline") or {}).get("world_event_id") or 0)
    clauses, params = ["id>?"], [baseline]
    if source_kinds:
        clauses.append(f"source_kind IN ({','.join('?' for _ in source_kinds)})")
        params.extend(source_kinds)
    if event_types:
        clauses.append(f"event_type IN ({','.join('?' for _ in event_types)})")
        params.extend(event_types)
    with closing(conn):
        rows = conn.execute(
            f"SELECT id,event_type,source_kind,source_ref,summary,occurred_at,recorded_at FROM events "
            f"WHERE {' AND '.join(clauses)} ORDER BY id LIMIT 5000",
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------- C08

def _c08(session: dict[str, Any]) -> list[dict[str, Any]]:
    dormant = _events(session, event_types=("agency.dormant",))
    woke = _events(session, event_types=("desired_state.reactivated",))
    return [
        _check("Agency itself placed a goal into an explicit dormant/watch state during the session",
               bool(dormant), [e["summary"] for e in dormant][:5]),
        _check("a dormant goal was reactivated by its persisted wake condition",
               bool(woke) and bool(dormant) and woke[-1]["id"] > dormant[0]["id"],
               [e["summary"] for e in woke][:5]),
    ]


# --------------------------------------------------------------------------- C12

def _c12(session: dict[str, Any]) -> list[dict[str, Any]]:
    from jarvis_mrb.cloud_cognition import durable_telemetry

    started = datetime.fromisoformat(_since(session))
    rows = durable_telemetry(since_epoch=int(started.timestamp()))
    routes = [r for r in rows if r.get("event") == "route"]
    tiers = {str(r.get("tier")) for r in routes}
    results = [r for r in rows if r.get("event") == "cloud_result" and r.get("provider") == "groq"]
    fallbacks = [r for r in rows if r.get("event") == "cloud_fallback"]
    redacted = [r for r in routes if int(r.get("redactions") or 0) > 0]
    executed = [r for r in rows if r.get("event") == "execution_outcome" and r.get("proposal_tool")]
    try:
        from jarvis_mrb.permissions import TOOL_RISK
        protected = [r for r in executed if TOOL_RISK.get(str(r.get("proposal_tool")), "security") != "read"]
    except Exception:
        protected = []
    return [
        _check("deterministic, local and cloud tiers were each selected by routing", {"deterministic", "local", "cloud"} <= tiers,
               sorted(tiers)),
        _check("a real Groq structured proposal was resolved through the device-credential path (/cloud-cognition/resolve)",
               bool(results), results[-3:]),
        _check("a real cloud failure/unavailability fell back to local Jarvis and was reported", bool(fallbacks), fallbacks[-3:]),
        _check("a seeded credential-like secret was redacted on the real compile path", bool(redacted),
               [{k: r.get(k) for k in ("request_fingerprint", "redactions")} for r in redacted][-3:]),
        _check("a cloud proposal for a protected tool entered the normal execution boundary", bool(protected),
               [{k: r.get(k) for k in ("proposal_tool", "execution_ok")} for r in protected][-3:]),
    ]


# --------------------------------------------------------------------------- C16

def _c16(session: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from jarvis_mrb.world_armor_platform import _dbpath
        path = _dbpath(None)
    except Exception:
        return [_check("World Armor platform store readable", False, "unavailable")]
    conn = _ro(path)
    if conn is None:
        return [_check("World Armor platform store exists", False, str(path))]
    since = _since(session)
    with closing(conn):
        ok_rows = conn.execute(
            """SELECT DISTINCT g.id,g.kind,g.label,g.latitude,g.longitude,g.state FROM source_checks c
               JOIN source_grants g ON g.id=c.source_id WHERE c.checked_at>=? AND c.status='ok'""",
            (since,),
        ).fetchall()
        evidence = conn.execute(
            "SELECT DISTINCT source_id FROM source_evidence WHERE received_at>=?", (since,)
        ).fetchall()
        bad = conn.execute(
            "SELECT DISTINCT source_id,status FROM source_checks WHERE checked_at>=? AND status<>'ok' "
            "AND status<>'unchanged_published_frame'", (since,)
        ).fetchall()
        halted = conn.execute("SELECT id,label,state FROM source_grants WHERE state IN ('paused','stopped')").fetchall()
    with_evidence = {str(r[0]) for r in evidence}
    live = [dict(r) for r in ok_rows if str(r["id"]) in with_evidence]
    kinds = {str(r["kind"]) for r in live}

    def far_apart(items: list[dict[str, Any]]) -> bool:
        points = [(r["latitude"], r["longitude"]) for r in items if r["latitude"] is not None and r["longitude"] is not None]
        for i, a in enumerate(points):
            for b in points[i + 1:]:
                if abs(a[0] - b[0]) > 5 or abs(a[1] - b[1]) > 5:
                    return True
        return False

    return [
        _check("at least three enrolled public sources returned real media interpreted during the session",
               len(live) >= 3, [r["label"] for r in live]),
        _check("at least two distinct publisher/provider mechanisms", len(kinds) >= 2, sorted(kinds)),
        _check("at least two geographic regions", far_apart(live), [(r["label"], r["latitude"], r["longitude"]) for r in live]),
        _check("at least one arbitrary operator-enrolled public media source (not a fixed catalog)",
               any(str(r["kind"]) in {"public_https", "public_http"} for r in live), sorted(kinds)),
        _check("at least one source failed, went stale or was unavailable during the campaign",
               bool(bad), [dict(r) for r in bad][:10]),
        _check("pause/stop exercised on an enrolled source", bool(halted), [dict(r) for r in halted][:10]),
    ]


# --------------------------------------------------------------------------- C17

PLACE_PROVIDER_SOURCES = ("nws_alerts", "open_meteo_air", "usgs_earthquakes", "opensky")


def _c17(session: dict[str, Any]) -> list[dict[str, Any]]:
    observed = {e["source_kind"] for e in _events(session, source_kinds=PLACE_PROVIDER_SOURCES)
                if e["event_type"] != "world.provider_unavailable"}
    gaps = _events(session, event_types=("world.provider_unavailable",))
    checks = [
        _check(f"real {provider} request recorded with provenance through normal Jarvis use",
               provider in observed, provider)
        for provider in PLACE_PROVIDER_SOURCES
    ]
    checks.append(_check("at least one real unavailable/no-data/degraded provider case recorded as a gap",
                         bool(gaps), [e["summary"] for e in gaps][:5]))
    return checks


# --------------------------------------------------------------------------- C18

def _protected_duplicates(session: dict[str, Any]) -> list[dict[str, Any]]:
    conn = _world()
    if conn is None:
        return []
    from jarvis_mrb.permissions import TOOL_RISK
    protected = [name for name, risk in TOOL_RISK.items() if risk in {"external_write", "destructive"}]
    with closing(conn):
        rows = conn.execute(
            f"""SELECT tool,arguments_json,COUNT(*) AS n FROM action_verifications
                WHERE created_at>=? AND tool IN ({','.join('?' for _ in protected)})
                GROUP BY tool,arguments_json HAVING n>1""",
            (_local_since(session), *protected),
        ).fetchall()
    return [dict(row) for row in rows]


def _c18(session: dict[str, Any]) -> list[dict[str, Any]]:
    from jarvis_mrb.release_gates import service_identity
    from jarvis_mrb.world_armor_push import PUSH_STORE

    since = _since(session)
    conn = _ro(PUSH_STORE)
    sent, duplicates, token_events = [], [], []
    if conn is not None:
        with closing(conn):
            sent = [dict(r) for r in conn.execute(
                "SELECT event_id,title,created_at,attempts FROM push_outbox WHERE state='sent' AND created_at>=?", (since,))]
            duplicates = [dict(r) for r in conn.execute(
                "SELECT device_id,body,COUNT(*) AS n FROM push_outbox WHERE created_at>=? GROUP BY device_id,body HAVING n>1",
                (since,))]
            token_events = [dict(r) for r in conn.execute(
                "SELECT id,enabled,last_failure_reason,updated_at FROM push_devices WHERE updated_at>=? AND "
                "(enabled=0 OR last_failure_reason<>'')", (since,))]
    baseline_boot = (session.get("baseline") or {}).get("service_boot_id")
    service = service_identity()
    try:
        from jarvis_mrb.world_armor_watchdog import status as watchdog_status
        watchdog = watchdog_status()
    except Exception as exc:
        watchdog = {"error": type(exc).__name__}
    restarts = int(watchdog.get("restart_count") or 0)
    duplicates_protected = _protected_duplicates(session)
    from jarvis_mrb.release_gates import client_builds
    push_builds = [c for c in client_builds(since=session["started_at"])
                   if c["build_sha"] == session["sha"] and "[PersonalTeam]" not in str(c.get("model") or "")]
    return [
        _check("the push-entitled (paid team) iPhone build of the frozen SHA was used", bool(push_builds),
               [c.get("model") for c in push_builds][:3]),
        _check("APNs accepted at least one warning/urgent Jarvis push during the session (transport only)",
               bool(sent), sent[-5:]),
        _check("no duplicate user-level notification for the same content/device", not duplicates, duplicates[:5]),
        _check("invalid/revoked device-token handling exercised (device disabled or APNs failure recorded)",
               bool(token_events), token_events[:5]),
        _check("the supervised live collector was restarted by the watchdog after an induced failure",
               restarts > 0, {k: watchdog.get(k) for k in ("restart_count", "state", "child_pid", "updated_at", "error")}),
        _check("the Windows Jarvis service restarted during the session and came back healthy",
               bool(baseline_boot) and bool(service.get("reachable")) and service.get("boot_id") not in {None, baseline_boot},
               {"baseline_boot": baseline_boot, "current_boot": service.get("boot_id")}),
        _check("no duplicate protected action caused by recovery", not duplicates_protected, duplicates_protected[:5]),
    ]


# --------------------------------------------------------------------------- C19

def _c19(session: dict[str, Any]) -> list[dict[str, Any]]:
    from jarvis_mrb.world_armor_full import FULL_STORE

    since = _since(session)
    conn = _ro(FULL_STORE)
    if conn is None:
        return [_check("Presence store exists", False, str(FULL_STORE))]
    with closing(conn):
        receipts = [dict(r) for r in conn.execute(
            """SELECT r.id,r.status,r.requested_state,r.requested_at,r.completed_at,g.target_id,g.target_label,
                      g.max_uses,g.use_count,g.expires_at,g.created_at
               FROM presence_receipts r JOIN presence_grants g ON g.id=r.grant_id
               WHERE r.requested_at>=? ORDER BY r.requested_at""", (since,))]
        denials = [dict(r) for r in conn.execute(
            "SELECT grant_id,target_id,denied_at,reason FROM presence_denials WHERE denied_at>=? ORDER BY denied_at", (since,))]
    verified = [r for r in receipts if r["status"] == "verified_reported_state"]
    bounded = all(
        int(r["max_uses"]) <= 20
        and (datetime.fromisoformat(r["expires_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds() <= 3600
        for r in receipts
    )
    later_denial = bool(verified) and any(
        d["target_id"] == verified[0]["target_id"] and d["denied_at"] > verified[0]["requested_at"] for d in denials
    )
    readbacks = _events(session, event_types=("presence.homekit_readback",))
    non_success = [r for r in receipts if r["status"] in {"failed", "blocked", "unverified"}]
    return [
        _check("an exact, short-lived, use-bounded grant was used", bool(receipts) and bounded,
               [{k: r[k] for k in ("target_label", "max_uses", "created_at", "expires_at")} for r in receipts][:5]),
        _check("dispatch started unverified and became verified only by fresh HomeKit readback",
               bool(verified) and bool(readbacks), {"verified": verified[:3], "readback_events": len(readbacks)}),
        _check("an exhausted/expired/revoked grant then refused another actuation of the same light",
               later_denial, denials[:5]),
        _check("a failure/unreachable accessory produced failed/blocked/unverified rather than success",
               bool(non_success), non_success[:5]),
    ]


# --------------------------------------------------------------------------- C20

SEEDED_SECRET = "sk-" + "JARVISC20SEEDED" + "0123456789abcdef"


def _service_base() -> tuple[str, str]:
    from jarvis_mrb.server_config import load_server_config

    config = load_server_config()
    host = config.bind_host if config.bind_host not in {"0.0.0.0", "::", ""} else "127.0.0.1"
    return f"http://{host}:{config.port}", config.api_token


def _c20(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Live negative probes against the running service; every one must fail closed.

    The probes are deliberately unable to succeed legitimately (random grant,
    private/link-local targets, unknown node, wrong bearer), so they cannot
    cause an effect; they only prove the boundary on the deployed build.
    """
    import secrets

    import httpx

    base, token = _service_base()
    auth = {"Authorization": f"Bearer {token}"}
    checks: list[dict[str, Any]] = []

    def call(method: str, path: str, **kwargs: Any) -> tuple[int, str]:
        try:
            response = httpx.request(method, base + path, timeout=20.0, **kwargs)
            return response.status_code, response.text
        except httpx.HTTPError as exc:
            return -1, f"{type(exc).__name__}: {exc}"[:300]

    missing = call("GET", "/release/identity")
    wrong = call("GET", "/release/identity", headers={"Authorization": "Bearer wrong-" + secrets.token_hex(8)})
    checks.append(_check("missing and wrong Jarvis bearer are rejected", bool(token) and missing[0] == 401 and wrong[0] == 401,
                         {"missing": missing[0], "wrong": wrong[0], "token_configured": bool(token)}))

    grant = secrets.token_hex(16)
    presence = call("POST", "/world-armor/v8/presence/dispatch", headers=auth, json={"grant_id": grant, "desired_on": True})
    checks.append(_check("unknown/expired/revoked Presence grant cannot actuate", presence[0] in {404, 409, 422, 503},
                         {"status": presence[0], "detail": presence[1][:200]}))

    statuses = {}
    for url in ("http://192.168.1.10/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/"):
        statuses[url] = call("POST", "/world-armor/v1/cameras/page-media", headers=auth, json={"public_url": url})
    checks.append(_check("private, loopback and link-local camera/media targets are rejected",
                         all(code in {400, 403, 422, 503} for code, _ in statuses.values()),
                         {url: code for url, (code, _) in statuses.items()}))
    checks.append(_check("at least one disabled feature flag fails closed (503) on the deployed build",
                         any(code == 503 for code, _ in (*statuses.values(), presence)),
                         "if every feature is enabled, disable one flag for this probe and rerun"))

    node = call("POST", "/mesh/screen/begin", headers=auth, json={"node_id": "not-a-paired-node", "duration_seconds": 30})
    checks.append(_check("an unknown paired-node ID cannot open a screen session", node[0] in {404, 422, 503},
                         {"status": node[0]}))

    prepared = call("POST", "/cloud-cognition/prepare", headers=auth, json={
        "text": f"cloud: review this deployment plan. api_key={SEEDED_SECRET} and compare two rollout options",
        "session_id": "c20-probe", "mode": "cloud"})
    compiled_ok = prepared[0] == 200 and SEEDED_SECRET not in prepared[1]
    try:
        body = json.loads(prepared[1]) if prepared[0] == 200 else {}
    except ValueError:
        body = {}
    redactions = int(((body.get("context_debug") or {}).get("redactions")) or 0)
    checks.append(_check("seeded API-key-like string is redacted from the real cloud compile path",
                         compiled_ok and redactions > 0, {"status": prepared[0], "redactions": redactions}))
    if body.get("task_id"):
        call("POST", "/cloud-cognition/fallback", headers=auth,
             json={"task_id": body["task_id"], "reason": "C20 probe: not sent to any provider"})

    leaked = []
    conn = _world()
    if conn is not None:
        with closing(conn):
            leaked = conn.execute(
                "SELECT id,source_kind FROM events WHERE summary LIKE ? OR evidence LIKE ? OR payload_json LIKE ? LIMIT 5",
                (f"%{SEEDED_SECRET}%",) * 3,
            ).fetchall()
    from jarvis_mrb.cloud_cognition import durable_telemetry
    tele = [r for r in durable_telemetry(limit=20000) if SEEDED_SECRET in json.dumps(r)]
    checks.append(_check("seeded secret is absent from the world journal, Reality Graph events and routing telemetry",
                         not leaked and not tele, {"events": [dict(r) for r in leaked], "telemetry_rows": len(tele)}))
    return checks


# --------------------------------------------------------------------------- C21

def _c21(session: dict[str, Any]) -> list[dict[str, Any]]:
    from jarvis_mrb.release_soak import evaluate
    return evaluate(session)


for _gate, _fn in {
    "C08": _c08, "C12": _c12, "C16": _c16, "C17": _c17, "C18": _c18, "C19": _c19, "C20": _c20, "C21": _c21,
}.items():
    register_evaluator(_gate, _fn)
