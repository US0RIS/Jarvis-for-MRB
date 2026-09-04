from __future__ import annotations

import threading
import time
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.conversation import append_message, recent_messages
from jarvis_mrb.email_policy import get_allowed_recipients, set_allowed_recipients
from jarvis_mrb.jobs import run_due_jobs, trigger_event
from jarvis_mrb.server_config import load_server_config

_CONFIG = load_server_config()
BIND_HOST = _CONFIG.bind_host
PORT = _CONFIG.port
API_TOKEN = _CONFIG.api_token

app = FastAPI(title="Jarvis for MRB", version="0.8.0")
_scheduler_started = False


class CommandRequest(BaseModel):
    text: str
    session_id: str | None = None


class CommandResponse(BaseModel):
    ok: bool
    message: str


class EventRequest(BaseModel):
    event: str


class EmailAllowlistRequest(BaseModel):
    addresses: list[str]


class EmailAllowlistResponse(BaseModel):
    addresses: list[str]


def _check_auth(authorization: str | None) -> None:
    if not API_TOKEN:
        return
    expected = f"Bearer {API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid Jarvis API token")


def _execute_job(command: str) -> str:
    # Background jobs are intentionally stateless. They should not absorb or
    # contaminate the user's live conversational context.
    reply = handle_natural_language(command)
    return reply.message


def _scheduler_loop() -> None:
    while True:
        try:
            run_due_jobs(_execute_job)
        except Exception:
            pass
        time.sleep(1.0)


def _ensure_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    threading.Thread(target=_scheduler_loop, name="jarvis-scheduler", daemon=True).start()


@app.on_event("startup")
def startup() -> None:
    _ensure_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.8.0", "bind": BIND_HOST}


@app.post("/command", response_model=CommandResponse)
def command(request: CommandRequest, authorization: Annotated[str | None, Header()] = None) -> CommandResponse:
    _check_auth(authorization)
    session_id = request.session_id or "default"
    history = recent_messages(session_id, limit=20)
    reply = handle_natural_language(request.text, history=history)
    append_message(session_id, "user", request.text)
    if reply.message and reply.message != "__EXIT__":
        append_message(session_id, "assistant", reply.message)
    return CommandResponse(ok=reply.ok, message=reply.message)


@app.post("/event", response_model=CommandResponse)
def event(request: EventRequest, authorization: Annotated[str | None, Header()] = None) -> CommandResponse:
    _check_auth(authorization)
    result = trigger_event(request.event, _execute_job)
    return CommandResponse(ok=result.ok, message=result.message)


@app.get("/settings/email-allowlist", response_model=EmailAllowlistResponse)
def get_email_allowlist(authorization: Annotated[str | None, Header()] = None) -> EmailAllowlistResponse:
    _check_auth(authorization)
    return EmailAllowlistResponse(addresses=get_allowed_recipients())


@app.put("/settings/email-allowlist", response_model=EmailAllowlistResponse)
def put_email_allowlist(
    request: EmailAllowlistRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> EmailAllowlistResponse:
    _check_auth(authorization)
    try:
        addresses = set_allowed_recipients(request.addresses)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EmailAllowlistResponse(addresses=addresses)


def main() -> None:
    if BIND_HOST not in {"127.0.0.1", "localhost", "::1"} and not API_TOKEN:
        raise SystemExit("Refusing to expose Jarvis beyond localhost without an API token.")
    uvicorn.run(app, host=BIND_HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
