"""Spatial computing primitives: anchors, zones, semantic rooms, pointing loops.

future.md ideas implemented here: Persistent World Layer, Cross-Device Spatial
Anchor Abstraction, Anchor Confidence + Drift, Walk-Into Interfaces, Live Physical
Labels, Semantic Room Map, Place-Bound Live Data, Shared Spatial Context (consented
participants), Spatial Procedure Overlay (advance only on evidence), Visual Change
Memory, Navigation Landmark Memory, Indoor / place-of-context awareness ("what room
am I in"), Universal Object Interface (object bindings), Physical Macros (learned
procedure model), geofence predicates (tile38-style enter/exit), and the
Predict -> Point -> Verify -> Calibrate loop.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from jarvis_mrb.horus._util import as_dt, clamp, haversine_m, jaccard, stable_id

# =========================================================================== anchors


@dataclass
class AnchorObservation:
    device: str
    vendor_anchor_id: str
    position: tuple[float, float, float]  # metres in a shared frame
    quality: float  # 0..1 localisation quality reported/estimated
    at: datetime


@dataclass
class Anchor:
    """Jarvis-owned anchor ID hiding vendor anchor systems."""

    id: str
    label: str
    kind: str  # object | control | note | warning | location | procedure
    observations: list[AnchorObservation] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    shared_with: set[str] = field(default_factory=set)

    def estimate(self) -> dict[str, Any]:
        """Quality-weighted position, spread (drift) and confidence."""
        if not self.observations:
            return {"position": None, "confidence": 0.0, "drift_m": None}
        w = [max(o.quality, 1e-3) for o in self.observations]
        tot = sum(w)
        pos = tuple(sum(o.position[i] * wi for o, wi in zip(self.observations, w)) / tot for i in range(3))
        spread = max(math.dist(pos, o.position) for o in self.observations)
        conf = clamp((tot / len(w)) * (1.0 / (1.0 + spread)))
        return {"position": pos, "confidence": round(conf, 3), "drift_m": round(spread, 3),
                "needs_reanchor": spread > 0.25}

    def vendor_ids(self) -> dict[str, str]:
        return {o.device: o.vendor_anchor_id for o in self.observations}


class WorldLayer:
    """Persistent semantic anchors surviving sessions and devices."""

    def __init__(self) -> None:
        self.anchors: dict[str, Anchor] = {}

    def create(self, label: str, kind: str, obs: AnchorObservation, payload: dict[str, Any] | None = None) -> Anchor:
        a = Anchor(stable_id(label, obs.device, obs.vendor_anchor_id, length=10), label, kind, [obs], dict(payload or {}))
        self.anchors[a.id] = a
        return a

    def relocalize(self, anchor_id: str, obs: AnchorObservation) -> dict[str, Any]:
        self.anchors[anchor_id].observations.append(obs)
        return self.anchors[anchor_id].estimate()

    def by_vendor(self, device: str, vendor_id: str) -> Anchor | None:
        return next((a for a in self.anchors.values() if a.vendor_ids().get(device) == vendor_id), None)

    def share(self, anchor_id: str, participant: str, *, consented: bool) -> bool:
        """Shared Spatial Context only with explicit participant consent."""
        if not consented:
            return False
        self.anchors[anchor_id].shared_with.add(participant)
        return True

    def visible_to(self, participant: str) -> list[str]:
        return [a.id for a in self.anchors.values() if participant in a.shared_with]

    def label(self, anchor_id: str, live: dict[str, Any]) -> str:
        """Live Physical Label text: static payload + current dynamic data."""
        a = self.anchors[anchor_id]
        parts = [a.label] + [f"{k}: {v}" for k, v in {**a.payload, **live}.items()]
        return " · ".join(parts)


# =========================================================================== zones / rooms


@dataclass
class Zone:
    id: str
    name: str
    purpose: str
    polygon: list[tuple[float, float]] | None = None  # local metres (x, y)
    center_latlon: tuple[float, float] | None = None
    radius_m: float | None = None
    interface: str = ""  # walk-into interface to instantiate
    normal_objects: set[str] = field(default_factory=set)
    controls: dict[str, str] = field(default_factory=dict)  # control -> what it affects
    routines: list[str] = field(default_factory=list)
    live_data: list[str] = field(default_factory=list)  # place-bound feeds


def point_in_polygon(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


class SemanticMap:
    """Semantic Room Map + indoor place awareness + walk-into interfaces +
    geofence enter/exit predicates."""

    def __init__(self, zones: Iterable[Zone] = ()) -> None:
        self.zones = {z.id: z for z in zones}
        self.inside: dict[str, set[str]] = {}

    def locate(self, *, local_xy: tuple[float, float] | None = None, latlon: tuple[float, float] | None = None,
               beacons: dict[str, float] | None = None, beacon_zones: dict[str, str] | None = None) -> dict[str, Any]:
        """'What room am I in?' using whichever evidence is available, with the basis."""
        if local_xy is not None:
            for z in self.zones.values():
                if z.polygon and point_in_polygon(local_xy, z.polygon):
                    return {"zone": z.id, "name": z.name, "purpose": z.purpose, "basis": "local position"}
        if beacons and beacon_zones:
            best = max(beacons, key=beacons.get)
            if beacons[best] > -75 and best in beacon_zones:
                z = self.zones[beacon_zones[best]]
                return {"zone": z.id, "name": z.name, "purpose": z.purpose, "basis": f"BLE beacon {best}"}
        if latlon is not None:
            for z in self.zones.values():
                if z.center_latlon and z.radius_m and haversine_m(*latlon, *z.center_latlon) <= z.radius_m:
                    return {"zone": z.id, "name": z.name, "purpose": z.purpose, "basis": "GPS geofence"}
        return {"zone": None, "basis": "no evidence", "answer": "I don't know which room you're in."}

    def update(self, entity: str, zone_id: str | None) -> list[dict[str, Any]]:
        """Enter/exit events (tile38-style geofence predicates) with walk-into UI."""
        before = self.inside.get(entity, set())
        after = {zone_id} if zone_id else set()
        events = []
        for z in sorted(after - before):
            zone = self.zones[z]
            events.append({"entity": entity, "event": "enter", "zone": z,
                           "instantiate_interface": zone.interface or None, "live_data": zone.live_data})
        for z in sorted(before - after):
            events.append({"entity": entity, "event": "exit", "zone": z,
                           "teardown_interface": self.zones[z].interface or None})
        self.inside[entity] = after
        return events

    def misplaced(self, zone_id: str, observed_objects: Iterable[str]) -> dict[str, list[str]]:
        z = self.zones[zone_id]
        seen = set(observed_objects)
        return {"missing": sorted(z.normal_objects - seen), "unexpected": sorted(seen - z.normal_objects)}

    def what_controls(self, target: str) -> list[tuple[str, str]]:
        return [(z.id, c) for z in self.zones.values() for c, t in z.controls.items() if t == target]


# =========================================================================== procedures / change memory


class ProcedureOverlay:
    """Spatial Procedure Overlay: steps attach to a component and advance only when
    sensor/visual evidence satisfies the step's completion check."""

    def __init__(self, steps: list[dict[str, Any]]) -> None:
        self.steps = steps  # {"text", "anchor", "done_when": Callable[[dict], bool]}
        self.index = 0
        self.log: list[dict[str, Any]] = []

    @property
    def current(self) -> dict[str, Any] | None:
        return self.steps[self.index] if self.index < len(self.steps) else None

    def observe(self, evidence: dict[str, Any], at: datetime) -> dict[str, Any]:
        step = self.current
        if step is None:
            return {"status": "complete"}
        if step["done_when"](evidence):
            self.log.append({"step": self.index, "evidence": evidence, "at": as_dt(at).isoformat()})
            self.index += 1
            nxt = self.current
            return {"status": "advanced", "next": nxt["text"] if nxt else None, "anchor": nxt["anchor"] if nxt else None}
        return {"status": "waiting", "step": step["text"], "anchor": step["anchor"]}


