"""Repository Radar and meta-HORUS design tools.

future.md ideas implemented here: Repository Radar (score candidates for novelty,
fit to known capability gaps, activity and license; append to a human review
queue), the GitHub capability-mining catalog as structured data (research
candidates — *not* dependencies), Ongoing discovery rule, Concept Importer,
Anti-Feature Detector, Complexity Budget and Feature Crystallization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from jarvis_mrb.horus._util import as_dt, jaccard, tokens


@dataclass(frozen=True)
class Candidate:
    repo: str
    category: str
    primitive: str  # the missing primitive it could supply
    notes: str = ""
    license: str = "unverified"
    status: str = "research_candidate"  # research_candidate | evaluating | adopted | rejected


# Captured verbatim from future.md's GitHub surveys.  Status stays
# ``research_candidate`` until license/security/hardware review and an end-to-end
# test on the actual Jarvis hardware.
CATALOG: tuple[Candidate, ...] = (
    Candidate("opensymph/open-computer-use", "computer_use", "accessibility-first desktop control lane"),
    Candidate("heaventree/cua-desktop-ai", "computer_use", "model-agnostic computer-use SDK + evals"),
    Candidate("trycua/cua", "computer_use", "driver + isolated desktops + Cua Bench verification"),
    Candidate("microsoft/UFO", "computer_use", "Windows host/app agent split with UIA"),
    Candidate("bytedance/UI-TARS-desktop", "computer_use", "visual grounding fallback lane"),
    Candidate("browser-use/browser-use", "browser", "Playwright browser agent backend"),
    Candidate("arthurkatcher/desktop-use", "computer_use", "observable/replayable GUI missions"),
    Candidate("shlawgathon/Computer-Use", "computer_use", "demonstrate/record/replay workflows"),
    Candidate("mediar-ai/terminator", "computer_use", "deterministic Windows automation with AI recovery"),
    Candidate("ShawnPana/phone-harness", "phone", "iPhone Mirroring control surface"),
    Candidate("jackwener/opencli", "browser", "crystallize websites into deterministic tools"),
    Candidate("omxyz/lumen", "browser", "self-healing replay + completion verifier"),
    Candidate("vercel-labs/agent-browser", "browser", "accessibility-tree browser CLI"),
    Candidate("pinchtab/pinchtab", "browser", "persistent local browser control plane"),
    Candidate("lightpanda-io/browser", "browser", "low-overhead headless browser for read-only sensors"),
    Candidate("getzep/graphiti", "memory", "temporal knowledge graph semantics"),
    Candidate("neo4j-labs/agent-memory", "memory", "graph-native agent memory with reasoning traces"),
    Candidate("letta-ai/letta-code", "memory", "persistent agent identity across backends"),
    Candidate("xzf-thu/VoiceMem", "memory", "speculative memory prefetch for voice turns"),
    Candidate("AlexxIT/go2rtc", "cameras", "universal stream normalization gateway"),
    Candidate("koush/scrypted", "cameras", "camera plugin + detection pipeline"),
    Candidate("blakeblackshear/frigate", "cameras", "event-oriented local object detection"),
    Candidate("streamlink/streamlink", "cameras", "public livestream resolution"),
    Candidate("yt-dlp/yt-dlp", "cameras", "public livestream resolution"),
    Candidate("roboflow/supervision", "cameras", "tracking/zone eventification primitives"),
    Candidate("bluenviron/mediamtx", "media", "media router with recording/playback"),
    Candidate("dgtlmoon/changedetection.io", "monitoring", "generalized web Reality Diff"),
    Candidate("huginn/huginn", "monitoring", "persistent event agents graph"),
    Candidate("binwiederhier/ntfy", "monitoring", "self-hosted push bus for redundant alerts"),
    Candidate("drasi-project/drasi-platform", "data_plane", "change-query/reaction engine"),
    Candidate("eclipse-zenoh/zenoh", "data_plane", "pub/sub + store/query node transport"),
    Candidate("livekit/agents", "voice", "realtime multimodal session transport"),
    Candidate("rhasspy/wyoming", "voice", "interoperable voice satellite protocol"),
    Candidate("The-OASIS-Project/dawn", "voice", "multi-room presence topology reference"),
    Candidate("QwenAudio/qwen-audio-agent", "voice", "full-duplex conversation while work happens elsewhere"),
    Candidate("Intent-Lab/VisionClaw", "voice", "Ray-Ban realtime voice+vision transport reference"),
    Candidate("debpalash/VoiceStudio", "tts", "provider-independent local TTS service layer", license="AGPL-3.0"),
    Candidate("OpenMOSS/MOSS-TTS-Nano", "tts", "CPU-class cloned-voice fallback"),
    Candidate("resemble-ai/chatterbox", "tts", "high-quality open TTS", license="MIT"),
    Candidate("SWivid/F5-TTS", "tts", "zero-shot cloning TTS", license="MIT"),
    Candidate("fishaudio/fish-speech", "tts", "expressive TTS"),
    Candidate("ServeurpersoCom/qwentts.cpp", "tts", "native quantized Qwen TTS"),
    Candidate("FireRedTeam/FireRedTTS3", "tts", "voice design/cloning", license="Apache-2.0 (code)"),
    Candidate("k2-fsa/OmniVoice", "tts", "upstream OmniVoice engine"),
    Candidate("home-assistant/core", "physical", "capability bus for local devices"),
    Candidate("meshtastic/firmware", "physical", "off-grid LoRa mesh transport"),
    Candidate("juanfont/headscale", "physical", "self-hosted private device mesh"),
    Candidate("ruvnet/RuView", "sensing", "Wi-Fi CSI camera-free presence"),
    Candidate("esphome/esphome", "sensing", "standardized sensor-node firmware"),
    Candidate("merbanan/rtl_433", "sensing", "local RF sensor receiver"),
    Candidate("cpaczek/skylight", "rf", "ADS-B predict/point/verify/calibrate loop"),
    Candidate("wiedehopf/readsb", "rf", "local aircraft receiver"),
    Candidate("wiedehopf/tar1090", "rf", "aircraft history/visualization"),
    Candidate("jvde-github/AIS-catcher", "rf", "local AIS vessel receiving"),
    Candidate("SatDump/SatDump", "rf", "local satellite downlink processing"),
    Candidate("thkruz/keeptrack.space", "rf", "offline orbital world model"),
    Candidate("koala73/worldmonitor", "world", "global data-fusion source adapters"),
    Candidate("bilawalsidhu/gods-eye-view", "world", "3D spatial-intelligence globe reference", license="non-standard"),
    Candidate("tidwall/tile38", "world", "realtime geofencing database"),
    Candidate("organicmaps/organicmaps", "world", "offline maps/search"),
    Candidate("Project-OSRM/osrm-backend", "world", "offline routing"),
    Candidate("promptfoo/promptfoo", "verification", "model/agent regression matrices"),
    Candidate("langfuse/langfuse", "verification", "trace/eval observability"),
    Candidate("opensandbox-group/OpenSandbox", "verification", "isolated execution sandbox"),
    Candidate("firecracker-microvm/firecracker", "verification", "microVM isolation"),
)

PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "ISC"}


def score_candidate(meta: dict[str, Any], gaps: Iterable[str], *, existing_primitives: Iterable[str] = (),
                    now: datetime | None = None) -> dict[str, Any]:
    """Score a repository by fit to *known gaps*, novelty, activity and license —
    popularity alone is never sufficient."""
    desc = f"{meta.get('description', '')} {' '.join(meta.get('topics', []))}"
    dt = set(tokens(desc))
    fit = max((jaccard(dt, tokens(g)) for g in gaps), default=0.0)
    novelty = 1.0 - max((jaccard(dt, tokens(p)) for p in existing_primitives), default=0.0)
    days = (as_dt(now) - as_dt(meta["pushed_at"])).days if meta.get("pushed_at") else 9999
    activity = 1.0 if days <= 30 else 0.6 if days <= 180 else 0.2
    lic = meta.get("license") or "unknown"
    license_score = 1.0 if lic in PERMISSIVE else 0.5 if lic.startswith(("GPL", "AGPL", "LGPL")) else 0.2
    score = 0.45 * fit + 0.2 * novelty + 0.2 * activity + 0.15 * license_score
    return {"repo": meta.get("full_name"), "score": round(score, 3), "fit": round(fit, 3), "novelty": round(novelty, 3),
            "activity": activity, "license": lic, "stars_ignored": meta.get("stargazers_count"),
            "interesting": fit >= 0.15 and score >= 0.4}


class RadarQueue:
    def __init__(self) -> None:
        self.queue: list[dict[str, Any]] = []
        self.seen: set[str] = {c.repo.lower() for c in CATALOG}

    def offer(self, scored: dict[str, Any]) -> bool:
        repo = (scored.get("repo") or "").lower()
        if not scored.get("interesting") or repo in self.seen:
            return False
        self.seen.add(repo)
        self.queue.append({**scored, "status": "awaiting_human_review"})
        return True


def discovery_queries(categories: Iterable[str], *, year: int) -> list[str]:
    """Ongoing discovery rule: mechanical category queries + recently-created/high-growth."""
    out = []
    for c in categories:
        out.append(f"topic:{c} stars:>200")
        out.append(f"{c} created:>={year}-01-01 stars:>100")
        out.append(f"awesome {c}")
    return out


# =========================================================================== meta design tools

CONCEPTS = {
    "SRE": ["SLOs", "error budgets", "canary", "rollback", "runbooks", "blameless postmortems"],
    "aviation": ["sterile cockpit", "mode annunciation", "checklists", "crew resource management", "automation surprise"],
    "intelligence analysis": ["ACH", "key assumptions", "source independence", "collection plans", "confidence calibration"],
    "emergency management": ["incident command", "common operating picture", "escalation ladders", "drills"],
    "industrial control": ["alarm rationalization", "first-out", "operating envelopes", "condition-based maintenance"],
    "robotics": ["sensor fusion", "SLAM", "predict-point-verify", "state machines"],
    "HCI": ["interruptibility", "modality independence", "progressive disclosure", "direct manipulation"],
}


def concept_importer(subsystem_description: str) -> list[dict[str, Any]]:
    """Ask which existing discipline patterns a new subsystem should inherit."""
    words = set(tokens(subsystem_description))
    out = []
    for field_name, concepts in CONCEPTS.items():
        for c in concepts:
            overlap = words & set(tokens(c))
            if overlap:
                out.append({"discipline": field_name, "concept": c, "matched": sorted(overlap)})
    return out


ANTI_FEATURE_PATTERNS = {
    "complexity": ("too complicated", "confusing", "too many settings", "hard to configure"),
    "distraction": ("too many notifications", "spam", "annoying", "interrupts", "nagging"),
    "unreliability": ("stopped working", "broke", "flaky", "unreliable", "doesn't work"),
    "privacy": ("creepy", "listening", "tracking", "privacy", "data sold"),
    "maintenance": ("constantly update", "keeps breaking", "maintenance", "babysit"),
}


def anti_features(complaints: Iterable[str], *, min_count: int = 2) -> list[dict[str, Any]]:
    """Mine complaints into explicit design constraints."""
    counts = {k: 0 for k in ANTI_FEATURE_PATTERNS}
    for c in complaints:
        cl = c.lower()
        for k, pats in ANTI_FEATURE_PATTERNS.items():
            if any(p in cl for p in pats):
                counts[k] += 1
    constraints = {
        "complexity": "every capability must work with zero configuration defaults",
        "distraction": "all proactive output goes through the shared attention budget",
        "unreliability": "capability claims require current passing evidence",
        "privacy": "sensing is opt-in, scoped and visible",
        "maintenance": "automations carry owners, tests and retirement conditions",
    }
    return [{"theme": k, "count": n, "constraint": constraints[k]} for k, n in counts.items() if n >= min_count]


@dataclass
class ComplexityBudget:
    total: float
    spent: dict[str, float] = field(default_factory=dict)

    def request(self, subsystem: str, cost: float, *, collapses: Iterable[str] = ()) -> dict[str, Any]:
        """A primitive that collapses several special cases refunds their cost."""
        refunded = {c: self.spent[c] for c in collapses if c in self.spent}
        remaining = self.total - sum(v for k, v in self.spent.items() if k not in refunded)
        if cost > remaining:
            return {"approved": False, "remaining": remaining, "refunded": 0.0}
        for c in refunded:
            del self.spent[c]
        refund = sum(refunded.values())
        self.spent[subsystem] = cost
        return {"approved": True, "remaining": remaining - cost, "refunded": refund}


def crystallize(ideas: list[str], *, threshold: float = 0.2, primitives: dict[str, Iterable[str]] | None = None) -> list[dict[str, Any]]:
    """Feature Crystallization: find clusters of ideas that are one missing primitive."""
    prims = primitives or {
        "standing query engine": ("watch", "monitor", "alert", "standing", "query", "trigger"),
        "temporal truth model": ("history", "rewind", "diff", "temporal", "changed", "valid"),
        "attention arbitration": ("notification", "interrupt", "attention", "alert", "budget", "deliver"),
        "authority grants": ("permission", "grant", "authority", "emergency", "delegated", "scope"),
        "evidence ledger": ("evidence", "provenance", "receipt", "verify", "lineage", "source"),
    }
    out = []
    for name, keys in prims.items():
        ks = set(keys)
        members = [i for i in ideas if len(ks & set(tokens(i))) / max(1, min(len(ks), len(set(tokens(i))))) >= threshold]
        if len(members) >= 2:
            out.append({"primitive": name, "ideas": members, "count": len(members)})
    return sorted(out, key=lambda c: -c["count"])
