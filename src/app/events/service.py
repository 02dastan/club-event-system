"""Business rules of the Events module.

Other modules (for example Registrations) use events ONLY through EventService,
never through the repository or the events table (dependency rule 2).
"""
import uuid
from datetime import datetime
from typing import Callable, Optional

from ..messaging.event_bus import EventBus
from ..users.access import AccessPolicy
from .domain_events import EventCreated
from .models import Event, NewEvent
from .repository import EventRepository


class EventValidationError(Exception):
    """The event data breaks a business rule."""


class EventNotFound(Exception):
    pass


class EventService:
    def __init__(self, repository: EventRepository, access: AccessPolicy,
                 clock: Callable[[], datetime] = datetime.now,
                 publisher: Optional[EventBus] = None):


        self._repository = repository
        self._access = access
        self._clock = clock
        self._publisher = publisher

    def create_event(self, user_id: int, data: NewEvent) -> Event:
        if not self._access.is_club_organizer(user_id, data.club_id):
            raise self._access.deny(user_id, "create event for club", str(data.club_id))
        if not data.title.strip():
            raise EventValidationError("Title must not be empty")
        if data.starts_at <= self._clock():
            raise EventValidationError("Event must start in the future")
        event = self._repository.add(data)
        if self._publisher is not None:

            
            self._publisher.publish(EventCreated(
                event_id=str(uuid.uuid4()),
                club_event_id=event.id,
                club_id=event.club_id,
                occurred_at=self._clock(),
            ))
        return event

    def get_event(self, event_id: int) -> Event:
        event = self._repository.get(event_id)
        if event is None:
            raise EventNotFound(f"Event {event_id} not found")
        return event

    def list_events(self) -> list[Event]:
        return self._repository.list_all()