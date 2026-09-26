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
_external_watches_started = False
_tts_start_attempted = False
_knowledge_started = False
_proactive_started = False
_world_armor_live_started = False
_world_armor_push_started = False
_world_armor_guard_started = False


class CommandRequest(BaseModel):
    text: str
    session_id: str | None = None


class CloudCognitionPrepareRequest(BaseModel):
    text: str
    session_id: str | None = None
    mode: str = "auto"


class CloudCognitionResolveRequest(BaseModel):
    task_id: str
    proposal: dict[str, Any]
    metadata: dict[str, Any] | None = None


class CloudCognitionFeedbackRequest(BaseModel):
    request_fingerprint: str
    user_corrected: bool = False
    cloud_materially_changed_result: bool | None = None
    note: str = ""


class ExternalWatchCreateRequest(BaseModel):
    scope: str = "personal"
    kind: str
    label: str
    config: dict[str, Any]
    interval_seconds: int = 3600
    expires_hours: int = 24


class ExternalWatchLookupRequest(BaseModel):
    id: str = ""
    scope: str = "personal"


class DiligenceMatterRequest(BaseModel):
    label: str
    project_entity_id: str = ""


class DiligenceIssuerRequest(BaseModel):
    matter_id: str
    cik: str
    asserted_name: str


class DiligenceEPAFacilityRequest(BaseModel):
    matter_id: str
    cik: str
    frs_id: str
    label: str


class EPADirectLookupRequest(BaseModel):
    frs_id: str


class DiligenceClaimRequest(BaseModel):
    matter_id: str
    cik: str
    taxonomy: str
    tag: str
    unit: str = "USD"
    value: float
    end: str
    start: str = ""
    source_ref: str
    context: str = ""


class DiligenceLookupRequest(BaseModel):
    matter_id: str
    include_sanctions: bool = False


class RegionalAirspaceRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 20.0


class OfficialCameraAnalysisRequest(BaseModel):
    camera_id: str


class NearbyFacilitiesRequest(BaseModel):
    latitude: float
    longitude: float
    radius_m: int = 1500
    limit: int = 18


class PhysicalConditionsRequest(BaseModel):
    latitude: float
    longitude: float


class LifeCreateRequest(BaseModel):
    kind: str
    title: str
    domain: str
    description: str = ""
    deadline_at: str | None = None
    next_step: str = ""
    depends_on: list[str] | None = None
    quantity: float | None = None
    location: str = ""
    source_ref: str = ""
    client_request_id: str | None = None


class LifeReceiptRequest(BaseModel):
    record_id: str
    expected_version: int
    outcome: str
    source_kind: str
    evidence_ref: str


class LifeRetireRequest(BaseModel):
    record_id: str
    expected_version: int


class LifeTransitionRequest(BaseModel):
    template: str
    title: str
    client_request_id: str


class LifeHandoffRequest(BaseModel):
    title: str
    summary: str
    next_step: str
    linked_ids: list[str]
    client_request_id: str


class LifeRecordRequest(BaseModel):
    record_id: str


class LifeFrictionRequest(BaseModel):
    label: str
    occurred_at: str | None = None


class LifeWhatIfRequest(BaseModel):
    activity_minutes: int
    days: int
    daily_free_minutes: int


class WorldArmorCreateRequest(BaseModel):
    label: str
    latitude: float
    longitude: float
    radius_km: float = 30.0
    lifetime_hours: int = 24


class WorldArmorIdRequest(BaseModel):
    investigation_id: str


class WorldArmorReplayRequest(BaseModel):
    investigation_id: str
    as_known_at: str | None = None


class WorldArmorWatchCreateRequest(BaseModel):
    investigation_id: str
    interval_minutes: int = 60
    max_checks: int = 6
    lifetime_hours: int = 6
    attention_kind: str = "off"
    attention_threshold: float | None = None
    attention_cooldown_minutes: int = 60


class WorldArmorWatchIdRequest(BaseModel):
    watch_id: str


class WorldArmorNoticeIdRequest(BaseModel):
    notice_id: str


class WorldArmorPublicCameraSearchRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 30
    limit: int = 30


class WorldArmorCameraInspectRequest(BaseModel):
    investigation_id: str
    camera_ref: str = ""
    public_url: str = ""
    condition: str = ""


class WorldArmorCameraReceiptIdRequest(BaseModel):
    receipt_id: str


class WorldArmorMovementEnrollRequest(BaseModel):
    label: str
    kind: str
    grant_class: str
    terms_reference: str
    authorized_automated_access: bool = False
    provider_min_interval_seconds: int = 0
    cadence_seconds: int = 0
    retention_days: int = 7
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None


class WorldArmorMovementIDRequest(BaseModel):
    source_id: str


class WorldArmorMovementActionRequest(BaseModel):
    source_id: str
    action: str


class WorldArmorSourceEnrollRequest(BaseModel):
    label: str
    kind: str
    locator: str
    grant_class: str
    terms_reference: str
    authorized_automated_access: bool = False
    automated_min_interval_seconds: int = 0
    cadence_seconds: int = 0
    sample_budget: int | None = None
    consent_expires_at: str | None = None
    retention_days: int = 30
    scene_goal: str = ""
    latitude: float | None = None
    longitude: float | None = None


class WorldArmorSourceIDRequest(BaseModel):
    source_id: str


class WorldArmorSourceActionRequest(BaseModel):
    source_id: str
    action: str


class WorldArmorSourcePlanRequest(BaseModel):
    source_ids: list[str] | None = None
    max_concurrent: int = 4


class WorldArmorPublicPageRequest(BaseModel):
    public_url: str


