"""Physical-world provider normalisers in the Caltrans-adapter shape.

Every adapter here is a *parser/normaliser* over a payload the caller fetched from
an allowlisted official/public or user-owned source; none performs network I/O.
Each output is a timestamped observation with provenance, a ``tier`` (locally
observed vs provider-reported: Direct-Observation Tier / RF Reality Layer) and
"possible condition" framing where perception is involved.

future.md ideas covered: more state DOT camera feeds (WSDOT-shaped catalog),
ALERTWildfire cameras, harbor/coastal webcams, NOAA/NDBC buoys, PurpleAir/AirNow
local AQI, GTFS-realtime delays, FAA NOTAMs, Home Assistant as a capability bus
(Capability Bus Adapters, smart plugs with grant + readback), authenticated bench
sensor node, local ADS-B (readsb/tar1090), local AIS (AIS-catcher), rtl_433 RF
sensors (enrolled devices only), ESPHome/MQTT sensor fabric, Wi-Fi CSI camera-free
presence, Camera-Free Room Model fusion, Physical Sensor Gateway envelope, Universal
Media Gateway (discovery separated from transport), webcam-only livestream filter,
Eventification of camera detections (zone crossings), and LoRa/Meshtastic compact
alert encoding for off-grid transport.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlparse

from jarvis_mrb.horus._util import UTC, as_dt, stable_id

LOCAL = "locally_observed"
PROVIDER = "provider_reported"


@dataclass
class Observation:
    source: str
    kind: str
    subject: str
    at: datetime
    values: dict[str, Any]
    tier: str = PROVIDER
    latlon: tuple[float, float] | None = None
    framing: str = "observed"
    provenance: dict[str, Any] = field(default_factory=dict)


def allowlisted(url: str, hosts: Iterable[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


# =========================================================================== cameras


def normalize_dot_cameras(payload: list[dict[str, Any]], *, source: str, allowed_hosts: Iterable[str]) -> list[dict[str, Any]]:
    """WSDOT-style camera catalog (``CameraID, Title, ImageURL, CameraLocation{Latitude,Longitude}``)
    → cached catalog entries; images on non-allowlisted hosts are rejected."""
    out = []
    for c in payload:
        url = c.get("ImageURL") or c.get("image_url") or ""
        loc = c.get("CameraLocation") or {}
        lat = loc.get("Latitude", c.get("lat"))
        lon = loc.get("Longitude", c.get("lon"))
        if not url or lat is None or lon is None or not allowlisted(url, allowed_hosts):
            continue
        out.append({"id": f"{source}:{c.get('CameraID', c.get('id'))}", "title": c.get("Title", c.get("title", "")),
                    "image_url": url, "lat": float(lat), "lon": float(lon), "source": source,
                    "framing": "possible visible condition, not a confirmed incident"})
    return out


def wildfire_camera_observation(camera: dict[str, Any], smoke_score: float, at: datetime) -> Observation:
    """ALERTWildfire-style observation: never a confirmed fire claim."""
    label = "possible visible smoke" if smoke_score >= 0.6 else "no smoke visible in frame"
    return Observation(camera["source"], "camera_smoke", camera["id"], as_dt(at),
                       {"smoke_score": round(smoke_score, 3), "label": label}, PROVIDER,
                       (camera["lat"], camera["lon"]), "possible visible condition, not a confirmed incident",
                       {"image_url": camera["image_url"]})


_WEBCAM_POS = re.compile(r"\b(live ?cam|webcam|live view|beach cam|harbor|harbour|port|pier|surf cam|traffic cam|"
                         r"weather cam|camera|24/7 live)\b", re.I)
_WEBCAM_NEG = re.compile(r"\b(music|lofi|lo-fi|gaming|gameplay|news|podcast|radio|asmr|stream highlights|"
                         r"loop|relaxing|sleep|study|mix|reaction)\b", re.I)


def is_webcam_stream(title: str, description: str = "") -> bool:
    """Webcam-only filter so arbitrary livestreams don't become 'cameras'."""
    text = f"{title} {description}"
    return bool(_WEBCAM_POS.search(text)) and not _WEBCAM_NEG.search(text)


