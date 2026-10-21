"""Truthful Callless session state machine (pure logic, no I/O).

States::

    requested -> ringing   (receiver grant/ask: receiver must accept)
              -> authorized (receiver grant/open and receiver's client armed)
    ringing   -> authorized (receiver accepted)
    authorized -> signaling (first SDP/ICE message relayed through the hub)
    signaling  -> media_connected (BOTH clients attest live audio)
    media_connected -> signaling (a client reports media lost; may recover)
    any live state -> ended(reason) | failed(reason)

WebSocket signaling being established is NOT live audio. ``media_connected``
is reached only when both participants have separately reported, after their
own RTCPeerConnection reached 'connected' and an inbound audio track was
actually receiving packets. The hub cannot verify those client attestations;
it only refuses to infer connection from signaling.

Only metadata (state, reason, timestamps) is kept. No SDP, ICE or audio.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

LIVE_STATES = ("requested", "ringing", "authorized", "signaling", "media_connected")
TERMINAL_STATES = ("ended", "failed")

# Reasons a client may assert for its own hangup.
CLIENT_REASONS = frozenset({"hangup", "network", "media", "error"})
# Reasons that mean "it did not work" (state "failed") when audio was never live.
FAILURE_REASONS = frozenset({"network", "media", "timeout", "error"})

RING_TIMEOUT_SECONDS = 60.0
MEDIA_TIMEOUT_SECONDS = 30.0
MAX_SESSION_SECONDS = 4 * 3600


@dataclass
class Session:
    sid: str
    caller: int
    callee: int
    access: str                      # "open" | "ask": how the receiver authorized it
    state: str = "requested"
    created: float = field(default_factory=time.monotonic)      # request time
    created_wall: float = field(default_factory=time.time)
    marks: dict[str, float] = field(default_factory=dict)       # state -> monotonic
    media: dict[int, bool] = field(default_factory=dict)        # user -> attested live audio
    muted: dict[int, bool] = field(default_factory=dict)
    ever_connected: bool = False
    reason: str = ""
    watchdog: object | None = None

    def __post_init__(self):
        self.marks["requested"] = self.created

    # -- queries ---------------------------------------------------------
    def participants(self) -> tuple[int, int]:
        return self.caller, self.callee

    def peer_of(self, user_id: int) -> int:
        return self.callee if user_id == self.caller else self.caller

    def live(self) -> bool:
        return self.state in LIVE_STATES

    def elapsed_ms(self, mark: str) -> int | None:
        at = self.marks.get(mark)
        return None if at is None else int(round((at - self.created) * 1000))

    @property
    def connect_ms(self) -> int | None:
        """Request -> media_connected, measured on the hub's monotonic clock."""
        return self.elapsed_ms("media_connected_first")

    # -- transitions -----------------------------------------------------
    def advance(self, state: str) -> bool:
        allowed = {
            "requested": {"ringing", "authorized"},
            "ringing": {"authorized"},
            "authorized": {"signaling"},
            "signaling": {"media_connected"},
            "media_connected": {"signaling"},
        }
        if state not in allowed.get(self.state, ()):
            return False
        self.state = state
        self.marks[state] = time.monotonic()
        if state == "media_connected" and "media_connected_first" not in self.marks:
            self.marks["media_connected_first"] = self.marks[state]
            self.ever_connected = True
        return True

    def report_media(self, user_id: int, live: bool) -> str | None:
        """Record one participant's attestation. Returns the new state if it changed."""
        if user_id not in self.participants() or self.state not in ("signaling", "media_connected"):
            return None
        self.media[user_id] = bool(live)
        both = all(self.media.get(uid) for uid in self.participants())
        if both and self.state == "signaling":
            return "media_connected" if self.advance("media_connected") else None
        if not both and self.state == "media_connected":
            return "signaling" if self.advance("signaling") else None
        return None

    def terminal_state(self, reason: str) -> str:
        if reason in FAILURE_REASONS and not self.ever_connected:
            return "failed"
        return "ended"

    def finish(self, reason: str) -> str:
        """Move to a terminal state (idempotent). Returns the terminal state."""
        if not self.live():
            return self.state
        self.state = self.terminal_state(reason)
        self.marks[self.state] = time.monotonic()
        self.reason = reason
        return self.state

    def duration_ms(self) -> int | None:
        """Media-connected -> end, or None when audio was never live."""
        first = self.marks.get("media_connected_first")
        end = self.marks.get(self.state) if self.state in TERMINAL_STATES else None
        if first is None or end is None:
            return None
        return int(round((end - first) * 1000))

    def snapshot(self) -> dict:
        return {"state": self.state, "reason": self.reason or None,
                "connect_ms": self.connect_ms,
                "authorized_ms": self.elapsed_ms("authorized"),
                "muted": {str(uid): bool(v) for uid, v in self.muted.items()}}
