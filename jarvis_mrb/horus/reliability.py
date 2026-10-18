"""Sisyphus: reliability, self-healing and maintenance primitives.

future.md ideas implemented here (SRE / distributed systems / industrial control):
Jarvis Reliability SLOs, Capability Error Budgets, Automation Ownership Registry,
Automation Maintenance Cost Meter, Runbook Compiler, Human-Fix Memory,
Recurring-Failure Clustering, Known-Good State Snapshots, Change-Correlation Engine,
Canary Actions, Progressive Rollout, Automatic Rollback Contract, Chaos Jarvis /
Failure rehearsal, Automation Dependency Map, Graceful-Degradation Planner,
Offline degradation plans / Offline Capability Manifest, Split-Brain Detector,
Eventual-Reconciliation Ledger, Local Mesh Sync (state exchange), Long-Now Export,
Capability Evidence Ledger, Self-Healing Integrations (schema-drift detection +
sandboxed repair proposal), Condition-Based Maintenance, Degradation Trend Detector,
Operating Envelope Model, Maintenance Verification, Intervention Timeline, Power /
Connectivity Survival Mode load shedding, and Self-hosted backup/failover checks.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, jaccard, mad, median, plain, stable_id, tokens

# =========================================================================== SLOs / error budgets


@dataclass
class SLO:
    capability: str
    objective: float  # e.g. 0.99 good events
    window: timedelta = timedelta(days=28)
    description: str = ""


class SLOTracker:
    def __init__(self, slos: Iterable[SLO]) -> None:
        self.slos = {s.capability: s for s in slos}
        self.events: dict[str, list[tuple[datetime, bool]]] = {}

    def record(self, capability: str, good: bool, at: datetime) -> None:
        self.events.setdefault(capability, []).append((as_dt(at), bool(good)))

    def report(self, capability: str, now: datetime) -> dict[str, Any]:
        slo = self.slos[capability]
        now = as_dt(now)
        window = [g for t, g in self.events.get(capability, []) if now - t <= slo.window]
        total = len(window)
        bad = total - sum(window)
        allowed = (1 - slo.objective) * total
        if total == 0 or bad == 0:
            remaining = 1.0
        elif allowed == 0:
            remaining = -1.0
        else:
            remaining = (allowed - bad) / allowed
        return {
            "capability": capability,
            "sli": (sum(window) / total) if total else None,
            "objective": slo.objective,
            "events": total,
            "bad": bad,
            "error_budget_remaining": remaining,
            "exhausted": total > 0 and remaining <= 0,
        }

    def engineering_focus(self, now: datetime) -> dict[str, Any]:
        """Repeated budget exhaustion shifts attention from features to reliability."""
        exhausted = [c for c in self.slos if self.report(c, now)["exhausted"]]
        return {"focus": "reliability" if exhausted else "features", "exhausted": exhausted}


# =========================================================================== automation registry


@dataclass
class AutomationRecord:
    id: str
    purpose: str
    owner: str
    trigger: str
    dependencies: list[str]
    permissions: list[str]
    side_effects: list[str]
    rollback: str
    retirement_condition: str
    last_tested: datetime | None = None
    minutes_saved_per_run: float = 0.0
    runs_per_month: float = 0.0
    maintenance_minutes_per_month: float = 0.0
    failures_per_month: float = 0.0


REQUIRED_FIELDS = ("purpose", "owner", "trigger", "rollback", "retirement_condition")


class AutomationRegistry:
    """Every automation declares purpose/owner/deps/permissions/side effects/rollback/
    last test/retirement so the system never accumulates mysterious jobs."""

    def __init__(self) -> None:
        self.records: dict[str, AutomationRecord] = {}

    def register(self, rec: AutomationRecord) -> None:
        missing = [f for f in REQUIRED_FIELDS if not str(getattr(rec, f)).strip()]
        if missing:
            raise ValueError(f"automation {rec.id} missing {missing}")
        self.records[rec.id] = rec

    def audit(self, now: datetime, max_untested: timedelta = timedelta(days=90)) -> list[dict[str, Any]]:
        out = []
        for r in self.records.values():
            issues = []
            if r.last_tested is None or as_dt(now) - as_dt(r.last_tested) > max_untested:
                issues.append("untested")
            if self.net_value(r.id) < 0:
                issues.append("net-negative")
            if issues:
                out.append({"automation": r.id, "issues": issues, "net_minutes_per_month": self.net_value(r.id)})
        return out

    def net_value(self, automation_id: str) -> float:
        """Automation Maintenance Cost Meter (minutes/month; failures cost 15 min each)."""
        r = self.records[automation_id]
        saved = r.minutes_saved_per_run * r.runs_per_month
        cost = r.maintenance_minutes_per_month + 15.0 * r.failures_per_month
        return saved - cost


# =========================================================================== dependency map / chaos / degradation


class DependencyMap:
    """Capability -> dependencies.  A capability works if any one of each
    alternative group is up (``requires`` is AND of OR-groups)."""

    def __init__(self) -> None:
        self.requires: dict[str, list[list[str]]] = {}
        self.importance: dict[str, float] = {}

    def add(self, capability: str, *groups: Iterable[str], importance: float = 1.0) -> None:
        self.requires[capability] = [list(g) for g in groups]
        self.importance[capability] = importance

    def works(self, capability: str, down: set[str], _seen: frozenset[str] = frozenset()) -> bool:
        if capability in down:
            return False
        if capability not in self.requires or capability in _seen:
            return capability not in down
        seen = _seen | {capability}
        return all(any(self.works(d, down, seen) for d in group) for group in self.requires[capability])

    def capabilities(self) -> list[str]:
        return sorted(self.requires)

    def blast_radius(self, component: str) -> list[str]:
        return [c for c in self.capabilities() if c != component and not self.works(c, {component})]

    def single_points_of_failure(self) -> dict[str, list[str]]:
        """Chaos Jarvis / failure rehearsal: remove each leaf in simulation."""
        leaves = sorted({d for groups in self.requires.values() for g in groups for d in g} - set(self.requires))
        return {leaf: radius for leaf in leaves if (radius := self.blast_radius(leaf))}

    def manifest(self, down: Iterable[str]) -> dict[str, list[str]]:
        """Offline Capability Manifest: what still works right now."""
        d = set(down)
        works = [c for c in self.capabilities() if self.works(c, d)]
        return {"available": works, "unavailable": [c for c in self.capabilities() if c not in works]}

    def degradation_plan(self, capability: str) -> list[dict[str, Any]]:
        """Graceful-Degradation Planner: substitutes for each dependency."""
        plan = []
        for group in self.requires.get(capability, []):
            plan.append({"primary": group[0], "fallbacks": group[1:],
                         "single_point": len(group) == 1})
        return plan


def survival_mode(workloads: list[dict[str, Any]], *, battery_fraction: float, grid_power: bool,
                  internet: bool) -> dict[str, Any]:
    """Power/Connectivity Survival Mode: shed nonessential work as infrastructure degrades.
    Workload: ``{"name", "class": critical|important|optional, "needs_internet": bool, "watts": float}``."""
    keep_classes = {"critical", "important", "optional"}
    if not grid_power:
        keep_classes = {"critical", "important"} if battery_fraction > 0.5 else {"critical"}
    kept, shed = [], []
    for w in workloads:
        if w["class"] not in keep_classes or (w.get("needs_internet") and not internet):
            shed.append(w["name"])
        else:
            kept.append(w["name"])
    return {"keep": kept, "shed": shed,
            "mode": "normal" if grid_power and internet else "survival",
            "estimated_watts": sum(w.get("watts", 0) for w in workloads if w["name"] in kept)}


# =========================================================================== failures / changes / snapshots


def cluster_failures(incidents: list[dict[str, Any]], threshold: float = 0.4) -> list[list[str]]:
    """Recurring-Failure Clustering by message/component similarity."""
    clusters: list[tuple[set[str], list[str]]] = []
    for inc in incidents:
        sig = set(tokens(inc.get("message", ""))) | {f"component:{inc.get('component', '')}"}
        for csig, members in clusters:
            if jaccard(sig, csig) >= threshold:
                members.append(inc["id"])
                csig |= sig
                break
        else:
            clusters.append((sig, [inc["id"]]))
    return [m for _, m in clusters]


def correlate_changes(failure_at: datetime, changes: list[dict[str, Any]], *, lookback: timedelta = timedelta(hours=24),
                      affected: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Change-Correlation Engine: rank recent changes plausibly preceding a failure."""
    f = as_dt(failure_at)
    aff = set(affected)
    out = []
    for c in changes:
        t = as_dt(c["at"])
        if not (f - lookback <= t <= f):
            continue
        recency = 1.0 - (f - t) / lookback
        overlap = 1.0 if aff & set(c.get("touches", [])) else 0.0
        out.append({**plain(c), "score": round(0.6 * overlap + 0.4 * recency, 4)})
    return sorted(out, key=lambda x: -x["score"])


