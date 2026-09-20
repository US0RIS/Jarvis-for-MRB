from __future__ import annotations

"""Conservative model-free gate for *conversational routing*, not opinions.

These utterances ask for a perspective on ideas already in the conversation.
They do not need the JSON tool-planner protocol. This gate does NOT compose
the opinion: the conversational model does, using the actual recent exchange.

Do not broaden this into a general "what do you think of X" matcher: X may be
a live stock price, private email, professional question or unknown product
whose answer requires evidence or authorized source access.
"""

import re


_PREFIX = r"(?:(?:okay|ok|well|honestly|actually|so)[, ]+)*"
_DEICTIC_TOPIC = (
    r"(?:this|that|these|those|our) "
    r"(?:idea|ideas|plan|plans|design|designs|approach|approaches|"
    r"option|options|proposal|proposals|project|projects)"
)
_OPINION = (
    r"(?:what do you think|what(?:'s| is) your take|"
    r"what(?:'s| is) your opinion|your thoughts)"
)
_PATTERNS = (
    _PREFIX + _OPINION + r"(?: (?:about|of|on) (?:" + _DEICTIC_TOPIC + r"|this|that))?",
    _PREFIX + r"which (?:of )?(?:these|those|our) "
    r"(?:ideas|plans|designs|approaches|options|proposals) "
    r"(?:would you (?:choose|pick|prefer)|do you prefer)",
    _PREFIX + r"do you (?:like|prefer) (?:this|that) "
    r"(?:idea|plan|design|approach|option|proposal)",
    _PREFIX + r"(?:would you|do you) (?:go with|choose|pick) "
    r"(?:this|that) (?:idea|plan|design|approach|option|proposal)",
)
_COMPILED = tuple(re.compile(r"^(?:" + pattern + r")$", re.IGNORECASE) for pattern in _PATTERNS)


def is_explicit_in_context_opinion(text: str) -> bool:
    """True only for a standalone request for a take on supplied ideas."""
    if not isinstance(text, str) or len(text) > 240 or "\n" in text:
        return False
    normalized = re.sub(r"\s+", " ", text.strip()).rstrip("?.!").strip()
    if not normalized:
        return False
    return any(pattern.fullmatch(normalized) is not None for pattern in _COMPILED)
