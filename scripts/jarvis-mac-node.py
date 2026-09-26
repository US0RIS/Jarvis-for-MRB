#!/usr/bin/env python3
"""Explicitly started, read-only Jarvis macOS node.

Bind to loopback by default, or to an explicitly supplied Tailscale IP.
The parent Jarvis Windows service is the ONLY intended remote caller.
This process never runs arbitrary user-supplied shell commands or exposes files.
Screen capture is opt-in twice: --allow-screen on the Mac, then a short-lived
session requested from Jarvis's authenticated phone UI. macOS Screen Recording
permission must independently be granted to the terminal/Python executable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
import ipaddress
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VERSION = 1
MAX_SCREEN_BYTES = 4_000_000
MAX_SESSION_SECONDS = 300
MAX_REQUEST_BYTES = 4096
MAX_WORLD_BYTES = 8_000_000
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
_EXACT_APPS = ("Safari", "Notes", "Calendar", "Preview", "Finder")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(now: datetime) -> str:
    return now.isoformat()


class NodeState:
    def __init__(self, *, token: str, device_id: str, label: str,
                 allow_screen: bool = False,
                 allow_app_launch: bool = False,
                 allow_world_observer: bool = False,
                 world_capacity: int = 1) -> None:
        if len(token) < 32:
            raise ValueError("Node bearer token must be at least 32 random characters.")
        if not device_id or not device_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Device ID must use only letters, digits, - and _.")
        self.token = token
        self.device_id = device_id[:48]
        self.label = label[:100]
        self.allow_screen = bool(allow_screen)
        self.allow_app_launch = bool(allow_app_launch)
        if type(world_capacity) is not int or not 1 <= world_capacity <= 16:
            raise ValueError("World observer capacity must be 1–16.")
        self.allow_world_observer = bool(allow_world_observer)
        self.world_capacity = world_capacity
        self.world_active_requests = 0
        self.last_app_request_at = 0.0
        self.last_world_request_at = 0.0
        self.session_expiry: datetime | None = None
        self.lock = threading.RLock()

    def active(self) -> bool:
        with self.lock:
            return bool(self.allow_screen and self.session_expiry
                        and utcnow() < self.session_expiry)

    def start(self, seconds: int) -> str:
        if not self.allow_screen:
            raise PermissionError("Mac screen serving was not enabled at startup.")
        if isinstance(seconds, bool) or not 15 <= seconds <= MAX_SESSION_SECONDS:
            raise ValueError("Screen session must be 15–300 seconds.")
        with self.lock:
            self.session_expiry = utcnow() + timedelta(seconds=seconds)
            return iso(self.session_expiry)

    def end(self) -> None:
        with self.lock:
            self.session_expiry = None

    def authorize_world_observation(self) -> None:
        if not self.allow_world_observer:
            raise PermissionError(
                "Mac was not started with read-only world-observer consent."
            )
        with self.lock:
            now = time.monotonic()
            if self.world_active_requests >= self.world_capacity:
                raise RuntimeError("Mac world-observer capacity is currently full.")
            if now - self.last_world_request_at < 0.05:
                raise RuntimeError("Mac world-observer request rate limited.")
            self.last_world_request_at = now
            self.world_active_requests += 1

    def finish_world_observation(self) -> None:
        with self.lock:
            self.world_active_requests = max(0, self.world_active_requests - 1)

    def worker_metrics(self) -> dict[str, Any]:
        with self.lock:
            active = self.world_active_requests
            capacity = self.world_capacity
        cpus = max(1, int(os.cpu_count() or 1))
        try:
            load = float(os.getloadavg()[0])
        except (AttributeError, OSError):
            load = 0.0
        return {
            "active_requests": active,
            "capacity": capacity,
            "cpu_count": cpus,
            "load_1m": round(load, 3),
            "normalized_load": round(max(0.0, load) / cpus, 4),
        }

    def authorize_exact_app(self, name: str) -> None:
        if name not in _EXACT_APPS:
            raise ValueError("Application not in Jarvis's fixed Mac allowlist.")
        if not self.allow_app_launch or platform.system() != "Darwin":
            raise PermissionError("Mac was not started with explicit app-launch consent.")
        with self.lock:
            now = time.monotonic()
            if now - self.last_app_request_at < 3:
                raise RuntimeError("Mac app launch rate limited.")
            # Reserve before the external side effect. Never retry automatically.
            self.last_app_request_at = now


def _launch_exact_app(name: str) -> dict[str, Any]:
    if name not in _EXACT_APPS or platform.system() != "Darwin":
        raise ValueError("Only fixed registered macOS applications are supported.")
    try:
        launched = subprocess.run(
            ["/usr/bin/open", "-a", name],
            capture_output=True, check=False, timeout=8
        )
        if launched.returncode != 0:
            raise RuntimeError("macOS did not accept the exact app launch request.")
        # Running-process observation is NOT proof of focus or a new window.
        running = subprocess.run(
            ["/usr/bin/pgrep", "-x", name],
            capture_output=True, check=False, timeout=3
        )
        seen = running.returncode == 0
        return {
            "status": ("launch_accepted_process_observed"
                       if seen else "launch_accepted_process_unverified"),
            "app_name": name,
            "process_observed": seen,
            "source": "macOS /usr/bin/open and pgrep; no foreground-focus claim",
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Exact app launch or process check unavailable.") from exc


def _observe_exact_apps() -> dict[str, Any]:
    """Fresh process evidence for an immutable, non-sensitive allowlist only."""
    now = iso(utcnow())
    if platform.system() != "Darwin":
        return {
            "status": "unavailable", "observed_at": now,
            "apps": {}, "source": "non-macOS test host",
        }
    observations: dict[str, str] = {}
    for name in _EXACT_APPS:
        try:
            result = subprocess.run(
                ["/usr/bin/pgrep", "-x", name],
                capture_output=True, timeout=2, check=False,
            )
            observations[name] = (
                "running" if result.returncode == 0 else
                "not_running" if result.returncode == 1 else "unknown"
            )
        except (OSError, subprocess.TimeoutExpired):
            observations[name] = "unknown"
    return {
        "status": "ok" if all(s != "unknown" for s in observations.values())
                  else "partial",
        "observed_at": now,
        "apps": observations,
        "source": "Mac /usr/bin/pgrep -x for five exact app names; "
                  "running process is not focused window or document",
    }


def _capture_screen() -> tuple[str, bytes]:
    if platform.system() != "Darwin":
        raise RuntimeError("Screen capture only implemented on macOS.")
    binary = shutil.which("screencapture")
    if not binary:
        raise RuntimeError("macOS screencapture command is unavailable.")
    with tempfile.TemporaryDirectory(prefix="jarvis-screen-") as folder:
        png = Path(folder) / "private-screen.png"
        try:
            result = subprocess.run(
                [binary, "-x", "-t", "png", str(png)],
                capture_output=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("macOS screen capture could not complete.") from exc
        if result.returncode != 0 or not png.exists() or png.stat().st_size < 80:
            raise RuntimeError("macOS Screen Recording permission or active display unavailable.")
        jpeg = Path(folder) / "private-screen.jpg"
        sips = shutil.which("sips")
        if sips:
            try:
                compressed = subprocess.run(
                    [sips, "-s", "format", "jpeg", "-s", "formatOptions", "60",
                     str(png), "--out", str(jpeg)],
                    capture_output=True, timeout=10, check=False,
                )
                if compressed.returncode == 0 and jpeg.exists() and 80 < jpeg.stat().st_size <= MAX_SCREEN_BYTES:
                    return "image/jpeg", jpeg.read_bytes()
            except (OSError, subprocess.TimeoutExpired):
                pass
        if png.stat().st_size > MAX_SCREEN_BYTES:
            raise RuntimeError("Captured screen exceeds the private 4 MB transfer limit.")
        return "image/png", png.read_bytes()



def _movement_bbox(latitude: float, longitude: float,
                   radius_km: float) -> dict[str, float]:
    if not all(
        isinstance(x, (int, float)) and not isinstance(x, bool)
        for x in (latitude, longitude, radius_km)
    ):
        raise ValueError("Numeric OpenSky region required.")
    lat, lon, radius = float(latitude), float(longitude), float(radius_km)
    if (not -90 <= lat <= 90 or not -180 <= lon <= 180
            or not 0 < radius <= 20_000):
        raise ValueError("OpenSky region outside allowed world geometry.")
    import math
    if radius >= 20_000:
        return {"lamin": -90.0, "lomin": -180.0,
                "lamax": 90.0, "lomax": 180.0}
    dlat = min(90.0, radius / 111.32)
    denom = 111.32 * max(0.01, abs(math.cos(math.radians(lat))))
    dlon = min(180.0, radius / denom)
    return {
        "lamin": max(-90.0, lat - dlat),
        "lomin": max(-180.0, lon - dlon),
        "lamax": min(90.0, lat + dlat),
        "lomax": min(180.0, lon + dlon),
    }


def _world_perception_module():
    # Keep the Mac node lightweight at startup; camera dependencies are loaded
    # only when this explicit observer capability is used.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from jarvis_mrb import world_armor_perception
    return world_armor_perception


def _validate_world_task(payload: dict[str, Any]) -> None:
    kind = payload.get("kind")
    if kind == "opensky_region":
        if set(payload) - {"kind", "latitude", "longitude", "radius_km"}:
            raise ValueError("Unregistered OpenSky observer field.")
        _movement_bbox(
            payload.get("latitude"), payload.get("longitude"),
            payload.get("radius_km"),
        )
        return
    if kind == "camera_source":
        allowed = {
            "kind", "source_kind", "locator", "scene_goal",
            "last_image_hash",
        }
        if set(payload) - allowed:
            raise ValueError("Unregistered camera observer field.")
        if payload.get("source_kind") not in {
            "caltrans", "public_https", "public_http"
        }:
            raise ValueError(
                "Mac camera workers support Caltrans or explicit public media only."
            )
        locator = payload.get("locator")
        if type(locator) is not str or not 1 <= len(locator) <= 1800:
            raise ValueError("Camera locator is absent or oversized.")
        last_hash = payload.get("last_image_hash")
        if last_hash is not None and (
            type(last_hash) is not str or len(last_hash) != 64
            or any(ch not in "0123456789abcdef" for ch in last_hash.lower())
        ):
            raise ValueError("Last camera frame digest is invalid.")
        perception = _world_perception_module()
        perception.validate_scene_goal(payload.get("scene_goal") or "")
        return
    raise ValueError("Unregistered world-observer task.")


def _observe_public_world(payload: dict[str, Any]) -> dict[str, Any]:
    """One typed read-only public-world observation with no action authority."""
    _validate_world_task(payload)
    if payload.get("kind") == "camera_source":
        perception = _world_perception_module()
        frame: bytes | None = None
        try:
            received = perception.acquire_source(
                payload["source_kind"], payload["locator"]
            )
            frame = received.pop("frame")
            digest = received.get("sha256")
            if type(digest) is not str or len(digest) != 64 or not frame:
                raise RuntimeError("Camera adapter yielded no normalized frame.")
            same = payload.get("last_image_hash") == digest
            evaluation = None if same else perception.interpret_frame(
                frame, payload.get("scene_goal") or ""
            )
            return {
                "status": "ok",
                "provider": "public_camera",
                "worker_observed_at": iso(utcnow()),
                "sha256": digest,
                "retrieved_at": received.get("retrieved_at"),
                "media_kind": received.get("media_kind"),
                "source_display": received.get("source_display"),
                "same_published_frame": same,
                "evaluation": evaluation,
                "raw_image_returned": False,
                "source": (
                    "Rights-scoped enrolled public camera fetched and "
                    "interpreted on explicitly opted-in private Mac worker"
                ),
            }
        finally:
            frame = None

    box = _movement_bbox(
        payload.get("latitude"), payload.get("longitude"),
        payload.get("radius_km"),
    )
    query = urlencode({**box, "extended": 1})
    request = Request(
        OPENSKY_STATES_URL + "?" + query,
        headers={
            "Accept": "application/json",
            "User-Agent": "JarvisMeshNode/1 (read-only OpenSky observer)",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=12) as response:
            if response.status != 200:
                raise RuntimeError("OpenSky provider rejected worker request.")
            body = response.read(MAX_WORLD_BYTES + 1)
    except Exception as exc:
        raise RuntimeError("OpenSky worker request unavailable.") from exc
    if len(body) > MAX_WORLD_BYTES:
        raise RuntimeError("OpenSky worker response exceeds transfer budget.")
    try:
        result = json.loads(body)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise RuntimeError("OpenSky worker returned invalid JSON.") from exc
    if (not isinstance(result, dict)
            or not isinstance(result.get("states"), (list, type(None)))
            or not isinstance(result.get("time"), (int, float))):
        raise RuntimeError("OpenSky worker response has unsupported schema.")
    return {
        "status": "ok",
        "provider": "opensky",
        "worker_observed_at": iso(utcnow()),
        "provider_payload": result,
        "source": "OpenSky fetched by explicitly opted-in private Mac worker",
    }

def handler_for(state: NodeState) -> type[BaseHTTPRequestHandler]:
    class NodeHandler(BaseHTTPRequestHandler):
        server_version = "JarvisMeshNode/1"
        sys_version = ""

        def log_message(self, _format: str, *_args: object) -> None:
            # Never include auth, body, private screen contents or paths in logs.
            return

        def _authorized(self) -> bool:
            expected = "Bearer " + state.token
            value = self.headers.get("Authorization", "")
            if not hmac.compare_digest(value, expected):
                self._json(401, {"status": "unauthorized"})
                return False
            return True

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _context(self) -> dict[str, Any]:
            return {
                "protocol": VERSION,
                "device_id": state.device_id,
                "label": state.label,
                "platform": platform.system().lower(),
                "observed_at": iso(utcnow()),
                "capabilities": {
                    "status": "read_only",
                    "screen": ("session_opt_in" if state.allow_screen else "disabled"),
                    "app_launch": (
                        "exact_user_tap_only"
                        if state.allow_app_launch and platform.system() == "Darwin"
                        else "disabled"
                    ),
                    "remote_input": "not_implemented",
                    "clipboard": "not_implemented",
                    "file_transfer": "not_implemented",
                    "world_observer": (
                        "opensky_region_read_only"
                        if state.allow_world_observer else "disabled"
                    ),
                    "world_observer_capabilities": (
                        [
                            "opensky_region_read_only",
                            "camera_source_analysis_read_only",
                        ]
                        if state.allow_world_observer else []
                    ),
                },
                "worker_metrics": state.worker_metrics(),
                "screen_session_active": state.active(),
                "host": platform.node()[:100],
                "macos_screen_recording_permission": "not_probed",
            }

        def do_GET(self) -> None:
            if not self._authorized():
                return
            if self.path in {"/v1/health", "/v1/context"}:
                self._json(200, self._context())
                return
            if self.path == "/v1/apps":
                self._json(200, {"device_id": state.device_id,
                                 **_observe_exact_apps()})
                return
            if self.path != "/v1/screen":
                self._json(404, {"status": "not_found"})
                return
            if not state.active():
                self._json(403, {"status": "screen_session_expired_or_disabled"})
                return
            try:
                media, data = _capture_screen()
            except RuntimeError:
                self._json(503, {"status": "screen_capture_unavailable",
                                 "reason": "Check Mac Screen Recording permission, active display and image limit."})
                return
            if not state.active():  # expiry/revocation during capture vetoes output
                self._json(403, {"status": "screen_session_expired_or_disabled"})
                return
            self.send_response(200)
            self.send_header("Content-Type", media)
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            if not self._authorized():
                return
            if self.path not in {
                "/v1/session", "/v1/app/open", "/v1/world/observe"
            }:
                self._json(404, {"status": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= MAX_REQUEST_BYTES:
                    raise ValueError("Invalid request size.")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("JSON object required.")
                if self.path == "/v1/world/observe":
                    _validate_world_task(payload)
                    state.authorize_world_observation()
                    try:
                        result = _observe_public_world(payload)
                        self._json(200, {
                            **result, "device_id": state.device_id,
                        })
                    finally:
                        state.finish_world_observation()
                    return
                if self.path == "/v1/app/open":
                    name = payload.get("app_name")
                    if not isinstance(name, str):
                        raise ValueError("Exact application required.")
                    state.authorize_exact_app(name)
                    result = _launch_exact_app(name)
                    self._json(200, {**result, "device_id": state.device_id})
                    return
                duration = payload.get("duration_seconds", 120)
                if type(duration) is not int:
                    raise ValueError("Duration must be a number of seconds.")
                expiry = state.start(duration)
                self._json(200, {"status": "active", "expires_at": expiry,
                                 "device_id": state.device_id})
            except (ValueError, TypeError, AttributeError):
                self._json(422, {"status": "invalid_session_or_app_request"})
            except PermissionError:
                self._json(403, {"status": "mac_startup_opt_in_required"})
            except RuntimeError:
                self._json(503, {"status": "opted_in_node_operation_unavailable_or_rate_limited"})

        def do_DELETE(self) -> None:
            if not self._authorized():
                return
            if self.path != "/v1/session":
                self._json(404, {"status": "not_found"})
                return
            state.end()
            self._json(200, {"status": "closed", "device_id": state.device_id})

    return NodeHandler


def _bind_address(value: str) -> str:
    addr = ipaddress.ip_address(value)
    if addr.is_loopback:
        return value
    if not addr.version == 4 or not addr in ipaddress.ip_network("100.64.0.0/10"):
        raise ValueError("Mac node must bind to loopback or its explicit Tailscale IPv4 address.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis read-only Mac mesh node")
    parser.add_argument("--bind", default="127.0.0.1",
                        help="127.0.0.1, or this Mac's own Tailscale 100.64.0.0/10 IPv4")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--device-id", required=True,
                        help="Explicit registered observer ID, e.g. macbook, macmini, observer-3")
    parser.add_argument("--label", default="Jarvis Mac")
    parser.add_argument("--world-capacity", type=int, default=1,
                        help="Maximum concurrent typed World Armor observations (1–16)")
    parser.add_argument("--allow-screen", action="store_true",
                        help="Explicitly allow 15–300s phone-initiated screenshot sessions")
    parser.add_argument("--allow-app-launch", action="store_true",
                        help="Separately enable five fixed Mac app names by explicit phone tap")
    parser.add_argument("--allow-world-observer", action="store_true",
                        help="Enable typed read-only OpenSky and enrolled public-camera observations for World Armor")
    args = parser.parse_args()
    token = os.environ.get("JARVIS_MESH_NODE_TOKEN", "")
    if not 1 <= args.port <= 65535:
        parser.error("Invalid TCP port")
    state = NodeState(
        token=token, device_id=args.device_id, label=args.label,
        allow_screen=args.allow_screen,
        allow_app_launch=args.allow_app_launch,
        allow_world_observer=args.allow_world_observer,
        world_capacity=args.world_capacity,
    )
    host = _bind_address(args.bind)
    server = ThreadingHTTPServer((host, args.port), handler_for(state))
    print(f"Jarvis Mac node {state.device_id}: listening on {host}:{args.port}; "
          f"screen opt-in: {state.allow_screen}; exact app launch opt-in: "
          f"{state.allow_app_launch}; world observer opt-in: "
          f"{state.allow_world_observer}; Mac OS permissions still apply.",
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
