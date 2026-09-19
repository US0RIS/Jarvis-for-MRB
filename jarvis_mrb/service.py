from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Annotated, Any

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import jarvis_mrb.agent as agent_module
import jarvis_mrb.streaming_agent as streaming_agent_module
from jarvis_mrb.agent import handle_natural_language
from jarvis_mrb.audio_damping import status as audio_damping_status_data
from jarvis_mrb.conversation import ConversationMessage, append_message, recent_messages
from jarvis_mrb.email_policy import get_allowed_recipients, set_allowed_recipients
from jarvis_mrb.environment_state import get_state, update_state
from jarvis_mrb.event_bus import companion_events, emit_proactive, emit_thinking
from jarvis_mrb.jobs import run_due_jobs, trigger_event
from jarvis_mrb.knowledge_index import refresh as refresh_knowledge_index
from jarvis_mrb.knowledge_index import status as knowledge_status_data
from jarvis_mrb.meeting_notes import append_transcript as append_meeting_transcript
from jarvis_mrb.meeting_notes import finish as finish_meeting_notes
from jarvis_mrb.meeting_notes import start as start_meeting_notes
from jarvis_mrb.memory import memory_context, remember_exchange_async, status as memory_status_data
from jarvis_mrb.model_router import choose_model
from jarvis_mrb.planner_model import (
    FAST_MODEL,
    QUALITY_MODEL,
    get_auto_route,
    get_planner_model,
    model_options,
    planner_settings,
    set_auto_route,
    set_planner_model,
)
from jarvis_mrb.proactive_monitor import check_once as proactive_check_once
from jarvis_mrb.proactive_monitor import start as start_proactive_monitor
from jarvis_mrb.resource_monitor import sample as resource_status_data
from jarvis_mrb.runtime_health import record_failure as record_runtime_failure
from jarvis_mrb.runtime_health import record_success as record_runtime_success
from jarvis_mrb.runtime_health import status as runtime_health_status_data
from jarvis_mrb.sandbox import status as sandbox_status_data
from jarvis_mrb.server_config import load_server_config
from jarvis_mrb.spatial_memory import status as spatial_status_data
from jarvis_mrb.streaming_agent import stream_natural_language
from jarvis_mrb.tools.web import web_status
from jarvis_mrb.tts_client import ensure_tts_server, synthesize_wav, tts_health
from jarvis_mrb.vision import status as vision_status_data, submit_frame
from jarvis_mrb.visual_history import status as visual_history_status_data
from jarvis_mrb.world_migrations import run_migrations, status as migration_status_data
from jarvis_mrb.world_verification import status as verification_status_data

_CONFIG = load_server_config()
BIND_HOST = _CONFIG.bind_host
PORT = _CONFIG.port
API_TOKEN = _CONFIG.api_token

_INITIAL_MODEL = get_planner_model()
agent_module.OLLAMA_MODEL = _INITIAL_MODEL
streaming_agent_module.OLLAMA_MODEL = _INITIAL_MODEL

app = FastAPI(title="Jarvis for MRB", version="0.13.0")
_scheduler_started = False
_tts_start_attempted = False
_knowledge_started = False
_proactive_started = False


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
    model: str | None = None
    auto_route: bool | None = None


class PlannerModelResponse(BaseModel):
    model: str
    auto_route: bool
    options: list[str]


class TTSRequest(BaseModel):
    text: str


class MeetingStartRequest(BaseModel):
    title: str = ""


class MeetingStartResponse(BaseModel):
    ok: bool
    meeting_id: int
    message: str


class MeetingTranscriptRequest(BaseModel):
    meeting_id: int
    text: str


class MeetingFinishRequest(BaseModel):
    meeting_id: int


def _check_auth(authorization: str | None) -> None:
    if not API_TOKEN:
        return
    expected = f"Bearer {API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid Jarvis API token")


def _websocket_authorized(websocket: WebSocket) -> bool:
    if not API_TOKEN:
        return True
    return websocket.headers.get("authorization") == f"Bearer {API_TOKEN}"


