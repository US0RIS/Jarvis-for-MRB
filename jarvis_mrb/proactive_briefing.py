from __future__ import annotations

"""Evidence-gated pre-meeting briefings (not an autonomous agent).

The existing calendar check in ``proactive_monitor`` calls
:func:`consider_event` for events starting soon. About ``briefing_lead_minutes``
(default 15) before start, this module asks ``world_prebrief.build`` for
evidence, scores how relevant that evidence is, and only interrupts when the
score reaches the user's threshold. Weak or missing evidence is recorded as a
suppressed item (inspectable via the attention ledger) and says nothing.

Interruption preferences (enable/disable, snooze, quiet hours) and the shared
hourly budget, duplicate guard and truthful delivery ledger live in
``proactive_attention`` so briefings and watch alerts behave identically.
Spoken text only restates facts present in the evidence.
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from jarvis_mrb import proactive_attention as attention
from jarvis_mrb.voice_router import VoiceTurn, register
from jarvis_mrb.voice_time import (
    clock_words, local_clock, number_words, parse_duration_seconds, parse_until, span_words, when_words,
)

EvidenceProvider = Callable[[str, str], "dict[str, Any] | None"]
WatchAlertProvider = Callable[[datetime], "list[dict[str, Any]]"]

WATCH_ALERT_LOOKBACK_SECONDS = 3 * 3600
SOURCE = "Horus world model (connected documents, commitments and calendar)"


def _default_evidence(event_id: str, summary: str) -> dict[str, Any] | None:
    from jarvis_mrb.world_prebrief import build
    return build(event_id, summary)


def _default_watch_alerts(now: datetime) -> list[dict[str, Any]]:
    return attention.recent_emitted(kind="watch_alert", within_seconds=WATCH_ALERT_LOOKBACK_SECONDS, now=now, limit=3)


def _default_belief_gaps(summary: str, start: datetime, now: datetime) -> list[Any]:
    from jarvis_mrb import belief_gap
    return [gap for gap, _event in belief_gap.upcoming_decision_gaps(
        [{"title": summary, "start": start.isoformat()}], now=now)]


def score_evidence(evidence: dict[str, Any], watch_alerts: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Relevance 0-100 with a readable breakdown. Only evidence flags count."""
    score = 0.0
    lines: list[str] = []

    def add(points: float, why: str) -> None:
        nonlocal score
        score += points
        lines.append(f"{why} (+{points:g})")

    term = bool(evidence.get("has_term_conflict"))
    doc = bool(evidence.get("has_document_change"))
    if term:
        add(60, "a project term changed or conflicts across your connected sources")
    if doc:
        add(45, "a connected document changed")
    if evidence.get("has_commitments"):
        add(30, "a commitment is still pending")
        if evidence.get("severity") == "warning" and not (term or doc):
            add(10, "the pre-brief flagged it as overdue")
    if evidence.get("has_intentions"):
        add(10, "you have a related next action")
    if evidence.get("has_recent_evidence") and not (term or doc):
        add(15, "recent connected updates exist")
    if watch_alerts:
        add(25, f"a watch alert fired within the last {span_words(WATCH_ALERT_LOOKBACK_SECONDS)}")
        if any(a.get("severity") in {"warning", "critical"} for a in watch_alerts):
            add(10, "that alert was rated warning or higher")
    return min(100.0, score), lines


