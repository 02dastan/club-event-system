"""Consumer of EventCreated: keeps a counter of created events for every club."""
import sqlite3

from ..events.domain_events import EventCreated

CONSUMER_NAME = "club_statistics"


class ClubStatisticsConsumer:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def handle(self, event: EventCreated) -> None:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO processed_events (consumer, event_id) VALUES (?, ?)",
                (CONSUMER_NAME, event.event_id),
            )
            if cursor.rowcount == 0:
                return
            self._conn.execute(
                "INSERT INTO club_stats (club_id, events_created, last_event_at) VALUES (?, 1, ?)"
                " ON CONFLICT (club_id) DO UPDATE SET"
                " events_created = events_created + 1, last_event_at = excluded.last_event_at",
                (event.club_id, event.occurred_at.isoformat()),
            )

    def events_created(self, club_id: int) -> int:
        row = self._conn.execute(
            "SELECT events_created FROM club_stats WHERE club_id = ?", (club_id,)
        ).fetchone()
        return row["events_created"] if row else 0