def _command_alias(text: str) -> str:
    normalized = " ".join(text.lower().strip().split()).strip(".?!")
    if normalized in {
        "execute exact command",
        "execute the exact command",
        "run exact command",
        "run the exact command",
    }:
        return "confirm"
    if normalized in {"cancel exact command", "cancel the exact command"}:
        return "cancel"
    return text


def _voice_safe_confirmation(message: str) -> str:
    """Keep terminal confirmation explicit instead of letting iOS abbreviate it.

    The iPhone deliberately shortens ordinary confirmation prompts to avoid reading
    full email bodies/recipients aloud. For the isolated terminal tool, the user
    specifically requested that the exact command itself be spoken before approval.
    Rewording the final phrase avoids the generic confirmation abbreviation while
    keeping the backend's pending security action intact.
    """
    lower = message.lower()
    if "exact isolated terminal command" not in lower:
        return message
    value = message
    for phrase in (
        "Say 'confirm' to proceed or 'cancel'.",
        'Say "confirm" to proceed or "cancel".',
        "Say confirm to proceed or cancel.",
    ):
        if phrase in value:
            value = value.replace(
                phrase,
                "After hearing that exact command, say 'execute exact command' to proceed, or 'never mind' to cancel.",
            )
            break
    return value


def _contextual_history(session_id: str, query: str, *, limit: int = 20) -> list[ConversationMessage]:
    history = recent_messages(session_id, limit=limit)
    retrieved = memory_context(query, limit=3)
    if retrieved:
        history = [ConversationMessage(role="assistant", content=retrieved), *history]
    return history


def _execute_job(command: str) -> str:
    reply = handle_natural_language(command)
    message = reply.message
    normalized = command.lower()
    if message and ("briefing" in normalized or normalized.startswith("remind ")):
        emit_proactive(message, cue="task_complete", severity="info")
    return message


def _scheduler_loop() -> None:
    healthy_marked = False
    while True:
        try:
            run_due_jobs(_execute_job)
            if not healthy_marked:
                record_runtime_success("scheduler")
                healthy_marked = True
        except Exception as exc:
            record_runtime_failure("scheduler", exc)
            healthy_marked = False
        time.sleep(1.0)


def _ensure_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    threading.Thread(target=_scheduler_loop, name="jarvis-scheduler", daemon=True).start()


def _knowledge_loop() -> None:
    time.sleep(20)
    while True:
        try:
            result = refresh_knowledge_index()
            if bool(result.get("ok", True)):
                record_runtime_success("knowledge_refresh")
            else:
                errors = result.get("errors") or ["Knowledge refresh returned degraded status"]
                record_runtime_failure("knowledge_refresh", "; ".join(str(item) for item in errors[:5]))
        except Exception as exc:
            record_runtime_failure("knowledge_refresh", exc)
        time.sleep(15 * 60)


def _ensure_knowledge_refresh() -> None:
    global _knowledge_started
    if _knowledge_started:
        return
    _knowledge_started = True
    threading.Thread(target=_knowledge_loop, name="jarvis-knowledge-refresh", daemon=True).start()


def _start_tts_in_background() -> None:
    global _tts_start_attempted
    if _tts_start_attempted:
        return
    _tts_start_attempted = True

    def start() -> None:
        try:
            ensure_tts_server(wait_seconds=0.0)
            if tts_health():
                record_runtime_success("tts_start")
            else:
                record_runtime_failure("tts_start", "TTS process start returned but health is not ready yet")
        except Exception as exc:
            record_runtime_failure("tts_start", exc)

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


def _warm_fast_model() -> None:
    if not get_auto_route():
        return
    threading.Thread(
        target=_warm_selected_model,
        args=(QUALITY_MODEL, FAST_MODEL),
        name="jarvis-fast-warm",
        daemon=True,
    ).start()


