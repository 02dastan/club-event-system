from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewEvent:
    """Data an organizer sends to create an event."""
    club_id: int
    title: str
    description: str
    starts_at: datetime
    venue: str
    category: str
    capacity: int


@dataclass(frozen=True)
class Event:
    id: int
    club_id: int
    title: str
    description: str
    starts_at: datetime
    venue: str
    category: str
    capacity: int
    status: str
