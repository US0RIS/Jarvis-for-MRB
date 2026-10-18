"""Life admin, proactive scheduling and opportunity detection (Mercury + Cassandra).

future.md ideas implemented here: Push-don't-pull pre-meeting brief scheduling,
Bind calendar events to exact coordinates (geofence ETA alerts), Health-aware
scheduling flags, Email triage + drafted replies awaiting approval, Post-meeting
action-item extraction → tasks, Subscription/renewal and bill tracking from
receipts, Spending-anomaly detection, Contract/lease clause extraction, Vehicle
maintenance tracking, Package/delivery correlation, Meeting document freshness
check, Trip timeline fusion + departure checklist, General action-receipt capture,
Evening wind-down summary, Obligation Extraction, Preparation Engine, Opportunity
Detector, Micro-Opportunity Bundling, Useful Boredom Detector, Nearest-obligation
HUD, Gamified progress on admin tasks.

All extraction is deterministic pattern matching over text the caller supplies;
nothing is sent anywhere.  Drafted replies are never sent by this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from jarvis_mrb.horus._util import UTC, as_dt, haversine_m, mad, median, stable_id

# =========================================================================== calendar / brief


@dataclass
class Event:
    id: str
    title: str
    start: datetime
    end: datetime
    location: str = ""
    latlon: tuple[float, float] | None = None
    attendees: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    importance: str = "normal"  # normal | high


def brief_schedule(events: list[Event], *, lead_minutes: int = 15, now: datetime | None = None) -> list[dict[str, Any]]:
    """Push the pre-meeting brief automatically N minutes before each event."""
    now = as_dt(now)
    out = []
    for e in sorted(events, key=lambda e: e.start):
        push_at = as_dt(e.start) - timedelta(minutes=lead_minutes)
        if as_dt(e.start) > now:
            out.append({"event": e.id, "push_at": max(push_at, now).isoformat(), "title": e.title,
                        "kind": "prebrief", "late": push_at < now})
    return out


def geofence_eta_alert(event: Event, here: tuple[float, float], now: datetime, *, speed_mps: float = 13.4,
                       buffer_min: float = 5) -> dict[str, Any] | None:
    """'You're 12 minutes from the office, meeting starts in 10.'  Requires the event
    to be bound to coordinates; otherwise says so instead of guessing."""
    if event.latlon is None:
        return {"status": "unbound", "message": f"'{event.title}' has no bound coordinates; ETA unknown."}
    dist = haversine_m(*here, *event.latlon)
    eta = dist / speed_mps / 60
    until = (as_dt(event.start) - as_dt(now)).total_seconds() / 60
    if until < 0:
        return None
    if eta + buffer_min >= until:
        return {"status": "at_risk", "eta_min": round(eta), "starts_in_min": round(until),
                "message": f"You're {round(eta)} minutes from {event.location or 'the venue'}, "
                           f"'{event.title}' starts in {round(until)}."}
    return {"status": "ok", "eta_min": round(eta), "starts_in_min": round(until)}


def bind_location(event: Event, places: dict[str, tuple[float, float]]) -> Event:
    """Bind an event's free-text location to known coordinates (exact alias match)."""
    key = event.location.strip().lower()
    for name, ll in places.items():
        if name.lower() == key or (key and name.lower() in key):
            event.latlon = ll
            break
    return event


def health_flags(events: list[Event], sleep_hours: float | None, *, day: date, resting_hr_delta: float | None = None) -> list[str]:
    """Health-aware scheduling flags from opt-in health data."""
    if sleep_hours is None:
        return []
    flags = []
    morning = [e for e in events if as_dt(e.start).date() == day and as_dt(e.start).hour < 11]
    important = [e for e in morning if e.importance == "high"]
    if sleep_hours < 5 and important:
        e = important[0]
        flags.append(f"You slept {sleep_hours:g} hours and have '{e.title}' at {as_dt(e.start).strftime('%H:%M')}.")
    if resting_hr_delta is not None and resting_hr_delta >= 8 and events:
        flags.append("Resting heart rate is well above your baseline; consider a lighter day.")
    return flags


# =========================================================================== email


TRIAGE_RULES = [
    ("decision_needed", r"\b(approve|approval|decide|decision|sign|contract|offer|deadline|urgent|asap)\b"),
    ("scheduling", r"\b(meet|meeting|schedule|availability|calendar|reschedule|call)\b"),
    ("receipt", r"\b(receipt|order confirmation|your order|invoice|payment received|charged)\b"),
    ("newsletter", r"\b(unsubscribe|newsletter|digest|weekly roundup)\b"),
    ("fyi", r"\b(fyi|for your information|heads up)\b"),
]


