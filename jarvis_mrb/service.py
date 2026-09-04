from __future__ import annotations

import threading
import time
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.jobs import run_due_jobs, trigger_event
from jarvis_mrb.server_config import load_server_config

_CONFIG = load_server_config()
BIND_HOST = _CONFIG.bind_host
PORT = _CONFIG.port
API_TOKEN = _CONFIG.api_token

app = FastAPI(title="Jarvis for MRB", version="0.6.0")
_scheduler_started = False


class CommandRequest(BaseModel):
    text: str


class CommandResponse(BaseModel):
    ok: bool
    message: str


class EventRequest(BaseModel):
    event: str


def _check_auth(authorization: str | None) -> None:
    if not API_TOKEN:
        return
    expected = f"Bearer {API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid Jarvis API token")


def _execute_job(command: str) -> str:
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
    return {"status": "ok", "version": "0.6.0", "bind": BIND_HOST}


@app.post("/command", response_model=CommandResponse)
def command(request: CommandRequest, authorization: Annotated[str | None, Header()] = None) -> CommandResponse:
    _check_auth(authorization)
    reply = handle_natural_language(request.text)
    return CommandResponse(ok=reply.ok, message=reply.message)


@app.post("/event", response_model=CommandResponse)
def event(request: EventRequest, authorization: Annotated[str | None, Header()] = None) -> CommandResponse:
    _check_auth(authorization)
    result = trigger_event(request.event, _execute_job)
    return CommandResponse(ok=result.ok, message=result.message)


def main() -> None:
    if BIND_HOST not in {"127.0.0.1", "localhost", "::1"} and not API_TOKEN:
        raise SystemExit("Refusing to expose Jarvis beyond localhost without an API token.")
    uvicorn.run(app, host=BIND_HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
