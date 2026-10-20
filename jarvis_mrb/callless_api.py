"""Callless self-hosted identity, presence and WebRTC signaling API.

The hub is the rendezvous server. It does not record or relay microphone media.
Clients on separate machines must use the SAME hub URL; remote microphone access
requires HTTPS/WSS and ICE/TURN support. One process owns ephemeral socket state.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from jarvis_mrb.callless_core import CalllessError, CalllessStore

router = APIRouter()
store = CalllessStore()
connections: dict[int, WebSocket] = {}
sessions: dict[str, dict] = {}
session_lock = asyncio.Lock()
failures: dict[str, deque[float]] = defaultdict(deque)


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
    return {"user": user, "online": user["id"] in connections}


@api_router.put("/presence")
async def presence(body: PresenceRequest, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    try:
        updated = store.set_status(user["id"], body.status)
    except CalllessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.status == "closed":
        # Close any ongoing sessions; client must explicitly re-open.
        for sid, session in list(sessions.items()):
            if user["id"] in (session["caller"], session["callee"]):
                peer = session["callee"] if session["caller"] == user["id"] else session["caller"]
                sessions.pop(sid, None)
                await _emit(peer, {"type": "ended", "session_id": sid, "reason": "unavailable"})
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
    peer = store.lookup(body.handle)
    if peer and body.blocked:
        for sid, session in list(sessions.items()):
            if {session["caller"], session["callee"]} == {user["id"], peer["id"]}:
                sessions.pop(sid, None)
                await _emit(peer["id"], {"type": "ended", "session_id": sid, "reason": "unavailable"})
    return {"ok": True}


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


@api_router.post("/sessions")
async def call(body: SessionRequest, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    peer = store.lookup(body.target)
    if not peer or not store.permitted(user["id"], peer["id"]):
        raise HTTPException(status_code=404, detail="No approved contact with that handle.")
    if user["id"] not in connections:
        raise HTTPException(status_code=409, detail="Open Callless in a connected browser tab first.")
    if peer["id"] not in connections or peer["status"] == "closed":
        raise HTTPException(status_code=409, detail="Contact is not currently reachable.")
    if peer["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot connect to yourself.")
    async with session_lock:
        for stale_id, existing in list(sessions.items()):
            if time.monotonic() - existing["created"] > 4 * 3600:
                sessions.pop(stale_id, None)
        for existing in sessions.values():
            if user["id"] in (existing["caller"], existing["callee"]) or peer["id"] in (existing["caller"], existing["callee"]):
                raise HTTPException(status_code=409, detail="One participant is already in a session.")
        sid = secrets.token_urlsafe(24)
        status = "connected" if peer["status"] == "open" else "pending"
        sessions[sid] = {"caller": user["id"], "callee": peer["id"], "status": status, "created": time.monotonic()}
    delivered = await _emit(peer["id"], {"type": "incoming", "session_id": sid, "from": user["handle"], "status": status})
    if not delivered:
        sessions.pop(sid, None)
        raise HTTPException(status_code=409, detail="Contact disconnected.")
    return {"session_id": sid, "status": status, "contact": peer["handle"]}


@api_router.post("/sessions/{sid}/accept")
async def accept_call(sid: str, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    session = sessions.get(sid)
    if not session or session["callee"] != user["id"] or session["status"] != "pending":
        raise HTTPException(status_code=404, detail="No pending request.")
    session["status"] = "connected"
    await _emit(session["caller"], {"type": "accepted", "session_id": sid})
    return {"session_id": sid, "status": "connected"}


@api_router.post("/sessions/{sid}/end")
async def end_call(sid: str, authorization: str | None = Header(default=None)) -> dict:
    user = _auth(authorization)
    session = sessions.get(sid)
    if not session or user["id"] not in (session["caller"], session["callee"]):
        raise HTTPException(status_code=404, detail="Session not found.")
    sessions.pop(sid, None)
    peer = session["callee"] if session["caller"] == user["id"] else session["caller"]
    await _emit(peer, {"type": "ended", "session_id": sid})
    return {"ok": True}


@router.websocket("/callless/v1/socket")
async def socket_channel(ws: WebSocket) -> None:
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
        previous = connections.get(user["id"])
        connections[user["id"]] = ws
        if previous is not None and previous is not ws:
            await previous.close(code=4000)
        await ws.send_json({"type": "ready", "user": user})
        while True:
            data = await ws.receive_json()
            if not isinstance(data, dict) or len(json.dumps(data)) > 35000:
                await ws.close(code=1009)
                break
            kind = data.get("type")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
                continue
            if kind not in {"signal", "hangup"}:
                continue
            sid = str(data.get("session_id") or "")
            session = sessions.get(sid)
            if not session or user["id"] not in (session["caller"], session["callee"]):
                continue
            if kind == "hangup":
                sessions.pop(sid, None)
                peer = session["callee"] if user["id"] == session["caller"] else session["caller"]
                await _emit(peer, {"type": "ended", "session_id": sid})
                continue
            if session["status"] != "connected" or time.monotonic() - session["created"] > 4 * 3600:
                continue
            if not store.permitted(session["caller"], session["callee"]):
                continue
            payload = data.get("payload")
            if not isinstance(payload, dict) or payload.get("type") not in {"ready", "offer", "answer", "candidate"}:
                continue
            peer = session["callee"] if user["id"] == session["caller"] else session["caller"]
            await _emit(peer, {"type": "signal", "session_id": sid, "payload": payload})
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, KeyError, TypeError):
        pass
    finally:
        if user and connections.get(user["id"]) is ws:
            connections.pop(user["id"], None)
            for sid, session in list(sessions.items()):
                if user["id"] in (session["caller"], session["callee"]):
                    sessions.pop(sid, None)
                    peer = session["callee"] if user["id"] == session["caller"] else session["caller"]
                    await _emit(peer, {"type": "ended", "session_id": sid, "reason": "disconnected"})

# Import and mount api_router alongside router at the application level.
# Avoid nested includes so service.app.routes contains only concrete routes.
