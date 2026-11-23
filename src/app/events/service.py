"""Business rules of the Events module."""
from contextlib import nullcontext
from datetime import date, datetime
from typing import Callable, ContextManager, Iterable, Optional

from ..users.access import AccessPolicy
from .models import Event, NewEvent
from .repository import EventRepository


class EventValidationError(Exception):
    """The event data breaks a business rule."""


class EventNotFound(Exception):
    pass


class EventConflict(Exception):
    pass


class EventService:
    def __init__(self, repository: EventRepository, access: AccessPolicy,
                 clock: Callable[[], datetime] = datetime.now, *,
                 transaction: Callable[[], ContextManager] = nullcontext,
                 member_ids: Callable[[int], Iterable[int]] = lambda _: (),
                 participant_ids: Callable[[int], Iterable[int]] = lambda _: (),
                 enqueue: Optional[Callable[[int, str], None]] = None):
        self._repository = repository
        self._access = access
        self._clock = clock
        self._transaction = transaction
        self._member_ids = member_ids
        self._participant_ids = participant_ids
        self._enqueue = enqueue

    def create_event(self, user_id: int, data: NewEvent) -> Event:
        with self._transaction():
            if self._access.is_club_organizer(user_id, data.club_id):
                self._validate(data)
                event = self._repository.add(data)
                self._notify(self._member_ids(event.club_id), "New club event", event)
                return event
        raise self._access.deny(user_id, "create event for club", str(data.club_id))

    def update_event(self, user_id: int, event_id: int, data: NewEvent) -> Event:
        with self._transaction():
            event = self.get_event(event_id)
            if self._access.is_club_organizer(user_id, event.club_id):
                if event.status != "PUBLISHED":
                    raise EventConflict("A cancelled event cannot be edited")
                if data.club_id != event.club_id:
                    raise EventValidationError("The hosting club cannot be changed")
                self._validate(data)
                participants = tuple(self._participant_ids(event.id))
                if data.capacity < len(participants):
                    raise EventConflict("Capacity cannot be less than the current registration count")
                updated = self._repository.update(event_id, data)
                if updated != event:
                    self._notify(participants, "Event updated", updated)
                return updated
        raise self._access.deny(user_id, "edit event", str(event_id))

    def cancel_event(self, user_id: int, event_id: int) -> Event:
        with self._transaction():
            event = self.get_event(event_id)
            if self._access.is_club_organizer(user_id, event.club_id):
                if event.status == "CANCELLED":
                    return event
                cancelled = self._repository.cancel(event_id)
                self._notify(self._participant_ids(event_id), "Event cancelled", cancelled)
                return cancelled
        raise self._access.deny(user_id, "cancel event", str(event_id))

    def get_event(self, event_id: int) -> Event:
        event = self._repository.get(event_id)
        if event is None:
            raise EventNotFound(f"Event {event_id} not found")
        return event

    def list_events(self, *, q: str = "", category: Optional[str] = None,
                    on_date: Optional[date] = None, club_id: Optional[int] = None,
                    limit: Optional[int] = None, offset: int = 0) -> list[Event]:
        if not any((q, category, on_date, club_id, limit, offset)):
            return self._repository.list_all()
        return self._repository.find(q=q.strip(), category=category, on_date=on_date,
                                     club_id=club_id, limit=limit, offset=offset)

    def upcoming_published(self, start: datetime, end: datetime) -> list[Event]:
        return self._repository.upcoming_published(start, end)

    def categories(self) -> list[str]:
        return self._repository.categories()

    def _validate(self, data: NewEvent) -> None:
        for value, label in ((data.title, "Title"), (data.venue, "Venue"),
                             (data.category, "Category")):
            if not value.strip():
                raise EventValidationError(f"{label} must not be empty")
        if data.starts_at.tzinfo is not None:
            raise EventValidationError("Use a local event date and time without a timezone offset")
        if data.starts_at <= self._clock():
            raise EventValidationError("Event must start in the future")

    def _notify(self, recipients: Iterable[int], action: str, event: Event) -> None:
        if self._enqueue is None:
            return
        message = f"{action}: '{event.title}' on {event.starts_at:%d.%m.%Y %H:%M} at {event.venue}."
        for recipient_id in recipients:
            self._enqueue(recipient_id, message)
