"""Notifications module: the transactional outbox (ADR-001).

Business modules call `enqueue` inside their own transaction, so the message is
saved together with the business change or not at all. Nothing here talks to
Telegram or SMTP.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass(frozen=True)
class OutboxMessage:
    id: int
    recipient_id: int
    text: str
    status: str
    attempts: int
    created_at: str
    sent_at: Optional[str]


class Outbox(Protocol):
    def enqueue(self, recipient_id: int, text: str) -> None: ...


class SqliteOutbox:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def enqueue(self, recipient_id: int, text: str) -> None:
        # No commit here: the caller's transaction decides.
        self._conn.execute(
            "INSERT INTO notification_outbox (recipient_id, text, created_at) VALUES (?, ?, ?)",
            (recipient_id, text, _now()),
        )

    def pending(self, limit: int = 20) -> list[OutboxMessage]:
        rows = self._conn.execute(
            "SELECT * FROM notification_outbox WHERE status = 'PENDING' ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
        return [OutboxMessage(**dict(r)) for r in rows]

    def list_all(self) -> list[OutboxMessage]:
        rows = self._conn.execute("SELECT * FROM notification_outbox ORDER BY id DESC").fetchall()
        return [OutboxMessage(**dict(r)) for r in rows]

    def mark_sent(self, message_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE notification_outbox SET status = 'SENT', attempts = attempts + 1, sent_at = ?"
                " WHERE id = ?", (_now(), message_id))

    def mark_attempt_failed(self, message_id: int, max_attempts: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE notification_outbox SET attempts = attempts + 1,"
                " status = CASE WHEN attempts + 1 >= ? THEN 'FAILED' ELSE 'PENDING' END"
                " WHERE id = ?", (max_attempts, message_id))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
