from __future__ import annotations

import json
from pathlib import Path

import jarvis_mrb.agent as agent
import jarvis_mrb.permissions as permissions
from jarvis_mrb.tools import forgecad


def test_forgecad_tool_risks_are_native() -> None:
    assert permissions.TOOL_RISK["forgecad.status"] == "read"
    assert permissions.TOOL_RISK["forgecad.change"] == "local_write"
    assert permissions.TOOL_RISK["forgecad.analyze"] == "local_write"


def test_forgecad_refuses_non_loopback_discovery(tmp_path: Path, monkeypatch) -> None:
    discovery = tmp_path / "jarvis_bridge.json"
    discovery.write_text(json.dumps({
        "base_url": "http://192.168.1.50:8765",
        "header": "X-ForgeCAD-Jarvis-Key",
        "token": "x" * 48,
    }), encoding="utf-8")
    monkeypatch.setattr(forgecad, "DISCOVERY_FILE", discovery)
    try:
        forgecad._connection()
    except ValueError as exc:
        assert "non-loopback" in str(exc)
    else:
        raise AssertionError("ForgeCAD bridge accepted a non-loopback endpoint")


def test_forgecad_status_fast_path(monkeypatch) -> None:
    monkeypatch.setattr(forgecad, "status", lambda: forgecad.ToolResult(True, "ForgeCAD is connected."))
    reply = agent._fast_path("Jarvis, is ForgeCAD connected?")
    assert reply is not None
    assert reply.ok
    assert "connected" in reply.message.lower()


def test_forgecad_mutation_routes_to_change(monkeypatch) -> None:
    calls = []
    def fake_change(request: str, **kwargs):
        calls.append((request, kwargs))
        return forgecad.ToolResult(True, "Branched and changed the design.")
    monkeypatch.setattr(forgecad, "change", fake_change)
    reply = agent._fast_path("In ForgeCAD, make the shoulder bracket 15 percent thicker")
    assert reply is not None
    assert reply.ok
    assert calls
    assert calls[0][1].get("always_branch") is True
