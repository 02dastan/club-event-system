"""Schedule a reminder per confirmed participant and event start time."""
from datetime import datetime, timedelta
from typing import Callable, ContextManager, Iterable, Protocol

from .outbox import SqliteOutbox


class UpcomingEvent(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def title(self) -> str: ...

    @property
    def starts_at(self) -> datetime: ...

    @property
    def venue(self) -> str: ...


class ReminderJob:
    def __init__(self, outbox: SqliteOutbox,
                 due_events: Callable[[datetime, datetime], Iterable[UpcomingEvent]],
                 participant_ids: Callable[[int], Iterable[int]],
                 transaction: Callable[[], ContextManager],
                 clock: Callable[[], datetime] = datetime.now,
                 lead_time: timedelta = timedelta(hours=24)):
        self._outbox = outbox
        self._due_events = due_events
        self._participant_ids = participant_ids
        self._transaction = transaction
        self._clock = clock
        self._lead_time = lead_time

    def enqueue_due(self) -> int:
        now = self._clock()
        queued = 0
        with self._transaction():
            for event in self._due_events(now, now + self._lead_time):
                message = f"Reminder: '{event.title}' starts on {event.starts_at:%d.%m.%Y %H:%M} at {event.venue}."
                for recipient_id in self._participant_ids(event.id):
                    queued += self._outbox.enqueue_reminder(event.id, recipient_id, event.starts_at, message)
        return queued
