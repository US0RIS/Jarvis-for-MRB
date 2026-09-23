from __future__ import annotations

"""Jarvis Reality Mesh, first *actual* cross-device read-only execution slice.

No network discovery, unapproved target URLs, arbitrary RPC, device control,
screen recording without Mac and phone consent, or inferred provider coverage.
Configured Mac endpoints/tokens live ONLY in Windows process environment.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import ipaddress
import json
import os
import platform
from urllib.parse import urlsplit
from typing import Any

import httpx

_IDS = ("macbook", "macmini")
_MAX_BODY = 4_000_000
_MAX_JSON = 32_768


class NodeUnavailable(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config(node_id: str) -> tuple[str, str] | None:
    if node_id not in _IDS:
        raise ValueError("Only explicitly configured MacBook and Mac mini nodes are supported.")
    prefix = "JARVIS_MESH_" + node_id.upper()
    base = str(os.environ.get(prefix + "_URL", "")).strip().rstrip("/")
    token = str(os.environ.get(prefix + "_TOKEN", "")).strip()
    if not base or not token:
        return None
    if len(token) < 32:
        return None
    parsed = urlsplit(base)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or parsed.port not in range(1, 65536)):
        return None
    host = parsed.hostname or ""
    # Never let these credentials traverse the open Internet or a hostname
    # supplied in a request. Tailscale MagicDNS HTTPS is supported separately.
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if parsed.scheme != "https" or not host.endswith(".ts.net"):
            return None
    else:
        tailscale = ipaddress.ip_network("100.64.0.0/10")
        if parsed.scheme != "http" or not (
            address.is_loopback or address in tailscale
        ):
            return None
    return base, token


def _request(node_id: str, method: str, path: str, *,
             payload: dict[str, Any] | None = None,
             image: bool = False) -> tuple[dict[str, Any] | None, bytes | None, str]:
    config = _config(node_id)
    if config is None:
        raise NodeUnavailable("not configured or private transport/token invalid")
    base, token = config
    if method not in {"GET", "POST", "DELETE"} or path not in {
        "/v1/health", "/v1/context", "/v1/session", "/v1/screen"
    }:
        raise ValueError("Unregistered mesh method/path.")
    try:
        with httpx.Client(
            timeout=httpx.Timeout(6.0 if image else 2.5, connect=1.2),
            follow_redirects=False, trust_env=False
        ) as client:
            with client.stream(
                method, base + path,
                headers={"Authorization": "Bearer " + token,
                         "Accept": "image/jpeg,image/png" if image else "application/json"},
                json=payload,
            ) as response:
                if response.status_code != 200 or response.is_redirect:
                    raise NodeUnavailable("node rejected request or Mac permission is unavailable")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                if image:
                    if content_type not in {"image/jpeg", "image/png"}:
                        raise NodeUnavailable("node returned non-image screen data")
                    maximum = _MAX_BODY
                else:
                    if content_type != "application/json":
                        raise NodeUnavailable("node returned unexpected status content")
                    maximum = _MAX_JSON
                chunks = bytearray()
                for piece in response.iter_bytes():
                    chunks.extend(piece)
                    if len(chunks) > maximum:
                        raise NodeUnavailable("node response exceeds safe transfer limit")
                if image:
                    # Enforce recognizable binary signature, not just Content-Type.
                    valid = chunks.startswith(b"\xff\xd8\xff") if content_type == "image/jpeg" else chunks.startswith(b"\x89PNG\r\n\x1a\n")
                    if not valid or len(chunks) < 80:
                        raise NodeUnavailable("invalid image bytes returned by node")
                    return None, bytes(chunks), content_type
                decoded = json.loads(chunks)
                if not isinstance(decoded, dict):
                    raise NodeUnavailable("invalid node JSON response")
                return decoded, None, content_type
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise NodeUnavailable("node could not be reached or response was invalid") from exc


def probe(node_id: str) -> dict[str, Any]:
    record = {
        "id": node_id,
        "label": "MacBook Air" if node_id == "macbook" else "Mac mini",
        "status": "unconfigured" if _config(node_id) is None else "unavailable",
        "checked_at": _now(),
        "platform": "macos",
        "capabilities": {"context": "unknown", "screen": "unknown"},
        "screen_session_active": False,
        "evidence": "Explicit configuration absent; no host discovery.",
    }
    if record["status"] == "unconfigured":
        return record
    try:
        data, _, _ = _request(node_id, "GET", "/v1/health")
        if not data or data.get("protocol") != 1 or data.get("device_id") != node_id:
            raise NodeUnavailable("node identity or protocol mismatch")
        if data.get("platform") != "darwin" or not isinstance(data.get("capabilities"), dict):
            raise NodeUnavailable("node platform/capabilities mismatch")
        try:
            observed = datetime.fromisoformat(str(data["observed_at"]).replace("Z", "+00:00"))
            if observed.tzinfo is None or abs((datetime.now(timezone.utc) - observed).total_seconds()) > 30:
                raise NodeUnavailable("node clock/observation is stale")
        except (KeyError, ValueError, TypeError):
            raise NodeUnavailable("node observation time absent")
        record.update({
            "status": "online",
            "label": str(data.get("label") or record["label"])[:100],
            "observed_at": data["observed_at"],
            "capabilities": data["capabilities"],
            "screen_session_active": data.get("screen_session_active") is True,
            "evidence": "Live authenticated response from matching explicitly configured macOS node.",
        })
    except NodeUnavailable as exc:
        record["evidence"] = str(exc)
    return record


def nodes() -> dict[str, Any]:
    from jarvis_mrb.pc_context import snapshot

    checked = _now()
    windows = {
        "id": "windows",
        "label": "Jarvis Windows host",
        "status": "online" if platform.system() == "Windows" else "local_test_host",
        "platform": platform.system().lower(),
        "checked_at": checked,
        "capabilities": {
            "context": "read_only",
            "screen": "not_implemented",
            "remote_input": "not_implemented",
            "file_transfer": "not_implemented",
        },
        "screen_session_active": False,
        "evidence": "Jarvis service is responding on this host; no desktop image asserted.",
    }
    try:
        context = snapshot()
        windows["foreground_app"] = str(context.get("foreground_process") or "")[:100]
        windows["context_observed_at"] = context.get("captured_at")
    except Exception:
        windows["foreground_app"] = ""
        windows["context_observed_at"] = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(probe, _IDS))
    return {
        "checked_at": checked,
        "automatic_network_scanning": False,
        "machine_action_authority": "No remote input or arbitrary command RPC",
        "nodes": [windows, *results],
    }


def _valid_node(node_id: str) -> None:
    if node_id not in _IDS:
        raise ValueError("This node does not offer a paired screen session.")
    status = probe(node_id)
    if status["status"] != "online":
        raise NodeUnavailable("Mac node not live, authenticated and identity-verified.")
    if status["capabilities"].get("screen") != "session_opt_in":
        raise NodeUnavailable("Mac has not opted into explicit screen sessions.")


def begin_screen(node_id: str, *, seconds: int = 120) -> dict[str, Any]:
    if type(seconds) is not int or not 15 <= seconds <= 300:
        raise ValueError("Screen consent must be 15–300 seconds.")
    _valid_node(node_id)
    response, _, _ = _request(
        node_id, "POST", "/v1/session",
        payload={"duration_seconds": seconds}
    )
    if not response or response.get("status") != "active" or response.get("device_id") != node_id:
        raise NodeUnavailable("Mac did not confirm a new exact-node screen session.")
    return {
        "node_id": node_id,
        "status": "active",
        "expires_at": response["expires_at"],
        "source": "Mac screen with Mac startup opt-in and explicit iPhone session",
    }


def finish_screen(node_id: str) -> dict[str, str]:
    if node_id not in _IDS:
        raise ValueError("Not a screen-enabled mesh node.")
    _request(node_id, "DELETE", "/v1/session")
    return {"node_id": node_id, "status": "closed"}


def frame(node_id: str) -> tuple[bytes, str]:
    if node_id not in _IDS:
        raise ValueError("Not a screen-enabled mesh node.")
    if _config(node_id) is None:
        raise NodeUnavailable("Mac node is not configured")
    _, data, media = _request(node_id, "GET", "/v1/screen", image=True)
    if data is None:
        raise NodeUnavailable("No screen returned")
    return data, media


def public_sources() -> dict[str, Any]:
    """Provider registry/coverage is descriptive; nothing is queried here."""
    return {
        "checked_at": _now(),
        "registry_is_coverage_not_live_observation": True,
        "sources": [
            {
                "id": "caltrans_cwwp2",
                "label": "Caltrans official highway traffic cameras",
                "coverage": "California state highway camera catalog only",
                "kind": "catalog and periodically refreshed still/stream URLs",
                "status": "integrated_not_checked",
                "source_url": "https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm",
            },
            {
                "id": "openmeteo_air",
                "label": "Open-Meteo / CAMS modelled air quality",
                "coverage": "Global model, coarse resolution; not a local sensor",
                "kind": "modelled public environmental data",
                "status": "integrated_not_checked",
                "source_url": "https://open-meteo.com/en/docs/air-quality-api",
            },
            {
                "id": "nws",
                "label": "National Weather Service active alerts",
                "coverage": "United States supported points; not Melbourne or global",
                "kind": "official weather point alerts",
                "status": "integrated_not_checked",
                "source_url": "https://www.weather.gov/documentation/services-web-alerts",
            },
            {
                "id": "usgs",
                "label": "USGS regional earthquake event feed",
                "coverage": "Reported earthquake events, not all hazards",
                "kind": "official event reports",
                "status": "integrated_not_checked",
                "source_url": "https://earthquake.usgs.gov/fdsnws/event/1/",
            },
            {
                "id": "osm",
                "label": "OpenStreetMap public facilities",
                "coverage": "Community-mapped facilities; completeness not assured",
                "kind": "public map observations",
                "status": "integrated_not_checked",
                "source_url": "https://www.openstreetmap.org/",
            },
        ],
    }


def observe_place(latitude: float, longitude: float) -> dict[str, Any]:
    from jarvis_mrb.physical_awareness import physical_awareness
    from jarvis_mrb.physical_conditions import _validate_position

    _validate_position(latitude, longitude)
    snapshot = physical_awareness(latitude, longitude)
    return {
        "checked_at": _now(),
        "world_graph_kind": "one_time_place_observation",
        "source_coverage_is_not_completeness": True,
        "coordinates_stored_by_mesh": False,
        "data": snapshot,
        "notes": (
            "Independent providers; no inference that no published event means "
            "no hazard. Unsupported local traffic camera areas remain unsupported."
        ),
    }
