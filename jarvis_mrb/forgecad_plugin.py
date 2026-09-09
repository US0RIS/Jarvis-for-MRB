from __future__ import annotations

import re
from typing import Any

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    import jarvis_mrb.agent as agent
    import jarvis_mrb.permissions as permissions
    from jarvis_mrb.tools import forgecad

    permissions.TOOL_RISK.update({
        "forgecad.status": "read",
        "forgecad.summary": "read",
        "forgecad.designs": "read",
        "forgecad.history": "read",
        "forgecad.diff": "read",
        "forgecad.component_select": "read",
        "forgecad.reality_scan": "read",
        "forgecad.analyze": "local_write",
        "forgecad.change": "local_write",
        "forgecad.campaign": "local_write",
    })

    original_execute = agent._execute_unchecked
    original_describe = agent._describe_action
    original_fast = agent._fast_path

    def execute(tool: str, args: dict[str, Any]) -> agent.AgentReply:
        if tool == "forgecad.status": return agent._result(forgecad.status())
        if tool == "forgecad.summary": return agent._result(forgecad.summary())
        if tool == "forgecad.designs": return agent._result(forgecad.designs())
        if tool == "forgecad.history": return agent._result(forgecad.history(int(args.get("limit") or 20)))
        if tool == "forgecad.diff": return agent._result(forgecad.diff(str(args.get("design") or "")))
        if tool == "forgecad.change": return agent._result(forgecad.change(str(args.get("request") or ""), execute=bool(args.get("execute", True)), always_branch=True))
        if tool == "forgecad.reality_scan": return agent._result(forgecad.analyze("reality_scan"))
        if tool == "forgecad.analyze":
            return agent._result(forgecad.analyze(
                str(args.get("kind") or "reality_scan"),
                object_id=str(args.get("object_id") or "") or None,
                object_name=str(args.get("object") or args.get("part") or "") or None,
                params=dict(args.get("params") or {}),
            ))
        if tool == "forgecad.component_select":
            return agent._result(forgecad.select_component(
                str(args.get("category") or ""),
                dict(args.get("constraints") or {}),
                query=str(args.get("query") or ""),
                weights=dict(args.get("weights") or {}),
            ))
        if tool == "forgecad.campaign":
            goal = str(args.get("goal") or args.get("request") or "").strip()
            if not goal:
                return agent.AgentReply(False, "ForgeCAD campaign requires an engineering goal.")
            try:
                data = forgecad._request(
                    "POST", "/api/jarvis/campaign",
                    body={"goal": goal, "model": args.get("model"), "variants": max(2, min(int(args.get("variants") or 6), 12)), "execute": bool(args.get("execute", True))},
                    timeout=900.0,
                )
            except ValueError as exc:
                return agent.AgentReply(False, str(exc))
            if not data.get("executed", True):
                plan = data.get("plan") or {}
                return agent.AgentReply(True, f"ForgeCAD planned {len(plan.get('variants') or [])} design variants without executing them.")
            ranking = data.get("ranking") or []
            best = data.get("best_branch") or (ranking[0].get("branch") if ranking else None)
            failures = sum(1 for row in ranking if (row.get("requirements") or {}).get("failed", 0))
            return agent.AgentReply(True, f"ForgeCAD completed an autonomous engineering campaign across {len(data.get('outcomes') or ranking)} branch variants. Best candidate: {best or 'none'}. {failures} ranked candidate(s) still fail one or more explicit requirements. The starting design was restored and all experiments remain in project history.")
        return original_execute(tool, args)

    def describe(tool: str, args: dict[str, Any]) -> str:
        if tool == "forgecad.change":
            request = " ".join(str(args.get("request") or "").split())[:300]
            return f"branch the current ForgeCAD design and apply this engineering change: {request!r}"
        if tool == "forgecad.campaign":
            goal = " ".join(str(args.get("goal") or args.get("request") or "").split())[:300]
            return f"launch a multi-branch ForgeCAD engineering campaign for this goal: {goal!r}"
        if tool == "forgecad.analyze":
            return f"run ForgeCAD {args.get('kind') or 'engineering'} analysis on {args.get('object') or args.get('object_id') or 'the requested part'}"
        return original_describe(tool, args)

    def fast_path(text: str) -> agent.AgentReply | None:
        n = " ".join(text.strip().lower().split())
        scoped = any(x in n for x in ("forgecad", "forge cad", "cad model", "cad design", "the design", "our design", "design branch", "design history"))
        if scoped:
            if any(x in n for x in ("is forgecad running", "forgecad status", "cad status", "is forgecad connected")):
                return agent.execute_tool("forgecad.status", {})
            if any(x in n for x in ("list designs", "show designs", "design branches", "list branches", "what designs")):
                return agent.execute_tool("forgecad.designs", {})
            if any(x in n for x in ("design history", "project history", "forgecad history", "cad history")):
                return agent.execute_tool("forgecad.history", {"limit": 20})
            if any(x in n for x in ("reality scan", "risk scan", "failure scan", "check for overheating", "check overheating", "check vibration risk")):
                return agent.execute_tool("forgecad.reality_scan", {})

            m = re.search(r"(?:compare|diff|differences? (?:for|in))\s+(?:the\s+)?(?:design\s+|branch\s+)?([a-z0-9._-]+)", n)
            if m:
                return agent.execute_tool("forgecad.diff", {"design": m.group(1)})

            campaign_cues = (
                " figure out how to ", " solve the ", " solve this ", " eliminate ", " optimize ", " optimise ",
                " find the best ", " try different ", " explore designs ", " explore variants ", " fix the vibration ",
                " fix this vibration ", " stop the overheating ", " reduce overheating ", " redesign it to ",
            )
            padded = f" {n} "
            if any(cue in padded for cue in campaign_cues):
                return agent.execute_tool("forgecad.campaign", {"goal": text, "variants": 6, "execute": True})

            mutation = (
                " change ", " adjust ", " modify ", " update ", " replace ", " add ", " remove ", " delete ",
                " make ", " thicken ", " thin ", " move ", " resize ", " enlarge ", " shrink ", " swap ",
                " edit ", " rewrite ", " refactor ", " branch ", " use a different ", " choose a different ",
            )
            if any(cue in padded for cue in mutation):
                return agent.execute_tool("forgecad.change", {"request": text, "execute": True})

            if any(x in n for x in ("current design", "design status", "design mass", "cad model", "tell me about the design", "what is in the design")):
                return agent.execute_tool("forgecad.summary", {})

        return original_fast(text)

    agent._execute_unchecked = execute
    agent._describe_action = describe
    agent._fast_path = fast_path
    _INSTALLED = True
