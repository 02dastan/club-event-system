"""Business rules of the Registrations module (FR3).

A student registers in one action. The registration and its confirmation message
are saved in ONE transaction (ADR-001); Telegram/SMTP are never called here.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, ContextManager

from ..events.models import Event
from ..events.service import EventService
from ..notifications.outbox import Outbox
from ..users.access import AccessPolicy, PermissionDenied
from .repository import DuplicateRegistration, Registration, RegistrationRepository


class RegistrationClosed(Exception):
    """The event cannot accept new participants."""


@dataclass(frozen=True)
class StudentRegistration:
    registration: Registration
    event: Event


@dataclass(frozen=True)
class Participant:
    student_id: int
    name: str
    registered_at: str


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
        if not self._access.is_student(student_id):
            raise self._access.deny(student_id, "register for event", str(event_id))
        with self._transaction():
            event = self._events.get_event(event_id)
            if event.status == "CANCELLED":
                raise RegistrationClosed("Registration is closed: the event was cancelled")
            if event.starts_at <= self._clock():
                raise RegistrationClosed("Registration is closed: the event has already started")
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

    def for_student(self, student_id: int) -> list[StudentRegistration]:
        if not self._access.is_student(student_id):
            raise self._access.deny(student_id, "view student registrations", str(student_id))
        entries = [StudentRegistration(row, self._events.get_event(row.event_id))
                   for row in self._repository.for_student(student_id)]
        return sorted(entries, key=lambda entry: entry.event.starts_at)

    def cancel(self, student_id: int, event_id: int) -> None:
        if not self._access.is_student(student_id):
            raise self._access.deny(student_id, "cancel student registration", str(event_id))
        with self._transaction():
            self._events.get_event(event_id)
            self._repository.remove(event_id, student_id)

    def participant_ids(self, event_id: int) -> list[int]:
        return [row.student_id for row in self._repository.for_event(event_id)]

    def participants(self, organizer_id: int, event_id: int) -> list[Participant]:
        event = self._events.get_event(event_id)
        if not self._access.is_club_organizer(organizer_id, event.club_id):
            raise self._access.deny(organizer_id, "view event participants", str(event_id))
        rows = self._repository.for_event(event_id)
        names = self._access.names_for([row.student_id for row in rows])
        return [Participant(row.student_id, names[row.student_id], row.created_at) for row in rows]

    def remove_participant(self, organizer_id: int, event_id: int, student_id: int) -> None:
        try:
            with self._transaction():
                event = self._events.get_event(event_id)
                if not self._access.is_club_organizer(organizer_id, event.club_id):
                    raise PermissionDenied()
                if self._repository.remove(event_id, student_id):
                    self._outbox.enqueue(student_id, f"Your registration for '{event.title}' was cancelled by the organizer.")
        except PermissionDenied:
            raise self._access.deny(organizer_id, "remove event participant", str(event_id)) from None