class WorldArmorImportCameraWatchRequest(BaseModel):
    investigation_id: str
    watch_id: str

class WorldArmorCorrelationRequest(BaseModel):
    investigation_id: str
    start_at: str
    end_at: str
    as_known_at: str | None = None
    source_ids: list[str] | None = None
    query_radius_km: float | None = None


class WorldArmorPushTokenRequest(BaseModel):
    device_token: str


class WorldArmorFullBrowserRequest(BaseModel):
    after_seq: int = 0
    limit: int = 200
    start_at: str | None = None
    end_at: str | None = None
    investigation_id: str | None = None
    as_known_at: str | None = None


class WorldArmorFullCausalRequest(BaseModel):
    investigation_id: str
    start_at: str
    end_at: str
    hypothesis_id: str | None = None
    as_known_at: str | None = None


class WorldArmorFullParallelRequest(BaseModel):
    after_seq: int = 0
    start_at: str | None = None
    end_at: str | None = None
    investigation_id: str | None = None
    hypothesis_id: str | None = None
    as_known_at: str | None = None


class WorldArmorPresenceGrantRequest(BaseModel):
    actuator_kind: str
    target_id: str
    target_label: str
    lifetime_seconds: int = 120
    max_uses: int = 1


class WorldArmorPresenceGrantIDRequest(BaseModel):
    grant_id: str


class WorldArmorPresenceDispatchRequest(BaseModel):
    grant_id: str
    desired_on: bool


class WorldArmorPresenceReceiptRequest(BaseModel):
    request_id: str
    status: str
    message: str


class RealityLensRequest(BaseModel):
    latitude: float
    longitude: float
    label: str
    remember: bool = False


class RealityLensForgetRequest(BaseModel):
    latitude: float
    longitude: float


class RealityGraphQuestionRequest(BaseModel):
    latitude: float
    longitude: float
    question: str = ""


class RealityGraphMissionRequest(BaseModel):
    mission: dict[str, Any]
    observations: list[dict[str, Any]]
    question: str = ""

class RealityGraphCreateRequest(BaseModel):
    goal: str
    deadline: str | None = None
    lifetime_hours: int = 24


class RealityGraphAppendRequest(BaseModel):
    mission_id: str
    observations: list[dict[str, Any]]


class RealityGraphStoredRequest(BaseModel):
    mission_id: str
    question: str = ""



class NearbyPublicCameraRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 10.0
    limit: int = 8


class ConductorPlanRequest(BaseModel):
    node_id: str
    apps: list[str]
    screen_requested: bool = False


class ConductorExecuteRequest(BaseModel):
    id: str
    node_id: str
    apps: list[str]
    one_use_grant: str


class ConductorMissionRequest(BaseModel):
    id: str


class MeshAppLaunchRequest(BaseModel):
    node_id: str
    app_name: str


class MeshNodeSessionRequest(BaseModel):
    node_id: str
    duration_seconds: int = 120


class MeshNodeRequest(BaseModel):
    node_id: str


class GuardianObjectiveRequest(BaseModel):
    id: str = ""


class GuardianObjectiveSnoozeRequest(BaseModel):
    id: str
    hours: int = 1


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


def _check_mesh_auth(authorization: str | None) -> None:
    """Private device/desktop presence must never run on tokenless Jarvis."""
    if not API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Configure a private Jarvis API bearer token before enabling Reality Mesh.",
        )
    _check_auth(authorization)


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


def _external_watch_loop() -> None:
    # Explicitly created watches only. Runs in a separate daemon so a slow
    # third-party provider cannot block normal task scheduling or phone commands.
    time.sleep(5)
    while True:
        try:
            from jarvis_mrb.external_watches import run_due_watches
            run_due_watches(limit=2)
            record_runtime_success("external_watches")
        except Exception as exc:
            record_runtime_failure("external_watches", exc)
        time.sleep(60)


def _ensure_external_watch_runner() -> None:
    global _external_watches_started
    if _external_watches_started:
        return
    _external_watches_started = True
    threading.Thread(
        target=_external_watch_loop,
        name="jarvis-public-evidence-watches", daemon=True,
    ).start()


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


def _ensure_world_armor_live_supervisor() -> None:
    global _world_armor_live_started
    from jarvis_mrb.world_armor_live import (
        autostart_enabled, start_supervisor, supervisor_alive,
    )
    if not autostart_enabled():
        return
    if supervisor_alive():
        _world_armor_live_started = True
        return
    _world_armor_live_started = False
    if start_supervisor():
        _world_armor_live_started = True
        record_runtime_success("world_armor_live")


def _world_armor_guard_loop() -> None:
    while True:
        try:
            _ensure_world_armor_live_supervisor()
            _ensure_world_armor_push_worker()
        except Exception as exc:
            record_runtime_failure("world_armor_guard", exc)
        time.sleep(15)


def _ensure_world_armor_guard() -> None:
    global _world_armor_guard_started
    if _world_armor_guard_started:
        return
    from jarvis_mrb.world_armor_live import autostart_enabled
    from jarvis_mrb.world_armor_push import enabled as push_enabled
    if not autostart_enabled() and not push_enabled():
        return
    _world_armor_guard_started = True
    threading.Thread(
        target=_world_armor_guard_loop,
        name="world-armor-runtime-guard",
        daemon=True,
    ).start()


