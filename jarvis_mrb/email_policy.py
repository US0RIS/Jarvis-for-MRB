from __future__ import annotations

import json
import os
import re
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
POLICY_PATH = APP_DIR / "email_policy.json"

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(address: str) -> str:
    return address.strip().lower()


def _valid_email(address: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(normalize_email(address)))


def get_allowed_recipients() -> list[str]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not POLICY_PATH.exists():
        return []
    try:
        payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    raw = payload.get("allowed_recipients", []) if isinstance(payload, dict) else []
    if not isinstance(raw, list):
        return []

    values = {normalize_email(str(item)) for item in raw if _valid_email(str(item))}
    return sorted(values)


def set_allowed_recipients(addresses: list[str]) -> list[str]:
    normalized: set[str] = set()
    invalid: list[str] = []
    for item in addresses:
        value = normalize_email(str(item))
        if not value:
            continue
        if not _valid_email(value):
            invalid.append(value)
            continue
        normalized.add(value)

    if invalid:
        raise ValueError("Invalid email address(es): " + ", ".join(invalid))

    APP_DIR.mkdir(parents=True, exist_ok=True)
    result = sorted(normalized)
    POLICY_PATH.write_text(
        json.dumps({"allowed_recipients": result}, indent=2),
        encoding="utf-8",
    )
    return result


def recipient_is_allowed(address: str) -> bool:
    # An empty allowlist is intentionally fail-closed. Voice recognition and an
    # accidental confirmation must never be able to create a new recipient.
    return normalize_email(address) in set(get_allowed_recipients())


def blocked_recipient_message(address: str) -> str:
    return (
        f"Email to {normalize_email(address)} was blocked because that address is not "
        "on Jarvis's allowed-recipient list. Add it in the Jarvis iPhone app settings first."
    )
