"""Local/Ollama or BYOK model transport. Secrets are never written to settings JSON.

Hosted model calls may transmit prompts and conversation context to the chosen
provider; the local deterministic permission / tool-execution gates remain in Horus.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterator

import httpx

from jarvis_mrb.server_config import APP_DIR

SETTINGS_PATH = APP_DIR / "inference.json"
PROVIDERS = {
    "ollama": "",
    "openai": "https://api.openai.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
}
DEFAULT_MODELS = {
    "openai": "gpt-5.5",
    "openrouter": "openai/gpt-5.5",
    "anthropic": "claude-sonnet-4-5",
}
_LOCK = threading.RLock()
_KEY_SERVICE = "Horus BYOK"


class ProviderError(RuntimeError):
    pass


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError as exc:
        raise ProviderError("The system credential-store dependency is missing.") from exc


def _credential(provider: str) -> str:
    try:
        value = _keyring().get_password(_KEY_SERVICE, provider)
    except Exception as exc:
        raise ProviderError("The operating-system credential store is unavailable.") from exc
    return (value or "").strip()


def get_inference_config() -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        obj = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            data = obj
    except (OSError, ValueError):
        pass
    provider = str(data.get("provider") or "ollama")
    if provider not in PROVIDERS:
        provider = "ollama"
    if provider == "ollama":
        from jarvis_mrb.planner_model import get_planner_model
        model = get_planner_model()
    else:
        model = str(data.get("model") or DEFAULT_MODELS[provider])
    return {"provider": provider, "model": model}


def inference_status() -> dict[str, Any]:
    config = get_inference_config()
    provider = config["provider"]
    try:
        has_key = bool(_credential(provider)) if provider != "ollama" else True
    except ProviderError:
        has_key = False
    return {
        **config,
        "key_configured": has_key,
        "providers": list(PROVIDERS),
        "local": provider == "ollama",
    }


def configure_inference(provider: str, model: str = "", api_key: str | None = None) -> dict[str, Any]:
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider.")
    model = model.strip() or DEFAULT_MODELS.get(provider) or ""
    if provider == "ollama":
        from jarvis_mrb.planner_model import SUPPORTED_MODELS, get_planner_model, set_planner_model
        model = model or get_planner_model()
        if model not in SUPPORTED_MODELS:
            raise ValueError("Select a supported local Ollama planner model.")
    if provider != "ollama" and not re.fullmatch(r"[A-Za-z0-9_./:+-]{2,100}", model):
        raise ValueError("Invalid model identifier.")
    if api_key is not None:
        if provider == "ollama":
            raise ValueError("Local Ollama does not accept an API key.")
        if not api_key.strip() or len(api_key) > 512 or any(c.isspace() for c in api_key):
            raise ValueError("Invalid API key.")
    with _LOCK:
        # Ensure that secret storage works BEFORE saving a new hosted provider.
        if api_key is not None:
            try:
                _keyring().set_password(_KEY_SERVICE, provider, api_key.strip())
            except Exception as exc:
                raise ProviderError("Cannot save the API key in the operating-system credential store.") from exc
        elif provider != "ollama" and not _credential(provider):
            raise ValueError("Enter an API key for this provider first.")
        if provider == "ollama":
            set_planner_model(model)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps({"provider": provider, "model": model}, indent=2), encoding="utf-8")
        os.replace(temporary, SETTINGS_PATH)
    return inference_status()


def _message_parts(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    history = [{"role": m["role"], "content": m["content"]}
               for m in messages if m["role"] in {"user", "assistant"}]
    return system, history


def _invoke(messages: list[dict[str, str]], *, max_tokens: int = 2500) -> str:
    config = get_inference_config()
    provider = config["provider"]
    if provider == "ollama":
        raise ProviderError("Hosted inference was not selected.")
    key = _credential(provider)
    if not key:
        raise ProviderError("No API key has been saved for this provider.")
    if provider == "anthropic":
        system, history = _message_parts(messages)
        payload: dict[str, Any] = {
            "model": config["model"], "max_tokens": max_tokens,
            "system": system, "messages": history,
        }
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        payload = {
            "model": config["model"],
            "messages": messages,
            "max_completion_tokens" if provider == "openai" else "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {key}"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/US0RIS/Jarvis-for-MRB"
            headers["X-Title"] = "Horus"
    try:
        with httpx.Client(timeout=httpx.Timeout(90.0, connect=8.0), follow_redirects=False) as client:
            response = client.post(PROVIDERS[provider], json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise ProviderError(f"{provider} returned HTTP {exc.response.status_code}; check the model, API key, and provider balance.") from None
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError(f"Unable to reach {provider} or parse its response.") from exc

    try:
        if provider == "anthropic":
            return "".join(str(p.get("text", "")) for p in data["content"] if p.get("type") == "text").strip()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(str(p.get("text", "")) for p in content if isinstance(p, dict)).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProviderError(f"{provider} returned an unsupported reply format.") from exc
    raise ProviderError(f"{provider} returned no text.")


def plan_with_provider(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Request one JSON plan; parsing cannot itself grant action authority."""
    content = _invoke(messages)
    # Some providers wrap an otherwise valid JSON object in markdown fences.
    content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content, flags=re.I)
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ProviderError("Provider did not return a valid JSON planner object.") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("Provider planner response must be an object.")
    return parsed


def answer_with_provider(messages: list[dict[str, str]]) -> str:
    return _invoke(messages)