@dataclass
class CameraSource:
    """Universal Media Gateway: discovery/provenance is separate from transport."""

    id: str
    provider: str
    page_url: str
    stream_url: str
    protocol: str  # jpeg | mjpeg | hls | rtsp | webrtc
    latlon: tuple[float, float]
    public: bool
    license_note: str = ""


def gateway_plan(cam: CameraSource, *, gateway_base: str = "http://127.0.0.1:1984") -> dict[str, Any]:
    """Return the normalised consumer URL a go2rtc-like gateway would expose, plus the
    exact original source so the UI can show what Jarvis used."""
    if not cam.public:
        return {"ok": False, "reason": "source not established as public/authorized"}
    native = {"jpeg": "frame.jpeg", "mjpeg": "stream.mjpeg", "hls": "stream.m3u8", "rtsp": "stream.mp4",
              "webrtc": "webrtc"}
    if cam.protocol not in native:
        return {"ok": False, "reason": f"unsupported protocol {cam.protocol}"}
    return {"ok": True, "consumer_url": f"{gateway_base}/api/{native[cam.protocol]}?src={cam.id}",
            "source_of_truth": {"provider": cam.provider, "page": cam.page_url, "stream": cam.stream_url},
            "gateway_config": {cam.id: cam.stream_url}}


def zone_crossings(tracks: dict[str, list[tuple[datetime, tuple[float, float]]]], zone: list[tuple[float, float]],
                   *, camera: str, evidence_prefix: str = "") -> list[dict[str, Any]]:
    """Eventification of detections: raw boxes/tracks -> 'track entered/left zone'."""
    from jarvis_mrb.horus.spatial import point_in_polygon

    events = []
    for tid, pts in tracks.items():
        inside_prev = None
        for t, p in sorted(pts):
            inside = point_in_polygon(p, zone)
            if inside_prev is not None and inside != inside_prev:
                events.append({"camera": camera, "track": tid, "event": "entered_zone" if inside else "left_zone",
                               "at": as_dt(t).isoformat(), "evidence": f"{evidence_prefix}{camera}@{as_dt(t).isoformat()}"})
            inside_prev = inside
    return sorted(events, key=lambda e: e["at"])


# =========================================================================== marine / air


