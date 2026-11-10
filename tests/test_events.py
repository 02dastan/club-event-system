from datetime import datetime, timedelta

import pytest

from app.events.models import Event, NewEvent
from app.events.service import EventService, EventValidationError
from conftest import ORGANIZER, STUDENT_ONE, event_body


# --- API tests: request -> service -> SQLite (in memory) -> response ---

def test_organizer_creates_event_and_it_appears_in_catalog(client):
    created = client.post("/api/events", json=event_body(), headers=ORGANIZER)

    assert created.status_code == 201
    catalog = client.get("/api/events").json()
    assert [e["title"] for e in catalog] == ["Robot building workshop"]


def test_event_in_the_past_is_rejected(client):
    past = (datetime.now() - timedelta(days=1)).isoformat(timespec="minutes")

    response = client.post("/api/events", json=event_body(starts_at=past), headers=ORGANIZER)

    assert response.status_code == 400
    assert client.get("/api/events").json() == []


def test_capacity_must_be_positive(client):
    response = client.post("/api/events", json=event_body(capacity=0), headers=ORGANIZER)

    assert response.status_code == 422


def test_student_cannot_create_event_and_attempt_is_audited(client):
    """Security scenario: unauthorized request is rejected, nothing changes, attempt recorded."""
    response = client.post("/api/events", json=event_body(), headers=STUDENT_ONE)

    assert response.status_code == 403
    assert client.get("/api/events").json() == []
    audit = client.app.state.db.execute("SELECT user_id, action FROM audit_log").fetchall()
    assert [tuple(r) for r in audit] == [(2, "create event for club")]


# --- Unit test: service with a fake repository, fake access policy and a fixed clock ---

class FakeEventRepository:
    def __init__(self):
        self.saved = []

    def add(self, data: NewEvent) -> Event:
        event = Event(id=len(self.saved) + 1, status="PUBLISHED", **vars(data))
        self.saved.append(event)
        return event

    def get(self, event_id):
        return next((e for e in self.saved if e.id == event_id), None)

    def list_all(self):
        return list(self.saved)


class AllowAll:
    def is_club_organizer(self, user_id, club_id):
        return True


def test_service_uses_injected_clock_for_the_future_date_rule():
    now = datetime(2026, 11, 10, 12, 0)
    repo = FakeEventRepository()
    service = EventService(repo, AllowAll(), clock=lambda: now)
    data = NewEvent(club_id=1, title="Talk", description="", starts_at=now,
                    venue="Hall", category="Talk", capacity=10)

    with pytest.raises(EventValidationError):
        service.create_event(user_id=1, data=data)
    assert repo.saved == []
