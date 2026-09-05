from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "JarvisForMRB"
DB_PATH = APP_DIR / "conversation.sqlite3"
DEFAULT_HISTORY_MESSAGES = 20
MAX_STORED_MESSAGES_PER_SESSION = 200

# Older conversation remains durable, but it should not be placed in every prompt.
# Small local models are especially prone to "topic gravity": when current speech is
# imperfect or underspecified, an old concrete topic can become the model's default
# interpretation. Jarvis therefore supplies only the immediately preceding exchange
# unless the user explicitly signals that an older turn matters.
_EXTENDED_CONTEXT_PATTERNS = (
    r"\bremember\b",
    r"\brecall\b",
    r"\bearlier\b",
    r"\bprevious(?:ly)?\b",
    r"\bbefore\b",
    r"\blast time\b",
    r"\bback to\b",
    r"\bgo back to\b",
    r"\b(?:a|the) few (?:turns|prompts|messages) ago\b",
    r"\b\d+ (?:turns|prompts|messages) ago\b",
    r"\b(?:you|we|i) (?:said|mentioned|told|discussed|talked|looked|worked)\b",
    r"\bwhat (?:did|was|were) (?:you|we|i)\b",
    r"\b(?:first|second|third|fourth|fifth|other|former|latter) (?:one|thing|option|idea|point)\b",
    r"\bthe one (?:you|we|i)\b",
    r"\bwhich one (?:did|was|were)\b",
)


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str


def _connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_session_id_id ON conversation_messages(session_id, id)"
    )
    conn.commit()
    return conn


def _clean_session_id(session_id: str | None) -> str:
    value = (session_id or "default").strip()
    return value[:128] or "default"


def append_message(session_id: str | None, role: str, content: str) -> None:
    role = role.strip().lower()
    if role not in {"user", "assistant"}:
        raise ValueError(f"Unsupported conversation role: {role}")
    text = content.strip()
    if not text:
        return
    sid = _clean_session_id(session_id)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversation_messages(session_id, role, content, created_at) VALUES(?,?,?,?)",
            (sid, role, text[:12000], datetime.now().astimezone().isoformat()),
        )
        # Keep enough durable history for continuity without letting the database
        # grow forever. The model only receives a selected recent window.
        conn.execute(
            """
            DELETE FROM conversation_messages
            WHERE session_id=? AND id NOT IN (
                SELECT id FROM conversation_messages
                WHERE session_id=? ORDER BY id DESC LIMIT ?
            )
            """,
            (sid, sid, MAX_STORED_MESSAGES_PER_SESSION),
        )
        conn.commit()


def recent_messages(
    session_id: str | None,
    limit: int = DEFAULT_HISTORY_MESSAGES,
) -> list[ConversationMessage]:
    sid = _clean_session_id(session_id)
    safe_limit = max(0, min(int(limit), 100))
    if safe_limit == 0:
        return []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM conversation_messages
            WHERE session_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (sid, safe_limit),
        ).fetchall()
    return [
        ConversationMessage(role=str(row["role"]), content=str(row["content"]))
        for row in reversed(rows)
    ]


def requests_extended_context(query: str) -> bool:
    """Return true only when the current wording explicitly reaches farther back.

    Ordinary follow-ups still receive the immediately preceding user/assistant
    exchange, which is enough for pronouns such as "it" or "that". Wider history is
    reserved for explicit historical references, preventing an unrelated older topic
    from becoming the fallback interpretation of a noisy speech transcript.
    """
    normalized = " ".join((query or "").lower().split())
    if not normalized:
        return False
    return any(re.search(pattern, normalized) for pattern in _EXTENDED_CONTEXT_PATTERNS)


def contextual_messages(
    session_id: str | None,
    query: str,
    *,
    immediate_limit: int = 2,
    extended_limit: int = 12,
) -> list[ConversationMessage]:
    limit = extended_limit if requests_extended_context(query) else immediate_limit
    return recent_messages(session_id, limit=limit)


def clear_session(session_id: str | None) -> None:
    sid = _clean_session_id(session_id)
    with _connect() as conn:
        conn.execute("DELETE FROM conversation_messages WHERE session_id=?", (sid,))
        conn.commit()
