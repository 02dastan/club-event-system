"""Data access for the Events module. Only this module reads the events table."""
import sqlite3
from datetime import datetime
from typing import Optional, Protocol

from .models import Event, NewEvent


class EventRepository(Protocol):
    def add(self, data: NewEvent) -> Event: ...
    def get(self, event_id: int) -> Optional[Event]: ...
    def list_all(self) -> list[Event]: ...


class SqliteEventRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, data: NewEvent) -> Event:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO events (club_id, title, description, starts_at, venue, category, capacity)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (data.club_id, data.title, data.description, data.starts_at.isoformat(),
                 data.venue, data.category, data.capacity),
            )
        return self.get(cursor.lastrowid)

    def get(self, event_id: int) -> Optional[Event]:
        row = self._conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return _to_event(row) if row else None

    def list_all(self) -> list[Event]:
        rows = self._conn.execute("SELECT * FROM events ORDER BY starts_at").fetchall()
        return [_to_event(r) for r in rows]


def _to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"], club_id=row["club_id"], title=row["title"],
        description=row["description"], starts_at=datetime.fromisoformat(row["starts_at"]),
        venue=row["venue"], category=row["category"], capacity=row["capacity"],
        status=row["status"],
    )
