"""Data access for the Events module. Only this module reads the events table."""
import sqlite3
from contextlib import nullcontext
from datetime import date, datetime
from typing import Optional, Protocol

from .models import Event, NewEvent

EVENTS_SCHEMA = """
CREATE INDEX IF NOT EXISTS events_catalog_order_idx ON events (status, starts_at, id);
"""

SEARCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS event_search (
    event_id INTEGER PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE,
    normalized TEXT NOT NULL
)
"""


class EventRepository(Protocol):
    def add(self, data: NewEvent) -> Event: ...
    def get(self, event_id: int) -> Optional[Event]: ...
    def update(self, event_id: int, data: NewEvent) -> Event: ...
    def cancel(self, event_id: int) -> Event: ...
    def list_all(self) -> list[Event]: ...
    def find(self, *, q: str, category: Optional[str], on_date: Optional[date],
             club_id: Optional[int], limit: Optional[int], offset: int) -> list[Event]: ...
    def categories(self) -> list[str]: ...
    def upcoming_published(self, start: datetime, end: datetime) -> list[Event]: ...


class SqliteEventRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._backfill_search()

    def _write(self):
        # Standalone writes commit here. An enclosing transaction can also enqueue notifications.
        return nullcontext() if self._conn.in_transaction else self._conn

    def _backfill_search(self) -> None:
        # Existing event records predate the normalized search text.
        with self._write():
            self._conn.execute(SEARCH_SCHEMA)
            self._conn.create_function("event_casefold", 1, str.casefold, deterministic=True)
            self._conn.execute(
                "INSERT INTO event_search (event_id, normalized)"
                " SELECT id, event_casefold(title || char(10) || description || char(10) || venue)"
                " FROM events LEFT JOIN event_search ON event_search.event_id = events.id"
                " WHERE event_search.event_id IS NULL",
            )

    def _save_search(self, event_id: int, data: NewEvent) -> None:
        normalized = "\n".join((data.title, data.description, data.venue)).casefold()
        self._conn.execute(
            "INSERT INTO event_search (event_id, normalized) VALUES (?, ?)"
            " ON CONFLICT (event_id) DO UPDATE SET normalized = excluded.normalized",
            (event_id, normalized),
        )

    def add(self, data: NewEvent) -> Event:
        with self._write():
            cursor = self._conn.execute(
                "INSERT INTO events (club_id, title, description, starts_at, venue, category, capacity)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (data.club_id, data.title, data.description, data.starts_at.isoformat(),
                 data.venue, data.category, data.capacity),
            )
            self._save_search(cursor.lastrowid, data)
            return self.get(cursor.lastrowid)

    def get(self, event_id: int) -> Optional[Event]:
        row = self._conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return _to_event(row) if row else None

    def update(self, event_id: int, data: NewEvent) -> Event:
        with self._write():
            self._conn.execute(
                "UPDATE events SET title = ?, description = ?, starts_at = ?, venue = ?,"
                " category = ?, capacity = ? WHERE id = ?",
                (data.title, data.description, data.starts_at.isoformat(), data.venue,
                 data.category, data.capacity, event_id),
            )
            self._save_search(event_id, data)
            return self.get(event_id)

    def cancel(self, event_id: int) -> Event:
        with self._write():
            self._conn.execute("UPDATE events SET status = 'CANCELLED' WHERE id = ?", (event_id,))
            return self.get(event_id)

    def list_all(self) -> list[Event]:
        return self.find(q="", category=None, on_date=None, club_id=None, limit=None, offset=0)

    def find(self, *, q: str, category: Optional[str], on_date: Optional[date],
             club_id: Optional[int], limit: Optional[int], offset: int) -> list[Event]:
        filters = ["status = 'PUBLISHED'"]
        source = "events"
        params = []
        if q:
            source += " JOIN event_search ON event_search.event_id = events.id"
            filters.append("instr(event_search.normalized, ?) > 0")
            params.append(q.casefold())
        if category is not None:
            filters.append("category = ?")
            params.append(category)
        if on_date is not None:
            filters.append("substr(starts_at, 1, 10) = ?")
            params.append(on_date.isoformat())
        if club_id is not None:
            filters.append("club_id = ?")
            params.append(club_id)

        where = " AND ".join(filters)
        rows = self._conn.execute(
            f"SELECT events.* FROM {source} WHERE {where} ORDER BY starts_at, id LIMIT ? OFFSET ?",
            (*params, limit if limit is not None else -1, offset),
        )
        return [_to_event(row) for row in rows]

    def upcoming_published(self, start: datetime, end: datetime) -> list[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE status = 'PUBLISHED' AND starts_at > ? AND starts_at <= ?"
            " ORDER BY starts_at, id",
            (start.isoformat(), end.isoformat()),
        )
        return [_to_event(row) for row in rows]

    def categories(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT category FROM events WHERE status = 'PUBLISHED'"
            " ORDER BY category COLLATE NOCASE, category",
        )
        return [row["category"] for row in rows]


def _to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"], club_id=row["club_id"], title=row["title"],
        description=row["description"], starts_at=datetime.fromisoformat(row["starts_at"]),
        venue=row["venue"], category=row["category"], capacity=row["capacity"],
        status=row["status"],
    )
