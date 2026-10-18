"""End-user programming: learn, generalise and verify automations (Sisyphus).

future.md ideas implemented here: Routine Learning Without Programming (repeated
context -> action patterns proposed as automations, with conditions/exceptions),
Just-in-Time Automation ("do the rest like that" — infer a transformation from
completed examples and preview the remainder), Demonstrate -> Compile -> Verify
(recorded workflow -> variables/constants -> deterministic program -> replay
verification before activation), Automation Generalization Dialog (ask only the
questions needed to separate constants from variables), Physical/digital macro
replay with an explicit agent-only edge, and Self-Healing replay checkpoints.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, plain, stable_id

# =========================================================================== routine learning


def learn_routines(log: list[dict[str, Any]], *, min_support: int = 3, min_confidence: float = 0.75,
                   context_keys: Iterable[str] = ("place", "weekday", "hour_bucket", "device")) -> list[dict[str, Any]]:
    """Mine (context condition -> action) rules from an event log.

    Each log item: ``{"action": str, "context": {...}}``.  A rule ``ctx[k]==v ->
    action`` is proposed when it is frequent and reliable; contexts where the action
    is usually skipped are reported as exceptions.  Proposals ask, never enable."""
    keys = list(context_keys)
    cond_counts: Counter[tuple[str, Any]] = Counter()
    pair_counts: Counter[tuple[str, Any, str]] = Counter()
    for item in log:
        ctx = item.get("context", {})
        for k in keys:
            if k in ctx:
                cond_counts[(k, ctx[k])] += 1
                if item.get("action"):
                    pair_counts[(k, ctx[k], item["action"])] += 1
    proposals = []
    for (k, v, action), n in pair_counts.items():
        if action == "none":
            continue
        conf = n / cond_counts[(k, v)]
        if n >= min_support and conf >= min_confidence:
            exceptions = sorted({str(i["context"]) for i in log
                                 if i.get("context", {}).get(k) == v and i.get("action") != action})[:3]
            proposals.append({"when": f"{k} == {v!r}", "do": action, "support": n, "confidence": round(conf, 3),
                              "exceptions": exceptions, "status": "ask_user",
                              "question": f"You usually '{action}' when {k} is {v}. Automate it?"})
    return sorted(proposals, key=lambda p: (-p["confidence"], -p["support"]))


# =========================================================================== just-in-time automation


@dataclass
class Transform:
    description: str
    fn: Callable[[str], str]


def _candidate_transforms(examples: list[tuple[str, str]]) -> list[Transform]:
    cands = [
        Transform("uppercase", str.upper), Transform("lowercase", str.lower), Transform("title case", str.title),
        Transform("strip whitespace", str.strip),
        Transform("snake_case", lambda s: re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")),
        Transform("kebab-case", lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")),
    ]
    a, b = examples[0]
    # prefix / suffix addition
    if b.endswith(a) and len(b) > len(a):
        p = b[: len(b) - len(a)]
        cands.append(Transform(f"add prefix {p!r}", lambda s, p=p: p + s))
    if b.startswith(a) and len(b) > len(a):
        suf = b[len(a):]
        cands.append(Transform(f"add suffix {suf!r}", lambda s, suf=suf: s + suf))
    # substring replacement learned from the first example (least general; tried last)
    replacements: list[Transform] = []
    for i in range(len(a)):
        for j in range(i + 1, len(a) + 1):
            old = a[i:j]
            if len(old) < 1 or len(old) == len(a) or a.count(old) != 1:
                continue
            pre, post = a[:i], a[j:]
            if b.startswith(pre) and b.endswith(post) and len(b) >= len(pre) + len(post):
                new = b[len(pre): len(b) - len(post)]
                if new != old:
                    replacements.append(Transform(f"replace {old!r} with {new!r}", lambda s, o=old, n=new: s.replace(o, n)))
    # token reorder: "Last, First" style splits
    for sep in (",", " ", "-", "_", "/", "."):
        parts_a = [p.strip() for p in a.split(sep)]
        if len(parts_a) < 2:
            continue
        for out_sep in (" ", ", ", "-", "_", "/", "."):
            for order in _orders(len(parts_a)):
                if out_sep.join(parts_a[k] for k in order) == b:
                    cands.append(Transform(
                        f"split on {sep!r}, reorder {order}, join with {out_sep!r}",
                        lambda s, sep=sep, out=out_sep, order=order: out.join(
                            [p.strip() for p in s.split(sep)][k] for k in order)))
    # date reformat YYYY-MM-DD <-> MM/DD/YYYY
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", b):
        cands.append(Transform("ISO date -> MM/DD/YYYY", lambda s: f"{s[5:7]}/{s[8:10]}/{s[0:4]}"))
    return cands + sorted(replacements, key=lambda t: -len(t.description))


def _orders(n: int) -> list[tuple[int, ...]]:
    from itertools import permutations

    return list(permutations(range(min(n, 4))))


def infer_transform(examples: list[tuple[str, str]]) -> Transform | None:
    """Find the simplest candidate consistent with *all* completed examples."""
    if not examples:
        return None
    for t in _candidate_transforms(examples):
        try:
            if all(t.fn(a) == b for a, b in examples):
                return t
        except (IndexError, ValueError):
            continue
    return None


def do_the_rest(examples: list[tuple[str, str]], remaining: list[str]) -> dict[str, Any]:
    """'Do the rest like that' with a preview; nothing is applied here."""
    t = infer_transform(examples)
    if t is None:
        return {"status": "no_consistent_rule", "ask": "Show me one or two more examples?"}
    preview = []
    for r in remaining:
        try:
            preview.append({"input": r, "output": t.fn(r)})
        except (IndexError, ValueError):
            preview.append({"input": r, "output": None, "error": "rule does not apply"})
    return {"status": "preview", "rule": t.description, "preview": preview, "apply_requires_confirmation": True}


# =========================================================================== demonstrate -> compile -> verify


@dataclass
class Step:
    action: str  # e.g. open_folder, rename, upload, click
    args: dict[str, Any]
    variable_edge: bool = False  # requires agent judgment (genuinely variable)


@dataclass
class CompiledWorkflow:
    name: str
    steps: list[Step]
    variables: dict[str, str]  # var -> description
    constants: dict[str, Any]
    questions: list[str] = field(default_factory=list)
    verified: bool = False
    version: int = 1

    def program(self) -> list[dict[str, Any]]:
        return [plain(s) for s in self.steps]


def compile_demonstrations(name: str, demos: list[list[Step]], *, context_values: dict[str, Any] | None = None) -> CompiledWorkflow:
    """Literals that differ across demonstrations become variables; identical ones are
    constants.  With a single demo, literals equal to a current-context value (open
    folder, selected file...) become *questions* for the Generalization Dialog."""
    if not demos:
        raise ValueError("need a demonstration")
    lengths = {len(d) for d in demos}
    if len(lengths) != 1:
        raise ValueError("demonstrations differ in structure; record again or mark variable edges")
    ctx = context_values or {}
    steps, variables, constants, questions = [], {}, {}, []
    for i, step_versions in enumerate(zip(*demos)):
        actions = {s.action for s in step_versions}
        if len(actions) != 1:
            steps.append(Step("agent_decides", {"options": sorted(actions)}, variable_edge=True))
            continue
        args = {}
        for key in step_versions[0].args:
            vals = [s.args.get(key) for s in step_versions]
            if len({repr(v) for v in vals}) > 1:
                var = f"step{i}_{key}"
                variables[var] = f"{step_versions[0].action}.{key} (varied: {vals[:3]})"
                args[key] = "{" + var + "}"
            else:
                v = vals[0]
                ctx_key = next((k for k, cv in ctx.items() if cv == v), None)
                if len(demos) == 1 and ctx_key is not None:
                    var = f"step{i}_{key}"
                    questions.append(f"Always {v!r}, or whichever {ctx_key.replace('_', ' ')} is current?")
                    variables[var] = f"pending answer: {ctx_key}"
                    args[key] = "{" + var + "}"
                else:
                    constants[f"step{i}_{key}"] = v
                    args[key] = v
        steps.append(Step(step_versions[0].action, args, any(s.variable_edge for s in step_versions)))
    return CompiledWorkflow(name, steps, variables, constants, questions)


def answer_question(wf: CompiledWorkflow, var: str, *, constant_value: Any | None = None) -> None:
    """Resolve a generalization question: either pin to a constant or keep variable."""
    if constant_value is not None:
        for s in wf.steps:
            for k, v in list(s.args.items()):
                if v == "{" + var + "}":
                    s.args[k] = constant_value
        wf.variables.pop(var, None)
        wf.constants[var] = constant_value
    else:
        wf.variables[var] = wf.variables[var].replace("pending answer: ", "from context: ")


def instantiate(wf: CompiledWorkflow, bindings: dict[str, Any]) -> list[Step]:
    missing = [v for v in wf.variables if v not in bindings]
    if missing:
        raise KeyError(f"unbound variables {missing}")
    out = []
    for s in wf.steps:
        args = {k: (bindings[v[1:-1]] if isinstance(v, str) and v.startswith("{") and v.endswith("}") and v[1:-1] in bindings else v)
                for k, v in s.args.items()}
        out.append(Step(s.action, args, s.variable_edge))
    return out


def verify_replay(wf: CompiledWorkflow, bindings: dict[str, Any], execute: Callable[[Step], dict[str, Any]],
                  expected_state: Callable[[], bool], *, agent: Callable[[Step], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Dry-run/replay for the user to verify before activation; variable edges go to
    the agent (if provided) and everything else is deterministic."""
    receipts = []
    for s in instantiate(wf, bindings):
        if s.variable_edge:
            if agent is None:
                return {"verified": False, "reason": "variable edge needs an agent", "receipts": receipts}
            receipts.append({"step": s.action, "via": "agent", **agent(s)})
        else:
            receipts.append({"step": s.action, "via": "deterministic", **execute(s)})
    wf.verified = bool(expected_state()) and all(r.get("ok", True) for r in receipts)
    return {"verified": wf.verified, "receipts": receipts, "activation": "allowed" if wf.verified else "blocked"}


def replay_with_checkpoints(steps: list[Step], execute: Callable[[Step], dict[str, Any]],
                            check: Callable[[int], bool], recover: Callable[[int, Step], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Known-good action replay with per-step verification and optional AI recovery
    (lumen/terminator pattern): stuck steps escalate instead of looping."""
    log = []
    for i, s in enumerate(steps):
        r = execute(s)
        ok = check(i)
        if not ok and recover is not None:
            r = recover(i, s)
            ok = check(i)
            log.append({"step": i, "recovered": ok})
        if not ok:
            return {"status": "stuck", "at_step": i, "log": log}
        log.append({"step": i, "ok": True, "receipt": r})
    return {"status": "complete", "log": log}


def workflow_id(wf: CompiledWorkflow) -> str:
    return stable_id(wf.name, wf.program(), length=10)


def stamp(wf: CompiledWorkflow, at: datetime) -> dict[str, Any]:
    return {"id": workflow_id(wf), "name": wf.name, "version": wf.version, "verified": wf.verified,
            "at": as_dt(at).isoformat()}
