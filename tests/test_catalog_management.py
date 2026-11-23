from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import connect
from app.events.models import NewEvent
from app.events.repository import SqliteEventRepository
from app.events.service import EventService
from app.main import create_app
from app.users.access import AccessPolicy
from conftest import ORGANIZER, STUDENT_ONE, STUDENT_TWO, event_body


ADMIN = {"X-User-Id": "4"}


def test_club_roster_and_membership_permissions(client):
    club = client.get("/api/clubs/1").json()
    assert club["name"] == "SDU Robotics Club"

    membership = "/api/clubs/1/membership"
    assert client.put(membership, headers=ORGANIZER).status_code == 403
    assert client.put(membership, headers=STUDENT_ONE).status_code == 204
    assert client.put(membership, headers=STUDENT_ONE).status_code == 204
    assert client.get("/api/clubs/memberships", headers=STUDENT_ONE).json() == [1]

    members = "/api/clubs/1/members"
    assert client.get(members, headers=STUDENT_TWO).status_code == 403
    assert client.get(members, headers=ORGANIZER).json() == [{"id": 2, "name": "Student One"}]
    assert client.delete(members + "/2", headers=ORGANIZER).status_code == 204
    assert client.get("/api/clubs/memberships", headers=STUDENT_ONE).json() == []
    assert client.delete(membership, headers=STUDENT_ONE).status_code == 204

    new_club = {"name": "Photography Club", "description": "Campus walks", "organizer_id": 1}
    assert client.post("/api/clubs", headers=STUDENT_ONE, json=new_club).status_code == 403
    club = client.post("/api/clubs", headers=ADMIN, json=new_club)
    assert club.status_code == 201
    assert client.get(f"/api/clubs/{club.json()['id']}").json()["description"] == "Campus walks"


def test_event_update_cancel_expand_the_outbox_and_check_capacity(client):
    assert client.put("/api/clubs/1/membership", headers=STUDENT_ONE).status_code == 204
    event = event_body(capacity=2)
    created = client.post("/api/events", headers=ORGANIZER, json=event)
    assert created.status_code == 201
    path = f"/api/events/{created.json()['id']}"
    for student in (STUDENT_ONE, STUDENT_TWO):
        assert client.post(path + "/registrations", headers=student).status_code == 201

    assert client.put(path, headers=STUDENT_TWO, json=event).status_code == 403
    assert client.delete(path, headers=STUDENT_TWO).status_code == 403
    assert client.put(path, headers=ORGANIZER, json={**event, "capacity": 1}).status_code == 409
    assert client.get(path).json()["capacity"] == 2
    assert client.put(path, headers=ORGANIZER, json={**event, "venue": "Hall B"}).status_code == 200
    for _ in range(2):
        assert client.delete(path, headers=ORGANIZER).json()["status"] == "CANCELLED"
    assert client.get(path).json()["status"] == "CANCELLED"
    assert client.get("/api/events").json() == []

    messages = client.app.state.db.execute("SELECT recipient_id, text FROM notification_outbox")
    announcements = [(row["recipient_id"], row["text"].split(":")[0]) for row in messages]
    assert [row for row in announcements if row[1] == "New club event"] == [(2, "New club event")]
    assert [row for row in announcements if row[1] == "Event updated"] == [
        (2, "Event updated"), (3, "Event updated"),
    ]
    assert [row for row in announcements if row[1] == "Event cancelled"] == [
        (2, "Event cancelled"), (3, "Event cancelled"),
    ]
    actions = client.app.state.db.execute("SELECT action FROM audit_log ORDER BY id")
    assert [row["action"] for row in actions] == ["edit event", "cancel event"]


def test_catalog_applies_search_filters_before_pagination(client, create_event):
    start = (datetime.now() + timedelta(days=7)).replace(hour=10, minute=0, second=0, microsecond=0)
    create_event(title="Робототехника — практика", starts_at=start.isoformat(), category="Workshop")
    expected = create_event(
        title="Робототехника — вопросы", starts_at=start.replace(hour=11).isoformat(),
        category="Workshop",
    )
    create_event(title="Робототехника — лекция", starts_at=start.isoformat(), category="Talk")

    response = client.get("/api/events", params={
        "q": "РОБОТОТЕХНИКА",
        "category": "Workshop",
        "date": start.date().isoformat(),
        "club_id": 1,
        "offset": 1,
        "limit": 1,
    })
    assert response.status_code == 200
    assert [event["id"] for event in response.json()] == [expected]
    assert client.get("/api/events/categories").json() == ["Talk", "Workshop"]


def test_catalog_backfills_search_for_old_events_and_follows_edits(tmp_path, senders):
    path = str(tmp_path / "older.db")
    body = event_body(title="СТАРОЕ название")
    conn = connect(path)
    with conn:
        conn.execute(
            "INSERT INTO events (club_id, title, description, starts_at, venue, category, capacity)"
            " VALUES (:club_id, :title, :description, :starts_at, :venue, :category, :capacity)",
            body,
        )
    conn.close()

    app = create_app(path, senders=senders, demo_mode=True)
    with TestClient(app) as client:
        previous = client.get("/api/events", params={"q": "старое"}).json()
        assert len(previous) == 1
        event_id = previous[0]["id"]
        edit = client.put(f"/api/events/{event_id}", headers=ORGANIZER,
                          json={**body, "title": "НОВОЕ название"})
        assert edit.status_code == 200
        assert client.get("/api/events", params={"q": "старое"}).json() == []
        assert client.get("/api/events", params={"q": "новое"}).json() == [edit.json()]


def test_event_creation_rolls_back_if_enqueue_fails():
    conn = connect(":memory:")
    now = datetime.now()

    @contextmanager
    def transaction():
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            yield

    def fail_after_write(student_id, message):
        conn.execute(
            "INSERT INTO notification_outbox (recipient_id, text, created_at) VALUES (?, ?, ?)",
            (student_id, message, now.isoformat()),
        )
        raise RuntimeError("outbox write failed")

    service = EventService(
        SqliteEventRepository(conn), AccessPolicy(conn), transaction=transaction,
        member_ids=lambda _club_id: [2], enqueue=fail_after_write,
    )
    data = NewEvent(1, "Talk", "", now + timedelta(days=1), "Hall", "Talk", 10)
    try:
        with pytest.raises(RuntimeError, match="outbox write failed"):
            service.create_event(1, data)
        assert service.list_events() == []
        assert conn.execute("SELECT count(*) FROM notification_outbox").fetchone()[0] == 0
    finally:
        conn.close()