def triage_email(msg: dict[str, str]) -> dict[str, Any]:
    text = f"{msg.get('subject', '')} {msg.get('body', '')}".lower()
    for label, pattern in TRIAGE_RULES:
        if re.search(pattern, text):
            break
    else:
        label = "routine"
    needs_human = label == "decision_needed"
    draft = None
    if label == "scheduling":
        draft = (f"Hi {msg.get('from_name', '').split(' ')[0] or 'there'},\n\nThanks — I'm checking my calendar and "
                 "will confirm a time shortly.\n")
    elif label in ("routine", "fyi"):
        draft = "Thanks, received.\n"
    return {"id": msg.get("id"), "label": label, "needs_decision": needs_human,
            "draft": draft, "send_status": "awaiting_explicit_approval" if draft else None}


# =========================================================================== meetings / obligations

_ACTION = re.compile(
    r"^(?:[-*•]\s*)?(?:action(?: item)?:\s*|todo:\s*|ai:\s*)?(?P<owner>[A-Z][a-z]+|I|We)\s+"
    r"(?P<verb>will|to|should|needs? to|must|agreed to)\s+(?P<task>.+?)(?:\s+(?:by|before|due)\s+(?P<due>[\w ,/-]+?))?\.?$",
    re.M)
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def resolve_due(text: str | None, ref: datetime) -> datetime | None:
    if not text:
        return None
    t = text.strip().lower()
    ref = as_dt(ref)
    if t in ("today", "eod", "end of day"):
        return ref.replace(hour=17, minute=0, second=0, microsecond=0)
    if t == "tomorrow":
        return (ref + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
    if t == "next week":
        return ref + timedelta(days=7)
    for i, d in enumerate(_WEEKDAYS):
        if t.endswith(d):
            ahead = (i - ref.weekday()) % 7 or 7
            return (ref + timedelta(days=ahead)).replace(hour=17, minute=0, second=0, microsecond=0)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 17, tzinfo=UTC)
    m = re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
    if m:
        year = int(m.group(3)) if m.group(3) else ref.year
        year = year + 2000 if year < 100 else year
        return datetime(year, int(m.group(1)), int(m.group(2)), 17, tzinfo=UTC)
    return None


def extract_action_items(notes: str, *, meeting_id: str, ended_at: datetime, me: str = "I") -> list[dict[str, Any]]:
    """Post-meeting action items → Life Fabric-shaped tasks with evidence."""
    out = []
    for m in _ACTION.finditer(notes):
        owner = m.group("owner")
        out.append({
            "id": stable_id(meeting_id, m.group(0), length=10),
            "owner": "me" if owner in ("I", me) else owner,
            "task": m.group("task").strip(),
            "due": iso_or_none(resolve_due(m.group("due"), ended_at)),
            "evidence": {"meeting": meeting_id, "line": m.group(0).strip()},
            "status": "open",
        })
    return out