def _safe_operational_health() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        migrations = migration_status_data()
    except Exception as exc:
        migrations = {"ready": False, "current": 0, "target": 0, "error": str(exc)[:500]}
    try:
        verification = verification_status_data()
    except Exception as exc:
        verification = {"installed": False, "error": str(exc)[:500]}
    try:
        runtime = runtime_health_status_data()
    except Exception as exc:
        runtime = {"degraded": 1, "error": str(exc)[:500]}
    return migrations, verification, runtime


@app.on_event("startup")
def startup() -> None:
    global _proactive_started
    # Schema compatibility is a hard startup boundary. Jarvis must not start background
    # writers against a newer/partial world schema. Additive migrations are backed up
    # before modification and are idempotent on subsequent launches.
    try:
        run_migrations(backup=True)
        record_runtime_success("schema_migrations")
    except Exception as exc:
        try:
            record_runtime_failure("schema_migrations", exc)
        except Exception:
            pass
        raise

    try:
        from jarvis_mrb.agency_bootstrap import prepare as prepare_agency
        agency = prepare_agency(sync_goals=True)
        if not bool(agency.get("ok")):
            raise RuntimeError("; ".join(str(item) for item in agency.get("errors", [])) or "Agency initialization failed.")
        record_runtime_success("agency")
        from jarvis_mrb.agency_release import deployment_sha as agency_deployment_sha
        from jarvis_mrb.agency_runtime import record_boot as record_agency_boot
        record_agency_boot(deployment_sha=agency_deployment_sha())
    except Exception as exc:
        record_runtime_failure("agency", exc)
        raise

    _ensure_scheduler()
    _ensure_knowledge_refresh()
    _start_tts_in_background()
    start_proactive_monitor()
    _proactive_started = True
    record_runtime_success("proactive_monitor")
    _warm_fast_model()


@app.get("/health")
def health() -> dict[str, Any]:
    settings = planner_settings()
    sandbox_state = sandbox_status_data()
    migrations, verification, runtime = _safe_operational_health()
    try:
        from jarvis_mrb.tool_audit import status as tool_audit_status
        audit = tool_audit_status()
    except Exception as exc:
        audit = {"installed": False, "error": str(exc)[:500]}
    try:
        from jarvis_mrb.agency_bootstrap import status as agency_status
        agency = agency_status()
    except Exception as exc:
        agency = {"ready": False, "mode": "unknown", "error": str(exc)[:500]}

    return {
        "status": "ok",
        "version": "0.13.0",
        "bind": BIND_HOST,
        "tts": "ready" if tts_health() else "starting-or-unavailable",
        "web_search": "ready" if web_status().ok else "unconfigured",
        "planner_model": settings["model"],
        "auto_route": settings["auto_route"],
        "sandbox": "ready" if sandbox_state.get("docker") else "docker-unavailable",
        "visual_history": "ready",
        "resource_guardrails": "active",
        "world_model": "ready" if bool(migrations.get("ready")) else "migration-required",
        "world_schema_version": int(migrations.get("current") or 0),
        "world_schema_target": int(migrations.get("target") or 0),
        "verification": "ready" if bool(verification.get("installed")) and bool(verification.get("independent_readback")) else "degraded",
        "tool_audit": "ready" if bool(audit.get("installed")) else "degraded",
        "runtime_health": "ready" if int(runtime.get("degraded") or 0) == 0 else "degraded",
        "scheduler": "running" if _scheduler_started else "stopped",
        "knowledge_refresh": "running" if _knowledge_started else "stopped",
        "proactive_monitor": "running" if _proactive_started else "stopped",
        "agency": "ready" if bool(agency.get("ready")) else "degraded",
        "agency_mode": str(agency.get("mode") or "unknown"),
        "agency_desired_states": agency.get("desired_states") or {},
        "agency_plans": agency.get("plans") or {},
        "agency_steps": agency.get("steps") or {},
    }


