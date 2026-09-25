from __future__ import annotations

"""Read-only manifest of *actual, named* capabilities, not model-invented tools.

Contract definition and permission are NOT proof of current connectivity or
proof that an external action succeeded. A proposed intervention cannot invoke
tools through this module. Phone-local authority is intentionally absent here.
"""

from datetime import datetime, timezone
from typing import Any

# Scope is deliberately literal and bounded: no arbitrary tool names or custom
# code execution, no implicit ability to command any HomeKit accessory.
_MANIFEST: tuple[tuple[str, str, str], ...] = (
    ("calendar.query", "Read actual Calendar events", "read_only"),
    ("gmail.query", "Read authorized Gmail messages", "read_only"),
    ("pc.list_running_apps", "Observe running Windows apps", "read_only"),
    ("browser.list_tabs", "Observe open browser tabs", "read_only"),
    ("system.resources", "Observe Windows resources", "read_only"),
    ("web.search", "Find public evidence with source checks", "read_only"),
    ("agency.status", "Observe protected Agency goal state", "read_only"),
    ("pc.launch_app", "Launch one named Windows application", "local_write"),
    ("browser.open_site", "Open an explicit public website", "local_write"),
    ("calendar.create", "Create a Calendar event", "external_write"),
    ("gmail.send", "Send a message to exact recipients", "external_write"),
)


def catalog() -> dict[str, Any]:
    from jarvis_mrb.permissions import TOOL_RISK, decide
    from jarvis_mrb.workflow_engine import _ALLOWED_NODE_TOOLS

    capabilities: list[dict[str, Any]] = []
    for tool, description, effect in _MANIFEST:
        known = tool in TOOL_RISK
        permission = decide(tool)
        capabilities.append({
            "id": tool,
            "label": description,
            "effect": effect,
            "contract_defined": bool(known),
            "permission_allowed": bool(known and permission.allowed),
            "requires_confirmation": bool(permission.needs_confirmation),
            "agency_scope_implemented": bool(tool in _ALLOWED_NODE_TOOLS),
            "live_connection_verified": False,
            "execution_authorized_by_catalog": False,
            "actual_external_outcome_verified": False,
            "source": "Jarvis built-in tool registry and current permissions",
        })
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "catalog_is_read_only": True,
        "model_may_add_tools": False,
        "phone_local_permissions_included": False,
        "capabilities": capabilities,
    }
