from dataclasses import dataclass
from datetime import datetime
import sqlite3
from typing import Callable


@dataclass(frozen=True)
class AccessDenied:
    event_id: int  # The committed audit row identifies this denial.
    user_id: int
    occurred_at: datetime


class AccessDeniedBus:
    def __init__(self):
        self._handlers: list[Callable[[AccessDenied], None]] = []

    def subscribe(self, handler: Callable[[AccessDenied], None]) -> None:
        self._handlers.append(handler)

    def publish(self, event: AccessDenied) -> None:
        for handler in self._handlers:
            handler(event)


class DeniedAttemptCounter:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def handle(self, event: AccessDenied) -> None:
        # Only a fresh receipt fires the database trigger that increments the count.
        with self._conn:
            self._conn.execute(
                "INSERT INTO counted_denials (event_id, user_id) VALUES (?, ?) "
                "ON CONFLICT(event_id) DO NOTHING",
                (event.event_id, event.user_id),
            )
