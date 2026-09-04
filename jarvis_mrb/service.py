from __future__ import annotations

import json
import threading
import time
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.conversation import append_message, recent_messages
from jarvis_mrb.email_policy import get_allowed_recipients, set_allowed_recipients
from jarvis_mrb.jobs import run_due_jobs, trigger_event
from jarvis_mrb.server_config import load_server_config
from jarvis_mrb.streaming_agent import stream_natural_language
from jarvis_mrb.tts_client import ensure_tts_server, synthesize_wav, tts_health

_CONFIG = load_server_config()
BIND_HOST = _CONFIG.bind_host
PORT = _CONFIG.port
API_TOKEN = _CONFIG.api_token

app = FastAPI(title="Jarvis for MRB", version="0.9.0")
_scheduler_started = False
_tts_start_attempted = False


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


class TTSRequest(BaseModel):
    text: str


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


def _start_tts_in_background() -> None:
    global _tts_start_attempted
    if _tts_start_attempted:
        return
    _tts_start_attempted = True

    def start() -> None:
        try:
            # Model loading can take a while on first boot; never block the Jarvis
            # API startup. The iPhone falls back to Apple TTS until Qwen is ready.
            ensure_tts_server(wait_seconds=0.0)
        except Exception:
            pass

    threading.Thread(target=start, name="jarvis-tts-start", daemon=True).start()


@app.on_event("startup")
def startup() -> None:
    _ensure_scheduler()
    _start_tts_in_background()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": "0.9.0",
        "bind": BIND_HOST,
        "tts": "ready" if tts_health() else "starting-or-unavailable",
    }


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


@app.post("/command/stream")
def command_stream(
    request: CommandRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Stream Jarvis text as newline-delimited JSON.

    For model-only conversation, the transport begins forwarding Qwen tokens just
    after the one-line tool decision, rather than waiting for the complete answer.
    Tool calls remain atomic because Jarvis must know which action to execute before
    it can truthfully report the result.
    """
    _check_auth(authorization)
    session_id = request.session_id or "default"
    history = recent_messages(session_id, limit=20)

    def generate():
        pieces: list[str] = []
        ok = True
        try:
            yield json.dumps({"type": "start"}) + "\n"
            for piece in stream_natural_language(request.text, history=history):
                if not piece:
                    continue
                pieces.append(piece)
                yield json.dumps({"type": "delta", "text": piece}, ensure_ascii=False) + "\n"
        except Exception as exc:
            ok = False
            message = f"I'm sorry, sir. Streaming failed: {exc}"
            pieces.append(message)
            yield json.dumps({"type": "delta", "text": message}, ensure_ascii=False) + "\n"
        finally:
            full = "".join(pieces).strip()
            append_message(session_id, "user", request.text)
            if full:
                append_message(session_id, "assistant", full)
            yield json.dumps({"type": "done", "ok": ok}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.post("/event", response_model=CommandResponse)
def event(request: EventRequest, authorization: Annotated[str | None, Header()] = None) -> CommandResponse:
    _check_auth(authorization)
    result = trigger_event(request.event, _execute_job)
    return CommandResponse(ok=result.ok, message=result.message)


@app.get("/tts/status")
def tts_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    _check_auth(authorization)
    return {"status": "ready" if tts_health() else "unavailable"}


@app.post("/tts")
def tts(request: TTSRequest, authorization: Annotated[str | None, Header()] = None) -> Response:
    _check_auth(authorization)
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="TTS text is empty")
    try:
        audio = synthesize_wav(text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Local Qwen3-TTS is unavailable: {exc}") from exc
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


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
