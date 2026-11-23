"""Users module: where to deliver a message for a user.

A user who linked Telegram gets Telegram messages; everyone else gets e-mail
(Milestone 2 clarification 3).
"""
import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Contact:
    channel: str   # "telegram" or "email"
    address: str   # Telegram chat id or e-mail address


class UserDirectory:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def contact_for(self, user_id: int) -> Optional[Contact]:
        row = self._conn.execute(
            "SELECT email, telegram_chat_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        if row["telegram_chat_id"]:
            return Contact("telegram", row["telegram_chat_id"])
        return Contact("email", row["email"])

    def link_telegram(self, user_id: int, chat_id: int) -> bool:
        """Attach a Telegram chat only if it is available to this user."""
        address = str(chat_id)
        updated = self._conn.execute(
            "UPDATE users SET telegram_chat_id = ? WHERE id = ? AND NOT EXISTS ("
            " SELECT 1 FROM users WHERE telegram_chat_id = ? AND id <> ?)",
            (address, user_id, address, user_id),
        )
        return updated.rowcount == 1

    def unlink_telegram(self, user_id: int) -> None:
        self._conn.execute("UPDATE users SET telegram_chat_id = NULL WHERE id = ?", (user_id,))
