"""Callless self-hosted identity, presence and WebRTC signaling API.

The hub is the rendezvous server. It does not record or relay microphone media.
Clients on separate machines must use the SAME hub URL; remote microphone access
requires HTTPS/WSS and ICE/TURN support. One process owns ephemeral socket state.

Session lifecycle (see ``callless_session``): requested -> ringing | authorized
-> signaling -> media_connected -> ended(reason) | failed(reason). A WebSocket
being open or SDP/ICE being relayed is signaling, not audio: the hub reports
``media_connected`` only after BOTH clients attest live inbound audio.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from jarvis_mrb import callless_session as machine
from jarvis_mrb.callless_core import CalllessError, CalllessStore
from jarvis_mrb.callless_session import Session

router = APIRouter()
store = CalllessStore()
connections: dict[int, WebSocket] = {}
client_caps: dict[int, set[str]] = {}
armed: set[int] = set()          # users whose client armed microphone consent on this socket
sessions: dict[str, Session] = {}
session_lock = asyncio.Lock()
failures: dict[str, deque[float]] = defaultdict(deque)
MEDIA_CAP = "media-v1"           # client reports media truthfully and plays tones
_hub_loop: asyncio.AbstractEventLoop | None = None
UNREACHABLE = "Contact is not currently reachable."


def _secure(request) -> bool:
    host = request.client.host if request.client else ""
    return request.url.scheme in {"https", "wss"} or host in {"127.0.0.1", "::1"}


def _require_secure(request: Request) -> None:
    if not _secure(request):
        raise HTTPException(status_code=403, detail="Callless accounts and audio require HTTPS outside localhost.")


def _auth(token: str | None) -> dict:
    prefix = "Bearer "
    if not token or not token.startswith(prefix):
        raise HTTPException(status_code=401, detail="Callless sign-in required.")
    user = store.authenticate(token[len(prefix):])
    if user is None:
        raise HTTPException(status_code=401, detail="Callless session expired.")
    return user


def _limit_login(request: Request) -> None:
    addr = (request.client.host if request.client else "unknown")[:128]
    now = time.monotonic()
    bucket = failures[addr]
    while bucket and bucket[0] < now - 60:
        bucket.popleft()
    if len(bucket) >= 8:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts; retry later.")
    bucket.append(now)


# Account and bearer-token requests require TLS outside localhost.
api_router = APIRouter(prefix="/callless/v1", dependencies=[Depends(_require_secure)])


class Credentials(BaseModel):
    handle: str = Field(max_length=28)
    password: str = Field(max_length=256)
    name: str = Field(default="", max_length=70)


class PresenceRequest(BaseModel):
    status: str


class InviteRequest(BaseModel):
    code: str = Field(max_length=128)


class ContactRequest(BaseModel):
    handle: str = Field(max_length=28)
    blocked: bool = True


class GrantRequest(BaseModel):
    handle: str = Field(max_length=28)
    level: str = Field(max_length=8)


class SessionRequest(BaseModel):
    target: str = Field(max_length=28)


async def _emit(user_id: int, message: dict) -> bool:
    ws = connections.get(user_id)
    if ws is None:
        return False
    try:
        await ws.send_json(message)
        return True
    except Exception:
        if connections.get(user_id) is ws:
            connections.pop(user_id, None)
        return False


# --------------------------------------------------------------------------
# Hub session helpers
# --------------------------------------------------------------------------

def _state_message(s: Session) -> dict:
    return {"type": "state", "session_id": s.sid, **s.snapshot()}


async def _notify_state(s: Session) -> None:
    message = _state_message(s)
    for uid in s.participants():
        await _emit(uid, message)


def _violation(s: Session) -> str | None:
    """Reason this session is no longer authorized right now, or None."""
    if not store.permitted(s.caller, s.callee):
        return "revoked"
    level = store.effective_access(s.caller, s.callee)
    if level == "closed":
        return "unavailable" if store.user_status(s.callee) == "closed" else "revoked"
    if s.access == "open" and level != "open":
        return "revoked"
    return None


async def _finish(sid: str, reason: str) -> Session | None:
    """End a session exactly once and tell BOTH parties, whatever the reason."""
    s = sessions.pop(sid, None)
    if s is None:
        return None
    watchdog = s.watchdog
    if isinstance(watchdog, asyncio.Task) and watchdog is not asyncio.current_task():
        watchdog.cancel()
    terminal = s.finish(reason)
    try:
        store.log_session({"sid": s.sid, "caller_id": s.caller, "callee_id": s.callee,
                           "access": s.access, "requested": s.created_wall, "state": terminal,
                           "reason": reason, "authorized_ms": s.elapsed_ms("authorized"),
                           "connect_ms": s.connect_ms, "duration_ms": s.duration_ms()})
    except sqlite3.Error:
        pass   # metadata only; never block teardown
    message = {"type": "ended", "session_id": sid, "reason": reason, "state": terminal,
               "connect_ms": s.connect_ms}
    for uid in s.participants():
        await _emit(uid, message)
    return s


async def _enforce_all() -> None:
    """Re-check every live session against current grants, blocks and status."""
    for sid, s in list(sessions.items()):
        reason = _violation(s)
        if reason:
            await _finish(sid, reason)


async def _end_user_sessions(user_id: int, reason: str) -> None:
    for sid, s in list(sessions.items()):
        if user_id in s.participants():
            await _finish(sid, reason)


def _hangup_reason(s: Session, user_id: int, claimed: str | None) -> str:
    if s.state in ("requested", "ringing"):
        return "declined" if user_id == s.callee else "cancelled"
    return claimed if claimed in machine.CLIENT_REASONS else "hangup"


async def _watch(sid: str) -> None:
    """Bounded waits: unanswered ring, no media in time, or absolute max length."""
    while True:
            s = sessions.get(sid)
            if s is None:
                return
            now = time.monotonic()
            if s.state in ("requested", "ringing"):
                due, reason = s.marks[s.state] + machine.RING_TIMEOUT_SECONDS, "no_answer"
            elif s.state == "media_connected":
                due, reason = s.created + machine.MAX_SESSION_SECONDS, "timeout"
            else:
                start = s.marks[s.state] if s.ever_connected else s.marks.get("authorized", s.created)
                due, reason = start + machine.MEDIA_TIMEOUT_SECONDS, "timeout"
            if due <= now:
                await _finish(sid, reason)
                return
            await asyncio.sleep(min(due - now, 5.0))


def active_session_for(user_id: int) -> Session | None:
    for s in sessions.values():
        if user_id in s.participants() and s.live():
            return s
    return None


def request_end_for_user(user_id: int, reason: str = "hangup") -> str:
    """Thread-safe end request used by the backend voice handler.

    Returns "ended" (hub confirmed), "scheduled", "none" (nothing live) or
    "unavailable" (hub event loop not running in this process).
    """
    s = active_session_for(user_id)
    if s is None:
        return "none"
    loop = _hub_loop
    if loop is None or loop.is_closed():
        return "unavailable"
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        loop.create_task(_finish(s.sid, reason))
        return "scheduled"
    try:
        asyncio.run_coroutine_threadsafe(_finish(s.sid, reason), loop).result(timeout=5)
    except Exception:
        return "unavailable"
    return "ended"


# --------------------------------------------------------------------------
# Static client
# --------------------------------------------------------------------------

@router.get("/callless/")
def client_html() -> HTMLResponse:
    from importlib.resources import files
    content = files("jarvis_mrb").joinpath("callless_ui.html").read_text(encoding="utf-8")
    return HTMLResponse(content, headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
                                   "connect-src 'self' wss:; img-src 'self' data:; media-src 'self' blob:; "
                                   "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    })


@router.get("/callless/client.js")
def client_js() -> Response:
    from importlib.resources import files
    js = files("jarvis_mrb").joinpath("callless_ui.js").read_text(encoding="utf-8")
    return Response(content=js, media_type="text/javascript", headers={"Cache-Control": "no-store"})


@router.get("/callless/client.css")
def client_css() -> Response:
    from importlib.resources import files
    css = files("jarvis_mrb").joinpath("callless_ui.css").read_text(encoding="utf-8")
    return Response(content=css, media_type="text/css", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------
# Accounts, presence, contacts, grants
# --------------------------------------------------------------------------

@api_router.post("/register", status_code=201)
def register(request: Request, body: Credentials) -> dict:
    _require_secure(request)
    _limit_login(request)
    try:
        user, token = store.register(body.handle, body.name, body.password)
    except CalllessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "token": token}


@api_router.post("/login")
def login(request: Request, body: Credentials) -> dict:
    _require_secure(request)
    _limit_login(request)
    try:
        user, token = store.login(body.handle, body.password)
    except CalllessError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"user": user, "token": token}


@api_router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    _auth(authorization)
    store.logout(authorization[7:])
    return {"ok": True}


@api_router.get("/me")
def me(authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    return {"user": user, "online": user["id"] in connections, "armed": user["id"] in armed}


@api_router.put("/presence")
async def presence(body: PresenceRequest, authorization: str | None = Header(default=None)) -> dict:
    """Global status. Effective access is min(per-contact grant, global status)."""
    user = _auth(authorization)
    try:
        updated = store.set_status(user["id"], body.status)
    except CalllessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.status == "closed":
        # Close any ongoing sessions; client must explicitly re-open.
        await _end_user_sessions(user["id"], "unavailable")
    await _enforce_all()
    return {"user": updated}


@api_router.get("/contacts")
def contacts(authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    items = store.contacts(user["id"])
    for item in items:
        item["online"] = item["id"] in connections
    return {"contacts": items}


@api_router.post("/invite")
def invite(authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    return {"code": store.invitation(user["id"]), "expires_seconds": 900}


@api_router.post("/accept")
def accept(body: InviteRequest, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    try:
        added = store.accept_invitation(user["id"], body.code)
    except CalllessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"contact": added}


@api_router.put("/block")
async def block(body: ContactRequest, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    try:
        store.block(user["id"], body.handle, body.blocked)
    except CalllessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _enforce_all()     # blocking tears down any live session immediately
    return {"ok": True}


@api_router.put("/grants")
async def set_grant(body: GrantRequest, authorization: str | None = Header(default=None)) -> dict:
    """Set MY grant to a contact: what they may do when they request me.

    Directional: this says nothing about what that contact grants me.
    Lowering a grant immediately ends any session that depended on it.
    """
    user = _auth(authorization)
    try:
        level = store.set_grant(user["id"], body.handle, body.level)
    except CalllessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _enforce_all()
    return {"handle": body.handle.strip().lower(), "my_grant": level}


@api_router.get("/ice")
def ice(authorization: str | None = Header(default=None)) -> dict:
    _auth(authorization)
    # The default STUN server is not a relay. Operators can supply a TURN
    # configuration on trusted servers via CALLLESS_ICE_SERVERS_JSON.
    raw = os.environ.get("CALLLESS_ICE_SERVERS_JSON", "")
    servers = [{"urls": "stun:stun.l.google.com:19302"}]
    if raw:
        try:
            value = json.loads(raw)
            if isinstance(value, list) and len(value) <= 5:
                servers = value
        except (ValueError, TypeError):
            pass
    return {"ice_servers": servers}


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def _describe(s: Session, user_id: int) -> dict:
    outgoing = s.caller == user_id
    other = store.public_by_id(s.callee if outgoing else s.caller)
    return {"session_id": s.sid, "direction": "outgoing" if outgoing else "incoming",
            "peer": other["handle"] if other else None, "access": s.access,
            "requested_at": s.created_wall, **s.snapshot(), "live": True}


@api_router.get("/sessions/recent")
def recent_sessions(limit: int = 20, authorization: str | None = Header(default=None)) -> dict:
    """Per-user session metadata (no SDP/ICE/audio): state, reason and timings."""
    user = _auth(authorization)
    live = [_describe(s, user["id"]) for s in sessions.values() if user["id"] in s.participants()]
    return {"sessions": live + store.recent_sessions(user["id"], limit)}


@api_router.get("/sessions/{sid}")
def session_state(sid: str, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    s = sessions.get(sid)
    if s is None or user["id"] not in s.participants():
        raise HTTPException(status_code=404, detail="Session not found.")
    return _describe(s, user["id"])


@api_router.post("/sessions")
async def call(body: SessionRequest, authorization: str | None = Header(default=None)) -> dict:
    """Request a conversation. Refusals other than "no such contact" and
    "you are busy" share one message so closed, blocked-by-them, unsupported
    and offline are indistinguishable to the requester."""
    user = _auth(authorization)
    peer = store.lookup(body.target)
    if peer and peer["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot connect to yourself.")
    if not peer or not store.has_contact(user["id"], peer["id"]):
        raise HTTPException(status_code=404, detail="No approved contact with that handle.")
    if user["id"] not in connections or MEDIA_CAP not in client_caps.get(user["id"], set()):
        raise HTTPException(status_code=409, detail="Open an up-to-date Callless client in a connected browser tab first.")
    level = store.effective_access(user["id"], peer["id"])
    if level == "closed" or peer["id"] not in connections or MEDIA_CAP not in client_caps.get(peer["id"], set()):
        raise HTTPException(status_code=409, detail=UNREACHABLE)
    # open => no ring, but only once the receiver's client armed mic consent on
    # this socket. Otherwise the receiver is asked, never connected silently.
    access = "open" if level == "open" and peer["id"] in armed else "ask"
    global _hub_loop
    _hub_loop = asyncio.get_running_loop()
    async with session_lock:
        for stale_id, existing in list(sessions.items()):
            if time.monotonic() - existing.created > machine.MAX_SESSION_SECONDS:
                await _finish(stale_id, "timeout")
        for existing in sessions.values():
            if {user["id"], peer["id"]} & set(existing.participants()):
                raise HTTPException(status_code=409, detail="One participant is already in a session.")
        sid = secrets.token_urlsafe(24)
        s = Session(sid=sid, caller=user["id"], callee=peer["id"], access=access)
        s.advance("authorized" if access == "open" else "ringing")
        sessions[sid] = s
    delivered = await _emit(peer["id"], {"type": "incoming", "session_id": sid, "from": user["handle"],
                                         "name": user["name"], "state": s.state, "access": access})
    if not delivered:
        sessions.pop(sid, None)
        raise HTTPException(status_code=409, detail=UNREACHABLE)
    s.watchdog = asyncio.get_running_loop().create_task(_watch(sid))
    return {"session_id": sid, "state": s.state, "contact": peer["handle"]}


@api_router.post("/sessions/{sid}/accept")
async def accept_call(sid: str, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    s = sessions.get(sid)
    if not s or s.callee != user["id"] or s.state != "ringing":
        raise HTTPException(status_code=404, detail="No pending request.")
    reason = _violation(s)
    if reason:
        await _finish(sid, reason)
        raise HTTPException(status_code=404, detail="No pending request.")
    s.advance("authorized")
    await _notify_state(s)
    return {"session_id": sid, "state": s.state}


@api_router.post("/sessions/{sid}/end")
async def end_call(sid: str, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    s = sessions.get(sid)
    if not s or user["id"] not in s.participants():
        raise HTTPException(status_code=404, detail="Session not found.")
    await _finish(sid, _hangup_reason(s, user["id"], None))
    return {"ok": True}


@router.websocket("/callless/v1/socket")
async def socket_channel(ws: WebSocket) -> None:
    global _hub_loop
    if not _secure(ws):
        await ws.close(code=4403)
        return
    origin = ws.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.netloc.lower() != ws.headers.get("host", "").lower():
            await ws.close(code=4403)
            return
    await ws.accept()
    _hub_loop = asyncio.get_running_loop()
    user = None
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=8)
        if not isinstance(first, dict) or first.get("type") != "auth":
            await ws.close(code=4401)
            return
        user = store.authenticate(str(first.get("token") or ""))
        if user is None:
            await ws.close(code=4401)
            return
        raw_caps = first.get("caps")
        caps = {str(c)[:32] for c in raw_caps[:8]} if isinstance(raw_caps, list) else set()
        previous = connections.get(user["id"])
        if previous is not None and previous is not ws:
            # A second tab/device takes over: the first one's audio is gone.
            await _end_user_sessions(user["id"], "peer_left")
        connections[user["id"]] = ws
        client_caps[user["id"]] = caps
        armed.discard(user["id"])
        if previous is not None and previous is not ws:
            await previous.close(code=4000)
        await ws.send_json({"type": "ready", "user": user, "features": {"media": MEDIA_CAP in caps}})
        while True:
            data = await ws.receive_json()
            if not isinstance(data, dict) or len(json.dumps(data)) > 35000:
                await ws.close(code=1009)
                break
            kind = data.get("type")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
                continue
            if kind == "arm":
                if data.get("armed") is True:
                    armed.add(user["id"])
                else:
                    armed.discard(user["id"])
                await ws.send_json({"type": "armed", "armed": user["id"] in armed})
                continue
            if kind not in {"signal", "hangup", "media", "mute"}:
                continue
            sid = str(data.get("session_id") or "")
            s = sessions.get(sid)
            if not s or user["id"] not in s.participants():
                continue
            if kind == "hangup":
                claimed = data.get("reason") if isinstance(data.get("reason"), str) else None
                await _finish(sid, _hangup_reason(s, user["id"], claimed))
                continue
            # Every later message re-checks authorization, so a revoked grant
            # or block also rejects in-flight offers and media reports.
            reason = _violation(s)
            if reason is None and time.monotonic() - s.created > machine.MAX_SESSION_SECONDS:
                reason = "timeout"
            if reason:
                await _finish(sid, reason)
                continue
            if s.state not in ("authorized", "signaling", "media_connected"):
                continue
            if kind == "signal":
                payload = data.get("payload")
                if not isinstance(payload, dict) or payload.get("type") not in {"ready", "offer", "answer", "candidate", "restart"}:
                    continue
                if s.state == "authorized" and s.advance("signaling"):
                    await _notify_state(s)
                await _emit(s.peer_of(user["id"]), {"type": "signal", "session_id": sid, "payload": payload})
            elif kind == "media":
                report = data.get("state")
                if report in ("connected", "lost"):
                    if s.report_media(user["id"], report == "connected"):
                        await _notify_state(s)
                elif report == "failed":
                    claimed = data.get("reason") if isinstance(data.get("reason"), str) else "network"
                    await _finish(sid, claimed if claimed in machine.CLIENT_REASONS and claimed != "hangup" else "network")
            elif kind == "mute":
                muted = data.get("muted") is True
                s.muted[user["id"]] = muted
                await _emit(s.peer_of(user["id"]), {"type": "peer_muted", "session_id": sid, "muted": muted})
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, KeyError, TypeError):
        pass
    finally:
        if user and connections.get(user["id"]) is ws:
            connections.pop(user["id"], None)
            client_caps.pop(user["id"], None)
            armed.discard(user["id"])
            await _end_user_sessions(user["id"], "peer_left")

# Import and mount api_router alongside router at the application level.
# Avoid nested includes so service.app.routes contains only concrete routes.
