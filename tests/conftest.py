from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.notifications.sender import DeliveryError

ORGANIZER = {"X-User-Id": "1"}
STUDENT_ONE = {"X-User-Id": "2"}   # Telegram linked
STUDENT_TWO = {"X-User-Id": "3"}   # e-mail only


class FakeNotificationSender:
    """Test double for NotificationSender: records messages, can simulate an outage."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent = []

    def send(self, address: str, text: str) -> None:
        if self.fail:
            raise DeliveryError("channel is down")
        self.sent.append((address, text))


@pytest.fixture
def senders():
    return {"telegram": FakeNotificationSender(), "email": FakeNotificationSender()}


@pytest.fixture
def client(senders):
    """A fresh app with an in-memory database and fake senders (no file, no real services)."""
    return TestClient(create_app(":memory:", senders=senders))


def event_body(**overrides):
    body = {
        "club_id": 1,
        "title": "Robot building workshop",
        "description": "Intro session",
        "starts_at": (datetime.now() + timedelta(days=7)).isoformat(timespec="minutes"),
        "venue": "Room A101",
        "category": "Workshop",
        "capacity": 20,
    }
    body.update(overrides)
    return body


@pytest.fixture
def create_event(client):
    def _create(**overrides) -> int:
        response = client.post("/api/events", json=event_body(**overrides), headers=ORGANIZER)
        assert response.status_code == 201, response.text
        return response.json()["id"]
    return _create