def iso_or_none(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


_COMMIT = re.compile(r"\b(I(?:'ll| will)|we(?:'ll| will)|let me|I can|I promise to)\s+(?P<task>[^.!?\n]+)", re.I)
_REQUEST = re.compile(r"\b(?:can|could|would) you (?:please )?(?P<task>[^.!?\n]+)\??", re.I)


class ObligationGraph:
    """Obligation Extraction: commitments from email/messages/docs/calendar/receipts."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def ingest(self, text: str, *, source: str, author: str, at: datetime, me: str = "me") -> list[dict[str, Any]]:
        added = []
        for m in _COMMIT.finditer(text):
            due = None
            dm = re.search(r"\bby (\w+(?: \w+)?)", m.group("task"))
            if dm:
                due = resolve_due(dm.group(1), at)
            owner = me if author == me else author
            added.append(self._add(m.group("task").strip(), owner, source, at, due))
        for m in _REQUEST.finditer(text):
            if author != me:
                added.append(self._add(m.group("task").strip(), me, source, at, None, requested_by=author))
        return added

    def _add(self, task: str, owner: str, source: str, at: datetime, due: datetime | None, requested_by: str = "") -> dict[str, Any]:
        oid = stable_id(task.lower(), owner, length=10)
        item = self.items.setdefault(oid, {"id": oid, "task": task, "owner": owner, "due": iso_or_none(due),
                                           "evidence": [], "status": "open", "depends_on": [],
                                           "requested_by": requested_by})
        item["evidence"].append({"source": source, "at": as_dt(at).isoformat()})
        return item

    def depend(self, a: str, b: str) -> None:
        self.items[a]["depends_on"].append(b)

    def resolve(self, oid: str, evidence: str) -> None:
        self.items[oid]["status"] = "done"
        self.items[oid]["evidence"].append({"source": evidence, "resolution": True})

    def open_for(self, owner: str) -> list[dict[str, Any]]:
        return sorted((i for i in self.items.values() if i["owner"] == owner and i["status"] == "open"),
                      key=lambda i: i["due"] or "9999")


# =========================================================================== receipts / subscriptions / spending

_AMOUNT = re.compile(r"\$\s?(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)")
_RENEW = re.compile(r"\b(renews?|renewal|auto-?renew|next billing|will be charged|subscription)\b", re.I)
_PERIOD = re.compile(r"\b(monthly|annual(?:ly)?|yearly|weekly|per month|per year|/mo|/yr)\b", re.I)
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2},? \d{4})\b", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_date(text: str) -> date | None:
    t = text.strip().lower()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})$", t)
    if m:
        y = int(m.group(3))
        return date(y + 2000 if y < 100 else y, int(m.group(1)), int(m.group(2)))
    m = re.match(r"([a-z]{3})[a-z]* (\d{1,2}),? (\d{4})$", t)
    if m and m.group(1) in _MONTHS:
        return date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))
    return None


def parse_receipt(msg: dict[str, str]) -> dict[str, Any] | None:
    text = f"{msg.get('subject', '')}\n{msg.get('body', '')}"
    amt = _AMOUNT.search(text)
    if not amt:
        return None
    amount = float(amt.group(1).replace(",", ""))
    is_sub = bool(_RENEW.search(text))
    period = _PERIOD.search(text)
    dates = [d for d in (parse_date(x) for x in _DATE.findall(text)) if d]
    merchant = msg.get("from_name") or msg.get("from", "").split("@")[-1]
    return {"merchant": merchant, "amount": amount, "subscription": is_sub,
            "period": (period.group(1).lower() if period else None),
            "renews_on": dates[-1].isoformat() if is_sub and dates else None,
            "evidence": msg.get("id")}


def renewal_deadlines(receipts: list[dict[str, Any]], *, today: date, warn_days: int = 7) -> list[dict[str, Any]]:
    out = []
    for r in receipts:
        if r and r.get("subscription") and r.get("renews_on"):
            d = date.fromisoformat(r["renews_on"])
            days = (d - today).days
            if 0 <= days <= warn_days:
                out.append({**r, "days_until_renewal": days})
    return sorted(out, key=lambda r: r["days_until_renewal"])


def spending_anomalies(history: list[dict[str, Any]], new: list[dict[str, Any]], *, z: float = 3.5) -> list[dict[str, Any]]:
    """Flag charges out of pattern vs the user's *own* history (robust z per merchant,
    falling back to the global distribution; never-seen merchants flagged softly)."""
    by_m: dict[str, list[float]] = {}
    for h in history:
        by_m.setdefault(h["merchant"], []).append(float(h["amount"]))
    all_amts = [float(h["amount"]) for h in history]
    out = []
    for c in new:
        amts = by_m.get(c["merchant"])
        ref = amts if amts and len(amts) >= 3 else all_amts
        if len(ref) < 3:
            continue
        m, d = median(ref), mad(ref) or max(1.0, 0.05 * median(ref))
        score = (float(c["amount"]) - m) / (1.4826 * d)
        if score >= z:
            out.append({**c, "robust_z": round(score, 2), "typical": m,
                        "basis": "merchant history" if ref is amts else "overall history"})
        elif not amts:
            out.append({**c, "robust_z": round(score, 2), "typical": None, "basis": "new merchant", "soft": True})
    return out


# =========================================================================== contracts

_AUTO_RENEW = re.compile(r"(automatically renew|auto-?renew|shall renew|renew for (?:successive|additional))[^.]*\.", re.I)
_NOTICE = re.compile(r"\(?(\d{1,3})\)?\s*days?['’]?\s*(?:prior\s*)?(?:written\s*)?notice", re.I)
_TERM_END = re.compile(r"(?:terminat\w+|expir\w+|end)\w*\s+on\s+(" + _DATE.pattern[2:-2] + r")", re.I)


def extract_contract_clauses(text: str) -> dict[str, Any]:
    """Renewal deadlines and auto-renewal clauses → Life Fabric deadlines."""
    auto = _AUTO_RENEW.search(text)
    notice = _NOTICE.search(text)
    end = _TERM_END.search(text)
    end_date = parse_date(end.group(1)) if end else None
    out: dict[str, Any] = {
        "auto_renews": bool(auto),
        "auto_renew_clause": auto.group(0).strip() if auto else None,
        "notice_days": int(notice.group(1)) if notice else None,
        "term_ends": end_date.isoformat() if end_date else None,
    }
    if end_date and out["notice_days"] is not None:
        out["notice_deadline"] = (end_date - timedelta(days=out["notice_days"])).isoformat()
    return out


# =========================================================================== vehicle / packages / docs


@dataclass
class MaintenanceItem:
    name: str
    every_miles: int | None
    every_days: int | None
    last_miles: int
    last_date: date


def vehicle_due(items: list[MaintenanceItem], *, odometer: int, today: date, soon_miles: int = 500,
                soon_days: int = 14) -> list[dict[str, Any]]:
    out = []
    for it in items:
        reasons, status = [], "ok"
        if it.every_miles:
            left = it.last_miles + it.every_miles - odometer
            if left <= 0:
                status = "overdue"
            elif left <= soon_miles and status != "overdue":
                status = "soon"
            reasons.append(f"{left} miles left")
        if it.every_days:
            left_d = (it.last_date + timedelta(days=it.every_days) - today).days
            if left_d <= 0:
                status = "overdue"
            elif left_d <= soon_days and status == "ok":
                status = "soon"
            reasons.append(f"{left_d} days left")
        if status != "ok":
            out.append({"item": it.name, "status": status, "detail": ", ".join(reasons)})
    return out


_TRACKING = re.compile(r"\b(1Z[0-9A-Z]{16}|\d{12}|\d{20,22}|9\d{15,21})\b")


def correlate_packages(emails: list[dict[str, Any]], door_events: list[dict[str, Any]], *,
                       window: timedelta = timedelta(minutes=20)) -> list[dict[str, Any]]:
    """Courier says 'delivered' + a door/geofence event near that time = arrived."""
    out = []
    for e in emails:
        body = f"{e.get('subject', '')} {e.get('body', '')}"
        if not re.search(r"\bdelivered\b", body, re.I):
            continue
        t = as_dt(e["at"])
        tracking = _TRACKING.search(body)
        near = [d for d in door_events if abs(as_dt(d["at"]) - t) <= window]
        out.append({"tracking": tracking.group(1) if tracking else None, "claimed_delivered_at": t.isoformat(),
                    "corroborated": bool(near), "evidence": [d.get("id") for d in near],
                    "status": "arrived" if near else "claimed_only"})
    return out


def document_freshness(event: Event, versions: dict[str, list[dict[str, Any]]], last_reviewed: dict[str, datetime],
                       now: datetime) -> list[str]:
    """Meeting document freshness: 'this deck was updated 40 minutes ago'."""
    notes = []
    for doc in event.documents:
        vs = sorted(versions.get(doc, []), key=lambda v: as_dt(v["at"]))
        if not vs:
            continue
        latest = as_dt(vs[-1]["at"])
        reviewed = last_reviewed.get(doc)
        if reviewed is None or latest > as_dt(reviewed):
            mins = int((as_dt(now) - latest).total_seconds() // 60)
            notes.append(f"'{doc}' was updated {mins} minutes ago, after you last reviewed it.")
    return notes


# =========================================================================== trips / receipts


_FLIGHT = re.compile(r"\b(?:flight\s*)?([A-Z]{2}\s?\d{1,4})\b.*?\b([A-Z]{3})\s*(?:→|->|to)\s*([A-Z]{3})\b", re.S)
_HOTEL = re.compile(r"\b(check-?in)\b", re.I)


def trip_timeline(confirmations: list[dict[str, Any]], *, destination_checks: dict[str, Any] | None = None) -> dict[str, Any]:
    """Trip timeline fusion from confirmation emails + day-of departure checklist."""
    items = []
    for c in confirmations:
        body = f"{c.get('subject', '')}\n{c.get('body', '')}"
        fm = _FLIGHT.search(body)
        if fm:
            items.append({"kind": "flight", "at": as_dt(c["at"]).isoformat(), "flight": fm.group(1).replace(" ", ""),
                          "from": fm.group(2), "to": fm.group(3), "evidence": c.get("id")})
        elif _HOTEL.search(body):
            items.append({"kind": "hotel", "at": as_dt(c["at"]).isoformat(), "evidence": c.get("id"),
                          "name": c.get("from_name", "")})
    items.sort(key=lambda i: i["at"])
    checklist = ["ID / passport", "phone + charger", "confirmation numbers offline"]
    if any(i["kind"] == "flight" for i in items):
        checklist += ["check in online (24h before)", "verify gate/time on the day"]
    risks = []
    for k, v in (destination_checks or {}).items():
        if v:
            risks.append(f"destination {k}: {v}")
            checklist.append(f"review {k} before departure")
    return {"timeline": items, "checklist": checklist, "destination_risks": risks}


class ActionReceipts:
    """General action-receipt capture: reservations, form submissions, etc."""

    def __init__(self) -> None:
        self.pending: dict[str, dict[str, Any]] = {}

    def expect(self, action_id: str, description: str, match_terms: Iterable[str], *, deadline: datetime) -> None:
        self.pending[action_id] = {"description": description, "terms": [t.lower() for t in match_terms],
                                   "deadline": as_dt(deadline), "status": "awaiting_receipt", "evidence": None}

    def offer(self, message: dict[str, Any]) -> list[str]:
        text = f"{message.get('subject', '')} {message.get('body', '')}".lower()
        confirmed = []
        for aid, p in self.pending.items():
            if p["status"] == "awaiting_receipt" and all(t in text for t in p["terms"]):
                p["status"], p["evidence"] = "confirmed", message.get("id")
                confirmed.append(aid)
        return confirmed

    def overdue(self, now: datetime) -> list[str]:
        out = []
        for aid, p in self.pending.items():
            if p["status"] == "awaiting_receipt" and as_dt(now) > p["deadline"]:
                p["status"] = "unconfirmed"
                out.append(aid)
        return out


# =========================================================================== summaries / preparation / opportunities


def evening_summary(events_today: list[Event], events_tomorrow: list[Event], open_tasks: list[dict[str, Any]], *,
                    sleep_avg: float | None = None) -> str:
    lines = [f"Today: {len(events_today)} events."]
    if open_tasks:
        top = sorted(open_tasks, key=lambda t: t.get("due") or "9999")[:3]
        lines.append("Still open: " + "; ".join(t["task"] for t in top) + ".")
    if events_tomorrow:
        first = min(events_tomorrow, key=lambda e: e.start)
        lines.append(f"Tomorrow starts with '{first.title}' at {as_dt(first.start).strftime('%H:%M')}.")
        docs = [d for e in events_tomorrow for d in e.documents]
        if docs:
            lines.append("Prep: review " + ", ".join(docs[:3]) + ".")
    if sleep_avg is not None and sleep_avg < 6.5:
        lines.append(f"Your recent sleep averages {sleep_avg:g}h; an earlier night may help.")
    return " ".join(lines)


def prepare(event: Event, *, vehicle_range_mi: float | None = None, trip_distance_mi: float | None = None,
            forecast: dict[str, Any] | None = None, travel_min: float | None = None, parking_min: float = 0,
            security_min: float = 0, changed_docs: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Preparation Engine: work backward from the event to required state."""
    steps = []
    start = as_dt(event.start)
    if vehicle_range_mi is not None and trip_distance_mi is not None and vehicle_range_mi < 1.2 * trip_distance_mi * 2:
        steps.append({"do": "charge/fuel vehicle tonight", "by": (start - timedelta(hours=10)).isoformat(),
                      "why": f"range {vehicle_range_mi:g} mi vs round trip {2 * trip_distance_mi:g} mi + margin"})
    if forecast:
        if forecast.get("precip_prob", 0) >= 0.5:
            steps.append({"do": "bring rain gear", "why": f"{int(forecast['precip_prob'] * 100)}% chance of rain"})
        if forecast.get("temp_f") is not None and forecast["temp_f"] <= 45:
            steps.append({"do": "bring a warm layer", "why": f"{forecast['temp_f']}°F forecast"})
    if travel_min is not None:
        leave = start - timedelta(minutes=travel_min + parking_min + security_min + 10)
        steps.append({"do": "leave", "by": leave.isoformat(),
                      "why": f"travel {travel_min:g} + parking {parking_min:g} + security {security_min:g} + 10 buffer"})
    for d in changed_docs:
        steps.append({"do": f"review updated '{d}'", "by": (start - timedelta(minutes=30)).isoformat(),
                      "why": "document changed since your last review"})
    return steps


