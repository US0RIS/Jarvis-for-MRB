from __future__ import annotations

"""Operator-run, source/device Reality Mesh acceptance check.

Default mode does no network probing or screen capture. --probe does live
authenticated status probes to only explicitly configured private Mac nodes.
--exercise-screen NODE is deliberately opt-in; it briefly views exactly one
host screen in RAM, verifies type/length and always tries to revoke consent.
No image bytes, authentication secrets or configured network URLs are printed.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import platform
from typing import Any

from jarvis_mrb import reality_mesh
from jarvis_mrb.server_config import load_server_config


def _configured(node: str) -> bool:
    return reality_mesh._config(node) is not None


def report(*, probe: bool = False, exercise_screen: str | None = None) -> dict[str, Any]:
    from jarvis_mrb import mesh_windows_apps, mesh_windows_screen

    config = load_server_config()
    result: dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "jarvis_api_bearer_configured": bool(config.api_token),
        "windows_interactive_host": platform.system() == "Windows",
        "windows_screen_startup_opt_in": mesh_windows_screen.enabled(),
        "windows_exact_app_startup_opt_in": mesh_windows_apps.enabled(),
        "macbook_configured": _configured("macbook"),
        "macmini_configured": _configured("macmini"),
        "probe_live_nodes_requested": probe,
        "source_registry": [
            {"id": item["id"], "coverage": item["coverage"], "status": item["status"]}
            for item in reality_mesh.public_sources()["sources"]
        ],
        "screen_captured": False,
        "screenshots_persisted": False,
        "arbitrary_device_execution": False,
    }
    if probe:
        for node in ("macbook", "macmini"):
            state = reality_mesh.probe(node)
            result[node] = {
                "status": state["status"],
                "evidence": state["evidence"],
                "capabilities": state.get("capabilities", {}),
            }
    if exercise_screen is not None:
        if exercise_screen not in {"windows", "macbook", "macmini"}:
            raise ValueError("Check exactly windows, macbook or macmini.")
        receipt: dict[str, Any] = {
            "node_id": exercise_screen,
            "status": "unknown",
            "frame_bytes": 0,
            "media_type": "",
            "remote_revoke_confirmed": False,
        }
        try:
            # 15 seconds is the smallest possible grant. Operator explicitly
            # requests this CLI action; no image is saved or returned to stdout.
            reality_mesh.begin_screen(exercise_screen, seconds=15)
            frame, media = reality_mesh.frame(exercise_screen)
            receipt.update({
                "status": "image_captured_in_ram",
                "frame_bytes": len(frame),
                "media_type": media,
            })
            result["screen_captured"] = True
        except (reality_mesh.NodeUnavailable, ValueError) as exc:
            receipt["status"] = "unavailable"
            receipt["reason"] = type(exc).__name__
        finally:
            try:
                # Even a failed screenshot has no reason to keep the grant.
                reality_mesh.finish_screen(exercise_screen)
                receipt["remote_revoke_confirmed"] = True
            except (reality_mesh.NodeUnavailable, ValueError):
                receipt["remote_revoke_confirmed"] = False
                receipt["safety_note"] = "Remote revocation unconfirmed; 15-second node expiry applies."
        result["screen_exercise"] = receipt
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis private Reality Mesh acceptance")
    parser.add_argument("--probe", action="store_true",
                        help="Query only exact configured Mac node identities/status")
    parser.add_argument("--exercise-screen", choices=("windows", "macbook", "macmini"),
                        help="Capture one explicitly approved private host screen in RAM, then revoke")
    parser.add_argument("--strict", action="store_true",
                        help="Exit nonzero if bearer missing, a configured Mac is not online, "
                             "or requested screen check lacks verified capture/revocation")
    args = parser.parse_args()
    result = report(probe=args.probe, exercise_screen=args.exercise_screen)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict:
        failed = not result["jarvis_api_bearer_configured"]
        if args.probe:
            for node in ("macbook", "macmini"):
                if result[node + "_configured"] and result[node]["status"] != "online":
                    failed = True
        if args.exercise_screen is not None:
            exercise = result["screen_exercise"]
            if (exercise["status"] != "image_captured_in_ram"
                    or not exercise["remote_revoke_confirmed"]):
                failed = True
        if failed:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
