from __future__ import annotations

import json
import threading
import time
from typing import Annotated

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import jarvis_mrb.agent as agent_module
import jarvis_mrb.streaming_agent as streaming_agent_module
from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.conversation import append_message, recent_messages
from jarvis_mrb.email_policy import get_allowed_recipients, set_allowed_recipients
from jarvis_mrb.jobs import run_due_jobs, trigger_event
from jarvis_mrb.planner_model import get_planner_model, model_options, set_planner_model
from jarvis_mrb.server_config import load_server_config
from jarvis_mrb.streaming_agent import stream_natural_language
from jarvis_mrb.tts_client import ensure_tts_server, synthesize_wav, tts_health

_CONFIG = load_server_config()
BIND_HOST = _CONFIG.bind_host
PORT = _CONFIG.port
API_TOKEN = _CONFIG.api_token

# agent.py predates runtime model switching and keeps the selected model in a
# module global. Initialize both the normal and streaming planners from the
# persisted setting on every service start; the settings endpoint updates both
# globals immediately, so switching models never requires a Jarvis restart.
_INITIAL_MODEL = get_planner_model()
agent_module.OLLAMA_MODEL = _INITIAL_MODEL
streaming_agent_module.OLLAMA_MODEL = _INITIAL_MODEL

app = FastAPI(title="Jarvis for MRB", version="0.10.0")
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


class PlannerModelRequest(BaseModel):
    model: str


class PlannerModelResponse(BaseModel):
    model: str
    options: list[str]


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
            # API startup. The iPhone falls back to Apple TTS until local TTS is ready.
            ensure_tts_server(wait_seconds=0.0)
        except Exception:
            pass

    threading.Thread(target=start, name="jarvis-tts-start", daemon=True).start()


def _installed_ollama_models() -> set[str]:
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{agent_module.OLLAMA_URL}/api/tags")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=503, detail=f"Cannot query Ollama models: {exc}") from exc

    result: set[str] = set()
    for item in payload.get("models", []) if isinstance(payload, dict) else []:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                result.add(name)
    return result


def _warm_selected_model(previous: str, selected: str) -> None:
    """Best-effort model handoff without delaying the phone settings UI.

    Ollama's empty generate request is its preload/unload mechanism. Releasing the
    old model matters on a 16 GB RTX 5080: keeping the 27B and 8B planners resident
    together would waste VRAM and can make the supposedly fast model slower.
    """
    try:
        with httpx.Client(timeout=120.0) as client:
            if previous and previous != selected:
                try:
                    client.post(
                        f"{agent_module.OLLAMA_URL}/api/generate",
                        json={"model": previous, "prompt": "", "keep_alive": 0},
                    )
                except httpx.HTTPError:
                    pass
            client.post(
                f"{agent_module.OLLAMA_URL}/api/generate",
                json={
                    "model": selected,
                    "prompt": "",
                    "keep_alive": agent_module.OLLAMA_KEEP_ALIVE,
                },
            )
    except httpx.HTTPError:
        pass


@app.on_event("startup")
def startup() -> None:
    _ensure_scheduler()
    _start_tts_in_background()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": "0.10.0",
        "bind": BIND_HOST,
        "tts": "ready" if tts_health() else "starting-or-unavailable",
        "planner_model": agent_module.OLLAMA_MODEL,
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
        raise HTTPException(status_code=503, detail=f"Local TTS is unavailable: {exc}") from exc
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.get("/settings/planner-model", response_model=PlannerModelResponse)
def get_planner_model_setting(
    authorization: Annotated[str | None, Header()] = None,
) -> PlannerModelResponse:
    _check_auth(authorization)
    return PlannerModelResponse(model=agent_module.OLLAMA_MODEL, options=model_options())


@app.put("/settings/planner-model", response_model=PlannerModelResponse)
def put_planner_model_setting(
    request: PlannerModelRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> PlannerModelResponse:
    _check_auth(authorization)
    requested = request.model.strip()
    if requested not in model_options():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported planner model. Choose one of: {', '.join(model_options())}",
        )

    installed = _installed_ollama_models()
    if requested not in installed:
        raise HTTPException(
            status_code=400,
            detail=f"Ollama model {requested} is not installed on the Jarvis PC.",
        )

    previous = agent_module.OLLAMA_MODEL
    try:
        selected = set_planner_model(requested)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    agent_module.OLLAMA_MODEL = selected
    streaming_agent_module.OLLAMA_MODEL = selected

    if previous != selected:
        threading.Thread(
            target=_warm_selected_model,
            args=(previous, selected),
            name="jarvis-planner-warm",
            daemon=True,
        ).start()

    return PlannerModelResponse(model=selected, options=model_options())


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
