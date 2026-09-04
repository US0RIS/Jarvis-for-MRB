from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis_mrb.planner_model import FAST_MODEL, QUALITY_MODEL, get_auto_route, get_planner_model


@dataclass(frozen=True)
class RouteDecision:
    model: str
    reason: str
    announce_analysis: bool = False


_COMPLEX_PATTERNS = [
    r"\barchitect(?:ure)?\b",
    r"\bdesign (?:a|an|the)\b",
    r"\bdebug\b",
    r"\broot cause\b",
    r"\bprove\b",
    r"\bderive\b",
    r"\boptimi[sz]e\b",
    r"\btrade[- ]?offs?\b",
    r"\bcompare\b.*\b(?:options|approaches|models|architectures)\b",
    r"\bwrite|generate|refactor\b.*\bcode\b",
    r"\bmath(?:ematics|ematical)?\b",
    r"\bcalculate\b.*\b(?:probability|expected|variance|integral|derivative)\b",
    r"\bresearch\b",
    r"\banaly[sz]e\b.*\b(?:deep|carefully|thoroughly|architecture|code|data)\b",
    r"\bsecurity review\b",
    r"\bthreat model\b",
]

_FAST_PATTERNS = [
    r"^(?:open|close|launch|start|stop|is|are|what's|whats|read|show|list|check)\b",
    r"\bcalendar\b",
    r"\bemail\b",
    r"\bspotify\b",
    r"\bbrowser\b",
    r"\bweather\b",
]


def choose_model(text: str) -> RouteDecision:
    """Select 8B vs 27B without spending a model call on classification.

    A model-based classifier would force the 8B model to load before a 27B request,
    which is counterproductive on a single 16 GB GPU. This deterministic classifier
    is effectively free and errs toward the quality model when requests are long or
    clearly reasoning-heavy.
    """
    selected = get_planner_model()
    if not get_auto_route():
        return RouteDecision(selected, "manual planner selection", False)

    normalized = " ".join(text.lower().split())
    words = normalized.split()

    if any(re.search(pattern, normalized) for pattern in _COMPLEX_PATTERNS):
        return RouteDecision(QUALITY_MODEL, "complex reasoning cue", True)
    if len(words) >= 75 or len(normalized) >= 480:
        return RouteDecision(QUALITY_MODEL, "long multi-part request", True)
    if normalized.count(" and ") >= 4 or normalized.count(" then ") >= 2:
        return RouteDecision(QUALITY_MODEL, "multi-stage request", True)
    if any(re.search(pattern, normalized) for pattern in _FAST_PATTERNS) and len(words) < 45:
        return RouteDecision(FAST_MODEL, "routine interaction", False)

    # Fast is the speculative default. If it cannot produce a valid tool protocol,
    # streaming_agent can fall back rather than making every ordinary turn pay 27B latency.
    return RouteDecision(FAST_MODEL, "default low-latency route", False)
