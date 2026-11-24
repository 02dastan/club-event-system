from datetime import datetime
from uuid import UUID, uuid4

from app.registrations.domain_events import StudentRegistered
from conftest import STUDENT_ONE


def test_successful_registration_publishes_after_commit_and_writes_audit(client, create_event, monkeypatch):
    event_id = create_event()
    db = client.app.state.db
    bus = client.app.state.event_bus
    publish = bus.publish
    published = []

    def observe_publication(fact):
        assert not db.in_transaction
        published.append(fact)
        publish(fact)

    monkeypatch.setattr(bus, "publish", observe_publication)
    path = f"/api/events/{event_id}/registrations"
    response = client.post(path, headers=STUDENT_ONE)

    assert response.status_code == 201
    registration = response.json()["registration"]
    assert len(published) == 1
    fact = published[0]
    assert isinstance(fact, StudentRegistered)
    assert UUID(fact.event_id).version == 4
    assert fact.registration_id == registration["id"]
    assert fact.student_id == registration["student_id"] == 2
    assert fact.occurred_at == datetime.fromisoformat(registration["created_at"])

    rows = db.execute(
        "SELECT user_id, target, created_at FROM audit_log WHERE action = 'STUDENT_REGISTERED'"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        (2, str(registration["id"]), fact.occurred_at.isoformat()),
    ]

    assert client.post(path, headers=STUDENT_ONE).status_code == 409
    assert published == [fact]


def test_duplicate_delivery_creates_only_one_registration_audit_entry(client):
    bus = client.app.state.event_bus
    db = client.app.state.db
    fact = StudentRegistered(
        event_id=str(uuid4()), registration_id=42, student_id=2,
        occurred_at=datetime(2026, 11, 24, 14, 30),
    )

    bus.publish(fact)
    bus.publish(fact)

    rows = db.execute(
        "SELECT user_id, target, created_at FROM audit_log WHERE action = 'STUDENT_REGISTERED'"
    ).fetchall()
    assert [tuple(row) for row in rows] == [(2, "42", fact.occurred_at.isoformat())]
    assert db.execute(
        "SELECT COUNT(*) FROM processed_events WHERE consumer = ? AND event_id = ?",
        ("registration_audit", fact.event_id),
    ).fetchone()[0] == 1