@app.get("/agency/command-view")
def agency_command_view(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Authenticated read-only status for an optional iPhone / glasses display."""
    _check_auth(authorization)
    from jarvis_mrb.agency_command_view import build_command_view
    return build_command_view()


@app.post("/command", response_model=CommandResponse)
def command(request: CommandRequest, authorization: Annotated[str | None, Header()] = None) -> CommandResponse:
    _check_auth(authorization)
    emit_thinking(True)
    try:
        session_id = request.session_id or "default"
        effective_text = _command_alias(request.text)
        history = _contextual_history(session_id, effective_text, limit=12)
        reply = handle_natural_language(effective_text, history=history)
        message = _voice_safe_confirmation(reply.message)
        append_message(session_id, "user", request.text)
        if message and message != "__EXIT__":
            append_message(session_id, "assistant", message)
            remember_exchange_async(session_id, request.text, message)
        return CommandResponse(ok=reply.ok, message=message)
    finally:
        emit_thinking(False)


@app.post("/command/stream")
def command_stream(
    request: CommandRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    _check_auth(authorization)
    emit_thinking(True)
    try:
        session_id = request.session_id or "default"
        effective_text = _command_alias(request.text)
        route = choose_model(effective_text)
        history_limit = 8 if route.model == FAST_MODEL else 20
        history = _contextual_history(session_id, effective_text, limit=history_limit)
    except Exception:
        emit_thinking(False)
        raise

    def generate():
        pieces: list[str] = []
        ok = True
        first_output = True
        try:
            yield json.dumps(
                {
                    "type": "start",
                    "model": route.model,
                    "route_reason": route.reason,
                }
            ) + "\n"
            for piece in stream_natural_language(
                effective_text,
                history=history,
                model_override=route.model,
                announce_analysis=route.announce_analysis,
            ):
                if not piece:
                    continue
                delivered_piece = _voice_safe_confirmation(piece)
                if first_output:
                    first_output = False
                    emit_thinking(False)
                pieces.append(delivered_piece)
                yield json.dumps({"type": "delta", "text": delivered_piece}, ensure_ascii=False) + "\n"
        except Exception as exc:
            if first_output:
                first_output = False
                emit_thinking(False)
            ok = False
            message = f"I'm sorry, sir. Streaming failed: {exc}"
            pieces.append(message)
            yield json.dumps({"type": "delta", "text": message}, ensure_ascii=False) + "\n"
        finally:
            emit_thinking(False)
            full = "".join(pieces).strip()
            append_message(session_id, "user", request.text)
            if full:
                append_message(session_id, "assistant", full)
                remember_exchange_async(session_id, request.text, full)

            if get_auto_route() and route.model == QUALITY_MODEL:
                threading.Thread(
                    target=_warm_selected_model,
                    args=(QUALITY_MODEL, FAST_MODEL),
                    name="jarvis-fast-rewarm",
                    daemon=True,
                ).start()

            yield json.dumps({"type": "done", "ok": ok}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.post("/event", response_model=CommandResponse)
def event(request: EventRequest, authorization: Annotated[str | None, Header()] = None) -> CommandResponse:
    _check_auth(authorization)
    if request.event == "home_arrival":
        update_state({"location": "home", "active_profile": "home"})
    elif request.event == "home_departure":
        update_state({"location": "away", "active_profile": "mobile"})
    result = trigger_event(request.event, _execute_job)
    return CommandResponse(ok=result.ok, message=result.message)


@app.post("/proactive/check")
def proactive_check(authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    _check_auth(authorization)
    proactive_check_once()
    return {"status": "checked"}


@app.post("/meeting/start", response_model=MeetingStartResponse)
def meeting_start(
    request: MeetingStartRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> MeetingStartResponse:
    _check_auth(authorization)
    item = start_meeting_notes(request.title)
    update_state({"meeting": {"active": True, "id": item["id"], "title": item.get("title") or ""}})
    return MeetingStartResponse(
        ok=True,
        meeting_id=int(item["id"]),
        message=f"Meeting-note session {item['id']} started.",
    )


@app.post("/meeting/transcript", response_model=CommandResponse)
def meeting_transcript(
    request: MeetingTranscriptRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> CommandResponse:
    _check_auth(authorization)
    try:
        append_meeting_transcript(request.meeting_id, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CommandResponse(ok=True, message="Transcript segment stored locally.")


@app.post("/meeting/finish", response_model=CommandResponse)
def meeting_finish(
    request: MeetingFinishRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> CommandResponse:
    _check_auth(authorization)
    try:
        message = finish_meeting_notes(request.meeting_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    update_state({"meeting": {"active": False, "id": request.meeting_id}})
    companion_events.publish(
        {
            "type": "meeting_complete",
            "meeting_id": request.meeting_id,
            "message": message,
            "cue": "task_complete",
        }
    )
    return CommandResponse(ok=True, message=message)


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
    settings = planner_settings()
    return PlannerModelResponse(
        model=str(settings["model"]),
        auto_route=bool(settings["auto_route"]),
        options=model_options(),
    )


@app.put("/settings/planner-model", response_model=PlannerModelResponse)
def put_planner_model_setting(
    request: PlannerModelRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> PlannerModelResponse:
    _check_auth(authorization)
    previous = agent_module.OLLAMA_MODEL
    selected = previous

    if request.model is not None:
        requested = request.model.strip()
        if requested not in model_options():
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported planner model. Choose one of: {', '.join(model_options())}",
            )
        installed = _installed_ollama_models()
        if requested not in installed:
            raise HTTPException(status_code=400, detail=f"Ollama model {requested} is not installed on the Jarvis PC.")
        try:
            selected = set_planner_model(requested)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        agent_module.OLLAMA_MODEL = selected
        streaming_agent_module.OLLAMA_MODEL = selected

    if request.auto_route is not None:
        set_auto_route(request.auto_route)

    warm_target = FAST_MODEL if get_auto_route() else selected
    if previous != warm_target or request.auto_route is not None:
        threading.Thread(
            target=_warm_selected_model,
            args=(previous, warm_target),
            name="jarvis-planner-warm",
            daemon=True,
        ).start()

    settings = planner_settings()
    return PlannerModelResponse(
        model=str(settings["model"]),
        auto_route=bool(settings["auto_route"]),
        options=model_options(),
    )


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


@app.get("/memory/status")
def memory_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _check_auth(authorization)
    return memory_status_data()


@app.get("/knowledge/status")
def knowledge_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _check_auth(authorization)
    return knowledge_status_data()


@app.get("/spatial/status")
def spatial_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _check_auth(authorization)
    return spatial_status_data()


@app.get("/sandbox/status")
def sandbox_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _check_auth(authorization)
    return sandbox_status_data()


@app.get("/vision/status")
def vision_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _check_auth(authorization)
    return vision_status_data()


@app.get("/visual-history/status")
def visual_history_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _check_auth(authorization)
    return visual_history_status_data()


@app.get("/resources/status")
def resources_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _check_auth(authorization)
    return resource_status_data()


@app.get("/audio-damping/status")
def audio_damping_status(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _check_auth(authorization)
    return audio_damping_status_data()


@app.get("/state")
def state(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _check_auth(authorization)
    return get_state()


@app.websocket("/ws/companion")
async def companion_socket(websocket: WebSocket) -> None:
    if not _websocket_authorized(websocket):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    loop = asyncio.get_running_loop()
    subscriber_id, event_queue = companion_events.register(loop)
    update_state({"devices": {"phone_transport": "connected"}})

    async def send_events() -> None:
        while True:
            event = await event_queue.get()
            await websocket.send_text(json.dumps(event, ensure_ascii=False))

    sender = asyncio.create_task(send_events())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            frame = message.get("bytes")
            if isinstance(frame, (bytes, bytearray)):
                submit_frame(bytes(frame))
                continue
            text = message.get("text")
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("type") == "environment" and isinstance(payload.get("state"), dict):
                update_state(dict(payload["state"]))
            elif payload.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        companion_events.unregister(subscriber_id)
        update_state({"devices": {"phone_transport": "disconnected"}})


def main() -> None:
    if BIND_HOST not in {"127.0.0.1", "localhost", "::1"} and not API_TOKEN:
        raise SystemExit("Refusing to expose Jarvis beyond localhost without an API token.")
    uvicorn.run(app, host=BIND_HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