def snapshot_diff(known_good: dict[str, Any], current: dict[str, Any], _prefix: str = "") -> list[dict[str, Any]]:
    """Known-Good State Snapshots: structural diff of config/state."""
    out = []
    for k in sorted(set(known_good) | set(current)):
        path = f"{_prefix}{k}"
        a, b = known_good.get(k, "<absent>"), current.get(k, "<absent>")
        if isinstance(a, dict) and isinstance(b, dict):
            out.extend(snapshot_diff(a, b, path + "."))
        elif a != b:
            out.append({"path": path, "known_good": a, "current": b})
    return out


class HumanFixMemory:
    """Correlate anomaly signatures with what the human did to resolve them."""

    def __init__(self) -> None:
        self.cases: list[dict[str, Any]] = []

    def record(self, signature: dict[str, Any], fix: str, worked: bool, at: datetime) -> None:
        self.cases.append({"signature": signature, "fix": fix, "worked": worked, "at": as_dt(at).isoformat()})

    def suggest(self, signature: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for c in self.cases:
            if not c["worked"]:
                continue
            keys = set(signature) | set(c["signature"])
            same = [k for k in keys if signature.get(k) == c["signature"].get(k)]
            diff = [k for k in keys if signature.get(k) != c["signature"].get(k)]
            sim = len(same) / len(keys) if keys else 0
            if sim >= 0.5:
                out.append({"fix": c["fix"], "similarity": round(sim, 3), "differences": sorted(diff), "from": c["at"]})
        return sorted(out, key=lambda x: -x["similarity"])


def compile_runbook(incident: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Runbook Compiler: deterministic steps plus explicit judgment points."""
    compiled = []
    for i, s in enumerate(steps, 1):
        compiled.append({
            "step": i,
            "action": s["action"],
            "kind": "judgment" if s.get("judgment") else "deterministic",
            "verify": s.get("verify", "confirm the symptom changed as expected"),
            "rollback": s.get("rollback"),
        })
    return {"id": stable_id(incident, steps, length=10), "incident": incident, "steps": compiled,
            "judgment_points": [c["step"] for c in compiled if c["kind"] == "judgment"]}


# =========================================================================== canary / rollout / rollback


def progressive_rollout(targets: list[str], apply: Callable[[str], dict[str, Any]],
                        verify: Callable[[str], bool], rollback: Callable[[str], None], *,
                        stages: tuple[float, ...] = (0.0, 0.25, 0.5, 1.0)) -> dict[str, Any]:
    """Canary first (one target), then expand by stage; halt and roll back all applied
    targets on any failed verification (Automatic Rollback Contract)."""
    applied: list[str] = []
    stage_sizes = []
    for frac in stages:
        size = max(1, math.ceil(frac * len(targets))) if frac > 0 else 1
        stage_sizes.append(min(size, len(targets)))
    for size in stage_sizes:
        for t in targets[len(applied):size]:
            receipt = apply(t)
            applied.append(t)
            if not receipt.get("ok", True) or not verify(t):
                for done in reversed(applied):
                    rollback(done)
                return {"status": "halted_and_rolled_back", "failed_on": t, "rolled_back": list(reversed(applied))}
    return {"status": "complete", "applied": applied}


@dataclass
class RollbackContract:
    action: str
    success_condition: Callable[[dict[str, Any]], bool]
    rollback: Callable[[], None]
    reversible: bool = True

    def execute(self, do: Callable[[], dict[str, Any]], observe: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        receipt = do()
        state = observe()
        if self.success_condition(state):
            return {"action": self.action, "status": "succeeded", "receipt": receipt}
        if self.reversible:
            self.rollback()
            return {"action": self.action, "status": "rolled_back", "observed": state}
        return {"action": self.action, "status": "failed_irreversible:escalate", "observed": state}


# =========================================================================== split brain / reconciliation


def detect_split_brain(nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Nodes report ``{"authority": {...}, "state": {...}}``; flag incompatible beliefs."""
    issues = []
    leaders = {n: v.get("authority", {}).get("leader") for n, v in nodes.items()}
    distinct = {l for l in leaders.values() if l}
    if len(distinct) > 1:
        issues.append({"kind": "authority_conflict", "leaders": leaders})
    keys = set().union(*(v.get("state", {}).keys() for v in nodes.values())) if nodes else set()
    for k in sorted(keys):
        vals = {n: v.get("state", {}).get(k) for n, v in nodes.items() if k in v.get("state", {})}
        if len({json.dumps(x, sort_keys=True, default=str) for x in vals.values()}) > 1:
            issues.append({"kind": "state_divergence", "key": k, "values": vals})
    return issues


@dataclass
class LedgerEntry:
    node: str
    key: str
    value: Any
    at: datetime
    lamport: int
    kind: str = "observation"  # observation | action


class ReconciliationLedger:
    """Eventual-Reconciliation Ledger / Local Mesh Sync: append-only per node, merged
    with explicit conflicts instead of 'cloud copy wins'."""

    def __init__(self, node: str) -> None:
        self.node = node
        self.clock = 0
        self.entries: list[LedgerEntry] = []

    def record(self, key: str, value: Any, at: datetime, kind: str = "observation") -> LedgerEntry:
        self.clock += 1
        e = LedgerEntry(self.node, key, value, as_dt(at), self.clock, kind)
        self.entries.append(e)
        return e

    def export(self, since_lamport: int = 0) -> list[dict[str, Any]]:
        return [plain(e) for e in self.entries if e.lamport > since_lamport]

    def merge(self, remote: list[dict[str, Any]], *, base: dict[str, Any] | None = None) -> dict[str, Any]:
        incoming = [LedgerEntry(r["node"], r["key"], r["value"], as_dt(r["at"]), r["lamport"], r.get("kind", "observation"))
                    for r in remote]
        known = {(e.node, e.lamport) for e in self.entries}
        new = [e for e in incoming if (e.node, e.lamport) not in known]
        self.entries.extend(new)
        self.clock = max([self.clock] + [e.lamport for e in new])
        merged: dict[str, Any] = dict(base or {})
        conflicts = []
        by_key: dict[str, list[LedgerEntry]] = {}
        for e in self.entries:
            by_key.setdefault(e.key, []).append(e)
        for key, es in by_key.items():
            latest_per_node: dict[str, LedgerEntry] = {}
            for e in sorted(es, key=lambda e: (e.at, e.lamport)):
                latest_per_node[e.node] = e
            values = {json.dumps(e.value, sort_keys=True, default=str) for e in latest_per_node.values()}
            winner = max(latest_per_node.values(), key=lambda e: (e.at, e.lamport, e.node))
            merged[key] = winner.value
            if len(values) > 1:
                conflicts.append({"key": key, "positions": {n: e.value for n, e in latest_per_node.items()},
                                  "resolved_to": winner.value, "rule": "latest observation time",
                                  "needs_review": any(e.kind == "action" for e in latest_per_node.values())})
        return {"state": merged, "conflicts": conflicts, "new_entries": len(new)}


# =========================================================================== capability evidence ledger


@dataclass
class CapabilityEvidence:
    capability: str
    commit: str | None = None
    environment: str | None = None
    last_passing_test: datetime | None = None
    trace_ref: str | None = None
    observed_deployed: bool = False


def capability_claim(ev: CapabilityEvidence, now: datetime, max_age: timedelta = timedelta(days=14)) -> str:
    """A capability with no current passing evidence is never simply 'working'."""
    if ev.commit is None:
        return "designed"
    if ev.last_passing_test is None:
        return "implemented-unverified"
    if as_dt(now) - as_dt(ev.last_passing_test) > max_age:
        return "verified-stale"
    if ev.observed_deployed and ev.environment:
        return "observed-deployed"
    return "verified-in-ci"


# =========================================================================== self-healing integrations


def schema_signature(payload: Any, _prefix: str = "") -> dict[str, str]:
    if isinstance(payload, dict):
        out: dict[str, str] = {}
        for k, v in payload.items():
            out.update(schema_signature(v, f"{_prefix}{k}."))
        return out
    if isinstance(payload, list):
        return schema_signature(payload[0], _prefix + "[].") if payload else {_prefix.rstrip("."): "list"}
    return {_prefix.rstrip("."): type(payload).__name__}


def detect_schema_drift(expected: dict[str, str], payload: Any) -> dict[str, Any]:
    actual = schema_signature(payload)
    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    retyped = sorted(k for k in set(expected) & set(actual) if expected[k] != actual[k])
    renames = []
    for m in missing:
        leaf = m.rsplit(".", 1)[-1]
        for a in added:
            if expected[m] == actual[a] and (leaf in a or a.rsplit(".", 1)[-1] in m or
                                             jaccard(tokens(leaf.replace("_", " ")), tokens(a.rsplit(".", 1)[-1].replace("_", " "))) > 0.3):
                renames.append({"from": m, "to": a})
    return {"drift": bool(missing or added or retyped), "missing": missing, "added": added,
            "retyped": retyped, "candidate_renames": renames}


def propose_repair(drift: dict[str, Any], sample_payloads: list[Any], extractor: Callable[[Any, dict[str, str]], Any],
                   validate: Callable[[Any], bool]) -> dict[str, Any]:
    """Test a field-mapping repair in a dry run over samples; propose, never auto-apply."""
    mapping = {r["from"]: r["to"] for r in drift.get("candidate_renames", [])}
    if not mapping:
        return {"status": "no-candidate-repair", "escalate": True}
    results = []
    for p in sample_payloads:
        try:
            results.append(bool(validate(extractor(p, mapping))))
        except Exception:  # noqa: BLE001 - dry-run must contain failures
            results.append(False)
    ok = bool(results) and all(results)
    return {"status": "proposed" if ok else "repair-failed-dry-run", "mapping": mapping,
            "dry_run_passed": sum(results), "dry_run_total": len(results), "requires_approval": True,
            "rollback": "restore previous mapping"}


# =========================================================================== condition-based maintenance


@dataclass
class TelemetryLimit:
    metric: str
    warn: float
    critical: float
    higher_is_worse: bool = True


def condition_check(readings: dict[str, float], limits: Iterable[TelemetryLimit]) -> list[dict[str, Any]]:
    """Deterministic thresholds for Jarvis hardware (temps, SMART, battery, errors)."""
    out = []
    for lim in limits:
        v = readings.get(lim.metric)
        if v is None:
            out.append({"metric": lim.metric, "level": "unknown"})
            continue
        worse = (lambda a, b: a >= b) if lim.higher_is_worse else (lambda a, b: a <= b)
        level = "critical" if worse(v, lim.critical) else "warn" if worse(v, lim.warn) else "ok"
        if level != "ok":
            out.append({"metric": lim.metric, "value": v, "level": level})
    return out


def degradation_trend(series: list[tuple[datetime, float]], *, baseline_points: int = 10, z: float = 3.0,
                      min_slope_per_day: float | None = None) -> dict[str, Any]:
    """Slow drift from an entity's own baseline even before a fixed alarm threshold."""
    if len(series) < baseline_points + 3:
        return {"status": "insufficient-history"}
    pts = sorted(series)
    base = [v for _, v in pts[:baseline_points]]
    m, spread = median(base), mad(base) or 1e-9
    recent = [v for _, v in pts[-3:]]
    robust_z = (median(recent) - m) / (1.4826 * spread)
    t0 = pts[0][0]
    xs = [(as_dt(t) - as_dt(t0)).total_seconds() / 86400 for t, _ in pts]
    ys = [v for _, v in pts]
    xm, ym = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - xm) ** 2 for x in xs) or 1e-9
    slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / denom
    drifting = abs(robust_z) >= z or (min_slope_per_day is not None and abs(slope) >= min_slope_per_day)
    return {"status": "drifting" if drifting else "stable", "robust_z": round(robust_z, 3),
            "slope_per_day": round(slope, 5), "baseline_median": m}


