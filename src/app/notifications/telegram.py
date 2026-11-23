"""One-time codes and a polling adapter for linking Telegram chats to accounts."""
import hashlib
import re
import secrets
import sqlite3
import time
from typing import Callable, ContextManager, Optional, Protocol

from ..users.contacts import UserDirectory


class SqliteTelegramLinks:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def replace_code(self, user_id: int, code_hash: str, expires_at: int, now: int) -> None:
        self._conn.execute("DELETE FROM telegram_link_codes WHERE expires_at <= ?", (now,))
        self._conn.execute(
            "INSERT INTO telegram_link_codes (user_id, code_hash, expires_at) VALUES (?, ?, ?)"
            " ON CONFLICT (user_id) DO UPDATE SET code_hash = excluded.code_hash,"
            " expires_at = excluded.expires_at",
            (user_id, code_hash, expires_at),
        )

    def valid_user_id(self, code_hash: str, now: int) -> Optional[int]:
        row = self._conn.execute(
            "SELECT user_id FROM telegram_link_codes WHERE code_hash = ? AND expires_at > ?",
            (code_hash, now),
        ).fetchone()
        return row["user_id"] if row else None

    def delete_code(self, user_id: int) -> None:
        self._conn.execute("DELETE FROM telegram_link_codes WHERE user_id = ?", (user_id,))


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class TelegramLinkService:
    EXPIRES_IN = 10 * 60

    def __init__(self, repository: SqliteTelegramLinks, contacts: UserDirectory,
                 transaction: Callable[[], ContextManager], bot_username: str,
                 clock: Callable[[], float] = time.time):
        username = bot_username.strip().removeprefix("@")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", username):
            raise ValueError("TELEGRAM_BOT_USERNAME must be the Telegram bot username")
        self._repository = repository
        self._contacts = contacts
        self._transaction = transaction
        self._bot_username = username
        self._clock = clock

    def issue_link(self, user_id: int) -> str:
        code = secrets.token_urlsafe(24)
        now = int(self._clock())
        with self._transaction():
            self._repository.replace_code(user_id, _hash_code(code), now + self.EXPIRES_IN, now)
        return f"https://t.me/{self._bot_username}?start={code}"

    def consume(self, code: str, chat_id: int) -> bool:
        if chat_id <= 0 or not re.fullmatch(r"[A-Za-z0-9_-]{32}", code):
            return False
        with self._transaction():
            user_id = self._repository.valid_user_id(_hash_code(code), int(self._clock()))
            if user_id is None or not self._contacts.link_telegram(user_id, chat_id):
                return False
            self._repository.delete_code(user_id)
            return True

    def unlink(self, user_id: int) -> None:
        with self._transaction():
            self._repository.delete_code(user_id)
            self._contacts.unlink_telegram(user_id)


class TelegramUpdates(Protocol):
    def get_updates(self, offset: Optional[int] = None) -> list[dict]: ...


class TelegramLinkPoller:
    """Read bot updates in one worker and confirm processed IDs on the next poll."""

    def __init__(self, api: TelegramUpdates, links: TelegramLinkService):
        self._api = api
        self._links = links
        self._offset: Optional[int] = None

    def poll(self) -> int:
        updates = self._api.get_updates(offset=self._offset)
        self._offset = None
        linked = 0
        for update in updates:
            update_id = update["update_id"]
            message = update.get("message", {})
            chat = message.get("chat", {})
            words = message.get("text", "").split()
            if chat.get("type") == "private" and len(words) == 2 and words[0] == "/start":
                linked += self._links.consume(words[1], chat["id"])
            self._offset = max(self._offset or 0, update_id + 1)
        return linked