def _compact(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _minutes_words(minutes: float) -> str:
    n = max(1, int(round(minutes)))
    return number_words(n) if n < 60 else str(n)


def _compose_text(summary: str, minutes: float, evidence: dict[str, Any],
                  watch_alerts: list[dict[str, Any]]) -> str:
    n = max(1, int(round(minutes)))
    head = f"{_compact(summary, 80)} starts in {_minutes_words(minutes)} minute{'s' if n != 1 else ''}."
    facts = [_compact(f, 170) for f in (evidence.get("facts") or [])[:2]]
    body = " ".join(f if f.endswith((".", "!", "?")) else f + "." for f in facts)
    extra = ""
    if watch_alerts:
        first = watch_alerts[0]
        extra = (f" Also, a watch alert at {local_clock(first.get('created_at'))}: "
                 f"{_compact(str(first.get('text') or ''), 150)}")
    return _compact(f"{head} {body}{extra}".strip(), 520)


def consider_event(
    event_id: str,
    summary: str,
    start: datetime,
    *,
    now: datetime | None = None,
    evidence_provider: EvidenceProvider | None = None,
    watch_alert_provider: WatchAlertProvider | None = None,
    belief_gap_provider: Any = None,
) -> dict[str, Any]:
    """Decide whether this upcoming event deserves a spoken briefing.

    Returns ``{"decision": emitted|suppressed|duplicate|skipped, "reason": ...}``.
    Safe to call every monitor cycle: emitted briefings are deduped per
    event+start, suppressions are collapsed per reason."""
    instant = (now or datetime.now(timezone.utc))
    if instant.tzinfo is None or start.tzinfo is None:
        raise ValueError("Briefing times must be timezone-aware.")
    prefs = attention.get_prefs(now=instant)
    minutes = (start - instant).total_seconds() / 60.0
    lead = prefs["briefing_lead_minutes"]
    if minutes <= 0 or not (lead - 7 < minutes <= lead + 5):
        return {"decision": "skipped", "reason": "outside_window", "minutes": round(minutes, 1)}

    key = f"briefing:{event_id}:{start.astimezone(timezone.utc).isoformat()}"
    threshold = prefs["briefing_threshold"]
    base = dict(kind="briefing", subject=event_id, dedupe_key=key, title="Horus briefing", threshold=threshold,
                source=SOURCE, observed_at=instant.astimezone(timezone.utc).isoformat(),
                rule=(f"pre-meeting briefing about {lead} minutes before an event, spoken only when evidence "
                      f"relevance reaches {threshold:g}"))
    if attention.is_emitted(key):
        return {"decision": "duplicate", "reason": "duplicate"}

    try:
        evidence = (evidence_provider or _default_evidence)(event_id, summary)
    except Exception as exc:
        evidence = None
        base["evidence_lines"] = [f"evidence lookup failed: {type(exc).__name__}"]
    # A belief gap (a figure the user last discussed has since changed in a
    # document this event is about) is independent, evidence-backed context.
    try:
        gaps = list((belief_gap_provider or _default_belief_gaps)(summary, start, instant))[:1]
    except Exception:
        gaps = []
    if gaps and not evidence:
        evidence = {"facts": []}
    if not evidence:
        item = attention.ProactiveItem(
            **{**base, "evidence_lines": base.get("evidence_lines") or ["no usable evidence was found for this event"]},
            text="", score=0.0)
        out = attention.record_suppressed(item, "no_evidence", now=instant)
        return {**out, "score": 0.0}

    try:
        alerts = (watch_alert_provider or _default_watch_alerts)(instant)
    except Exception:
        alerts = []
    score, breakdown = score_evidence(evidence, alerts)
    text = _compose_text(summary, minutes, evidence, alerts)
    gap_evidence: dict[str, Any] = {}
    if gaps:
        from jarvis_mrb import belief_gap
        gap = gaps[0]
        score = min(100.0, score + 60)
        breakdown.append("the last recorded reference to a related document used a figure that has since changed (+60)")
        text = _compact(f"{text} {belief_gap.warning_text(gap, instant)}", 640)
        gap_evidence = dict(gap.evidence)
    severity = "warning" if evidence.get("severity") == "warning" else "info"
    item = attention.ProactiveItem(
        **base, text=text, severity=severity, score=score,
        evidence_lines=[*(evidence.get("facts") or [])[:2], *breakdown],
        evidence={"facts": evidence.get("facts"), "flags": {k: evidence.get(k) for k in (
            "has_commitments", "has_intentions", "has_recent_evidence", "has_document_change",
            "has_term_conflict")}, "watch_alert_ids": [a.get("id") for a in alerts],
            "event_summary": summary, "minutes_before_start": round(minutes, 1),
            "belief_gap": gap_evidence or None})
    if score < threshold:
        out = attention.record_suppressed(item, "weak_evidence", now=instant)
        return {**out, "score": score}
    out = attention.submit(item, now=instant)
    if gaps and out.get("decision") == "emitted":
        from jarvis_mrb import belief_gap
        belief_gap._record_warning(gaps[0], "upcoming_event_briefing", instant)
    return {**out, "score": score, "text": text}


# Name used by proactive_monitor.
handle_calendar_event = consider_event


# ------------------------------------------------------------ voice control ---

def _norm(text: str) -> str:
    t = str(text or "").lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9:.' ]+", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    t = " ".join(t.split())
    t = re.sub(r"^(?:(?:hey|ok|okay) )?(?:horus|jarvis) ", "", t)
    return re.sub(r"^(?:please |can you |could you )+", "", t).strip()


_Q = r"(?:the |my |all )?(?:(?:proactive|meeting|pre meeting|premeeting|pre-meeting) )"
_Q_OPT = r"(?:the |my |all )?(?:(?:proactive|meeting|pre meeting|premeeting|pre-meeting) )?"
_SNOOZE = re.compile(r"^snooze (?:" + _Q_OPT + r")briefings?(?: (?P<rest>(?:for|until|till) .+))?$")
_DISABLE = re.compile(
    r"^(?:(?:stop|disable|pause|cancel|end) " + _Q + r"briefings?|"
    r"turn (?:off|of) " + _Q_OPT + r"briefings?|turn " + _Q_OPT + r"briefings? off|"
    r"stop briefing me (?:before|ahead of) (?:my )?(?:meetings|events)|no more (?:proactive|meeting) briefings?)$")
_ENABLE = re.compile(
    r"^(?:turn " + _Q_OPT + r"briefings? (?:back )?on(?: again)?|turn (?:back )?on " + _Q_OPT + r"briefings?|"
    r"(?:enable|resume|restart|unsnooze) " + _Q + r"briefings?|"
    r"(?:start|resume) briefing me (?:before|ahead of) (?:my )?(?:meetings|events)(?: again)?)$")
_QUIET_SET = re.compile(r"^(?:set|use|enable|turn on) quiet hours (?:from |between )?(?P<a>[0-9a-z: ]+?) (?:to|until|till|and) (?P<b>[0-9a-z: ]+)$")
_QUIET_OFF = re.compile(r"^(?:turn off|clear|disable|remove|cancel) quiet hours$")
_LIMIT = re.compile(
    r"^(?:set|limit|change) (?:my |the )?(?:interruption|alert|proactive|notification) (?:limit|budget) (?:to )?(?P<n>\d+)(?: (?:per|an|a|each) hour)?$|"
    r"^limit (?:proactive )?(?:alerts|interruptions|notifications) to (?P<m>\d+)(?: (?:per|an|a|each) hour)?$")
_STATUS = re.compile(
    r"^(?:are|is) (?:proactive |meeting )?briefings? (?:on|off|enabled|disabled|turned on|turned off)$|"
    r"^what(?:'s| are| is) my (?:proactive )?(?:briefing|interruption|attention) (?:settings?|preferences)$|"
    r"^(?:are you|is horus) (?:going to )?brief(?:ing)? me before (?:my )?(?:meetings|events)$")

_CLOCK_TOKEN = re.compile(r"^(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\s*(?P<ap>am|pm|a m|p m)?$")


def _hhmm(token: str) -> str | None:
    token = token.strip()
    if token in {"midnight"}:
        return "00:00"
    if token in {"noon"}:
        return "12:00"
    m = _CLOCK_TOKEN.match(token)
    if not m:
        return None
    hour, minute, ap = int(m.group("h")), int(m.group("m") or 0), (m.group("ap") or "").replace(" ", "")
    if ap:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ap == "pm" else 0)
    elif hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def _human_hhmm(value: str) -> str:
    return clock_words(datetime(2000, 1, 1, int(value[:2]), int(value[3:])))