class OperatingEnvelope:
    """Learn normal *combinations* of state (per-bin ranges) rather than scalar limits."""

    def __init__(self, condition_key: str, value_key: str, margin: float = 0.1) -> None:
        self.ck, self.vk, self.margin = condition_key, value_key, margin
        self.ranges: dict[Any, tuple[float, float]] = {}

    def fit(self, samples: Iterable[dict[str, Any]]) -> None:
        for s in samples:
            c, v = s[self.ck], float(s[self.vk])
            lo, hi = self.ranges.get(c, (v, v))
            self.ranges[c] = (min(lo, v), max(hi, v))

    def check(self, sample: dict[str, Any]) -> dict[str, Any]:
        c, v = sample[self.ck], float(sample[self.vk])
        if c not in self.ranges:
            return {"status": "unseen-combination", "condition": c}
        lo, hi = self.ranges[c]
        pad = (hi - lo) * self.margin or abs(hi) * self.margin
        if lo - pad <= v <= hi + pad:
            return {"status": "normal"}
        return {"status": "outside-envelope", "condition": c, "value": v, "expected": [lo, hi]}


def verify_maintenance(symptom: Callable[[dict[str, Any]], bool], before: dict[str, Any], after: dict[str, Any],
                       known_good: dict[str, Any]) -> dict[str, Any]:
    """Maintenance Verification: symptom gone AND no new deviation from known-good."""
    new_issues = [d for d in snapshot_diff(known_good, after) if d not in snapshot_diff(known_good, before)]
    resolved = symptom(before) and not symptom(after)
    return {"symptom_resolved": resolved, "new_abnormal_state": new_issues,
            "verified": resolved and not new_issues}


def intervention_timeline(entity: str, *streams: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Intervention Timeline: telemetry, alerts, human & Jarvis actions, maintenance,
    config changes and outcomes for one entity on a single ordered timeline."""
    merged = [dict(e) for s in streams for e in s if e.get("entity") == entity]
    return sorted(merged, key=lambda e: as_dt(e["at"]))


def backup_status(copies: list[dict[str, Any]], now: datetime, *, min_copies: int = 2,
                  max_age: timedelta = timedelta(days=1)) -> dict[str, Any]:
    """Self-hosted backup/failover: 'important files exist in two places' as a check."""
    fresh = [c for c in copies if as_dt(now) - as_dt(c["verified_at"]) <= max_age and c.get("checksum_ok", True)]
    locations = {c["location"] for c in fresh}
    return {"healthy": len(locations) >= min_copies, "fresh_locations": sorted(locations),
            "stale_or_bad": [c["location"] for c in copies if c not in fresh]}