def free_gaps(events: list[Event], *, day_start: datetime, day_end: datetime, min_minutes: int = 15) -> list[tuple[datetime, datetime]]:
    cur = as_dt(day_start)
    gaps = []
    for e in sorted(events, key=lambda e: e.start):
        s = as_dt(e.start)
        if (s - cur).total_seconds() >= min_minutes * 60:
            gaps.append((cur, s))
        cur = max(cur, as_dt(e.end))
    if (as_dt(day_end) - cur).total_seconds() >= min_minutes * 60:
        gaps.append((cur, as_dt(day_end)))
    return gaps


@dataclass
class Errand:
    id: str
    title: str
    minutes: float
    latlon: tuple[float, float] | None = None
    value: float = 1.0
    needs: set[str] = field(default_factory=set)  # tools/conditions
    outdoor: bool = False


def opportunities(*, here: tuple[float, float] | None, free_minutes: float, errands: list[Errand],
                  conditions: set[str] = frozenset(), radius_m: float = 1500) -> dict[str, Any]:
    """Opportunity Detector + Micro-Opportunity Bundling + Useful Boredom Detector.
    Returns one best single task and the best nearby bundle that fits the window."""
    feasible = []
    for e in errands:
        if not e.needs <= set(conditions):
            continue
        if e.outdoor and "good_weather" not in conditions:
            continue
        travel = 0.0
        if e.latlon is not None:
            if here is None:
                continue
            d = haversine_m(*here, *e.latlon)
            if d > radius_m:
                continue
            travel = d / 80.0  # walking m/min
        if e.minutes + travel <= free_minutes:
            feasible.append((e, travel))
    if not feasible:
        return {"single": None, "bundle": [], "message": None}
    best = max(feasible, key=lambda x: x[0].value / (x[0].minutes + x[1]))[0]
    # greedy bundle by value density among nearby items
    bundle, used = [], 0.0
    for e, travel in sorted(feasible, key=lambda x: -(x[0].value / (x[0].minutes + x[1] + 1))):
        cost = e.minutes + (travel if not bundle else travel * 0.3)
        if used + cost <= free_minutes:
            bundle.append(e)
            used += cost
    msg = None
    if len(bundle) >= 2:
        msg = (f"You're already near here and have {int(free_minutes)} free minutes; "
               + " and ".join(b.title for b in bundle) + " can all be done now.")
    else:
        msg = f"You have {int(free_minutes)} free minutes: {best.title} fits."
    return {"single": best.id, "bundle": [b.id for b in bundle], "minutes": round(used, 1), "message": msg}