def _ensure_world_armor_push_worker() -> None:
    global _world_armor_push_started
    from jarvis_mrb.world_armor_push import enabled, start_worker, worker_alive
    if not enabled():
        return
    if worker_alive():
        _world_armor_push_started = True
        return
    if start_worker():
        _world_armor_push_started = True
        record_runtime_success("world_armor_push")


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
    _ensure_external_watch_runner()
    _ensure_knowledge_refresh()
    try:
        _ensure_world_armor_live_supervisor()
    except Exception as exc:
        record_runtime_failure("world_armor_live", exc)
    try:
        _ensure_world_armor_push_worker()
    except Exception as exc:
        record_runtime_failure("world_armor_push", exc)
    try:
        _ensure_world_armor_guard()
    except Exception as exc:
        record_runtime_failure("world_armor_guard", exc)
    _start_tts_in_background()
    start_proactive_monitor()
    _proactive_started = True
    record_runtime_success("proactive_monitor")
    _warm_fast_model()


@app.get("/routing/status")
def model_routing_status(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.deterministic_dispatch import routing_status
    return routing_status()


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
        "external_watches": "running" if _external_watches_started else "stopped",
        "model_free_routing": __import__("jarvis_mrb.deterministic_dispatch", fromlist=["routing_status"]).routing_status(),
        "knowledge_refresh": "running" if _knowledge_started else "stopped",
        "proactive_monitor": "running" if _proactive_started else "stopped",
        "world_armor_live": "running" if _world_armor_live_started else "stopped",
        "agency": "ready" if bool(agency.get("ready")) else "degraded",
        "agency_mode": str(agency.get("mode") or "unknown"),
        "agency_desired_states": agency.get("desired_states") or {},
        "agency_plans": agency.get("plans") or {},
        "agency_steps": agency.get("steps") or {},
    }


def _armor_error(exc: Exception) -> None:
    from jarvis_mrb.world_armor_phase1 import ArmorDisabled
    if isinstance(exc, ArmorDisabled):
        raise HTTPException(status_code=503, detail=str(exc)[:200]) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)[:200]) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    raise exc


