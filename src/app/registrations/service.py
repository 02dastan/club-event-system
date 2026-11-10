"""Business rules of the Registrations module (FR3).

A student registers in one action. The registration and its confirmation message
are saved in ONE transaction (ADR-001); Telegram/SMTP are never called here.
"""
from datetime import datetime
from typing import Callable, ContextManager

from ..events.service import EventService
from ..notifications.outbox import Outbox
from ..users.access import AccessPolicy
from .repository import DuplicateRegistration, Registration, RegistrationRepository


class RegistrationClosed(Exception):
    """The event is full or has already started."""


class RegistrationService:
    def __init__(self, repository: RegistrationRepository, events: EventService,
                 access: AccessPolicy, outbox: Outbox,
                 transaction: Callable[[], ContextManager],
                 clock: Callable[[], datetime] = datetime.now):
        self._repository = repository
        self._events = events
        self._access = access
        self._outbox = outbox
        self._transaction = transaction
        self._clock = clock

    def register(self, student_id: int, event_id: int) -> Registration:
        event = self._events.get_event(event_id)  # raises EventNotFound
        if not self._access.is_student(student_id):
            raise self._access.deny(student_id, "register for event", str(event_id))
        if event.starts_at <= self._clock():
            raise RegistrationClosed("Registration is closed: the event has already started")

        with self._transaction():
            if self._repository.exists(event_id, student_id):
                raise DuplicateRegistration("Student is already registered for this event")
            if self._repository.count_for_event(event_id) >= event.capacity:
                raise RegistrationClosed("Registration is closed: the event is full")
            registration = self._repository.add(
                event_id, student_id, self._clock().isoformat(timespec="seconds"))
            self._outbox.enqueue(
                student_id,
                f"You are registered for '{event.title}' on "
                f"{event.starts_at:%d.%m.%Y %H:%M} at {event.venue}.",
            )
        return registration