def visual_change(previous: dict[str, Any], current: dict[str, Any], *, position_tol: float = 0.1) -> list[dict[str, Any]]:
    """Visual Change Memory over detected objects ``{label: {"pos": (x,y), "state": str}}``."""
    out = []
    for lbl in sorted(set(previous) | set(current)):
        a, b = previous.get(lbl), current.get(lbl)
        if a is None:
            out.append({"object": lbl, "change": "appeared"})
        elif b is None:
            out.append({"object": lbl, "change": "disappeared"})
        else:
            if math.dist(a["pos"], b["pos"]) > position_tol:
                out.append({"object": lbl, "change": "moved", "distance": round(math.dist(a["pos"], b["pos"]), 3)})
            if a.get("state") != b.get("state"):
                out.append({"object": lbl, "change": "state", "before": a.get("state"), "after": b.get("state")})
    return out


class LandmarkMemory:
    """Navigation Landmark Memory: landmarks and decision points on familiar routes."""

    def __init__(self) -> None:
        self.routes: dict[str, list[dict[str, Any]]] = {}

    def learn(self, route: str, landmark: str, latlon: tuple[float, float], *, decision: str = "") -> None:
        pts = self.routes.setdefault(route, [])
        for p in pts:
            if haversine_m(*p["latlon"], *latlon) < 30:
                p["seen"] += 1
                if decision:
                    p["decision"] = decision
                return
        pts.append({"landmark": landmark, "latlon": latlon, "decision": decision, "seen": 1})

    def guidance(self, route: str, here: tuple[float, float], *, ahead_m: float = 300) -> list[str]:
        out = []
        for p in self.routes.get(route, []):
            d = haversine_m(*here, *p["latlon"])
            if d <= ahead_m and p["seen"] >= 2:
                txt = f"In about {int(d)} m: {p['landmark']}"
                if p["decision"]:
                    txt += f" — {p['decision']}"
                out.append(txt)
        return out


# =========================================================================== object bindings / physical macros


