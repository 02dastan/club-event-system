"""Business facts of the Events module that have already happened."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EventCreated:
    event_id: str
    club_event_id: int
    club_id: int
    occurred_at: datetime