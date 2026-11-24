"""Business facts published by the Registrations module."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StudentRegistered:
    event_id: str
    registration_id: int
    student_id: int
    occurred_at: datetime
