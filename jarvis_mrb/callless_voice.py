"""Voice-turn handler for Callless ("get me to Alex", "end the Callless conversation").

Honesty boundary: the Horus backend is not a Callless media endpoint. The
microphone, WebRTC peer connection and the "both sides report live audio"
evidence live in the user's Callless browser tab. This handler therefore never
says a conversation is connected. It can only:

* resolve a spoken name against the approved contacts of the Callless account
  this backend is linked to (``CALLLESS_LOCAL_HANDLE``), and say whether that
  contact looks reachable, always telling the user that audio must be
  confirmed in the Callless client; and
* end a live Callless session for the linked account (a real hub action,
  confirmed by the hub before it speaks).

Without a linked account the answer says the iPhone app opens Callless and
media must be confirmed there. "get me to <place>" is left alone unless the
user says "Callless" or the name matches a linked contact.
"""
from __future__ import annotations

import os
import re

LOCAL_HANDLE_ENV = "CALLLESS_LOCAL_HANDLE"

_CONNECT = re.compile(
    r"^(?:(?:hey|ok|okay)[, ]+)?(?:horus[, ]+)?(?:please[, ]+)?"
    r"(?:get me to|get me through to|connect me to|connect me with|put me through to|"
    r"callless with|callless)\s+(.+?)\s*[.?!]*$", re.IGNORECASE)
_END = re.compile(
    r"^(?:(?:hey|ok|okay)[, ]+)?(?:horus[, ]+)?(?:please[, ]+)?"
    r"(?:(?:end|stop|close|disconnect|leave)\s+(?:the\s+|my\s+)?callless"
    r"(?:\s+(?:conversation|session|connection|call))?|hang up (?:the\s+)?callless"
    r"(?:\s+(?:conversation|session|connection|call))?)\s*[.?!]*$", re.IGNORECASE)
_TRAILING_VIA = re.compile(r"\s+(?:on|via|using|through|with|in)\s+callless$", re.IGNORECASE)

NO_IDENTITY = ("The iPhone app opens Callless for that. Audio only counts as connected once Callless "
               "itself confirms both sides can hear each other, and I can't confirm that from here.")
_CONFIRM = ("Open Callless on your phone and tap Connect. I can't start or confirm audio from here; "
            "Callless will tell you when both sides' audio is actually live.")


def _local_account(api):
    handle = os.environ.get(LOCAL_HANDLE_ENV, "").strip().lower()
    if not handle:
        return None, False
    return api.store.lookup(handle), True


def handle(text: str, turn=None) -> str | None:
    from jarvis_mrb import callless_api as api

    spoken_text = " ".join(str(text or "").split())
    mentions = "callless" in spoken_text.lower()

    if _END.match(spoken_text):
        local, configured = _local_account(api)
        if not configured or local is None:
            return ("I can't end a Callless conversation from here because this backend isn't linked to "
                    "your Callless account. Use Disconnect in the Callless client.")
        outcome = api.request_end_for_user(local["id"], "hangup")
        if outcome == "none":
            return "There is no live Callless conversation for your account on this hub."
        if outcome == "ended":
            return "I ended your Callless conversation. Both sides are shown that it ended."
        if outcome == "scheduled":
            return "I've asked the hub to end your Callless conversation."
        return "I couldn't reach the Callless hub to end it. Use Disconnect in the Callless client."

    match = _CONNECT.match(spoken_text)
    if not match:
        return None
    name = _TRAILING_VIA.sub("", match.group(1)).strip()
    name = re.sub(r"^(?:@)", "", name)
    if not name:
        return None

    local, configured = _local_account(api)
    if not configured:
        return NO_IDENTITY if mentions else None
    if local is None:
        return ("The Callless account this backend is linked to doesn't exist on this hub. " + NO_IDENTITY
                ) if mentions else None

    matches = api.store.resolve_contact(local["id"], name)
    if not matches:
        return (f"I don't have an approved Callless contact called {name}.") if mentions else None
    if len(matches) > 1:
        options = ", ".join("@" + item["handle"] for item in matches[:4])
        return f"More than one Callless contact matches {name}: {options}. Say the handle."
    peer = matches[0]
    label = peer["name"] or peer["handle"]
    # Closed grants, blocks and offline contacts are deliberately indistinguishable.
    reachable = (peer["id"] in api.connections
                 and api.store.effective_access(local["id"], peer["id"]) != "closed")
    if not reachable:
        return f"{label} isn't reachable on Callless right now."
    if local["id"] not in api.connections:
        return f"{label} looks reachable, but your own Callless client isn't connected. {_CONFIRM}"
    return f"{label} looks reachable on Callless. {_CONFIRM}"


def _register() -> None:
    try:
        from jarvis_mrb import voice_router
    except ImportError:
        return   # voice router not present in this build; handle() remains callable
    voice_router.register("callless", handle)


_register()
