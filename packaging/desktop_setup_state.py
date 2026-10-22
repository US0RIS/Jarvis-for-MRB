"""Truthful setup progress for Horus's Windows/phone/AirPods workflow.

One authenticated iPhone request is not proof of AirPods pairing. Likewise,
an open backend port is not evidence of a working model or an audio route.
This module is intentionally independent of Qt so it can be regression-tested.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SetupState:
    engine_online: bool
    provider_configured: bool
    lan_ready: bool
    phone_recent: bool
    audio_user_confirmed: bool
    provider: str
    model: str

    @property
    def checks(self) -> tuple[bool, ...]:
        return (
            self.engine_online,
            self.provider_configured,
            self.lan_ready,
            self.phone_recent,
            self.audio_user_confirmed,
        )

    @property
    def completed(self) -> int:
        return sum(self.checks)

    @property
    def next_step(self) -> int | None:
        return next((i for i, done in enumerate(self.checks) if not done), None)


def derive_setup_state(data: dict[str, Any] | None, inference: dict[str, Any],
                       bind_host: str, token_set: bool,
                       user_confirmed_audio: bool) -> SetupState:
    info = data or {}
    health = info.get("health") if isinstance(info.get("health"), dict) else {}
    online = bool(info.get("online"))
    remote = info.get("phone") if isinstance(info.get("phone"), dict) else {}
    # A local model selection requires a separate actual response test. An
    # API key's presence is configuration, not verified model capability.
    provider = str(inference.get("provider") or "unknown")
    model = str(inference.get("model") or "")
    configured = bool(model) and (
        provider == "ollama" or
        (provider in {"openai", "anthropic", "openrouter"} and
         bool(inference.get("key_configured")))
    )
    config_bind = bind_host not in {"127.0.0.1", "localhost", "::1", ""}
    # The service must actually be running on its LAN bind, rather than merely
    # having a saved config awaiting restart.
    actual_bind = str(health.get("bind") or "")
    effective_bind = actual_bind not in {"127.0.0.1", "localhost", "::1", ""}
    lan = online and config_bind and bool(token_set) and effective_bind
    return SetupState(
        engine_online=online,
        provider_configured=configured,
        lan_ready=lan,
        phone_recent=lan and bool(remote.get("recent_authenticated_app_checkin")),
        audio_user_confirmed=bool(user_confirmed_audio),
        provider=provider,
        model=model,
    )