def nearest_obligations(*, now: datetime, events: list[Event], deadlines: list[dict[str, Any]],
                        places: list[dict[str, Any]], here: tuple[float, float] | None) -> dict[str, Any]:
    """Nearest-obligation glanceable HUD payload."""
    future = [e for e in events if as_dt(e.start) >= as_dt(now)]
    nxt = min(future, key=lambda e: e.start) if future else None
    dl = min((d for d in deadlines if d.get("due")), key=lambda d: d["due"], default=None)
    near = None
    if here is not None and places:
        near = min(places, key=lambda p: haversine_m(*here, *p["latlon"]))
        near = {**near, "distance_m": round(haversine_m(*here, *near["latlon"]))}
    return {"next_event": {"title": nxt.title, "start": as_dt(nxt.start).isoformat()} if nxt else None,
            "next_deadline": dl, "nearest_place": near}


def progress(tasks: list[dict[str, Any]], *, streak_days: int = 0) -> dict[str, Any]:
    """Gamified progress for the admin grind: % done, level, streak, next milestone."""
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    pct = 0 if total == 0 else round(100 * done / total)
    level = done // 5 + 1
    return {"done": done, "total": total, "percent": pct, "level": level, "streak_days": streak_days,
            "next_milestone": (level * 5) - done,
            "bar": "█" * (pct // 10) + "░" * (10 - pct // 10)}

