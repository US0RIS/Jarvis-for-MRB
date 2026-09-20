from __future__ import annotations

"""Model-free routing for explicit Jarvis commands.

The router only chooses existing permission-aware executors; it NEVER executes,
bypasses approvals, or guesses a recipient, person, deadline or ambiguous target.
A miss goes to the existing model planner.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Route:
    family: str
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    answer: str = ""


def _tool(family: str, name: str, **args: Any) -> Route:
    return Route(family, name, args)


def _match(pattern: str, text: str) -> re.Match[str] | None:
    return re.fullmatch(pattern, text, flags=re.IGNORECASE)


def _clock(text: str, now: datetime) -> Route | None:
    stamp = lambda value: value.strftime("%I:%M %p").lstrip("0")
    day = lambda value: value.strftime("%A, %B ") + str(value.day) + value.strftime(", %Y")
    if text in {"what time is it", "what is the time", "what's the time", "current time", "tell me the time"}:
        return Route("clock.local", answer="It is " + stamp(now) + " locally.")
    if text in {"what date is it", "what day is it", "what day is today", "what's today's date", "what is today's date", "today's date"}:
        return Route("clock.local", answer="Today is " + day(now) + ".")
    m = _match(r"(?:what time is it|what(?:'s| is) the time|current time) in ([a-z ]+)", text)
    if not m:
        return None
    city = m.group(1).lower()
    zones = {
        "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
        "san francisco": "America/Los_Angeles", "nyc": "America/New_York",
        "new york": "America/New_York", "washington dc": "America/New_York",
        "chicago": "America/Chicago", "denver": "America/Denver",
        "phoenix": "America/Phoenix", "honolulu": "Pacific/Honolulu",
        "london": "Europe/London", "amsterdam": "Europe/Amsterdam",
        "oslo": "Europe/Oslo", "paris": "Europe/Paris",
        "tokyo": "Asia/Tokyo", "melbourne": "Australia/Melbourne",
        "sydney": "Australia/Sydney", "cape town": "Africa/Johannesburg",
        "dubai": "Asia/Dubai", "singapore": "Asia/Singapore",
        "mumbai": "Asia/Kolkata", "auckland": "Pacific/Auckland",
    }
    if city not in zones:
        return None
    local = now.astimezone(ZoneInfo(zones[city]))
    return Route("clock.city", answer=f"It is {stamp(local)} on {day(local)} in {city.title()}.")


def _arithmetic(text: str) -> Route | None:
    m = _match(
        r"(?:what(?:'s| is) |calculate |compute )?"
        r"(-?\d{1,12}(?:\.\d{1,8})?)\s*"
        r"(\+|plus|-|minus|\*|×|times|multiplied by|/|÷|divided by)\s*"
        r"(-?\d{1,12}(?:\.\d{1,8})?)", text)
    if not m:
        return None
    a, operator, b = Decimal(m.group(1)), m.group(2).lower(), Decimal(m.group(3))
    try:
        if operator in {"+", "plus"}:
            result = a + b
        elif operator in {"-", "minus"}:
            result = a - b
        elif operator in {"*", "×", "times", "multiplied by"}:
            result = a * b
        else:
            if b == 0:
                return Route("math", answer="Division by zero is undefined.")
            result = a / b
        rounded = result.quantize(Decimal("0.000000000001")) if result.as_tuple().exponent < -12 else result
    except InvalidOperation:
        return None
    value = format(rounded, "f")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return Route("math", answer=(value if value != "-0" else "0")
                 + (" (rounded to twelve decimal places)." if rounded != result else "."))
    

def _calendar_day(which: str, now: datetime) -> Route:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    offset = {"yesterday": -1, "today": 0, "tomorrow": 1}[which.lower()]
    start = midnight + timedelta(days=offset)
    end = midnight + timedelta(days=offset + 1)
    return _tool("calendar.day", "calendar.query",
                 direction="past" if offset < 0 else "future",
                 start=start.isoformat(), end=end.isoformat(), limit=20)


_EXACT: dict[str, tuple[str, str, dict[str, Any]]] = {
    "list my browser tabs": ("browser.tabs", "browser.list_tabs", {}),
    "show browser tabs": ("browser.tabs", "browser.list_tabs", {}),
    "what tabs are open in my browser": ("browser.tabs", "browser.list_tabs", {}),
    "is my browser connected": ("browser.status", "browser.status", {}),
    "is opera connected": ("browser.status", "browser.status", {}),
    "is google connected": ("google.status", "google.status", {}),
    "are gmail and calendar connected": ("google.status", "google.status", {}),
    "is web search working": ("web.status", "web.status", {}),
    "what is running on my computer": ("pc.apps", "pc.list_running_apps", {"limit": 30}),
    "what's running on my computer": ("pc.apps", "pc.list_running_apps", {"limit": 30}),
    "which programs are running": ("pc.apps", "pc.list_running_apps", {"limit": 30}),
    "which apps are running": ("pc.apps", "pc.list_running_apps", {"limit": 30}),
    "what is on my desktop": ("pc.context", "pc.context", {}),
    "what's on my desktop": ("pc.context", "pc.context", {}),
    "what window is active": ("pc.context", "pc.context", {}),
    "how much vram do i have free": ("resources", "system.resources", {}),
    "how much ram is free": ("resources", "system.resources", {}),
    "check gpu temperature": ("resources", "system.resources", {}),
    "is minecraft running": ("minecraft", "pc.minecraft_status", {}),
    "launch minecraft": ("minecraft", "pc.launch_minecraft", {}),
    "ensure minecraft is running": ("minecraft", "pc.ensure_minecraft_running", {}),
    "check the sandbox": ("sandbox", "sandbox.status", {}),
    "is the sandbox running": ("sandbox", "sandbox.status", {}),
    "show my scheduled reminders": ("jobs", "jobs.list", {}),
    "list my reminders": ("jobs", "jobs.list", {}),
    "show my reminders": ("jobs", "jobs.list", {}),
    "list my meeting notes": ("meeting", "meeting.list", {"limit": 10}),
    "show my recent meetings": ("meeting", "meeting.list", {"limit": 10}),
    "show my temporary context": ("state", "state.temp_get", {}),
    "show my persistent context": ("state", "state.get", {}),
    "list custom tools": ("custom", "custom.list", {}),
    "list repair proposals": ("custom", "custom.repairs", {}),
    "is agency enabled": ("agency", "agency.status", {}),
    "show agency status": ("agency", "agency.status", {}),
    "what is on my calendar": ("calendar", "calendar.list", {"days": 7, "limit": 10}),
    "show my upcoming meetings": ("calendar", "calendar.list", {"days": 7, "limit": 10}),
    "what are my upcoming appointments": ("calendar", "calendar.list", {"days": 7, "limit": 10}),
    "what's on my calendar this week": ("calendar", "calendar.list", {"days": 7, "limit": 20}),
    "what is on my calendar this week": ("calendar", "calendar.list", {"days": 7, "limit": 20}),
    "find conflicts on my calendar": ("calendar", "calendar.conflicts", {"days": 7}),
    "what is in my inbox": ("gmail", "gmail.query", {"query": "in:inbox", "limit": 5}),
    "show my inbox": ("gmail", "gmail.query", {"query": "in:inbox", "limit": 5}),
    "what are my unread messages": ("gmail", "gmail.query", {"query": "is:unread in:inbox", "limit": 5}),
    "what is my latest sent email": ("gmail", "gmail.query", {"query": "in:sent", "limit": 1}),
    "what was my last sent email": ("gmail", "gmail.query", {"query": "in:sent", "limit": 1}),
    "show my sent emails": ("gmail", "gmail.query", {"query": "in:sent", "limit": 5}),
    "list recent emails": ("gmail", "gmail.query", {"query": "in:inbox", "limit": 5}),
    "what was my most recent meeting": ("calendar", "calendar.recent", {"days_back": 3650}),
    "list my background tasks": ("background", "background.list", {"limit": 10}),
}


def dispatch(text: str, *, now: datetime | None = None) -> Route | None:
    """Anchored literal/parameter rules only; unknown/ambiguous text => None."""
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3000:
        return None
    raw = re.sub(r"\s+", " ", text.strip())
    spoken = raw.rstrip("?.!").strip()
    lower = spoken.lower()
    current = now or datetime.now().astimezone()
    answer = _clock(lower, current) or _arithmetic(lower)
    if answer:
        return answer
    if lower in _EXACT:
        family, tool, arguments = _EXACT[lower]
        return Route(family, tool, dict(arguments))

    m = _match(r"(?:what(?:'s| is) on|show|list|check) my (?:calendar|schedule|appointments)(?: for)? (today|tomorrow|yesterday)", spoken)
    if m:
        return _calendar_day(m.group(1), current)
    m = _match(r"(?:do i have (?:any )?(?:meetings|appointments)|am i busy|am i free) (today|tomorrow)", spoken)
    if m:
        return _calendar_day(m.group(1), current)
    m = _match(r"(?:what(?:'s| is) on|show|list|check) my (?:calendar|schedule|appointments) (?:for |over )?the next (\d{1,2}) days", spoken)
    if m and 1 <= int(m.group(1)) <= 30:
        return _tool("calendar.range", "calendar.query", direction="future", days=int(m.group(1)), limit=20)
    m = _match(r"(?:show|list|find) my (?:calendar events|appointments|meetings) (?:about|containing|for) (.{2,160})", spoken)
    if m:
        return _tool("calendar.search", "calendar.query", direction="future", days=90, limit=20, query=m.group(1).strip())
    m = _match(r"(?:show|list|find) my (?:past|previous) (?:calendar events|appointments|meetings)(?: from the last (\d{1,3}) days)?", spoken)
    if m:
        days = int(m.group(1)) if m.group(1) else 30
        if 1 <= days <= 365:
            return _tool("calendar.past", "calendar.query", direction="past", days=days, limit=20)

    m = _match(r"(?:search|find|look up) (?:in )?my (?:gmail|inbox|emails|email) (?:for|about|containing) (.{2,240})", spoken)
    if m:
        return _tool("gmail.search", "gmail.query", query=m.group(1).strip(), limit=10)
    email = r"[A-Za-z0-9.!#$%&'*+/=?^_{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    m = _match(r"(?:show|find|list|read) (?:emails|email|messages) from (" + email + r")", spoken)
    if m:
        return _tool("gmail.sender", "gmail.query", query="from:" + m.group(1), limit=10)
    m = _match(r"(?:show|list|find) (?:my )?(?:unread )?(?:emails|email|messages) (?:about|with subject|containing) (.{2,160})", spoken)
    if m:
        return _tool("gmail.search", "gmail.query", query=m.group(1).strip(), limit=10)

    m = _match(r"(?:find|search) (?:in )?(?:my )?(?:local records|notes|knowledge|memory|all my data) (?:for|about|containing) (.{2,220})", spoken)
    if m:
        return _tool("knowledge", "knowledge.search", query=m.group(1).strip(), limit=7)
    m = _match(r"(?:find|search) (?:across )?(?:my )?(?:emails and calendar|email and calendar|email, calendar and notes) (?:for|about) (.{2,220})", spoken)
    if m:
        return _tool("knowledge", "knowledge.search", query=m.group(1).strip(), limit=7)

    m = _match(r"(?:show|check|find|status of) background task #?(\d{1,8})", spoken)
    if m:
        return _tool("background", "background.status", task_id=int(m.group(1)))
    m = _match(r"(?:stop|cancel) (?:scheduled )?reminder #?(\d{1,8})", spoken)
    if m:
        return _tool("jobs", "jobs.cancel", job_id=int(m.group(1)))
    m = _match(r"(?:stop|cancel) background (?:task|job) #?(\d{1,8})", spoken)
    if m:
        return _tool("background", "background.cancel", task_id=int(m.group(1)))

    m = _match(r"(?:start|begin) (?:taking |recording )?meeting notes(?: for (.{2,120}))?", spoken)
    if m:
        return _tool("meeting", "meeting.start", title=(m.group(1) or "").strip())
    m = _match(r"(?:stop|finish|end) (?:meeting notes|meeting note session) #?(\d{1,8})", spoken)
    if m:
        return _tool("meeting", "meeting.finish", meeting_id=int(m.group(1)))

    m = _match(r"(?:check|show|find) (?:browser )?tab (?:named |called |for )?(.{2,120})", spoken)
    if m:
        return _tool("browser", "browser.tab_status", query=m.group(1).strip())
    m = _match(r"(?:switch to|focus|select) (?:the )?(?:browser )?tab (?:named |called |for )?(.{2,120})", spoken)
    if m:
        return _tool("browser", "browser.focus_tab", query=m.group(1).strip())
    m = _match(r"(?:close|quit) (?:the )?(?:browser )?tab (?:named |called |for )?(.{2,120})", spoken)
    if m:
        return _tool("browser", "browser.close_tab", query=m.group(1).strip())
    m = _match(r"(?:open|go to|visit) (https?://[^\s]{4,300}|www\.[^\s]{4,300})", spoken)
    if m:
        return _tool("pc", "pc.open_url", url=m.group(1).strip())
    m = _match(r"(?:open|launch|start) (?:the )?app (?:named |called )?(.{2,100})", spoken)
    if m:
        return _tool("pc", "pc.launch_app", name=m.group(1).strip())
    m = _match(r"(?:close|quit) (?:the )?app (?:named |called )?(.{2,100})", spoken)
    if m:
        return _tool("pc", "pc.close_app", name=m.group(1).strip())
    m = _match(r"(?:is|check whether) (?:the )?app (?:named |called )?(.{2,100}) (?:running|open)", spoken)
    if m:
        return _tool("pc", "pc.app_status", name=m.group(1).strip())

    m = _match(r"(?:run|execute) (?:a )?web search (?:for|about) (.{2,240})", spoken)
    if m:
        return _tool("web", "web.search", query=m.group(1).strip(), num=5)
    m = _match(r"(?:look up|search online for|search the internet for) (.{2,240})", spoken)
    if m:
        return _tool("web", "web.search", query=m.group(1).strip(), num=5)
    m = _match(r"(?:show|list) (?:my )?(?:last|recent) (\d{1,2}) expenses", spoken)
    if m and 1 <= int(m.group(1)) <= 30:
        return _tool("expenses", "expense.list", limit=int(m.group(1)))
    m = _match(r"(?:show|list) (?:my )?(?:last|recent) (\d{1,2}) meetings", spoken)
    if m and 1 <= int(m.group(1)) <= 30:
        return _tool("meeting", "meeting.list", limit=int(m.group(1)))

    # Recurrence first: never turn "every day" into a one-time reminder.
    m = _match(r"(?:remind me )?every (day|weekday|week|monday through friday) at (.{2,55}?) to (.{2,300})", spoken)
    if m:
        rec = ("weekdays" if m.group(1).lower() in {"weekday", "monday through friday"}
               else "weekly" if m.group(1).lower() == "week" else "daily")
        return _tool("reminder.recurring", "jobs.create_recurring",
                     recurrence=rec, when=m.group(2).strip(), command=m.group(3).strip())
    m = _match(r"(?:remind me|set a reminder) (?:to )?(.{2,300}?) (?:on |at )(.{2,90})", spoken)
    if m:
        return _tool("reminder.once", "jobs.create_time", command=m.group(1).strip(), when=m.group(2).strip())

    m = _match(r"(?:send|write and send) (?:an? )?email to (" + email + r") (?:saying|with body) (.{2,1000})", raw)
    if m:
        # Existing gmail.send external-write approval is still mandatory.
        return _tool("email.send", "gmail.send", recipient=m.group(1), body=m.group(2).strip())
    m = _match(r"(?:add|create) calendar event: (.{2,140}) \| (\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?:[+-]\d\d:\d\d|Z)?) \| (\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?:[+-]\d\d:\d\d|Z)?)", raw)
    if m:
        return _tool("calendar.create", "calendar.create", summary=m.group(1).strip(),
                     start=m.group(2).replace(" ", "T"), end=m.group(3).replace(" ", "T"))
    m = _match(r"(?:show|list|trace) (?:the )?(?:chronos|world) (?:history|timeline|trace) (?:for|of) (.{2,180})", spoken)
    if m:
        return _tool("chronos", "chronos.trace", entity=m.group(1).strip(), limit=20)
    return None