class ObjectRegistry:
    """Universal Object Interface: 'this is the projector' becomes a reusable binding
    between a visual signature, manuals, discovered APIs and authorized controls."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}

    def bind(self, name: str, signature: Iterable[str], *, manual: str = "", device_api: str = "",
             controls: Iterable[str] = (), anchor: str = "") -> str:
        oid = stable_id(name, length=10)
        self.objects[oid] = {"name": name, "signature": set(signature), "manual": manual, "device_api": device_api,
                             "controls": set(controls), "anchor": anchor, "observations": 0}
        return oid

    def recognize(self, features: Iterable[str], min_overlap: float = 0.5) -> dict[str, Any] | None:
        f = set(features)
        best = max(self.objects.items(), key=lambda kv: jaccard(f, kv[1]["signature"]), default=None)
        if best is None or jaccard(f, best[1]["signature"]) < min_overlap:
            return None
        best[1]["observations"] += 1
        return {"id": best[0], **{k: v for k, v in best[1].items() if k != "signature"},
                "match": round(jaccard(f, best[1]["signature"]), 3)}

    def can(self, object_id: str, control: str) -> bool:
        return control in self.objects[object_id]["controls"]


def learn_physical_macro(demonstrations: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Physical Macros: from >=1 demonstrations (sequences of ``{"action", "object",
    "verify"}``) build the shared ordered procedure; steps present in every demo are
    required, others optional.  Each step records whether an authorized actuator can
    perform it (``"actuator"`` key) or Jarvis can only guide."""
    if not demonstrations:
        raise ValueError("need at least one demonstration")
    keyed = [[(s["action"], s.get("object", "")) for s in d] for d in demonstrations]
    common = [k for k in keyed[0] if all(k in other for other in keyed[1:])]
    steps = []
    first = {(s["action"], s.get("object", "")): s for s in demonstrations[0]}
    for d in demonstrations:
        for s in d:
            first.setdefault((s["action"], s.get("object", "")), s)
    seen = set()
    for d in keyed:
        for k in d:
            if k in seen:
                continue
            seen.add(k)
            s = first[k]
            steps.append({"action": k[0], "object": k[1], "required": k in common, "verify": s.get("verify", ""),
                          "mode": "perform" if s.get("actuator") else "guide"})
    return {"steps": steps, "demonstrations": len(demonstrations)}


# =========================================================================== predict / point / verify / calibrate


class PointingLoop:
    """Generalised Skylight loop: telemetry predicts target bearing; actuator points;
    perception verifies; measured error updates an exponential calibration offset."""

    def __init__(self, alpha: float = 0.3) -> None:
        self.offset = (0.0, 0.0)  # (azimuth, elevation) degrees
        self.alpha = alpha
        self.history: list[dict[str, Any]] = []

    @staticmethod
    def bearing(observer: tuple[float, float, float], target: tuple[float, float, float]) -> tuple[float, float]:
        """Azimuth/elevation from observer (lat, lon, alt_m) to target (lat, lon, alt_m)."""
        lat1, lon1, alt1 = observer
        lat2, lon2, alt2 = target
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dl = math.radians(lon2 - lon1)
        az = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                     math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360
        ground = haversine_m(lat1, lon1, lat2, lon2)
        el = math.degrees(math.atan2(alt2 - alt1, ground))
        return az, el

    def lead(self, position: tuple[float, float, float], velocity_mps: tuple[float, float, float], latency_s: float) -> tuple[float, float, float]:
        """Lead prediction: advance target by actuator/vision latency (vn, ve, vu)."""
        lat, lon, alt = position
        vn, ve, vu = velocity_mps
        dlat = (vn * latency_s) / 111_320.0
        dlon = (ve * latency_s) / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
        return lat + dlat, lon + dlon, alt + vu * latency_s

    def command(self, observer: tuple[float, float, float], target: tuple[float, float, float]) -> tuple[float, float]:
        az, el = self.bearing(observer, target)
        return (az + self.offset[0]) % 360, el + self.offset[1]

    def verify(self, commanded: tuple[float, float], detected_error: tuple[float, float] | None) -> dict[str, Any]:
        """``detected_error`` = (d_az, d_el) of the target from frame centre, or None if
        perception did not find it (no calibration update from a miss)."""
        if detected_error is None:
            self.history.append({"commanded": commanded, "verified": False})
            return {"verified": False, "offset": self.offset}
        daz, del_ = detected_error
        self.offset = (self.offset[0] + self.alpha * daz, self.offset[1] + self.alpha * del_)
        self.history.append({"commanded": commanded, "verified": True, "error": detected_error})
        return {"verified": abs(daz) < 1 and abs(del_) < 1, "offset": self.offset}


def walk_into(semantic_map: SemanticMap, entity: str, zone_id: str | None, launch: Callable[[str], None]) -> list[dict[str, Any]]:
    """Instantiate the zone's interface on entry (and report teardown on exit)."""
    events = semantic_map.update(entity, zone_id)
    for e in events:
        if e["event"] == "enter" and e.get("instantiate_interface"):
            launch(e["instantiate_interface"])
    return events
