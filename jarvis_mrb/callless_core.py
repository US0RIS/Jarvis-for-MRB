"""Callless identity and contact authorization for a single self-hosted hub.

No conversation audio, SDP, or ICE candidates are retained in SQLite. Only
session metadata (who, when, final state/reason, measured connect time) is
logged, for the per-user recent-sessions view, and pruned after 30 days.
All mutating operations use the hub's own per-user bearer identity, not the
Horus PC administrator token.

Authorization model (directional)::

    effective(caller -> callee) = most restrictive of
        (a) the callee's PER-CONTACT grant to that caller (open | ask | closed)
        (b) the callee's GLOBAL status (open | ask | closed)
    and "closed" whenever the contact link is missing or either side blocks.

closed < ask < open. A global "open" never upgrades a per-contact "ask":
immediate access must be knowingly granted per contact. A global "ask" or
"closed" caps every per-contact grant. Grants are directional: A letting B in
says nothing about B letting A in. New and migrated contacts start at "ask".
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import hmac
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from jarvis_mrb.server_config import APP_DIR

HANDLE = re.compile(r"^[a-z][a-z0-9_]{2,27}$")
STATUSES = {"open", "ask", "closed"}
RANK = {"closed": 0, "ask": 1, "open": 2}
SESSION_LOG_DAYS = 30
SESSION_LOG_MAX_PER_USER = 200
TTL_SECONDS = 30 * 24 * 3600
INVITE_SECONDS = 15 * 60


class CalllessError(ValueError):
    pass


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CalllessStore:
    def __init__(self, path: Path | None = None):
        self.path = path or APP_DIR / "callless.sqlite3"
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'closed',
                    created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires REAL NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS auth_expiry ON auth(expires);
                CREATE TABLE IF NOT EXISTS invites (
                    code_hash TEXT PRIMARY KEY,
                    issuer INTEGER NOT NULL,
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    user_id INTEGER NOT NULL,
                    peer_id INTEGER NOT NULL,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, peer_id)
                );
                CREATE TABLE IF NOT EXISTS session_log (
                    sid TEXT PRIMARY KEY,
                    caller_id INTEGER NOT NULL,
                    callee_id INTEGER NOT NULL,
                    access TEXT NOT NULL,
                    requested REAL NOT NULL,
                    state TEXT NOT NULL,
                    reason TEXT,
                    authorized_ms INTEGER,
                    connect_ms INTEGER,
                    duration_ms INTEGER
                );
                CREATE INDEX IF NOT EXISTS session_log_caller ON session_log(caller_id, requested);
                CREATE INDEX IF NOT EXISTS session_log_callee ON session_log(callee_id, requested);
            """)
            self._migrate(db)

    @staticmethod
    def _migrate(db: sqlite3.Connection) -> None:
        """Additive, idempotent migrations for databases created by older versions."""
        columns = {row["name"] for row in db.execute("PRAGMA table_info(contacts)")}
        if "grant_level" not in columns:
            # grant_level: what contacts.user_id lets contacts.peer_id do when
            # the peer requests them. Existing contacts become "ask" in BOTH
            # directions: a migration never silently grants immediate access.
            db.execute("ALTER TABLE contacts ADD COLUMN grant_level TEXT NOT NULL DEFAULT 'ask'")

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def public(row: sqlite3.Row) -> dict:
        return {"id": row["id"], "handle": row["handle"],
                "name": row["name"], "status": row["status"]}

    @staticmethod
    def _pass_hash(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 320_000).hex()

    def _issue_token(self, db: sqlite3.Connection, user_id: int) -> str:
        raw = secrets.token_urlsafe(32)
        db.execute("INSERT INTO auth(token_hash,user_id,expires) VALUES(?,?,?)",
                   (_sha(raw), user_id, time.time() + TTL_SECONDS))
        return raw

    def register(self, handle: str, name: str, password: str) -> tuple[dict, str]:
        handle = handle.strip().lower()
        name = name.strip()
        if not HANDLE.fullmatch(handle) or not 1 <= len(name) <= 70:
            raise CalllessError("Choose a handle of 3–28 lowercase letters/numbers/underscores and a display name.")
        if not 12 <= len(password) <= 256:
            raise CalllessError("Use a password between 12 and 256 characters.")
        salt = secrets.token_hex(16)
        digest = self._pass_hash(password, salt)
        with self.lock, self._db() as db:
            try:
                db.execute("INSERT INTO users(handle,name,salt,password_hash,created) VALUES(?,?,?,?,?)",
                           (handle, name, salt, digest, time.time()))
                row = db.execute("SELECT * FROM users WHERE handle=?", (handle,)).fetchone()
                token = self._issue_token(db, row["id"])
                db.commit()
            except sqlite3.IntegrityError as exc:
                raise CalllessError("That handle is already taken.") from exc
        return self.public(row), token

    def login(self, handle: str, password: str) -> tuple[dict, str]:
        handle = handle.strip().lower()
        with self.lock, self._db() as db:
            row = db.execute("SELECT * FROM users WHERE handle=?", (handle,)).fetchone()
            # Perform an expensive comparison even for a non-existent handle.
            salt = row["salt"] if row else "00" * 16
            expected = row["password_hash"] if row else "00" * 32
            if not hmac.compare_digest(self._pass_hash(password, salt), expected) or row is None:
                raise CalllessError("Invalid handle or password.")
            token = self._issue_token(db, row["id"])
            db.commit()
        return self.public(row), token

    def authenticate(self, token: str) -> dict | None:
        if not token or len(token) > 256:
            return None
        with self.lock, self._db() as db:
            row = db.execute("""
                SELECT users.* FROM auth JOIN users ON auth.user_id=users.id
                WHERE auth.token_hash=? AND auth.expires>?
            """, (_sha(token), time.time())).fetchone()
        return self.public(row) if row else None

    def logout(self, token: str) -> None:
        with self.lock, self._db() as db:
            db.execute("DELETE FROM auth WHERE token_hash=?", (_sha(token),))
            db.commit()

    def set_status(self, user_id: int, status: str) -> dict:
        if status not in STATUSES:
            raise CalllessError("Status must be open, ask, or closed.")
        with self.lock, self._db() as db:
            db.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            db.commit()
        if row is None:
            raise CalllessError("Account not found.")
        return self.public(row)

    def lookup(self, handle: str) -> dict | None:
        with self.lock, self._db() as db:
            row = db.execute("SELECT * FROM users WHERE handle=?", (handle.strip().lower(),)).fetchone()
        return self.public(row) if row else None

    def public_by_id(self, user_id: int) -> dict | None:
        with self.lock, self._db() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return self.public(row) if row else None

    def invitation(self, user_id: int) -> str:
        code = secrets.token_urlsafe(24)
        with self.lock, self._db() as db:
            db.execute("INSERT INTO invites(code_hash,issuer,expires) VALUES(?,?,?)",
                       (_sha(code), user_id, time.time() + INVITE_SECONDS))
            db.commit()
        return code

    def accept_invitation(self, user_id: int, code: str) -> dict:
        with self.lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            invite = db.execute("SELECT * FROM invites WHERE code_hash=? AND expires>?",
                                (_sha(code.strip()), time.time())).fetchone()
            if invite is None:
                raise CalllessError("Invitation is invalid, expired, or already used.")
            peer_id = invite["issuer"]
            if peer_id == user_id:
                raise CalllessError("You cannot add yourself.")
            blocked = db.execute("""SELECT 1 FROM contacts WHERE
                (user_id=? AND peer_id=? OR user_id=? AND peer_id=?) AND blocked=1
            """, (user_id, peer_id, peer_id, user_id)).fetchone()
            if blocked:
                raise CalllessError("A contact block prevents pairing.")
            db.execute("DELETE FROM invites WHERE code_hash=?", (_sha(code.strip()),))
            for a,b in ((user_id,peer_id),(peer_id,user_id)):
                # New contacts start at "ask" in both directions; "open" is
                # always a separate, explicit grant by the receiving person.
                db.execute("INSERT OR IGNORE INTO contacts(user_id,peer_id,grant_level) VALUES(?,?,'ask')", (a,b))
            row = db.execute("SELECT * FROM users WHERE id=?", (peer_id,)).fetchone()
            db.commit()
        return self.public(row)

    def contacts(self, user_id: int) -> list[dict]:
        with self.lock, self._db() as db:
            rows = db.execute("""
                SELECT u.*, c.blocked, c.grant_level FROM contacts c JOIN users u ON c.peer_id=u.id
                WHERE c.user_id=? ORDER BY u.handle
            """, (user_id,)).fetchall()
        # A contact's own global status and grant toward me are deliberately
        # not exposed: "closed" must be indistinguishable from "offline".
        return [{"id": row["id"], "handle": row["handle"], "name": row["name"],
                 "blocked": bool(row["blocked"]), "my_grant": row["grant_level"]} for row in rows]

    def permitted(self, user_id: int, peer_id: int) -> bool:
        with self.lock, self._db() as db:
            rows = db.execute("""SELECT user_id,blocked FROM contacts
                WHERE (user_id=? AND peer_id=?) OR (user_id=? AND peer_id=?)
            """, (user_id,peer_id,peer_id,user_id)).fetchall()
        return len(rows) == 2 and not any(row["blocked"] for row in rows)

    def block(self, user_id: int, peer_handle: str, blocked: bool = True) -> None:
        peer = self.lookup(peer_handle)
        if not peer:
            raise CalllessError("Contact not found.")
        with self.lock, self._db() as db:
            changed = db.execute("UPDATE contacts SET blocked=? WHERE user_id=? AND peer_id=?",
                                 (1 if blocked else 0, user_id, peer["id"]))
            if changed.rowcount == 0:
                raise CalllessError("Only approved contacts can be blocked.")
            db.commit()

    # -- directional grants ------------------------------------------------
    def set_grant(self, user_id: int, peer_handle: str, level: str) -> str:
        """Set what *user_id* lets *peer* do when the peer requests them."""
        if level not in STATUSES:
            raise CalllessError("Grant must be open, ask, or closed.")
        peer = self.lookup(peer_handle)
        if not peer:
            raise CalllessError("Contact not found.")
        with self.lock, self._db() as db:
            changed = db.execute("UPDATE contacts SET grant_level=? WHERE user_id=? AND peer_id=?",
                                 (level, user_id, peer["id"]))
            if changed.rowcount == 0:
                raise CalllessError("Only approved contacts can receive a grant.")
            db.commit()
        return level

    def grant_level(self, grantor_id: int, grantee_id: int) -> str:
        with self.lock, self._db() as db:
            row = db.execute("SELECT grant_level FROM contacts WHERE user_id=? AND peer_id=?",
                             (grantor_id, grantee_id)).fetchone()
        return row["grant_level"] if row and row["grant_level"] in STATUSES else "closed"

    def has_contact(self, user_id: int, peer_id: int) -> bool:
        """True when both contact rows exist and *user_id* has not blocked the peer."""
        with self.lock, self._db() as db:
            rows = db.execute("""SELECT user_id,blocked FROM contacts
                WHERE (user_id=? AND peer_id=?) OR (user_id=? AND peer_id=?)
            """, (user_id, peer_id, peer_id, user_id)).fetchall()
        mine = [row for row in rows if row["user_id"] == user_id]
        return len(rows) == 2 and bool(mine) and not mine[0]["blocked"]

    def effective_access(self, caller_id: int, callee_id: int) -> str:
        """What *caller* may do to *callee* right now. See module docstring."""
        if caller_id == callee_id or not self.permitted(caller_id, callee_id):
            return "closed"
        grant = self.grant_level(callee_id, caller_id)
        status = self.user_status(callee_id)
        return min(grant, status, key=lambda value: RANK[value])

    def user_status(self, user_id: int) -> str:
        with self.lock, self._db() as db:
            row = db.execute("SELECT status FROM users WHERE id=?", (user_id,)).fetchone()
        return row["status"] if row and row["status"] in STATUSES else "closed"

    def resolve_contact(self, user_id: int, spoken: str) -> list[dict]:
        """Unblocked contacts whose handle, display name or first name matches."""
        wanted = " ".join(spoken.strip().lower().lstrip("@").split())
        if not wanted:
            return []
        exact, partial = [], []
        for item in self.contacts(user_id):
            if item["blocked"]:
                continue
            name = " ".join(item["name"].lower().split())
            if wanted in (item["handle"], name) or wanted.replace(" ", "") == item["handle"]:
                exact.append(item)
            elif " " not in wanted and name.split()[:1] == [wanted]:
                partial.append(item)   # first-name match
        return exact or partial

    # -- session metadata log (no SDP / ICE / audio) -----------------------
    def log_session(self, entry: dict) -> None:
        with self.lock, self._db() as db:
            db.execute("""INSERT OR REPLACE INTO session_log
                (sid,caller_id,callee_id,access,requested,state,reason,authorized_ms,connect_ms,duration_ms)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (entry["sid"], entry["caller_id"], entry["callee_id"], entry["access"],
                        entry["requested"], entry["state"], entry.get("reason"),
                        entry.get("authorized_ms"), entry.get("connect_ms"), entry.get("duration_ms")))
            db.execute("DELETE FROM session_log WHERE requested<?",
                       (time.time() - SESSION_LOG_DAYS * 86400,))
            db.commit()

    def recent_sessions(self, user_id: int, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit), SESSION_LOG_MAX_PER_USER))
        with self.lock, self._db() as db:
            rows = db.execute("""
                SELECT s.*, c.handle AS caller_handle, e.handle AS callee_handle
                FROM session_log s JOIN users c ON s.caller_id=c.id JOIN users e ON s.callee_id=e.id
                WHERE s.caller_id=? OR s.callee_id=? ORDER BY s.requested DESC LIMIT ?
            """, (user_id, user_id, limit)).fetchall()
        items = []
        for row in rows:
            outgoing = row["caller_id"] == user_id
            items.append({"session_id": row["sid"], "direction": "outgoing" if outgoing else "incoming",
                          "peer": row["callee_handle"] if outgoing else row["caller_handle"],
                          "access": row["access"], "requested_at": row["requested"],
                          "state": row["state"], "reason": row["reason"],
                          "authorized_ms": row["authorized_ms"], "connect_ms": row["connect_ms"],
                          "duration_ms": row["duration_ms"]})
        return items