def _monitor_running() -> bool:
    module = sys.modules.get("jarvis_mrb.proactive_monitor")
    return bool(module is not None and getattr(module, "_STARTED", False))


def _monitor_note() -> str:
    return "" if _monitor_running() else (
        " The background monitor is not running in this session, so nothing will be briefed until the Horus service is up.")


def status_text(now: datetime | None = None) -> str:
    instant = now or datetime.now(timezone.utc)
    p = attention.get_prefs(now=instant)
    budget = attention.budget_status(now=instant)
    if not p["briefings_enabled"]:
        state = "Proactive briefings are off."
    elif p["snoozed"]:
        until = datetime.fromisoformat(p["snooze_until"])
        state = f"Proactive briefings are snoozed until {when_words(until, instant)}."
    else:
        state = (f"Proactive briefings are on. I speak about {p['briefing_lead_minutes']} minutes before a meeting, "
                 "only when what I found scores high enough.")
    quiet = (f" Quiet hours are {_human_hhmm(p['quiet_start'])} to {_human_hhmm(p['quiet_end'])}."
             if p["quiet_start"] and p["quiet_end"] else "")
    return (f"{state}{quiet} I've used {budget['used']} of {budget['max_per_hour']} proactive interruptions this hour."
            + _monitor_note())


def handle(text: str, turn: VoiceTurn) -> str | None:
    n = _norm(text)
    if not n or "brief" not in n and "quiet hours" not in n and "limit" not in n and "budget" not in n:
        return None
    instant = datetime.now().astimezone()
    m = _SNOOZE.match(n)
    if m:
        rest = m.group("rest") or ""
        seconds = None
        until = parse_until(rest, instant) if rest else None
        if until is not None:
            seconds = (until - instant).total_seconds()
        elif rest:
            seconds = parse_duration_seconds(rest)
        if not seconds or seconds <= 0:
            return "For how long? For example, say 'snooze briefings for an hour'."
        if seconds > 7 * 86400:
            return "I can snooze briefings for at most 7 days."
        end = instant + timedelta(seconds=int(seconds))
        attention.set_prefs(snooze_until=end)
        return (f"Okay, no proactive briefings until {when_words(end, instant)}. "
                "Watch alerts you asked for still come through.")
    if _DISABLE.match(n):
        attention.set_prefs(briefings_enabled=False)
        return ("Okay, proactive meeting briefings are off. Say 'turn briefings back on' any time. "
                "Watch alerts you asked for and your scheduled daily briefing are unaffected.")
    if _ENABLE.match(n):
        attention.set_prefs(briefings_enabled=True, snooze_until="")
        return ("Proactive meeting briefings are back on. I only speak when a meeting has something that scores "
                "high enough, like a changed document or a pending commitment." + _monitor_note())
    m = _QUIET_SET.match(n)
    if m:
        a, b = _hhmm(m.group("a")), _hhmm(m.group("b"))
        if not a or not b or a == b:
            return "Tell me both times, like 'set quiet hours from 10 pm to 7 am'."
        attention.set_prefs(quiet_start=a, quiet_end=b)
        return f"Quiet hours set from {_human_hhmm(a)} to {_human_hhmm(b)}. Briefings stay silent then; watch alerts you asked for do not."
    if _QUIET_OFF.match(n):
        attention.set_prefs(quiet_start="", quiet_end="")
        return "Quiet hours are off."
    m = _LIMIT.match(n)
    if m:
        count = int(m.group("n") or m.group("m"))
        if not 1 <= count <= 60:
            return "Pick a limit between 1 and 60 per hour."
        attention.set_prefs(hourly_budget=count)
        return f"Okay, at most {count} proactive interruptions per hour. Critical weather and earthquake alerts can still go through."
    if _STATUS.match(n):
        return status_text(instant)
    return None


register("proactive_briefing", handle)