def parse_ndbc(text: str, station: str) -> list[Observation]:
    """NOAA NDBC realtime2 standard meteorological text (``MM`` = missing)."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    header = lines[0].lstrip("#").split()
    out = []
    for line in lines[1:]:
        if line.startswith("#"):
            continue
        parts = line.split()
        row = dict(zip(header, parts))
        try:
            at = datetime(int(row["YY"]), int(row["MM"]), int(row["DD"]), int(row["hh"]), int(row["mm"]), tzinfo=UTC)
        except (KeyError, ValueError):
            continue

        def num(k: str) -> float | None:
            v = row.get(k)
            return None if v in (None, "MM") else float(v)

        out.append(Observation(f"ndbc:{station}", "marine", station, at, {
            "wave_height_m": num("WVHT"), "wind_speed_mps": num("WSPD"), "gust_mps": num("GST"),
            "water_temp_c": num("WTMP"), "air_temp_c": num("ATMP"), "dominant_period_s": num("DPD")}))
    return out


# EPA 2024 PM2.5 AQI breakpoints (µg/m³, 24h-style truncation to 0.1).
_PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500),
]


def pm25_to_aqi(pm: float) -> int | None:
    c = int(max(pm, 0.0) * 10) / 10.0
    for lo, hi, ilo, ihi in _PM25_BREAKPOINTS:
        if lo <= c <= hi:
            return round((ihi - ilo) / (hi - lo) * (c - lo) + ilo)
    return 500 if c > 325.4 else None


def parse_airnow(observations: list[dict[str, Any]]) -> list[Observation]:
    out = []
    for o in observations:
        at = datetime.strptime(f"{o['DateObserved'].strip()} {int(o['HourObserved']):02d}", "%Y-%m-%d %H").replace(tzinfo=UTC)
        out.append(Observation("airnow", "aqi", o.get("ReportingArea", ""), at,
                               {"parameter": o["ParameterName"], "aqi": o["AQI"],
                                "category": (o.get("Category") or {}).get("Name")},
                               PROVIDER, (o.get("Latitude"), o.get("Longitude")) if o.get("Latitude") else None))
    return out


def parse_purpleair(sensor: dict[str, Any], *, at: datetime) -> Observation:
    pm = float(sensor.get("pm2.5_atm", sensor.get("pm2.5", 0.0)))
    return Observation("purpleair", "aqi", str(sensor.get("sensor_index", "")), as_dt(at),
                       {"pm2_5": pm, "aqi": pm25_to_aqi(pm), "basis": "uncorrected PM2.5 → EPA 2024 breakpoints"},
                       PROVIDER, (sensor.get("latitude"), sensor.get("longitude")) if sensor.get("latitude") else None)


def gtfs_delays(feed: dict[str, Any], *, stop_id: str) -> list[dict[str, Any]]:
    """Decoded GTFS-realtime FeedMessage (dict form) → delays at a stop."""
    out = []
    for ent in feed.get("entity", []):
        tu = ent.get("trip_update") or ent.get("tripUpdate")
        if not tu:
            continue
        trip = tu.get("trip", {})
        for stu in tu.get("stop_time_update", tu.get("stopTimeUpdate", [])):
            if str(stu.get("stop_id", stu.get("stopId"))) != stop_id:
                continue
            ev = stu.get("arrival") or stu.get("departure") or {}
            delay = ev.get("delay")
            if delay is not None:
                out.append({"route": trip.get("route_id", trip.get("routeId")), "trip": trip.get("trip_id", trip.get("tripId")),
                            "delay_min": round(delay / 60, 1), "message": f"route {trip.get('route_id', trip.get('routeId'))} "
                                                                          f"is {round(delay / 60)} minutes {'late' if delay > 0 else 'early'}"})
    return out


_NOTAM = re.compile(r"!(?P<loc>[A-Z]{3,4})\s+(?P<num>\d{2}/\d{3,4})\s+(?P<body>.*?)\s+(?P<start>\d{10})-(?P<end>\d{10}|PERM)", re.S)


def parse_notam(text: str) -> dict[str, Any] | None:
    """Domestic-format NOTAM line → why airspace/runway near you is affected."""
    m = _NOTAM.search(" ".join(text.split()))
    if not m:
        return None

    def t(v: str) -> str | None:
        if v == "PERM":
            return None
        return datetime.strptime(v, "%y%m%d%H%M").replace(tzinfo=UTC).isoformat()

    body = m.group("body")
    kind = "runway" if "RWY" in body else "airspace" if re.search(r"\b(TFR|AIRSPACE|UAS|SKYDIVE)\b", body) else \
        "navaid" if re.search(r"\b(VOR|ILS|NDB)\b", body) else "other"
    return {"location": m.group("loc"), "number": m.group("num"), "text": body, "kind": kind,
            "effective": t(m.group("start")), "expires": t(m.group("end"))}


# =========================================================================== direct observation (local RF / sensors)


def parse_readsb(aircraft_json: dict[str, Any], *, receiver: str, home: tuple[float, float] | None = None) -> list[Observation]:
    from jarvis_mrb.horus._util import haversine_m

    now = as_dt(aircraft_json.get("now", 0))
    out = []
    for a in aircraft_json.get("aircraft", []):
        if "lat" not in a or "lon" not in a:
            continue
        rate = a.get("baro_rate", a.get("geom_rate"))
        vals = {"flight": (a.get("flight") or "").strip(), "alt_ft": a.get("alt_baro"), "vert_rate_fpm": rate,
                "trend": "descending" if rate is not None and rate < -300 else "climbing" if rate is not None and rate > 300 else "level",
                "gs_kt": a.get("gs"), "seen_s": a.get("seen")}
        if home:
            vals["distance_mi"] = round(haversine_m(home[0], home[1], a["lat"], a["lon"]) / 1609.344, 2)
        out.append(Observation(f"adsb:{receiver}", "aircraft", a["hex"], now - timedelta(seconds=a.get("seen", 0)),
                               vals, LOCAL, (a["lat"], a["lon"])))
    return out


def parse_ais_catcher(messages: list[dict[str, Any]], *, receiver: str, at: datetime) -> list[Observation]:
    out = []
    for m in messages:
        if m.get("lat") is None or m.get("lon") is None:
            continue
        out.append(Observation(f"ais:{receiver}", "vessel", str(m["mmsi"]), as_dt(m.get("rxtime", at)) if isinstance(m.get("rxtime"), (int, float)) else as_dt(at),
                               {"speed_kt": m.get("speed"), "course": m.get("course"), "name": m.get("shipname")},
                               LOCAL, (m["lat"], m["lon"])))
    return out


def parse_rtl433(lines: Iterable[str], *, enrolled: dict[str, str]) -> list[Observation]:
    """rtl_433 JSON lines.  Only *enrolled* devices (``model:id`` -> name) are ingested;
    every other nearby broadcast is ignored rather than treated as Jarvis property."""
    out = []
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = f"{d.get('model')}:{d.get('id')}"
        if key not in enrolled:
            continue
        vals = {k: d[k] for k in ("temperature_C", "humidity", "battery_ok", "rain_mm", "wind_avg_km_h", "water") if k in d}
        out.append(Observation("rtl433", "rf_sensor", enrolled[key], as_dt(d.get("time", "1970-01-01T00:00:00")), vals, LOCAL))
    return out


def parse_esphome_state(topic: str, payload: str, *, at: datetime, prefix: str = "esphome") -> Observation | None:
    """ESPHome/MQTT ``<prefix>/<node>/sensor/<name>/state`` → observation."""
    parts = topic.split("/")
    if len(parts) < 5 or parts[0] != prefix or parts[-1] != "state":
        return None
    node, component, name = parts[1], parts[2], parts[3]
    try:
        value: Any = float(payload)
    except ValueError:
        value = payload.strip().upper() if payload.strip().upper() in ("ON", "OFF") else payload.strip()
    return Observation(f"esphome:{node}", component, name, as_dt(at), {"value": value}, LOCAL)


def csi_presence(amplitude_variance: list[float], *, baseline: float, motion_factor: float = 3.0,
                 presence_factor: float = 1.5) -> dict[str, Any]:
    """Wi-Fi CSI as a camera-free room sensor: only independently verifiable
    primitives (presence / motion).  Pose/vitals are deliberately not inferred."""
    if not amplitude_variance:
        return {"presence": None, "motion": None, "basis": "no CSI samples"}
    v = sum(amplitude_variance) / len(amplitude_variance)
    return {"presence": v >= presence_factor * baseline, "motion": v >= motion_factor * baseline,
            "score": round(v / baseline, 2) if baseline else None, "unsupported": ["pose", "vitals"]}


def room_presence(signals: dict[str, bool | None], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Camera-Free Room Model: fuse mmWave/CSI/BLE/door/light/audio-label signals."""
    w = weights or {"mmwave": 0.9, "csi": 0.6, "ble_phone": 0.7, "door": 0.3, "light_on": 0.2, "audio_voice": 0.6}
    known = {k: v for k, v in signals.items() if v is not None}
    if not known:
        return {"occupied": None, "confidence": 0.0, "basis": []}
    miss_yes, miss_no = 1.0, 1.0
    for k, v in known.items():
        if v:
            miss_yes *= 1 - w.get(k, 0.3)
        else:
            miss_no *= 1 - w.get(k, 0.3) * 0.7
    p_yes, p_no = 1 - miss_yes, 1 - miss_no
    occupied = p_yes > p_no
    return {"occupied": occupied, "confidence": round(abs(p_yes - p_no), 3), "basis": sorted(known)}


