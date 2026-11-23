from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.database import connect
from app.events.models import NewEvent
from app.events.repository import SqliteEventRepository
from app.events.service import EventService
from app.main import create_app
from app.registrations.repository import SqliteRegistrationRepository
from app.registrations.service import RegistrationClosed, RegistrationService
from app.users.access import AccessPolicy
from conftest import ORGANIZER, STUDENT_ONE, STUDENT_TWO, event_body


def registrations_count(client):
    return client.app.state.db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]


# --- Normal successful case (end to end through the API) ---

def test_student_registers_and_confirmation_is_queued(client, create_event):
    event_id = create_event()

    response = client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_ONE)

    assert response.status_code == 201
    assert response.json()["registration"]["student_id"] == 2
    outbox = client.get("/api/notifications").json()
    assert len(outbox) == 1
    assert outbox[0]["status"] == "PENDING"
    assert "Robot building workshop" in outbox[0]["text"]


# --- Business rule: one registration per student per event ---

def test_student_cannot_register_twice_for_the_same_event(client, create_event):
    event_id = create_event()
    client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_ONE)

    second = client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_ONE)

    assert second.status_code == 409
    assert registrations_count(client) == 1
    assert len(client.get("/api/notifications").json()) == 1  # no second confirmation


# --- Invalid / failure cases ---

def test_registration_rejected_when_event_is_full(client, create_event):
    event_id = create_event(capacity=1)
    client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_ONE)

    response = client.post(f"/api/events/{event_id}/registrations", headers=STUDENT_TWO)

    assert response.status_code == 409
    assert "full" in response.json()["detail"]
    assert registrations_count(client) == 1


def test_registration_for_unknown_event_returns_404(client):
    response = client.post("/api/events/999/registrations", headers=STUDENT_ONE)

    assert response.status_code == 404


def test_organizer_cannot_register_as_participant(client, create_event):
    event_id = create_event()

    response = client.post(f"/api/events/{event_id}/registrations", headers=ORGANIZER)

    assert response.status_code == 403
    assert registrations_count(client) == 0


# --- Design rule: registration and outbox message are one transaction (ADR-001) ---

class BrokenOutbox:
    def enqueue(self, recipient_id, text):
        raise RuntimeError("outbox write failed")


def test_registration_is_rolled_back_if_outbox_write_fails():
    conn = connect(":memory:")
    access = AccessPolicy(conn)
    events = EventService(SqliteEventRepository(conn), access)
    event = events.create_event(1, NewEvent(1, "Talk", "", datetime.now() + timedelta(days=1),
                                            "Hall", "Talk", 10))
    service = RegistrationService(SqliteRegistrationRepository(conn), events, access,
                                  BrokenOutbox(), transaction=lambda: conn)

    with pytest.raises(RuntimeError):
        service.register(student_id=2, event_id=event.id)

    assert conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 0


def test_registration_closed_after_event_started():
    conn = connect(":memory:")
    access = AccessPolicy(conn)
    start = datetime(2026, 12, 1, 15, 0)
    events = EventService(SqliteEventRepository(conn), access, clock=lambda: start - timedelta(days=1))
    event = events.create_event(1, NewEvent(1, "Talk", "", start, "Hall", "Talk", 10))
    service = RegistrationService(SqliteRegistrationRepository(conn), events, access,
                                  outbox=None, transaction=lambda: conn,
                                  clock=lambda: start + timedelta(minutes=5))

    with pytest.raises(RegistrationClosed):
        service.register(student_id=2, event_id=event.id)


def test_cancel_registration_releases_seat_and_updates_my_list(client, create_event):
    event_id = create_event(capacity=1)
    registrations = f"/api/events/{event_id}/registrations"
    assert client.post(registrations, headers=STUDENT_ONE).status_code == 201

    mine = client.get("/api/registrations/me", headers=STUDENT_ONE)
    assert [entry["event"]["id"] for entry in mine.json()] == [event_id]
    assert client.get(registrations, headers=STUDENT_TWO).status_code == 403
    assert client.get(registrations, headers=ORGANIZER).json()[0]["student_id"] == 2

    assert client.delete(f"{registrations}/me", headers=STUDENT_TWO).status_code == 204
    assert client.post(registrations, headers=STUDENT_TWO).status_code == 409
    assert client.delete(f"{registrations}/me", headers=STUDENT_ONE).status_code == 204
    assert client.get("/api/registrations/me", headers=STUDENT_ONE).json() == []
    assert client.post(registrations, headers=STUDENT_TWO).status_code == 201


def test_concurrent_requests_cannot_overbook_the_last_seat(tmp_path, senders):
    app = create_app(tmp_path / "last-seat.db", senders=senders, demo_mode=True)
    with TestClient(app) as session:
        event_id = session.post("/api/events", json=event_body(capacity=1), headers=ORGANIZER).json()["id"]
        registrations = f"/api/events/{event_id}/registrations"
        start = Barrier(2, timeout=5)

        def register(headers):
            start.wait()
            return session.post(registrations, headers=headers).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(register, [STUDENT_ONE, STUDENT_TWO]))

        assert sorted(results) == [201, 409]
        assert len(session.get(registrations, headers=ORGANIZER).json()) == 1
        assert len(session.get("/api/notifications").json()) == 1