@app.get("/world-armor/v1/capabilities")
def world_armor_capabilities(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_phase1 import capabilities
    return capabilities()


@app.post("/world-armor/v1/investigations")
def world_armor_create(
    request: WorldArmorCreateRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_phase1 import create_investigation
    try:
        return create_investigation(
            request.label, request.latitude, request.longitude,
            radius_km=request.radius_km, lifetime_hours=request.lifetime_hours,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.get("/world-armor/v1/investigations")
def world_armor_list(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_phase1 import list_investigations
    try:
        return list_investigations()
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/observe")
def world_armor_observe(
    request: WorldArmorIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_phase1 import observe_once
    try:
        return observe_once(request.investigation_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/replay")
def world_armor_replay(
    request: WorldArmorReplayRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_phase1 import replay
    try:
        return replay(request.investigation_id, as_known_at=request.as_known_at)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/changes")
def world_armor_changes(
    request: WorldArmorIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_phase1 import compare_recent
    try:
        return compare_recent(request.investigation_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/correlate")
def world_armor_correlate(
    request: WorldArmorCorrelationRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_correlate import correlate
    try:
        return correlate(
            request.investigation_id,
            start_at=request.start_at, end_at=request.end_at,
            as_known_at=request.as_known_at,
            source_ids=request.source_ids,
            query_radius_km=request.query_radius_km,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/hypotheses/query")
def world_armor_hypotheses(
    request: WorldArmorCorrelationRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_hypotheses import build_evidence_graph
    try:
        return build_evidence_graph(
            request.investigation_id,
            start_at=request.start_at, end_at=request.end_at,
            as_known_at=request.as_known_at,
            source_ids=request.source_ids,
            query_radius_km=request.query_radius_km,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/watches")
def world_armor_watch_create(
    request: WorldArmorWatchCreateRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_watches import create_watch
    try:
        return create_watch(
            request.investigation_id,
            interval_minutes=request.interval_minutes,
            max_checks=request.max_checks,
            lifetime_hours=request.lifetime_hours,
            attention_kind=request.attention_kind,
            attention_threshold=request.attention_threshold,
            attention_cooldown_minutes=request.attention_cooldown_minutes,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.get("/world-armor/v1/watches")
def world_armor_watch_list(
    response: Response,
    investigation_id: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_watches import list_watches
    try:
        return list_watches(investigation_id=investigation_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/watches/stop")
def world_armor_watch_stop(
    request: WorldArmorWatchIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_watches import stop_watch
    try:
        return stop_watch(request.watch_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/watches/forget")
def world_armor_watch_forget(
    request: WorldArmorWatchIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_watches import forget_watch
    try:
        return forget_watch(request.watch_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/watches/pause")
def world_armor_watch_pause(
    request: WorldArmorWatchIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_watches import pause_watch
    try:
        return pause_watch(request.watch_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/watches/resume")
def world_armor_watch_resume(
    request: WorldArmorWatchIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_watches import resume_watch
    try:
        return resume_watch(request.watch_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.get("/world-armor/v1/notices")
def world_armor_notice_list(
    response: Response,
    investigation_id: str | None = None,
    watch_id: str | None = None,
    unread_only: bool = False,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_attention import list_notices
    try:
        return list_notices(
            investigation_id=investigation_id, watch_id=watch_id,
            unread_only=unread_only,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/notices/read")
def world_armor_notice_read(
    request: WorldArmorNoticeIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_attention import mark_read
    try:
        return mark_read(request.notice_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/notices/forget")
def world_armor_notice_forget(
    request: WorldArmorNoticeIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_attention import forget_notice
    try:
        return forget_notice(request.notice_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


def _world_armor_platform_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)[:240]) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)[:240]) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=503, detail=str(exc)[:240]) from exc
    raise exc


@app.get("/world-armor/v8/push/status")
def world_armor_push_status(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_push import status
    return status()


@app.post("/world-armor/v8/push/register")
def world_armor_push_register(
    request: WorldArmorPushTokenRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_push import register_device
    try:
        result = register_device(request.device_token)
        _ensure_world_armor_push_worker()
        return result
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v8/push/unregister")
def world_armor_push_unregister(
    request: WorldArmorPushTokenRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_push import unregister_device
    try:
        return unregister_device(request.device_token)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v8/status")
def world_armor_full_status(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import full_status
    return full_status()


@app.post("/world-armor/v8/reality-browser")
def world_armor_reality_browser(
    request: WorldArmorFullBrowserRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import reality_browser
    try:
        return reality_browser(
            after_seq=request.after_seq,
            limit=request.limit,
            start_at=request.start_at,
            end_at=request.end_at,
            investigation_id=request.investigation_id,
            as_known_at=request.as_known_at,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v8/synthetic-senses")
def world_armor_synthetic_senses(
    request: WorldArmorFullBrowserRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import synthetic_senses
    try:
        return synthetic_senses(
            after_seq=request.after_seq,
            limit=request.limit,
            start_at=request.start_at,
            end_at=request.end_at,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v8/causal-debugger")
def world_armor_causal_debugger(
    request: WorldArmorFullCausalRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import causal_debugger
    try:
        return causal_debugger(
            request.investigation_id,
            start_at=request.start_at,
            end_at=request.end_at,
            hypothesis_id=request.hypothesis_id,
            as_known_at=request.as_known_at,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v8/parallel-existence")
def world_armor_parallel_existence(
    request: WorldArmorFullParallelRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import parallel_existence
    try:
        return parallel_existence(
            after_seq=request.after_seq,
            start_at=request.start_at,
            end_at=request.end_at,
            investigation_id=request.investigation_id,
            hypothesis_id=request.hypothesis_id,
            as_known_at=request.as_known_at,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v8/presence")
def world_armor_presence_list(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import list_presence_grants
    return list_presence_grants()


@app.post("/world-armor/v8/presence/grants")
def world_armor_presence_grant(
    request: WorldArmorPresenceGrantRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import create_presence_grant
    try:
        return create_presence_grant(
            actuator_kind=request.actuator_kind,
            target_id=request.target_id,
            target_label=request.target_label,
            lifetime_seconds=request.lifetime_seconds,
            max_uses=request.max_uses,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v8/presence/revoke")
def world_armor_presence_revoke(
    request: WorldArmorPresenceGrantIDRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import revoke_presence_grant
    try:
        return revoke_presence_grant(request.grant_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v8/presence/dispatch")
def world_armor_presence_dispatch(
    request: WorldArmorPresenceDispatchRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import dispatch_presence
    try:
        return dispatch_presence(
            request.grant_id,
            desired_on=request.desired_on,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v8/presence/receipt")
def world_armor_presence_receipt(
    request: WorldArmorPresenceReceiptRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_full import record_presence_receipt
    try:
        return record_presence_receipt(
            request.request_id,
            status=request.status,
            message=request.message,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v7/live/status")
def world_armor_live_status(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_live import status
    return status()


@app.get("/world-armor/v7/live/events")
def world_armor_live_events(
    response: Response,
    after_seq: int = 0,
    limit: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_live import events
    try:
        return events(after_seq=after_seq, limit=limit)
    except ValueError as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v7/live/start")
def world_armor_live_start(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    global _world_armor_live_started
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_live import start_supervisor, status
    try:
        _world_armor_live_started = bool(start_supervisor())
        return status()
    except (ValueError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v7/live/stop")
def world_armor_live_stop(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    global _world_armor_live_started
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_live import stop_supervisor, status
    stop_supervisor()
    _world_armor_live_started = False
    return status()


@app.get("/world-armor/v6/workers")
@app.get("/world-armor/v4/workers")
def world_armor_distributed_workers(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_distributed import available_workers
    try:
        return available_workers()
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v3/movement-sources")
def world_armor_movement_enroll(
    request: WorldArmorMovementEnrollRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_movement import enroll_source
    try:
        return enroll_source(**request.model_dump())
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v3/movement-sources")
def world_armor_movement_sources(
    response: Response,
    offset: int = 0,
    page_size: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_movement import list_sources
    try:
        return list_sources(offset=offset, page_size=page_size)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v3/movement-sources/transition")
def world_armor_movement_transition(
    request: WorldArmorMovementActionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_movement import transition_source
    try:
        return transition_source(request.source_id, request.action)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v3/movement-sources/forget")
def world_armor_movement_forget(
    request: WorldArmorMovementIDRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_movement import forget_source
    try:
        return forget_source(request.source_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v3/movement/collect")
def world_armor_movement_collect(
    request: WorldArmorMovementIDRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_movement import collect_source
    try:
        return collect_source(request.source_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v3/movement/nearby")
def world_armor_movement_nearby(
    response: Response,
    latitude: float,
    longitude: float,
    radius_km: float = 50,
    entity_type: str | None = None,
    after_seq: int = 0,
    page_size: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_movement import nearby
    try:
        return nearby(
            latitude, longitude, radius_km=radius_km,
            entity_type=entity_type, after_seq=after_seq,
            page_size=page_size,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v3/movement/track")
def world_armor_movement_track(
    response: Response,
    entity_id: str,
    after_seq: int = 0,
    page_size: int = 200,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_movement import track
    try:
        return track(
            entity_id, after_seq=after_seq, page_size=page_size,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v2/source-grants")
def world_armor_source_enroll(
    request: WorldArmorSourceEnrollRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_platform import enroll_source
    try:
        return enroll_source(**request.model_dump())
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v2/source-grants")
def world_armor_sources(
    response: Response,
    offset: int = 0,
    page_size: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_platform import list_sources
    try:
        return list_sources(offset=offset, page_size=page_size)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v2/source-grants/transition")
def world_armor_source_transition(
    request: WorldArmorSourceActionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_platform import transition_source
    try:
        return transition_source(request.source_id, request.action)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v2/source-grants/forget")
def world_armor_source_forget(
    request: WorldArmorSourceIDRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_platform import forget_source
    try:
        return forget_source(request.source_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v2/sources/observe")
def world_armor_source_observe(
    request: WorldArmorSourceIDRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_observe import observe_source
    try:
        return observe_source(request.source_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v2/observations")
def world_armor_source_observations(
    response: Response,
    source_id: str | None = None,
    after_seq: int = 0,
    page_size: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_platform import observations
    try:
        return observations(source_id=source_id, after_seq=after_seq,
                            page_size=page_size)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v2/notices")
def world_armor_source_notices(
    response: Response,
    source_id: str | None = None,
    after_seq: int = 0,
    page_size: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_platform import notices
    try:
        return notices(source_id=source_id, after_seq=after_seq,
                       page_size=page_size)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v2/plan")
def world_armor_source_plan(
    request: WorldArmorSourcePlanRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_platform import plan
    try:
        return plan(source_ids=request.source_ids,
                    max_concurrent=request.max_concurrent)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.get("/world-armor/v2/combined-evidence")
def world_armor_combined_evidence(
    response: Response,
    investigation_id: str,
    after_seq: int = 0,
    page_size: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_graph import combined_evidence
    try:
        return combined_evidence(investigation_id,
                                 after_seq=after_seq,page_size=page_size)
    except (ValueError, KeyError, RuntimeError) as exc:
        _world_armor_platform_error(exc)


@app.post("/world-armor/v1/cameras/page-media")
def world_armor_camera_page_media(
    request: WorldArmorPublicPageRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_cameras import _authorize_camera
    from jarvis_mrb.public_camera_media import discover_public_page_media
    try:
        _authorize_camera()
        return discover_public_page_media(request.public_url)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/cameras/discover")
def world_armor_camera_discover(
    request: WorldArmorPublicCameraSearchRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_cameras import discover_public_cameras_global
    try:
        return discover_public_cameras_global(
            request.latitude, request.longitude,
            radius_km=request.radius_km, limit=request.limit,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/cameras/import-watch")
def world_armor_camera_import_watch(
    request: WorldArmorImportCameraWatchRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_cameras import import_external_camera_watch
    try:
        return import_external_camera_watch(
            request.investigation_id, request.watch_id,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/cameras/inspect")
def world_armor_camera_inspect(
    request: WorldArmorCameraInspectRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_cameras import inspect_camera
    try:
        return inspect_camera(
            request.investigation_id, camera_ref=request.camera_ref,
            public_url=request.public_url, condition=request.condition,
        )
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="Public camera source or local vision service unavailable.",
        ) from exc


@app.get("/world-armor/v1/cameras/receipts")
def world_armor_camera_receipts(
    response: Response,
    investigation_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_cameras import list_camera_receipts
    try:
        return list_camera_receipts(investigation_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/cameras/forget")
def world_armor_camera_forget(
    request: WorldArmorCameraReceiptIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_cameras import forget_camera_receipt
    try:
        return forget_camera_receipt(request.receipt_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/world-armor/v1/forget")
def world_armor_forget(
    request: WorldArmorIdRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.world_armor_phase1 import forget
    try:
        return forget(request.investigation_id)
    except (ValueError, KeyError, RuntimeError) as exc:
        _armor_error(exc)


@app.post("/conductor/workstation/plan")
def conductor_workstation_plan(
    request: ConductorPlanRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb import conductor
    try:
        return conductor.plan(
            request.node_id, request.apps, screen=request.screen_requested
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    except conductor.MissionBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)[:200]) from exc


@app.post("/conductor/workstation/execute")
def conductor_workstation_execute(
    request: ConductorExecuteRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb import conductor
    try:
        return conductor.execute(
            request.id, request.one_use_grant, request.node_id, request.apps
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    except conductor.MissionBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)[:200]) from exc


@app.get("/conductor/workstation/recent")
def conductor_workstation_recent(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb import conductor
    return conductor.recent()


@app.post("/conductor/workstation/status")
def conductor_workstation_status(
    request: ConductorMissionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb import conductor
    try:
        return conductor.get(request.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)[:200]) from exc


@app.post("/conductor/workstation/revoke")
def conductor_workstation_revoke(
    request: ConductorMissionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb import conductor
    try:
        return conductor.revoke(request.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)[:200]) from exc


@app.post("/mesh/app/open")
def reality_mesh_open_exact_mac_app(
    request: MeshAppLaunchRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_mesh import (
        launch_exact_mac_app, launch_exact_windows_app, NodeUnavailable
    )
    try:
        if request.node_id == "windows":
            return launch_exact_windows_app(request.app_name)
        return launch_exact_mac_app(request.node_id, request.app_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    except NodeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:200]) from exc


@app.get("/mesh/nodes")
def reality_mesh_nodes(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_mesh import nodes
    return nodes()


@app.get("/mesh/public-sources")
def reality_mesh_public_sources(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_mesh import public_sources
    return public_sources()


@app.post("/mesh/place")
def reality_mesh_place(
    request: PhysicalConditionsRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_mesh import observe_place
    try:
        return observe_place(request.latitude, request.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:250]) from exc




@app.get("/mesh/graph/fabric")
def reality_graph_fabric(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph import build_fabric_graph
    return build_fabric_graph()


@app.post("/mesh/graph")
def reality_graph_snapshot(
    request: PhysicalConditionsRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph import build_place_graph
    try:
        return build_place_graph(request.latitude, request.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:250]) from exc


# Life Fabric is a separately authorized personal ledger. These endpoints
# never initiate payment, contact a third party or control any device.
@app.get("/life/capabilities")
def life_capabilities(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import capabilities
    return capabilities()


@app.post("/life/records/create")
def life_record_create(
    request: LifeCreateRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import create
    try:
        return create(**request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.get("/life/records")
def life_records(
    response: Response,
    kind: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import list_records
    try:
        return list_records(kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/life/records/receipt")
def life_record_receipt(
    request: LifeReceiptRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import receipt
    try:
        return receipt(request.record_id, outcome=request.outcome,
                       source_kind=request.source_kind, evidence_ref=request.evidence_ref,
                       expected_version=request.expected_version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/life/records/retire")
def life_record_retire(
    request: LifeRetireRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import retire
    try:
        return retire(request.record_id, expected_version=request.expected_version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/life/records/forget")
def life_record_forget(
    request: LifeRetireRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import forget
    try:
        return forget(request.record_id, expected_version=request.expected_version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/life/friction/clear")
def life_friction_clear(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import clear_friction
    return clear_friction()


@app.get("/life/readiness")
def life_readiness(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import readiness
    return readiness()


@app.post("/life/transition")
def life_transition(
    request: LifeTransitionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import transition
    try:
        return transition(request.template, request.title,
                          client_request_id=request.client_request_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/life/handoff")
def life_handoff(
    request: LifeHandoffRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import handoff
    try:
        return handoff(request.title, request.summary, request.next_step,
                       request.linked_ids, client_request_id=request.client_request_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/life/handoff/resume")
def life_handoff_resume(
    request: LifeRecordRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import resume
    try:
        return resume(request.record_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/life/friction/log")
def life_friction_log(
    request: LifeFrictionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import friction
    try:
        return friction(request.label, occurred_at=request.occurred_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.get("/life/friction/candidates")
def life_friction_candidates(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import friction_candidates
    return friction_candidates()


@app.post("/life/what-if/minutes")
def life_what_if_minutes(
    request: LifeWhatIfRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.life_fabric import simulate_minutes
    try:
        return simulate_minutes(**request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/reality/lens/sense")
def reality_lens_sense(
    request: RealityLensRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """One explicit place observation; memory is strictly opt-in per request."""
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_lens import sense_place
    try:
        return sense_place(request.latitude, request.longitude,
                           request.label, remember=request.remember)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.get("/reality/lens/memories")
def reality_lens_memories(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_lens import list_memories
    return list_memories()


@app.post("/reality/lens/forget")
def reality_lens_forget(
    request: RealityLensForgetRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_lens import forget_place
    try:
        return forget_place(request.latitude, request.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc


@app.post("/mesh/graph/context")
def reality_graph_context(
    request: PhysicalConditionsRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph import build_place_graph, model_context
    try:
        return model_context(build_place_graph(request.latitude, request.longitude))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:250]) from exc


@app.post("/mesh/graph/answer")
def reality_graph_answer(
    request: RealityGraphQuestionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph import build_place_graph, answer_place_question, model_context
    try:
        graph = build_place_graph(request.latitude, request.longitude)
        direct = answer_place_question(graph, request.question)
        if direct is not None:
            return direct
        return {
            "answered_without_model": False,
            "reason": "No deterministic rule matched; use the bounded semantic packet only if model reasoning is necessary.",
            "model_context": model_context(graph),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:250]) from exc


@app.post("/mesh/graph/mission")
def reality_graph_mission(
    request: RealityGraphMissionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Normalize/correlate already-authorized provider observations; no actuation."""
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph import build_mission_graph, answer_mission_question, model_context
    graph = build_mission_graph(request.mission, request.observations)
    if request.question:
        direct = answer_mission_question(graph, request.question)
        if direct is not None:
            return {"graph": graph, "answer": direct}
    return {
        "graph": graph,
        "answer": None,
        "model_context": model_context(graph),
        "model_needed": bool(request.question),
    }


def _stored_graph_error(exc: Exception) -> None:
    from jarvis_mrb.reality_graph_missions import GraphUnavailable
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)[:200]) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    if isinstance(exc, GraphUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)[:200]) from exc
    raise exc


@app.post("/mesh/graph/missions/create")
def reality_graph_stored_create(
    request: RealityGraphCreateRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph_missions import create
    try:
        return create(request.goal, deadline=request.deadline, lifetime_hours=request.lifetime_hours)
    except (KeyError, ValueError, RuntimeError) as exc:
        _stored_graph_error(exc)


@app.post("/mesh/graph/missions/append")
def reality_graph_stored_append(
    request: RealityGraphAppendRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph_missions import append
    try:
        return append(request.mission_id, request.observations)
    except (KeyError, ValueError, RuntimeError) as exc:
        _stored_graph_error(exc)


@app.post("/mesh/graph/missions/snapshot")
def reality_graph_stored_snapshot(
    request: RealityGraphStoredRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph_missions import snapshot
    try:
        return snapshot(request.mission_id, question=request.question)
    except (KeyError, ValueError, RuntimeError) as exc:
        _stored_graph_error(exc)


@app.post("/mesh/graph/missions/stop")
def reality_graph_stored_stop(
    request: RealityGraphStoredRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph_missions import stop
    try:
        return stop(request.mission_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _stored_graph_error(exc)


@app.post("/mesh/graph/missions/delete")
def reality_graph_stored_delete(
    request: RealityGraphStoredRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_graph_missions import delete
    try:
        return delete(request.mission_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        _stored_graph_error(exc)


@app.post("/mesh/screen/begin")
def reality_mesh_screen_begin(
    request: MeshNodeSessionRequest,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_mesh_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.reality_mesh import begin_screen, NodeUnavailable
    try:
        return begin_screen(request.node_id, seconds=request.duration_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    except NodeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:200]) from exc


@app.post("/mesh/screen/stop")
def reality_mesh_screen_stop(
    request: MeshNodeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _check_mesh_auth(authorization)
    from jarvis_mrb.reality_mesh import finish_screen, NodeUnavailable
    try:
        return finish_screen(request.node_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    except NodeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:200]) from exc


@app.get("/mesh/screen/{node_id}")
def reality_mesh_screen_frame(
    node_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _check_mesh_auth(authorization)
    from jarvis_mrb.reality_mesh import frame, NodeUnavailable
    try:
        data, media_type = frame(node_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:200]) from exc
    except NodeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:200]) from exc
    return Response(
        content=data, media_type=media_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/missions/affordances")
def mission_affordance_catalog(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """No execution: named real tool contracts and permission boundaries."""
    _check_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.mission_affordances import catalog
    return catalog()


@app.get("/guardian/calendar")
def guardian_calendar_expectations(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Read-only, authenticated upcoming expectations for local iPhone evaluation.

    Never send raw GPS or navigation history to the Jarvis backend. Calendar
    summaries/locations are returned only to this authorized phone request;
    MapKit resolves the destination and estimates travel on-device.
    """
    _check_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.tools.google import query_calendar_events
    from datetime import datetime, timezone

    result = query_calendar_events(direction="future", days=1, limit=12)
    if not result.ok:
        # Unavailable calendar is unknown, NOT evidence of no commitments.
        raise HTTPException(status_code=503, detail="Calendar unavailable for Guardian.")
    raw = (result.data or {}).get("events") or []
    events = []
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        start = str(item.get("start") or "")[:48]
        # Ignore all-day events, which are not travel deadlines.
        if "T" not in start or not str(item.get("location") or "").strip():
            continue
        events.append({
            "id": str(item.get("id") or "")[:180],
            "summary": str(item.get("summary") or "Appointment")[:160],
            "start": start,
            "location": str(item.get("location") or "").strip()[:300],
        })
    return {
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
    }


@app.get("/guardian/objectives")
def guardian_objective_overview(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.guardian_objectives import overview
    return overview()


@app.get("/guardian/objectives/evaluate")
def guardian_objective_evaluation(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    from jarvis_mrb.guardian_objectives import evaluate_once
    return {"evaluations": evaluate_once(emit=False)}


@app.post("/guardian/objectives/enroll")
def guardian_objective_enroll(
    request: GuardianObjectiveRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.guardian_objectives import enroll
    try:
        return enroll(request.id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:320]) from exc


@app.post("/guardian/objectives/revoke")
def guardian_objective_revoke(
    request: GuardianObjectiveRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.guardian_objectives import revoke
    try:
        return revoke(request.id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:320]) from exc


@app.post("/guardian/objectives/snooze")
def guardian_objective_snooze(
    request: GuardianObjectiveSnoozeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.guardian_objectives import snooze
    try:
        return snooze(request.id, hours=request.hours)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:320]) from exc


@app.get("/ambient/status")
def ambient_opportunity_status(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.sensor_opportunities import status
    return status()


@app.post("/external/watch/create")
def external_watch_create(
    request: ExternalWatchCreateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.external_watches import create_watch
    try:
        return create_watch(
            request.scope, request.kind, request.label, request.config,
            interval_seconds=request.interval_seconds, expires_hours=request.expires_hours,
        )
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:300]) from exc


@app.post("/external/watch/list")
def external_watch_list(
    request: ExternalWatchLookupRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.external_watches import list_watches
    try:
        return {"watches": list_watches(request.scope)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/watch/check")
def external_watch_check(
    request: ExternalWatchLookupRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.external_watches import check_watch
    try:
        return check_watch(request.id, request.scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/watch/stop")
def external_watch_stop(
    request: ExternalWatchLookupRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.external_watches import stop_watch
    try:
        return stop_watch(request.id, request.scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/watch/history")
def external_watch_history(
    request: ExternalWatchLookupRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.external_watches import watch_history
    try:
        return {"observations": watch_history(request.id, request.scope)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/diligence/list")
def external_diligence_list(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.matter_diligence import list_matters
    return {"matters": list_matters()}


@app.post("/external/diligence/matter")
def external_diligence_matter(
    request: DiligenceMatterRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.matter_diligence import create_matter
    try:
        return create_matter(request.label, project_entity_id=request.project_entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/diligence/issuer")
def external_diligence_issuer(
    request: DiligenceIssuerRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.matter_diligence import add_issuer
    try:
        return add_issuer(request.matter_id, request.cik, request.asserted_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/diligence/epa-facility")
def external_diligence_epa_facility(
    request: DiligenceEPAFacilityRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.matter_diligence import add_epa_facility
    try:
        return add_epa_facility(
            request.matter_id, request.cik, request.frs_id, request.label
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/epa/facility")
def external_epa_facility(
    request: EPADirectLookupRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.public_epa import fetch_epa_facility
    try:
        return fetch_epa_facility(request.frs_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="EPA ECHO source unavailable.") from exc


@app.post("/external/diligence/claim")
def external_diligence_claim(
    request: DiligenceClaimRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.matter_diligence import add_numeric_claim
    try:
        return add_numeric_claim(
            request.matter_id, request.cik,
            taxonomy=request.taxonomy, tag=request.tag,
            unit=request.unit, value=request.value,
            end=request.end, start=request.start,
            source_ref=request.source_ref, context=request.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/diligence/check")
def external_diligence_check(
    request: DiligenceLookupRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.matter_diligence import check_matter
    try:
        return check_matter(request.matter_id, include_sanctions=request.include_sanctions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/external/diligence/view")
def external_diligence_view(
    request: DiligenceLookupRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.matter_diligence import get_matter
    try:
        return get_matter(request.matter_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/physical/incidents")
def public_incident_region(
    request: PhysicalConditionsRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Official recent earthquake detections, not comprehensive emergency dispatch."""
    _check_auth(authorization)
    from jarvis_mrb.public_incidents import regional_earthquakes
    try:
        return regional_earthquakes(request.latitude, request.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/physical/airspace")
def public_airspace_region(
    request: RegionalAirspaceRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.public_airspace import airspace_region
    try:
        return airspace_region(
            request.latitude, request.longitude, radius_km=request.radius_km,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/physical/awareness")
def nearby_physical_awareness(
    request: PhysicalConditionsRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """On-demand multisource briefing; no background surveillance."""
    _check_auth(authorization)
    from jarvis_mrb.physical_awareness import physical_awareness
    try:
        return physical_awareness(request.latitude, request.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/physical/public-cameras/analyze")
def analyze_public_camera_still(
    request: OfficialCameraAnalysisRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Explicit one-still vision pass for a catalog-verified public camera ID."""
    _check_auth(authorization)
    from jarvis_mrb.public_camera_vision import analyze_official_still
    try:
        return analyze_official_still(request.camera_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="Published camera or local vision service is unavailable.",
        ) from exc


@app.post("/physical/facilities")
def nearby_public_facilities(
    request: NearbyFacilitiesRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """On-demand public utility map, not a medical/emergency locator guarantee."""
    _check_auth(authorization)
    from jarvis_mrb.public_facilities import nearby_mapped_facilities
    try:
        return nearby_mapped_facilities(
            request.latitude, request.longitude,
            radius_m=request.radius_m, limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/physical/conditions")
def nearby_physical_conditions(
    request: PhysicalConditionsRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """On-demand, authenticated external weather/air lookup. Never an all clear."""
    _check_auth(authorization)
    from jarvis_mrb.physical_conditions import physical_conditions
    try:
        return physical_conditions(request.latitude, request.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/physical/public-cameras")
def nearby_public_cameras(
    request: NearbyPublicCameraRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Opt-in public provider lookup. POST avoids putting coordinates in URL access logs."""
    _check_auth(authorization)
    from jarvis_mrb.public_camera_catalog import discover_public_cameras
    try:
        return discover_public_cameras(
            request.latitude, request.longitude,
            radius_km=request.radius_km, limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/agency/command-view")
def agency_command_view(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Authenticated read-only status for an optional iPhone / glasses display."""
    _check_auth(authorization)
    from jarvis_mrb.agency_command_view import build_command_view
    return build_command_view()


@app.get("/cloud-cognition/status")
def cloud_cognition_status(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.cloud_cognition import telemetry_snapshot
    return telemetry_snapshot()


@app.post("/cloud-cognition/prepare")
def cloud_cognition_prepare(
    request: CloudCognitionPrepareRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.cloud_cognition import prepare_cloud_task

    session_id = request.session_id or "default"
    effective_text = _command_alias(request.text)
    history = _contextual_history(session_id, effective_text, limit=12)
    return prepare_cloud_task(
        effective_text,
        session_id=session_id,
        history=history,
        force=request.mode,
    )


@app.post("/cloud-cognition/resolve", response_model=CommandResponse)
def cloud_cognition_resolve(
    request: CloudCognitionResolveRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> CommandResponse:
    _check_auth(authorization)
    from jarvis_mrb.agent import execute_tool
    from jarvis_mrb.cloud_cognition import (
        consume_cloud_task,
        record_cloud_result,
        record_execution_outcome,
        validate_proposal,
    )

    task = consume_cloud_task(request.task_id)
    proposal = validate_proposal(request.proposal)
    record_cloud_result(task, proposal, request.metadata)

    # Cloud output is a proposal, never authority. Existing deterministic tool
    # dispatch remains the only execution path and therefore keeps the normal
    # permissions, confirmations, audit and verification semantics.
    if proposal.tool:
        reply = execute_tool(proposal.tool, proposal.arguments)
        message = _voice_safe_confirmation(reply.message)
        record_execution_outcome(task, proposal, ok=reply.ok, outcome=message)
        return CommandResponse(ok=reply.ok, message=message)
    message = proposal.response or "I could not form a useful cloud answer."
    record_execution_outcome(task, proposal, ok=True, outcome=message)
    return CommandResponse(ok=True, message=message)


@app.post("/cloud-cognition/feedback")
def cloud_cognition_feedback(
    request: CloudCognitionFeedbackRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_auth(authorization)
    from jarvis_mrb.cloud_cognition import record_routing_feedback
    record_routing_feedback(
        request_fingerprint=request.request_fingerprint,
        user_corrected=request.user_corrected,
        cloud_materially_changed_result=request.cloud_materially_changed_result,
        note=request.note,
    )
    return {"ok": True}


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
            message = f"Streaming failed: {exc}"
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