def sign_sensor_report(secret: bytes, report: dict[str, Any]) -> str:
    body = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()


def verify_sensor_report(secrets: dict[str, bytes], report: dict[str, Any], signature: str, *, now: datetime,
                         max_skew: timedelta = timedelta(minutes=5), seen_nonces: set[str] | None = None) -> Observation | None:
    """Authenticated bench sensor node / Physical Sensor Gateway envelope:
    HMAC per node, timestamp skew bound, nonce replay protection."""
    key = secrets.get(report.get("node", ""))
    if key is None or not hmac.compare_digest(sign_sensor_report(key, report), signature):
        return None
    at = as_dt(report["at"])
    if abs(as_dt(now) - at) > max_skew:
        return None
    if seen_nonces is not None:
        if report.get("nonce") in seen_nonces:
            return None
        seen_nonces.add(report.get("nonce"))
    return Observation(f"node:{report['node']}", report.get("kind", "sensor"), report.get("subject", report["node"]), at,
                       dict(report.get("values", {})), LOCAL)


# =========================================================================== Home Assistant capability bus


class HomeAssistantBus:
    """Treat Home Assistant as a subordinate capability bus: discover entities, wrap
    them in Jarvis authority (exact, short-lived, use-bounded grants) and verify via
    state readback.  Locks/garage/alarm domains are excluded by default."""

    DEFAULT_ALLOWED = {"light", "switch", "fan", "media_player", "sensor", "binary_sensor", "climate"}
    SERVICES = {"light": ("turn_on", "turn_off"), "switch": ("turn_on", "turn_off"), "fan": ("turn_on", "turn_off"),
                "media_player": ("media_play", "media_pause"), "climate": ("set_temperature",)}

    def __init__(self, allowed_domains: Iterable[str] | None = None) -> None:
        self.allowed = set(allowed_domains or self.DEFAULT_ALLOWED)
        self.grants: dict[str, dict[str, Any]] = {}

    def discover(self, states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        caps = []
        for s in states:
            domain = s["entity_id"].split(".", 1)[0]
            if domain not in self.allowed:
                continue
            caps.append({"entity_id": s["entity_id"], "domain": domain,
                         "name": (s.get("attributes") or {}).get("friendly_name", s["entity_id"]),
                         "state": s.get("state"), "actions": list(self.SERVICES.get(domain, ())),
                         "effect": "read" if domain in ("sensor", "binary_sensor") else "device"})
        return caps

    def grant(self, entity_id: str, service: str, *, now: datetime, ttl: timedelta = timedelta(minutes=2), uses: int = 1) -> str:
        domain = entity_id.split(".", 1)[0]
        if domain not in self.allowed or service not in self.SERVICES.get(domain, ()):
            raise PermissionError(f"{service} on {entity_id} not permitted")
        gid = stable_id(entity_id, service, now, length=10)
        self.grants[gid] = {"entity_id": entity_id, "service": service, "expires": as_dt(now) + ttl, "uses": uses}
        return gid

    def dispatch(self, grant_id: str, *, now: datetime) -> dict[str, Any]:
        g = self.grants.get(grant_id)
        if g is None or g["uses"] <= 0 or as_dt(now) >= g["expires"]:
            return {"status": "rejected", "reason": "no valid grant"}
        g["uses"] -= 1
        domain, _ = g["entity_id"].split(".", 1)
        return {"status": "dispatched_unverified",
                "request": {"method": "POST", "path": f"/api/services/{domain}/{g['service']}",
                            "json": {"entity_id": g["entity_id"]}}}

    @staticmethod
    def verify(service: str, readback_state: str) -> dict[str, Any]:
        expected = {"turn_on": "on", "turn_off": "off", "media_play": "playing", "media_pause": "paused"}.get(service)
        if expected is None:
            return {"status": "verification_not_defined"}
        return {"status": "verified" if readback_state == expected else "mismatch", "expected": expected, "observed": readback_state}


# =========================================================================== off-grid transport


def lora_compact(alert: dict[str, Any], *, max_bytes: int = 200) -> bytes:
    """Compact alert encoding for LoRa/Meshtastic-class links (~200 byte payloads)."""
    pri = {"info": "I", "warning": "W", "urgent": "U", "critical": "C"}.get(alert.get("priority", "info"), "I")
    ts = as_dt(alert.get("at")).strftime("%d%H%M")
    text = re.sub(r"\s+", " ", str(alert.get("text", ""))).strip()
    head = f"{pri}|{ts}|{alert.get('code', '')}|"
    budget = max_bytes - len(head.encode())
    enc = text.encode()[:max(0, budget)]
    while True:
        try:
            enc.decode()
            break
        except UnicodeDecodeError:
            enc = enc[:-1]
    return head.encode() + enc


def lora_expand(payload: bytes) -> dict[str, str]:
    pri, ts, code, text = payload.decode().split("|", 3)
    return {"priority": {"I": "info", "W": "warning", "U": "urgent", "C": "critical"}[pri], "ddhhmm": ts, "code": code, "text": text}
